"""Ruffle —— 无广告的开源 Flash 模拟器（GitHub: ruffle-rs/ruffle）。

**为什么不是 Adobe Flash？**
Flash Player（PPAPI 插件）已经在 2020 年底停止支持，Chromium 内核
（本程序使用的 WebView2 / QtWebEngine）从 88 版起**彻底移除了 Flash 插件接口**，
所以任何"官方 Flash"都无法再装进现代内核。Ruffle 用 Rust 写了一个 Flash 运行时，
再编译成 **WebAssembly** 在网页里跑，因此不需要插件、没有广告，是目前唯一可行的方案。

本模块负责：

* 把随程序分发的 Ruffle 文件（``lib/ruffle/``）通过一个虚拟域名
  ``https://ruffle.litebrowser.local/`` 提供给网页（WebView2 用资源拦截实现）；
* 生成注入页面的引导脚本，让 Ruffle 自动接管页面里的 Flash 内容；
* 为直接打开的 ``.swf`` 文件生成一个独立的播放页。
"""

from __future__ import annotations

import html
import json
import logging
import secrets
import threading
import time
from pathlib import Path

from .config import APP_NAME, APP_VERSION, resource_path

log = logging.getLogger(__name__)

#: 虚拟域名：网页从这里加载 Ruffle（由内核层拦截并返回本地文件）
SCHEME = "https"
HOST = "ruffle.litebrowser.local"
PUBLIC_PATH = f"{SCHEME}://{HOST}/"

#: Ruffle 版本（随 lib/ruffle 里的文件一起更新）
RUFFLE_VERSION = "0.6.0"

#: 允许从本地供给的文件名（白名单，避免任意文件读取）
_ALLOWED_SUFFIXES = (".js", ".wasm", ".json", ".map")
_ALLOWED_NAMES = ("LICENSE_APACHE", "LICENSE_MIT")

_MIME = {
    ".js": "application/javascript; charset=utf-8",
    ".wasm": "application/wasm",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
}


def ruffle_dir() -> Path:
    """Ruffle 文件所在目录。"""
    return resource_path("lib", "ruffle")


def available() -> bool:
    """随程序分发的 Ruffle 是否齐全。"""
    folder = ruffle_dir()
    return (folder / "ruffle.js").exists()


def version_text() -> str:
    return f"Ruffle {RUFFLE_VERSION}" if available() else "Ruffle 未安装"


def serve(name: str) -> tuple[bytes, str] | None:
    """按文件名读取 Ruffle 资源，返回 (内容, MIME)；不在白名单返回 None。"""
    clean = (name or "").split("?", 1)[0].split("#", 1)[0].strip("/")
    if not clean or "/" in clean or ".." in clean:
        return None
    if clean not in _ALLOWED_NAMES and not clean.endswith(_ALLOWED_SUFFIXES):
        return None
    path = ruffle_dir() / clean
    if not path.exists() or not path.is_file():
        return None
    suffix = path.suffix.lower()
    mime = _MIME.get(suffix, "application/octet-stream")
    try:
        return path.read_bytes(), mime
    except OSError:
        return None


def config_dict(*, enable: bool = True) -> dict:
    """给网页用的 Ruffle 配置（关掉水印/日志，开启自动播放）。"""
    return {
        "polyfills": True,          # 伪造 navigator.plugins，让老站点以为装了 Flash
        "autoplay": "on",
        "unmuteOverlay": "hidden",
        "splashScreen": False,
        "letterbox": "on",
        "scale": "showAll",
        "quality": "high",
        "warnOnUnsupportedContent": False,
        "logLevel": "error",
        "openUrlMode": "allow",
        "allowScriptAccess": True,
        "contextMenu": "on",
        "showSwfDownload": False,
    }


def bootstrap_script(public_path: str = "", config_json: str = "", token: str = "") -> str:
    """注入到每个页面的引导脚本：配置 Ruffle 并加载它。

    ``token`` 会写进页面里的 .swf 地址改写逻辑，代理只接受带该 token 的请求。
    """
    path = public_path or PUBLIC_PATH
    config = config_json or json.dumps(config_dict(), ensure_ascii=False)
    token_js = json.dumps(token or "")
    return f"""
(function () {{
  try {{
    if (window.__liteRuffleLoaded || window.__liteRuffleLoading) return;
    window.__liteRuffleLoading = true;
    var PUBLIC = {json.dumps(path)};
    var EXTRA = {config};
    var TOKEN = {token_js};
    window.RufflePlayer = window.RufflePlayer || {{}};
    var base = window.RufflePlayer.config || {{}};
    for (var key in EXTRA) {{ if (!(key in base)) base[key] = EXTRA[key]; }}
    window.RufflePlayer.config = base;
    // 有些站点会检查这些老接口，Ruffle 的 polyfill 需要它们存在
    try {{ window.RufflePlayer.publicPath = PUBLIC; }} catch (e) {{}}

    // 先把页面里的 .swf 地址改写成由本程序代取的地址：
    // 自托管的 Ruffle 只能跨域抓取带 CORS 头的资源，而大多数 Flash 站点
    // （比如 4399 的 s7.4399.com）并不发这些头，直接抓会报「被 CORS 策略阻止」。
    // 这个 MutationObserver 在 ruffle.js 之前注册，因此会先于 Ruffle 处理同一个变更。
    function proxy(target) {{
      try {{
        if (!target || typeof target !== 'string') return target;
        if (target.indexOf(PUBLIC) === 0) return target;
        if (target.indexOf('.swf') < 0) return target;
        if (!/^https?:\\/\\//i.test(target)) {{
          target = new URL(target, location.href).href;
        }}
        return PUBLIC + 'proxy?token=' + encodeURIComponent(TOKEN)
          + '&url=' + encodeURIComponent(target);
      }} catch (e) {{ return target; }}
    }}
    var ATTRS = ['src', 'data', 'movie'];
    function rewrite(el) {{
      if (!el || el.nodeType !== 1) return;
      var tag = (el.tagName || '').toLowerCase();
      if (tag !== 'embed' && tag !== 'object' && tag !== 'param') return;
      for (var i = 0; i < ATTRS.length; i++) {{
        var name = ATTRS[i];
        var value = el.getAttribute && el.getAttribute(name);
        if (value && value.indexOf('.swf') >= 0 && value.indexOf('/proxy?url=') < 0) {{
          try {{ el.setAttribute(name, proxy(value)); }} catch (e) {{}}
        }}
      }}
    }}
    function scan(root) {{
      if (!root || root.nodeType !== 1) return;
      rewrite(root);
      var list = root.querySelectorAll ? root.querySelectorAll('embed,object,param') : [];
      for (var i = 0; i < list.length; i++) rewrite(list[i]);
    }}
    try {{
      var observer = new MutationObserver(function (records) {{
        for (var i = 0; i < records.length; i++) {{
          var rec = records[i];
          if (rec.type === 'attributes') rewrite(rec.target);
          else for (var j = 0; j < rec.addedNodes.length; j++) scan(rec.addedNodes[j]);
        }}
      }});
      observer.observe(document.documentElement || document, {{
        childList: true, subtree: true, attributes: true, attributeFilter: ATTRS
      }});
      window.__liteSwfRewriter = observer;
      document.addEventListener('DOMContentLoaded', function () {{ scan(document.body); }});
      scan(document.documentElement);
    }} catch (e) {{}}

    var script = document.createElement('script');
    script.src = PUBLIC + 'ruffle.js';
    script.async = false;
    script.onload = function () {{ window.__liteRuffleLoaded = true; }};
    script.onerror = function () {{ window.__liteRuffleFailed = true; }};
    (document.head || document.documentElement).appendChild(script);
  }} catch (err) {{
    window.__liteRuffleFailed = String(err);
  }}
}})();
""".strip()


def swf_page(swf_url: str, token: str = "") -> str:
    """为直接打开的 .swf 生成播放页。"""
    path = PUBLIC_PATH
    play_url = (proxy_url(swf_url, token)
                if swf_url.lower().startswith(("http://", "https://")) else swf_url)
    from urllib.parse import unquote, urlsplit

    try:
        label = unquote(urlsplit(swf_url).path.rsplit("/", 1)[-1]) or "Flash 播放"
    except ValueError:
        label = "Flash 播放"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(label)} - {html.escape(APP_NAME)}</title>
<style>
  html, body {{ margin: 0; height: 100%; background: #1B1B1B; overflow: hidden; }}
  #player {{ position: absolute; inset: 0; }}
  #tip {{ position: absolute; left: 0; right: 0; bottom: 6px; text-align: center;
         color: #9A9A9A; font: 12px "Microsoft YaHei", sans-serif; pointer-events: none; }}
</style>
</head>
<body>
<div id="player"></div>
<div id="tip">由 {html.escape(version_text())} 运行（开源 Flash 模拟器，无广告）</div>
<script>
  window.RufflePlayer = window.RufflePlayer || {{}};
  window.RufflePlayer.config = {json.dumps(config_dict(), ensure_ascii=False)};
  window.RufflePlayer.publicPath = {json.dumps(path)};
  window.__swfSource = {json.dumps(play_url)};
  window.__swfOriginal = {json.dumps(swf_url)};
</script>
<script src="{path}ruffle.js"></script>
<script>
(function () {{
  function start() {{
    if (!window.RufflePlayer || !window.RufflePlayer.newest) {{
      document.getElementById('tip').textContent = 'Ruffle 加载失败，请检查「设置 → 网络」中的 Flash 兼容开关。';
      return;
    }}
    var ruffle = window.RufflePlayer.newest();
    var player = ruffle.createPlayer();
    player.style.width = '100%';
    player.style.height = '100%';
    document.getElementById('player').appendChild(player);
    player.load(window.__swfSource);
  }}
  if (document.readyState === 'complete' || document.readyState === 'interactive') start();
  else window.addEventListener('DOMContentLoaded', start);
}})();
</script>
</body>
</html>
"""


def write_swf_page(swf_url: str, token: str = "") -> Path:
    """把 .swf 播放页写到数据目录并返回路径。"""
    from .config import data_dir

    folder = data_dir() / "pages"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "swf-player.html"
    path.write_text(swf_page(swf_url, token), encoding="utf-8")
    return path


def swf_page_url(swf_url: str, token: str = "") -> str:
    return write_swf_page(swf_url, token).as_uri()


def is_swf_url(url: str) -> bool:
    """判断是否是直接的 .swf 地址。"""
    text = (url or "").split("?", 1)[0].split("#", 1)[0].lower()
    return text.endswith(".swf")


def proxy_url(target: str, token: str = "") -> str:
    """把外部 .swf 地址包装成由本程序代取的地址（解决跨域取不到的问题）。

    ``token`` 是本次 Ruffle 播放会话的授权凭据，缺少它代理会拒绝服务。
    """
    from urllib.parse import quote

    query = f"url={quote(target, safe='')}"
    if token:
        query = f"token={quote(token, safe='')}&{query}"
    return f"{PUBLIC_PATH}proxy?{query}"


def is_proxy_url(url: str) -> bool:
    return "ruffle.litebrowser.local/proxy" in (url or "")


def parse_proxy_request(url: str) -> tuple[str, str]:
    """解析代理请求，返回 (目标地址, token)。"""
    from urllib.parse import parse_qs, unquote, urlsplit

    try:
        query = urlsplit(url).query
    except ValueError:
        return "", ""
    params = parse_qs(query)
    target = unquote((params.get("url") or [""])[0])
    token = (params.get("token") or [""])[0]
    return target, token


def unproxy_target(url: str) -> str:
    """从代理地址还原目标地址。"""
    return parse_proxy_request(url)[0]


# --------------------------------------------------------------------------- #
# Ruffle 播放会话授权
# --------------------------------------------------------------------------- #
class RuffleSessions:
    """为每个 Ruffle 播放会话发放不可预测的随机 token。

    代理接口不再把 Referer 当作唯一授权依据（Referer 可被伪造/省略），
    改为要求请求携带本进程发放、且与会话绑定的 token：

    * token 由 ``secrets.token_urlsafe`` 生成，不可预测；
    * 带过期时间，过期或超过会话上限即失效；
    * 页面导航离开 / 标签页关闭时主动 revoke；
    * 不写入历史记录与配置（内置页面地址不参与历史记录）。
    """

    #: token 有效期（秒）
    TTL_SECONDS = 30 * 60
    #: 同时存在的会话上限（超出时淘汰最早的）
    MAX_SESSIONS = 128

    def __init__(self) -> None:
        self._tokens: dict[str, float] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._purge_locked(now)
            while len(self._tokens) >= self.MAX_SESSIONS:
                oldest = min(self._tokens, key=lambda key: self._tokens[key])
                self._tokens.pop(oldest, None)
            self._tokens[token] = now + self.TTL_SECONDS
        return token

    def valid(self, token: str) -> bool:
        if not token:
            return False
        now = time.time()
        with self._lock:
            expiry = self._tokens.get(token)
            if expiry is None:
                return False
            if expiry < now:
                self._tokens.pop(token, None)
                return False
            return True

    def revoke(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._tokens.pop(token, None)

    def revoke_all(self) -> None:
        with self._lock:
            self._tokens.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._tokens)

    def _purge_locked(self, now: float) -> None:
        expired = [key for key, expiry in self._tokens.items() if expiry < now]
        for key in expired:
            self._tokens.pop(key, None)


#: 全局会话表（跨标签页共享，token 与会话一一对应）
SESSIONS = RuffleSessions()


#: 代理取回的最大体积（防止被超大文件拖死）
MAX_PROXY_BYTES = 64 * 1024 * 1024


def _host_is_private(host: str) -> bool:
    """兼容旧调用：判断主机是否解析到非公网地址。

    真正的校验在 :mod:`litebrowser.safefetch` 里完成（含逐跳重校验与 IP 钉住），
    这里只作为对外的辅助判断保留。
    """
    from .safefetch import is_public_host

    return not is_public_host(host)


def _is_swf_content(body: bytes, _content_type: str) -> bool:
    """校验取回的内容确实是 SWF（防止拿到防盗链的 HTML 页面）。"""
    return len(body) >= 8 and body[:3] in (b"FWS", b"CWS", b"ZWS")


def fetch_swf(target: str, referer: str = "") -> tuple[bytes, str] | None:
    """代取外部 .swf，返回 (内容, MIME)；被拒绝或失败返回 None。

    安全策略全部交由 :func:`litebrowser.safefetch.fetch` 执行：
    只允许 http/https、逐跳校验解析地址、连接钉住已验证 IP、
    最多 5 次跳转、限制响应体积；这里再要求内容必须是合法 SWF。
    """
    from .safefetch import FetchError, fetch

    if not is_swf_url(target):
        log.info("Ruffle 代理拒绝：不是 .swf 地址（%s）", target[:120])
        return None
    try:
        result = fetch(
            target,
            referer=referer,
            max_bytes=MAX_PROXY_BYTES,
            validator=_is_swf_content,
        )
    except FetchError as exc:
        log.warning("Ruffle 代取被拒绝或失败：%s（%s）", exc, target[:120])
        return None
    except Exception:  # noqa: BLE001 - 未预期异常需要记录，不能静默
        log.exception("Ruffle 代取出现未预期异常：%s", target[:120])
        return None
    mime = result.content_type or "application/x-shockwave-flash"
    if result.redirects:
        log.info("Ruffle 代取完成：%s 次跳转，%d 字节", result.redirects, len(result.body))
    return result.body, mime


def supports_current_engine(engine_id: str) -> bool:
    """只有 WebView2 能用资源拦截把本地 Ruffle 供給网页。"""
    return (engine_id or "") == "webview2"


def info() -> dict:
    """给设置页展示的信息。"""
    folder = ruffle_dir()
    total = 0
    if folder.exists():
        for item in folder.glob("*"):
            if item.is_file() and item.name.endswith((".js", ".wasm")):
                total += item.stat().st_size
    return {
        "available": available(),
        "version": RUFFLE_VERSION,
        "size_mb": round(total / 1048576, 1),
        "path": str(folder),
        "app_version": APP_VERSION,
    }
