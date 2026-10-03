"""插件管理界面：Chrome 扩展 + 油猴用户脚本。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .config import APP_NAME
from .extensions import ExtensionStore
from .userscripts import UserScriptStore
from .widgets import XPDialog


class ExtensionManagerDialog(XPDialog):
    """插件管理：Chrome 扩展 + 油猴脚本。"""

    def __init__(
        self,
        extensions: ExtensionStore,
        userscripts: UserScriptStore,
        parent: QWidget | None = None,
        *,
        engine_id: str = "",
        on_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent, title="插件管理", icon_name="settings")
        self.extensions = extensions
        self.userscripts = userscripts
        self.engine_id = engine_id
        self.on_changed = on_changed
        self.setMinimumSize(780, 540)

        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_extensions(), "Chrome 扩展")
        self.tabs.addTab(self._build_userscripts(), "油猴脚本")
        layout.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

        self.extensions.changed.connect(self.reload_extensions)
        self.userscripts.changed.connect(self.reload_userscripts)
        self.reload_extensions()
        self.reload_userscripts()

    # ------------------------------------------------------------------ #
    # Chrome 扩展
    # ------------------------------------------------------------------ #
    def _build_extensions(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        supported = self.engine_id == "webview2"
        tip = QLabel(
            "扩展按 Chrome 扩展规范加载（Manifest V2 / V3 已解压目录，支持 .crx / .zip 安装）。\n"
            + (
                "当前内核：Edge WebView2 —— 支持加载扩展。"
                if supported
                else "当前内核：QtWebEngine —— 不支持 Chrome 扩展，"
                     "请在「设置 → 外观 → 渲染引擎」切换为 Edge WebView2 后重启。"
            )
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #3A3A3A;")
        layout.addWidget(tip)

        self.ext_tree = QTreeWidget(page)
        self.ext_tree.setColumnCount(4)
        self.ext_tree.setHeaderLabels(["名称", "版本", "状态", "权限"])
        self.ext_tree.setRootIsDecorated(False)
        self.ext_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ext_tree.setUniformRowHeights(True)
        self.ext_tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.ext_tree.setColumnWidth(0, 200)
        self.ext_tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.ext_tree.setColumnWidth(1, 80)
        self.ext_tree.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.ext_tree.setColumnWidth(2, 80)
        self.ext_tree.header().setSectionResizeMode(3, QHeaderView.Stretch)
        self.ext_tree.itemDoubleClicked.connect(lambda *_: self._toggle_extension())
        layout.addWidget(self.ext_tree, 1)

        row = QHBoxLayout()
        for text, slot in (
            ("从文件夹安装(&D)...", self._install_extension_folder),
            ("安装 crx/zip(&C)...", self._install_extension_archive),
            ("启用/禁用(&E)", self._toggle_extension),
            ("删除(&R)", self._remove_extension),
            ("打开扩展目录(&O)", lambda: self._open(self.extensions.directory())),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def reload_extensions(self) -> None:
        self.ext_tree.clear()
        for extension in self.extensions.all():
            if extension.error:
                status = "错误"
            else:
                status = "已启用" if extension.enabled else "已禁用"
            node = QTreeWidgetItem(
                [
                    extension.display_name,
                    extension.version or "-",
                    status,
                    extension.permissions_text,
                ]
            )
            node.setData(0, Qt.UserRole, extension.id)
            node.setIcon(0, icons.icon("app", 16))
            node.setToolTip(0, str(extension.path))
            if extension.error:
                node.setToolTip(2, extension.error)
                node.setForeground(2, Qt.red)
            elif not extension.enabled:
                node.setForeground(2, Qt.gray)
            self.ext_tree.addTopLevelItem(node)

    def _current_extension_id(self) -> Optional[str]:
        node = self.ext_tree.currentItem()
        return str(node.data(0, Qt.UserRole)) if node is not None else None

    def _install_extension_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择扩展文件夹（内含 manifest.json）")
        if not folder:
            return
        self._install(Path(folder))

    def _install_extension_archive(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择扩展包", "", "Chrome 扩展 (*.crx *.zip);;所有文件 (*.*)"
        )
        if path:
            self._install(Path(path))

    def _install(self, path: Path) -> None:
        try:
            extension = self.extensions.install(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"安装失败：{exc}")
            return
        QMessageBox.information(
            self,
            APP_NAME,
            f"已安装扩展：{extension.display_name}"
            + ("\n\n重新打开标签页或重启程序后生效。" if extension else ""),
        )
        self._notify_changed()

    def _toggle_extension(self) -> None:
        ext_id = self._current_extension_id()
        if ext_id is None:
            return
        extension = self.extensions.at(ext_id)
        if extension is None:
            return
        self.extensions.set_enabled(ext_id, not extension.enabled)
        self._notify_changed()

    def _remove_extension(self) -> None:
        ext_id = self._current_extension_id()
        if ext_id is None:
            return
        extension = self.extensions.at(ext_id)
        if extension is None:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"确定要删除扩展“{extension.display_name}”吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.extensions.remove(ext_id)
            self._notify_changed()

    # ------------------------------------------------------------------ #
    # 油猴脚本
    # ------------------------------------------------------------------ #
    def _build_userscripts(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        tip = QLabel(
            "支持 Greasemonkey / Tampermonkey 的 .user.js 脚本（@match / @include / @exclude / "
            "@run-at / @grant / @require）。\n"
            "内置 GM API：GM_getValue / GM_setValue / GM_addStyle / GM_xmlhttpRequest（宿主发起，"
            "不受同源限制）/ GM_openInTab / GM_notification / GM_registerMenuCommand 等。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #3A3A3A;")
        layout.addWidget(tip)

        self.script_tree = QTreeWidget(page)
        self.script_tree.setColumnCount(4)
        self.script_tree.setHeaderLabels(["名称", "版本", "状态", "匹配站点"])
        self.script_tree.setRootIsDecorated(False)
        self.script_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.script_tree.setUniformRowHeights(True)
        self.script_tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.script_tree.setColumnWidth(0, 200)
        self.script_tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.script_tree.setColumnWidth(1, 80)
        self.script_tree.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.script_tree.setColumnWidth(2, 80)
        self.script_tree.header().setSectionResizeMode(3, QHeaderView.Stretch)
        self.script_tree.itemDoubleClicked.connect(lambda *_: self._show_script())
        layout.addWidget(self.script_tree, 1)

        row = QHBoxLayout()
        for text, slot in (
            ("安装脚本文件(&I)...", self._install_script_file),
            ("从网址安装(&U)...", self._install_script_url),
            ("启用/禁用(&E)", self._toggle_script),
            ("详情(&D)", self._show_script),
            ("删除(&R)", self._remove_script),
            ("打开脚本目录(&O)", lambda: self._open(self.userscripts.directory())),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def reload_userscripts(self) -> None:
        self.script_tree.clear()
        for script in self.userscripts.all():
            if script.error:
                status = "错误"
            else:
                status = "已启用" if script.enabled else "已禁用"
            node = QTreeWidgetItem(
                [script.display_name, script.version or "-", status, script.patterns_text]
            )
            node.setData(0, Qt.UserRole, script.id)
            node.setIcon(0, icons.icon("star", 16))
            node.setToolTip(3, "\n".join(script.patterns))
            if script.error:
                node.setToolTip(2, script.error)
                node.setForeground(2, Qt.red)
            elif not script.enabled:
                node.setForeground(2, Qt.gray)
            self.script_tree.addTopLevelItem(node)

    def _current_script_id(self) -> Optional[str]:
        node = self.script_tree.currentItem()
        return str(node.data(0, Qt.UserRole)) if node is not None else None

    def _install_script_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择用户脚本", "", "用户脚本 (*.user.js *.js);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            script = self.userscripts.install_file(Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"安装失败：{exc}")
            return
        QMessageBox.information(
            self, APP_NAME, f"已安装脚本：{script.display_name}\n匹配：{script.patterns_text}"
        )
        self._notify_changed()

    def _install_script_url(self) -> None:
        url, ok = QInputDialog.getText(
            self, "从网址安装用户脚本", "脚本地址（.user.js）："
        )
        if not ok or not url.strip():
            return
        try:
            script = self.userscripts.install_url(url.strip())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"安装失败：{exc}")
            return
        QMessageBox.information(
            self, APP_NAME, f"已安装脚本：{script.display_name}\n匹配：{script.patterns_text}"
        )
        self._notify_changed()

    def _toggle_script(self) -> None:
        script_id = self._current_script_id()
        if script_id is None:
            return
        script = self.userscripts.at(script_id)
        if script is None:
            return
        self.userscripts.set_enabled(script_id, not script.enabled)
        self._notify_changed()

    def _show_script(self) -> None:
        script_id = self._current_script_id()
        if script_id is None:
            return
        script = self.userscripts.at(script_id)
        if script is None:
            return
        grants = ", ".join(script.grants) if script.grants else "无"
        detail = (
            f"名称：{script.name}\n"
            f"版本：{script.version or '-'}\n"
            f"命名空间：{script.namespace or '-'}\n"
            f"说明：{script.description or '-'}\n"
            f"运行时机：{script.run_at}\n"
            f"申请权限：{grants}\n"
            f"匹配站点：\n  " + "\n  ".join(script.patterns or ["（无）"])
        )
        if script.excludes:
            detail += "\n排除：\n  " + "\n  ".join(script.excludes)
        if script.requires:
            detail += "\n依赖（@require）：\n  " + "\n  ".join(script.requires)
        QMessageBox.information(self, f"用户脚本 - {script.display_name}", detail)

    def _remove_script(self) -> None:
        script_id = self._current_script_id()
        if script_id is None:
            return
        script = self.userscripts.at(script_id)
        if script is None:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"确定要删除脚本“{script.display_name}”吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.userscripts.remove(script_id)
            self._notify_changed()

    # ------------------------------------------------------------------ #
    # 公共
    # ------------------------------------------------------------------ #
    def _open(self, path: Path) -> None:
        import os
        import subprocess
        import sys

        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

    def _notify_changed(self) -> None:
        if self.on_changed is not None:
            self.on_changed()
