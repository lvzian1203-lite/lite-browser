"""浏览器渲染引擎抽象层。

lite browser 支持两种 Chromium 内核：

* ``webview2``   —— Microsoft Edge WebView2（推荐，Windows 自带运行时，
                    含 H.264/AAC 等完整编解码器，可直接播放哔哩哔哩等站点）
* ``qtwebengine`` —— Qt 自带的 QtWebEngine（跨平台回退方案，
                    官方二进制包不含 H.264/AAC）
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QWidget

from .config import APP_NAME, data_dir

ENGINE_WEBVIEW2 = "webview2"
ENGINE_QTWEB = "qtwebengine"
ENGINE_AUTO = "auto"

ENGINE_LABELS = {
    ENGINE_WEBVIEW2: "Edge WebView2（Chromium，含 H.264/AAC）",
    ENGINE_QTWEB: "QtWebEngine（Chromium，仅开源编解码器）",
}

#: DNS 预解析：只预解析 / 预连接域名，不下载完整页面，代价很低
_PREFETCH_JS = r"""
(function () {
  try {
    if (window.__litePrefetched) { return; }
    window.__litePrefetched = true;
    var links = document.querySelectorAll('a[href^="http"]');
    var seen = {}, count = 0;
    for (var i = 0; i < links.length && count < 24; i++) {
      try {
        var url = new URL(links[i].href);
        if (seen[url.host]) { continue; }
        seen[url.host] = 1;
        count++;
        var dns = document.createElement('link');
        dns.rel = 'dns-prefetch';
        dns.href = url.protocol + '//' + url.host;
        document.head.appendChild(dns);
        var conn = document.createElement('link');
        conn.rel = 'preconnect';
        conn.href = url.protocol + '//' + url.host;
        conn.crossOrigin = 'anonymous';
        document.head.appendChild(conn);
      } catch (e) {}
    }
  } catch (e) {}
})();
"""


class BrowserEngine(QWidget):
    """一个标签页里的网页视图。"""

    url_changed = Signal(str)
    title_changed = Signal(str)
    load_started = Signal()
    load_progress = Signal(int)
    load_finished = Signal(bool)
    icon_changed = Signal(object)
    status_message = Signal(str)
    new_window_requested = Signal(str)
    fullscreen_requested = Signal(bool)
    accelerator = Signal(int, bool, bool, bool)   # vk, ctrl, shift, alt
    find_result = Signal(int, int)
    #: 显示自定义错误页（url, 错误码）
    error_page_shown = Signal(str, int)
    #: HTTPS 证书校验失败（CertificateInfo）
    certificate_error = Signal(object)
    #: 错误页 / 警告页发来的内部命令，如 lite:home、lite:allow?url=...
    command_requested = Signal(str)
    #: 自动弹窗被拦截（网址）
    popup_blocked = Signal(str)

    engine_id = ENGINE_QTWEB

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        #: 由主窗口注入：根据建议文件名返回保存路径，返回 None 表示取消
        self.save_path_provider: Optional[Callable[[str], Optional[str]]] = None
        #: 由主窗口注入：新建一个标签页并返回其引擎（QtWebEngine 的 createWindow 需要）
        self.new_tab_provider: Optional[Callable[[], "BrowserEngine"]] = None
        #: 由主窗口注入：下载管理器（统一下载目录与进度）
        self.download_manager = None
        #: 无痕浏览：不写入历史、Cookie 与缓存
        self.incognito = False
        self._pending_url: Optional[str] = None
        #: 正在显示自定义错误页时记录原始网址（地址栏保持显示它）
        self._error_url = ""
        #: 被拦截的网址（恶意网址警告页）
        self._blocked_url = ""
        #: 正在加载内置页面（错误页 / 警告页）
        self._internal_page = False
        #: 由主窗口注入：网址安全判定器（netsec.SecurityManager）
        self.security_manager = None
        #: 由主窗口注入：广告屏蔽规则库（adblock.AdRuleStore）
        self.adblock_store = None
        #: 由主窗口注入：配置对象
        self.config = None
        #: 用户在警告页上选择「继续访问」的网址
        self._allow_once: set[str] = set()
        #: 当前标签页要屏蔽的广告元素选择器
        self._ad_rules: list[str] = []
        #: 是否拦截网页自动弹出的窗口（非用户点击触发）
        self._block_popups = True
        #: Ruffle（Flash 兼容）状态
        self._ruffle_enabled = False
        self._ruffle_public_path = ""
        self._ruffle_config = ""
        #: 内部页面（错误页 / 警告页 / .swf 播放页 / 自检页）期间地址栏要显示的网址
        self.address_override = ""

    # -- 元信息 ----------------------------------------------------------- #
    @property
    def engine_label(self) -> str:
        return ENGINE_LABELS.get(self.engine_id, self.engine_id)

    def is_ready(self) -> bool:
        return True

    # -- 导航 ------------------------------------------------------------- #
    def load(self, url: str) -> None:  # pragma: no cover - 抽象
        raise NotImplementedError

    def current_url(self) -> str:  # pragma: no cover - 抽象
        return ""

    def current_title(self) -> str:  # pragma: no cover - 抽象
        return ""

    def can_go_back(self) -> bool:
        return False

    def can_go_forward(self) -> bool:
        return False

    def go_back(self) -> None:
        pass

    def go_forward(self) -> None:
        pass

    def reload(self) -> None:
        pass

    def stop(self) -> None:
        pass

    # -- 缩放 ------------------------------------------------------------- #
    def zoom_factor(self) -> float:
        return 1.0

    def set_zoom_factor(self, factor: float) -> None:
        pass

    # -- 脚本 / 查找 ------------------------------------------------------ #
    def run_js(self, code: str, callback: Optional[Callable[[object], None]] = None) -> None:
        pass

    def find_text(self, text: str, forward: bool = True) -> None:
        pass

    def clear_find(self) -> None:
        pass

    def edit_action(self, name: str) -> None:
        """name: copy / cut / paste / undo / redo / selectall"""

    # -- 其它 ------------------------------------------------------------- #
    def save_page(self) -> None:
        pass

    def open_dev_tools(self) -> None:
        pass

    def focus_content(self) -> None:
        self.setFocus()

    def shutdown(self) -> None:
        pass

    # -- 用户代理 --------------------------------------------------------- #
    def set_user_agent(self, user_agent: str) -> None:
        """设置 User-Agent（空字符串表示使用内核默认值）。"""

    # -- Cookie / 缓存 ---------------------------------------------------- #
    def list_cookies(self, callback) -> None:
        """异步枚举 Cookie，回调参数为 [{domain, name, path, ...}]。"""
        callback([])

    def delete_cookie(self, cookie: dict) -> None:
        pass

    def delete_all_cookies(self) -> None:
        pass

    def delete_session_cookies(self) -> None:
        pass

    def clear_cache(self) -> None:
        pass

    def clear_site_data(self) -> None:
        """清理 localStorage / IndexedDB 等站点数据。"""

    # -- 错误页 / 保存 / 打印 --------------------------------------------- #
    def show_error_page(self, html: str, url: str = "") -> None:
        """显示内置页面。

        做法是先把 HTML 写成临时文件，再用**普通导航**打开：
        比 NavigateToString / setHtml 更稳（不会与被取消的导航互相触发），
        两个内核也共用同一套实现。地址栏显示 ``address_override``
        （即用户实际访问的网址），不会暴露内部临时文件路径。
        """
        if url:
            self.address_override = url
        try:
            folder = data_dir() / "pages"
            folder.mkdir(parents=True, exist_ok=True)
            for stale in folder.glob("internal-*.html"):
                try:
                    stale.unlink()
                except OSError:
                    pass
            self._page_seq = getattr(self, "_page_seq", 0) + 1
            path = folder / f"internal-{self._page_seq}.html"
            path.write_text(html, encoding="utf-8")
        except OSError:
            return
        self._internal_page = True
        self.load(path.as_uri())

    def set_error_page(self, url: str, code: int, message: str = "",
                       *, can_go_back: bool = True) -> None:
        """生成并显示自定义错误页。"""
        from .errors import error_page
        from .theme import current as current_theme

        spec = current_theme()
        html = error_page(
            url, code, message,
            dark=spec.dark,
            accent=spec.highlight,
            title=APP_NAME,
            can_go_back=can_go_back,
        )
        self._error_url = url
        self.show_error_page(html, url)
        self.error_page_shown.emit(url, code)

    def set_warning_page(self, url: str, verdict) -> None:
        """显示恶意网址警告页。"""
        from .errors import warning_page
        from .theme import current as current_theme

        spec = current_theme()
        html = warning_page(
            url,
            getattr(verdict, "reasons", []),
            title=getattr(verdict, "title", "该网址可能存在风险"),
            dark=spec.dark,
            accent=spec.highlight,
            app_title=APP_NAME,
        )
        self._error_url = url
        self._blocked_url = url
        self.show_error_page(html, url)
        self.error_page_shown.emit(url, -100)

    def save_page_as(self, path: str, fmt: str = "mhtml") -> bool:
        """另存网页：fmt = mhtml | html | html-only。"""
        return False

    def print_page(self) -> None:
        """打印当前网页。"""

    def export_pdf(self, path: str) -> bool:
        """导出为 PDF。"""
        return False

    # -- 性能 ------------------------------------------------------------- #
    def set_content_visible(self, visible: bool) -> None:
        """显示 / 隐藏网页内容（后台标签页隐藏后才能真正挂起并省内存）。"""

    def suspend(self) -> None:
        """挂起（释放后台标签页资源）。"""

    def resume(self) -> None:
        """恢复挂起的标签页。"""

    def is_suspended(self) -> bool:
        return False

    def is_playing_audio(self) -> bool:
        """页面是否正在播放声音/视频（挂起会打断播放，需要跳过）。"""
        return False

    # -- 加载偏好 --------------------------------------------------------- #
    def set_preferences(self, *, load_images: bool = True, preload: bool = False,
                        smooth_scroll: bool = False) -> None:
        """设置加载偏好（图片 / DNS 预解析 / 平滑滚动）。"""
        self._prefs = {
            "load_images": bool(load_images),
            "preload": bool(preload),
            "smooth_scroll": bool(smooth_scroll),
        }

    def prefetch_links(self) -> None:
        """对当前页面的链接做 DNS 预解析，加快点击后的打开速度。"""
        if not getattr(self, "_prefs", {}).get("preload"):
            return
        self.run_js(_PREFETCH_JS)

    # -- 广告屏蔽 / Flash 兼容 -------------------------------------------- #
    def set_adblock(self, rules: list[str] | None = None, *, block_popups: bool = True) -> None:
        """设置当前标签页要屏蔽的元素选择器与弹窗策略。"""
        self._ad_rules = list(rules or [])
        self._block_popups = bool(block_popups)
        self.apply_adblock()

    def apply_adblock(self) -> None:
        """把屏蔽规则注入当前页面（含动态内容监听）。"""
        rules = getattr(self, "_ad_rules", None)
        if not rules:
            return
        from .adblock import apply_script

        self.run_js(apply_script(rules))

    def _rules_for(self, url: str) -> list[str]:
        """查询适用于该网址的广告屏蔽规则。"""
        store = getattr(self, "adblock_store", None)
        if store is None:
            return []
        try:
            return store.selectors_for(url)
        except Exception:
            return []

    def start_ad_picker(self) -> None:
        """进入「点选广告元素」模式。"""
        from .adblock import picker_script

        self.run_js(picker_script())

    #: 是否支持 Ruffle（本地资源供给依赖 WebView2 的资源拦截能力）
    supports_ruffle = False

    def set_ruffle(self, enabled: bool, public_path: str = "", config_json: str = "") -> None:
        """启用 / 关闭 Ruffle（无广告 Flash 模拟器）。"""
        self._ruffle_enabled = bool(enabled)
        self._ruffle_public_path = public_path
        self._ruffle_config = config_json
        self.apply_ruffle()

    def apply_ruffle(self) -> None:
        """把 Ruffle 引导脚本注入当前页面。"""
        if not getattr(self, "_ruffle_enabled", False):
            return
        from .ruffle import bootstrap_script

        self.run_js(bootstrap_script(
            getattr(self, "_ruffle_public_path", ""),
            getattr(self, "_ruffle_config", ""),
        ))

    # -- 内部命令（错误页/警告页按钮） ------------------------------------ #
    def handle_internal_url(self, url: str) -> bool:
        """拦截 ``lite:`` 开头的内部命令，返回 True 表示已处理。"""
        if not url or not url.lower().startswith("lite:"):
            return False
        self.command_requested.emit(url)
        return True


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def await_task(task, on_done, on_error=None, interval: int = 20) -> None:
    """在 Qt 事件循环中轮询 .NET Task 的完成状态。

    直接访问 ``task.Result`` 会阻塞主线程，而 WebView2 的异步回调
    恰恰需要主线程继续跑消息循环，因此必须轮询。
    """
    timer = QTimer()

    def check() -> None:
        try:
            done = bool(task.IsCompleted)
        except Exception as exc:  # noqa: BLE001
            timer.stop()
            if on_error is not None:
                on_error(exc)
            return
        if not done:
            return
        timer.stop()
        try:
            if bool(task.IsFaulted):
                raise RuntimeError(str(task.Exception))
            on_done(task.Result)
        except Exception as exc:  # noqa: BLE001
            if on_error is not None:
                on_error(exc)

    timer.timeout.connect(check)
    timer.start(interval)


# --------------------------------------------------------------------------- #
# 工厂
# --------------------------------------------------------------------------- #
def available_engines() -> list[str]:
    """返回当前系统可用的引擎 id 列表（按优先级排序）。"""
    engines: list[str] = []
    try:
        from . import wv2engine

        if wv2engine.is_supported():
            engines.append(ENGINE_WEBVIEW2)
    except Exception:
        pass
    engines.append(ENGINE_QTWEB)
    return engines


def resolve_engine(preferred: str) -> str:
    """把用户设置解析成实际可用的引擎。"""
    engines = available_engines()
    if preferred in engines:
        return preferred
    return engines[0]


def create_engine(
    engine_id: str, parent: QWidget | None = None, *, incognito: bool = False
) -> BrowserEngine:
    """按 id 创建引擎实例。"""
    if engine_id == ENGINE_WEBVIEW2:
        from . import wv2engine

        return wv2engine.WebView2Engine(parent, incognito=incognito)
    from . import qtengine

    return qtengine.QtWebEngine(parent, incognito=incognito)


def prepare_engine(engine_id: str) -> None:
    """在创建 QApplication 之前调用（QtWebEngine 需要提前导入）。"""
    if engine_id == ENGINE_QTWEB:
        from . import qtengine  # noqa: F401
