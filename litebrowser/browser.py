"""浏览器主窗口：标签页、地址栏、书签栏、全屏、菜单。"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
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

from . import icons, theme
from .bookmarks import BookmarkStore
from .config import APP_NAME, APP_VERSION, AUTHOR, Config, data_dir
from .crypto import DataVault
from .dialogs import (
    AboutDialog,
    AdRulesDialog,  # noqa: F401  (延迟使用，保留导入便于帮助/设置复用)
    BookmarkEditDialog,
    BookmarkManagerDialog,
    SettingsDialog,
)
from .downloads import DownloadManager
from .engine import BrowserEngine, create_engine, resolve_engine
from .history import HistoryStore
from .managers import DownloadManagerDialog, HistoryDialog
from .widgets import XPWindow


class MainWindow(XPWindow):
    """lite browser 主窗口。"""

    def __init__(
        self,
        config: Config,
        bookmarks: BookmarkStore,
        initial_url: Optional[str] = None,
        engine_id: Optional[str] = None,
        vault: Optional[DataVault] = None,
        history: Optional[HistoryStore] = None,
        downloads: Optional[DownloadManager] = None,
        security=None,
        performance=None,
        adblock=None,
    ) -> None:
        super().__init__(title=APP_NAME, icon=icons.app_icon())
        self.config = config
        self.bookmarks = bookmarks
        self.initial_url = (initial_url or "").strip() or None
        self.engine_id = engine_id or resolve_engine(str(config.get("engine") or "auto"))
        self.vault = vault
        self.history = history
        self.downloads = downloads
        self.security = security
        self.performance = performance
        if adblock is None:
            from .adblock import AdRuleStore

            adblock = AdRuleStore()
        self.adblock = adblock
        self._popup_blocked_count = 0
        self._security_level = "ok"
        self._security_text = "尚未打开网页"
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

        if self.performance is not None:
            self.performance.tabs_provider = lambda: [
                self.tabs.widget(index)
                for index in range(self.tabs.count())
                if isinstance(self.tabs.widget(index), BrowserEngine)
            ]
            self.performance.current_provider = self.current_engine
            self.performance.start()

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
        self.security_button = QToolButton(self.body)
        self.security_button.setAutoRaise(True)
        self.security_button.setIconSize(QSize(16, 16))
        self.security_button.setToolTip("连接安全性")
        self.security_button.clicked.connect(self.show_security_details)
        self.security_button.setIcon(icons.icon("lock", 16))
        security_wrap = QWidget(self.body)
        security_layout = QHBoxLayout(security_wrap)
        security_layout.setContentsMargins(2, 0, 4, 0)
        security_layout.setSpacing(2)
        security_layout.addWidget(self.security_button)
        self.toolbar.addWidget(security_wrap)
        self.toolbar.addWidget(self.address)
        self.toolbar.addSeparator()

        self.act_go = QAction(icons.icon("go", 22), "转到", self)
        self.act_star = QAction(icons.icon("star_add", 22), "收藏", self)
        self.act_bookmarks = QAction(icons.icon("bookmarks", 22), "收藏夹", self)
        self.act_download = QAction(icons.icon("download", 22), "下载", self)
        self.act_history = QAction(icons.icon("history", 22), "历史", self)
        self.act_incognito = QAction(icons.icon("incognito", 22), "无痕", self)
        self.act_incognito.setCheckable(True)
        self.act_settings = QAction(icons.icon("settings", 22), "设置", self)
        for action in (
            self.act_go,
            self.act_star,
            self.act_bookmarks,
            self.act_download,
            self.act_history,
            self.act_incognito,
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

        self.progress = QProgressBar()
        self.progress.setFixedSize(150, 14)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)

        self.lbl_incognito = QLabel("无痕浏览")
        self.lbl_incognito.setObjectName("incognitoBadge")
        self.lbl_incognito.setToolTip("当前处于无痕浏览模式：不记录历史、Cookie 与缓存")
        self.lbl_incognito.setVisible(False)

        self.lbl_engine = QLabel("")
        self.lbl_engine.setToolTip("当前渲染引擎")

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setFixedWidth(46)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)

        # 底边栏右侧显示版本号（点击可打开「关于」）
        self.btn_version = QToolButton(self.status)
        self.btn_version.setObjectName("statusVersion")
        self.btn_version.setText(f"v{APP_VERSION}")
        self.btn_version.setAutoRaise(True)
        self.btn_version.setCursor(Qt.PointingHandCursor)
        self.btn_version.setToolTip(f"{APP_NAME} v{APP_VERSION}\n作者：{AUTHOR}\n点击查看「关于」")
        self.btn_version.clicked.connect(self.show_about)

        # 状态栏内容放进一个容器：QStatusBar.addWidget 每次都会重新排版并 polish，
        # 逐个添加会明显拖慢启动（实测 5 次约 350ms）
        status_wrap = QWidget(self.status)
        status_wrap.setObjectName("statusWrap")
        status_row = QHBoxLayout(status_wrap)
        status_row.setContentsMargins(6, 0, 6, 0)
        status_row.setSpacing(8)
        status_row.addWidget(self.lbl_status, 1)
        status_row.addWidget(self.progress)
        status_row.addWidget(self.lbl_incognito)
        status_row.addWidget(self.lbl_engine)
        status_row.addWidget(self.lbl_zoom)
        status_row.addWidget(self.btn_version)
        self.status.addWidget(status_wrap, 1)
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
        self.address.returnPressed.connect(self.navigate_from_address)

    def _build_find_bar(self) -> QWidget:
        bar = QWidget(self.body)
        bar.setObjectName("findBar")
        # 样式由全局 QSS（QWidget#findBar）提供，随主题与深浅色变化
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
        self.act_save_as = QAction(icons.icon("save", 16), "页面另存为(A)...", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+S"))
        self.act_save_as.triggered.connect(self.save_page_dialog)
        self.act_save_mhtml = QAction(icons.icon("save", 16), "保存为 MHTML 单文件(M)...", self)
        self.act_save_mhtml.triggered.connect(lambda: self.save_page_as("mhtml"))
        self.act_save_html = QAction(icons.icon("save", 16), "保存为完整网页(H)...", self)
        self.act_save_html.triggered.connect(lambda: self.save_page_as("html"))
        self.act_save_html_only = QAction("保存为仅 HTML(S)...", self)
        self.act_save_html_only.triggered.connect(lambda: self.save_page_as("html-only"))
        self.act_print = QAction(icons.icon("print", 16), "打印(P)...", self)
        self.act_print.setShortcut(QKeySequence("Ctrl+P"))
        self.act_print.triggered.connect(self.print_page)
        self.act_pdf = QAction(icons.icon("print", 16), "导出为 PDF(D)...", self)
        self.act_pdf.triggered.connect(self.export_pdf)
        self.act_quit = QAction(icons.icon("exit", 16), "退出(X)", self)
        self.act_quit.setShortcut(QKeySequence("Alt+F4"))
        self.act_quit.triggered.connect(self.close)
        for action in (
            self.act_new_tab,
            self.act_close_tab,
            None,
            self.act_save_as,
            self.act_save_mhtml,
            self.act_save_html,
            self.act_save_html_only,
            None,
            self.act_print,
            self.act_pdf,
            None,
            self.act_quit,
        ):
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
        self.act_dark_mode = QAction(icons.icon("incognito", 16), "深色模式(D)", self)
        self.act_dark_mode.setCheckable(True)
        self.act_dark_mode.setShortcut(QKeySequence("Ctrl+Shift+D"))
        self.act_dark_mode.setToolTip("浅色 / 深色模式切换（会记住选择）")
        self.act_dark_mode.toggled.connect(self.toggle_dark_mode)
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
            None,
            self.act_dark_mode,
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
        self.act_desktop_shortcut = QAction(icons.icon("app", 16), "创建桌面快捷方式(S)", self)
        self.act_desktop_shortcut.triggered.connect(lambda: self.create_shortcut("desktop"))
        self.act_startmenu_shortcut = QAction("创建开始菜单快捷方式(M)", self)
        self.act_startmenu_shortcut.triggered.connect(lambda: self.create_shortcut("startmenu"))
        tools_menu.addAction(self.act_open_downloads)
        tools_menu.addAction(self.act_open_history)
        self.act_open_data = QAction(icons.icon("settings", 16), "Cookie 与缓存管理(K)...", self)
        self.act_open_data.setShortcut(QKeySequence("Ctrl+Shift+Del"))
        self.act_open_data.triggered.connect(self.open_data_manager)
        tools_menu.addAction(self.act_open_data)
        tools_menu.addSeparator()
        self.act_mark_ad = QAction(icons.icon("warn", 16), "标记并屏蔽广告元素(M)", self)
        self.act_mark_ad.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.act_mark_ad.setToolTip("点一下网页上要屏蔽的广告（弹窗、横幅、浮层），以后打开同一网站自动隐藏")
        self.act_mark_ad.triggered.connect(self.mark_ad_element)
        self.act_ad_rules = QAction(icons.icon("settings", 16), "广告屏蔽规则(R)...", self)
        self.act_ad_rules.triggered.connect(self.open_ad_rules)
        self.act_flash_compat = QAction(icons.icon("globe", 16), "Flash 兼容（Ruffle，无广告）(F)", self)
        self.act_flash_compat.setCheckable(True)
        self.act_flash_compat.setToolTip(
            "用开源 Ruffle 模拟器运行 Flash 内容（4399 小游戏等），无广告、无需装 Flash 插件"
        )
        self.act_flash_compat.toggled.connect(self.toggle_flash_compat)
        tools_menu.addAction(self.act_mark_ad)
        tools_menu.addAction(self.act_ad_rules)
        tools_menu.addAction(self.act_flash_compat)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_toggle_incognito)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_export_plain)
        tools_menu.addSeparator()
        tools_menu.addAction(self.act_desktop_shortcut)
        tools_menu.addAction(self.act_startmenu_shortcut)

        settings_menu = bar.addMenu("设置(S)")
        self.act_open_settings = QAction(icons.icon("settings", 16), "设置(O)...", self)
        self.act_open_settings.triggered.connect(self.open_settings)
        self.act_about = QAction(icons.icon("info", 16), f"关于 {APP_NAME}(A)", self)
        self.act_about.triggered.connect(self.show_about)
        settings_menu.addAction(self.act_open_settings)
        settings_menu.addSeparator()
        settings_menu.addAction(self.act_about)

        help_menu = bar.addMenu("帮助(H)")
        self.act_guide = QAction(icons.icon("info", 16), "使用帮助(H)...", self)
        self.act_guide.setShortcut(QKeySequence("F1"))
        self.act_guide.triggered.connect(lambda: self.open_help("start"))
        self.act_video_check = QAction(icons.icon("globe", 16), "视频播放自检(V)", self)
        self.act_video_check.triggered.connect(self.open_video_check)
        self.act_shortcuts = QAction(icons.icon("find", 16), "快捷键一览(K)...", self)
        self.act_shortcuts.triggered.connect(lambda: self.open_help("shortcut"))
        self.act_faq = QAction(icons.icon("warn", 16), "常见问题(Q)...", self)
        self.act_faq.triggered.connect(lambda: self.open_help("faq"))
        self.act_feature_help = QAction(icons.icon("app", 16), "功能说明(F)...", self)
        self.act_feature_help.triggered.connect(lambda: self.open_help("theme"))
        self.act_help = QAction(icons.icon("info", 16), f"关于 {APP_NAME}(A)", self)
        self.act_help.triggered.connect(self.show_about)
        for action in (
            self.act_guide,
            self.act_video_check,
            self.act_shortcuts,
            self.act_feature_help,
            self.act_faq,
            None,
            self.act_help,
        ):
            help_menu.addAction(action) if action else help_menu.addSeparator()

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
        engine.new_tab_provider = lambda: self.new_tab(switch=True, autoload=False)
        engine.accelerator_handler = self._handle_accelerator
        engine.security_manager = self.security
        engine.config = self.config

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
        engine.certificate_error.connect(
            lambda info, e=engine: self._on_certificate_error(e, info)
        )
        engine.error_page_shown.connect(
            lambda url, code, e=engine: self._on_error_page(e, url, code)
        )
        engine.command_requested.connect(lambda url, e=engine: self._on_command(e, url))
        engine.popup_blocked.connect(lambda url, e=engine: self._on_popup_blocked(e, url))
        engine.adblock_store = self.adblock

        from .useragent import resolve

        try:
            engine.set_user_agent(resolve(str(self.config.get("user_agent") or "")))
            load_images = self.config.get("load_images")
            engine.set_preferences(
                load_images=True if load_images is None else bool(load_images),
                preload=bool(self.config.get("preload_links")),
                smooth_scroll=bool(self.config.get("smooth_scroll")),
            )
        except Exception:
            pass
        # 广告屏蔽 / 弹窗拦截 / Flash 兼容
        try:
            engine._block_popups = bool(self.adblock.block_popups)
            engine.set_adblock(
                self.adblock.selectors_for(engine.current_url()),
                block_popups=self.adblock.block_popups,
            )
            self._apply_ruffle_to_engine(engine)
        except Exception:
            pass
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
            engine.load(self._swf_redirect(target, engine) or target)
        elif url:
            engine.load(self._swf_redirect(url, engine) or url)
        engine.set_zoom_factor(float(self.config.get("zoom") or 1.0))
        if not engine.is_ready():
            self.lbl_status.setText("正在启动渲染引擎…")
            self.progress.setRange(0, 0)
            self.progress.setVisible(True)
        return engine

    def close_tab(self, index: int) -> None:
        if index < 0:
            return
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        if isinstance(widget, BrowserEngine):
            if self.performance is not None:
                self.performance.note_closed(widget)
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

    def _load_finished_extra(self, engine: BrowserEngine) -> None:
        """加载完成后刷新安全指示与预读取。"""
        if engine is self.current_engine():
            self._update_security_indicator()
        if bool(self.config.get("preload_links")):
            try:
                engine.prefetch_links()
            except Exception:
                pass

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
        self._update_security_indicator()
        self._sync_content_visibility()
        if self.performance is not None:
            self.performance.note_active(engine)

    def _sync_content_visibility(self) -> None:
        """只显示当前标签页的网页内容，后台标签页隐藏后才能真正挂起省内存。"""
        current = self.current_engine()
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if not isinstance(widget, BrowserEngine):
                continue
            try:
                widget.set_content_visible(widget is current)
            except Exception:
                continue

    # ------------------------------------------------------------------ #
    # 网页保存 / 打印
    # ------------------------------------------------------------------ #
    def _suggest_filename(self, suffix: str) -> str:
        engine = self.current_engine()
        title = (engine.current_title() if engine is not None else "") or "page"
        name = re.sub(r'[\\/:*?"<>|]+', "_", title).strip()[:80] or "page"
        folder = Path(str(self.config.get("download_dir") or Path.home()))
        return str(folder / f"{name}{suffix}")

    def save_page_dialog(self) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        path, selected = QFileDialog.getSaveFileName(
            self,
            "页面另存为",
            self._suggest_filename(".mhtml"),
            "MHTML 单文件 (*.mhtml);;完整网页 (*.htm *.html);;仅 HTML (*.html)",
        )
        if not path:
            return
        if "MHTML" in selected:
            fmt = "mhtml"
            if not path.lower().endswith(".mhtml"):
                path += ".mhtml"
        elif "完整" in selected:
            fmt = "html"
        else:
            fmt = "html-only"
        self._perform_save(path, fmt)

    def save_page_as(self, fmt: str) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        suffix = ".mhtml" if fmt == "mhtml" else ".html"
        filters = {
            "mhtml": "MHTML 单文件 (*.mhtml)",
            "html": "完整网页 (*.htm *.html)",
            "html-only": "仅 HTML (*.html)",
        }[fmt]
        path, _selected = QFileDialog.getSaveFileName(
            self, "保存网页", self._suggest_filename(suffix), filters
        )
        if not path:
            return
        self._perform_save(path, fmt)

    def _perform_save(self, path: str, fmt: str) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        ok = engine.save_page_as(path, fmt)
        if ok:
            QMessageBox.information(self, APP_NAME, f"已保存到：\n{path}")
        else:
            QMessageBox.warning(self, APP_NAME, "保存失败：当前内核不支持该操作。")

    def print_page(self) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        if engine.engine_id == "webview2":
            engine.print_page()
            return
        # QtWebEngine 6 取消了直接打印接口，改为导出 PDF 后交给系统打印
        from PySide6.QtCore import QDir

        path = Path(QDir.tempPath()) / f"lite-browser-print-{int(time.time())}.pdf"
        engine.export_pdf(str(path))
        QTimer.singleShot(1500, lambda: self._open_pdf(path))
        self.lbl_status.setText("已生成打印预览 PDF，正在打开…")

    def export_pdf(self) -> None:
        engine = self.current_engine()
        if engine is None:
            return
        path, _selected = QFileDialog.getSaveFileName(
            self, "导出为 PDF", self._suggest_filename(".pdf"), "PDF 文件 (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if engine.export_pdf(path):
            QTimer.singleShot(1500, lambda: QMessageBox.information(
                self, APP_NAME, f"已导出 PDF：\n{path}"
            ))
        else:
            QMessageBox.warning(self, APP_NAME, "导出失败：当前内核不支持该操作。")

    def _open_pdf(self, path: Path) -> None:
        import os

        try:
            if path.exists():
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                QMessageBox.warning(self, APP_NAME, "生成 PDF 失败。")
        except Exception:
            QMessageBox.information(self, APP_NAME, f"PDF 已生成：\n{path}")

    # ------------------------------------------------------------------ #
    # 数据管理 / 安全
    # ------------------------------------------------------------------ #
    def open_data_manager(self) -> None:
        from .datamanage import CookieManagerDialog

        dialog = CookieManagerDialog(self.current_engine, self, performance=self.performance)
        dialog.exec()

    # ------------------------------------------------------------------ #
    # 帮助
    # ------------------------------------------------------------------ #
    def open_help(self, topic: str = "start") -> None:
        from .help import HelpDialog

        dialog = HelpDialog(self, window=self, config=self.config, initial=topic)
        dialog.exec()

    def open_video_check(self) -> None:
        """打开「视频播放自检」页，用于确认内核是否支持 H.264/AAC。"""
        from .engine import ENGINE_LABELS
        from .videocheck import page_url

        version = ""
        try:
            from .wv2engine import browser_version

            version = browser_version()
        except Exception:
            version = ""
        url = page_url(
            engine_id=self.engine_id,
            engine_label=ENGINE_LABELS.get(self.engine_id, self.engine_id),
            browser_version=version,
        )
        engine = self.current_engine()
        if engine is not None:
            engine.address_override = "lite:video-check"
        self.navigate(url)

    # ------------------------------------------------------------------ #
    # 快捷方式
    # ------------------------------------------------------------------ #
    def create_shortcut(self, folder: str = "desktop") -> None:
        from .shelllink import create_shortcut, shortcut_path

        name = APP_NAME
        if shortcut_path(name, folder).exists():
            answer = QMessageBox.question(
                self,
                APP_NAME,
                f"快捷方式已存在：\n{shortcut_path(name, folder)}\n\n是否覆盖？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        ok, message = create_shortcut(
            name,
            folder=folder,
            description=f"{APP_NAME} - {APP_VERSION}（作者 {AUTHOR}）",
        )
        if ok:
            QMessageBox.information(
                self, APP_NAME,
                ("已在桌面创建快捷方式：\n" if folder == "desktop" else "已在开始菜单创建快捷方式：\n")
                + message,
            )
        else:
            QMessageBox.warning(self, APP_NAME, f"创建快捷方式失败：\n{message}")

    def _update_security_indicator(self) -> None:
        from .netsec import security_icon

        engine = self.current_engine()
        url = engine.current_url() if engine is not None else ""
        if engine is not None and getattr(engine, "_blocked_url", ""):
            level, text = "danger", "已拦截：该网址可能存在风险"
        elif not url:
            level, text = "ok", "尚未打开网页"
        elif url.lower().startswith("https://"):
            level, text = "ok", "安全连接（HTTPS，已加密）"
        elif url.lower().startswith(("file://", "about:", "lite:", "data:", "view-source:")):
            level, text = "ok", "本地页面"
        else:
            level, text = "warn", "不安全连接（HTTP，未加密）"
        self._security_level = level
        self._security_text = text
        try:
            self.security_button.setIcon(icons.icon(security_icon(level), 16))
            self.security_button.setToolTip(f"{text}\n点击查看详细信息")
        except Exception:
            pass

    def show_security_details(self) -> None:
        from .datamanage import CookieManagerDialog

        engine = self.current_engine()
        url = engine.current_url() if engine is not None else ""
        host = ""
        try:
            from urllib.parse import urlsplit

            host = urlsplit(url).hostname or ""
        except Exception:
            host = ""
        scheme = url.split(":")[0] if ":" in url else ""
        detail = (
            f"连接状态：{getattr(self, '_security_text', '未知')}\n"
            f"地址：{url or '（无）'}\n"
            f"主机：{host or '（无）'}\n"
            f"协议：{scheme or '（无）'}\n"
        )
        if scheme == "https":
            detail += "传输加密：TLS（由内核完成证书校验）\n"
        elif scheme == "http":
            detail += "传输加密：无（内容可能在传输过程中被窃取或篡改）\n"
        detail += f"\n当前内核：{self.engine_id}"

        dialog = QMessageBox(self)
        dialog.setWindowTitle("连接安全性")
        dialog.setIcon(QMessageBox.Information)
        dialog.setText("连接安全性详细信息")
        dialog.setInformativeText(detail)
        btn_cookie = dialog.addButton("管理 Cookie 与缓存", QMessageBox.ActionRole)
        dialog.addButton("关闭", QMessageBox.AcceptRole)
        dialog.exec()
        if dialog.clickedButton() is btn_cookie:
            CookieManagerDialog(self.current_engine, self, performance=self.performance).exec()

    def _on_certificate_error(self, engine: BrowserEngine, info) -> None:
        from .datamanage import CertificateDialog

        if not bool(self.config.get("certificate_warning", True)):
            try:
                engine.resolve_certificate(False)
            except Exception:
                pass
            return

        had_focus = self.isActiveWindow()
        dialog = CertificateDialog(info, self)
        accepted = dialog.exec() == QDialog.Accepted and dialog.allowed
        try:
            engine.resolve_certificate(bool(accepted))
        except Exception:
            pass
        if had_focus:
            self.raise_()

    def _on_error_page(self, engine: BrowserEngine, url: str, code: int) -> None:
        tab_index = self.tabs.indexOf(engine)
        if code == -100:
            message = "已拦截可能存在风险的网址"
            title = "已拦截的网址"
        else:
            from .errors import friendly

            message = friendly(code) if code else "无法打开该页面"
            title = "无法访问此页面"
        if tab_index >= 0:
            self.tabs.setTabText(tab_index, title)
            self.tabs.setTabToolTip(tab_index, f"{message}\n{url}")
        if engine is self.current_engine():
            self.address.setText(url)
            self.setWindowTitle(f"{title} - {APP_NAME}")
        self.lbl_status.setText(f"{message}　{url}")
        self._update_security_indicator()

    def _on_command(self, engine: BrowserEngine, command: str) -> None:
        from urllib.parse import parse_qs, unquote

        target = (command or "")[5:]
        if target.startswith("home"):
            engine._error_url = ""
            engine._blocked_url = ""
            engine.load(self.config.homepage)
            return
        if target.startswith("allow?"):
            query = parse_qs(target[6:])
            real = unquote((query.get("url") or [""])[0])
            if not real:
                return
            engine._allow_once.add(real)
            engine._error_url = ""
            engine._blocked_url = ""
            engine.load(real)
            return
        if target.startswith("adpick?"):
            self._accept_ad_pick(engine, command)
            return

    # ------------------------------------------------------------------ #
    # 广告标记与屏蔽
    # ------------------------------------------------------------------ #
    def _accept_ad_pick(self, engine: BrowserEngine, command: str) -> None:
        """收到点选结果：按域名记录规则并立即生效。"""
        from .adblock import parse_pick_command

        selector, host = parse_pick_command(command)
        if not selector:
            self.lbl_status.setText("未能生成选择器，广告标记已取消")
            return
        page_url = engine.current_url() or host
        rule = self.adblock.add(page_url or host, selector)
        if rule is None:
            self.lbl_status.setText("广告标记失败：网页地址无效")
            return
        engine.set_adblock(self.adblock.selectors_for(page_url), block_popups=self.adblock.block_popups)
        self.lbl_status.setText(f"✓ 已屏蔽该元素（规则已保存到 {rule.domain}）")
        self._notify(
            "已加入屏蔽规则",
            f"一只路过的哈基米 🐱 帮你记住了这个广告元素：\n{selector}\n"
            f"以后打开 {rule.domain} 会自动隐藏它，喵喵。",
            icon="cat",
        )

    def mark_ad_element(self) -> None:
        """进入广告元素点选模式。"""
        engine = self.current_engine()
        if engine is None:
            return
        try:
            engine.start_ad_picker()
        except Exception:
            return
        self.lbl_status.setText("广告标记模式：点一下要屏蔽的广告，按 Esc 取消")

    def open_ad_rules(self) -> None:
        """打开广告屏蔽规则管理。"""
        from .dialogs import AdRulesDialog

        dialog = AdRulesDialog(self.adblock, self, navigate=self.navigate)
        dialog.exec()
        self._apply_adblock_to_all()

    def _apply_adblock_to_all(self) -> None:
        for index in range(self.tabs.count()):
            engine = self.tabs.widget(index)
            if isinstance(engine, BrowserEngine):
                try:
                    engine._block_popups = bool(self.adblock.block_popups)
                    engine.set_adblock(
                        self.adblock.selectors_for(engine.current_url()),
                        block_popups=self.adblock.block_popups,
                    )
                except Exception:
                    continue

    def _on_popup_blocked(self, engine: BrowserEngine, url: str) -> None:
        self._popup_blocked_count += 1
        short = (url or "").split("?")[0][:60]
        suffix = f"：{short}" if short else ""
        self.lbl_status.setText(
            f"已拦截网页自动弹窗{suffix}（本次已拦 {self._popup_blocked_count} 个）"
        )

    # ------------------------------------------------------------------ #
    # Flash 兼容（Ruffle）
    # ------------------------------------------------------------------ #
    def _apply_ruffle_to_engine(self, engine: BrowserEngine) -> None:
        from .ruffle import PUBLIC_PATH, config_dict, supports_current_engine

        enabled = bool(self.config.get("flash_compat")) and supports_current_engine(
            self.engine_id
        )
        if not getattr(engine, "supports_ruffle", False):
            enabled = False
        try:
            import json

            engine.set_ruffle(enabled, PUBLIC_PATH, json.dumps(config_dict(), ensure_ascii=False))
        except Exception:
            pass

    def _apply_ruffle_to_all(self) -> None:
        for index in range(self.tabs.count()):
            engine = self.tabs.widget(index)
            if isinstance(engine, BrowserEngine):
                self._apply_ruffle_to_engine(engine)

    def toggle_flash_compat(self, enabled: bool) -> None:
        """开关 Ruffle（无广告 Flash 模拟器）。"""
        self.config.set("flash_compat", bool(enabled))
        self._apply_ruffle_to_all()
        if enabled:
            if not getattr(self.current_engine(), "supports_ruffle", True):
                self.lbl_status.setText("Flash 兼容需要 Edge WebView2 内核（当前是 QtWebEngine）")
            else:
                self.lbl_status.setText("已开启 Flash 兼容（Ruffle，无广告），刷新页面生效")
        else:
            self.lbl_status.setText("已关闭 Flash 兼容")
        if hasattr(self, "act_flash_compat"):
            self.act_flash_compat.blockSignals(True)
            self.act_flash_compat.setChecked(bool(enabled))
            self.act_flash_compat.blockSignals(False)

    # ------------------------------------------------------------------ #
    # 会话恢复
    # ------------------------------------------------------------------ #
    def _session_tabs(self) -> list[str]:
        urls = []
        for index in range(self.tabs.count()):
            engine = self.tabs.widget(index)
            if isinstance(engine, BrowserEngine):
                url = engine.current_url()
                if url and url != "about:blank":
                    urls.append(url)
        return urls

    def _save_session(self) -> None:
        if not bool(self.config.get("restore_session")):
            return
        try:
            self.config.set("session_tabs", self._session_tabs())
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 导航
    # ------------------------------------------------------------------ #
    def _startup_url(self) -> str:
        mode = str(self.config.get("startup_mode") or "home")
        if mode == "blank":
            return "about:blank"
        if mode == "last":
            last = str(self.config.get("last_url") or "").strip()
            if last and not last.lower().startswith(("file:", "data:")):
                return self.normalize_homepage(last)
        return self.normalize_homepage(self.config.homepage)

    @staticmethod
    def normalize_homepage(text: str) -> str:
        """把首页地址补全成合法 URL。

        用户常常直接填 ``cn.bing.com`` 这样的域名（没有协议头），
        直接交给内核会打不开，这里统一补成 ``https://``。
        """
        from .config import DEFAULT_HOMEPAGE

        value = (text or "").strip()
        if not value:
            return DEFAULT_HOMEPAGE
        lowered = value.lower()
        for prefix in (
            "http://", "https://", "file://", "about:", "data:", "chrome://",
            "edge://", "view-source:", "ftp://", "lite:",
        ):
            if lowered.startswith(prefix):
                return value
        if re.match(r"^localhost(:\d+)?([/?#].*)?$", lowered):
            return "http://" + value
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?([/?#].*)?$", value):
            return "http://" + value
        if re.match(r"^[^\s/?#]+\.[a-z]{2,}(:\d+)?([/?#].*)?$", lowered):
            return "https://" + value
        # 不是网址（可能是搜索词），交给调用方处理
        return value

    def _open_startup_page(self) -> None:
        if self.initial_url:
            target = self.normalize_url(self.initial_url, self.config.search_url) or self.initial_url
            self.new_tab(target)
            return
        # 会话恢复：先只加载第一个标签页，其余标签页延迟加载（加快启动）
        if bool(self.config.get("restore_session")):
            saved = [str(item) for item in (self.config.get("session_tabs") or []) if item]
            if saved:
                self.new_tab(saved[0])
                for url in saved[1:]:
                    engine = self.new_tab(url, switch=False, autoload=False)
                    self.tabs.setTabText(self.tabs.indexOf(engine), "待加载")
                    engine._pending_url = url
                return
        self.new_tab(self._startup_url())

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
        # 直接打开 .swf：用内置的 Ruffle 播放页，而不是让浏览器去下载它
        target = self._swf_redirect(url, engine)
        engine.load(target or url)

    def _swf_redirect(self, url: str, engine: BrowserEngine) -> Optional[str]:
        """SWF 地址改走 Ruffle 播放页（仅在 Flash 兼容开启且内核支持时）。"""
        from .ruffle import is_swf_url, swf_page_url

        if not is_swf_url(url):
            return None
        if not bool(self.config.get("flash_compat")):
            return None
        if not getattr(engine, "supports_ruffle", False):
            return None
        try:
            page = swf_page_url(url)
        except Exception:
            return None
        # 地址栏保留原始的 .swf 地址，不暴露内部播放页路径
        engine.address_override = url
        return page

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
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setVisible(True)
            self.lbl_status.setText("正在打开网页...")

    def _on_load_progress(self, engine: BrowserEngine, value: int) -> None:
        if engine is self.current_engine():
            self.progress.setValue(int(value))

    def _on_load_finished(self, engine: BrowserEngine, ok: bool) -> None:
        if engine is self.current_engine():
            self.progress.setRange(0, 100)
            self.progress.setVisible(False)
            self.lbl_status.setText("完成" if ok else "无法打开该网页")
            self._update_navigation(engine)
        if ok:
            self._record_history(engine)
        self._load_finished_extra(engine)

    def _record_history(self, engine: BrowserEngine) -> None:
        """记录浏览历史（无痕模式或关闭历史时不写入）。"""
        if self.history is None or self.incognito:
            return
        if not bool(self.config.get("history_enabled")):
            return
        url = engine.current_url()
        if not url:
            return
        if url.lower().startswith("data:") or getattr(engine, "_error_url", ""):
            # 自定义错误页 / 警告页不记入历史
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
        if engine is not self.current_engine():
            return
        override = str(getattr(engine, "address_override", "") or "")
        if override and url.lower().startswith("file:"):
            # 内置页面（错误页 / 警告页 / .swf 播放页 / 自检页）：
            # 地址栏显示用户实际打开的内容，而不是内部临时文件路径
            self.address.setText(override)
            self.address.setCursorPosition(0)
        else:
            if override and not url.lower().startswith("file:"):
                engine.address_override = ""
            if url != "about:blank" or not self.address.hasFocus():
                self.address.setText(url)
                self.address.setCursorPosition(0)
            self.config.set("last_url", url, save=False)
        self._update_navigation(engine)
        self._refresh_zoom_label()
        self._update_security_indicator()

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
        # 下载完成 → 右下角气泡提示
        self.downloads.completed.connect(self._on_download_completed)

    def _on_download_completed(self, filename: str, folder: str) -> None:
        """下载完成提示：一只路过的哈基米帮你把文件放好了。"""
        self._notify(
            "下载完成",
            f"一只路过的哈基米 🐱 帮你将「{filename}」放在了：\n{folder}\n喵喵。",
            icon="cat",
            on_click=lambda: self._open_path(folder),
        )

    def _notify(self, title: str, message: str, *, icon: str = "cat",
                on_click=None, timeout_ms: int = 5000) -> None:
        """右下角气泡提示（可手动关闭，无人操作则自动消失）。"""
        from .widgets import ToastNotification

        try:
            toast = ToastNotification(
                title, message, icon_name=icon, timeout_ms=timeout_ms,
                accent=theme.current().highlight, on_click=on_click,
            )
            toast.show()
        except Exception:
            pass

    def _open_path(self, path: str) -> None:
        """用系统默认方式打开文件或文件夹。"""
        import os

        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

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
        self.apply_engine_settings()
        self.apply_theme_from_config()

    # ------------------------------------------------------------------ #
    # 主题
    # ------------------------------------------------------------------ #
    def toggle_dark_mode(self, enabled: bool) -> None:
        """浅色 / 深色快速切换，并立即写入配置（下次启动保持选择）。"""
        mode = "dark" if enabled else "light"
        if str(self.config.get("ui_mode") or "light") == mode:
            return
        self.config.set("ui_mode", mode)
        self.apply_theme_from_config()
        self.lbl_status.setText("已切换到深色模式" if enabled else "已切换到浅色模式")

    def apply_theme_from_config(self) -> None:
        """按当前配置重新生成并应用主题（不动配置）。"""
        spec = theme.spec_for(
            str(self.config.get("ui_theme") or theme.DEFAULT_THEME),
            str(self.config.get("ui_mode") or "light"),
            str(self.config.get("ui_accent") or ""),
        )
        theme.set_current(spec)
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, spec)
        if hasattr(self, "act_dark_mode"):
            self.act_dark_mode.blockSignals(True)
            self.act_dark_mode.setChecked(spec.dark)
            self.act_dark_mode.blockSignals(False)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """主题变化后刷新自绘控件。"""
        try:
            self.caption.update()
            self.client.update()
        except Exception:
            pass
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if widget is not None:
                widget.update()
        self._update_security_indicator()

    # ------------------------------------------------------------------ #
    # 启动耗时
    # ------------------------------------------------------------------ #
    def note_startup_time(self, seconds: float) -> None:
        """记录本次启动耗时，供「设置 → 性能」显示。"""
        self.startup_seconds = float(seconds)
        try:
            self.config.set("last_startup_seconds", round(float(seconds), 3), save=False)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 引擎设置（UA / 图片 / 预读取 / 平滑滚动）
    # ------------------------------------------------------------------ #
    def apply_engine_settings(self) -> None:
        from .useragent import resolve

        user_agent = resolve(str(self.config.get("user_agent") or ""))
        load_images = self.config.get("load_images")
        load_images = True if load_images is None else bool(load_images)
        preload = bool(self.config.get("preload_links"))
        smooth = bool(self.config.get("smooth_scroll"))

        for index in range(self.tabs.count()):
            engine = self.tabs.widget(index)
            if not isinstance(engine, BrowserEngine):
                continue
            try:
                engine.set_user_agent(user_agent)
                engine.set_preferences(
                    load_images=load_images, preload=preload, smooth_scroll=smooth
                )
            except Exception:
                continue
        self._update_security_indicator()

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
        if hasattr(self, "act_dark_mode"):
            self.act_dark_mode.blockSignals(True)
            self.act_dark_mode.setChecked(str(self.config.get("ui_mode") or "light") == "dark")
            self.act_dark_mode.blockSignals(False)
        if hasattr(self, "act_flash_compat"):
            self.act_flash_compat.blockSignals(True)
            self.act_flash_compat.setChecked(bool(self.config.get("flash_compat")))
            self.act_flash_compat.blockSignals(False)
        try:
            self.adblock.block_popups = bool(self.config.get("block_popups"))
            self.adblock.save()
        except Exception:
            pass
        self._apply_adblock_to_all()
        self._apply_ruffle_to_all()

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
                url = engine.current_url()
                # 内置错误页 / 警告页的地址不要记为「上次打开的网址」
                if url and not getattr(engine, "_error_url", "") \
                        and not url.lower().startswith(("file:", "data:")):
                    self.config.set("last_url", url, save=False)
            self._save_session()
            self.config.save()
        except Exception:
            pass
        if self.performance is not None:
            try:
                self.performance.stop()
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
