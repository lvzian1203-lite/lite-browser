"""视频播放自检页。

「帮助 → 视频播放自检」会生成并打开这个页面，用来快速判断
当前内核能不能播放 HTML5 视频（尤其是哔哩哔哩这类需要 H.264/AAC 的站点）：

* 显示当前渲染引擎、WebView2 版本、User-Agent；
* 实测 ``canPlayType`` 与 ``MediaSource.isTypeSupported`` 对
  H.264 / AAC / H.265 / AV1 的支持；
* 播放一段测试视频，并给出针对性的排查建议。
"""

from __future__ import annotations

import html as _html
import json
from pathlib import Path

from .config import APP_NAME, APP_VERSION, data_dir

#: 测试视频（公开可用的 H.264 样例）
TEST_VIDEO = "https://www.w3schools.com/html/mov_bbb.mp4"

#: 哔哩哔哩参考视频
BILI_VIDEO = "https://www.bilibili.com/video/BV1GJ411x7h7/"


def _engine_advice(engine_id: str, codec_ok: bool) -> tuple[str, str]:
    """返回 (状态等级, 建议 HTML)。"""
    if engine_id == "qtwebengine":
        return "bad", """
        <p><b>当前使用的是 QtWebEngine 内核</b>，它使用的是 Qt 官方的
        Chromium 构建，<b>不含 H.264 / AAC 等专有编解码器</b>，
        因此哔哩哔哩等站点会提示「您当前的浏览器不支持 HTML5 播放器」。</p>
        <p><b>解决方法</b>：打开「设置 → 外观 → 渲染引擎」，
        选择 <b>Edge WebView2（Chromium，含 H.264/AAC）</b>，
        确定后重启程序即可。</p>
        """
    if not codec_ok:
        return "bad", """
        <p>当前是 Edge WebView2 内核，但检测到 <b>H.264 解码不可用</b>。
        这通常说明系统的 WebView2 运行时缺少媒体组件。</p>
        <p><b>解决方法</b>：到微软官网下载并安装
        「Microsoft Edge WebView2 Runtime（Evergreen Standalone Installer）」，
        或直接修复 / 重装 Microsoft Edge，然后重启程序。</p>
        """
    return "ok", """
    <p>当前内核支持 H.264 / AAC，可以正常播放哔哩哔哩等站点的 HTML5 视频。</p>
    <p><b>如果个别视频仍然播不了</b>，请依次确认：</p>
    <ul>
      <li><b>是否需要登录</b>：番剧、影视、1080P 以上清晰度、部分 UP 主视频
          要求登录后才能观看。未登录时页面会显示「出错啦」或要求登录。</li>
      <li><b>是否在后台被挂起</b>：后台标签页闲置较久会被挂起以省内存。
          正在播放音频/视频的标签页已自动跳过挂起；
          如仍遇到播放中断，可在「设置 → 性能」关闭「后台标签页自动挂起」。</li>
      <li><b>是否是大会员内容</b>：会员专享清晰度 / 番剧需要相应权限。</li>
      <li><b>网络原因</b>：视频分片（.m4s）走的是独立 CDN，
          可在「工具 → Cookie 与缓存管理」里清理缓存后刷新页面重试。</li>
    </ul>
    """


def build_page(engine_id: str = "", engine_label: str = "", browser_version: str = "",
               extra: dict | None = None) -> str:
    """生成自检页 HTML。"""
    level, advice = _engine_advice(engine_id, True)
    payload = json.dumps(
        {
            "engine": engine_id,
            "label": engine_label,
            "version": browser_version,
            "app": APP_NAME,
            "appVersion": APP_VERSION,
        },
        ensure_ascii=False,
    )
    badge_color = {"ok": "#1E7B34", "bad": "#B02A1E"}.get(level, "#8A6A00")
    badge_text = {"ok": "支持 HTML5 视频", "bad": "⚠ 当前内核无法播放多数视频"}.get(
        level, "需要确认"
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>视频播放自检 - {_html.escape(APP_NAME)}</title>
<style>
  body {{ font: 14px/1.7 "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 20px 26px 40px; color: #1F1F1F; background: #F7F7F7; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: #6A6A6A; margin-bottom: 16px; }}
  .badge {{ display: inline-block; padding: 3px 12px; border-radius: 12px;
            color: #fff; background: {badge_color}; font-size: 13px; }}
  .card {{ background: #fff; border: 1px solid #E2E2E2; border-radius: 8px;
           padding: 14px 18px; margin: 14px 0; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td {{ padding: 4px 8px; border-bottom: 1px solid #EEE; }}
  td:first-child {{ width: 220px; color: #555; }}
  .ok {{ color: #1E7B34; font-weight: bold; }}
  .no {{ color: #B02A1E; font-weight: bold; }}
  video {{ width: 480px; max-width: 100%; background: #000; border-radius: 6px; }}
  code {{ background: #F0F0F0; padding: 1px 5px; border-radius: 3px; }}
  .tip {{ color: #6A6A6A; font-size: 13px; }}
  button {{ font: inherit; padding: 6px 16px; border-radius: 5px; cursor: pointer;
            border: 1px solid #C6C6C6; background: #FDFDFD; margin-right: 8px; }}
  button:hover {{ border-color: #0067C0; color: #0067C0; }}
</style>
</head>
<body>
<h1>视频播放自检</h1>
<div class="sub">{_html.escape(APP_NAME)} {_html.escape(APP_VERSION)}
  · 用于确认当前内核能否播放 HTML5 视频（如哔哩哔哩）</div>
<div class="badge" id="badge">{badge_text}</div>

<div class="card">
  <table>
    <tr><td>渲染引擎</td><td id="engine">{_html.escape(engine_label or engine_id or '未知')}</td></tr>
    <tr><td>内核版本</td><td id="ver">{_html.escape(browser_version or '（未报告）')}</td></tr>
    <tr><td>User-Agent</td><td id="ua">读取中…</td></tr>
    <tr><td>H.264（video/mp4; avc1）</td><td id="h264">检测中…</td></tr>
    <tr><td>AAC（audio/mp4; mp4a）</td><td id="aac">检测中…</td></tr>
    <tr><td>H.265（HEVC）</td><td id="h265">检测中…</td></tr>
    <tr><td>AV1</td><td id="av1">检测中…</td></tr>
    <tr><td>MediaSource（MSE，流媒体必需）</td><td id="mse">检测中…</td></tr>
    <tr><td>加密媒体（EME/Widevine）</td><td id="eme">检测中…</td></tr>
  </table>
</div>

<div class="card">
  <div style="margin-bottom:8px"><b>测试视频</b>（H.264 + AAC）</div>
  <video id="v" controls autoplay muted playsinline src="{TEST_VIDEO}"></video>
  <div class="tip" id="vstat" style="margin-top:8px">正在加载…</div>
  <div style="margin-top:10px">
    <button onclick="location.href='{BILI_VIDEO}'">打开哔哩哔哩测试视频</button>
    <button onclick="document.getElementById('v').play()">重新播放测试视频</button>
  </div>
</div>

<div class="card" id="advice">
  <b>结论与建议</b>
  {advice}
  <div class="tip">提示：修改「设置 → 外观 → 渲染引擎」后需要重启程序才能生效。</div>
</div>

<script>
var INFO = {payload};

function mark(id, value) {{
  var node = document.getElementById(id);
  if (!node) return;
  var yes = !!value;
  node.innerHTML = yes ? '<span class="ok">支持</span>'
                       : '<span class="no">不支持</span>';
}}

(function () {{
  var t = document.createElement('video');
  var pick = function (type) {{
    var r = t.canPlayType(type);
    return r === 'probably' || r === 'maybe';
  }};
  var h264 = pick('video/mp4; codecs="avc1.42E01E"');
  var aac = pick('audio/mp4; codecs="mp4a.40.2"');
  mark('h264', h264);
  mark('aac', aac);
  mark('h265', pick('video/mp4; codecs="hev1.1.6.L93.B0"'));
  mark('av1', pick('video/mp4; codecs="av01.0.05M.08"'));
  var mse = false;
  try {{
    mse = !!(window.MediaSource &&
             MediaSource.isTypeSupported('video/mp4; codecs="avc1.640028"'));
  }} catch (e) {{}}
  mark('mse', mse);
  mark('eme', !!(navigator.requestMediaKeySystemAccess));
  document.getElementById('ua').textContent = navigator.userAgent;
  document.getElementById('ua').title = navigator.userAgent;

  if (!h264) {{
    var badge = document.getElementById('badge');
    badge.textContent = '⚠ 当前内核不支持 H.264，多数视频无法播放';
    badge.style.background = '#B02A1E';
  }}
}})();

(function () {{
  var v = document.getElementById('v');
  var stat = document.getElementById('vstat');
  function tick() {{
    stat.textContent =
      'currentTime = ' + v.currentTime.toFixed(2) + ' 秒　' +
      'readyState = ' + v.readyState + '　' +
      '尺寸 = ' + v.videoWidth + '×' + v.videoHeight + '　' +
      'error = ' + (v.error ? (v.error.code + ' / ' + v.error.message) : '无');
  }}
  setInterval(tick, 400);
  tick();
}})();
</script>
</body>
</html>
"""


def write_page(engine_id: str = "", engine_label: str = "", browser_version: str = "",
               extra: dict | None = None) -> Path:
    """把自检页写入数据目录并返回路径。"""
    folder = data_dir() / "pages"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "video-check.html"
    path.write_text(
        build_page(engine_id, engine_label, browser_version, extra), encoding="utf-8"
    )
    return path


def page_url(**kwargs) -> str:
    return write_page(**kwargs).as_uri()
