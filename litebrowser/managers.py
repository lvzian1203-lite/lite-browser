"""下载管理器窗口与历史记录窗口（仿 XP 风格）。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .config import APP_NAME
from .downloads import DownloadItem, DownloadManager
from .history import HistoryStore

#: 搜索关键字高亮用的“荧光笔”配色（浅色/深色下都清晰）
_HIGHLIGHT_BG = QColor("#FFE066")
_HIGHLIGHT_FG = QColor("#3A2A00")


class HighlightDelegate(QStyledItemDelegate):
    """在列表项里高亮显示命中的搜索关键字。"""

    def __init__(self, parent: QWidget | None = None, columns: tuple[int, ...] = (1, 2)) -> None:
        super().__init__(parent)
        self._keyword = ""
        self._columns = columns

    def set_keyword(self, text: str) -> None:
        self._keyword = (text or "").strip()

    def paint(self, painter, option, index) -> None:  # noqa: D102
        text = index.data(Qt.DisplayRole)
        keyword = self._keyword
        if (
            not keyword
            or index.column() not in self._columns
            or not isinstance(text, str)
            or not text
        ):
            super().paint(painter, option, index)
            return

        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.text = ""            # 背景交给样式画，文字自己画
        widget = style_option.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, style_option, painter, widget)

        rect = style.subElementRect(QStyle.SE_ItemViewItemText, style_option, widget)
        if not rect.isValid():
            return

        painter.save()
        painter.setClipRect(rect)
        selected = bool(style_option.state & QStyle.State_Selected)
        font = QFont(style_option.font)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        shown = metrics.elidedText(text, Qt.ElideRight, rect.width())
        base_color = (
            style_option.palette.highlightedText().color()
            if selected
            else style_option.palette.text().color()
        )

        lowered = shown.lower()
        needle = keyword.lower()
        x = rect.left()
        cursor = 0
        baseline = rect.top() + (rect.height() + metrics.ascent() - metrics.descent()) // 2
        while cursor < len(shown):
            found = lowered.find(needle, cursor)
            if found < 0 or not needle:
                break
            if found > cursor:
                piece = shown[cursor:found]
                painter.setPen(base_color)
                painter.drawText(x, baseline, piece)
                x += metrics.horizontalAdvance(piece)
            matched = shown[found:found + len(needle)]
            width = metrics.horizontalAdvance(matched)
            painter.fillRect(QRect(x - 1, rect.top() + 1, width + 2, rect.height() - 2),
                             _HIGHLIGHT_BG)
            painter.setPen(_HIGHLIGHT_FG)
            painter.drawText(x, baseline, matched)
            x += width
            cursor = found + len(needle)

        if cursor < len(shown):
            painter.setPen(base_color)
            painter.drawText(x, baseline, shown[cursor:])
        painter.restore()
from .widgets import XPDialog

from .i18n import tr, trf


class DownloadManagerDialog(XPDialog):
    """内置下载管理器：查看进度、打开文件、更改下载目录。"""

    def __init__(
        self,
        manager: DownloadManager,
        parent: QWidget | None = None,
        folder_asker: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        super().__init__(parent, title=tr("下载"), icon_name="download")
        self.manager = manager
        self.folder_asker = folder_asker
        self.setMinimumSize(720, 460)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        # 下载目录
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel(tr("下载目录(D)：")))
        self.lbl_folder = QLineEdit(str(self.manager.default_folder()))
        self.lbl_folder.setReadOnly(True)
        self.lbl_folder.setCursorPosition(0)
        self.lbl_folder.setToolTip(str(self.manager.default_folder()))
        folder_row.addWidget(self.lbl_folder, 1)
        self.btn_change_folder = QPushButton(tr("更改(C)..."))
        self.btn_open_folder = QPushButton(tr("打开目录(O)"))
        folder_row.addWidget(self.btn_change_folder)
        folder_row.addWidget(self.btn_open_folder)
        layout.addLayout(folder_row)

        # 列表
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([tr("文件名"), tr("大小"), tr("状态"), tr("开始时间")])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 170), (2, 130), (3, 150)):
            self.tree.header().setSectionResizeMode(column, QHeaderView.Fixed)
            self.tree.setColumnWidth(column, width)
        self.tree.itemDoubleClicked.connect(lambda *_: self._open())
        layout.addWidget(self.tree, 1)

        # 按钮
        row = QHBoxLayout()
        self.btn_open = QPushButton(tr("打开(O)"))
        self.btn_folder = QPushButton(tr("打开所在文件夹(F)"))
        self.btn_cancel = QPushButton(tr("取消下载(C)"))
        self.btn_remove = QPushButton(tr("从列表删除(D)"))
        self.btn_clear = QPushButton(tr("清除已完成"))
        self.btn_close = QPushButton(tr("关闭"))
        for button in (self.btn_open, self.btn_folder, self.btn_cancel,
                       self.btn_remove, self.btn_clear):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.btn_close)
        layout.addLayout(row)

        self.btn_change_folder.clicked.connect(self._change_folder)
        self.btn_open_folder.clicked.connect(self._open_default_folder)
        self.btn_open.clicked.connect(self._open)
        self.btn_folder.clicked.connect(self._open_item_folder)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_clear.clicked.connect(self.manager.clear_finished)
        self.btn_close.clicked.connect(self.accept)

        self.manager.changed.connect(self.reload)
        self.manager.updated.connect(lambda _item: self.reload())
        self.reload()

    # -- 列表 ------------------------------------------------------------- #
    def reload(self) -> None:
        selected = self._current_id()
        self.tree.clear()
        for item in self.manager.items():
            node = QTreeWidgetItem(
                [
                    item.filename,
                    item.size_text,
                    f"{item.state_text}" + (f"  {item.progress}%" if item.state == "running" else ""),
                    item.started_text,
                ]
            )
            node.setData(0, Qt.UserRole, item.id)
            node.setToolTip(0, str(item.path))
            if item.state == "done":
                node.setIcon(0, icons.icon("download", 16))
            elif item.state == "failed":
                node.setIcon(0, icons.icon("stop", 16))
            else:
                node.setIcon(0, icons.icon("go", 16))
            if item.error:
                node.setToolTip(2, item.error)
            self.tree.addTopLevelItem(node)
            if selected is not None and item.id == selected:
                self.tree.setCurrentItem(node)
        self.lbl_folder.setText(str(self.manager.default_folder()))
        self.lbl_folder.setCursorPosition(0)
        self.lbl_folder.setToolTip(str(self.manager.default_folder()))

    def _current_id(self) -> Optional[int]:
        node = self.tree.currentItem()
        return int(node.data(0, Qt.UserRole)) if node is not None else None

    def _current_item(self) -> Optional[DownloadItem]:
        target = self._current_id()
        if target is None:
            return None
        for item in self.manager.items():
            if item.id == target:
                return item
        return None

    # -- 操作 ------------------------------------------------------------- #
    def _change_folder(self) -> None:
        asker = self.folder_asker
        if asker is None:
            chosen = QFileDialog.getExistingDirectory(self, tr("选择下载目录"), str(self.manager.default_folder()))
        else:
            chosen = asker(tr("请选择默认下载目录："))
        if chosen:
            self.manager.set_default_folder(chosen)
            self.lbl_folder.setText(chosen)

    def _open_default_folder(self) -> None:
        folder = self.manager.default_folder()
        try:
            import os

            os.startfile(str(folder))  # type: ignore[attr-defined]
        except Exception:
            pass

    def _open(self) -> None:
        item = self._current_item()
        if item is not None:
            self.manager.open_file(item)

    def _open_item_folder(self) -> None:
        item = self._current_item()
        if item is not None:
            self.manager.open_folder(item)

    def _cancel(self) -> None:
        item = self._current_item()
        if item is not None:
            self.manager.cancel(item)

    def _remove(self) -> None:
        item = self._current_item()
        if item is None:
            return
        if item.state == "running":
            answer = QMessageBox.question(
                self, APP_NAME, tr("该任务正在下载，确定要取消并删除吗？"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            self.manager.cancel(item)
        self.manager.remove(item)


class HistoryDialog(XPDialog):
    """历史记录：按日期分组，标注每个页面打开的日期与时间。"""

    def __init__(
        self,
        store: HistoryStore,
        parent: QWidget | None = None,
        open_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent, title=tr("历史记录"), icon_name="history")
        self.store = store
        self.open_callback = open_callback
        self.setMinimumSize(760, 500)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(tr("搜索(S)：")))
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText(tr("按标题或网址筛选"))
        search_row.addWidget(self.edit_search, 1)
        self.lbl_count = QLabel("")
        search_row.addWidget(self.lbl_count)
        layout.addLayout(search_row)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([tr("时间"), tr("标题"), tr("网址")])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tree.setColumnWidth(0, 120)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Interactive)
        self.tree.setColumnWidth(1, 280)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        # 搜索关键字在标题与网址列中高亮显示
        self._highlight = HighlightDelegate(self.tree, columns=(1, 2))
        self.tree.setItemDelegateForColumn(1, self._highlight)
        self.tree.setItemDelegateForColumn(2, self._highlight)
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.btn_open = QPushButton(tr("打开(O)"))
        self.btn_remove = QPushButton(tr("删除(D)"))
        self.btn_clear = QPushButton(tr("清空全部(L)"))
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_remove)
        row.addSpacing(14)
        row.addWidget(QLabel(tr("按时间清除：")))
        self.combo_range = QComboBox()
        self.combo_range.addItem(tr("最近 1 小时以前"), ("hours", 1))
        self.combo_range.addItem(tr("今天以前"), ("today", 0))
        self.combo_range.addItem(tr("最近 7 天以前"), ("days", 7))
        self.combo_range.addItem(tr("最近 30 天以前"), ("days", 30))
        row.addWidget(self.combo_range)
        self.btn_purge = QPushButton(tr("清除(G)"))
        row.addWidget(self.btn_purge)
        row.addStretch(1)
        self.btn_close = QPushButton(tr("关闭"))
        row.addWidget(self.btn_close)
        layout.addLayout(row)

        self.edit_search.textChanged.connect(lambda _text: self.reload())
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_purge.clicked.connect(self._purge)
        self.btn_close.clicked.connect(self.accept)
        self.store.changed.connect(self.reload)

        self.reload()

    # -- 列表 ------------------------------------------------------------- #
    def reload(self) -> None:
        self.tree.clear()
        keyword = self.edit_search.text()
        self._highlight.set_keyword(keyword)
        groups = self.store.grouped(keyword)
        total = 0
        for label, entries in groups:
            parent = QTreeWidgetItem([label, trf('（{0} 条）', len(entries)), ""])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setIcon(0, icons.icon("folder", 16))
            self.tree.addTopLevelItem(parent)
            parent.setFirstColumnSpanned(True)
            parent.setExpanded(True)
            for entry in entries:
                child = QTreeWidgetItem([entry.time_text, entry.title, entry.url])
                child.setData(0, Qt.UserRole, entry.url)
                if entry.visit_count > 1:
                    child.setText(1, trf('{0}（访问 {1} 次）', entry.title, entry.visit_count))
                child.setToolTip(2, entry.url)
                parent.addChild(child)
                total += 1
        self.lbl_count.setText(
            trf('共 {0} 条记录', total) + (tr("（已筛选，高亮显示匹配内容）") if keyword.strip() else "")
        )
        self.tree.viewport().update()

    def _selected_urls(self) -> list[str]:
        urls: list[str] = []
        for node in self.tree.selectedItems():
            url = node.data(0, Qt.UserRole)
            if url:
                urls.append(str(url))
        return urls

    def _on_double_click(self, node: QTreeWidgetItem, _column: int) -> None:
        url = node.data(0, Qt.UserRole)
        if url and self.open_callback is not None:
            self.open_callback(str(url))
            self.accept()

    def _open_selected(self) -> None:
        urls = self._selected_urls()
        if urls and self.open_callback is not None:
            self.open_callback(urls[0])
            self.accept()

    def _remove_selected(self) -> None:
        urls = self._selected_urls()
        if not urls:
            return
        removed = self.store.remove_urls(urls)
        if removed:
            self.reload()

    def _clear_all(self) -> None:
        if not len(self.store):
            return
        answer = QMessageBox.question(
            self, APP_NAME, tr("确定要清空全部历史记录吗？"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.store.clear()
            self.reload()

    def _purge(self) -> None:
        unit, value = self.combo_range.currentData()
        if unit == "hours":
            limit = time.time() - value * 3600
        elif unit == "today":
            from datetime import datetime

            limit = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        else:
            limit = time.time() - value * 86400
        removed = self.store.purge_before(limit)
        QMessageBox.information(self, APP_NAME, trf('已清除 {0} 条历史记录。', removed))
        self.reload()
