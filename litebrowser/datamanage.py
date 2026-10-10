"""数据管理：Cookie 管理器、缓存与站点数据清理、证书详情。

视觉入口整合在「设置 → 隐私与安全」与「工具 → Cookie 与缓存管理」中。
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .config import APP_NAME
from .netsec import CertificateInfo
from .performance import PerformanceManager, format_size
from .widgets import XPDialog

from .i18n import tr, trf


def _expiry_text(item: dict) -> str:
    if item.get("session"):
        return tr("会话结束时")
    expires = item.get("expires")
    try:
        expires = float(expires)
    except (TypeError, ValueError):
        return tr("未知")
    if expires <= 0:
        return tr("会话结束时")
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(expires))


class CookieManagerDialog(XPDialog):
    """Cookie 管理。"""

    def __init__(
        self,
        engine_provider: Callable[[], object],
        parent: QWidget | None = None,
        *,
        performance: Optional[PerformanceManager] = None,
    ) -> None:
        super().__init__(parent, title=tr("Cookie 与缓存管理"), icon_name="settings")
        self.engine_provider = engine_provider
        self.performance = performance
        self._cookies: list[dict] = []
        self.setMinimumSize(760, 520)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_cookies(), "Cookie")
        self.tabs.addTab(self._build_storage(), tr("缓存与站点数据"))
        layout.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(tr("关闭"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

        self.reload_cookies()

    # ------------------------------------------------------------------ #
    # Cookie
    # ------------------------------------------------------------------ #
    def _build_cookies(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        tip = QLabel(
            tr("这里列出当前内核保存的全部 Cookie。删除后立即生效，"
            "已登录的网站可能需要重新登录。")
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("筛选：")))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(tr("输入域名或名称关键字"))
        self.filter_edit.textChanged.connect(self._apply_filter)
        row.addWidget(self.filter_edit, 1)
        refresh = QPushButton(tr("刷新"))
        refresh.clicked.connect(self.reload_cookies)
        row.addWidget(refresh)
        layout.addLayout(row)

        self.cookie_tree = QTreeWidget(page)
        self.cookie_tree.setColumnCount(5)
        self.cookie_tree.setHeaderLabels([tr("域名"), tr("名称"), tr("路径"), tr("安全"), tr("过期时间")])
        self.cookie_tree.setRootIsDecorated(False)
        self.cookie_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.cookie_tree.setUniformRowHeights(True)
        header = self.cookie_tree.header()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        self.cookie_tree.setColumnWidth(0, 240)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        self.cookie_tree.setColumnWidth(1, 200)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.cookie_tree.setColumnWidth(2, 90)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.cookie_tree.setColumnWidth(3, 70)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.cookie_tree, 1)

        buttons = QHBoxLayout()
        for text, slot in (
            (tr("删除所选(&D)"), self.delete_selected),
            (tr("删除全部(&A)"), self.delete_all),
            (tr("删除会话 Cookie(&S)"), self.delete_session),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.cookie_count = QLabel(tr("共 0 条"))
        buttons.addWidget(self.cookie_count)
        layout.addLayout(buttons)
        return page

    def reload_cookies(self) -> None:
        engine = self.engine_provider() if self.engine_provider else None
        if engine is None:
            self.cookie_count.setText(tr("没有可用的标签页"))
            return
        self.cookie_count.setText(tr("正在读取…"))
        engine.list_cookies(self._on_cookies)

    def _on_cookies(self, cookies: list) -> None:
        self._cookies = list(cookies or [])
        self._apply_filter()

    def _apply_filter(self) -> None:
        keyword = (self.filter_edit.text() or "").strip().lower()
        self.cookie_tree.clear()
        shown = 0
        for item in self._cookies:
            domain = str(item.get("domain") or "")
            name = str(item.get("name") or "")
            if keyword and keyword not in domain.lower() and keyword not in name.lower():
                continue
            node = QTreeWidgetItem(
                [
                    domain,
                    name,
                    str(item.get("path") or "/"),
                    tr("是") if item.get("secure") else "",
                    _expiry_text(item),
                ]
            )
            node.setData(0, Qt.UserRole, item)
            if item.get("session"):
                node.setForeground(4, Qt.gray)
            self.cookie_tree.addTopLevelItem(node)
            shown += 1
        self.cookie_count.setText(trf('共 {0} / {1} 条', shown, len(self._cookies)))

    def _selected(self) -> list[dict]:
        result = []
        for node in self.cookie_tree.selectedItems():
            data = node.data(0, Qt.UserRole)
            if isinstance(data, dict):
                result.append(data)
        return result

    def delete_selected(self) -> None:
        engine = self.engine_provider() if self.engine_provider else None
        if engine is None:
            return
        selected = self._selected()
        if not selected:
            QMessageBox.information(self, APP_NAME, tr("请先选择要删除的 Cookie。"))
            return
        if QMessageBox.question(
            self, APP_NAME, trf('确定删除选中的 {0} 条 Cookie 吗？', len(selected)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        for item in selected:
            engine.delete_cookie(item)
        self.reload_cookies()

    def delete_all(self) -> None:
        engine = self.engine_provider() if self.engine_provider else None
        if engine is None:
            return
        if QMessageBox.question(
            self, APP_NAME, tr("确定删除全部 Cookie 吗？所有网站的登录状态都会失效。"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        engine.delete_all_cookies()
        self.reload_cookies()

    def delete_session(self) -> None:
        engine = self.engine_provider() if self.engine_provider else None
        if engine is None:
            return
        engine.delete_session_cookies()
        self.reload_cookies()

    # ------------------------------------------------------------------ #
    # 缓存与站点数据
    # ------------------------------------------------------------------ #
    def _build_storage(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(10)

        self.storage_info = QLabel(tr("正在统计…"))
        self.storage_info.setWordWrap(True)
        layout.addWidget(self.storage_info)

        self.suspend_check = QCheckBox(tr("后台标签页闲置后自动挂起（释放内存占用）"))
        layout.addWidget(self.suspend_check)

        row = QHBoxLayout()
        clear_cache = QPushButton(tr("清除缓存(&C)"))
        clear_cache.clicked.connect(self.clear_cache)
        row.addWidget(clear_cache)
        clear_site = QPushButton(tr("清除站点数据(&L)"))
        clear_site.setToolTip(tr("清理 localStorage、IndexedDB 等站点存储"))
        clear_site.clicked.connect(self.clear_site_data)
        row.addWidget(clear_site)
        clear_all = QPushButton(tr("清除全部浏览数据(&A)"))
        clear_all.clicked.connect(self.clear_everything)
        row.addWidget(clear_all)
        refresh = QPushButton(tr("重新统计"))
        refresh.clicked.connect(self.refresh_storage)
        row.addWidget(refresh)
        row.addStretch(1)
        layout.addLayout(row)

        note = QLabel(
            tr("说明：缓存用于加速网页加载，清除后首次访问网站会稍慢；"
            "站点数据包含网页的本地存储与离线数据，清除可能导致网站设置丢失。")
        )
        note.setWordWrap(True)
        note.setProperty("role", "hint")
        layout.addWidget(note)
        layout.addStretch(1)

        if self.performance is not None:
            self.suspend_check.setChecked(bool(self.performance.enabled))
            self.suspend_check.toggled.connect(self._on_suspend_toggled)
        else:
            self.suspend_check.setEnabled(False)

        self.refresh_storage()
        return page

    def _on_suspend_toggled(self, checked: bool) -> None:
        config = getattr(self.performance, "config", None) if self.performance else None
        if config is not None:
            config.set("suspend_background_tabs", bool(checked))

    def refresh_storage(self) -> None:
        if self.performance is None:
            self.storage_info.setText(tr("无法统计缓存占用。"))
            return
        stats = self.performance.stats()
        text = (
            f"磁盘缓存：<b>{format_size(stats['cache'])}</b>　　"
            f"用户配置目录：<b>{format_size(stats['profile'])}</b><br>"
            f"主进程内存：<b>{format_size(stats['memory'])}</b>　　"
            f"标签页：<b>{stats['tabs']}</b> 个（已挂起 {stats['suspended']} 个）"
        )
        self.storage_info.setText(text)

    def clear_cache(self) -> None:
        engine = self.engine_provider() if self.engine_provider else None
        if engine is None:
            QMessageBox.information(self, APP_NAME, tr("请先打开一个标签页。"))
            return
        engine.clear_cache()
        QMessageBox.information(self, APP_NAME, tr("已清除缓存。"))
        self.refresh_storage()

    def clear_site_data(self) -> None:
        engine = self.engine_provider() if self.engine_provider else None
        if engine is None:
            return
        if QMessageBox.question(
            self, APP_NAME, tr("确定清除站点数据（localStorage / IndexedDB 等）吗？"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        engine.clear_site_data()
        QMessageBox.information(self, APP_NAME, tr("已清除站点数据。"))
        self.refresh_storage()

    def clear_everything(self) -> None:
        engine = self.engine_provider() if self.engine_provider else None
        if engine is None:
            return
        if QMessageBox.question(
            self, APP_NAME,
            tr("确定清除全部浏览数据吗？\n\n包括：Cookie、缓存、站点数据。\n"
            "书签、历史记录与下载记录不会被删除。"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        engine.clear_cache()
        engine.delete_all_cookies()
        engine.clear_site_data()
        QMessageBox.information(self, APP_NAME, tr("已清除全部浏览数据。"))
        self.reload_cookies()
        self.refresh_storage()


class CertificateDialog(XPDialog):
    """HTTPS 证书问题提示。"""

    def __init__(self, info: CertificateInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent, title=tr("证书错误"), icon_name="warn")
        self.info = info
        self.allowed = False
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        headline = QLabel(tr("此网站的安全证书有问题"))
        font = headline.font()
        font.setBold(True)
        font.setPointSizeF(11.0)
        headline.setFont(font)
        headline.setProperty("role", "error")
        layout.addWidget(headline)

        warn = QLabel(
            tr("证书用于确认网站身份并加密通信。继续访问可能使您的信息被窃取或篡改。")
        )
        warn.setWordWrap(True)
        layout.addWidget(warn)

        detail = QLabel(
            f"<b>访问的网站：</b>{info.host or tr('未知')}<br>"
            f"<b>问题：</b>{info.error or tr('证书不受信任')}<br>"
            f"<b>颁发给：</b>{info.subject or tr('未知')}<br>"
            f"<b>颁发者：</b>{info.issuer or tr('未知')}<br>"
            f"<b>有效期：</b>{info.valid_from or '?'} 至 {info.valid_to or '?'}"
        )
        detail.setWordWrap(True)
        detail.setProperty("role", "card")
        detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(detail)

        row = QHBoxLayout()
        back = QPushButton(tr("返回安全页面(&B)"))
        back.setDefault(True)
        back.clicked.connect(self.reject)
        row.addWidget(back)
        row.addStretch(1)
        proceed = QPushButton(tr("继续访问（不推荐）(&P)"))
        proceed.clicked.connect(self._proceed)
        row.addWidget(proceed)
        layout.addLayout(row)

    def _proceed(self) -> None:
        if QMessageBox.warning(
            self, APP_NAME,
            tr("确定要继续访问吗？\n\n继续访问会让本次连接失去证书保护，"
            "请不要在该网站输入密码或支付信息。"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            self.allowed = True
            self.accept()


class ClearDataProgress(QWidget):
    """清理进度提示（简单封装，供设置页复用）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(tr("准备清理…"))
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        layout.addWidget(self.bar)

    def set_progress(self, value: int, text: str = "") -> None:
        self.bar.setValue(max(0, min(100, value)))
        if text:
            self.label.setText(text)
