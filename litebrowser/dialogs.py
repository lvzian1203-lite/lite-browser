"""仿 XP 风格的设置 / 关于 / 书签管理对话框。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import i18n, icons, theme
from . import netsec as security
from .config import (
    APP_NAME,
    APP_VERSION,
    AUTHOR,
    BUILD_YEAR,
    COPYRIGHT,
    DEFAULT_HOMEPAGE,
    SEARCH_ENGINES,
    Config,
)
from .useragent import UA_PRESETS, default_user_agent
from .widgets import XPDialog

from .i18n import tr, trf


class PasswordDialog(XPDialog):
    """设置 / 输入加密口令。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = tr("设置加密口令"),
        confirm: bool = True,
        prompt: str = "",
    ) -> None:
        super().__init__(parent, title=title, icon_name="settings")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        if prompt:
            label = QLabel(prompt)
            label.setWordWrap(True)
            layout.addWidget(label)

        form = QFormLayout()
        form.setSpacing(8)
        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)
        form.addRow(tr("口令(P)："), self.edit_password)
        self.edit_confirm = QLineEdit()
        self.edit_confirm.setEchoMode(QLineEdit.Password)
        form.addRow(tr("确认口令(C)："), self.edit_confirm)
        if not confirm:
            self.edit_confirm.setVisible(False)
            form.labelForField(self.edit_confirm).setVisible(False)
        layout.addLayout(form)

        hint = QLabel(tr("口令用于保护书签、历史记录与下载记录（AES-256-GCM）。"))
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText(tr("确定"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("取消"))
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, 0, Qt.AlignRight)
        self.edit_password.setFocus()

    def _on_ok(self) -> None:
        if not self.edit_password.text():
            QMessageBox.warning(self, APP_NAME, tr("口令不能为空。"))
            return
        if self.edit_confirm.isVisible() and self.edit_password.text() != self.edit_confirm.text():
            QMessageBox.warning(self, APP_NAME, tr("两次输入的口令不一致。"))
            return
        self.accept()

    def password(self) -> str:
        return self.edit_password.text()


def chromium_versions() -> tuple[str, str]:
    """返回 (QtWebEngine 版本, Chromium 版本)。"""
    try:
        from PySide6.QtWebEngineCore import (  # type: ignore
            qWebEngineChromiumVersion,
            qWebEngineVersion,
        )

        return qWebEngineVersion(), qWebEngineChromiumVersion()
    except Exception:
        try:
            from PySide6.QtWebEngineCore import qWebEngineVersion  # type: ignore

            return qWebEngineVersion(), tr("未知")
        except Exception:
            return tr("未知"), tr("未知")


def engine_summary(engine_id: str) -> tuple[str, str, str]:
    """返回 (引擎名称, 内核版本, 视频解码说明)。"""
    if engine_id == "webview2":
        try:
            from . import wv2engine

            version = wv2engine.browser_version()
        except Exception:
            version = tr("未知")
        return (
            tr("Edge WebView2（Microsoft Edge 内核）"),
            f"Chromium {version}",
            tr("H.264 / AAC / MP3 等完整编解码器，可播放哔哩哔哩等站点"),
        )

    webengine_version, chromium_version = chromium_versions()
    return (
        trf('QtWebEngine {0}（Qt 自带内核）', webengine_version),
        f"Chromium {chromium_version}",
        tr("仅含开源编解码器（VP8/VP9/AV1/Opus），不支持 H.264/AAC"),
    )


# --------------------------------------------------------------------------- #
# 关于
# --------------------------------------------------------------------------- #
class AboutPanel(QWidget):
    """“关于”信息面板：名称、版本、作者。"""

    def __init__(self, parent: QWidget | None = None, engine_id: str = "") -> None:
        super().__init__(parent)
        webengine_version, chromium_version = chromium_versions()
        engine_name, engine_version, codec_text = engine_summary(engine_id or "qtwebengine")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 10)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(icons.icon("app", 48).pixmap(64, 64))
        header.addWidget(logo, 0, Qt.AlignTop)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        name = QLabel(APP_NAME)
        name_font = QFont(name.font())
        name_font.setPointSizeF(16.0)
        name_font.setBold(True)
        name.setFont(name_font)
        name.setProperty("role", "heading")
        title_box.addWidget(name)

        version = QLabel(trf('版本 {0}  （Chromium 内核）', APP_VERSION))
        title_box.addWidget(version)
        title_box.addSpacing(2)
        author = QLabel(trf('作者：{0}', AUTHOR))
        author_font = QFont(author.font())
        author_font.setBold(True)
        author.setFont(author_font)
        title_box.addWidget(author)
        title_box.addStretch(1)
        header.addLayout(title_box, 1)
        layout.addLayout(header)

        line = QLabel()
        line.setFixedHeight(1)
        line.setProperty("role", "hline")
        layout.addWidget(line)

        info = QLabel(
            f"渲染引擎：{engine_name}\n"
            f"内核版本：{engine_version}\n"
            f"视频解码：{codec_text}\n"
            f"界面风格：Windows XP (Luna)\n"
            f"{COPYRIGHT}"
        )
        info.setProperty("role", "info")
        layout.addWidget(info)

        tip = QLabel(
            tr("本程序使用 Python + PySide6 编写。\n"
            "可在「设置 → 外观 → 渲染引擎」中切换内核。")
        )
        tip.setProperty("role", "hint")
        layout.addWidget(tip)
        layout.addStretch(1)


class AboutDialog(XPDialog):
    """独立的“关于 lite browser”对话框。"""

    def __init__(self, parent: QWidget | None = None, engine_id: str = "") -> None:
        super().__init__(parent, title=trf('关于 {0}', APP_NAME), icon_name="info")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(AboutPanel(self, engine_id))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, self)
        buttons.button(QDialogButtonBox.Ok).setText(tr("确定"))
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons, 0, Qt.AlignRight)


# --------------------------------------------------------------------------- #
# 设置
# --------------------------------------------------------------------------- #
class SettingsDialog(XPDialog):
    """设置对话框：常规 / 外观 / 关于。"""

    def __init__(
        self,
        config: Config,
        parent: QWidget | None = None,
        *,
        current_url: str = "",
        initial_tab: int = 0,
        engine_id: str = "",
        vault=None,
        history=None,
        downloads=None,
    ) -> None:
        super().__init__(parent, title=tr("设置"), icon_name="settings")
        self.config = config
        self.current_url = current_url
        self.current_engine = engine_id
        self.vault = vault
        self.history = history
        self.downloads = downloads
        self._accent_color = ""
        self.setMinimumSize(600, 560)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._scroll_page(self._build_general()), tr("常规"))
        self.tabs.addTab(self._scroll_page(self._build_appearance()), tr("外观"))
        self.tabs.addTab(self._scroll_page(self._build_performance()), tr("性能"))
        self.tabs.addTab(self._scroll_page(self._build_network()), tr("网络"))
        self.tabs.addTab(self._scroll_page(self._build_engine_env()), tr("内核与环境"))
        self.tabs.addTab(self._scroll_page(self._build_privacy()), tr("隐私与安全"))
        self.tabs.addTab(AboutPanel(self.tabs, engine_id), tr("关于"))
        self.tabs.setCurrentIndex(max(0, min(initial_tab, self.tabs.count() - 1)))
        layout.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_ok = QPushButton(tr("确定"))
        self.btn_ok.setDefault(True)
        self.btn_cancel = QPushButton(tr("取消"))
        self.btn_apply = QPushButton(tr("应用(A)"))
        self.btn_apply.setEnabled(False)
        row.addWidget(self.btn_ok)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_apply)
        layout.addLayout(row)

        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self.apply)

        self._load_values()
        self._connect_dirty()

    # -- 页面 ------------------------------------------------------------- #
    def _scroll_page(self, page: QWidget) -> QWidget:
        """把设置页放进滚动区，避免内容过多时控件重叠。"""
        from PySide6.QtWidgets import QScrollArea

        area = QScrollArea(self.tabs)
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(page)
        return area

    def _build_general(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        home_box = QGroupBox(tr("主页"))
        home_layout = QVBoxLayout(home_box)
        home_layout.setSpacing(6)
        home_layout.addWidget(QLabel(tr("可以指定浏览器启动时以及点击“主页”按钮时打开的页面：")))

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel(tr("主页地址(H)：")))
        self.edit_home = QLineEdit()
        self.edit_home.setPlaceholderText(DEFAULT_HOMEPAGE)
        url_row.addWidget(self.edit_home, 1)
        home_layout.addLayout(url_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_use_current = QPushButton(tr("使用当前页(C)"))
        self.btn_use_default = QPushButton(tr("使用默认页(D)"))
        self.btn_use_blank = QPushButton(tr("使用空白页(B)"))
        self.btn_use_current.setEnabled(bool(self.current_url))
        btn_row.addWidget(self.btn_use_current)
        btn_row.addWidget(self.btn_use_default)
        btn_row.addWidget(self.btn_use_blank)
        home_layout.addLayout(btn_row)
        layout.addWidget(home_box)

        start_box = QGroupBox(tr("启动时"))
        start_layout = QVBoxLayout(start_box)
        self.radio_home = QRadioButton(tr("打开主页"))
        self.radio_blank = QRadioButton(tr("打开空白页"))
        self.radio_last = QRadioButton(tr("打开上次关闭时的页面"))
        for radio in (self.radio_home, self.radio_blank, self.radio_last):
            start_layout.addWidget(radio)
        layout.addWidget(start_box)

        search_box = QGroupBox(tr("地址栏搜索"))
        search_layout = QFormLayout(search_box)
        self.combo_search = QComboBox()
        for engine in SEARCH_ENGINES:
            self.combo_search.addItem(engine["name"], engine["id"])
        search_layout.addRow(tr("默认搜索引擎(S)："), self.combo_search)
        layout.addWidget(search_box)

        download_box = QGroupBox(tr("下载"))
        download_layout = QVBoxLayout(download_box)
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel(tr("下载目录(D)：")))
        self.edit_download_dir = QLineEdit(str(self.config.get("download_dir") or ""))
        self.edit_download_dir.setPlaceholderText(tr("首次下载时会提示选择"))
        folder_row.addWidget(self.edit_download_dir, 1)
        self.btn_browse_dir = QPushButton(tr("浏览(B)..."))
        folder_row.addWidget(self.btn_browse_dir)
        download_layout.addLayout(folder_row)
        self.check_ask_dir = QCheckBox(tr("每次下载都询问保存位置"))
        download_layout.addWidget(self.check_ask_dir)
        layout.addWidget(download_box)
        layout.addStretch(1)

        self.btn_browse_dir.clicked.connect(self._browse_download_dir)
        self.btn_use_current.clicked.connect(
            lambda: self.edit_home.setText(self.current_url)
        )
        self.btn_use_default.clicked.connect(
            lambda: self.edit_home.setText(DEFAULT_HOMEPAGE)
        )
        self.btn_use_blank.clicked.connect(lambda: self.edit_home.setText("about:blank"))
        return page

    def _browse_download_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, tr("选择下载目录"), self.edit_download_dir.text() or str(Path.home())
        )
        if folder:
            self.edit_download_dir.setText(folder)

    def _build_privacy(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        ad_box = QGroupBox(tr("广告与弹窗拦截"))
        ad_layout = QVBoxLayout(ad_box)
        self.check_block_popups = QCheckBox(tr("拦截网页自动弹出的窗口（非用户点击触发）"))
        ad_layout.addWidget(self.check_block_popups)
        rule_row = QHBoxLayout()
        self.btn_ad_rules = QPushButton(tr("广告屏蔽规则(&R)..."))
        rule_row.addWidget(self.btn_ad_rules)
        rule_row.addStretch(1)
        ad_layout.addLayout(rule_row)
        ad_hint = QLabel(
            "看到网页上的广告、浮层或弹窗广告时，按 <b>Ctrl+Shift+A</b> "
            "（或「工具 → 标记并屏蔽广告元素」）后点一下它，"
            "程序就会记下这个网站的这条规则，以后自动隐藏。\n"
            "规则按网站保存，可随时在上面按钮里查看、删除或清空。"
        )
        ad_hint.setWordWrap(True)
        ad_hint.setProperty("role", "hint")
        ad_layout.addWidget(ad_hint)
        layout.addWidget(ad_box)

        incognito_box = QGroupBox(tr("无痕浏览"))
        incognito_layout = QVBoxLayout(incognito_box)
        self.check_incognito = QCheckBox(tr("启用无痕浏览模式（不记录历史、Cookie 与缓存）"))
        incognito_layout.addWidget(self.check_incognito)
        incognito_hint = QLabel(
            tr("开启后：浏览历史不写入磁盘，Cookie / 缓存仅保存在内存中，\n"
            "关闭程序或切换模式后不会保留。切换模式会重新打开标签页。")
        )
        incognito_hint.setProperty("role", "hint")
        incognito_layout.addWidget(incognito_hint)
        layout.addWidget(incognito_box)

        history_box = QGroupBox(tr("浏览历史"))
        history_layout = QVBoxLayout(history_box)
        self.check_history = QCheckBox(tr("记录浏览历史（含打开日期与时间）"))
        history_layout.addWidget(self.check_history)
        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel(tr("保留时间(K)：")))
        self.combo_keep = QComboBox()
        self.combo_keep.addItem(tr("永久保留"), 0)
        self.combo_keep.addItem(tr("30 天"), 30)
        self.combo_keep.addItem(tr("90 天"), 90)
        self.combo_keep.addItem(tr("180 天"), 180)
        self.combo_keep.addItem(tr("365 天"), 365)
        keep_row.addWidget(self.combo_keep)
        keep_row.addStretch(1)
        self.btn_clear_history = QPushButton(tr("立即清除历史记录"))
        keep_row.addWidget(self.btn_clear_history)
        history_layout.addLayout(keep_row)
        layout.addWidget(history_box)

        crypto_box = QGroupBox(tr("数据加密"))
        crypto_layout = QVBoxLayout(crypto_box)
        self.lbl_crypto = QLabel("")
        self.lbl_crypto.setWordWrap(True)
        self.lbl_crypto.setProperty("role", "info")
        crypto_layout.addWidget(self.lbl_crypto)
        crypto_row = QHBoxLayout()
        self.btn_set_password = QPushButton(tr("设置口令(P)..."))
        self.btn_clear_password = QPushButton(tr("取消口令"))
        self.btn_export_plain = QPushButton(tr("导出明文数据(E)..."))
        crypto_row.addWidget(self.btn_set_password)
        crypto_row.addWidget(self.btn_clear_password)
        crypto_row.addWidget(self.btn_export_plain)
        crypto_row.addStretch(1)
        crypto_layout.addLayout(crypto_row)
        layout.addWidget(crypto_box)

        data_box = QGroupBox(tr("Cookie 与缓存"))
        data_layout = QVBoxLayout(data_box)
        self.lbl_data = QLabel("")
        self.lbl_data.setWordWrap(True)
        self.lbl_data.setProperty("role", "info")
        data_layout.addWidget(self.lbl_data)
        data_row = QHBoxLayout()
        self.btn_data_manager = QPushButton(tr("管理 Cookie 与缓存(M)..."))
        self.btn_clear_cache_now = QPushButton(tr("立即清除缓存"))
        self.btn_clear_cookies_now = QPushButton(tr("立即清除 Cookie"))
        data_row.addWidget(self.btn_data_manager)
        data_row.addWidget(self.btn_clear_cache_now)
        data_row.addWidget(self.btn_clear_cookies_now)
        data_row.addStretch(1)
        data_layout.addLayout(data_row)
        layout.addWidget(data_box)
        layout.addStretch(1)

        self.btn_clear_history.clicked.connect(self._clear_history)
        self.btn_ad_rules.clicked.connect(self._open_ad_rules)
        self.btn_flash_test.clicked.connect(self._open_flash_test)
        self.check_flash.toggled.connect(lambda _v: self._update_flash_label())
        self.btn_set_password.clicked.connect(self._set_password)
        self.btn_clear_password.clicked.connect(self._clear_password)
        self.btn_export_plain.clicked.connect(self._export_plain)
        self.btn_data_manager.clicked.connect(self._open_data_manager)
        self.btn_clear_cache_now.clicked.connect(self._clear_cache_now)
        self.btn_clear_cookies_now.clicked.connect(self._clear_cookies_now)
        self._refresh_crypto_label()
        QTimer.singleShot(0, self._refresh_data_label)
        return page

    # -- Cookie / 缓存 ----------------------------------------------------- #
    def _refresh_data_label(self) -> None:
        from .performance import format_size

        manager = getattr(self.parent(), "performance", None)
        if manager is None:
            self.lbl_data.setText(tr("Cookie 与缓存由内核管理，可在此查看与清理。"))
            return
        stats = manager.stats()
        self.lbl_data.setText(
            f"磁盘缓存占用：<b>{format_size(stats['cache'])}</b>；"
            f"当前标签页：{stats['tabs']} 个。\n"
            "Cookie 用于保存登录状态；缓存用于加速网页加载，两者都可以随时清理。"
        )

    def _engine(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, "current_engine"):
            try:
                return parent.current_engine()
            except Exception:
                return None
        return None

    def _open_data_manager(self) -> None:
        from .datamanage import CookieManagerDialog

        manager = getattr(self.parent(), "performance", None)
        dialog = CookieManagerDialog(self._engine, self, performance=manager)
        dialog.exec()
        self._refresh_data_label()
        self._refresh_perf()

    def _clear_cache_now(self) -> None:
        engine = self._engine()
        if engine is None:
            QMessageBox.information(self, APP_NAME, tr("请先打开一个标签页。"))
            return
        engine.clear_cache()
        self._refresh_data_label()
        QMessageBox.information(self, APP_NAME, tr("已清除磁盘缓存。"))

    def _clear_cookies_now(self) -> None:
        engine = self._engine()
        if engine is None:
            QMessageBox.information(self, APP_NAME, tr("请先打开一个标签页。"))
            return
        if QMessageBox.question(
            self, APP_NAME, tr("确定清除全部 Cookie 吗？所有网站的登录状态都会失效。"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        engine.delete_all_cookies()
        self._refresh_data_label()
        QMessageBox.information(self, APP_NAME, tr("已清除全部 Cookie。"))

    # -- 加密相关 --------------------------------------------------------- #
    def _refresh_crypto_label(self) -> None:
        if self.vault is None:
            self.lbl_crypto.setText(tr("（未初始化数据保险库）"))
            self.btn_set_password.setEnabled(False)
            self.btn_clear_password.setEnabled(False)
            self.btn_export_plain.setEnabled(False)
            return
        text = trf('加密算法：AES-256-GCM\n当前状态：{0}\n', self.vault.describe())
        text += tr("涉及文件：data\\bookmarks.dat、history.dat、downloads.dat")
        self.lbl_crypto.setText(text)
        self.btn_clear_password.setEnabled(bool(getattr(self.vault, "has_password", lambda: False)()))

    def _set_password(self) -> None:
        if self.vault is None:
            return
        dialog = PasswordDialog(self, title=tr("设置加密口令"))
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.vault.set_password(dialog.password())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, trf('设置口令失败：{0}', exc))
            return
        # 用新密钥重新加密各数据文件
        if self.history is not None:
            self.history.save()
        if self.downloads is not None:
            self.downloads.save()
        if self.parent() is not None and hasattr(self.parent(), "resave_bookmarks"):
            self.parent().resave_bookmarks()
        QMessageBox.information(self, APP_NAME, tr("已启用口令保护，下次启动需要输入口令。"))
        self._refresh_crypto_label()

    def _clear_password(self) -> None:
        if self.vault is None:
            return
        answer = QMessageBox.question(
            self, APP_NAME, tr("取消口令后，主密钥将改由 Windows 账户保护，是否继续？"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.vault.clear_password()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, trf('取消失败：{0}', exc))
            return
        self._refresh_crypto_label()

    def _export_plain(self) -> None:
        if self.vault is None:
            return
        folder = QFileDialog.getExistingDirectory(self, tr("导出明文数据到"), str(Path.home()))
        if not folder:
            return
        if self.parent() is not None and hasattr(self.parent(), "export_plain_data"):
            count = self.parent().export_plain_data(Path(folder))
            QMessageBox.information(self, APP_NAME, trf('已导出 {0} 个文件到：\n{1}', count, folder))
        else:
            QMessageBox.warning(self, APP_NAME, tr("导出失败：无法访问主窗口。"))

    def _clear_history(self) -> None:
        if self.history is None:
            return
        answer = QMessageBox.question(
            self, APP_NAME, tr("确定要清空全部历史记录吗？"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.history.clear()
            QMessageBox.information(self, APP_NAME, tr("历史记录已清空。"))

    def _build_appearance(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        theme_box = QGroupBox(tr("界面风格"))
        theme_layout = QVBoxLayout(theme_box)

        row_style = QHBoxLayout()
        row_style.addWidget(QLabel(tr("UI 风格(T)：")))
        self.combo_theme = QComboBox()
        for theme_id, name in theme.theme_names():
            self.combo_theme.addItem(tr(name), theme_id)
        row_style.addWidget(self.combo_theme, 1)
        theme_layout.addLayout(row_style)

        # 界面语言：中文（简体）/ English
        row_lang = QHBoxLayout()
        row_lang.addWidget(QLabel(tr("界面语言(L)：")))
        self.combo_language = QComboBox()
        for code, name in i18n.available_languages():
            self.combo_language.addItem(name, code)
        self.combo_language.setToolTip(tr("切换到 English 后，菜单、对话框与提示都会变成英文"))
        self.combo_language.currentIndexChanged.connect(self._on_language_changed)
        row_lang.addWidget(self.combo_language, 1)
        theme_layout.addLayout(row_lang)

        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel(tr("明暗模式(M)：")))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(tr("浅色"), "light")
        self.combo_mode.addItem(tr("深色"), "dark")
        row_mode.addWidget(self.combo_mode, 1)
        theme_layout.addLayout(row_mode)

        row_accent = QHBoxLayout()
        self.check_accent = QCheckBox(tr("自定义边框颜色"))
        row_accent.addWidget(self.check_accent)
        self.btn_accent = QPushButton(tr("选择颜色(C)..."))
        self.btn_accent.clicked.connect(self._pick_accent)
        row_accent.addWidget(self.btn_accent)
        self.accent_preview = QLabel()
        self.accent_preview.setFixedSize(40, 18)
        self.accent_preview.setFrameShape(QLabel.Box)
        row_accent.addWidget(self.accent_preview)
        self.btn_accent_reset = QPushButton(tr("用主题默认值"))
        self.btn_accent_reset.clicked.connect(self._reset_accent)
        row_accent.addWidget(self.btn_accent_reset)
        row_accent.addStretch(1)
        theme_layout.addLayout(row_accent)

        theme_hint = QLabel(
            trf('可切换 {0} 种界面风格（', len(theme.THEME_ORDER))
            + "、".join(
                # 主题名也要跟着界面语言走，否则英文界面里会夹着"经典/哈基米"等中文
                tr(name).split("（")[0].split(" (")[0]
                for _tid, name in theme.theme_names()
            )
            + tr("），并支持深色 / 浅色模式；"
            "自定义边框颜色会同时应用到标题栏与窗口边框。切换后立即生效，无需重启。")
        )
        theme_hint.setWordWrap(True)
        theme_hint.setProperty("role", "hint")
        theme_layout.addWidget(theme_hint)
        layout.addWidget(theme_box)

        engine_box = QGroupBox(tr("渲染引擎（切换后需重启程序）"))
        engine_layout = QVBoxLayout(engine_box)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("内核(E)：")))
        self.combo_engine = QComboBox()
        from .engine import ENGINE_AUTO, ENGINE_LABELS, available_engines

        self.combo_engine.addItem(tr("自动选择（推荐）"), ENGINE_AUTO)
        for item in available_engines():
            self.combo_engine.addItem(ENGINE_LABELS.get(item, item), item)
        row.addWidget(self.combo_engine, 1)
        engine_layout.addLayout(row)

        _name, _version, codec = engine_summary(self.current_engine)
        engine_note = QLabel(
            trf('当前引擎：{0}\n视频解码：{1}', _name, codec)
        )
        engine_note.setWordWrap(True)
        engine_note.setProperty("role", "info")
        engine_layout.addWidget(engine_note)
        layout.addWidget(engine_box)

        bar_box = QGroupBox(tr("工具栏"))
        bar_layout = QVBoxLayout(bar_box)
        self.check_bookmark_bar = QCheckBox(tr("显示书签栏"))
        self.check_status_bar = QCheckBox(tr("显示状态栏"))
        bar_layout.addWidget(self.check_bookmark_bar)
        bar_layout.addWidget(self.check_status_bar)
        layout.addWidget(bar_box)

        frame_box = QGroupBox(tr("窗口"))
        frame_layout = QVBoxLayout(frame_box)
        self.check_native_frame = QCheckBox(tr("使用系统原生窗口边框（经典 XP 外观请勿勾选）"))
        frame_layout.addWidget(self.check_native_frame)
        hint = QLabel(tr("修改窗口边框样式需要重启 lite browser 才会生效。"))
        hint.setProperty("role", "hint")
        frame_layout.addWidget(hint)
        layout.addWidget(frame_box)

        zoom_box = QGroupBox(tr("网页缩放"))
        zoom_layout = QHBoxLayout(zoom_box)
        self.combo_zoom = QComboBox()
        for percent in (50, 75, 90, 100, 110, 125, 150, 175, 200):
            self.combo_zoom.addItem(f"{percent}%", percent)
        zoom_layout.addWidget(QLabel(tr("默认缩放比例(Z)：")))
        zoom_layout.addWidget(self.combo_zoom)
        zoom_layout.addStretch(1)
        layout.addWidget(zoom_box)
        layout.addStretch(1)
        return page

    # -- 性能 ------------------------------------------------------------- #
    def _build_performance(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        memory_box = QGroupBox(tr("内存优化"))
        memory_layout = QVBoxLayout(memory_box)
        self.check_suspend = QCheckBox(tr("后台标签页闲置后自动挂起（释放渲染进程内存）"))
        memory_layout.addWidget(self.check_suspend)
        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel(tr("闲置时间超过(A)：")))
        self.spin_suspend = QSpinBox()
        self.spin_suspend.setRange(1, 240)
        self.spin_suspend.setSuffix(tr(" 分钟"))
        self.spin_suspend.setFixedWidth(110)
        delay_row.addWidget(self.spin_suspend)
        delay_row.addStretch(1)
        self.btn_suspend_now = QPushButton(tr("立即挂起后台标签页"))
        delay_row.addWidget(self.btn_suspend_now)
        memory_layout.addLayout(delay_row)
        memory_hint = QLabel(
            tr("挂起后内核会释放该标签页的渲染进程与内存，切回该标签页时自动恢复，"
            "页面状态（滚动位置、表单内容）不会丢失。")
        )
        memory_hint.setWordWrap(True)
        memory_hint.setProperty("role", "hint")
        memory_layout.addWidget(memory_hint)
        layout.addWidget(memory_box)

        start_box = QGroupBox(tr("启动与加载"))
        start_layout = QVBoxLayout(start_box)
        self.check_restore_session = QCheckBox(tr("启动时恢复上次关闭时的标签页"))
        self.check_preload = QCheckBox(
            tr("预读取当前网页中的链接（DNS 预解析 / 预连接，默认关闭）")
        )
        self.check_smooth_scroll = QCheckBox(tr("开启平滑滚动"))
        self.check_images = QCheckBox(tr("加载网页图片（关闭可显著提速省流量）"))
        for widget in (
            self.check_restore_session,
            self.check_preload,
            self.check_smooth_scroll,
            self.check_images,
        ):
            start_layout.addWidget(widget)

        # 明确隐私影响：这不是纯粹的"性能优化"
        preload_hint = QLabel(
            "注意：开启「预读取链接」后，浏览器会提前对页面中链接的域名发起 "
            "DNS 查询或网络连接（dns-prefetch / preconnect），"
            "因此这些域名可能在你实际点击之前就知道你访问过当前页面。"
            "该选项默认关闭。"
        )
        preload_hint.setWordWrap(True)
        preload_hint.setProperty("role", "hint")
        start_layout.addWidget(preload_hint)
        layout.addWidget(start_box)

        stats_box = QGroupBox(tr("运行状态"))
        stats_layout = QVBoxLayout(stats_box)
        self.lbl_perf = QLabel(tr("正在统计…"))
        self.lbl_perf.setWordWrap(True)
        stats_layout.addWidget(self.lbl_perf)
        stats_row = QHBoxLayout()
        self.btn_refresh_stats = QPushButton(tr("刷新统计(R)"))
        self.btn_clean_cache = QPushButton(tr("清理缓存(C)"))
        stats_row.addWidget(self.btn_refresh_stats)
        stats_row.addWidget(self.btn_clean_cache)
        stats_row.addStretch(1)
        stats_layout.addLayout(stats_row)
        layout.addWidget(stats_box)
        layout.addStretch(1)

        self.btn_suspend_now.clicked.connect(self._suspend_background_now)
        self.btn_refresh_stats.clicked.connect(self._refresh_perf)
        self.btn_clean_cache.clicked.connect(self._clean_cache)
        return page

    def _refresh_perf(self) -> None:
        from .performance import format_duration, format_size

        manager = getattr(self.parent(), "performance", None)
        startup = float(self.config.get("last_startup_seconds") or 0)
        startup_text = trf('上次启动耗时：<b>{0}</b><br>', format_duration(startup)) if startup else ""
        if manager is None:
            self.lbl_perf.setText(startup_text or tr("（性能管理器未启用）"))
            return
        stats = manager.stats()
        self.lbl_perf.setText(
            f"主进程内存：<b>{format_size(stats['memory'])}</b>（提交 "
            f"{format_size(stats['commit'])}）<br>"
            f"磁盘缓存：<b>{format_size(stats['cache'])}</b>　"
            f"用户配置：<b>{format_size(stats['profile'])}</b><br>"
            f"标签页：<b>{stats['tabs']}</b> 个，已挂起 <b>{stats['suspended']}</b> 个<br>"
            f"{startup_text}"
            f"本次运行：{format_duration(stats['uptime'])}"
        )

    def _suspend_background_now(self) -> None:
        manager = getattr(self.parent(), "performance", None)
        if manager is None:
            return
        count = manager.suspend_all_background()
        self._refresh_perf()
        QMessageBox.information(self, APP_NAME, trf('已挂起 {0} 个后台标签页，切回时自动恢复。', count))

    def _clean_cache(self) -> None:
        parent = self.parent()
        engine = None
        if parent is not None and hasattr(parent, "current_engine"):
            engine = parent.current_engine()
        if engine is None:
            QMessageBox.information(self, APP_NAME, tr("请先打开一个标签页。"))
            return
        engine.clear_cache()
        self._refresh_perf()
        QMessageBox.information(self, APP_NAME, tr("已清除磁盘缓存。"))

    # -- 网络 ------------------------------------------------------------- #
    def _build_network(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        flash_box = QGroupBox(tr("Flash 兼容（Ruffle，无广告）"))
        flash_layout = QVBoxLayout(flash_box)
        self.check_flash = QCheckBox(
            tr("启用 Flash 兼容：用小游戏/动画网站需要的 Flash 运行时")
        )
        flash_layout.addWidget(self.check_flash)
        flash_row = QHBoxLayout()
        self.btn_flash_test = QPushButton(tr("打开 Flash 小游戏测试(&T)"))
        flash_row.addWidget(self.btn_flash_test)
        flash_row.addStretch(1)
        flash_layout.addLayout(flash_row)
        self.lbl_flash = QLabel("")
        self.lbl_flash.setWordWrap(True)
        self.lbl_flash.setProperty("role", "info")
        flash_layout.addWidget(self.lbl_flash)
        flash_hint = QLabel(
            "说明：Adobe Flash Player 已在 2020 年底停止支持，Chromium 内核"
            "（含本程序使用的 WebView2）从 88 版起<b>彻底移除了 Flash 插件接口</b>，"
            "所以无法再安装官方 Flash。这里内置的是 GitHub 上开源的 "
            "<b>Ruffle</b>（Rust 写的 Flash 运行时，编译成 WebAssembly），"
            "它能在现代内核里直接运行 Flash 内容，<b>没有广告</b>，"
            "也会让网页以为本机装了 Flash。<br>"
            "遇到 Flash 网站打不开时，也可以把 .swf 地址直接粘到地址栏，"
            "程序会用内置播放器打开它。"
        )
        flash_hint.setWordWrap(True)
        flash_hint.setProperty("role", "hint")
        flash_layout.addWidget(flash_hint)
        layout.addWidget(flash_box)

        ua_box = QGroupBox(tr("User-Agent（用户代理）"))
        ua_layout = QVBoxLayout(ua_box)
        ua_row = QHBoxLayout()
        ua_row.addWidget(QLabel(tr("预设(U)：")))
        self.combo_ua = QComboBox()
        for name, value in UA_PRESETS:
            self.combo_ua.addItem(name, value)
        ua_row.addWidget(self.combo_ua, 1)
        ua_layout.addLayout(ua_row)

        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel(tr("自定义值(C)：")))
        self.edit_ua = QLineEdit()
        self.edit_ua.setPlaceholderText(tr("留空表示使用内核默认 User-Agent"))
        custom_row.addWidget(self.edit_ua, 1)
        ua_layout.addLayout(custom_row)

        self.lbl_ua_effective = QLabel("")
        self.lbl_ua_effective.setWordWrap(True)
        self.lbl_ua_effective.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_ua_effective.setProperty("role", "dim")
        ua_layout.addWidget(self.lbl_ua_effective)
        layout.addWidget(ua_box)

        cert_box = QGroupBox(tr("HTTPS 证书校验"))
        cert_layout = QVBoxLayout(cert_box)
        self.check_strict_cert = QCheckBox(tr("严格模式：证书有问题时直接拒绝，不询问"))
        self.check_cert_warn = QCheckBox(tr("证书有问题时弹出提示，由我决定是否继续"))
        cert_layout.addWidget(self.check_strict_cert)
        cert_layout.addWidget(self.check_cert_warn)
        cert_hint = QLabel(
            tr("证书校验用于确认网站身份并加密通信。关闭提示后，证书异常将按内核默认行为处理（通常直接拦截）。")
        )
        cert_hint.setWordWrap(True)
        cert_hint.setProperty("role", "hint")
        cert_layout.addWidget(cert_hint)
        layout.addWidget(cert_box)

        safe_box = QGroupBox(tr("可疑网址拦截"))
        safe_layout = QVBoxLayout(safe_box)
        self.check_block = QCheckBox(tr("启用可疑网址拦截（黑名单 + 本地启发式规则）"))
        safe_layout.addWidget(self.check_block)
        safe_row = QHBoxLayout()
        self.btn_blocklist = QPushButton(tr("管理黑名单(L)..."))
        self.btn_blocklist.clicked.connect(self._edit_blocklist)
        safe_row.addWidget(self.btn_blocklist)
        self.btn_blocklist_file = QPushButton(tr("打开名单文件(F)"))
        self.btn_blocklist_file.clicked.connect(self._open_blocklist_file)
        safe_row.addWidget(self.btn_blocklist_file)
        safe_row.addStretch(1)
        safe_layout.addLayout(safe_row)
        self.lbl_blocklist = QLabel("")
        self.lbl_blocklist.setWordWrap(True)
        self.lbl_blocklist.setProperty("role", "hint")
        safe_layout.addWidget(self.lbl_blocklist)
        # 明确能力边界：这是本地启发式规则，不是网址信誉库
        block_disclaimer = QLabel(security.DISCLAIMER)
        block_disclaimer.setWordWrap(True)
        block_disclaimer.setProperty("role", "dim")
        safe_layout.addWidget(block_disclaimer)
        layout.addWidget(safe_box)
        layout.addStretch(1)

        self.combo_ua.currentIndexChanged.connect(self._on_ua_preset)
        self.edit_ua.textChanged.connect(self._update_ua_label)
        self.check_strict_cert.toggled.connect(self._on_strict_toggled)
        return page

    def _on_ua_preset(self, _index: int = 0) -> None:
        value = self.combo_ua.currentData() or ""
        if value == "__custom__":
            self.edit_ua.setEnabled(True)
            self.edit_ua.setFocus()
        else:
            self.edit_ua.setEnabled(False)
            self.edit_ua.setText(value)
        self._update_ua_label()

    def _update_ua_label(self) -> None:
        from .useragent import is_mobile

        value = self.edit_ua.text().strip()
        if not value:
            value = default_user_agent()
            prefix = tr("当前使用内核默认 UA：")
        else:
            prefix = tr("当前将使用自定义 UA：")
        extra = tr("（移动端标识，网站会返回手机版页面）") if is_mobile(value) else ""
        self.lbl_ua_effective.setText(f"{prefix}{extra}\n{value}")

    def _on_strict_toggled(self, checked: bool) -> None:
        if checked and self.check_cert_warn.isChecked():
            self.check_cert_warn.setChecked(False)

    def _edit_blocklist(self) -> None:
        parent = self.parent()
        manager = getattr(parent, "security", None)
        if manager is None:
            QMessageBox.information(self, APP_NAME, tr("（安全管理器未启用）"))
            return
        dialog = BlocklistDialog(manager, self)
        dialog.exec()
        self._update_blocklist_label()

    def _open_blocklist_file(self) -> None:
        import os
        import subprocess

        parent = self.parent()
        manager = getattr(parent, "security", None)
        if manager is None:
            return
        path = manager.list_path
        try:
            if not path.exists():
                manager.save()
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception:
            try:
                subprocess.Popen(["notepad.exe", str(path)])
            except Exception:
                QMessageBox.information(self, APP_NAME, trf('名单文件位置：\n{0}', path))

    def _update_flash_label(self) -> None:
        """显示 Ruffle 的版本、体积与当前内核是否支持。"""
        from . import ruffle

        from .engine import capabilities_for

        info = ruffle.info()
        # 按能力表判断（P2-2）
        engine_ok = capabilities_for(self.current_engine).ruffle
        if not info["available"]:
            self.lbl_flash.setText(tr("⚠ 未找到内置的 Ruffle 文件（lib/ruffle），Flash 兼容不可用。"))
            self.check_flash.setEnabled(False)
            return
        parts = [
            trf('内置版本：{0}\u3000体积：{1} MB', info['version'], info['size_mb']),
            trf('当前内核：{0}', '支持' if engine_ok else '不支持（需要 Edge WebView2）'),
        ]
        if not engine_ok:
            parts.append(
                tr("当前使用 QtWebEngine，无法把本地 Ruffle 提供给网页；"
                "请到「外观 → 渲染引擎」切换为 Edge WebView2 后重启。")
            )
        elif not self.check_flash.isChecked():
            parts.append(tr("当前为关闭状态：遇到 Flash 网站会提示需要安装 Flash。"))
        else:
            parts.append(tr("当前为开启状态：网页里的 Flash 会自动用 Ruffle 运行。"))
        self.lbl_flash.setText("　｜　".join(parts))

    def _open_flash_test(self) -> None:
        """打开一个 4399 Flash 小游戏，方便确认 Flash 兼容是否生效。"""
        parent = self.parent()
        url = "https://www.4399.com/flash/34111.htm"
        if parent is not None and hasattr(parent, "navigate"):
            try:
                self.config.set("flash_compat", self.check_flash.isChecked())
                parent.navigate(url)
                self.accept()
                return
            except Exception:
                pass
        QMessageBox.information(
            self, APP_NAME, trf('请手动打开测试页面：\n{0}\n\n点击页面里的「开始游戏」即可。', url)
        )

    def _open_ad_rules(self) -> None:
        from .adblock import AdRuleStore

        parent = self.parent()
        store = getattr(parent, "adblock", None)
        if store is None:
            store = AdRuleStore()
        from .dialogs import AdRulesDialog

        dialog = AdRulesDialog(store, self)
        dialog.exec()

    def _update_blocklist_label(self) -> None:
        parent = self.parent()
        manager = getattr(parent, "security", None)
        if manager is None:
            self.lbl_blocklist.setText("")
            return
        self.lbl_blocklist.setText(
            f"黑名单 {len(manager.blocked_domains())} 条，白名单 "
            f"{len(manager.allowed_domains())} 条。"
            f"名单文件：{manager.list_path}"
        )

    # -- 主题 ------------------------------------------------------------- #
    def _accent(self) -> str:
        if not self.check_accent.isChecked():
            return ""
        return str(self._accent_color or "")

    def _pick_accent(self) -> None:
        initial = QColor(self._accent_color or "#0B5FE6")
        color = QColorDialog.getColor(initial, self, tr("选择边框颜色"))
        if not color.isValid():
            return
        self._accent_color = color.name()
        self.check_accent.setChecked(True)
        self._update_accent_preview()
        self._preview_theme()
        self._mark_dirty()

    def _reset_accent(self) -> None:
        self.check_accent.setChecked(False)
        self._accent_color = ""
        self._update_accent_preview()
        self._preview_theme()
        self._mark_dirty()

    def _update_accent_preview(self) -> None:
        color = self._accent() or theme.current().caption_mid
        self.accent_preview.setStyleSheet(
            f"background: {color}; border: 1px solid #808080;"
        )

    def _preview_theme(self) -> None:
        """即时预览主题（不写入配置）。"""
        from PySide6.QtWidgets import QApplication

        spec = theme.spec_for(
            str(self.combo_theme.currentData() or theme.DEFAULT_THEME),
            str(self.combo_mode.currentData() or "light"),
            self._accent(),
        )
        theme.set_current(spec)
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, spec)
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_theme"):
            try:
                parent.refresh_theme()
            except Exception:
                pass

    def reject(self) -> None:  # noqa: D102
        # 取消时还原保存的主题
        from PySide6.QtWidgets import QApplication

        spec = theme.spec_for(
            str(self.config.get("ui_theme") or theme.DEFAULT_THEME),
            str(self.config.get("ui_mode") or "light"),
            str(self.config.get("ui_accent") or ""),
        )
        theme.set_current(spec)
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, spec)
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_theme"):
            try:
                parent.refresh_theme()
            except Exception:
                pass
        super().reject()

    # -- 内核与环境 ------------------------------------------------------- #
    def _build_engine_env(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.lbl_engine_summary = QLabel(tr("正在检测…"))
        self.lbl_engine_summary.setWordWrap(True)
        font = self.lbl_engine_summary.font()
        font.setBold(True)
        self.lbl_engine_summary.setFont(font)
        layout.addWidget(self.lbl_engine_summary)

        self.engine_tree = QTreeWidget(page)
        self.engine_tree.setColumnCount(3)
        self.engine_tree.setHeaderLabels([tr("检测项目"), tr("状态"), tr("说明")])
        self.engine_tree.setRootIsDecorated(False)
        self.engine_tree.setUniformRowHeights(True)
        self.engine_tree.setMinimumHeight(220)
        header = self.engine_tree.header()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.engine_tree.setColumnWidth(0, 130)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.engine_tree.setColumnWidth(1, 66)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.engine_tree, 1)

        self.engine_progress = QProgressBar(page)
        self.engine_progress.setVisible(False)
        self.engine_progress.setTextVisible(True)
        layout.addWidget(self.engine_progress)

        row = QHBoxLayout()
        self.btn_webview_fix = QPushButton(tr("下载并安装 WebView2 运行时(&D)"))
        self.btn_webview_fix.setToolTip(
            tr("从微软官方下载 WebView2 引导安装器并运行（约 2 MB，需要联网）")
        )
        row.addWidget(self.btn_webview_fix)
        self.btn_engine_recheck = QPushButton(tr("重新检测(&R)"))
        row.addWidget(self.btn_engine_recheck)
        self.btn_webview_page = QPushButton(tr("打开官方下载页(&P)"))
        row.addWidget(self.btn_webview_page)
        row.addStretch(1)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        self.btn_engine_copy = QPushButton(tr("复制诊断报告(&C)"))
        self.btn_engine_save = QPushButton(tr("保存诊断报告(&S)..."))
        row2.addWidget(self.btn_engine_copy)
        row2.addWidget(self.btn_engine_save)
        row2.addStretch(1)
        layout.addLayout(row2)

        hint = QLabel(
            tr("说明：本程序使用 Edge WebView2 内核渲染网页。若系统缺少 WebView2 运行时，"
            "网页将无法显示，可点上面的按钮一键下载安装（安装过程由微软官方程序完成）。")
        )
        hint.setWordWrap(True)
        hint.setProperty("role", "hint")
        layout.addWidget(hint)
        layout.addStretch(1)

        self.btn_webview_fix.clicked.connect(self._download_webview2)
        self.btn_engine_recheck.clicked.connect(self._refresh_engine_checks)
        self.btn_webview_page.clicked.connect(self._open_webview2_page)
        self.btn_engine_copy.clicked.connect(self._copy_engine_report)
        self.btn_engine_save.clicked.connect(self._save_engine_report)
        self._downloader = None
        QTimer.singleShot(0, self._refresh_engine_checks)
        return page

    def _refresh_engine_checks(self) -> None:
        from .webview2doctor import BAD, OK, WARN, diagnose, summary

        checks = diagnose(self.current_engine)
        self._engine_checks = checks
        self.engine_tree.clear()
        colors = {OK: QColor("#1E7B34"), WARN: QColor("#8A6A00"), BAD: QColor("#B02A1E")}
        texts = {OK: tr("正常"), WARN: tr("注意"), BAD: tr("异常")}
        for item in checks:
            node = QTreeWidgetItem([item.title, texts.get(item.level, "?"), item.detail])
            node.setForeground(1, colors.get(item.level, QColor("#000000")))
            node.setIcon(1, icons.icon("lock" if item.ok else "warn", 14))
            if item.advice:
                node.setToolTip(2, item.advice)
                node.setText(2, item.detail + "　—　" + item.advice)
            self.engine_tree.addTopLevelItem(node)

        level, text = summary(checks)
        color = {OK: "#1E7B34", WARN: "#8A6A00", BAD: "#B02A1E"}.get(level, "#000000")
        self.lbl_engine_summary.setText(f"<span style='color:{color}'>{text}</span>")
        self.btn_webview_fix.setEnabled(level != OK)

    def _download_webview2(self) -> None:
        from .webview2doctor import RuntimeDownloader, open_download_page, run_installer

        if self._downloader is not None:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            tr("将从微软官方下载 WebView2 引导安装器（约 2 MB）并运行。\n\n"
            "安装过程由微软的安装程序完成，可能需要管理员确认。是否继续？"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return

        self.engine_progress.setVisible(True)
        self.engine_progress.setRange(0, 0)
        self.engine_progress.setFormat(tr("正在下载…"))
        self.btn_webview_fix.setEnabled(False)

        downloader = RuntimeDownloader(self)
        self._downloader = downloader

        def on_progress(received: int, total: int) -> None:
            if total > 0:
                self.engine_progress.setRange(0, 100)
                self.engine_progress.setValue(int(received * 100 / total))
                self.engine_progress.setFormat(
                    trf('正在下载… {0:.1f} / {1:.1f} MB', received / 1048576, total / 1048576)
                )
            else:
                self.engine_progress.setFormat(trf('正在下载… {0} KB', received // 1024))

        def on_finished(path: str) -> None:
            self._downloader = None
            self.engine_progress.setRange(0, 100)
            self.engine_progress.setValue(100)
            self.engine_progress.setFormat(tr("下载完成，正在启动安装程序…"))
            ok, error = run_installer(path)
            if not ok:
                self.engine_progress.setVisible(False)
                QMessageBox.warning(
                    self, APP_NAME,
                    trf('无法启动安装程序：{0}\n\n可点「打开官方下载页」手动下载。', error),
                )
                open_download_page()
            else:
                QMessageBox.information(
                    self, APP_NAME,
                    tr("已启动 WebView2 安装程序。\n\n"
                    "请按微软的安装向导完成安装（可能需要管理员确认），完成后回到这里点「重新检测」。"),
                )
            self.engine_progress.setVisible(False)
            self._refresh_engine_checks()

        def on_failed(message: str) -> None:
            self._downloader = None
            self.engine_progress.setVisible(False)
            self._refresh_engine_checks()
            answer2 = QMessageBox.question(
                self, APP_NAME,
                trf('下载失败：{0}\n\n是否改为打开官方下载页面手动安装？', message),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if answer2 == QMessageBox.Yes:
                open_download_page()

        downloader.progress.connect(on_progress)
        downloader.finished.connect(on_finished)
        downloader.failed.connect(on_failed)
        downloader.start()

    def _open_webview2_page(self) -> None:
        from .webview2doctor import open_download_page

        open_download_page()

    def _copy_engine_report(self) -> None:
        from .webview2doctor import report_text

        text = report_text(getattr(self, "_engine_checks", []))
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        QMessageBox.information(self, APP_NAME, tr("诊断报告已复制到剪贴板。"))

    def _save_engine_report(self) -> None:
        from .webview2doctor import report_text, save_report

        path, _selected = QFileDialog.getSaveFileName(
            self, tr("保存诊断报告"), str(Path.home() / tr("lite-browser-诊断报告.txt")),
            tr("文本文件 (*.txt)"),
        )
        if not path:
            return
        text = report_text(getattr(self, "_engine_checks", []))
        if save_report(text, Path(path)):
            QMessageBox.information(self, APP_NAME, trf('已保存到：\n{0}', path))
        else:
            QMessageBox.warning(self, APP_NAME, tr("保存失败，请换个位置再试。"))

    # -- 取值 / 赋值 ------------------------------------------------------ #
    def _load_values(self) -> None:
        # 载入配置时控件会发出 currentIndexChanged，那不是用户操作：
        # 用标志位挡住，否则切换语言的处理函数会在构造期间弹出模态提示框
        # （实测会让「打开设置」每次都莫名弹一次语言切换提示，甚至阻塞对话框构造）
        self._loading_values = True
        try:
            theme_index = self.combo_theme.findData(str(self.config.get("ui_theme") or theme.DEFAULT_THEME))
            language_index = self.combo_language.findData(
                i18n.normalize_language(str(self.config.get("ui_language") or ""))
            )
            self.combo_language.setCurrentIndex(max(0, language_index))
            self.combo_theme.setCurrentIndex(max(0, theme_index))
        finally:
            self._loading_values = False
        mode_index = self.combo_mode.findData(str(self.config.get("ui_mode") or "light"))
        self.combo_mode.setCurrentIndex(max(0, mode_index))
        self._accent_color = str(self.config.get("ui_accent") or "")
        self.check_accent.setChecked(bool(self._accent_color))
        self._update_accent_preview()

        self.check_suspend.setChecked(bool(self.config.get("suspend_background_tabs")))
        self.spin_suspend.setValue(int(self.config.get("suspend_after_minutes") or 10))
        self.check_restore_session.setChecked(bool(self.config.get("restore_session")))
        self.check_preload.setChecked(bool(self.config.get("preload_links")))
        self.check_smooth_scroll.setChecked(bool(self.config.get("smooth_scroll")))
        if self.config.get("load_images") is None:
            self.check_images.setChecked(True)
        else:
            self.check_images.setChecked(bool(self.config.get("load_images")))

        from .useragent import preset_index

        ua_value = str(self.config.get("user_agent") or "")
        index = preset_index(ua_value)
        self.combo_ua.setCurrentIndex(index)
        if UA_PRESETS[index][1] == "__custom__":
            self.edit_ua.setEnabled(True)
            self.edit_ua.setText(ua_value)
        else:
            self.edit_ua.setEnabled(False)
            self.edit_ua.setText(ua_value)
        self._update_ua_label()

        self.check_strict_cert.setChecked(bool(self.config.get("strict_certificate")))
        warn = self.config.get("certificate_warning")
        self.check_cert_warn.setChecked(True if warn is None else bool(warn))
        self.check_block.setChecked(bool(self.config.get("block_malicious")))
        self._update_blocklist_label()
        self.check_block_popups.setChecked(bool(self.config.get("block_popups")))
        self.check_flash.setChecked(bool(self.config.get("flash_compat")))
        self._update_flash_label()
        QTimer.singleShot(0, self._refresh_perf)

        self.edit_home.setText(str(self.config.get("homepage") or DEFAULT_HOMEPAGE))

        mode = str(self.config.get("startup_mode") or "home")
        self.radio_home.setChecked(mode == "home")
        self.radio_blank.setChecked(mode == "blank")
        self.radio_last.setChecked(mode == "last")

        index = self.combo_search.findData(str(self.config.get("search_engine") or "bing"))
        self.combo_search.setCurrentIndex(max(0, index))

        self.check_bookmark_bar.setChecked(bool(self.config.get("show_bookmark_bar")))
        self.check_status_bar.setChecked(bool(self.config.get("show_status_bar")))
        self.check_native_frame.setChecked(bool(self.config.get("native_frame")))

        zoom = int(round(float(self.config.get("zoom") or 1.0) * 100))
        zoom_index = self.combo_zoom.findData(zoom)
        if zoom_index < 0:
            self.combo_zoom.addItem(f"{zoom}%", zoom)
            zoom_index = self.combo_zoom.count() - 1
        self.combo_zoom.setCurrentIndex(zoom_index)

        engine_index = self.combo_engine.findData(str(self.config.get("engine") or "auto"))
        self.combo_engine.setCurrentIndex(max(0, engine_index))

        self.edit_download_dir.setText(str(self.config.get("download_dir") or ""))
        self.check_ask_dir.setChecked(bool(self.config.get("ask_download_dir")))

        self.check_incognito.setChecked(bool(self.config.get("incognito")))
        self.check_history.setChecked(bool(self.config.get("history_enabled")))
        keep_index = self.combo_keep.findData(int(self.config.get("history_keep_days") or 0))
        self.combo_keep.setCurrentIndex(max(0, keep_index))

    def _connect_dirty(self) -> None:
        self.edit_home.textChanged.connect(self._mark_dirty)
        self.combo_search.currentIndexChanged.connect(self._mark_dirty)
        self.combo_zoom.currentIndexChanged.connect(self._mark_dirty)
        self.combo_engine.currentIndexChanged.connect(self._mark_dirty)
        self.combo_keep.currentIndexChanged.connect(self._mark_dirty)
        self.edit_download_dir.textChanged.connect(self._mark_dirty)
        self.combo_theme.currentIndexChanged.connect(self._on_theme_changed)
        self.combo_mode.currentIndexChanged.connect(self._on_theme_changed)
        self.check_accent.toggled.connect(self._on_theme_changed)
        self.combo_ua.currentIndexChanged.connect(self._mark_dirty)
        self.edit_ua.textChanged.connect(self._mark_dirty)
        self.spin_suspend.valueChanged.connect(self._mark_dirty)
        for widget in (
            self.radio_home,
            self.radio_blank,
            self.radio_last,
            self.check_bookmark_bar,
            self.check_status_bar,
            self.check_native_frame,
            self.check_incognito,
            self.check_history,
            self.check_ask_dir,
            self.check_suspend,
            self.check_restore_session,
            self.check_preload,
            self.check_smooth_scroll,
            self.check_images,
            self.check_strict_cert,
            self.check_cert_warn,
            self.check_block,
        ):
            widget.toggled.connect(self._mark_dirty)

    def _on_theme_changed(self, *_args) -> None:
        self._update_accent_preview()
        self._preview_theme()
        self._mark_dirty()

    def _on_language_changed(self, *_args) -> None:
        """切换界面语言：立即写入配置，重启后整体生效。"""
        code = str(self.combo_language.currentData() or i18n.DEFAULT_LANGUAGE)
        current = i18n.normalize_language(str(self.config.get("ui_language") or ""))
        if getattr(self, "_loading_values", False) or code == current:
            # 载入配置时的信号、或用户选了同一个语言：什么都不做
            return
        i18n.set_language(code)          # 让随后新建的对话框立刻用新语言
        self.config.set("ui_language", code)
        self._mark_dirty()
        name = i18n.language_name(code)
        QMessageBox.information(
            self, APP_NAME,
            trf("界面语言已切换为 {0}。\n菜单与对话框将在重新启动程序后全部生效。", name),
        )

    def _mark_dirty(self, *_args) -> None:
        self.btn_apply.setEnabled(True)

    def values(self) -> dict:
        if self.radio_blank.isChecked():
            mode = "blank"
        elif self.radio_last.isChecked():
            mode = "last"
        else:
            mode = "home"

        homepage = self.edit_home.text().strip() or DEFAULT_HOMEPAGE
        # 用户常常只填 cn.bing.com 这样的域名，这里统一补全协议头再保存
        try:
            from .browser import MainWindow

            homepage = MainWindow.normalize_homepage(homepage)
        except Exception:
            pass
        ua_value = self.combo_ua.currentData() or ""
        if ua_value == "__custom__":
            ua_value = self.edit_ua.text().strip()
        return {
            "homepage": homepage,
            "startup_mode": mode,
            "search_engine": self.combo_search.currentData(),
            "engine": self.combo_engine.currentData(),
            "show_bookmark_bar": self.check_bookmark_bar.isChecked(),
            "show_status_bar": self.check_status_bar.isChecked(),
            "native_frame": self.check_native_frame.isChecked(),
            "zoom": float(self.combo_zoom.currentData()) / 100.0,
            "download_dir": self.edit_download_dir.text().strip(),
            "ask_download_dir": self.check_ask_dir.isChecked(),
            "history_enabled": self.check_history.isChecked(),
            "history_keep_days": int(self.combo_keep.currentData() or 0),
            "incognito": self.check_incognito.isChecked(),
            "ui_theme": self.combo_theme.currentData() or theme.DEFAULT_THEME,
            "ui_language": self.combo_language.currentData()
            or i18n.DEFAULT_LANGUAGE,
            "ui_mode": self.combo_mode.currentData() or "light",
            "ui_accent": self._accent(),
            "suspend_background_tabs": self.check_suspend.isChecked(),
            "suspend_after_minutes": int(self.spin_suspend.value()),
            "restore_session": self.check_restore_session.isChecked(),
            "preload_links": self.check_preload.isChecked(),
            "smooth_scroll": self.check_smooth_scroll.isChecked(),
            "load_images": self.check_images.isChecked(),
            "user_agent": ua_value,
            "strict_certificate": self.check_strict_cert.isChecked(),
            "certificate_warning": self.check_cert_warn.isChecked(),
            "block_malicious": self.check_block.isChecked(),
            "block_popups": self.check_block_popups.isChecked(),
            "flash_compat": self.check_flash.isChecked(),
        }

    def apply(self) -> None:
        self.config.update(self.values())
        self.btn_apply.setEnabled(False)
        parent = self.parent()
        if parent is not None and hasattr(parent, "on_settings_applied"):
            parent.on_settings_applied(self.config)

    def _on_ok(self) -> None:
        self.apply()
        self.accept()


# --------------------------------------------------------------------------- #
# 书签
# --------------------------------------------------------------------------- #
class BookmarkEditDialog(XPDialog):
    """添加 / 编辑单个书签。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = "",
        url: str = "",
        editing: bool = False,
    ) -> None:
        super().__init__(
            parent,
            title=tr("编辑书签") if editing else tr("添加收藏"),
            icon_name="star_add",
        )
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)
        self.edit_name = QLineEdit(title)
        self.edit_url = QLineEdit(url)
        form.addRow(tr("名称(N)："), self.edit_name)
        form.addRow(tr("地址(U)："), self.edit_url)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText(tr("确定"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("取消"))
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, 0, Qt.AlignRight)
        self.edit_name.setFocus()

    def _on_ok(self) -> None:
        if not self.edit_url.text().strip():
            QMessageBox.warning(self, APP_NAME, tr("请填写书签地址。"))
            return
        self.accept()

    def values(self) -> tuple[str, str]:
        return self.edit_name.text().strip(), self.edit_url.text().strip()


class BookmarkManagerDialog(XPDialog):
    """整理收藏夹。"""

    def __init__(self, store, parent: QWidget | None = None, open_callback=None) -> None:
        super().__init__(parent, title=tr("整理收藏夹"), icon_name="bookmarks")
        self.store = store
        self.open_callback = open_callback
        self.setMinimumSize(560, 400)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(QLabel(tr("收藏夹中的书签：")))

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([tr("名称"), tr("地址")])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.setColumnWidth(0, 190)
        self.tree.itemDoubleClicked.connect(lambda *_: self._open())
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.btn_open = QPushButton(tr("打开(O)"))
        self.btn_edit = QPushButton(tr("编辑(E)"))
        self.btn_remove = QPushButton(tr("删除(D)"))
        self.btn_up = QPushButton(tr("上移(U)"))
        self.btn_down = QPushButton(tr("下移(W)"))
        for button in (self.btn_open, self.btn_edit, self.btn_remove):
            row.addWidget(button)
        row.addSpacing(16)
        row.addWidget(self.btn_up)
        row.addWidget(self.btn_down)
        row.addStretch(1)
        self.btn_close = QPushButton(tr("关闭"))
        row.addWidget(self.btn_close)
        layout.addLayout(row)

        self.btn_open.clicked.connect(self._open)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.btn_close.clicked.connect(self.accept)
        self.store.changed.connect(self.reload)

        self.reload()

    # -- 列表 ------------------------------------------------------------- #
    def reload(self) -> None:
        selected = self.tree.currentItem()
        selected_url = selected.data(0, Qt.UserRole) if selected is not None else None
        self.tree.clear()
        for index, item in enumerate(self.store.items()):
            node = QTreeWidgetItem([item["title"], item["url"]])
            node.setData(0, Qt.UserRole, item["url"])
            node.setData(0, Qt.UserRole + 1, index)
            node.setIcon(0, icons.icon("star", 16))
            self.tree.addTopLevelItem(node)
            if selected_url and item["url"] == selected_url:
                self.tree.setCurrentItem(node)

    def _current_index(self) -> int:
        node = self.tree.currentItem()
        if node is None:
            return -1
        return int(node.data(0, Qt.UserRole + 1))

    def _open(self) -> None:
        node = self.tree.currentItem()
        if node is None:
            return
        url = node.data(0, Qt.UserRole)
        if self.open_callback is not None and url:
            self.open_callback(url)

    def _edit(self) -> None:
        index = self._current_index()
        item = self.store.at(index)
        if item is None:
            return
        dialog = BookmarkEditDialog(
            self, title=item["title"], url=item["url"], editing=True
        )
        if dialog.exec() == QDialog.Accepted:
            title, url = dialog.values()
            self.store.update(index, title, url)

    def _remove(self) -> None:
        index = self._current_index()
        item = self.store.at(index)
        if item is None:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            trf('确定要删除书签“{0}”吗？', item['title']),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.store.remove(index)

    def _move(self, delta: int) -> None:
        index = self._current_index()
        if index < 0:
            return
        new_index = self.store.move(index, delta)
        if new_index != index:
            node = self.tree.topLevelItem(new_index)
            if node is not None:
                self.tree.setCurrentItem(node)


# --------------------------------------------------------------------------- #
# 恶意网址名单
# --------------------------------------------------------------------------- #
class AdRulesDialog(XPDialog):
    """管理用户手动标记的广告屏蔽规则。"""

    def __init__(self, store, parent: QWidget | None = None, navigate=None) -> None:
        super().__init__(parent, title=tr("广告屏蔽规则"), icon_name="warn")
        self.store = store
        self.navigate = navigate
        self.setMinimumSize(640, 480)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        tip = QLabel(
            "在网页上按 <b>Ctrl+Shift+A</b>（或「工具 → 标记并屏蔽广告元素」），"
            "点一下要屏蔽的广告、弹窗或浮层，程序就会记下一条针对该网站的规则，"
            "以后打开同一网站自动隐藏它。规则按域名保存，可在这里查看与删除。"
        )
        tip.setWordWrap(True)
        tip.setProperty("role", "hint")
        layout.addWidget(tip)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([tr("网站"), tr("选择器"), tr("添加时间"), tr("备注")])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        self.tree.setColumnWidth(0, 150)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.tree.setColumnWidth(2, 130)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        self.tree.setColumnWidth(3, 100)
        layout.addWidget(self.tree, 1)

        self.box_popups = QCheckBox(tr("拦截网页自动弹出的窗口（非用户点击触发）"))
        self.box_popups.setChecked(bool(store.block_popups))
        self.box_popups.toggled.connect(self._on_popup_toggled)
        layout.addWidget(self.box_popups)

        row = QHBoxLayout()
        self.btn_goto = QPushButton(tr("打开该网站(&O)"))
        self.btn_goto.clicked.connect(self._open_selected_site)
        row.addWidget(self.btn_goto)
        self.btn_remove = QPushButton(tr("删除所选(&D)"))
        self.btn_remove.clicked.connect(self._remove_selected)
        row.addWidget(self.btn_remove)
        self.btn_clear = QPushButton(tr("清空全部(&C)"))
        self.btn_clear.clicked.connect(self._clear_all)
        row.addWidget(self.btn_clear)
        row.addStretch(1)
        self.btn_close = QPushButton(tr("关闭"))
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close)
        layout.addLayout(row)

        self.lbl_count = QLabel("")
        self.lbl_count.setProperty("role", "dim")
        layout.addWidget(self.lbl_count)

        self.reload()

    # ------------------------------------------------------------------ #
    def reload(self) -> None:
        self.tree.clear()
        for rule in self.store.rules:
            node = QTreeWidgetItem([rule.domain, rule.selector, rule.time_text, rule.note])
            node.setData(0, Qt.UserRole, rule)
            node.setToolTip(1, rule.selector)
            self.tree.addTopLevelItem(node)
        count = len(self.store.rules)
        domains = len(self.store.domains())
        self.lbl_count.setText(trf('共 {0} 条规则，覆盖 {1} 个网站', count, domains))

    def _selected_rules(self) -> list:
        rules = []
        for node in self.tree.selectedItems():
            rule = node.data(0, Qt.UserRole)
            if rule is not None:
                rules.append(rule)
        return rules

    def _on_popup_toggled(self, enabled: bool) -> None:
        self.store.set_block_popups(bool(enabled))

    def _open_selected_site(self) -> None:
        rules = self._selected_rules()
        if not rules or self.navigate is None:
            return
        self.navigate(f"https://{rules[0].domain}/")
        self.accept()

    def _remove_selected(self) -> None:
        rules = self._selected_rules()
        if not rules:
            return
        for rule in rules:
            self.store.remove(rule)
        self.reload()

    def _clear_all(self) -> None:
        if not self.store.rules:
            return
        answer = QMessageBox.question(
            self, APP_NAME, trf('确定要清空全部 {0} 条广告屏蔽规则吗？', len(self.store.rules)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.store.clear()
            self.reload()


class BlocklistDialog(XPDialog):
    """管理可疑网址的黑名单 / 白名单（本地启发式规则的基础名单）。"""

    def __init__(self, manager, parent: QWidget | None = None) -> None:
        super().__init__(parent, title=tr("可疑网址名单"), icon_name="warn")
        self.manager = manager
        self.setMinimumSize(520, 460)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        tip = QLabel(
            tr("命中黑名单的网址会被直接拦截并显示警告页；"
            "白名单中的域名永远不会被拦截（包括启发式规则）。\n"
            "规则支持 example.com 与 *.example.com 两种写法。")
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        lists = QHBoxLayout()

        blocked_box = QGroupBox(tr("黑名单（拦截）"))
        blocked_layout = QVBoxLayout(blocked_box)
        self.blocked_tree = QTreeWidget()
        self.blocked_tree.setHeaderLabels([tr("域名")])
        self.blocked_tree.setRootIsDecorated(False)
        blocked_layout.addWidget(self.blocked_tree)
        blocked_row = QHBoxLayout()
        add_blocked = QPushButton(tr("添加(&A)..."))
        add_blocked.clicked.connect(lambda: self._add(True))
        remove_blocked = QPushButton(tr("移除(&R)"))
        remove_blocked.clicked.connect(lambda: self._remove(True))
        blocked_row.addWidget(add_blocked)
        blocked_row.addWidget(remove_blocked)
        blocked_row.addStretch(1)
        blocked_layout.addLayout(blocked_row)
        lists.addWidget(blocked_box)

        allowed_box = QGroupBox(tr("白名单（放行）"))
        allowed_layout = QVBoxLayout(allowed_box)
        self.allowed_tree = QTreeWidget()
        self.allowed_tree.setHeaderLabels([tr("域名")])
        self.allowed_tree.setRootIsDecorated(False)
        allowed_layout.addWidget(self.allowed_tree)
        allowed_row = QHBoxLayout()
        add_allowed = QPushButton(tr("添加(&D)..."))
        add_allowed.clicked.connect(lambda: self._add(False))
        remove_allowed = QPushButton(tr("移除(&M)"))
        remove_allowed.clicked.connect(lambda: self._remove(False))
        allowed_row.addWidget(add_allowed)
        allowed_row.addWidget(remove_allowed)
        allowed_row.addStretch(1)
        allowed_layout.addLayout(allowed_row)
        lists.addWidget(allowed_box)

        layout.addLayout(lists, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(tr("关闭"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

        self._reload()

    def _reload(self) -> None:
        self.blocked_tree.clear()
        for domain in self.manager.blocked_domains():
            self.blocked_tree.addTopLevelItem(QTreeWidgetItem([domain]))
        self.allowed_tree.clear()
        for domain in self.manager.allowed_domains():
            self.allowed_tree.addTopLevelItem(QTreeWidgetItem([domain]))

    def _add(self, blocked: bool) -> None:
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(
            self, tr("添加域名"), tr("域名（例如 bad-site.com 或 *.bad-site.com）：")
        )
        if not ok or not text.strip():
            return
        for part in text.replace(",", " ").split():
            if blocked:
                self.manager.add_blocked(part)
            else:
                self.manager.add_allowed(part)
        self._reload()

    def _remove(self, blocked: bool) -> None:
        tree = self.blocked_tree if blocked else self.allowed_tree
        node = tree.currentItem()
        if node is None:
            return
        domain = node.text(0)
        if blocked:
            self.manager.remove_blocked(domain)
        else:
            self.manager.remove_allowed(domain)
        self._reload()
