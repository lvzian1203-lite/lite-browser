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
from pathlib import Path

from .config import APP_NAME, APP_VERSION, resource_path

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


def bootstrap_script(public_path: str = "", config_json: str = "") -> str:
    """注入到每个页面的引导脚本：配置 Ruffle 并加载它。"""
    path = public_path or PUBLIC_PATH
    config = config_json or json.dumps(config_dict(), ensure_ascii=False)
    return f"""
(function () {{
  try {{
    if (window.__liteRuffleLoaded || window.__liteRuffleLoading) return;
    window.__liteRuffleLoading = true;
    var PUBLIC = {json.dumps(path)};
    var EXTRA = {config};
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
        return PUBLIC + 'proxy?url=' + encodeURIComponent(target);
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


def swf_page(swf_url: str) -> str:
    """为直接打开的 .swf 生成播放页。"""
    path = PUBLIC_PATH
    safe_url = html.escape(swf_url, quote=True)
    play_url = proxy_url(swf_url) if swf_url.lower().startswith(("http://", "https://")) else swf_url
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


def write_swf_page(swf_url: str) -> Path:
    """把 .swf 播放页写到数据目录并返回路径。"""
    from .config import data_dir

    folder = data_dir() / "pages"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "swf-player.html"
    path.write_text(swf_page(swf_url), encoding="utf-8")
    return path


def swf_page_url(swf_url: str) -> str:
    return write_swf_page(swf_url).as_uri()


def is_swf_url(url: str) -> bool:
    """判断是否是直接的 .swf 地址。"""
    text = (url or "").split("?", 1)[0].split("#", 1)[0].lower()
    return text.endswith(".swf")


def proxy_url(target: str) -> str:
    """把外部 .swf 地址包装成由本程序代取的地址（解决跨域取不到的问题）。"""
    from urllib.parse import quote

    return f"{PUBLIC_PATH}proxy?url={quote(target, safe='')}"


def is_proxy_url(url: str) -> bool:
    return "ruffle.litebrowser.local/proxy" in (url or "")


def unproxy_target(url: str) -> str:
    """从代理地址还原目标地址。"""
    from urllib.parse import parse_qs, unquote, urlsplit

    try:
        query = urlsplit(url).query
    except ValueError:
        return ""
    params = parse_qs(query)
    value = (params.get("url") or [""])[0]
    return unquote(value)


#: 代理取回的最大体积（防止被超大文件拖死）
MAX_PROXY_BYTES = 64 * 1024 * 1024


def _host_is_private(host: str) -> bool:
    """拒绝代理到本机 / 内网地址，避免被网页当成 SSRF 跳板。"""
    import ipaddress
    import socket

    name = (host or "").strip().lower()
    if not name:
        return True
    if name in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    try:
        infos = socket.getaddrinfo(name, None)
    except OSError:
        return False
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast):
            return True
    return False


def fetch_swf(target: str, referer: str = "") -> tuple[bytes, str] | None:
    """代取外部 .swf，返回 (内容, MIME)；失败返回 None。

    只允许 http/https 且路径以 .swf 结尾的地址，并拒绝内网主机，
    这样即使被恶意网页调用也无法访问本地服务。
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    try:
        parts = urllib.parse.urlsplit(target)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    if not is_swf_url(target):
        return None
    if _host_is_private(parts.hostname or ""):
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer and referer.startswith(("http://", "https://")):
        headers["Referer"] = referer
    else:
        headers["Referer"] = f"{parts.scheme}://{parts.netloc}/"
    try:
        request = urllib.request.Request(target, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                return None
            data = response.read(MAX_PROXY_BYTES + 1)
            if len(data) > MAX_PROXY_BYTES:
                return None
            mime = response.headers.get("Content-Type") or "application/x-shockwave-flash"
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if len(data) < 8 or data[:3] not in (b"FWS", b"CWS", b"ZWS"):
        # 不是合法的 SWF（可能是防盗链返回的 HTML）
        return None
    return data, mime


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
