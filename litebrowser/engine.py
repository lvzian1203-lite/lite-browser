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

ENGINE_WEBVIEW2 = "webview2"
ENGINE_QTWEB = "qtwebengine"
ENGINE_AUTO = "auto"

ENGINE_LABELS = {
    ENGINE_WEBVIEW2: "Edge WebView2（Chromium，含 H.264/AAC）",
    ENGINE_QTWEB: "QtWebEngine（Chromium，仅开源编解码器）",
}


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
