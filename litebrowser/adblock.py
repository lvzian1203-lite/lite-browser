"""用户手动标记的广告屏蔽。

面向「你在网页上看到的那个广告弹窗」这种具体目标：用户点一下它，
程序记住一条针对该域名的元素规则，以后打开同一网站就自动隐藏它。

设计要点：

* **规则按域名保存**（``adblock.json``），可随时在设置里查看与删除；
* 点选模式下鼠标悬停会实时描边高亮，点击即记录，按 Esc 退出；
* 生成选择器时优先用 ``id``，其次用稳定的 class 组合，最后才退化为
  结构路径，避免规则过于脆弱或误伤；
* 规则通过注入 ``<style>`` + ``MutationObserver`` 应用，
  动态插入的广告也能被隐藏；
* 结果通过 ``lite:adpick?selector=...`` 内部命令回传主窗口，
  WebView2 与 QtWebEngine 两种内核都能用。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .config import data_dir

#: 单条选择器最长长度（防止异常数据）
MAX_SELECTOR = 300

#: 一次点选允许生成的选择器（主选择器 + 备用）
PICK_COMMAND = "lite:adpick"


@dataclass
class AdRule:
    """一条按域名生效的屏蔽规则。"""

    domain: str
    selector: str
    created_at: float = field(default_factory=time.time)
    note: str = ""

    @property
    def time_text(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.created_at))


def normalize_domain(url: str) -> str:
    """取出用于规则匹配的主机名（不含端口，统一小写）。"""
    text = (url or "").strip()
    if not text:
        return ""
    if text.lower().startswith("file:"):
        return "本地文件"
    match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)", text)
    host = match.group(1) if match else text.split("/", 1)[0]
    host = host.split("@")[-1].split(":")[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def rule_applies(rule_domain: str, domain: str) -> bool:
    """规则是否适用于该域名（支持 ``*.example.com`` 与 ``example.com`` 后缀匹配）。"""
    if not rule_domain or not domain:
        return False
    if rule_domain == domain:
        return True
    if rule_domain.startswith("*."):
        base = rule_domain[2:]
        return domain == base or domain.endswith("." + base)
    return domain.endswith("." + rule_domain)


class AdRuleStore:
    """广告屏蔽规则的持久化存储（明文 JSON，便于用户直接编辑与迁移）。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else data_dir() / "adblock.json"
        self.rules: list[AdRule] = []
        self.block_popups: bool = True
        self.load()

    # -- 读写 ------------------------------------------------------------- #
    def load(self) -> None:
        self.rules = []
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.block_popups = bool(raw.get("block_popups", True))
        for item in raw.get("rules", []):
            if not isinstance(item, dict):
                continue
            selector = str(item.get("selector") or "").strip()
            domain = str(item.get("domain") or "").strip().lower()
            if not selector or not domain:
                continue
            self.rules.append(
                AdRule(
                    domain=domain,
                    selector=selector[:MAX_SELECTOR],
                    created_at=float(item.get("created_at") or time.time()),
                    note=str(item.get("note") or ""),
                )
            )

    def save(self) -> None:
        payload = {
            "version": 1,
            "block_popups": bool(self.block_popups),
            "rules": [
                {
                    "domain": rule.domain,
                    "selector": rule.selector,
                    "created_at": rule.created_at,
                    "note": rule.note,
                }
                for rule in self.rules
            ],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    # -- 查询与修改 ------------------------------------------------------- #
    def selectors_for(self, url: str) -> list[str]:
        """返回适用于该网址的选择器列表（去重、保持顺序）。"""
        domain = normalize_domain(url)
        if not domain:
            return []
        found: list[str] = []
        for rule in self.rules:
            if rule_applies(rule.domain, domain) and rule.selector not in found:
                found.append(rule.selector)
        return found

    def add(self, url_or_domain: str, selector: str, note: str = "") -> AdRule | None:
        selector = (selector or "").strip()[:MAX_SELECTOR]
        domain = normalize_domain(url_or_domain)
        if not selector or not domain:
            return None
        for rule in self.rules:
            if rule.domain == domain and rule.selector == selector:
                return rule
        rule = AdRule(domain=domain, selector=selector, note=note)
        self.rules.append(rule)
        self.save()
        return rule

    def remove(self, rule: AdRule) -> bool:
        if rule in self.rules:
            self.rules.remove(rule)
            self.save()
            return True
        return False

    def remove_domain(self, domain: str) -> int:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.domain != domain]
        if len(self.rules) != before:
            self.save()
        return before - len(self.rules)

    def clear(self) -> None:
        self.rules = []
        self.save()

    def domains(self) -> list[str]:
        return sorted({rule.domain for rule in self.rules})

    def set_block_popups(self, enabled: bool) -> None:
        self.block_popups = bool(enabled)
        self.save()


# --------------------------------------------------------------------------- #
# 注入脚本
# --------------------------------------------------------------------------- #
def apply_script(selectors: Iterable[str]) -> str:
    """生成隐藏指定元素并持续监听动态内容的脚本。"""
    safe = [s for s in selectors if s][:200]
    if not safe:
        return "void 0"
    payload = json.dumps(safe, ensure_ascii=False)
    return f"""
(function () {{
  if (window.__liteAdblockReady) {{ window.__liteAdblockApply && window.__liteAdblockApply(); return; }}
  var selectors = {payload};
  var STYLE_ID = '__lite_adblock_style';
  function cssText() {{
    return selectors.map(function (s) {{
      return s + '{{display:none !important;visibility:hidden !important;}}';
    }}).join('\\n');
  }}
  function ensureStyle() {{
    var style = document.getElementById(STYLE_ID);
    if (!style) {{
      style = document.createElement('style');
      style.id = STYLE_ID;
      style.type = 'text/css';
      (document.head || document.documentElement).appendChild(style);
    }}
    if (style.textContent !== cssText()) style.textContent = cssText();
  }}
  window.__liteAdblockApply = ensureStyle;
  ensureStyle();
  // 有些广告脚本会把我们的样式删掉，或被隐藏后又重新插入，这里持续补刀
  if (!window.__liteAdblockObserver) {{
    var observer = new MutationObserver(function () {{
      ensureStyle();
      if (!document.getElementById(STYLE_ID)) ensureStyle();
    }});
    observer.observe(document.documentElement || document, {{
      childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class']
    }});
    window.__liteAdblockObserver = observer;
    document.addEventListener('DOMContentLoaded', ensureStyle);
    setInterval(ensureStyle, 3000);
  }}
  window.__liteAdblockReady = true;
}})();
""".strip()


def picker_script() -> str:
    """生成「点选广告元素」模式的脚本。"""
    return r"""
(function () {
  if (window.__liteAdPicker) { window.__liteAdPicker.cancel(); return; }
  var box = document.createElement('div');
  box.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;'
    + 'border:2px solid #FF3B30;background:rgba(255,59,48,0.18);border-radius:3px;'
    + 'box-shadow:0 0 0 9999px rgba(0,0,0,0.06);transition:all .05s linear;display:none';
  var tip = document.createElement('div');
  tip.style.cssText = 'position:fixed;z-index:2147483647;left:50%;top:12px;transform:translateX(-50%);'
    + 'background:#2B2B2B;color:#fff;padding:8px 16px;border-radius:8px;'
    + 'font:13px/1.5 "Microsoft YaHei",sans-serif;pointer-events:none;box-shadow:0 4px 16px rgba(0,0,0,.3)';
  tip.textContent = '广告标记模式：点击要屏蔽的元素，按 Esc 取消';
  var hint = document.createElement('div');
  hint.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;'
    + 'background:#FF3B30;color:#fff;padding:3px 8px;border-radius:4px;'
    + 'font:12px Consolas,monospace;display:none;max-width:70vw;overflow:hidden;'
    + 'white-space:nowrap;text-overflow:ellipsis';
  function esc(s) { return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/([^\w-])/g, '\\$1'); }

  function isJunk(el) {
    return !el || el === document.documentElement || el === document.body;
  }

  // 生成尽量稳定的选择器：优先 id，其次 class 组合，最后退回结构路径
  function selectorFor(el) {
    if (!el || el.nodeType !== 1) return '';
    if (el.id && !/^\d/.test(el.id) && el.id.length < 60) return '#' + esc(el.id);
    var parts = [];
    var node = el;
    var depth = 0;
    while (node && node.nodeType === 1 && depth < 5 && !isJunk(node)) {
      var part = node.tagName.toLowerCase();
      var cls = (node.className && typeof node.className === 'string')
        ? node.className.trim().split(/\s+/).filter(function (c) {
            return c && c.length < 32 && !/^(active|selected|hover|focus|show|hide|ng-|css-|jsx-)/i.test(c);
          }).slice(0, 3) : [];
      if (cls.length) part += '.' + cls.map(esc).join('.');
      else {
        var parent = node.parentElement;
        if (parent) {
          var same = Array.prototype.filter.call(parent.children, function (c) {
            return c.tagName === node.tagName;
          });
          if (same.length > 1) part += ':nth-of-type(' + (same.indexOf(node) + 1) + ')';
        }
      }
      parts.unshift(part);
      if (node.id && !/^\d/.test(node.id) && node.id.length < 60) {
        parts[0] = '#' + esc(node.id);
        break;
      }
      node = node.parentElement;
      depth++;
    }
    var selector = parts.join(' > ');
    // 校验选择器唯一性，避免误伤整块内容
    try {
      var hits = document.querySelectorAll(selector);
      if (hits.length > 12) return parts.slice(-1)[0];
    } catch (e) { return ''; }
    return selector;
  }

  function move(event) {
    var el = event.target;
    if (isJunk(el)) { box.style.display = 'none'; hint.style.display = 'none'; return; }
    var rect = el.getBoundingClientRect();
    box.style.display = 'block';
    box.style.left = rect.left + 'px';
    box.style.top = rect.top + 'px';
    box.style.width = rect.width + 'px';
    box.style.height = rect.height + 'px';
    var sel = selectorFor(el);
    hint.textContent = sel + '  （' + Math.round(rect.width) + '×' + Math.round(rect.height) + '）';
    hint.style.display = 'block';
    hint.style.left = Math.min(rect.left, window.innerWidth - 320) + 'px';
    hint.style.top = Math.max(4, rect.top - 26) + 'px';
  }

  function click(event) {
    event.preventDefault();
    event.stopPropagation();
    var selector = selectorFor(event.target);
    cancel();
    if (!selector) { alert('这个元素无法生成稳定的选择器，请换一个试试。'); return; }
    // WebView2 优先用 postMessage 回传：导航会被内核忽略或导致页面被替换，
    // 用消息通道更可靠；QtWebEngine 没有该接口，退回 lite: 内部命令。
    try {
      if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
        window.chrome.webview.postMessage(JSON.stringify({
          __lite: 'adpick', selector: selector, host: location.hostname
        }));
        return;
      }
    } catch (e) {}
    try {
      var url = 'lite:adpick?selector=' + encodeURIComponent(selector)
        + '&host=' + encodeURIComponent(location.hostname);
      location.href = url;
    } catch (e) {}
  }

  function key(event) {
    if (event.key === 'Escape') { event.preventDefault(); cancel(); }
  }

  function cancel() {
    document.removeEventListener('mousemove', move, true);
    document.removeEventListener('click', click, true);
    document.removeEventListener('keydown', key, true);
    if (box.parentNode) box.parentNode.removeChild(box);
    if (tip.parentNode) tip.parentNode.removeChild(tip);
    if (hint.parentNode) hint.parentNode.removeChild(hint);
    window.__liteAdPicker = null;
  }

  document.documentElement.appendChild(box);
  document.documentElement.appendChild(tip);
  document.documentElement.appendChild(hint);
  document.addEventListener('mousemove', move, true);
  document.addEventListener('click', click, true);
  document.addEventListener('keydown', key, true);
  window.__liteAdPicker = { cancel: cancel };
})();
""".strip()


def parse_pick_command(url: str) -> tuple[str, str]:
    """解析 ``lite:adpick?selector=...&host=...``，返回 (选择器, 主机名)。"""
    from urllib.parse import parse_qs, unquote, urlparse

    text = url or ""
    query = text.split("?", 1)[1] if "?" in text else ""
    params = parse_qs(query, keep_blank_values=True)
    selector = unquote((params.get("selector") or [""])[0]).strip()
    host = unquote((params.get("host") or [""])[0]).strip()
    return selector[:MAX_SELECTOR], host
