"""下载管理器窗口与历史记录窗口（仿 XP 风格）。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .config import APP_NAME
from .downloads import DownloadItem, DownloadManager
from .history import HistoryStore
from .widgets import XPDialog


class DownloadManagerDialog(XPDialog):
    """内置下载管理器：查看进度、打开文件、更改下载目录。"""

    def __init__(
        self,
        manager: DownloadManager,
        parent: QWidget | None = None,
        folder_asker: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        super().__init__(parent, title="下载", icon_name="download")
        self.manager = manager
        self.folder_asker = folder_asker
        self.setMinimumSize(720, 460)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        # 下载目录
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("下载目录(D)："))
        self.lbl_folder = QLineEdit(str(self.manager.default_folder()))
        self.lbl_folder.setReadOnly(True)
        self.lbl_folder.setCursorPosition(0)
        self.lbl_folder.setToolTip(str(self.manager.default_folder()))
        folder_row.addWidget(self.lbl_folder, 1)
        self.btn_change_folder = QPushButton("更改(C)...")
        self.btn_open_folder = QPushButton("打开目录(O)")
        folder_row.addWidget(self.btn_change_folder)
        folder_row.addWidget(self.btn_open_folder)
        layout.addLayout(folder_row)

        # 列表
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["文件名", "大小", "状态", "开始时间"])
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
        self.btn_open = QPushButton("打开(O)")
        self.btn_folder = QPushButton("打开所在文件夹(F)")
        self.btn_cancel = QPushButton("取消下载(C)")
        self.btn_remove = QPushButton("从列表删除(D)")
        self.btn_clear = QPushButton("清除已完成")
        self.btn_close = QPushButton("关闭")
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
            chosen = QFileDialog.getExistingDirectory(self, "选择下载目录", str(self.manager.default_folder()))
        else:
            chosen = asker("请选择默认下载目录：")
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
                self, APP_NAME, "该任务正在下载，确定要取消并删除吗？",
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
        super().__init__(parent, title="历史记录", icon_name="history")
        self.store = store
        self.open_callback = open_callback
        self.setMinimumSize(760, 500)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("搜索(S)："))
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("按标题或网址筛选")
        search_row.addWidget(self.edit_search, 1)
        self.lbl_count = QLabel("")
        search_row.addWidget(self.lbl_count)
        layout.addLayout(search_row)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["时间", "标题", "网址"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tree.setColumnWidth(0, 120)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Interactive)
        self.tree.setColumnWidth(1, 280)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.btn_open = QPushButton("打开(O)")
        self.btn_remove = QPushButton("删除(D)")
        self.btn_clear = QPushButton("清空全部(L)")
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_remove)
        row.addSpacing(14)
        row.addWidget(QLabel("按时间清除："))
        self.combo_range = QComboBox()
        self.combo_range.addItem("最近 1 小时以前", ("hours", 1))
        self.combo_range.addItem("今天以前", ("today", 0))
        self.combo_range.addItem("最近 7 天以前", ("days", 7))
        self.combo_range.addItem("最近 30 天以前", ("days", 30))
        row.addWidget(self.combo_range)
        self.btn_purge = QPushButton("清除(G)")
        row.addWidget(self.btn_purge)
        row.addStretch(1)
        self.btn_close = QPushButton("关闭")
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
        groups = self.store.grouped(keyword)
        total = 0
        for label, entries in groups:
            parent = QTreeWidgetItem([label, f"（{len(entries)} 条）", ""])
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
                    child.setText(1, f"{entry.title}（访问 {entry.visit_count} 次）")
                child.setToolTip(2, entry.url)
                parent.addChild(child)
                total += 1
        self.lbl_count.setText(f"共 {total} 条记录")

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
            self, APP_NAME, "确定要清空全部历史记录吗？",
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
        QMessageBox.information(self, APP_NAME, f"已清除 {removed} 条历史记录。")
        self.reload()
