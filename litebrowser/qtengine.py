"""QtWebEngine（Qt 自带 Chromium）引擎后端。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .config import cache_dir, profile_dir
from .engine import ENGINE_QTWEB, BrowserEngine

_profiles: dict[bool, Optional[QWebEngineProfile]] = {}
_download_handler: Optional[Callable[[object], None]] = None


def _set_attribute(settings: QWebEngineSettings, name: str, value) -> None:
    attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
    if attribute is not None:
        try:
            settings.setAttribute(attribute, value)
        except Exception:
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
        except Exception:
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
        except Exception:
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

    request.isFinished.connect(done)
    request.accept()


class _LitePage(QWebEnginePage):
    """新窗口改为新标签页，处理全屏与证书错误。"""

    def __init__(self, profile_: QWebEngineProfile, view: QWebEngineView, engine: "QtWebEngine") -> None:
        super().__init__(profile_, view)
        self._engine = engine
        self.fullScreenRequested.connect(self._on_fullscreen)
        self.certificateError.connect(self._on_certificate_error)

    def createWindow(self, _type):  # noqa: N802
        provider = self._engine.new_tab_provider
        if provider is None:
            return None
        engine = provider()
        return engine.page if isinstance(engine, QtWebEngine) else None

    def _on_fullscreen(self, request) -> None:
        request.accept()
        self._engine.fullscreen_requested.emit(bool(request.toggleOn()))

    def _on_certificate_error(self, error) -> bool:
        from PySide6.QtWidgets import QMessageBox

        from .config import APP_NAME

        answer = QMessageBox.warning(
            self._engine.window(),
            APP_NAME,
            f"该网站的安全证书有问题：\n{error.url().host()}\n\n"
            f"{error.description()}\n\n是否继续访问？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            error.acceptCertificate()
        else:
            error.rejectCertificate()
        return True

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802, D102
        return None


class QtWebEngine(BrowserEngine):
    """用 QWebEngineView 实现的引擎。"""

    engine_id = ENGINE_QTWEB

    def __init__(self, parent: QWidget | None = None, *, incognito: bool = False) -> None:
        super().__init__(parent)
        self.incognito = bool(incognito)
        self.setObjectName("qtEngine")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = QWebEngineView(self)
        self.page = _LitePage(profile(self.incognito), self.view, self)
        self.view.setPage(self.page)
        layout.addWidget(self.view)

        self.view.loadStarted.connect(self._on_started)
        self.view.loadProgress.connect(self.load_progress.emit)
        self.view.loadFinished.connect(self._on_finished)
        self.view.titleChanged.connect(self.title_changed.emit)
        self.view.urlChanged.connect(self._on_url)
        self.view.iconChanged.connect(self._on_icon)
        self.page.linkHovered.connect(self._on_hover)
        self.page.findTextFinished.connect(self._on_find)

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

    def open_dev_tools(self) -> None:
        self.page.triggerAction(QWebEnginePage.WebAction.InspectElement)

    def focus_content(self) -> None:
        self.view.setFocus()

    def shutdown(self) -> None:
        try:
            self.view.stop()
            self.view.setPage(None)
        except Exception:
            pass

    # -- 事件 ------------------------------------------------------------- #
    def _on_started(self) -> None:
        self.load_progress.emit(0)
        self.load_started.emit()

    def _on_finished(self, ok: bool) -> None:
        self.load_progress.emit(100)
        self.load_finished.emit(bool(ok))

    def _on_url(self, url: QUrl) -> None:
        self.url_changed.emit(url.toString())

    def _on_icon(self, icon) -> None:
        self.icon_changed.emit(icon)

    def _on_hover(self, url: str) -> None:
        self.status_message.emit(url)

    def _on_find(self, result) -> None:
        self.find_result.emit(result.numberOfMatches(), result.activeMatch())
