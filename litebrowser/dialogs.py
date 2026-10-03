"""仿 XP 风格的设置 / 关于 / 书签管理对话框。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    QPushButton,
    QRadioButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
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
from .widgets import XPDialog


class PasswordDialog(XPDialog):
    """设置 / 输入加密口令。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = "设置加密口令",
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
        form.addRow("口令(P)：", self.edit_password)
        self.edit_confirm = QLineEdit()
        self.edit_confirm.setEchoMode(QLineEdit.Password)
        form.addRow("确认口令(C)：", self.edit_confirm)
        if not confirm:
            self.edit_confirm.setVisible(False)
            form.labelForField(self.edit_confirm).setVisible(False)
        layout.addLayout(form)

        hint = QLabel("口令用于保护书签、历史记录与下载记录（AES-256-GCM）。")
        hint.setStyleSheet("color: #6A6A6A;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, 0, Qt.AlignRight)
        self.edit_password.setFocus()

    def _on_ok(self) -> None:
        if not self.edit_password.text():
            QMessageBox.warning(self, APP_NAME, "口令不能为空。")
            return
        if self.edit_confirm.isVisible() and self.edit_password.text() != self.edit_confirm.text():
            QMessageBox.warning(self, APP_NAME, "两次输入的口令不一致。")
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

            return qWebEngineVersion(), "未知"
        except Exception:
            return "未知", "未知"


def engine_summary(engine_id: str) -> tuple[str, str, str]:
    """返回 (引擎名称, 内核版本, 视频解码说明)。"""
    if engine_id == "webview2":
        try:
            from . import wv2engine

            version = wv2engine.browser_version()
        except Exception:
            version = "未知"
        return (
            "Edge WebView2（Microsoft Edge 内核）",
            f"Chromium {version}",
            "H.264 / AAC / MP3 等完整编解码器，可播放哔哩哔哩等站点",
        )

    webengine_version, chromium_version = chromium_versions()
    return (
        f"QtWebEngine {webengine_version}（Qt 自带内核）",
        f"Chromium {chromium_version}",
        "仅含开源编解码器（VP8/VP9/AV1/Opus），不支持 H.264/AAC",
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
        name.setStyleSheet("color: #003C74;")
        title_box.addWidget(name)

        version = QLabel(f"版本 {APP_VERSION}  （Chromium 内核）")
        title_box.addWidget(version)
        title_box.addSpacing(2)
        author = QLabel(f"作者：{AUTHOR}")
        author_font = QFont(author.font())
        author_font.setBold(True)
        author.setFont(author_font)
        title_box.addWidget(author)
        title_box.addStretch(1)
        header.addLayout(title_box, 1)
        layout.addLayout(header)

        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {theme.BORDER};")
        layout.addWidget(line)

        info = QLabel(
            f"渲染引擎：{engine_name}\n"
            f"内核版本：{engine_version}\n"
            f"视频解码：{codec_text}\n"
            f"界面风格：Windows XP (Luna)\n"
            f"{COPYRIGHT}"
        )
        info.setStyleSheet("color: #3A3A3A;")
        layout.addWidget(info)

        tip = QLabel(
            "本程序使用 Python + PySide6 编写。\n"
            "可在「设置 → 外观 → 渲染引擎」中切换内核。"
        )
        tip.setStyleSheet("color: #6A6A6A;")
        layout.addWidget(tip)
        layout.addStretch(1)


class AboutDialog(XPDialog):
    """独立的“关于 lite browser”对话框。"""

    def __init__(self, parent: QWidget | None = None, engine_id: str = "") -> None:
        super().__init__(parent, title=f"关于 {APP_NAME}", icon_name="info")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(AboutPanel(self, engine_id))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, self)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
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
        super().__init__(parent, title="设置", icon_name="settings")
        self.config = config
        self.current_url = current_url
        self.current_engine = engine_id
        self.vault = vault
        self.history = history
        self.downloads = downloads
        self.setMinimumSize(540, 460)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_general(), "常规")
        self.tabs.addTab(self._build_appearance(), "外观")
        self.tabs.addTab(self._build_privacy(), "隐私与安全")
        self.tabs.addTab(AboutPanel(self.tabs, engine_id), "关于")
        self.tabs.setCurrentIndex(max(0, min(initial_tab, self.tabs.count() - 1)))
        layout.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_ok = QPushButton("确定")
        self.btn_ok.setDefault(True)
        self.btn_cancel = QPushButton("取消")
        self.btn_apply = QPushButton("应用(A)")
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
    def _build_general(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        home_box = QGroupBox("主页")
        home_layout = QVBoxLayout(home_box)
        home_layout.setSpacing(6)
        home_layout.addWidget(QLabel("可以指定浏览器启动时以及点击“主页”按钮时打开的页面："))

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("主页地址(H)："))
        self.edit_home = QLineEdit()
        self.edit_home.setPlaceholderText(DEFAULT_HOMEPAGE)
        url_row.addWidget(self.edit_home, 1)
        home_layout.addLayout(url_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_use_current = QPushButton("使用当前页(C)")
        self.btn_use_default = QPushButton("使用默认页(D)")
        self.btn_use_blank = QPushButton("使用空白页(B)")
        self.btn_use_current.setEnabled(bool(self.current_url))
        btn_row.addWidget(self.btn_use_current)
        btn_row.addWidget(self.btn_use_default)
        btn_row.addWidget(self.btn_use_blank)
        home_layout.addLayout(btn_row)
        layout.addWidget(home_box)

        start_box = QGroupBox("启动时")
        start_layout = QVBoxLayout(start_box)
        self.radio_home = QRadioButton("打开主页")
        self.radio_blank = QRadioButton("打开空白页")
        self.radio_last = QRadioButton("打开上次关闭时的页面")
        for radio in (self.radio_home, self.radio_blank, self.radio_last):
            start_layout.addWidget(radio)
        layout.addWidget(start_box)

        search_box = QGroupBox("地址栏搜索")
        search_layout = QFormLayout(search_box)
        self.combo_search = QComboBox()
        for engine in SEARCH_ENGINES:
            self.combo_search.addItem(engine["name"], engine["id"])
        search_layout.addRow("默认搜索引擎(S)：", self.combo_search)
        layout.addWidget(search_box)

        download_box = QGroupBox("下载")
        download_layout = QVBoxLayout(download_box)
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("下载目录(D)："))
        self.edit_download_dir = QLineEdit(str(self.config.get("download_dir") or ""))
        self.edit_download_dir.setPlaceholderText("首次下载时会提示选择")
        folder_row.addWidget(self.edit_download_dir, 1)
        self.btn_browse_dir = QPushButton("浏览(B)...")
        folder_row.addWidget(self.btn_browse_dir)
        download_layout.addLayout(folder_row)
        self.check_ask_dir = QCheckBox("每次下载都询问保存位置")
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
            self, "选择下载目录", self.edit_download_dir.text() or str(Path.home())
        )
        if folder:
            self.edit_download_dir.setText(folder)

    def _build_privacy(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        incognito_box = QGroupBox("无痕浏览")
        incognito_layout = QVBoxLayout(incognito_box)
        self.check_incognito = QCheckBox("启用无痕浏览模式（不记录历史、Cookie 与缓存）")
        incognito_layout.addWidget(self.check_incognito)
        incognito_hint = QLabel(
            "开启后：浏览历史不写入磁盘，Cookie / 缓存仅保存在内存中，\n"
            "关闭程序或切换模式后不会保留。切换模式会重新打开标签页。"
        )
        incognito_hint.setStyleSheet("color: #6A6A6A;")
        incognito_layout.addWidget(incognito_hint)
        layout.addWidget(incognito_box)

        history_box = QGroupBox("浏览历史")
        history_layout = QVBoxLayout(history_box)
        self.check_history = QCheckBox("记录浏览历史（含打开日期与时间）")
        history_layout.addWidget(self.check_history)
        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel("保留时间(K)："))
        self.combo_keep = QComboBox()
        self.combo_keep.addItem("永久保留", 0)
        self.combo_keep.addItem("30 天", 30)
        self.combo_keep.addItem("90 天", 90)
        self.combo_keep.addItem("180 天", 180)
        self.combo_keep.addItem("365 天", 365)
        keep_row.addWidget(self.combo_keep)
        keep_row.addStretch(1)
        self.btn_clear_history = QPushButton("立即清除历史记录")
        keep_row.addWidget(self.btn_clear_history)
        history_layout.addLayout(keep_row)
        layout.addWidget(history_box)

        crypto_box = QGroupBox("数据加密")
        crypto_layout = QVBoxLayout(crypto_box)
        self.lbl_crypto = QLabel("")
        self.lbl_crypto.setWordWrap(True)
        self.lbl_crypto.setStyleSheet("color: #3A3A3A;")
        crypto_layout.addWidget(self.lbl_crypto)
        crypto_row = QHBoxLayout()
        self.btn_set_password = QPushButton("设置口令(P)...")
        self.btn_clear_password = QPushButton("取消口令")
        self.btn_export_plain = QPushButton("导出明文数据(E)...")
        crypto_row.addWidget(self.btn_set_password)
        crypto_row.addWidget(self.btn_clear_password)
        crypto_row.addWidget(self.btn_export_plain)
        crypto_row.addStretch(1)
        crypto_layout.addLayout(crypto_row)
        layout.addWidget(crypto_box)
        layout.addStretch(1)

        self.btn_clear_history.clicked.connect(self._clear_history)
        self.btn_set_password.clicked.connect(self._set_password)
        self.btn_clear_password.clicked.connect(self._clear_password)
        self.btn_export_plain.clicked.connect(self._export_plain)
        self._refresh_crypto_label()
        return page

    # -- 加密相关 --------------------------------------------------------- #
    def _refresh_crypto_label(self) -> None:
        if self.vault is None:
            self.lbl_crypto.setText("（未初始化数据保险库）")
            self.btn_set_password.setEnabled(False)
            self.btn_clear_password.setEnabled(False)
            self.btn_export_plain.setEnabled(False)
            return
        text = f"加密算法：AES-256-GCM\n当前状态：{self.vault.describe()}\n"
        text += "涉及文件：data\\bookmarks.dat、history.dat、downloads.dat"
        self.lbl_crypto.setText(text)
        self.btn_clear_password.setEnabled(bool(getattr(self.vault, "has_password", lambda: False)()))

    def _set_password(self) -> None:
        if self.vault is None:
            return
        dialog = PasswordDialog(self, title="设置加密口令")
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.vault.set_password(dialog.password())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"设置口令失败：{exc}")
            return
        # 用新密钥重新加密各数据文件
        if self.history is not None:
            self.history.save()
        if self.downloads is not None:
            self.downloads.save()
        if self.parent() is not None and hasattr(self.parent(), "resave_bookmarks"):
            self.parent().resave_bookmarks()
        QMessageBox.information(self, APP_NAME, "已启用口令保护，下次启动需要输入口令。")
        self._refresh_crypto_label()

    def _clear_password(self) -> None:
        if self.vault is None:
            return
        answer = QMessageBox.question(
            self, APP_NAME, "取消口令后，主密钥将改由 Windows 账户保护，是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.vault.clear_password()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"取消失败：{exc}")
            return
        self._refresh_crypto_label()

    def _export_plain(self) -> None:
        if self.vault is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "导出明文数据到", str(Path.home()))
        if not folder:
            return
        if self.parent() is not None and hasattr(self.parent(), "export_plain_data"):
            count = self.parent().export_plain_data(Path(folder))
            QMessageBox.information(self, APP_NAME, f"已导出 {count} 个文件到：\n{folder}")
        else:
            QMessageBox.warning(self, APP_NAME, "导出失败：无法访问主窗口。")

    def _clear_history(self) -> None:
        if self.history is None:
            return
        answer = QMessageBox.question(
            self, APP_NAME, "确定要清空全部历史记录吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.history.clear()
            QMessageBox.information(self, APP_NAME, "历史记录已清空。")

    def _build_appearance(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        engine_box = QGroupBox("渲染引擎（切换后需重启程序）")
        engine_layout = QVBoxLayout(engine_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("内核(E)："))
        self.combo_engine = QComboBox()
        from .engine import ENGINE_AUTO, ENGINE_LABELS, available_engines

        self.combo_engine.addItem("自动选择（推荐）", ENGINE_AUTO)
        for item in available_engines():
            self.combo_engine.addItem(ENGINE_LABELS.get(item, item), item)
        row.addWidget(self.combo_engine, 1)
        engine_layout.addLayout(row)

        _name, _version, codec = engine_summary(self.current_engine)
        engine_note = QLabel(
            f"当前引擎：{_name}\n"
            f"视频解码：{codec}"
        )
        engine_note.setWordWrap(True)
        engine_note.setStyleSheet("color: #3A3A3A;")
        engine_layout.addWidget(engine_note)
        layout.addWidget(engine_box)

        bar_box = QGroupBox("工具栏")
        bar_layout = QVBoxLayout(bar_box)
        self.check_bookmark_bar = QCheckBox("显示书签栏")
        self.check_status_bar = QCheckBox("显示状态栏")
        bar_layout.addWidget(self.check_bookmark_bar)
        bar_layout.addWidget(self.check_status_bar)
        layout.addWidget(bar_box)

        frame_box = QGroupBox("窗口")
        frame_layout = QVBoxLayout(frame_box)
        self.check_native_frame = QCheckBox("使用系统原生窗口边框（经典 XP 外观请勿勾选）")
        frame_layout.addWidget(self.check_native_frame)
        hint = QLabel("修改窗口边框样式需要重启 lite browser 才会生效。")
        hint.setStyleSheet("color: #6A6A6A;")
        frame_layout.addWidget(hint)
        layout.addWidget(frame_box)

        zoom_box = QGroupBox("网页缩放")
        zoom_layout = QHBoxLayout(zoom_box)
        self.combo_zoom = QComboBox()
        for percent in (50, 75, 90, 100, 110, 125, 150, 175, 200):
            self.combo_zoom.addItem(f"{percent}%", percent)
        zoom_layout.addWidget(QLabel("默认缩放比例(Z)："))
        zoom_layout.addWidget(self.combo_zoom)
        zoom_layout.addStretch(1)
        layout.addWidget(zoom_box)
        layout.addStretch(1)
        return page

    # -- 取值 / 赋值 ------------------------------------------------------ #
    def _load_values(self) -> None:
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
        ):
            widget.toggled.connect(self._mark_dirty)

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
            title="编辑书签" if editing else "添加收藏",
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
        form.addRow("名称(N)：", self.edit_name)
        form.addRow("地址(U)：", self.edit_url)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, 0, Qt.AlignRight)
        self.edit_name.setFocus()

    def _on_ok(self) -> None:
        if not self.edit_url.text().strip():
            QMessageBox.warning(self, APP_NAME, "请填写书签地址。")
            return
        self.accept()

    def values(self) -> tuple[str, str]:
        return self.edit_name.text().strip(), self.edit_url.text().strip()


class BookmarkManagerDialog(XPDialog):
    """整理收藏夹。"""

    def __init__(self, store, parent: QWidget | None = None, open_callback=None) -> None:
        super().__init__(parent, title="整理收藏夹", icon_name="bookmarks")
        self.store = store
        self.open_callback = open_callback
        self.setMinimumSize(560, 400)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(QLabel("收藏夹中的书签："))

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["名称", "地址"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.setColumnWidth(0, 190)
        self.tree.itemDoubleClicked.connect(lambda *_: self._open())
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.btn_open = QPushButton("打开(O)")
        self.btn_edit = QPushButton("编辑(E)")
        self.btn_remove = QPushButton("删除(D)")
        self.btn_up = QPushButton("上移(U)")
        self.btn_down = QPushButton("下移(W)")
        for button in (self.btn_open, self.btn_edit, self.btn_remove):
            row.addWidget(button)
        row.addSpacing(16)
        row.addWidget(self.btn_up)
        row.addWidget(self.btn_down)
        row.addStretch(1)
        self.btn_close = QPushButton("关闭")
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
            f"确定要删除书签“{item['title']}”吗？",
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
