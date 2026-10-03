"""油猴（用户脚本）支持。

* 解析 Greasemonkey / Tampermonkey 的 ``==UserScript==`` 元数据块；
* 支持 ``@match`` / ``@include`` / ``@exclude`` / ``@run-at`` / ``@grant`` / ``@require``；
* 生成注入脚本：内置 GM API 兼容层（GM_getValue / GM_setValue / GM_addStyle /
  GM_xmlhttpRequest / GM_openInTab / GM_notification / GM_registerMenuCommand /
  GM_setClipboard / unsafeWindow / GM_info）；
* GM 数据由宿主持久化（与书签、历史一样走加密存储），
  ``GM_xmlhttpRequest`` 由宿主发起请求，从而绕过浏览器同源限制。

脚本目录：``<数据目录>/userscripts/<脚本 ID>.user.js``
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from .crypto import DataVault

META_BLOCK = re.compile(r"//\s*==UserScript==(.*?)//\s*==/UserScript==", re.S)
META_LINE = re.compile(r"^\s*//\s*@(\S+)\s*(.*)$", re.M)
REQUIRE_LIMIT = 512 * 1024


# --------------------------------------------------------------------------- #
# 匹配规则
# --------------------------------------------------------------------------- #
def _glob_to_regex(pattern: str) -> str:
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*", ".*").replace(r"\?", ".")
    return "^" + escaped + "$"


def pattern_to_regex(pattern: str) -> str:
    """把 Chrome 匹配模式 / glob / 正则写成 Python 正则字符串。"""
    pattern = (pattern or "").strip()
    if not pattern:
        return ""
    if pattern == "<all_urls>":
        return r"^(https?|file|ftp):/{1,2}.*$"
    if len(pattern) > 2 and pattern.startswith("/") and pattern.endswith("/"):
        return pattern[1:-1]

    parts = re.match(r"^(\*|https?|file|ftp)://([^/]*)(/.*)?$", pattern)
    if not parts:
        return _glob_to_regex(pattern)

    scheme, host, path = parts.group(1), parts.group(2), parts.group(3) or "/*"
    scheme_re = r"https?" if scheme == "*" else re.escape(scheme)
    if host == "*":
        host_re = r"[^/]+"
    else:
        host_re = re.escape(host).replace(r"\*", "[^/]*")
    if path == "/*":
        path_re = r"/.*"
    else:
        path_re = re.escape(path).replace(r"\*", ".*")
    return f"^{scheme_re}://{host_re}{path_re}$"


@dataclass
class UserScript:
    """一个用户脚本。"""

    id: str
    name: str = ""
    namespace: str = ""
    version: str = ""
    description: str = ""
    matches: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    run_at: str = "document-end"
    grants: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    source: str = ""
    path: Optional[Path] = None
    enabled: bool = True
    installed_at: float = field(default_factory=time.time)
    error: str = ""

    @property
    def display_name(self) -> str:
        return self.name or self.id

    @property
    def patterns(self) -> list[str]:
        return list(self.matches) + list(self.includes)

    def match_regex(self) -> list[re.Pattern]:
        compiled = []
        for pattern in self.patterns:
            regex = pattern_to_regex(pattern)
            if regex:
                try:
                    compiled.append(re.compile(regex))
                except re.error:
                    continue
        return compiled

    def exclude_regex(self) -> list[re.Pattern]:
        compiled = []
        for pattern in self.excludes:
            regex = pattern_to_regex(pattern)
            if regex:
                try:
                    compiled.append(re.compile(regex))
                except re.error:
                    continue
        return compiled

    def matches_url(self, url: str) -> bool:
        if not url:
            return False
        includes = self.match_regex()
        if not includes:
            return False
        if not any(item.match(url) for item in includes):
            return False
        return not any(item.match(url) for item in self.exclude_regex())

    @property
    def patterns_text(self) -> str:
        if not self.patterns:
            return "（未指定 @match/@include，不会运行）"
        text = ", ".join(self.patterns[:3])
        if len(self.patterns) > 3:
            text += f" 等 {len(self.patterns)} 条"
        return text


def parse_userscript(text: str, fallback_name: str = "userscript") -> UserScript:
    """解析 .user.js 内容。"""
    text = text.replace("\r\n", "\n")
    block = META_BLOCK.search(text)
    if not block:
        raise ValueError("没有找到 ==UserScript== 元数据块，不是有效的用户脚本")

    metadata: dict[str, list[str]] = {}
    for line in META_LINE.finditer(block.group(1)):
        key = line.group(1).strip().lower()
        value = line.group(2).strip()
        metadata.setdefault(key, []).append(value)

    def first(key: str, default: str = "") -> str:
        values = metadata.get(key)
        return values[0] if values else default

    name = first("name", fallback_name)
    namespace = first("namespace")
    script_id = hashlib.sha1(
        f"{namespace}|{name}|{first('version')}".encode("utf-8")
    ).hexdigest()[:16]

    script = UserScript(
        id=script_id,
        name=name,
        namespace=namespace,
        version=first("version"),
        description=first("description"),
        matches=list(metadata.get("match", [])),
        includes=list(metadata.get("include", [])),
        excludes=list(metadata.get("exclude", [])),
        run_at=(first("run-at", "document-end") or "document-end").lower(),
        grants=list(metadata.get("grant", [])),
        requires=list(metadata.get("require", [])),
        source=text,
    )
    if not script.matches and not script.includes:
        script.matches = ["*://*/*"]
    return script


class UserScriptStore(QObject):
    """用户脚本集合 + GM 数据存储。"""

    changed = Signal()

    def __init__(self, vault: DataVault, config, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.config = config
        self.data_dir = Path(data_dir)
        self.directory().mkdir(parents=True, exist_ok=True)
        self.require_dir().mkdir(parents=True, exist_ok=True)
        self.values_path = self.data_dir / "data" / "userscripts.dat"
        self.values_legacy = self.data_dir / "userscripts_values.json"
        self._scripts: list[UserScript] = []
        self._values: dict[str, dict] = {}
        #: GM_registerMenuCommand 注册的命令 {script_id: [(name, command_id)]}
        self.menu_commands: dict[str, list[tuple[str, str]]] = {}
        self.load()

    # -- 路径 ------------------------------------------------------------- #
    def directory(self) -> Path:
        return self.data_dir / "userscripts"

    def require_dir(self) -> Path:
        return self.directory() / "requires"

    def _disabled(self) -> set[str]:
        return set(self.config.get("disabled_userscripts") or [])

    def _set_disabled(self, values: set[str]) -> None:
        self.config.set("disabled_userscripts", sorted(values))

    # -- 载入 ------------------------------------------------------------- #
    def load(self) -> None:
        disabled = self._disabled()
        scripts: list[UserScript] = []
        for path in sorted(self.directory().glob("*.user.js")):
            try:
                script = parse_userscript(path.read_text(encoding="utf-8-sig"), path.stem)
            except (OSError, ValueError) as exc:
                script = UserScript(id=path.stem, name=path.stem, path=path, error=str(exc))
            script.path = path
            script.enabled = script.id not in disabled
            scripts.append(script)
        self._scripts = scripts
        self._load_values()

    def save_values(self) -> None:
        try:
            self.vault.write_text(
                json.dumps({"version": 1, "values": self._values}, ensure_ascii=False),
                self.values_path,
                self.values_legacy,
            )
        except OSError:
            pass

    def _load_values(self) -> None:
        text = self.vault.read_text(self.values_path, self.values_legacy)
        if not text:
            self._values = {}
            return
        try:
            payload = json.loads(text)
        except ValueError:
            self._values = {}
            return
        values = payload.get("values") if isinstance(payload, dict) else None
        self._values = values if isinstance(values, dict) else {}

    # -- 查询 ------------------------------------------------------------- #
    def all(self) -> list[UserScript]:
        return list(self._scripts)

    def count(self) -> int:
        return len(self._scripts)

    def at(self, script_id: str) -> Optional[UserScript]:
        for script in self._scripts:
            if script.id == script_id:
                return script
        return None

    def enabled(self) -> list[UserScript]:
        return [item for item in self._scripts if item.enabled and not item.error]

    def matching(self, url: str) -> list[UserScript]:
        return [item for item in self.enabled() if item.matches_url(url)]

    # -- 安装 / 管理 ------------------------------------------------------ #
    def install_text(self, text: str, filename: str = "script.user.js") -> UserScript:
        script = parse_userscript(text, Path(filename).stem)
        target = self.directory() / f"{script.id}.user.js"
        if script.path is not None and script.path.exists():
            # 覆盖安装：保留原文件位置
            target = script.path
        target.write_text(text, encoding="utf-8")
        script.path = target

        self._scripts = [item for item in self._scripts if item.id != script.id]
        script.enabled = True
        self._scripts.append(script)
        disabled = self._disabled()
        disabled.discard(script.id)
        self._set_disabled(disabled)

        self.cache_requires(script)
        self.changed.emit()
        return script

    def install_file(self, path: Path) -> UserScript:
        path = Path(path)
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        return self.install_text(text, path.name)

    def install_url(self, url: str, timeout: int = 20) -> UserScript:
        """从网址安装用户脚本（例如 Greasy Fork 的 .user.js 链接）。"""
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 lite browser test"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(REQUIRE_LIMIT * 4)
        text = raw.decode("utf-8", errors="replace")
        name = url.rstrip("/").split("/")[-1] or "script.user.js"
        if not name.endswith(".js"):
            name += ".user.js"
        return self.install_text(text, name)

    def cache_requires(self, script: UserScript) -> int:
        """下载 @require 依赖并缓存，注入时直接内联。"""
        count = 0
        for url in script.requires:
            target = self.require_dir() / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.js"
            if target.exists():
                count += 1
                continue
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 lite browser test"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    data = response.read(REQUIRE_LIMIT)
                target.write_bytes(data)
                count += 1
            except Exception:
                continue
        return count

    def set_enabled(self, script_id: str, enabled: bool) -> None:
        disabled = self._disabled()
        if enabled:
            disabled.discard(script_id)
        else:
            disabled.add(script_id)
        self._set_disabled(disabled)
        script = self.at(script_id)
        if script is not None:
            script.enabled = enabled
        self.changed.emit()

    def remove(self, script_id: str) -> bool:
        script = self.at(script_id)
        if script is None:
            return False
        if script.path is not None:
            try:
                script.path.unlink()
            except OSError:
                pass
        self._scripts = [item for item in self._scripts if item.id != script_id]
        self._values.pop(script_id, None)
        self.save_values()
        self.changed.emit()
        return True

    # -- GM 数据 ---------------------------------------------------------- #
    def values_for(self, script_id: str) -> dict:
        return dict(self._values.get(script_id) or {})

    def set_value(self, script_id: str, key: str, value) -> None:
        self._values.setdefault(script_id, {})[str(key)] = value
        self.save_values()

    def delete_value(self, script_id: str, key: str) -> None:
        store = self._values.get(script_id)
        if store and str(key) in store:
            del store[str(key)]
            self.save_values()

    # -- 注入 ------------------------------------------------------------- #
    def build_bootstrap(self) -> str:
        """生成注入到每个页面的引导脚本（内含按 URL 匹配的逻辑）。"""
        blocks = []
        for script in self.enabled():
            patterns = [pattern_to_regex(item) for item in script.patterns]
            patterns = [item for item in patterns if item]
            excludes = [pattern_to_regex(item) for item in script.excludes]
            excludes = [item for item in excludes if item]

            requires = []
            for url in script.requires:
                cached = self.require_dir() / f"{hashlib.sha1(url.encode()).hexdigest()[:16]}.js"
                if cached.exists():
                    try:
                        requires.append(cached.read_text(encoding="utf-8", errors="replace"))
                    except OSError:
                        pass

            blocks.append(
                {
                    "id": script.id,
                    "name": script.name,
                    "version": script.version,
                    "namespace": script.namespace,
                    "description": script.description,
                    "runAt": script.run_at,
                    "includes": patterns,
                    "excludes": excludes,
                    "code": script.source,
                    "requires": requires,
                    "seed": self.values_for(script.id),
                }
            )

        payload = json.dumps(blocks, ensure_ascii=False)
        return _BOOTSTRAP_JS.replace("__LB_SCRIPTS__", payload)


# --------------------------------------------------------------------------- #
# 注入脚本模板
# --------------------------------------------------------------------------- #
_BOOTSTRAP_JS = r"""
(function () {
  if (window.__liteBrowserScriptsInstalled) { return; }
  window.__liteBrowserScriptsInstalled = true;

  var SCRIPTS = __LB_SCRIPTS__;
  var HOST = {
    send: function (message) {
      try {
        if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {
          window.chrome.webview.postMessage(JSON.stringify(message));
          return true;
        }
      } catch (e) {}
      return false;
    }
  };
  var LOCAL_PREFIX = '__lite_gm_';
  var asyncId = 0;
  var callbacks = {};
  var menus = [];

  window.__lbGmResult = function (id, payload) {
    var entry = callbacks[id];
    if (!entry) { return; }
    delete callbacks[id];
    try { entry(payload); } catch (e) { console.error('[lite browser] GM 回调异常', e); }
  };

  window.__lbGmMenu = function (scriptId, commandId) {
    for (var i = 0; i < menus.length; i++) {
      if (menus[i].scriptId === scriptId && menus[i].commandId === commandId) {
        try { menus[i].fn(); } catch (e) { console.error(e); }
        return;
      }
    }
  };

  function localKey(scriptId, key) { return LOCAL_PREFIX + scriptId + '_' + key; }

  function makeGM(block) {
    var id = block.id;
    var seed = block.seed || {};
    var values = {};
    for (var k in seed) { if (Object.prototype.hasOwnProperty.call(seed, k)) { values[k] = seed[k]; } }
    // 兼容：宿主不可用时用 localStorage 兜底
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var lk = localStorage.key(i);
        if (lk && lk.indexOf(LOCAL_PREFIX + id + '_') === 0) {
          var realKey = lk.substring((LOCAL_PREFIX + id + '_').length);
          if (!(realKey in values)) {
            try { values[realKey] = JSON.parse(localStorage.getItem(lk)); } catch (e) {}
          }
        }
      }
    } catch (e) {}

    function persist(key, value, remove) {
      var ok = HOST.send({ __lite_gm: 'value', id: id, key: key, value: value, remove: !!remove });
      if (!ok) {
        try {
          if (remove) { localStorage.removeItem(localKey(id, key)); }
          else { localStorage.setItem(localKey(id, key), JSON.stringify(value)); }
        } catch (e) {}
      }
    }

    var gm = {};
    gm.GM_info = {
      script: {
        name: block.name, namespace: block.namespace, version: block.version,
        description: block.description, matches: block.includes
      },
      scriptHandler: 'lite browser test',
      version: '1.0.test'
    };
    gm.unsafeWindow = window;
    gm.GM_getValue = function (key, def) {
      return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : def;
    };
    gm.GM_setValue = function (key, value) { values[key] = value; persist(key, value, false); };
    gm.GM_deleteValue = function (key) { delete values[key]; persist(key, null, true); };
    gm.GM_listValues = function () { return Object.keys(values); };
    gm.GM_addStyle = function (css) {
      var style = document.createElement('style');
      style.textContent = css;
      (document.head || document.documentElement).appendChild(style);
      return style;
    };
    gm.GM_log = function () {
      try { console.log.apply(console, ['[' + block.name + ']'].concat([].slice.call(arguments))); } catch (e) {}
    };
    gm.GM_setClipboard = function (text) {
      if (navigator.clipboard) { navigator.clipboard.writeText(String(text)); }
    };
    gm.GM_notification = function (text, title) {
      try {
        if (window.Notification && Notification.permission === 'granted') {
          new Notification(title || block.name, { body: String(text) });
        } else {
          console.log('[' + block.name + '] ' + text);
        }
      } catch (e) {}
    };
    gm.GM_openInTab = function (url, options) {
      HOST.send({ __lite_gm: 'open', url: String(url), background: !!(options && options.active === false) });
      return { close: function () {} };
    };
    gm.GM_registerMenuCommand = function (name, fn) {
      var commandId = 'cmd' + (menus.length + 1);
      menus.push({ scriptId: id, commandId: commandId, name: name, fn: fn });
      HOST.send({ __lite_gm: 'menu', id: id, commandId: commandId, name: String(name) });
    };
    gm.GM_xmlhttpRequest = function (details) {
      details = details || {};
      var requestId = 'x' + (++asyncId);
      var finished = false;
      function finish(payload) {
        if (finished) { return; }
        finished = true;
        var response = {
          readyState: 4,
          status: payload.status || 0,
          statusText: payload.statusText || '',
          responseText: payload.body || '',
          response: payload.body || '',
          finalUrl: payload.url || details.url
        };
        try {
          if (details.onload && payload.ok) { details.onload(response); }
          else if (details.onerror && !payload.ok) { details.onerror(response); }
          if (details.onloadend) { details.onloadend(response); }
        } catch (e) { console.error(e); }
      }
      if (!HOST.send({
        __lite_gm: 'xhr', id: id, requestId: requestId, details: {
          method: details.method || 'GET', url: details.url,
          headers: details.headers || {}, data: details.data || null,
          timeout: details.timeout || 20000
        }
      })) {
        // 宿主不可用：退回 fetch
        fetch(details.url, {
          method: details.method || 'GET',
          headers: details.headers || {},
          body: details.data || undefined
        }).then(function (r) {
          return r.text().then(function (t) { finish({ ok: r.ok, status: r.status, statusText: r.statusText, body: t }); });
        }).catch(function (e) { finish({ ok: false, status: 0, statusText: String(e) }); });
        return { abort: function () { finished = true; } };
      }
      callbacks[requestId] = finish;
      if (details.ontimeout) { setTimeout(function () { if (!finished) { details.ontimeout(); } }, (details.timeout || 20000) + 500); }
      return { abort: function () { finished = true; delete callbacks[requestId]; } };
    };
    return gm;
  }

  function shouldRun(block, url) {
    var ok = false;
    for (var i = 0; i < block.includes.length; i++) {
      try { if (new RegExp(block.includes[i]).test(url)) { ok = true; break; } } catch (e) {}
    }
    if (!ok) { return false; }
    for (var j = 0; j < block.excludes.length; j++) {
      try { if (new RegExp(block.excludes[j]).test(url)) { return false; } } catch (e) {}
    }
    return true;
  }

  function runBlock(block) {
    var gm;
    try { gm = makeGM(block); } catch (e) { console.error('[lite browser] 初始化失败', e); return; }
    var names = ['GM_info', 'unsafeWindow', 'GM_getValue', 'GM_setValue', 'GM_deleteValue',
                 'GM_listValues', 'GM_addStyle', 'GM_log', 'GM_setClipboard', 'GM_notification',
                 'GM_openInTab', 'GM_registerMenuCommand', 'GM_xmlhttpRequest'];
    var args = names.map(function (n) { return gm[n]; });
    try {
      var body = '';
      for (var r = 0; r < block.requires.length; r++) { body += block.requires[r] + '\n;\n'; }
      body += block.code;
      var factory = new Function(names.join(','), body);
      factory.apply(window, args);
      console.log('[lite browser] 已运行用户脚本：' + block.name);
    } catch (e) {
      console.error('[lite browser] 用户脚本执行失败：' + block.name, e);
    }
  }

  function schedule(block) {
    if (!shouldRun(block, location.href)) { return; }
    var runAt = (block.runAt || 'document-end').toLowerCase();
    if (runAt === 'document-start') {
      runBlock(block);
    } else if (runAt === 'document-idle') {
      window.addEventListener('load', function () { setTimeout(function () { runBlock(block); }, 0); });
    } else {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { runBlock(block); });
      } else {
        runBlock(block);
      }
    }
  }

  for (var i = 0; i < SCRIPTS.length; i++) { schedule(SCRIPTS[i]); }
})();
"""


# --------------------------------------------------------------------------- #
# GM 消息处理（宿主侧）
# --------------------------------------------------------------------------- #
def handle_gm_message(
    payload: dict,
    store: UserScriptStore,
    post_to_page: Callable[[str], None],
    open_tab: Optional[Callable[[str], None]] = None,
) -> bool:
    """处理页面发来的 GM 请求，返回是否已处理。"""
    op = payload.get("__lite_gm")
    if not op:
        return False

    if op == "value":
        script_id = str(payload.get("id") or "")
        key = str(payload.get("key") or "")
        if payload.get("remove"):
            store.delete_value(script_id, key)
        else:
            store.set_value(script_id, key, payload.get("value"))
        return True

    if op == "open":
        url = str(payload.get("url") or "")
        if url and open_tab is not None:
            open_tab(url)
        return True

    if op == "menu":
        script_id = str(payload.get("id") or "")
        store.menu_commands.setdefault(script_id, []).append(
            (str(payload.get("name") or "菜单命令"), str(payload.get("commandId") or ""))
        )
        return True

    if op == "xhr":
        request_id = str(payload.get("requestId") or "")
        details = payload.get("details") or {}
        script_id = str(payload.get("id") or "")
        print(f"[gm] 收到跨域请求 {request_id}: {details.get('method')} {details.get('url')}", flush=True)

        def worker() -> None:
            result = _perform_request(details)
            print(f"[gm] 请求完成 {request_id}: status={result.get('status')} "
                  f"bytes={len(result.get('body') or '')}", flush=True)
            js = (
                "window.__lbGmResult && window.__lbGmResult(%s, %s);"
                % (json.dumps(request_id), json.dumps(result, ensure_ascii=False))
            )
            try:
                post_to_page(js)
            except Exception as exc:  # noqa: BLE001
                print(f"[gm] 回传页面失败：{exc!r}", flush=True)

        threading.Thread(target=worker, daemon=True).start()
        return True

    if op == "log":
        print(f"[userscript] {payload.get('message')}", flush=True)
        return True

    return False


def _perform_request(details: dict) -> dict:
    """代表用户脚本发起 HTTP 请求（不受同源策略限制）。"""
    url = str(details.get("url") or "")
    method = str(details.get("method") or "GET").upper()
    headers = details.get("headers") or {}
    data = details.get("data")
    timeout = min(int(details.get("timeout") or 20000) / 1000.0, 60.0)

    body = None
    if data is not None:
        body = data.encode("utf-8") if isinstance(data, str) else bytes(data)

    try:
        request = urllib.request.Request(url, data=body, method=method)
        for key, value in (headers or {}).items():
            request.add_header(str(key), str(value))
        if not any(str(k).lower() == "user-agent" for k in (headers or {})):
            request.add_header("User-Agent", "Mozilla/5.0 lite browser test")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(REQUIRE_LIMIT * 8)
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                text = raw.decode(charset, errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status": response.status,
                "statusText": response.reason or "",
                "body": text,
                "url": response.geturl(),
            }
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read(REQUIRE_LIMIT).decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return {"ok": False, "status": exc.code, "statusText": str(exc.reason), "body": text, "url": url}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": 0, "statusText": str(exc), "body": "", "url": url}
