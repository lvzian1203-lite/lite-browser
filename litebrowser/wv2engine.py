"""Microsoft Edge WebView2 引擎后端（Windows）。

WebView2 使用系统自带的 Edge 运行时，是完整的 Chromium，
包含 H.264 / AAC 等专有编解码器，可以正常播放哔哩哔哩等站点的 HTML5 视频。
"""

from __future__ import annotations

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
from .engine import ENGINE_WEBVIEW2, BrowserEngine, await_task

#: WebView2 运行时在注册表中的标识
_RUNTIME_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

_STATE: dict = {"checked": False, "ok": False, "reason": "", "loaded": False}

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
        except OSError:
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
        except OSError:
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
        except Exception:
            pass
    _strip_motw(folder)

    try:
        from pythonnet import load

        last_error: Optional[Exception] = None
        for runtime in ("coreclr", "netfx"):
            try:
                load(runtime)
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error is not None:
            raise RuntimeError(f"没有可用的 .NET 运行时：{last_error}")

        import clr

        clr.AddReference(str(folder / "Microsoft.Web.WebView2.Core.dll"))
        clr.AddReference("System.Drawing.Primitives")

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
        from System.Drawing import Rectangle  # noqa: F401
        from System.IO import MemoryStream  # noqa: F401
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
        #: 用户脚本注入脚本的 ID（更新时用于移除旧脚本）
        self._userscript_script_id: Optional[str] = None
        self._extensions_loaded = False
        self._zoom = 1.0
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
            QTimer.singleShot(0, self._start)

    def is_ready(self) -> bool:
        return self._ready

    def _start(self) -> None:
        ok, error = load_runtime()
        if not ok:
            self._failed = True
            self.status_message.emit(f"WebView2 初始化失败：{error}")
            self.load_finished.emit(False)
            return

        from Microsoft.Web.WebView2.Core import (
            CoreWebView2Environment,
            CoreWebView2EnvironmentOptions,
        )

        options = CoreWebView2EnvironmentOptions()
        try:
            options.Language = "zh-CN"
        except Exception:
            pass
        # 允许加载 Chrome 扩展（Manifest V2 / V3 已解压扩展）
        try:
            options.AreBrowserExtensionsEnabled = True
        except Exception:
            pass

        user_data = data_dir() / "webview2"
        user_data.mkdir(parents=True, exist_ok=True)
        task = CoreWebView2Environment.CreateAsync(None, str(user_data), options)
        await_task(task, self._on_environment, self._on_failure)

    def _on_failure(self, error: Exception) -> None:
        self._failed = True
        self.status_message.emit(f"WebView2 初始化失败：{error}")
        self.load_finished.emit(False)

    def _on_environment(self, environment) -> None:
        from System import IntPtr

        try:
            _STATE["browser_version"] = str(environment.BrowserVersionString)
        except Exception:
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
        self._subscribe_event(core, "DownloadStarting",
                              CoreWebView2DownloadStartingEventArgs, self._on_download)
        self._subscribe_event(core, "ProcessFailed",
                              CoreWebView2ProcessFailedEventArgs, self._on_process_failed)
        self._subscribe_event(core, "FaviconChanged", Object, self._on_favicon_changed)
        self._subscribe_event(core, "ContainsFullScreenElementChanged", Object,
                              self._on_fullscreen_changed)
        self._subscribe_event(controller, "AcceleratorKeyPressed",
                              CoreWebView2AcceleratorKeyPressedEventArgs, self._on_accelerator)

        try:
            core.AddScriptToExecuteOnDocumentCreatedAsync(_INJECT_JS)
        except Exception:
            pass

        self._ready = True
        self._apply_plugins()
        self.set_zoom_factor(self._zoom)
        if self._pending_url:
            url, self._pending_url = self._pending_url, None
            self.load(url)

    # ------------------------------------------------------------------ #
    # 插件：Chrome 扩展 + 油猴脚本
    # ------------------------------------------------------------------ #
    def supports_extensions(self) -> bool:
        return True

    def refresh_plugins(self) -> None:
        self._apply_plugins(force_reload_extensions=True)

    def post_to_page(self, js: str) -> None:
        # 通过基类信号排队到 UI 线程，避免跨线程调用 COM 失败
        super().post_to_page(js)

    def _on_post_js(self, js: str) -> None:
        if self._core is None:
            return
        try:
            self._core.ExecuteScriptAsync(js)
        except Exception as exc:  # noqa: BLE001
            print(f"[wv2] 执行页面脚本失败：{exc!r}", flush=True)

    def _apply_plugins(self, force_reload_extensions: bool = False) -> None:
        self._apply_userscripts()
        if force_reload_extensions or not getattr(self, "_extensions_loaded", False):
            self._extensions_loaded = True
            self._apply_extensions()

    def _apply_userscripts(self) -> None:
        """把油猴脚本引导脚本注册到文档创建时。"""
        store = getattr(self, "userscript_store", None)
        core = self._core
        if core is None:
            return

        if self._userscript_script_id:
            try:
                core.RemoveScriptToExecuteOnDocumentCreated(self._userscript_script_id)
            except Exception:
                pass
            self._userscript_script_id = None

        if store is None or store.count() == 0:
            return
        try:
            js = store.build_bootstrap()
        except Exception:
            return
        if not js:
            return

        def done(script_id) -> None:
            self._userscript_script_id = str(script_id)
            print(f"[wv2] 用户脚本已注入（{len(store.enabled())} 个，id={script_id}）", flush=True)
            self.status_message.emit(f"已注入 {len(store.enabled())} 个用户脚本")

        def failed(error) -> None:
            print(f"[wv2] 用户脚本注入失败：{error}", flush=True)

        try:
            task = core.AddScriptToExecuteOnDocumentCreatedAsync(js)
        except Exception as exc:  # noqa: BLE001
            print(f"[wv2] AddScriptToExecuteOnDocumentCreatedAsync 调用失败：{exc!r}", flush=True)
            return
        await_task(task, done, failed)

    def _apply_extensions(self) -> None:
        """加载启用的 Chrome 扩展。"""
        store = getattr(self, "extension_store", None)
        core = self._core
        if store is None or core is None:
            return
        for extension in store.enabled():
            try:
                task = core.Profile.AddBrowserExtensionAsync(str(extension.path))
            except Exception as exc:  # noqa: BLE001
                print(f"[wv2] 扩展 {extension.display_name} 加载失败：{exc!r}", flush=True)
                continue

            def done(result, name=extension.display_name) -> None:
                print(f"[wv2] 已加载扩展：{name}", flush=True)
                self.status_message.emit(f"已加载扩展：{name}")

            def failed(error, name=extension.display_name) -> None:
                print(f"[wv2] 扩展加载失败：{name}（{error}）", flush=True)
                self.status_message.emit(f"扩展加载失败：{name}（{error}）")

            await_task(task, done, failed)

    def _on_extension_message(self, payload: dict) -> bool:
        """处理用户脚本发出的 GM 请求。"""
        store = getattr(self, "userscript_store", None)
        if store is None:
            return False
        from .userscripts import handle_gm_message

        return handle_gm_message(
            payload,
            store,
            self.post_to_page,
            open_tab=lambda url: self.new_window_requested.emit(url),
        )

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
        except Exception:
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
            except Exception:
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
        except Exception:
            pass

    def resizeEvent(self, event) -> None:  # noqa: D102
        super().resizeEvent(event)
        self._apply_bounds()

    def shutdown(self) -> None:
        try:
            if self._controller is not None:
                self._controller.Close()
        except Exception:
            pass
        self._controller = None
        self._core = None
        self._ready = False

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
            except Exception:
                pass
        return self._url

    def current_title(self) -> str:
        if self._core is not None:
            try:
                return str(self._core.DocumentTitle)
            except Exception:
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
        except Exception:
            pass

    def go_forward(self) -> None:
        try:
            self._core.GoForward()
        except Exception:
            pass

    def reload(self) -> None:
        try:
            self._core.Reload()
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self._core.Stop()
        except Exception:
            pass

    # -- 缩放 ------------------------------------------------------------- #
    def zoom_factor(self) -> float:
        return self._zoom

    def set_zoom_factor(self, factor: float) -> None:
        self._zoom = factor
        if self._controller is not None:
            try:
                self._controller.ZoomFactor = float(factor)
            except Exception:
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
        except Exception:
            pass

    def open_dev_tools(self) -> None:
        try:
            self._core.OpenDevToolsWindow()
        except Exception:
            pass

    def focus_content(self) -> None:
        try:
            self._controller.MoveFocus(0)  # CoreWebView2MoveFocusReason.Programmatic
        except Exception:
            self.setFocus()

    # -- 事件回调 --------------------------------------------------------- #
    def _on_nav_starting(self, sender, args) -> None:
        self._load_ok = True
        self.load_started.emit()
        self.load_progress.emit(10)
        self.status_message.emit("正在打开网页...")

    def _on_content_loading(self, sender, args) -> None:
        self.load_progress.emit(50)

    def _on_dom_loaded(self, sender, args) -> None:
        self.load_progress.emit(80)

    def _on_nav_completed(self, sender, args) -> None:
        ok = bool(args.IsSuccess)
        self._load_ok = ok
        self.load_progress.emit(100)
        self.load_finished.emit(ok)

    def _on_source_changed(self, sender, args) -> None:
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
        args.Handled = True
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
        if data.get("__lite") == "hover":
            self.status_message.emit(str(data.get("url") or ""))
            return
        if data.get("__lite_gm"):
            try:
                self._on_extension_message(data)
            except Exception:
                pass

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
            except Exception:
                pass

        try:
            await_task(self._core.GetFaviconAsync(CoreWebView2FaviconImageFormat.Png), done)
        except Exception:
            pass
    def _on_fullscreen_changed(self, sender, args) -> None:
        try:
            self.fullscreen_requested.emit(bool(self._core.ContainsFullScreenElement))
        except Exception:
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
        except Exception:
            pass
