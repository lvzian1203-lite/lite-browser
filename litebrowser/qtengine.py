"""QtWebEngine（Qt 自带 Chromium）引擎后端。"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QTimer, QUrl
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .config import cache_dir, profile_dir
from .engine import (
    ENGINE_QTWEB,
    BrowserEngine,
    EngineCapabilities,
    EngineState,
)

log = logging.getLogger(__name__)

_profiles: dict[bool, Optional[QWebEngineProfile]] = {}
_download_handler: Optional[Callable[[object], None]] = None


def qt_default_user_agent() -> str:
    """Qt 内核默认的 User-Agent。"""
    try:
        return QWebEngineProfile().httpUserAgent()
    except Exception:
        return ""


def _cookie_to_dict(cookie) -> dict:
    """把 QNetworkCookie 转成统一字典。"""
    try:
        name = bytes(cookie.name()).decode("utf-8", "replace")
    except Exception:
        name = ""
    try:
        domain = cookie.domain() or ""
    except Exception:
        domain = ""
    try:
        path = cookie.path() or "/"
    except Exception:
        path = "/"
    try:
        expires = cookie.expirationDate().toSecsSinceEpoch() if not cookie.isSessionCookie() else -1
    except Exception:
        expires = -1
    return {
        "name": name,
        "domain": domain,
        "path": path,
        "secure": bool(cookie.isSecure()),
        "http_only": bool(cookie.isHttpOnly()),
        "expires": int(expires),
        "session": bool(cookie.isSessionCookie()),
        "raw": cookie,
    }


def _set_attribute(settings: QWebEngineSettings, name: str, value) -> None:
    attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
    if attribute is not None:
        try:
            settings.setAttribute(attribute, value)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass


def _apply_settings(settings: QWebEngineSettings) -> None:
    for name, value in (
        ("JavascriptEnabled", True),
        ("JavascriptCanOpenWindows", True),
        ("LocalStorageEnabled", True),
        ("AutoLoadImages", True),
        ("FullScreenSupportEnabled", True),
        ("PdfViewerEnabled", True),
        ("WebGLEnabled", True),
        ("Accelerated2dCanvasEnabled", True),
        ("ScrollAnimatorEnabled", True),
        ("ShowScrollBars", True),
        ("ErrorPageEnabled", True),
        ("PluginsEnabled", False),
        ("ScreenCaptureEnabled", True),
        ("ClipboardReadWriteEnabled", True),
        ("HyperlinkAuditingEnabled", False),
        ("FocusOnNavigationEnabled", True),
    ):
        _set_attribute(settings, name, value)


def _strip_qt_token(user_agent: str) -> str:
    user_agent = re.sub(r"\s*QtWebEngine/[\d.]+", "", user_agent)
    user_agent = re.sub(r"\s*Qt/[\d.]+", "", user_agent)
    return user_agent


def profile(incognito: bool = False) -> QWebEngineProfile:
    """取得 profile；``incognito=True`` 时返回内存 profile（不落盘）。"""
    key = bool(incognito)
    cached = _profiles.get(key)
    if cached is not None:
        return cached

    if key:
        # 无痕：off-the-record，不写 Cookie / 缓存 / 历史
        profile_ = QWebEngineProfile()
        profile_.setHttpUserAgent(_strip_qt_token(QWebEngineProfile().httpUserAgent()))
        try:
            profile_.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
            profile_.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        profile_.setPersistentStoragePath("")
        profile_.setCachePath("")
    else:
        profile_dir().mkdir(parents=True, exist_ok=True)
        cache_dir().mkdir(parents=True, exist_ok=True)
        profile_ = QWebEngineProfile("litebrowser")
        profile_.setPersistentStoragePath(str(profile_dir()))
        profile_.setCachePath(str(cache_dir()))
        try:
            profile_.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
            profile_.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        profile_.setHttpUserAgent(_strip_qt_token(profile_.httpUserAgent()))

    _apply_settings(profile_.settings())
    profile_.downloadRequested.connect(_on_download)
    _profiles[key] = profile_
    return profile_


def set_download_handler(handler: Optional[Callable[[object], None]]) -> None:
    """由主窗口注入：接管下载（统一下载目录与进度）。"""
    global _download_handler
    _download_handler = handler


def _on_download(request) -> None:
    # 「网页另存为」由 QtWebEngine 内部发起，目标路径已由 save() 指定，
    # 不能走下载管理器（否则会被下载目录设置拦下来）
    try:
        if request.isSavePageDownload():
            request.accept()
            return
    except Exception as lite_exc:
        log.debug("忽略异常：%s", lite_exc)
        pass
    if _download_handler is not None:
        _download_handler(request)
    else:
        request.cancel()


def handle_download(request, manager) -> None:
    """把 QtWebEngine 的下载请求接入统一下载管理器。"""
    if manager is None:
        request.cancel()
        return
    item = manager.begin(request.downloadFileName(), request.url().toString())
    if item is None:
        request.cancel()
        return

    request.setDownloadDirectory(str(item.path.parent))
    request.setDownloadFileName(item.path.name)
    item.cancel_callback = request.cancel

    request.receivedBytesChanged.connect(
        lambda: manager.update_progress(item, request.receivedBytes(), request.totalBytes())
    )

    def done() -> None:
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

        ok = request.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted
        manager.finish(item, ok, "" if ok else "下载未完成")

    # Qt6 中 isFinished 是普通方法，完成信号叫 isFinishedChanged
    finished_signal = getattr(request, "isFinishedChanged", None) or getattr(
        request, "isFinished", None
    )
    try:
        finished_signal.connect(done)
    except AttributeError as lite_exc:
        log.debug("忽略异常：%s", lite_exc)
        pass
    request.accept()


class _LitePage(QWebEnginePage):
    """新窗口改为新标签页，处理全屏与证书错误。"""

    def __init__(self, profile_: QWebEngineProfile, view: QWebEngineView, engine: "QtWebEngine") -> None:
        super().__init__(profile_, view)
        self._engine = engine
        self.fullScreenRequested.connect(self._on_fullscreen)
        self.certificateError.connect(self._on_certificate_error)

    def createWindow(self, _type):  # noqa: N802
        # 非用户点击触发的弹窗（广告）直接丢弃
        if getattr(self._engine, "_block_popups", True):
            try:
                if not self._engine.popup_is_user_initiated():
                    self._engine.popup_blocked.emit("")
                    return None
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
        provider = self._engine.new_tab_provider
        if provider is None:
            return None
        engine = provider()
        return engine.page if isinstance(engine, QtWebEngine) else None

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802
        try:
            if self._engine.intercept_navigation(url.toString(), bool(is_main_frame)):
                return False
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def _on_fullscreen(self, request) -> None:
        request.accept()
        self._engine.fullscreen_requested.emit(bool(request.toggleOn()))

    def _on_certificate_error(self, error) -> bool:
        """证书校验失败：交给主窗口询问用户（期间挂起决策）。"""
        from .netsec import CertificateInfo, DANGER, SecurityManager

        try:
            info = CertificateInfo(
                host=error.url().host(),
                error=error.description(),
                is_error=True,
            )
        except Exception:
            info = CertificateInfo(error="证书校验失败", is_error=True)

        checker = self._engine.security_manager
        if checker is not None:
            info = checker.check_certificate(info)
        else:
            info.severity = DANGER

        if self._engine.strict_certificate():
            try:
                error.rejectCertificate()
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
            self._engine.status_message.emit(f"已拒绝不安全的连接：{info.host}")
            return True

        try:
            error.defer()
        except Exception:
            try:
                error.rejectCertificate()
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
            return True

        def decide(allow: bool) -> None:
            try:
                if allow:
                    error.acceptCertificate()
                else:
                    error.rejectCertificate()
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass

        self._engine._certificate_decider = decide
        self._engine.certificate_error.emit(info)
        return True

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802, D102
        return None


class QtWebEngine(BrowserEngine):
    """用 QWebEngineView 实现的引擎。"""

    engine_id = ENGINE_QTWEB
    #: QtWebEngine 不含专有编解码器，也无法提供本地 Ruffle（P2-2）
    capabilities = EngineCapabilities(ruffle=False, proprietary_codecs=False)

    #: 用户手势有效窗口（秒）：createWindow 距离最近一次真实点击/按键多久内算用户触发
    USER_GESTURE_WINDOW = 1.5

    def __init__(self, parent: QWidget | None = None, *, incognito: bool = False) -> None:
        super().__init__(parent)
        self.incognito = bool(incognito)
        self._suspended = False
        #: 最近一次真实用户输入（鼠标按下 / 按键）的时间戳
        self._last_user_input = 0.0
        self.setObjectName("qtEngine")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = QWebEngineView(self)
        self.page = _LitePage(profile(self.incognito), self.view, self)
        self.view.setPage(self.page)
        layout.addWidget(self.view)

        # 记录真实用户输入：QtWebEngine 没有 IsUserInitiated 之类的接口，
        # 只能用"最近是否有点击/按键"来近似判断弹窗来源。
        self.view.installEventFilter(self)

        self.view.loadStarted.connect(self._on_started)
        self.view.loadProgress.connect(self.load_progress.emit)
        self.view.loadFinished.connect(self._on_finished)
        self.view.titleChanged.connect(self.title_changed.emit)
        self.view.urlChanged.connect(self._on_url)
        self.view.iconChanged.connect(self._on_icon)
        self.page.linkHovered.connect(self._on_hover)
        self.page.findTextFinished.connect(self._on_find)

    # -- 用户手势 --------------------------------------------------------- #
    def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名
        try:
            kind = event.type()
            if kind in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.KeyPress,
                QEvent.Type.Wheel,
                QEvent.Type.TouchBegin,
            ):
                self.note_user_input()
        except Exception as exc:  # noqa: BLE001 - 记录时间戳失败不能影响事件派发
            log.debug("记录用户手势失败：%s", exc)
        return super().eventFilter(obj, event)

    def note_user_input(self) -> None:
        """记录一次真实用户输入（供弹窗判定使用）。"""
        self._last_user_input = time.monotonic()

    def has_recent_user_gesture(self) -> bool:
        """最近 USER_GESTURE_WINDOW 秒内是否有真实点击/按键。"""
        last = getattr(self, "_last_user_input", 0.0)
        if not last:
            return False
        return (time.monotonic() - last) <= self.USER_GESTURE_WINDOW

    # -- 导航 ------------------------------------------------------------- #
    def load(self, url: str) -> None:
        self.view.setUrl(QUrl(url))
        self.view.setFocus()

    def current_url(self) -> str:
        return self.view.url().toString()

    def current_title(self) -> str:
        return self.view.title()

    def can_go_back(self) -> bool:
        return self.view.history().canGoBack()

    def can_go_forward(self) -> bool:
        return self.view.history().canGoForward()

    def go_back(self) -> None:
        self.view.back()

    def go_forward(self) -> None:
        self.view.forward()

    def reload(self) -> None:
        self.view.reload()

    def stop(self) -> None:
        self.view.stop()

    # -- 缩放 ------------------------------------------------------------- #
    def zoom_factor(self) -> float:
        return self.view.zoomFactor()

    def set_zoom_factor(self, factor: float) -> None:
        self.view.setZoomFactor(factor)

    # -- 脚本 / 查找 ------------------------------------------------------ #
    def run_js(self, code: str, callback=None) -> None:
        self.page.runJavaScript(code, callback or (lambda _result: None))

    def find_text(self, text: str, forward: bool = True) -> None:
        if not text:
            self.page.findText("")
            return
        flags = QWebEnginePage.FindFlag(0)
        if not forward:
            flags |= QWebEnginePage.FindFlag.FindBackward
        self.page.findText(text, flags)

    def clear_find(self) -> None:
        self.page.findText("")

    def edit_action(self, name: str) -> None:
        mapping = {
            "undo": "Undo",
            "redo": "Redo",
            "cut": "Cut",
            "copy": "Copy",
            "paste": "Paste",
            "selectall": "SelectAll",
            "save": "SavePage",
        }
        action = getattr(QWebEnginePage.WebAction, mapping.get(name, ""), None)
        if action is not None:
            self.page.triggerAction(action)

    def save_page(self) -> None:
        self.edit_action("save")

    # ------------------------------------------------------------------ #
    # 用户代理 / Cookie / 缓存 / 错误页 / 保存 / 打印 / 性能
    # ------------------------------------------------------------------ #
    def set_user_agent(self, user_agent: str) -> None:
        try:
            profile(self.incognito).setHttpUserAgent(user_agent or qt_default_user_agent())
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def list_cookies(self, callback) -> None:
        store = profile(self.incognito).cookieStore()
        collected: list[dict] = []
        seen: set[tuple] = set()

        def add(cookie) -> None:
            item = _cookie_to_dict(cookie)
            key = (item["domain"], item["name"], item["path"])
            if key in seen:
                return
            seen.add(key)
            collected.append(item)

        def on_added(cookie) -> None:
            add(cookie)

        try:
            store.cookieAdded.connect(on_added)
            store.loadAllCookies()
        except Exception:
            callback([])
            return

        def finish() -> None:
            try:
                store.cookieAdded.disconnect(on_added)
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
            # loadAllCookies() 只返回持久化 Cookie，当前页面的会话 Cookie
            # 通过脚本再补一次，保证管理器里能看到它们
            def merge(result) -> None:
                text = str(result or "")
                domain = ""
                try:
                    from urllib.parse import urlsplit

                    host = urlsplit(self.current_url()).hostname or ""
                    domain = host
                except Exception:
                    host = ""
                for pair in text.split(";"):
                    if "=" not in pair:
                        continue
                    name, _, value = pair.strip().partition("=")
                    if not name:
                        continue
                    key = (domain, name, "/")
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(
                        {
                            "name": name,
                            "domain": domain,
                            "path": "/",
                            "secure": False,
                            "http_only": False,
                            "expires": -1,
                            "session": True,
                            "raw": None,
                        }
                    )
                callback(collected)

            try:
                self.page.runJavaScript("document.cookie", merge)
            except Exception:
                callback(collected)

        QTimer.singleShot(900, finish)

    def delete_cookie(self, cookie: dict) -> None:
        raw = cookie.get("raw")
        if raw is None:
            return
        try:
            profile(self.incognito).cookieStore().deleteCookie(raw)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def delete_all_cookies(self) -> None:
        try:
            profile(self.incognito).cookieStore().deleteAllCookies()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def delete_session_cookies(self) -> None:
        try:
            profile(self.incognito).cookieStore().deleteSessionCookies()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def clear_cache(self) -> None:
        try:
            profile(self.incognito).clearHttpCache()
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def clear_site_data(self) -> None:
        # QtWebEngine 未开放站点数据接口，尽量清空当前页面可访问的存储
        self.run_js(
            "try{localStorage.clear();sessionStorage.clear();}catch(e){}"
            "try{indexedDB.databases&&indexedDB.databases().then(function(l){"
            "l.forEach(function(d){indexedDB.deleteDatabase(d.name);});});}catch(e){}"
        )

    def save_page_as(self, path: str, fmt: str = "mhtml") -> bool:
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest

        mapping = {
            "mhtml": QWebEngineDownloadRequest.SavePageFormat.MimeHtmlSaveFormat,
            "html": QWebEngineDownloadRequest.SavePageFormat.CompleteHtmlSaveFormat,
            "html-only": QWebEngineDownloadRequest.SavePageFormat.SingleHtmlSaveFormat,
        }
        try:
            self.page.save(path, mapping.get(fmt, mapping["mhtml"]))
            return True
        except Exception:
            return False

    def export_pdf(self, path: str) -> bool:
        try:
            self.page.printToPdf(path)
            return True
        except Exception:
            return False

    def set_content_visible(self, visible: bool) -> None:
        try:
            self.view.setVisible(bool(visible))
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        if visible:
            self.resume()

    def suspend(self) -> None:
        try:
            self.page.setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
            self._suspended = True
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def resume(self) -> None:
        try:
            self.page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        self._suspended = False

    def is_suspended(self) -> bool:
        return bool(getattr(self, "_suspended", False))

    def is_playing_audio(self) -> bool:
        try:
            return bool(self.page.recentlyAudible())
        except Exception:
            return False

    def set_preferences(self, *, load_images: bool = True, preload: bool = False,
                        smooth_scroll: bool = False) -> None:
        super().set_preferences(
            load_images=load_images, preload=preload, smooth_scroll=smooth_scroll
        )
        try:
            settings = profile(self.incognito).settings()
            _set_attribute(settings, "AutoLoadImages", bool(load_images))
            _set_attribute(settings, "ScrollAnimatorEnabled", bool(smooth_scroll))
            _set_attribute(settings, "DnsPrefetchEnabled", bool(preload))
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    # ------------------------------------------------------------------ #
    # HTTPS 证书校验
    # ------------------------------------------------------------------ #
    def strict_certificate(self) -> bool:
        config = getattr(self, "config", None)
        try:
            return bool(config.get("strict_certificate")) if config is not None else False
        except Exception:
            return False

    def resolve_certificate(self, allow: bool) -> None:
        decider = getattr(self, "_certificate_decider", None)
        if decider is not None:
            self._certificate_decider = None
            decider(bool(allow))

    def open_dev_tools(self) -> None:
        self.page.triggerAction(QWebEnginePage.WebAction.InspectElement)

    def focus_content(self) -> None:
        self.view.setFocus()

    def shutdown(self) -> None:
        self.set_state(EngineState.CLOSING)
        try:
            self.revoke_ruffle_token()
            self.view.stop()
            self.view.setPage(None)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
        self.set_state(EngineState.CLOSED)

    # -- 事件 ------------------------------------------------------------- #
    def _on_started(self) -> None:
        self._error_url = ""
        self._blocked_url = ""
        self.load_progress.emit(0)
        self.load_started.emit()

    def popup_is_user_initiated(self) -> bool:
        """判断弹出窗口是否可能由用户操作触发。

        QtWebEngine 没有 ``IsUserInitiated`` 之类的接口，
        ``hasFocus()`` / ``isActiveWindow()`` 并不能代表"用户刚刚点了东西"，
        因此这里改用**用户手势时间窗**：只有最近
        :attr:`USER_GESTURE_WINDOW` 秒内发生过真实点击 / 按键 / 滚轮 / 触摸，
        才认为是用户触发。这样既能放行用户点击的 ``target="_blank"`` 链接，
        又能挡掉页面加载后自行弹出的脚本窗口。
        """
        if self.has_recent_user_gesture():
            return True
        # 手势窗口外：再给"窗口处于活动状态且刚切换过焦点"一个很弱的兜底，
        # 避免键盘激活链接（Enter）在个别平台上没有产生 KeyPress 事件时被误杀
        if getattr(self, "_last_user_input", 0.0) == 0.0:
            return bool(self.view.isActiveWindow() and self.view.hasFocus())
        return False

    def _inject_page_helpers(self) -> None:
        """把广告屏蔽规则注入当前页面（QtWebEngine 不支持 Ruffle 的本地资源供给）。"""
        rules = self._rules_for(self.current_url())
        self._ad_rules = rules
        if rules:
            from .adblock import apply_script

            self.run_js(apply_script(rules))

    def _on_finished(self, ok: bool) -> None:
        self.load_progress.emit(100)
        if not ok:
            self.set_state(EngineState.FAILED)
            self.load_finished.emit(False)
            self.set_error_page(
                self.current_url(), -16,
                "无法打开该页面（网络不可用、域名无法解析或服务器返回错误）",
            )
            return
        self.set_state(EngineState.READY)
        self.load_finished.emit(True)
        self._inject_page_helpers()
        self._check_http_status()

    def _check_http_status(self) -> None:
        """通过 PerformanceNavigationTiming 读取 HTTP 状态码。"""
        if self._error_url:
            return

        def done(result) -> None:
            try:
                status = int(result or 0)
            except Exception:
                status = 0
            if status >= 400 and not self._error_url:
                self.set_error_page(self.current_url(), status, "")

        self.run_js(
            "(function(){try{var e=performance.getEntriesByType('navigation')[0];"
            "return e&&e.responseStatus?e.responseStatus:0;}catch(err){return 0;}})()",
            done,
        )

    def intercept_navigation(self, url: str, is_main_frame: bool = True) -> bool:
        """返回 True 表示拦截这次导航。"""
        if not url:
            return False
        # 内置页面（错误页 / 警告页）自身的加载
        if self._internal_page and url.lower().startswith("file:"):
            self._internal_page = False
            return False
        self._internal_page = False
        if self.handle_internal_url(url):
            return True
        if not is_main_frame:
            return False
        if url.lower().startswith(("about:", "data:", "file:", "lite:", "view-source:", "blob:")):
            return False
        if url in self._allow_once:
            return False
        checker = self.security_manager
        if checker is None:
            return False
        try:
            verdict = checker.check_url(url)
        except Exception:
            return False
        if verdict.blocked:
            self._blocked_url = url
            self.set_warning_page(url, verdict)
            return True
        if verdict.suspicious and verdict.reasons:
            self.status_message.emit("⚠ " + verdict.reasons[0])
        return False

    def _on_url(self, url: QUrl) -> None:
        if self._error_url:
            return
        self.url_changed.emit(url.toString())

    def _on_icon(self, icon) -> None:
        self.icon_changed.emit(icon)

    def _on_hover(self, url: str) -> None:
        self.status_message.emit(url)

    def _on_find(self, result) -> None:
        self.find_result.emit(result.numberOfMatches(), result.activeMatch())
