"""Microsoft Edge WebView2 引擎后端（Windows）。

WebView2 使用系统自带的 Edge 运行时，是完整的 Chromium，
包含 H.264 / AAC 等专有编解码器，可以正常播放哔哩哔哩等站点的 HTML5 视频。
"""

from __future__ import annotations

import logging
import ctypes
import json
import os
import sys
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QWidget

from .config import data_dir, resource_path
from .engine import (
    ENGINE_WEBVIEW2,
    BrowserEngine,
    EngineCapabilities,
    EngineState,
    await_task,
)

log = logging.getLogger(__name__)

#: WebView2 运行时在注册表中的标识
_RUNTIME_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

_STATE: dict = {"checked": False, "ok": False, "reason": "", "loaded": False}


# --------------------------------------------------------------------------- #
# 环境复用与预热
#
# * 同一个 user data 目录只需要一个 CoreWebView2Environment：所有标签页共享它，
#   可以共用浏览器进程、缓存与 Cookie，明显降低多标签时的内存占用；
# * 程序启动时提前开始创建（界面构造/显示期间并行进行），首个标签页直接复用，
#   省下数百毫秒的首屏等待。
# --------------------------------------------------------------------------- #
_ENVIRONMENT: dict = {"started": False, "task": None, "environment": None, "error": None}

#: 代取的 .swf 缓存（重新加载页面时不必再下一次）
_SWF_CACHE: dict[str, tuple[bytes, str]] = {}
_SWF_CACHE_LIMIT = 48 * 1024 * 1024


def _build_environment_options(config):
    """构造 WebView2 环境参数（预热与实际创建共用，保证一致）。"""
    from Microsoft.Web.WebView2.Core import CoreWebView2EnvironmentOptions

    options = CoreWebView2EnvironmentOptions()
    try:
        options.Language = "zh-CN"
    except Exception as lite_exc:
        log.debug("忽略异常：%s", lite_exc)
        pass
    try:
        options.AreBrowserExtensionsEnabled = True
    except Exception as lite_exc:
        log.debug("忽略异常：%s", lite_exc)
        pass

    arguments: list[str] = []
    if config is not None:
        try:
            if config.get("smooth_scroll"):
                arguments.append("--enable-smooth-scrolling")
            cache_mb = int(config.get("cache_size_mb") or 0)
            if cache_mb > 0:
                arguments.append(f"--disk-cache-size={cache_mb * 1024 * 1024}")
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
    if arguments:
        try:
            options.AdditionalBrowserArguments = " ".join(arguments)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
    return options


def _create_environment_task(config):
    from Microsoft.Web.WebView2.Core import CoreWebView2Environment

    user_data = data_dir() / "webview2"
    user_data.mkdir(parents=True, exist_ok=True)
    return CoreWebView2Environment.CreateAsync(
        None, str(user_data), _build_environment_options(config)
    )


def prewarm_environment(config=None) -> None:
    """尽早开始创建 WebView2 环境（不阻塞界面），供所有标签页复用。"""
    if _ENVIRONMENT["started"]:
        return
    _ENVIRONMENT["started"] = True

    import time as _time

    t0 = _time.perf_counter()
    ok, error = load_runtime()
    _STATE["clr_ms"] = (_time.perf_counter() - t0) * 1000
    if not ok:
        _ENVIRONMENT["error"] = error
        _log_failure(f".NET 运行时加载失败：{error}")
        return
    try:
        _ENVIRONMENT["task_started"] = _time.perf_counter()
        _ENVIRONMENT["task"] = _create_environment_task(config)
    except Exception as exc:  # noqa: BLE001
        _ENVIRONMENT["error"] = exc
        _log_failure(f"WebView2 环境创建失败：{exc!r}")


def _log_failure(message: str) -> None:
    """把初始化失败原因写到数据目录，便于排查（窗口程序没有控制台）。"""
    try:
        (data_dir() / "webview_error.txt").write_text(
            f"{message}\n{_STATE.get('runtime_errors')}\n", encoding="utf-8"
        )
    except OSError as lite_exc:
        log.debug("忽略异常：%s", lite_exc)
        pass


def environment_task(config=None):
    """返回共享的环境创建任务（必要时立即创建）。"""
    if not _ENVIRONMENT["started"]:
        prewarm_environment(config)
    return _ENVIRONMENT["task"]


def cached_environment():
    """已就绪的共享环境（没有则返回 None）。"""
    return _ENVIRONMENT["environment"]


def store_environment(environment) -> None:
    _ENVIRONMENT["environment"] = environment


def environment_error():
    return _ENVIRONMENT["error"]

#: 虚拟键 -> Qt 键
_VK_TO_QT: dict[int, int] = {}
for _i in range(26):
    _VK_TO_QT[0x41 + _i] = int(Qt.Key_A) + _i
for _i in range(10):
    _VK_TO_QT[0x30 + _i] = int(Qt.Key_0) + _i
for _i in range(12):
    _VK_TO_QT[0x70 + _i] = int(Qt.Key_F1) + _i
_VK_TO_QT.update(
    {
        0x09: int(Qt.Key_Tab),
        0x0D: int(Qt.Key_Return),
        0x1B: int(Qt.Key_Escape),
        0x08: int(Qt.Key_Backspace),
        0x2E: int(Qt.Key_Delete),
        0x20: int(Qt.Key_Space),
        0x21: int(Qt.Key_PageUp),
        0x22: int(Qt.Key_PageDown),
        0x23: int(Qt.Key_End),
        0x24: int(Qt.Key_Home),
        0x25: int(Qt.Key_Left),
        0x26: int(Qt.Key_Up),
        0x27: int(Qt.Key_Right),
        0x28: int(Qt.Key_Down),
        0x6B: int(Qt.Key_Plus),
        0x6D: int(Qt.Key_Minus),
        0xBB: int(Qt.Key_Equal),
        0xBD: int(Qt.Key_Minus),
        0xDB: int(Qt.Key_BracketLeft),
        0xDD: int(Qt.Key_BracketRight),
    }
)

#: 需要转发给主窗口的按键（其余留给页面）
_FORWARD_VKS = set(_VK_TO_QT)
_FORWARD_VKS.update({0x74, 0x75, 0x76, 0x77, 0x7A})  # F5 F6 F7 F8 F11


# --------------------------------------------------------------------------- #
# 运行时加载
# --------------------------------------------------------------------------- #
def lib_dir() -> Path:
    """随程序分发的 WebView2 程序集目录。"""
    return resource_path("lib", "webview2")


def runtime_version() -> Optional[str]:
    """已安装的 WebView2 运行时版本（未安装返回 None）。"""
    if sys.platform != "win32":
        return None
    import winreg

    roots = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_RUNTIME_GUID}"),
    ]
    for root, path in roots:
        try:
            with winreg.OpenKey(root, path) as key:
                value, _ = winreg.QueryValueEx(key, "pv")
                if value:
                    return str(value)
        except OSError as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            continue
    return None


def is_supported() -> bool:
    """是否可以使用 WebView2 引擎（不加载 .NET，快速判断）。"""
    if _STATE["checked"]:
        return bool(_STATE["ok"])
    _STATE["checked"] = True

    if sys.platform != "win32":
        _STATE["reason"] = "仅支持 Windows"
        return False
    if not (lib_dir() / "Microsoft.Web.WebView2.Core.dll").exists():
        _STATE["reason"] = "缺少 WebView2 程序集"
        return False
    try:
        import pythonnet  # noqa: F401
    except Exception:
        _STATE["reason"] = "缺少 pythonnet"
        return False
    if runtime_version() is None:
        _STATE["reason"] = "未安装 WebView2 运行时"
        return False

    _STATE["ok"] = True
    return True


def unsupported_reason() -> str:
    return str(_STATE.get("reason") or "")


def browser_version() -> str:
    """WebView2 内核版本（优先返回实际运行的版本）。"""
    if _STATE.get("browser_version"):
        return str(_STATE["browser_version"])
    return runtime_version() or "未知"


def _strip_motw(folder: Path) -> None:
    """去掉“来自网络”标记，.NET Framework 才愿意加载这些程序集。"""
    for path in folder.rglob("*.dll"):
        try:
            os.remove(str(path) + ":Zone.Identifier")
        except OSError as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass


def _modifiers() -> tuple[bool, bool, bool]:
    user32 = ctypes.windll.user32
    ctrl = bool(user32.GetKeyState(0x11) & 0x8000)
    shift = bool(user32.GetKeyState(0x10) & 0x8000)
    alt = bool(user32.GetKeyState(0x12) & 0x8000)
    return ctrl, shift, alt


def load_runtime() -> tuple[bool, str]:
    """加载 .NET 运行时与 WebView2 程序集。返回 (是否成功, 错误信息)。"""
    if _STATE["loaded"]:
        return True, ""
    if _STATE.get("error"):
        return False, str(_STATE["error"])
    if not is_supported():
        return False, unsupported_reason()

    folder = lib_dir()
    native = folder / "runtimes" / "win-x64" / "native"
    if native.exists():
        os.environ["PATH"] = str(native) + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(str(native))
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
    _strip_motw(folder)

    try:
        import time as _t

        t_pre = _t.perf_counter()
        from pythonnet import load

        _STATE["t_importnet"] = (_t.perf_counter() - t_pre) * 1000

        t0 = _t.perf_counter()
        last_error: Optional[Exception] = None
        order: list[str] = []
        forced = os.environ.get("LITE_BROWSER_DOTNET")
        if forced in ("coreclr", "netfx"):
            order.append(forced)
        # 优先 .NET Framework：它是 Windows 自带组件，且打包后加载明显更快
        # （实测 coreclr 首次加载约 6.4s，netfx 约 0.3s）
        order += ["netfx", "coreclr"]
        tried: set[str] = set()
        errors: dict[str, str] = {}
        for runtime in order:
            if runtime in tried:
                continue
            tried.add(runtime)
            attempt = _t.perf_counter()
            try:
                load(runtime)
                _STATE["runtime"] = runtime
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                errors[runtime] = (
                    f"{( _t.perf_counter() - attempt) * 1000:.0f} ms, "
                    f"{type(exc).__name__}: {exc}"
                )
        _STATE["runtime_errors"] = errors
        if last_error is not None:
            raise RuntimeError(
                "没有可用的 .NET 运行时：" + "; ".join(f"{k}: {v}" for k, v in errors.items())
            )
        _STATE["t_load"] = (_t.perf_counter() - t0) * 1000

        t1 = _t.perf_counter()
        import clr

        _STATE["t_import"] = (_t.perf_counter() - t1) * 1000

        t2 = _t.perf_counter()
        clr.AddReference(str(folder / "Microsoft.Web.WebView2.Core.dll"))
        # .NET Framework 里叫 System.Drawing，.NET (CoreCLR) 里叫 System.Drawing.Primitives
        for assembly in ("System.Drawing.Primitives", "System.Drawing"):
            try:
                clr.AddReference(assembly)
                _STATE["drawing_assembly"] = assembly
                break
            except Exception:  # noqa: BLE001
                continue
        _STATE["t_ref"] = (_t.perf_counter() - t2) * 1000

        from Microsoft.Web.WebView2.Core import (  # noqa: F401
            CoreWebView2AcceleratorKeyPressedEventArgs,
            CoreWebView2ContentLoadingEventArgs,
            CoreWebView2DOMContentLoadedEventArgs,
            CoreWebView2DownloadStartingEventArgs,
            CoreWebView2Environment,
            CoreWebView2EnvironmentOptions,
            CoreWebView2NavigationCompletedEventArgs,
            CoreWebView2NavigationStartingEventArgs,
            CoreWebView2NewWindowRequestedEventArgs,
            CoreWebView2ProcessFailedEventArgs,
            CoreWebView2SourceChangedEventArgs,
            CoreWebView2WebMessageReceivedEventArgs,
        )
        from System import EventHandler, IntPtr, Object  # noqa: F401
        from System.IO import MemoryStream  # noqa: F401

        try:
            from System.Drawing import Rectangle  # noqa: F401
        except ImportError:
            Rectangle = None  # type: ignore[assignment]
        _STATE["t_types"] = (_t.perf_counter() - t2) * 1000
    except Exception as exc:  # noqa: BLE001
        _STATE["error"] = exc
        return False, str(exc)

    _STATE["loaded"] = True
    return True, ""


# --------------------------------------------------------------------------- #
# 注入脚本
# --------------------------------------------------------------------------- #
_INJECT_JS = r"""
(function () {
  if (window.__liteInjected) { return; }
  window.__liteInjected = true;
  function report(url) {
    try { window.chrome.webview.postMessage(JSON.stringify({ __lite: 'hover', url: url || '' })); }
    catch (e) {}
  }
  document.addEventListener('mouseover', function (e) {
    var t = e.target;
    var a = (t && t.closest) ? t.closest('a') : null;
    if (a) { report(a.href); }
  }, true);
  document.addEventListener('mouseout', function (e) {
    var t = e.target;
    var a = (t && t.closest) ? t.closest('a') : null;
    if (a) { report(''); }
  }, true);
})();
"""


class WebView2Engine(BrowserEngine):
    """用 WebView2 实现引擎。"""

    engine_id = ENGINE_WEBVIEW2
    supports_ruffle = True
    #: 能力描述：界面按能力判断而不是比较 engine_id（P2-2）
    capabilities = EngineCapabilities(ruffle=True)

    def __init__(self, parent: QWidget | None = None, *, incognito: bool = False) -> None:
        super().__init__(parent)
        self.incognito = bool(incognito)
        self.setObjectName("wv2Engine")
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, False)
        self.setAutoFillBackground(True)
        self.setStyleSheet("background: #FFFFFF;")

        self._controller = None
        self._core = None
        self._started = False
        self._ready = False
        self._failed = False
        self._delegates: list = []
        self._download_watch: list = []
        self._download_timer = QTimer(self)
        self._download_timer.setInterval(400)
        self._download_timer.timeout.connect(self._poll_downloads)
        self._zoom = 1.0
        self._default_ua = ""
        self._suspended = False
        self._pending_nav_url = ""
        self._document_status = 0
        self._title = ""
        self._url = ""
        self._load_ok = True
        self._find_js_callback: Optional[Callable] = None
        #: 主窗口注入：处理快捷键，返回 True 表示已处理
        self.accelerator_handler: Optional[Callable[[int, bool, bool, bool], bool]] = None

    # -- 生命周期 --------------------------------------------------------- #
    def showEvent(self, event) -> None:  # noqa: D102
        super().showEvent(event)
        if not self._started:
            self._started = True
            # 稍作延迟：先让主窗口完成首帧绘制，再初始化 WebView2
            QTimer.singleShot(30, self._start)

    def is_ready(self) -> bool:
        """就绪判定：优先用状态机，兼容旧的 _ready 标记。"""
        return bool(self._ready) or self.state is EngineState.READY

    def _start(self) -> None:
        self.set_state(EngineState.INITIALIZING)
        ok, error = load_runtime()
        if not ok:
            self.set_state(EngineState.FAILED)
            self._failed = True
            self.status_message.emit(f"WebView2 初始化失败：{error}")
            self.load_finished.emit(False)
            return

        # 复用共享环境：已就绪则直接用，否则等待预热任务（可能已在进行中）
        cached = cached_environment()
        if cached is not None:
            self._on_environment(cached)
            return

        task = environment_task(getattr(self, "config", None))
        if task is None:
            self._on_failure(environment_error() or RuntimeError("WebView2 环境创建失败"))
            return
        await_task(task, self._on_shared_environment, self._on_failure)

    def _on_shared_environment(self, environment) -> None:
        import time as _time

        started = _ENVIRONMENT.get("task_started")
        if started:
            _STATE["env_ms"] = (_time.perf_counter() - started) * 1000
        store_environment(environment)
        self._on_environment(environment)

    def _on_failure(self, error: Exception) -> None:
        self.set_state(EngineState.FAILED)
        log.error("WebView2 初始化失败：%s", error)
        self._failed = True
        self.status_message.emit(f"WebView2 初始化失败：{error}")
        self.load_finished.emit(False)

    def _on_environment(self, environment) -> None:
        from System import IntPtr

        self._environment = environment
        try:
            _STATE["browser_version"] = str(environment.BrowserVersionString)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

        task = None
        if self.incognito:
            # 无痕：InPrivate 模式，不写入 Cookie / 缓存 / 历史
            try:
                options = environment.CreateCoreWebView2ControllerOptions()
                options.IsInPrivateModeEnabled = True
                task = environment.CreateCoreWebView2ControllerAsync(
                    options, IntPtr(int(self.winId()))
                )
            except Exception:
                task = None
        if task is None:
            task = environment.CreateCoreWebView2ControllerAsync(IntPtr(int(self.winId())))
        await_task(task, self._on_controller, self._on_failure)

    def _on_controller(self, controller) -> None:
        from Microsoft.Web.WebView2.Core import (
            CoreWebView2AcceleratorKeyPressedEventArgs,
            CoreWebView2ContentLoadingEventArgs,
            CoreWebView2DOMContentLoadedEventArgs,
            CoreWebView2DownloadStartingEventArgs,
            CoreWebView2NavigationCompletedEventArgs,
            CoreWebView2NavigationStartingEventArgs,
            CoreWebView2NewWindowRequestedEventArgs,
            CoreWebView2ProcessFailedEventArgs,
            CoreWebView2SourceChangedEventArgs,
            CoreWebView2WebMessageReceivedEventArgs,
        )
        from System import Object

        self._controller = controller
        self._core = controller.CoreWebView2
        controller.IsVisible = True
        self._apply_bounds()
        self._configure_settings()

        core = self._core
        self._subscribe_event(core, "NavigationStarting",
                              CoreWebView2NavigationStartingEventArgs, self._on_nav_starting)
        self._subscribe_event(core, "NavigationCompleted",
                              CoreWebView2NavigationCompletedEventArgs, self._on_nav_completed)
        self._subscribe_event(core, "SourceChanged",
                              CoreWebView2SourceChangedEventArgs, self._on_source_changed)
        self._subscribe_event(core, "ContentLoading",
                              CoreWebView2ContentLoadingEventArgs, self._on_content_loading)
        self._subscribe_event(core, "DOMContentLoaded",
                              CoreWebView2DOMContentLoadedEventArgs, self._on_dom_loaded)
        self._subscribe_event(core, "DocumentTitleChanged", Object, self._on_title_changed)
        self._subscribe_event(core, "HistoryChanged", Object, self._on_history_changed)
        self._subscribe_event(core, "NewWindowRequested",
                              CoreWebView2NewWindowRequestedEventArgs, self._on_new_window)
        self._subscribe_event(core, "WebMessageReceived",
                              CoreWebView2WebMessageReceivedEventArgs, self._on_web_message)
        try:
            from Microsoft.Web.WebView2.Core import (
                CoreWebView2WebResourceResponseReceivedEventArgs,
            )

            self._subscribe_event(
                core, "WebResourceResponseReceived",
                CoreWebView2WebResourceResponseReceivedEventArgs,
                self._on_web_resource_response,
            )
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        self._subscribe_event(core, "DownloadStarting",
                              CoreWebView2DownloadStartingEventArgs, self._on_download)
        self._subscribe_event(core, "ProcessFailed",
                              CoreWebView2ProcessFailedEventArgs, self._on_process_failed)
        self._subscribe_event(core, "FaviconChanged", Object, self._on_favicon_changed)
        self._subscribe_event(core, "ContainsFullScreenElementChanged", Object,
                              self._on_fullscreen_changed)
        self._subscribe_event(controller, "AcceleratorKeyPressed",
                              CoreWebView2AcceleratorKeyPressedEventArgs, self._on_accelerator)
        self._subscribe_certificate_events(core)
        self._register_ruffle_handler()

        try:
            core.AddScriptToExecuteOnDocumentCreatedAsync(_INJECT_JS)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

        self._ready = True
        self.set_state(EngineState.READY)
        self.set_zoom_factor(self._zoom)
        if self._pending_url:
            url, self._pending_url = self._pending_url, None
            self.load(url)

    def _subscribe_event(self, target, event_name: str, args_type, handler) -> None:
        """订阅 .NET 事件，并保留委托引用（否则会被 Python GC 回收）。"""
        from System import EventHandler, Object

        adder = getattr(target, "add_" + event_name, None)
        if adder is None:
            return
        try:
            delegate = EventHandler[args_type or Object](handler)
        except Exception:
            try:
                delegate = EventHandler[Object](handler)
            except Exception:
                return
        self._delegates.append(delegate)
        try:
            adder(delegate)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def _configure_settings(self) -> None:
        settings = self._core.Settings
        for name, value in (
            ("IsScriptEnabled", True),
            ("IsWebMessageEnabled", True),
            ("AreDefaultScriptDialogsEnabled", True),
            ("AreDefaultContextMenusEnabled", True),
            ("AreDevToolsEnabled", True),
            ("AreBrowserAcceleratorKeysEnabled", True),
            ("IsStatusBarEnabled", False),
            ("IsZoomControlEnabled", True),
            ("IsPinchZoomEnabled", False),
            ("IsSwipeNavigationEnabled", False),
            ("IsPasswordAutosaveEnabled", False),
            ("IsGeneralAutofillEnabled", False),
            ("IsBuiltInErrorPageEnabled", True),
        ):
            try:
                setattr(settings, name, value)
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass

    def _apply_bounds(self) -> None:
        if self._controller is None:
            return
        from System.Drawing import Rectangle

        try:
            ratio = float(self.devicePixelRatioF()) or 1.0
            self._controller.RasterizationScale = ratio
            self._controller.Bounds = Rectangle(
                0, 0, max(1, int(self.width() * ratio)), max(1, int(self.height() * ratio))
            )
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def resizeEvent(self, event) -> None:  # noqa: D102
        super().resizeEvent(event)
        self._apply_bounds()

    def shutdown(self) -> None:
        self.set_state(EngineState.CLOSING)
        try:
            self.revoke_ruffle_token()
            if self._controller is not None:
                self._controller.Close()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        self._controller = None
        self._core = None
        self._ready = False
        self.set_state(EngineState.CLOSED)

    # -- 导航 ------------------------------------------------------------- #
    def load(self, url: str) -> None:
        if self._core is None:
            self._pending_url = url
            return
        self._core.Navigate(url)

    def current_url(self) -> str:
        if self._core is not None:
            try:
                return str(self._core.Source)
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
        return self._url

    def current_title(self) -> str:
        if self._core is not None:
            try:
                return str(self._core.DocumentTitle)
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
        return self._title

    def can_go_back(self) -> bool:
        try:
            return bool(self._core.CanGoBack)
        except Exception:
            return False

    def can_go_forward(self) -> bool:
        try:
            return bool(self._core.CanGoForward)
        except Exception:
            return False

    def go_back(self) -> None:
        try:
            self._core.GoBack()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def go_forward(self) -> None:
        try:
            self._core.GoForward()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def reload(self) -> None:
        try:
            self._core.Reload()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def stop(self) -> None:
        try:
            self._core.Stop()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    # -- 缩放 ------------------------------------------------------------- #
    def zoom_factor(self) -> float:
        return self._zoom

    def set_zoom_factor(self, factor: float) -> None:
        self._zoom = factor
        if self._controller is not None:
            try:
                self._controller.ZoomFactor = float(factor)
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass

    # -- 脚本 ------------------------------------------------------------- #
    def run_js(self, code: str, callback=None) -> None:
        if self._core is None:
            return
        try:
            task = self._core.ExecuteScriptAsync(code)
        except Exception:
            return
        if callback is None:
            return

        def done(result) -> None:
            try:
                callback(json.loads(result) if isinstance(result, str) else result)
            except Exception:
                callback(None)

        await_task(task, done)

    def edit_action(self, name: str) -> None:
        commands = {
            "undo": "undo",
            "redo": "redo",
            "cut": "cut",
            "copy": "copy",
            "paste": "paste",
            "selectall": "selectAll",
        }
        command = commands.get(name)
        if command:
            self.run_js(f"document.execCommand('{command}');")

    def find_text(self, text: str, forward: bool = True) -> None:
        if not text:
            self.clear_find()
            return
        script = (
            "(function(){var t=%s;var r=false;try{r=window.find(t,false,%s,true,false,true,false);}"
            "catch(e){r=false;}return r;})()"
            % (json.dumps(text, ensure_ascii=False), "false" if forward else "true")
        )
        self.run_js(script, lambda found: self.find_result.emit(1 if found else 0, 0))

    def clear_find(self) -> None:
        self.run_js("try{window.getSelection().removeAllRanges();}catch(e){}")

    def save_page(self) -> None:
        try:
            self._core.ShowSaveAsUIAsync()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def open_dev_tools(self) -> None:
        try:
            self._core.OpenDevToolsWindow()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def focus_content(self) -> None:
        try:
            self._controller.MoveFocus(0)  # CoreWebView2MoveFocusReason.Programmatic
        except Exception:
            self.setFocus()

    # -- 事件回调 --------------------------------------------------------- #
    def _on_nav_starting(self, sender, args) -> None:
        try:
            uri = str(args.Uri)
        except Exception:
            uri = ""

        # 0) 内置页面（错误页 / 警告页）自身的加载：保留原网址，不再拦截
        if self._internal_page and uri.lower().startswith("file:"):
            self._internal_page = False
            return
        self._internal_page = False

        # 0.5) 新的文档开始加载：轮换 Ruffle 会话 token（旧 token 立即失效）
        if not uri.lower().startswith(("lite:", "about:", "data:")):
            try:
                self.rotate_ruffle_token()
            except Exception as exc:  # noqa: BLE001
                log.debug("轮换 Ruffle token 失败：%s", exc)

        # 1) 内部命令（错误页 / 警告页上的按钮）
        if uri and self.handle_internal_url(uri):
            try:
                args.Cancel = True
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
            return

        # 2) 可疑网址提示（本地启发式规则）
        checker = self.security_manager
        if checker is not None and uri and not uri.lower().startswith(
            ("about:", "data:", "file:", "lite:", "view-source:")
        ) and uri not in self._allow_once:
            try:
                verdict = checker.check_url(uri)
            except Exception:
                verdict = None
            if verdict is not None and verdict.blocked:
                try:
                    args.Cancel = True
                except Exception as lite_exc:
                    log.debug("忽略异常：%s", lite_exc)
                    pass
                self._blocked_url = uri
                # 在 NavigationStarting 回调里直接导航会被内核忽略，延后一拍
                def _show(u=uri, v=verdict) -> None:
                    try:
                        self.set_warning_page(u, v)
                    except Exception as exc:  # noqa: BLE001
                        import traceback

                        print(f"[wv2] 显示警告页异常：{exc!r}", flush=True)
                        traceback.print_exc()

                QTimer.singleShot(0, _show)
                return
            if verdict is not None and verdict.suspicious and verdict.reasons:
                self.status_message.emit("⚠ " + verdict.reasons[0])

        self._load_ok = True
        self._error_url = ""
        self._blocked_url = ""
        self._pending_nav_url = uri
        self._document_status = 0
        self.load_started.emit()
        self.load_progress.emit(10)
        self.status_message.emit("正在打开网页...")

    def _on_content_loading(self, sender, args) -> None:
        self.load_progress.emit(50)
        # 新文档开始加载：这是注入屏蔽规则的最早时机
        self._inject_page_helpers()

    def _on_dom_loaded(self, sender, args) -> None:
        self.load_progress.emit(80)
        self._inject_page_helpers()

    # -- 广告屏蔽 / Ruffle ------------------------------------------------ #
    def _inject_page_helpers(self) -> None:
        """把广告屏蔽规则与 Ruffle 注入当前文档（幂等，可重复调用）。"""
        core = self._core
        if core is None:
            return
        scripts: list[str] = []
        try:
            url = self.current_url()
        except Exception:
            url = ""
        rules = self._rules_for(url)
        self._ad_rules = rules
        if rules:
            from .adblock import apply_script

            scripts.append(apply_script(rules))
        if getattr(self, "_ruffle_enabled", False):
            from .ruffle import bootstrap_script

            scripts.append(bootstrap_script(
                getattr(self, "_ruffle_public_path", ""),
                getattr(self, "_ruffle_config", ""),
                self.ruffle_token(),
            ))
        for script in scripts:
            try:
                core.ExecuteScriptAsync(script)
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                continue

    def _register_ruffle_handler(self) -> None:
        """拦截虚拟域名，把 lib/ruffle 里的文件供给网页。"""
        core = self._core
        if core is None:
            return
        try:
            from Microsoft.Web.WebView2.Core import (
                CoreWebView2WebResourceContext,
                CoreWebView2WebResourceRequestedEventArgs,
            )

            from . import ruffle

            core.AddWebResourceRequestedFilter(
                f"{ruffle.PUBLIC_PATH}*", CoreWebView2WebResourceContext.All
            )
            self._subscribe_event(
                core, "WebResourceRequested",
                CoreWebView2WebResourceRequestedEventArgs,
                self._on_web_resource_requested,
            )
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def _on_web_resource_requested(self, sender, args) -> None:
        from . import ruffle

        try:
            uri = str(args.Request.Uri)
        except Exception:
            return
        if ruffle.HOST not in uri:
            return
        name = uri.split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        if name == "proxy":
            self._serve_swf_proxy(uri, args)
            return
        served = ruffle.serve(name)
        if served is None:
            return
        data, mime = served
        response = self._make_resource_response(data, mime)
        if response is not None:
            args.Response = response

    def _serve_swf_proxy(self, uri: str, args) -> None:
        """代取外部 .swf：解决自托管 Ruffle 抓不到跨域 Flash 文件的问题。

        授权以**会话 token** 为主（不可预测、随文档轮换、标签页关闭即失效），
        Referer 只作为辅助信号——它可被伪造或省略，不构成授权依据。
        """
        from . import ruffle

        target, token = ruffle.parse_proxy_request(uri)
        if not target:
            log.debug("Ruffle 代理：请求缺少目标地址")
            return
        if not ruffle.SESSIONS.valid(token):
            log.warning("Ruffle 代理拒绝：token 无效或已过期（%s）", target[:120])
            return
        try:
            referer = str(args.Request.Headers.GetHeader("Referer") or "")
        except Exception as exc:  # noqa: BLE001
            log.debug("读取 Referer 失败：%s", exc)
            referer = ""
        if referer and not referer.lower().startswith("file:"):
            log.debug("Ruffle 代理：Referer 非本地播放页（%s）", referer[:80])
        cached = _SWF_CACHE.get(target)
        if cached is None:
            fetched = ruffle.fetch_swf(target, referer)
            if fetched is None:
                return
            cached = fetched
            if sum(len(item[0]) for item in _SWF_CACHE.values()) < _SWF_CACHE_LIMIT:
                _SWF_CACHE[target] = cached
        data, mime = cached
        response = self._make_resource_response(data, mime)
        if response is not None:
            args.Response = response

    def set_ruffle(self, enabled: bool, public_path: str = "", config_json: str = "") -> None:
        """启用 Ruffle：既要注入当前页面，也要让之后每个新文档都自动注入。"""
        super().set_ruffle(enabled, public_path, config_json)
        core = self._core
        if core is None:
            return
        script_id = getattr(self, "_ruffle_script_id", None)
        if script_id is not None:
            try:
                core.RemoveScriptToExecuteOnDocumentCreated(script_id)
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
            self._ruffle_script_id = None
        if not enabled:
            return
        from .ruffle import bootstrap_script

        script = bootstrap_script(public_path, config_json)
        try:
            task = core.AddScriptToExecuteOnDocumentCreatedAsync(script)
        except Exception:
            return

        def done(result) -> None:
            try:
                self._ruffle_script_id = str(result)
            except Exception:
                self._ruffle_script_id = None

        await_task(task, done)

    def _make_resource_response(self, data: bytes, mime: str):
        """把 Python 字节变成 WebView2 能用的响应对象。"""
        try:
            from System import Array, Byte
            from System.IO import MemoryStream
        except Exception:
            return None
        try:
            buffer = Array[Byte](data)
            stream = MemoryStream(buffer, False)
        except Exception:
            try:
                buffer = Array[Byte](list(data))
                stream = MemoryStream()
                stream.Write(buffer, 0, len(data))
                stream.Position = 0
            except Exception:
                return None
        headers = (
            f"Content-Type: {mime}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Cross-Origin-Resource-Policy: cross-origin\r\n"
            "Cache-Control: public, max-age=86400\r\n"
        )
        environment = getattr(self, "_environment", None)
        if environment is None:
            try:
                environment = self._core.Environment
            except Exception:
                environment = None
        if environment is None:
            return None
        try:
            return environment.CreateWebResourceResponse(stream, 200, "OK", headers)
        except Exception:
            return None

    def _on_nav_completed(self, sender, args) -> None:
        ok = bool(args.IsSuccess)
        self._load_ok = ok
        self.load_progress.emit(100)
        if self._error_url or self._blocked_url:
            # 正在显示内置页面：忽略（可能来自刚被取消的那次导航）
            self.load_finished.emit(ok)
            return
        if not ok:
            code, message = self._web_error(args)
            self.load_finished.emit(False)
            self.set_error_page(self._url or self.current_url(), code, message)
            return
        self.load_finished.emit(True)
        self._check_http_status()

    def _web_error(self, args) -> tuple[int, str]:
        """把 WebErrorStatus 转成 (错误码, 说明)。"""
        from .errors import WEBVIEW2_ERRORS

        try:
            status = int(args.WebErrorStatus)
        except Exception:
            status = 0
        if not status:
            # WebView2 对 HTTP 4xx/5xx 与部分连接失败都会报 IsSuccess=False +
            # WebErrorStatus=Unknown，此时优先用 WebResourceResponseReceived 抓到的状态码
            document_status = int(getattr(self, "_document_status", 0) or 0)
            if document_status >= 400:
                return document_status, ""
            return -16, "无法建立连接或页面无法打开"
        return -status, WEBVIEW2_ERRORS.get(status, "无法打开该页面")

    def _on_web_resource_response(self, sender, args) -> None:
        """记录主文档的 HTTP 状态码（用于识别 404/500 等）。"""
        try:
            uri = str(args.Request.Uri)
        except Exception:
            return
        pending = getattr(self, "_pending_nav_url", "")
        if not pending or uri != pending:
            return
        try:
            self._document_status = int(args.Response.StatusCode)
        except Exception:
            self._document_status = 0

    def _check_http_status(self) -> None:
        """读取主文档的 HTTP 状态码，4xx/5xx 时显示自定义错误页。"""
        if self._core is None or self._error_url:
            return
        js = (
            "(function(){try{var e=performance.getEntriesByType('navigation')[0];"
            "return e&&e.responseStatus?e.responseStatus:0;}catch(err){return 0;}})()"
        )

        def done(result) -> None:
            try:
                status = int(str(result).strip('"') or 0)
            except Exception:
                status = 0
            if status >= 400 and not self._error_url:
                url = self._url or self.current_url()
                self.set_error_page(url, status, "")

        try:
            task = self._core.ExecuteScriptAsync(js)

            def unwrap(_res) -> None:
                try:
                    payload = json.loads(str(task.Result))
                except Exception:
                    payload = 0
                done(payload)

            await_task(task, unwrap)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def _on_source_changed(self, sender, args) -> None:
        if self._error_url:
            # 正在显示自定义错误页，保持地址栏不变
            return
        url = self.current_url()
        self._url = url
        self.url_changed.emit(url)

    def _on_title_changed(self, sender, args) -> None:
        title = self.current_title()
        self._title = title
        self.title_changed.emit(title)

    def _on_history_changed(self, sender, args) -> None:
        pass

    def _on_new_window(self, sender, args) -> None:
        try:
            url = str(args.Uri)
        except Exception:
            url = ""
        try:
            user_initiated = bool(args.IsUserInitiated)
        except Exception:
            user_initiated = True
        args.Handled = True
        # 非用户点击触发的弹窗一律拦掉（广告弹窗基本都是这类）
        if getattr(self, "_block_popups", True) and not user_initiated:
            self.popup_blocked.emit(url)
            return
        if url:
            self.new_window_requested.emit(url)

    def _on_web_message(self, sender, args) -> None:
        try:
            raw = str(args.TryGetWebMessageAsString())
        except Exception:
            return
        try:
            data = json.loads(raw)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        kind = data.get("__lite")
        if kind == "hover":
            self.status_message.emit(str(data.get("url") or ""))
            return
        if kind == "adpick":
            from urllib.parse import quote

            selector = str(data.get("selector") or "")
            host = str(data.get("host") or "")
            if selector:
                self.command_requested.emit(
                    "lite:adpick?selector=" + quote(selector, safe="")
                    + "&host=" + quote(host, safe="")
                )

    def _on_download(self, sender, args) -> None:
        from pathlib import Path as _Path

        manager = self.download_manager
        operation = args.DownloadOperation
        url = ""
        try:
            if operation is not None:
                url = str(operation.Uri)
        except Exception:
            url = ""

        suggested = _Path(str(args.ResultFilePath)).name or "download"
        if manager is None:
            args.Handled = True
            return

        item = manager.begin(suggested, url)
        if item is None:
            args.Cancel = True
            return

        args.ResultFilePath = str(item.path)
        args.Handled = True

        if operation is None:
            manager.finish(item, False, "无法获取下载进度")
            return

        item.cancel_callback = operation.Cancel

        # WebView2 下载对象的事件在 pythonnet 下不可靠，改用定时轮询进度
        self._download_watch.append((item, operation, 0))
        if not self._download_timer.isActive():
            self._download_timer.start()

    def _poll_downloads(self) -> None:
        """轮询下载进度（替代不可靠的 .NET 事件）。"""
        manager = self.download_manager
        remaining: list = []
        for item, operation, failures in self._download_watch:
            try:
                received = int(operation.BytesReceived)
                total = int(operation.TotalBytesToReceive)
                state_text = str(operation.State)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                if failures <= 3:
                    print(f"[wv2] 读取下载状态失败：{exc!r}", flush=True)
                if failures < 40:
                    remaining.append((item, operation, failures))
                continue

            state = 2 if "Completed" in state_text else 3 if "Interrupted" in state_text else 1
            if manager is not None:
                if state == 1:
                    manager.update_progress(item, received, total)
                elif state == 2:
                    manager.update_progress(item, received or total, total or received)
                    manager.finish(item, True)
                    continue
                else:
                    reason = ""
                    try:
                        reason = str(operation.InterruptReason)
                    except Exception:
                        reason = ""
                    manager.finish(item, False, f"下载中断（{reason}）" if reason else "下载中断")
                    continue
            remaining.append((item, operation, failures))
        self._download_watch = remaining
        if not remaining:
            self._download_timer.stop()

    def _on_process_failed(self, sender, args) -> None:
        try:
            kind = int(args.ProcessFailedKind)
        except Exception:
            kind = -1
        self.status_message.emit(f"渲染进程异常（{kind}）")
        self.load_finished.emit(False)

    def _on_favicon_changed(self, sender, args) -> None:
        try:
            from Microsoft.Web.WebView2.Core import CoreWebView2FaviconImageFormat
            from System.IO import MemoryStream
        except Exception:
            return

        def done(stream) -> None:
            try:
                memory = MemoryStream()
                stream.CopyTo(memory)
                data = bytes(memory.ToArray())
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    self.icon_changed.emit(QIcon(pixmap))
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass

        try:
            await_task(self._core.GetFaviconAsync(CoreWebView2FaviconImageFormat.Png), done)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
    def _on_fullscreen_changed(self, sender, args) -> None:
        try:
            self.fullscreen_requested.emit(bool(self._core.ContainsFullScreenElement))
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def _on_accelerator(self, sender, args) -> None:
        try:
            vk = int(args.VirtualKey)
            event_kind = int(args.KeyEventKind)
        except Exception:
            return
        if event_kind != 0:          # 只处理 KeyDown
            return
        if self.accelerator_handler is None:
            return

        ctrl, shift, alt = _modifiers()
        # 只转发带 Ctrl/Alt 的组合键和功能键，其余留给页面
        if not (ctrl or alt or vk in (0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x7A, 0x1B)):
            return
        qt_key = _VK_TO_QT.get(vk)
        if qt_key is None:
            return
        try:
            if self.accelerator_handler(qt_key, ctrl, shift, alt):
                args.Handled = True
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    # ------------------------------------------------------------------ #
    # 用户代理 / Cookie / 缓存 / 错误页 / 保存 / 打印 / 性能
    # ------------------------------------------------------------------ #
    def set_user_agent(self, user_agent: str) -> None:
        core = self._core
        if core is None:
            return
        try:
            if not self._default_ua:
                self._default_ua = str(core.Settings.UserAgent)
            core.Settings.UserAgent = user_agent or self._default_ua
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def _cdp(self, method: str, params: Optional[dict] = None):
        """调用 DevTools 协议方法（失败返回 None）。"""
        if self._core is None:
            return None
        try:
            return self._core.CallDevToolsProtocolMethodAsync(
                method, json.dumps(params or {})
            )
        except Exception:
            return None

    def list_cookies(self, callback) -> None:
        if self._core is None:
            callback([])
            return
        self._cdp("Network.enable")

        def parse(result) -> None:
            try:
                payload = json.loads(str(result)) if result else {}
            except Exception:
                payload = {}
            items = []
            for item in payload.get("cookies") or []:
                items.append(
                    {
                        "name": str(item.get("name") or ""),
                        "domain": str(item.get("domain") or ""),
                        "path": str(item.get("path") or "/"),
                        "secure": bool(item.get("secure")),
                        "http_only": bool(item.get("httpOnly")),
                        "expires": item.get("expires", -1),
                        "session": bool(item.get("session")),
                        "raw": item,
                    }
                )
            callback(items)

        task = self._cdp("Network.getAllCookies")
        if task is None:
            callback([])
            return
        await_task(task, parse, lambda _error: callback([]))

    def delete_cookie(self, cookie: dict) -> None:
        raw = cookie.get("raw") or cookie
        self._cdp(
            "Network.deleteCookies",
            {
                "name": raw.get("name", ""),
                "domain": raw.get("domain", ""),
                "path": raw.get("path", "/"),
            },
        )

    def delete_all_cookies(self) -> None:
        self._cdp("Network.clearBrowserCookies")

    def delete_session_cookies(self) -> None:
        def remove(items) -> None:
            for item in items:
                if item.get("session"):
                    self.delete_cookie(item)

        self.list_cookies(remove)

    def clear_cache(self) -> None:
        self._cdp("Network.clearBrowserCache")

    def clear_site_data(self) -> None:
        try:
            from Microsoft.Web.WebView2.Core import CoreWebView2BrowsingDataKinds

            kinds = None
            for name in ("AllProfile", "AllSite", "LocalStorage", "IndexedDB"):
                kinds = getattr(CoreWebView2BrowsingDataKinds, name, None)
                if kinds is not None:
                    break
            if kinds is not None:
                task = self._core.Profile.ClearBrowsingDataAsync(kinds)
                await_task(task, lambda _result: None)
                return
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        # 退路：用 DevTools 协议清理当前来源
        try:
            origin = self.current_url().split("/", 3)
            if len(origin) >= 3:
                base = origin[0] + "//" + origin[2]
                self._cdp("Storage.clearDataForOrigin",
                          {"origin": base, "storageTypes": "all"})
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def save_page_as(self, path: str, fmt: str = "mhtml") -> bool:
        if self._core is None:
            return False
        if fmt == "mhtml":
            def write(result) -> None:
                try:
                    payload = json.loads(str(result))
                    data = payload.get("data") or ""
                    with open(path, "w", encoding="utf-8") as handle:
                        handle.write(data)
                except Exception as lite_exc:
                    log.debug("忽略异常：%s", lite_exc)
                    pass

            task = self._cdp("Page.captureSnapshot", {"format": "mhtml"})
            if task is None:
                return False
            await_task(task, write)
            return True
        # HTML 两种格式交给内核自带的「另存为」对话框（可选手动选择格式）
        try:
            task = self._core.ShowSaveAsUIAsync()
            await_task(task, lambda _result: None)
            return True
        except Exception:
            return False

    def print_page(self) -> None:
        if self._core is None:
            return
        try:
            task = self._core.ShowPrintUIAsync()
            await_task(task, lambda _result: None)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def export_pdf(self, path: str) -> bool:
        if self._core is None:
            return False
        try:
            settings = self._core.Environment.CreatePrintSettings()
            try:
                settings.ShouldPrintBackgrounds = True
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
            task = self._core.PrintToPdfAsync(path, settings)
            await_task(task, lambda _result: None)
            return True
        except Exception:
            return False

    def set_content_visible(self, visible: bool) -> None:
        try:
            if self._controller is not None:
                self._controller.IsVisible = bool(visible)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        if not visible:
            return
        self.resume()

    def suspend(self) -> None:
        core = self._core
        if core is None:
            return
        try:
            if core.IsSuspended:
                return
            task = core.TrySuspendAsync()
            await_task(task, lambda _ok: setattr(self, "_suspended", True))
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def resume(self) -> None:
        core = self._core
        if core is None:
            return
        try:
            if core.IsSuspended:
                core.Resume()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        self._suspended = False

    def is_suspended(self) -> bool:
        try:
            return bool(self._core is not None and self._core.IsSuspended)
        except Exception:
            return bool(getattr(self, "_suspended", False))

    def is_playing_audio(self) -> bool:
        """正在播放音频 / 视频时不要挂起，否则会打断播放。"""
        core = self._core
        if core is None:
            return False
        try:
            if bool(core.IsDocumentPlayingAudio):
                return True
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        # 有些站点会把视频静音自动播放，这里再检查一次页面里的 <video>
        try:
            task = core.ExecuteScriptAsync(
                "(function(){var l=document.querySelectorAll('video,audio');"
                "for(var i=0;i<l.length;i++){var m=l[i];"
                "if(!m.paused && !m.ended && m.readyState>2) return 1;} return 0;})()"
            )
            self._video_probe = task
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        return False

    # ------------------------------------------------------------------ #
    # 加载偏好
    # ------------------------------------------------------------------ #
    _IMAGE_BLOCK_PATTERNS = [
        "*.png*", "*.jpg*", "*.jpeg*", "*.gif*", "*.webp*", "*.bmp*", "*.svg*", "*.ico*",
    ]

    def set_preferences(self, *, load_images: bool = True, preload: bool = False,
                        smooth_scroll: bool = False) -> None:
        super().set_preferences(
            load_images=load_images, preload=preload, smooth_scroll=smooth_scroll
        )
        if self._core is None:
            return
        try:
            if load_images:
                # 不调用 setBlockedURLs：空数组虽然表示「不拦截」，但没必要
                # 每次都启用网络域，避免对视频等流式加载产生任何影响
                return
            self._cdp("Network.enable")
            self._cdp("Network.setBlockedURLs", {"urls": self._IMAGE_BLOCK_PATTERNS})
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    # ------------------------------------------------------------------ #
    # HTTPS 证书校验
    # ------------------------------------------------------------------ #
    def _subscribe_certificate_events(self, core) -> None:
        from Microsoft.Web.WebView2.Core import (
            CoreWebView2ServerCertificateErrorDetectedEventArgs,
        )
        from System import Object

        try:
            self._subscribe_event(
                core, "ServerCertificateErrorDetected",
                CoreWebView2ServerCertificateErrorDetectedEventArgs, self._on_certificate_error,
            )
        except Exception:
            try:
                self._subscribe_event(core, "ServerCertificateErrorDetected", Object,
                                      self._on_certificate_error)
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass

    def _on_certificate_error(self, sender, args) -> None:
        """证书校验失败：交给主窗口询问用户，期间保持挂起。"""
        from .netsec import CertificateInfo, SecurityManager

        info = CertificateInfo(is_error=True)
        try:
            info.host = str(args.RequestUri).split("/")[2]
        except Exception:
            info.host = ""
        try:
            info.error = str(args.ErrorStatus)
        except Exception:
            info.error = "证书校验失败"
        try:
            cert = args.ServerCertificate
            if cert is not None:
                info.subject = str(cert.Subject)
                info.issuer = str(cert.Issuer)
                info.valid_from = SecurityManager.describe_time(cert.ValidFrom)
                info.valid_to = SecurityManager.describe_time(cert.ValidTo)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

        checker = self.security_manager
        if checker is not None:
            info = checker.check_certificate(info)
        else:
            from .netsec import DANGER

            info.severity = DANGER

        # 严格模式：直接拒绝，不询问
        if bool(self._strict_certificate()):
            self._set_certificate_action(args, False)
            self.status_message.emit(f"已拒绝不安全的连接：{info.host}")
            return

        try:
            deferral = args.GetDeferral()
        except Exception:
            deferral = None

        def decide(allow: bool) -> None:
            self._set_certificate_action(args, allow)
            if deferral is not None:
                try:
                    deferral.Complete()
                except Exception as lite_exc:
                    log.debug("忽略异常：%s", lite_exc)
                    pass

        self._certificate_decider = decide
        self.certificate_error.emit(info)

    def _strict_certificate(self) -> bool:
        try:
            config = getattr(self, "config", None)
            return bool(config.get("strict_certificate")) if config is not None else False
        except Exception:
            return False

    @staticmethod
    def _set_certificate_action(args, allow: bool) -> None:
        try:
            from Microsoft.Web.WebView2.Core import (
                CoreWebView2ServerCertificateErrorAction,
            )

            if allow:
                action = getattr(CoreWebView2ServerCertificateErrorAction, "AlwaysAllow", None)
                if action is None:
                    action = CoreWebView2ServerCertificateErrorAction.Allow
            else:
                action = CoreWebView2ServerCertificateErrorAction.Cancel
            args.Action = action
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def resolve_certificate(self, allow: bool) -> None:
        """主窗口询问结束后调用。"""
        decider = getattr(self, "_certificate_decider", None)
        if decider is not None:
            self._certificate_decider = None
            decider(bool(allow))
