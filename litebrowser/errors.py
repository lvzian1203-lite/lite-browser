"""自定义错误页面：一只追着鼠标跑的猫。

网络错误（DNS 解析失败、连接被拒绝、超时）与 HTTP 4xx/5xx 都会显示这个页面，
页面里的猫会实时追逐鼠标指针，走过后留下脚印，靠近指针时会跳一下。
"""

from __future__ import annotations

import html as _html
import json
from typing import Optional

#: 常见 HTTP 状态码的中文说明（负数是网络层错误，与 WebView2 的 WebErrorStatus 对应）
STATUS_TEXT = {
    400: "请求无效",
    401: "需要身份验证",
    403: "拒绝访问",
    404: "找不到页面",
    405: "方法不被允许",
    408: "请求超时",
    410: "页面已被删除",
    429: "请求过于频繁",
    451: "因法律原因不可用",
    500: "服务器内部错误",
    501: "服务器不支持该请求",
    502: "网关错误",
    503: "服务暂时不可用",
    504: "网关超时",
    505: "HTTP 版本不受支持",
    520: "服务器返回未知错误",
}

#: WebView2 WebErrorStatus 数值 -> 说明（-N 表示第 N 个网络错误）
WEBVIEW2_ERRORS = {
    0: "未知错误",
    1: "证书中的主机名不正确",
    2: "证书已过期",
    3: "客户端证书有错误",
    4: "证书已被吊销",
    5: "证书无效",
    6: "无法访问服务器",
    7: "连接超时",
    8: "服务器返回无效响应",
    9: "连接被中止",
    10: "连接被重置",
    11: "连接已断开",
    12: "无法建立连接",
    13: "无法解析域名",
    14: "操作已取消",
    15: "重定向失败",
    16: "未知错误",
    17: "需要身份验证凭据",
    18: "代理需要身份验证凭据",
}

#: 网络错误的中文说明（用 -N 表示 WebView2 的第 N 个错误）
STATUS_TEXT.update({-key: value for key, value in WEBVIEW2_ERRORS.items() if key})
STATUS_TEXT[-100] = "已拦截的网址"


def describe(code: int, fallback: str = "") -> tuple[str, str]:
    """返回 (短标题, 详细说明)。"""
    mapped = STATUS_TEXT.get(code, "")
    if code in STATUS_TEXT:
        if fallback and mapped in ("未知错误", "网络错误", "无法打开该页面"):
            return fallback, ""
        return mapped, fallback
    if 400 <= code < 500:
        return f"客户端错误 {code}", fallback
    if 500 <= code < 600:
        return f"服务器错误 {code}", fallback
    if code < 0:
        return fallback or "网络错误", ""
    return fallback or "无法打开该页面", ""


def _escape(text: str) -> str:
    return _html.escape(text or "", quote=True)


def error_page(
    url: str,
    code: int = 0,
    message: str = "",
    *,
    dark: bool = False,
    accent: str = "#0B5FE6",
    title: str = "lite browser",
    can_go_back: bool = True,
) -> str:
    """生成错误页面 HTML。"""
    status = str(abs(code)) if code else "!"
    headline, detail = describe(code, message)
    if not detail:
        detail = message
    if detail == headline:
        detail = ""
    title_text = _escape(headline)
    detail_text = _escape(detail)
    url_text = _escape(url)

    bg = "#1E1E1E" if dark else "#F7F7F7"
    card = "#262626" if dark else "#FFFFFF"
    fg = "#E8E8E8" if dark else "#1F1F1F"
    dim = "#9A9A9A" if dark else "#6A6A6A"
    line = "#3A3A3A" if dark else "#E2E2E2"
    cat_body = "#8A8A8A" if dark else "#4A4A4A"
    cat_dark = "#6E6E6E" if dark else "#333333"
    cat_light = "#B0B0B0" if dark else "#5E5E5E"

    url_js = json.dumps(url or "", ensure_ascii=False)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_text}</title>
<style>
  :root {{
    --bg: {bg}; --card: {card}; --fg: {fg}; --dim: {dim};
    --line: {line}; --accent: {accent};
    --cat: {cat_body}; --cat-dark: {cat_dark}; --cat-light: {cat_light};
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    height: 100%; margin: 0; overflow: hidden;
    background: var(--bg); color: var(--fg);
    font: 14px/1.7 "Microsoft YaHei UI", "Segoe UI", Tahoma, sans-serif;
    cursor: crosshair; user-select: none;
  }}
  .wrap {{
    position: relative; z-index: 2; max-width: 720px; margin: 0 auto;
    padding: 8vh 24px 0; text-align: center;
  }}
  .code {{
    font: 700 86px/1 "Segoe UI", Tahoma, sans-serif;
    color: var(--accent); letter-spacing: 2px; text-shadow: 0 2px 0 rgba(0,0,0,.08);
  }}
  .headline {{ font-size: 22px; margin: 10px 0 6px; }}
  .detail {{ color: var(--dim); min-height: 24px; }}
  .url {{
    display: inline-block; max-width: 100%; margin-top: 18px; padding: 7px 14px;
    background: var(--card); border: 1px solid var(--line); border-radius: 6px;
    font: 12px/1.5 Consolas, monospace; color: var(--dim);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  .actions {{ margin-top: 22px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }}
  button {{
    font: inherit; padding: 7px 20px; border-radius: 5px; cursor: pointer;
    border: 1px solid var(--line); background: var(--card); color: var(--fg);
    transition: .15s;
  }}
  button:hover {{ border-color: var(--accent); color: var(--accent); }}
  button.primary {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  button.primary:hover {{ filter: brightness(1.1); color: #fff; }}
  .hint {{ margin-top: 26px; color: var(--dim); font-size: 12px; }}
  #stage {{ position: fixed; inset: 0; z-index: 1; pointer-events: none; }}
  .cat {{ position: absolute; width: 150px; height: 115px; will-change: transform; }}
  .paw {{
    position: absolute; width: 13px; height: 13px; margin: -6px 0 0 -6px;
    border-radius: 50%; background: var(--cat); opacity: .3;
    animation: fade 2.6s linear forwards;
  }}
  @keyframes fade {{ to {{ opacity: 0; transform: scale(.6); }} }}
</style>
</head>
<body>
<div class="wrap">
  <div class="code">{status}</div>
  <div class="headline">{title_text}</div>
  <div class="detail">{detail_text}</div>
  <div class="url" title="{url_text}">{url_text}</div>
  <div class="actions">
    <button class="primary" id="btn-retry">重新加载</button>
    <button id="btn-back">返回上一页</button>
    <button id="btn-home">回到主页</button>
  </div>
  <div class="hint">动一动鼠标，让小猫帮你把页面追回来 🐾</div>
</div>

<div id="stage">
  <svg class="cat" id="cat" viewBox="0 0 120 92" xmlns="http://www.w3.org/2000/svg">
    <path id="tail" d="M26 62 C6 58 4 40 16 34" fill="none"
          stroke="var(--cat)" stroke-width="7" stroke-linecap="round"/>
    <ellipse cx="58" cy="62" rx="32" ry="20" fill="var(--cat)"/>
    <rect id="leg-back" x="36" y="70" width="10" height="17" rx="5" fill="var(--cat-dark)"/>
    <rect id="leg-front" x="70" y="70" width="10" height="17" rx="5" fill="var(--cat-dark)"/>
    <circle cx="90" cy="44" r="21" fill="var(--cat)"/>
    <polygon points="74,28 79,8 90,24" fill="var(--cat)"/>
    <polygon points="94,24 103,6 108,28" fill="var(--cat)"/>
    <polygon points="77,27 80,14 87,24" fill="var(--cat-light)"/>
    <polygon points="96,24 102,12 105,27" fill="var(--cat-light)"/>
    <ellipse cx="84" cy="42" rx="4.6" ry="5" fill="#FFFFFF"/>
    <ellipse cx="97" cy="42" rx="4.6" ry="5" fill="#FFFFFF"/>
    <circle id="pupil-l" cx="84" cy="42" r="2.6" fill="#1B1B1B"/>
    <circle id="pupil-r" cx="97" cy="42" r="2.6" fill="#1B1B1B"/>
    <ellipse cx="91" cy="52" rx="7" ry="5" fill="var(--cat-light)"/>
    <path d="M88 50 l3 2 l3 -2" fill="none" stroke="#1B1B1B" stroke-width="1.4"
          stroke-linecap="round"/>
    <path id="whisker-a" d="M84 52 L70 48" stroke="var(--cat-light)" stroke-width="1.2"/>
    <path id="whisker-b" d="M84 55 L70 58" stroke="var(--cat-light)" stroke-width="1.2"/>
  </svg>
</div>

<script>
(function () {{
  var stage = document.getElementById('stage');
  var cat = document.getElementById('cat');
  var tail = document.getElementById('tail');
  var legBack = document.getElementById('leg-back');
  var legFront = document.getElementById('leg-front');
  var pupilL = document.getElementById('pupil-l');
  var pupilR = document.getElementById('pupil-r');

  var mouse = {{ x: window.innerWidth * 0.5, y: window.innerHeight * 0.72 }};
  var pos = {{ x: window.innerWidth * 0.5, y: window.innerHeight * 0.72 }};
  var target = {{ x: mouse.x, y: mouse.y }};
  var facing = 1;
  var hops = 0;
  var hopT = 0;
  var lastPaw = 0;

  document.addEventListener('mousemove', function (event) {{
    mouse.x = event.clientX;
    mouse.y = event.clientY;
  }});
  document.addEventListener('touchmove', function (event) {{
    if (event.touches.length) {{
      mouse.x = event.touches[0].clientX;
      mouse.y = event.touches[0].clientY;
    }}
  }}, {{ passive: true }});
  document.addEventListener('click', function () {{
    hops = 3;   // 点击时小猫连跳几下
  }});

  function addPaw(x, y) {{
    var paw = document.createElement('div');
    paw.className = 'paw';
    paw.style.left = x + 'px';
    paw.style.top = y + 'px';
    stage.appendChild(paw);
    setTimeout(function () {{ paw.remove(); }}, 2600);
  }}

  function frame(now) {{
    var dx = mouse.x - pos.x;
    var dy = (mouse.y - 26) - pos.y;
    var distance = Math.sqrt(dx * dx + dy * dy) || 1;
    var walking = distance > 46;

    if (walking) {{
      var speed = Math.min(7.5, 1.6 + distance * 0.045);
      pos.x += dx / distance * speed;
      pos.y += dy / distance * speed;
      if (dx < -6) {{ facing = -1; }} else if (dx > 6) {{ facing = 1; }}
      if (now - lastPaw > 190) {{
        lastPaw = now;
        addPaw(pos.x + (facing > 0 ? 30 : 120), pos.y + 110);
      }}
    }} else if (hops > 0) {{
      hopT += 0.34;
      if (hopT > Math.PI) {{ hopT = 0; hops--; }}
    }}

    var hop = hops > 0 ? Math.abs(Math.sin(hopT)) * 16 : 0;
    var idle = walking ? 0 : Math.sin(now / 520) * 1.6;
    cat.style.transform =
      'translate(' + (pos.x - 75) + 'px,' + (pos.y - hop - 57 + idle) + 'px) ' +
      'scaleX(' + facing + ')';

    var swing = walking ? Math.sin(now / 70) * 16 : 0;
    legBack.setAttribute('transform', 'rotate(' + swing + ' 41 72)');
    legFront.setAttribute('transform', 'rotate(' + (-swing) + ' 75 72)');

    var wag = walking ? Math.sin(now / 95) * 9 : Math.sin(now / 420) * 4;
    tail.setAttribute('d', 'M26 62 C6 58 4 40 16 34');
    tail.setAttribute('transform', 'rotate(' + wag + ' 26 62)');

    var eyeX = (mouse.x - (pos.x + (facing > 0 ? 0 : 0))) * 0.02;
    var eyeY = (mouse.y - pos.y) * 0.02;
    eyeX = Math.max(-2.2, Math.min(2.2, eyeX));
    eyeY = Math.max(-2, Math.min(2, eyeY));
    pupilL.setAttribute('cx', 84 + eyeX * facing);
    pupilL.setAttribute('cy', 42 + eyeY);
    pupilR.setAttribute('cx', 97 + eyeX * facing);
    pupilR.setAttribute('cy', 42 + eyeY);

    requestAnimationFrame(frame);
  }}
  requestAnimationFrame(frame);

  function host(action, payload) {{
    try {{
      if (window.chrome && window.chrome.webview && window.chrome.webview.postMessage) {{
        window.chrome.webview.postMessage(JSON.stringify({{
          __lite_error: action, url: {url_js}, data: payload || null
        }}));
        return true;
      }}
    }} catch (e) {{}}
    return false;
  }}

  document.getElementById('btn-retry').onclick = function () {{
    location.href = {url_js};
  }};
  document.getElementById('btn-back').onclick = function () {{
    if (history.length > 1) {{ history.back(); }}
    else if (!host('home')) {{ location.href = 'about:blank'; }}
  }};
  document.getElementById('btn-home').onclick = function () {{
    if (!host('home')) {{ location.href = 'about:blank'; }}
  }};
}})();
</script>
</body>
</html>
"""


def warning_page(
    url: str,
    reasons: list,
    *,
    title: str = "该网址可能存在风险",
    dark: bool = False,
    accent: str = "#C6362B",
    app_title: str = "lite browser",
) -> str:
    """恶意网址警告页。"""
    bg = "#1E1E1E" if dark else "#FDF6F5"
    card = "#262626" if dark else "#FFFFFF"
    fg = "#E8E8E8" if dark else "#1F1F1F"
    dim = "#9A9A9A" if dark else "#6A6A6A"
    line = "#3A3A3A" if dark else "#EBD3D0"
    url_text = _escape(url)
    title_text = _escape(title)
    items = "".join(
        f"<li>{_escape(str(item))}</li>" for item in (reasons or ["该网址被判定为可能存在风险"])
    )
    url_js = json.dumps(url or "", ensure_ascii=False)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_text} - {_escape(app_title)}</title>
<style>
  :root {{ --bg:{bg}; --card:{card}; --fg:{fg}; --dim:{dim}; --line:{line}; --danger:{accent}; }}
  * {{ box-sizing: border-box; }}
  html, body {{
    height: 100%; margin: 0; background: var(--bg); color: var(--fg);
    font: 14px/1.75 "Microsoft YaHei UI", "Segoe UI", Tahoma, sans-serif;
    display: flex; align-items: center; justify-content: center; user-select: none;
  }}
  .card {{
    width: min(720px, 92vw); background: var(--card); border: 1px solid var(--line);
    border-top: 5px solid var(--danger); border-radius: 8px; padding: 28px 30px 24px;
    box-shadow: 0 6px 22px rgba(0,0,0,.12);
  }}
  .row {{ display: flex; gap: 16px; align-items: flex-start; }}
  .sign {{
    flex: 0 0 54px; height: 54px; border-radius: 50%; background: var(--danger);
    color: #fff; font-size: 34px; font-weight: 700; line-height: 54px; text-align: center;
  }}
  h1 {{ font-size: 21px; margin: 2px 0 6px; color: var(--danger); }}
  .url {{
    margin: 14px 0 4px; padding: 8px 12px; background: var(--bg);
    border: 1px solid var(--line); border-radius: 5px;
    font: 12px/1.6 Consolas, monospace; color: var(--dim);
    word-break: break-all; max-height: 66px; overflow: auto;
  }}
  ul {{ margin: 12px 0 0; padding-left: 22px; }}
  li {{ margin: 4px 0; }}
  .actions {{ margin-top: 24px; display: flex; gap: 10px; flex-wrap: wrap; }}
  button {{
    font: inherit; padding: 8px 20px; border-radius: 5px; cursor: pointer;
    border: 1px solid var(--line); background: var(--card); color: var(--fg);
  }}
  button.primary {{ background: var(--danger); border-color: var(--danger); color: #fff; }}
  button.ghost {{ background: transparent; color: var(--dim); border-style: dashed; }}
  button.ghost:hover {{ color: var(--danger); border-color: var(--danger); }}
  .tip {{ margin-top: 16px; color: var(--dim); font-size: 12px; }}
</style>
</head>
<body>
  <div class="card">
    <div class="row">
      <div class="sign">!</div>
      <div style="flex:1">
        <h1>{title_text}</h1>
        <div>此页面已被 lite browser 的安全防护拦截。请确认您信任该网站后再继续。</div>
      </div>
    </div>
    <div class="url">{url_text}</div>
    <ul>{items}</ul>
    <div class="actions">
      <button class="primary" id="btn-back">返回安全页面</button>
      <button class="ghost" id="btn-continue">我了解风险，继续访问</button>
    </div>
    <div class="tip">提示：可在「设置 → 隐私与安全 → 恶意网址拦截」中管理黑名单与规则。</div>
  </div>
<script>
(function () {{
  document.getElementById('btn-back').onclick = function () {{
    if (history.length > 1) {{ history.back(); }}
    else {{ location.href = 'lite:home'; }}
  }};
  document.getElementById('btn-continue').onclick = function () {{
    location.href = 'lite:allow?url=' + encodeURIComponent({url_js});
  }};
}})();
</script>
</body>
</html>
"""


def is_error_code(code: int) -> bool:
    return code >= 400 or code < 0


def friendly(code: int, message: str = "") -> str:
    headline, detail = describe(code, message)
    return f"{headline}（{code}）" if code else (headline or message)
