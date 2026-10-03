"""浏览器主窗口：标签页、地址栏、书签栏、全屏、菜单。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, QStandardPaths, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .bookmarks import BookmarkStore
from .config import APP_NAME, Config, data_dir
from .crypto import DataVault
from .dialogs import (
    AboutDialog,
    BookmarkEditDialog,
    BookmarkManagerDialog,
    SettingsDialog,
)
from .downloads import DownloadManager
from .engine import BrowserEngine, create_engine, resolve_engine
from .history import HistoryStore
from .managers import DownloadManagerDialog, HistoryDialog
from .plugindialogs import ExtensionManagerDialog
from .widgets import XPWindow


class MainWindow(XPWindow):
    """lite browser test 主窗口。"""

    def __init__(
        self,
        config: Config,
        bookmarks: BookmarkStore,
        initial_url: Optional[str] = None,
        engine_id: Optional[str] = None,
        vault: Optional[DataVault] = None,
        history: Optional[HistoryStore] = None,
        downloads: Optional[DownloadManager] = None,
        extensions=None,
        userscripts=None,
    ) -> None:
        super().__init__(title=APP_NAME, icon=icons.app_icon())
        self.config = config
        self.bookmarks = bookmarks
        self.initial_url = (initial_url or "").strip() or None
        self.engine_id = engine_id or resolve_engine(str(config.get("engine") or "auto"))
        self.vault = vault
        self.history = history
        self.downloads = downloads
        self.extensions = extensions
        self.userscripts = userscripts
        self.incognito = bool(config.get("incognito")) if vault is not None else False

        self._fullscreen = False
        self._was_maximized = False
        self._switching = False
        self._shortcut_actions: list[QAction] = []

        self.setWindowTitle(APP_NAME)
        if bool(self.config.get("native_frame")):
            self.set_native_frame(True)
        self._build_ui()
        self._build_menus()
        self._build_shortcuts()
        self._collect_shortcuts()
        self._install_download_handler()
        self._purge_history()
        self.apply_config()

        self.bookmarks.changed.connect(self.rebuild_bookmark_bar)
        self.rebuild_bookmark_bar()

        self._restore_geometry()
        self._open_startup_page()

    # ------------------------------------------------------------------ #
    # 界面
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.menu_bar = QMenuBar(self.body)
        layout.addWidget(self.menu_bar)

        self.toolbar = QToolBar("标准按钮", self.body)
        self.toolbar.setObjectName("mainToolBar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setIconSize(QSize(22, 22))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        layout.addWidget(self.toolbar)

        self.act_back = QAction(icons.icon("back", 22), "后退", self)
        self.act_forward = QAction(icons.icon("forward", 22), "前进", self)
        self.act_stop = QAction(icons.icon("stop", 22), "停止", self)
        self.act_refresh = QAction(icons.icon("refresh", 22), "刷新", self)
        self.act_home = QAction(icons.icon("home", 22), "主页", self)
        for action in (
            self.act_back,
            self.act_forward,
            self.act_stop,
            self.act_refresh,
            self.act_home,
        ):
            self.toolbar.addAction(action)
        self.toolbar.addSeparator()

        self.address = QLineEdit(self.body)
        self.address.setMinimumWidth(220)
        self.address.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.address.setToolTip("输入网址，或输入关键字后按回车搜索")
        self.toolbar.addWidget(self.address)
        self.toolbar.addSeparator()

        self.act_go = QAction(icons.icon("go", 22), "转到", self)
        self.act_star = QAction(icons.icon("star_add", 22), "收藏", self)
        self.act_bookmarks = QAction(icons.icon("bookmarks", 22), "收藏夹", self)
        self.act_download = QAction(icons.icon("download", 22), "下载", self)
        self.act_history = QAction(icons.icon("history", 22), "历史", self)
        self.act_incognito = QAction(icons.icon("incognito", 22), "无痕", self)
        self.act_incognito.setCheckable(True)
        self.act_plugins = QAction(icons.icon("plugin", 22), "插件", self)
        self.act_plugins.setToolTip("管理 Chrome 扩展与油猴脚本 (Ctrl+Shift+E)")
        self.act_settings = QAction(icons.icon("settings", 22), "设置", self)
        for action in (
            self.act_go,
            self.act_star,
            self.act_bookmarks,
            self.act_download,
            self.act_history,
            self.act_incognito,
            self.act_plugins,
            self.act_settings,
        ):
            self.toolbar.addAction(action)

        self.bookmark_bar = QToolBar("书签栏", self.body)
        self.bookmark_bar.setObjectName("bookmarkBar")
        self.bookmark_bar.setMovable(False)
        self.bookmark_bar.setFloatable(False)
        self.bookmark_bar.setIconSize(QSize(16, 16))
        self.bookmark_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        layout.addWidget(self.bookmark_bar)

        self.find_bar = self._build_find_bar()
        layout.addWidget(self.find_bar)
        self.find_bar.setVisible(False)

        self.tabs = QTabWidget(self.body)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.btn_new_tab = QToolButton(self.tabs)
        self.btn_new_tab.setIcon(icons.icon("tab_new", 16))
        self.btn_new_tab.setToolTip("新建标签页 (Ctrl+T)")
        self.btn_new_tab.setAutoRaise(True)
        self.btn_new_tab.clicked.connect(lambda: self.new_tab())
        self.tabs.setCornerWidget(self.btn_new_tab, Qt.TopRightCorner)
        layout.addWidget(self.tabs, 1)

        self.status = QStatusBar(self.body)
        self.status.setSizeGripEnabled(False)
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setMinimumWidth(120)
        self.status.addWidget(self.lbl_status, 1)

        self.progress = QProgressBar(self.status)
        self.progress.setFixedSize(150, 14)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.status.addPermanentWidget(self.progress)

        self.lbl_incognito = QLabel("无痕浏览")
        self.lbl_incognito.setStyleSheet(
            "color: #FFFFFF; background: #C6362B; padding: 1px 6px; border-radius: 2px;"
        )
        self.lbl_incognito.setToolTip("当前处于无痕浏览模式：不记录历史、Cookie 与缓存")
        self.lbl_incognito.setVisible(False)
        self.status.addPermanentWidget(self.lbl_incognito)

        self.lbl_engine = QLabel("")
        self.lbl_engine.setToolTip("当前渲染引擎")
        self.status.addPermanentWidget(self.lbl_engine)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setFixedWidth(46)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.status.addPermanentWidget(self.lbl_zoom)
        layout.addWidget(self.status)

        self.act_back.triggered.connect(lambda: self._engine_call("go_back"))
        self.act_forward.triggered.connect(lambda: self._engine_call("go_forward"))
        self.act_stop.triggered.connect(lambda: self._engine_call("stop"))
        self.act_refresh.triggered.connect(lambda: self._engine_call("reload"))
        self.act_home.triggered.connect(self.go_home)
        self.act_go.triggered.connect(self.navigate_from_address)
        self.act_star.triggered.connect(self.add_current_bookmark)
        self.act_bookmarks.triggered.connect(self.manage_bookmarks)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_download.triggered.connect(self.open_downloads)
        self.act_history.triggered.connect(self.open_history)
        self.act_incognito.toggled.connect(self._on_incognito_toggled)
        self.act_plugins.triggered.connect(self.open_plugins)
        self.address.returnPressed.connect(self.navigate_from_address)

    def _build_find_bar(self) -> QWidget:
        bar = QWidget(self.body)
        bar.setObjectName("findBar")
        bar.setStyleSheet(
            "QWidget#findBar { background: #ECE9D8; border-bottom: 1px solid #ACA899; }"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(6)
        row.addWidget(QLabel("查找："))
        self.find_edit = QLineEdit(bar)
        self.find_edit.setFixedWidth(220)
        row.addWidget(self.find_edit)
        self.find_prev = QToolButton(bar)
        self.find_prev.setText("上一个")
        self.find_next = QToolButton(bar)
        self.find_next.setText("下一个")
        self.find_result = QLabel("", bar)
        self.find_result.setMinimumWidth(90)
        self.find_close = QToolButton(bar)
        self.find_close.setIcon(icons.icon("close", 16))
        self.find_close.setToolTip("关闭查找栏")
        row.addWidget(self.find_prev)
        row.addWidget(self.find_next)
        row.addWidget(self.find_result)
        row.addStretch(1)
        row.addWidget(self.find_close)

        self.find_edit.textChanged.connect(lambda text: self._find(text, True))
        self.find_edit.returnPressed.connect(lambda: self._find(self.find_edit.text(), True))
        self.find_next.clicked.connect(lambda: self._find(self.find_edit.text(), True))
        self.find_prev.clicked.connect(lambda: self._find(self.find_edit.text(), False))
        self.find_close.clicked.connect(self.hide_find_bar)
        return bar

    # ------------------------------------------------------------------ #
    # 菜单
    # ------------------------------------------------------------------ #
    def _build_menus(self) -> None:
        bar = self.menu_bar

        file_menu = bar.addMenu("文件(F)")
        self.act_new_tab = QAction(icons.icon("tab_new", 16), "新建标签页(T)", self)
        self.act_new_tab.setShortcut(QKeySequence("Ctrl+T"))
        self.act_new_tab.triggered.connect(lambda: self.new_tab())
        self.act_close_tab = QAction(icons.icon("close", 16), "关闭标签页(C)", self)
        self.act_close_tab.setShortcut(QKeySequence("Ctrl+W"))
        self.act_close_tab.triggered.connect(lambda: self.close_tab(self.tabs.currentIndex()))
        self.act_save_as = QAction(icons.icon("bookmarks", 16), "页面另存为(A)...", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+S"))
        self.act_save_as.triggered.connect(lambda: self._engine_call("save_page"))
        self.act_quit = QAction(icons.icon("exit", 16), "退出(X)", self)
        self.act_quit.setShortcut(QKeySequence("Alt+F4"))
        self.act_quit.triggered.connect(self.close)
        for action in (self.act_new_tab, self.act_close_tab, self.act_save_as, None, self.act_quit):
            file_menu.addAction(action) if action else file_menu.addSeparator()

        edit_menu = bar.addMenu("编辑(E)")
        self.act_undo = QAction("撤销(U)", self)
        self.act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.act_undo.triggered.connect(lambda: self._edit_action("undo"))
        self.act_redo = QAction("重做(R)", self)
        self.act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        self.act_redo.triggered.connect(lambda: self._edit_action("redo"))
        self.act_cut = QAction("剪切(T)", self)
        self.act_cut.setShortcut(QKeySequence("Ctrl+X"))
        self.act_cut.triggered.connect(lambda: self._edit_action("cut"))
        self.act_copy = QAction("复制(C)", self)
        self.act_copy.setShortcut(QKeySequence("Ctrl+C"))
        self.act_copy.triggered.connect(lambda: self._edit_action("copy"))
        self.act_paste = QAction("粘贴(P)", self)
        self.act_paste.setShortcut(QKeySequence("Ctrl+V"))
        self.act_paste.triggered.connect(lambda: self._edit_action("paste"))
        self.act_select_all = QAction("全选(A)", self)
        self.act_select_all.setShortcut(QKeySequence("Ctrl+A"))
        self.act_select_all.triggered.connect(lambda: self._edit_action("selectall"))
        self.act_find = QAction(icons.icon("find", 16), "在此页上查找(F)", self)
        self.act_find.setShortcut(QKeySequence("Ctrl+F"))
        self.act_find.triggered.connect(self.show_find_bar)
        for action in (
            self.act_undo,
            self.act_redo,
            None,
            self.act_cut,
            self.act_copy,
            self.act_paste,
            self.act_select_all,
            None,
            self.act_find,
        ):
            edit_menu.addAction(action) if action else edit_menu.addSeparator()

        view_menu = bar.addMenu("查看(V)")
        self.act_bookmark_bar = QAction("书签栏(B)", self, checkable=True)
        self.act_bookmark_bar.setShortcut(QKeySequence("Ctrl+Shift+B"))
        self.act_bookmark_bar.toggled.connect(self._toggle_bookmark_bar)
        self.act_status_bar = QAction("状态栏(S)", self, checkable=True)
        self.act_status_bar.toggled.connect(self._toggle_status_bar)
        self.act_fullscreen = QAction(icons.icon("fullscreen", 16), "全屏显示(F)", self)
        self.act_fullscreen.setShortcut(QKeySequence("F11"))
        self.act_fullscreen.triggered.connect(lambda: self.set_fullscreen(not self._fullscreen))
        self.act_zoom_in = QAction(icons.icon("zoom_in", 16), "放大(I)", self)
        self.act_zoom_in.setShortcut(QKeySequence("Ctrl+="))
        self.act_zoom_in.triggered.connect(lambda: self.change_zoom(+10))
        self.act_zoom_out = QAction(icons.icon("zoom_out", 16), "缩小(O)", self)
        self.act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.act_zoom_out.triggered.connect(lambda: self.change_zoom(-10))
        self.act_zoom_reset = QAction("实际大小(R)", self)
        self.act_zoom_reset.setShortcut(QKeySequence("Ctrl+0"))
        self.act_zoom_reset.triggered.connect(lambda: self.set_zoom(1.0))
        self.act_source = QAction("查看源代码(C)", self)
        self.act_source.setShortcut(QKeySequence("Ctrl+U"))
        self.act_source.triggered.connect(self.view_source)
        self.act_devtools = QAction("开发者工具(D)", self)
        self.act_devtools.setShortcut(QKeySequence("F12"))
        self.act_devtools.triggered.connect(lambda: self._engine_call("open_dev_tools"))
        for action in (
            self.act_bookmark_bar,
            self.act_status_bar,
            None,
            self.act_fullscreen,
            None,
            self.act_zoom_in,
            self.act_zoom_out,
            self.act_zoom_reset,
            None,
            self.act_source,
            self.act_devtools,
        ):
            view_menu.addAction(action) if action else view_menu.addSeparator()

        self.favorite_menu = bar.addMenu("收藏(A)")
        self.act_add_favorite = QAction(icons.icon("star_add", 16), "添加到收藏夹(A)...", self)
        self.act_add_favorite.setShortcut(QKeySequence("Ctrl+D"))
        self.act_add_favorite.triggered.connect(self.add_current_bookmark)
        self.act_manage_favorites = QAction(icons.icon("bookmarks", 16), "整理收藏夹(O)...", self)
        self.act_manage_favorites.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.act_manage_favorites.triggered.connect(self.manage_bookmarks)
        self.favorite_menu.addAction(self.act_add_favorite)
        self.favorite_menu.addAction(self.act_manage_favorites)
        self.favorite_menu.addSeparator()
        self._favorite_items_menu = self.favorite_menu.addMenu(icons.icon("star", 16), "收藏夹列表")

        tools_menu = bar.addMenu("工具(T)")
        self.act_open_downloads = QAction(icons.icon("download", 16), "下载管理(J)...", self)
        self.act_open_downloads.setShortcut(QKeySequence("Ctrl+J"))
        self.act_open_downloads.triggered.connect(self.open_downloads)
        self.act_open_history = QAction(icons.icon("history", 16), "历史记录(H)...", self)
        self.act_open_history.setShortcut(QKeySequence("Ctrl+H"))
        self.act_open_history.triggered.connect(self.open_history)
        self.act_toggle_incognito = QAction(icons.icon("incognito", 16), "无痕浏览模式(N)", self)
        self.act_toggle_incognito.setCheckable(True)
        self.act_toggle_incognito.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.act_toggle_incognito.toggled.connect(self._on_incognito_toggled)
        self.act_export_plain = QAction("导出明文数据(E)...", self)
        self.act_export_plain.triggered.connect(self.export_plain_dialog)
        self.act_open_plugins = QAction(icons.icon("plugin", 16), "插件管理(P)...", self)
        self.act_open_plugins.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.act_open_plugins.triggered.connect(self.open_plugins)
        self._script_menu = tools_menu.addMenu(icons.icon("plugin", 16), "用户脚本命令")
        self._script_menu.setEnabled(False)
        tools_menu.addAction(self.act_open_plugins)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_open_downloads)
        tools_menu.addAction(self.act_open_history)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_toggle_incognito)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_export_plain)
        tools_menu.addAction(self._script_menu.menuAction())

        settings_menu = bar.addMenu("设置(S)")
        self.act_open_settings = QAction(icons.icon("settings", 16), "设置(O)...", self)
        self.act_open_settings.triggered.connect(self.open_settings)
        self.act_about = QAction(icons.icon("info", 16), f"关于 {APP_NAME}(A)", self)
        self.act_about.triggered.connect(self.show_about)
        settings_menu.addAction(self.act_open_settings)
        settings_menu.addSeparator()
        settings_menu.addAction(self.act_about)

        help_menu = bar.addMenu("帮助(H)")
        self.act_help = QAction(icons.icon("info", 16), f"关于 {APP_NAME}(A)", self)
        self.act_help.triggered.connect(self.show_about)
        help_menu.addAction(self.act_help)

        self._menus = (
            file_menu,
            edit_menu,
            view_menu,
            self.favorite_menu,
            tools_menu,
            settings_menu,
            help_menu,
        )

    def _collect_shortcuts(self) -> None:
        for menu in self._menus:
            for action in menu.actions():
                if not action.shortcut().isEmpty():
                    self._shortcut_actions.append(action)

    def _build_shortcuts(self) -> None:
        self.sc_escape = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.sc_escape.setContext(Qt.WindowShortcut)
        self.sc_escape.setEnabled(False)
        self.sc_escape.activated.connect(self._on_escape)

        for keys, slot in (
            ("Ctrl+L", self.focus_address),
            ("Alt+Left", lambda: self._engine_call("go_back")),
            ("Alt+Right", lambda: self._engine_call("go_forward")),
            ("F5", lambda: self._engine_call("reload")),
            ("Ctrl+R", lambda: self._engine_call("reload")),
            ("Ctrl+Tab", self._next_tab),
            ("Ctrl+Shift+Tab", self._prev_tab),
        ):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.activated.connect(slot)

    # ------------------------------------------------------------------ #
    # 标签页
    # ------------------------------------------------------------------ #
    def _create_engine(self) -> BrowserEngine:
        engine = create_engine(self.engine_id, self.tabs, incognito=self.incognito)
        engine.download_manager = self.downloads
        engine.extension_store = self.extensions
        engine.userscript_store = self.userscripts
        engine.new_tab_provider = lambda: self.new_tab(switch=True, autoload=False)
        engine.accelerator_handler = self._handle_accelerator

        engine.url_changed.connect(lambda url, e=engine: self._on_url_changed(e, url))
        engine.title_changed.connect(lambda title, e=engine: self._on_title_changed(e, title))
        engine.load_started.connect(lambda e=engine: self._on_load_started(e))
        engine.load_progress.connect(lambda value, e=engine: self._on_load_progress(e, value))
        engine.load_finished.connect(lambda ok, e=engine: self._on_load_finished(e, ok))
        engine.icon_changed.connect(lambda icon, e=engine: self._on_icon_changed(e, icon))
        engine.status_message.connect(lambda text, e=engine: self._on_status_message(e, text))
        engine.new_window_requested.connect(self._on_new_window_requested)
        engine.fullscreen_requested.connect(self.set_fullscreen)
        engine.find_result.connect(self._on_find_result)
        return engine

    def new_tab(
        self, url: Optional[str] = None, *, switch: bool = True, autoload: bool = True
    ) -> BrowserEngine:
        engine = self._create_engine()
        index = self.tabs.addTab(engine, icons.icon("globe", 16), "新标签页")
        self.tabs.setTabToolTip(index, "新标签页")

        if switch:
            self.tabs.setCurrentIndex(index)
        if autoload:
            target = url or self._startup_url()
            engine.load(target)
        elif url:
            engine.load(url)
        engine.set_zoom_factor(float(self.config.get("zoom") or 1.0))
        return engine

    def close_tab(self, index: int) -> None:
        if index < 0:
            return
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        if isinstance(widget, BrowserEngine):
            widget.shutdown()
        if widget is not None:
            widget.deleteLater()
        if self.tabs.count() == 0 and not self._switching:
            self.close()

    def _next_tab(self) -> None:
        count = self.tabs.count()
        if count > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % count)

    def _prev_tab(self) -> None:
        count = self.tabs.count()
        if count > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % count)

    def current_engine(self) -> Optional[BrowserEngine]:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, BrowserEngine) else None

    def _engine_call(self, method: str) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        getattr(engine, method, lambda: None)()

    def _on_tab_changed(self, index: int) -> None:
        engine = self.current_engine()
        if engine is None:
            self.address.setText("")
            self.setWindowTitle(APP_NAME)
            return
        self.address.setText(engine.current_url())
        self._update_navigation(engine)
        self._update_title(engine)
        self._refresh_zoom_label()

    # ------------------------------------------------------------------ #
    # 导航
    # ------------------------------------------------------------------ #
    def _startup_url(self) -> str:
        mode = str(self.config.get("startup_mode") or "home")
        if mode == "blank":
            return "about:blank"
        if mode == "last":
            last = str(self.config.get("last_url") or "").strip()
            if last:
                return last
        return self.config.homepage

    def _open_startup_page(self) -> None:
        target = self.initial_url or self._startup_url()
        if self.initial_url:
            target = self.normalize_url(target, self.config.search_url) or target
        self.new_tab(target)

    @staticmethod
    def normalize_url(text: str, search_url_builder) -> str:
        """把地址栏输入转换成 URL，必要时交给搜索引擎。"""
        text = (text or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        for prefix in ("http://", "https://", "file://", "about:", "data:", "chrome://",
                       "view-source:", "ftp://", "mailto:", "edge://", "lite://"):
            if lowered.startswith(prefix):
                return text
        if " " in text or "." not in text:
            return search_url_builder(text)
        if re.match(r"^localhost(:\d+)?(/.*)?$", lowered):
            return "http://" + text
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?(/.*)?$", text):
            return "http://" + text
        if re.match(r"^[^\s/]+\.[a-z]{2,}(:\d+)?([/?#].*)?$", lowered):
            return "https://" + text
        return search_url_builder(text)

    def navigate_from_address(self) -> None:
        target = self.normalize_url(self.address.text(), self.config.search_url)
        if target:
            self.navigate(target)

    def navigate(self, url: str) -> None:
        engine = self.current_engine()
        if engine is None:
            self.new_tab(url)
            return
        engine.load(url)

    def go_home(self) -> None:
        self.navigate(self.config.homepage)

    def _update_navigation(self, engine: BrowserEngine) -> None:
        self.act_back.setEnabled(engine.can_go_back())
        self.act_forward.setEnabled(engine.can_go_forward())

    # ------------------------------------------------------------------ #
    # 加载状态
    # ------------------------------------------------------------------ #
    def _on_load_started(self, engine: BrowserEngine) -> None:
        if engine is self.current_engine():
            self.progress.setValue(0)
            self.progress.setVisible(True)
            self.lbl_status.setText("正在打开网页...")

    def _on_load_progress(self, engine: BrowserEngine, value: int) -> None:
        if engine is self.current_engine():
            self.progress.setValue(int(value))

    def _on_load_finished(self, engine: BrowserEngine, ok: bool) -> None:
        if engine is self.current_engine():
            self.progress.setVisible(False)
            self.lbl_status.setText("完成" if ok else "无法打开该网页")
            self._update_navigation(engine)
        if ok:
            self._record_history(engine)

    def _record_history(self, engine: BrowserEngine) -> None:
        """记录浏览历史（无痕模式或关闭历史时不写入）。"""
        if self.history is None or self.incognito:
            return
        if not bool(self.config.get("history_enabled")):
            return
        url = engine.current_url()
        if not url:
            return
        self.history.record(url, engine.current_title())

    def _on_title_changed(self, engine: BrowserEngine, title: str) -> None:
        index = self.tabs.indexOf(engine)
        if index >= 0:
            text = title or engine.current_url() or "新标签页"
            self.tabs.setTabText(index, text[:28])
            self.tabs.setTabToolTip(index, title or "")
        if engine is self.current_engine():
            self._update_title(engine)

    def _update_title(self, engine: BrowserEngine) -> None:
        title = engine.current_title() or engine.current_url() or "新标签页"
        self.setWindowTitle(f"{title} - {APP_NAME}" if title else APP_NAME)

    def _on_url_changed(self, engine: BrowserEngine, url: str) -> None:
        if engine is self.current_engine():
            if url != "about:blank" or not self.address.hasFocus():
                self.address.setText(url)
                self.address.setCursorPosition(0)
            self._update_navigation(engine)
            self.config.set("last_url", url, save=False)
            self._refresh_zoom_label()

    def _on_icon_changed(self, engine: BrowserEngine, icon) -> None:
        index = self.tabs.indexOf(engine)
        if index >= 0:
            self.tabs.setTabIcon(
                index, icon if icon is not None and not icon.isNull() else icons.icon("globe", 16)
            )

    def _on_status_message(self, engine: BrowserEngine, text: str) -> None:
        if engine is self.current_engine():
            self.lbl_status.setText(text or "完成")

    def _on_new_window_requested(self, url: str) -> None:
        self.new_tab(url)

    # ------------------------------------------------------------------ #
    # 书签
    # ------------------------------------------------------------------ #
    def rebuild_bookmark_bar(self) -> None:
        self.bookmark_bar.clear()
        for index, item in enumerate(self.bookmarks.items()):
            action = QAction(icons.icon("star", 16), item["title"], self)
            action.setToolTip(item["url"])
            action.triggered.connect(lambda _checked=False, url=item["url"]: self.navigate(url))
            self.bookmark_bar.addAction(action)

        self.bookmark_bar.addSeparator()
        add_action = QAction(icons.icon("star_add", 16), "添加...", self)
        add_action.triggered.connect(self.add_current_bookmark)
        self.bookmark_bar.addAction(add_action)

        manage_action = QAction(icons.icon("bookmarks", 16), "整理...", self)
        manage_action.triggered.connect(self.manage_bookmarks)
        self.bookmark_bar.addAction(manage_action)

        self._favorite_items_menu.clear()
        items = self.bookmarks.items()
        if not items:
            empty = self._favorite_items_menu.addAction("（暂无书签）")
            empty.setEnabled(False)
            return
        for item in items[:30]:
            action = self._favorite_items_menu.addAction(icons.icon("star", 16), item["title"])
            action.setToolTip(item["url"])
            action.triggered.connect(lambda _checked=False, url=item["url"]: self.navigate(url))

    def add_current_bookmark(self) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        url = engine.current_url()
        if not url or url == "about:blank":
            QMessageBox.information(self, APP_NAME, "当前页面没有可以收藏的地址。")
            return
        title = engine.current_title() or url
        existing = self.bookmarks.index_of(url)
        if existing >= 0:
            answer = QMessageBox.question(
                self,
                APP_NAME,
                f"“{title}”已经在收藏夹中，是否更新它的名称？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                dialog = BookmarkEditDialog(self, title=title, url=url, editing=True)
                if dialog.exec():
                    name, new_url = dialog.values()
                    self.bookmarks.update(existing, name, new_url)
            return

        dialog = BookmarkEditDialog(self, title=title, url=url)
        if dialog.exec():
            name, new_url = dialog.values()
            self.bookmarks.add(name, new_url)

    def manage_bookmarks(self) -> None:
        dialog = BookmarkManagerDialog(self.bookmarks, self, open_callback=self.navigate)
        dialog.exec()

    # ------------------------------------------------------------------ #
    # 设置 / 关于
    # ------------------------------------------------------------------ #
    def open_settings(self, tab: int = 0) -> None:
        engine = self.current_engine()
        dialog = SettingsDialog(
            self.config,
            self,
            current_url=engine.current_url() if engine is not None else "",
            initial_tab=tab,
            engine_id=self.engine_id,
            vault=self.vault,
            history=self.history,
            downloads=self.downloads,
        )
        dialog.exec()

    def show_about(self) -> None:
        """设置 - 关于：显示作者信息。"""
        AboutDialog(self, engine_id=self.engine_id).exec()

    # ------------------------------------------------------------------ #
    # 下载 / 历史 / 无痕
    # ------------------------------------------------------------------ #
    def _install_download_handler(self) -> None:
        if self.downloads is None:
            return
        from . import qtengine

        qtengine.set_download_handler(lambda request: qtengine.handle_download(request, self.downloads))

    def _ask_folder(self, prompt: str) -> Optional[str]:
        folder = QFileDialog.getExistingDirectory(
            self, prompt, str(self.downloads.default_folder()) if self.downloads else str(Path.home())
        )
        return folder or None

    def open_downloads(self) -> None:
        if self.downloads is None:
            return
        dialog = DownloadManagerDialog(self.downloads, self, folder_asker=self._ask_folder)
        dialog.exec()

    def open_history(self) -> None:
        if self.history is None:
            return
        dialog = HistoryDialog(self.history, self, open_callback=self.navigate)
        dialog.exec()

    # ------------------------------------------------------------------ #
    # 插件：Chrome 扩展 + 油猴脚本
    # ------------------------------------------------------------------ #
    def open_plugins(self) -> None:
        if self.extensions is None or self.userscripts is None:
            return
        dialog = ExtensionManagerDialog(
            self.extensions,
            self.userscripts,
            self,
            engine_id=self.engine_id,
            on_changed=self._on_plugins_changed,
        )
        dialog.exec()
        self._on_plugins_changed()

    def _on_plugins_changed(self) -> None:
        """扩展 / 脚本变化后让所有标签页重新加载插件。"""
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, BrowserEngine):
                try:
                    widget.refresh_plugins()
                except Exception:
                    pass
        self._refresh_script_menu()

    def _refresh_script_menu(self) -> None:
        """把用户脚本注册的菜单命令挂到「工具 → 用户脚本命令」。"""
        if self.userscripts is None:
            return
        self._script_menu.clear()
        count = 0
        for script in self.userscripts.enabled():
            commands = self.userscripts.menu_commands.get(script.id) or []
            if not commands:
                continue
            for name, command_id in commands:
                action = self._script_menu.addAction(icons.icon("plugin", 16), f"{name}（{script.display_name}）")
                action.triggered.connect(
                    lambda _checked=False, sid=script.id, cid=command_id: self._run_script_command(sid, cid)
                )
                count += 1
        self._script_menu.setEnabled(count > 0)
        if count == 0:
            empty = self._script_menu.addAction("（脚本尚未注册命令）")
            empty.setEnabled(False)

    def _run_script_command(self, script_id: str, command_id: str) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        engine.post_to_page(
            "window.__lbGmMenu && window.__lbGmMenu(%s, %s);"
            % (json.dumps(script_id), json.dumps(command_id))
        )

    def _purge_history(self) -> None:
        if self.history is None:
            return
        days = int(self.config.get("history_keep_days") or 0)
        if days > 0:
            self.history.purge_before(time.time() - days * 86400)

    def _on_incognito_toggled(self, enabled: bool) -> None:
        self.set_incognito(enabled)

    def set_incognito(self, enabled: bool) -> None:
        """切换无痕浏览模式；切换后会重新打开标签页。"""
        enabled = bool(enabled)
        if enabled == self.incognito:
            return
        if self.vault is None:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            ("开启无痕浏览模式后，浏览历史不会被记录，Cookie 与缓存只保存在内存中。\n"
             "切换模式会关闭当前所有标签页并重新打开，是否继续？")
            if enabled
            else "关闭无痕浏览模式后将恢复记录浏览历史，切换模式会重新打开标签页，是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            self._sync_incognito_actions()
            return

        self.incognito = enabled
        self.config.set("incognito", enabled)
        self._reload_session()
        self._sync_incognito_actions()

    def _sync_incognito_actions(self) -> None:
        for action in (self.act_incognito, self.act_toggle_incognito):
            action.blockSignals(True)
            action.setChecked(self.incognito)
            action.blockSignals(False)
        self.lbl_incognito.setVisible(self.incognito)
        self.act_incognito.setToolTip(
            "当前处于无痕浏览模式" if self.incognito else "点击切换到无痕浏览模式"
        )
        if self.downloads is not None:
            # 无痕模式下不把下载记录写入磁盘
            self.downloads.incognito = self.incognito

    def _reload_session(self) -> None:
        self._switching = True
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if isinstance(widget, BrowserEngine):
                widget.shutdown()
            if widget is not None:
                widget.deleteLater()
        self._switching = False
        self.new_tab(self.config.homepage)

    def export_plain_dialog(self) -> None:
        if self.vault is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "导出明文数据到", str(Path.home()))
        if not folder:
            return
        count = self.export_plain_data(Path(folder))
        QMessageBox.information(self, APP_NAME, f"已导出 {count} 个文件到：\n{folder}")

    def export_plain_data(self, folder: Path) -> int:
        """把加密的数据文件解密后导出为明文 JSON。"""
        if self.vault is None:
            return 0
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        sources = []
        if self.bookmarks is not None:
            sources.append(("bookmarks.json", self.bookmarks.blob_path, self.bookmarks.legacy_path))
        if self.history is not None:
            sources.append(("history.json", self.history.blob_path, self.history.legacy_path))
        if self.downloads is not None:
            sources.append(("downloads.json", self.downloads.blob_path, self.downloads.legacy_path))

        count = 0
        for name, blob, legacy in sources:
            text = self.vault.read_text(blob, legacy)
            if text:
                try:
                    (folder / name).write_text(text, encoding="utf-8")
                    count += 1
                except OSError:
                    pass
        return count

    def resave_bookmarks(self) -> None:
        if self.bookmarks is not None:
            self.bookmarks.save()

    def on_settings_applied(self, config: Config) -> None:
        self.apply_config()
        want_incognito = bool(config.get("incognito"))
        if want_incognito != self.incognito:
            self.set_incognito(want_incognito)
        if self.history is not None:
            days = int(config.get("history_keep_days") or 0)
            if days > 0:
                self.history.purge_before(time.time() - days * 86400)

    def apply_config(self) -> None:
        show_bar = bool(self.config.get("show_bookmark_bar"))
        self.act_bookmark_bar.setChecked(show_bar)
        self.bookmark_bar.setVisible(show_bar and not self._fullscreen)

        show_status = bool(self.config.get("show_status_bar"))
        self.act_status_bar.setChecked(show_status)
        self.status.setVisible(show_status and not self._fullscreen)

        self.lbl_engine.setText("WebView2" if self.engine_id == "webview2" else "QtWebEngine")
        self._sync_incognito_actions()
        self._apply_zoom()

    def _toggle_bookmark_bar(self, visible: bool) -> None:
        self.config.set("show_bookmark_bar", bool(visible))
        self.bookmark_bar.setVisible(bool(visible) and not self._fullscreen)

    def _toggle_status_bar(self, visible: bool) -> None:
        self.config.set("show_status_bar", bool(visible))
        self.status.setVisible(bool(visible) and not self._fullscreen)

    # ------------------------------------------------------------------ #
    # 缩放
    # ------------------------------------------------------------------ #
    def _apply_zoom(self) -> None:
        self.set_zoom(float(self.config.get("zoom") or 1.0))

    def _refresh_zoom_label(self) -> None:
        engine = self.current_engine()
        factor = engine.zoom_factor() if engine is not None else 1.0
        self.lbl_zoom.setText(f"{int(round(factor * 100))}%")

    def change_zoom(self, delta_percent: int) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        self.set_zoom(engine.zoom_factor() + delta_percent / 100.0)

    def set_zoom(self, factor: float) -> None:
        factor = max(0.25, min(5.0, factor))
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, BrowserEngine):
                widget.set_zoom_factor(factor)
        self.config.set("zoom", round(factor, 2))
        self._refresh_zoom_label()

    # ------------------------------------------------------------------ #
    # 全屏
    # ------------------------------------------------------------------ #
    def set_fullscreen(self, enabled: bool) -> None:
        """全屏显示 / 退出全屏。"""
        if enabled == self._fullscreen:
            return
        self._fullscreen = enabled

        if enabled:
            self._was_maximized = self.isMaximized()
            self.menu_bar.setVisible(False)
            self.toolbar.setVisible(False)
            self.bookmark_bar.setVisible(False)
            self.find_bar.setVisible(False)
            self.status.setVisible(False)
            self.tabs.tabBar().setVisible(False)
            self.tabs.setCornerWidget(None)
            self.set_window_chrome_visible(False)
            self.sc_escape.setEnabled(True)
            self.showFullScreen()
            self.lbl_status.setText("按 F11 或 Esc 退出全屏")
        else:
            self.menu_bar.setVisible(True)
            self.toolbar.setVisible(True)
            self.tabs.tabBar().setVisible(True)
            self.tabs.setCornerWidget(self.btn_new_tab, Qt.TopRightCorner)
            self.bookmark_bar.setVisible(bool(self.config.get("show_bookmark_bar")))
            self.status.setVisible(bool(self.config.get("show_status_bar")))
            self.set_window_chrome_visible(True)
            self.sc_escape.setEnabled(False)
            if self.isFullScreen():
                self.showNormal()
            if self._was_maximized:
                self.showMaximized()

        self.act_fullscreen.setChecked(enabled)

    def _on_escape(self) -> None:
        if self._fullscreen:
            self.set_fullscreen(False)

    def _handle_accelerator(self, key: int, ctrl: bool, shift: bool, alt: bool) -> bool:
        """处理来自 WebView2 的快捷键（网页视图有焦点时 Qt 收不到按键）。"""
        # Qt 修饰键的数值常量，避免不同绑定下枚举转换差异
        modifiers = 0
        if shift:
            modifiers |= 0x02000000      # Qt.ShiftModifier
        if ctrl:
            modifiers |= 0x04000000      # Qt.ControlModifier
        if alt:
            modifiers |= 0x08000000      # Qt.AltModifier
        sequence = QKeySequence(modifiers | int(key))

        for action in self._shortcut_actions:
            if action.isEnabled() and action.shortcut() == sequence:
                action.trigger()
                return True

        if key == int(Qt.Key_Escape) and self._fullscreen:
            self.set_fullscreen(False)
            return True
        if ctrl and key == int(Qt.Key_Tab):
            self._next_tab() if not shift else self._prev_tab()
            return True
        if alt and key == int(Qt.Key_Left):
            self._engine_call("go_back")
            return True
        if alt and key == int(Qt.Key_Right):
            self._engine_call("go_forward")
            return True
        return False

    # ------------------------------------------------------------------ #
    # 查找
    # ------------------------------------------------------------------ #
    def show_find_bar(self) -> None:
        self.find_bar.setVisible(True)
        self.find_edit.setFocus()
        self.find_edit.selectAll()
        if self.find_edit.text():
            self._find(self.find_edit.text(), True)

    def hide_find_bar(self) -> None:
        engine = self.current_engine()
        if engine is not None:
            engine.clear_find()
        self.find_bar.setVisible(False)
        self.find_result.setText("")

    def _find(self, text: str, forward: bool) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        engine.find_text(text, forward)

    def _on_find_result(self, matches: int, active: int) -> None:
        if not self.find_bar.isVisible():
            return
        if matches <= 0:
            self.find_result.setText("找不到匹配项")
        elif active:
            self.find_result.setText(f"第 {active + 1} / {matches} 个")
        else:
            self.find_result.setText(f"共 {matches} 个匹配")

    # ------------------------------------------------------------------ #
    # 其它
    # ------------------------------------------------------------------ #
    def focus_address(self) -> None:
        self.address.setFocus()
        self.address.selectAll()

    def view_source(self) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        url = engine.current_url()
        if url:
            self.new_tab("view-source:" + url)

    def _edit_action(self, name: str) -> None:
        engine = self.current_engine()
        if engine is not None:
            engine.edit_action(name)

    # ------------------------------------------------------------------ #
    # 几何 / 生命周期
    # ------------------------------------------------------------------ #
    def _restore_geometry(self) -> None:
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        geometry = self.config.get("window_geometry")

        width, height = 1080, 720
        if available is not None:
            width = min(width, available.width())
            height = min(height, available.height())

        if isinstance(geometry, (list, tuple)) and len(geometry) == 4:
            try:
                x, y, w, h = (int(v) for v in geometry)
                width = max(680, min(w, available.width() if available else w))
                height = max(460, min(h, available.height() if available else h))
                if available is not None:
                    x = min(max(x, available.left()), available.right() - width + 1)
                    y = min(max(y, available.top()), available.bottom() - height + 1)
                self.setGeometry(x, y, width, height)
            except (TypeError, ValueError):
                self.resize(width, height)
        else:
            self.resize(width, height)

        if screen is not None and not self.config.get("window_geometry"):
            available = screen.availableGeometry()
            self.move(
                available.center().x() - self.width() // 2,
                available.center().y() - self.height() // 2,
            )
        if bool(self.config.get("window_maximized")):
            self.showMaximized()

    def closeEvent(self, event) -> None:  # noqa: D102
        try:
            if not self.isMaximized() and not self.isFullScreen():
                rect = self.geometry()
                self.config.set(
                    "window_geometry",
                    [rect.x(), rect.y(), rect.width(), rect.height()],
                    save=False,
                )
            self.config.set("window_maximized", self.isMaximized(), save=False)
            engine = self.current_engine()
            if engine is not None:
                self.config.set("last_url", engine.current_url(), save=False)
            self.config.save()
        except Exception:
            pass
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, BrowserEngine):
                try:
                    widget.shutdown()
                except Exception:
                    pass
        super().closeEvent(event)
