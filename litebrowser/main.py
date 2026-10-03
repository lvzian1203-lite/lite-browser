"""程序入口。"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QStyleFactory

from . import icons, theme
from .bookmarks import BookmarkStore
from .browser import MainWindow
from .config import APP_NAME, APP_VERSION, ORG_NAME, Config, data_dir
from .crypto import CRYPTO_AVAILABLE, DataVault
from .dialogs import PasswordDialog
from .downloads import DownloadManager
from .engine import prepare_engine, resolve_engine
from .extensions import ExtensionStore
from .history import HistoryStore
from .userscripts import UserScriptStore


def _prepare_environment(argv: list[str]) -> None:
    """处理命令行参数与 Chromium 环境变量。"""
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")

    if "--no-sandbox" in argv:
        argv.remove("--no-sandbox")
        flags = (flags + " --no-sandbox").strip()
    if "--disable-gpu" in argv:
        argv.remove("--disable-gpu")
        flags = (flags + " --disable-gpu --disable-software-rasterizer").strip()

    if flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags

    # 让任务栏使用本程序自己的图标与名称
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"{ORG_NAME}.{APP_NAME}.{APP_VERSION}"
            )
        except Exception:
            pass


def _take_start_url(argv: list[str]) -> str | None:
    """取出命令行中要打开的网址（例如把 lite browser 设为默认浏览器时）。"""
    for index, item in enumerate(argv):
        if index == 0 or item.startswith("-"):
            continue
        if "://" in item or item.startswith(("www.", "about:")) or "." in item:
            del argv[index]
            return item
    return None


def _open_vault() -> DataVault | None:
    """初始化数据保险库；必要时提示输入口令。返回 None 表示本次不保存数据。"""
    vault = DataVault(data_dir())

    if not vault.available:
        QMessageBox.information(
            None,
            APP_NAME,
            "未安装 cryptography 加密库，书签 / 历史 / 下载记录将以明文保存。\n"
            "如需加密保护，请执行：pip install cryptography",
        )
        return vault

    if vault.initialize():
        return vault

    # 已有口令保护，需要用户输入
    for _attempt in range(3):
        dialog = PasswordDialog(
            None,
            title="输入加密口令",
            confirm=False,
            prompt="lite browser 的数据已加密，请输入口令解锁：",
        )
        if dialog.exec() != QDialog.Accepted:
            break
        if vault.unlock(dialog.password()):
            return vault
        QMessageBox.warning(None, APP_NAME, "口令不正确，请重试。")

    QMessageBox.warning(
        None,
        APP_NAME,
        "未能解锁加密数据，本次运行不会保存书签、历史记录与下载记录。",
    )
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _prepare_environment(argv)
    start_url = _take_start_url(argv)

    config = Config()
    engine_id = resolve_engine(str(config.get("engine") or "auto"))
    # QtWebEngine 必须在创建 QApplication 之前导入
    prepare_engine(engine_id)

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)
    app.setQuitOnLastWindowClosed(True)

    style = QStyleFactory.create("Windows") or QStyleFactory.create("Fusion")
    if style is not None:
        app.setStyle(style)
    app.setStyleSheet(theme.stylesheet())
    app.setWindowIcon(icons.app_icon())

    data_root = data_dir()
    vault = _open_vault()
    # vault 为 None（口令未解锁）时，用一个未解锁的保险库占位：
    # 读取返回空、写入被跳过，从而不会把数据写成明文。
    store_vault = vault if vault is not None else DataVault(data_root)

    bookmarks = BookmarkStore(store_vault, data_root)
    history = HistoryStore(store_vault, data_root)
    downloads = DownloadManager(config, store_vault, data_root)
    extensions = ExtensionStore(config, data_root)
    userscripts = UserScriptStore(store_vault, config, data_root)

    window = MainWindow(
        config,
        bookmarks,
        initial_url=start_url,
        engine_id=engine_id,
        vault=store_vault,
        history=history,
        downloads=downloads,
        extensions=extensions,
        userscripts=userscripts,
    )
    downloads.folder_asker = window._ask_folder
    window._refresh_script_menu()
    window.show()
    window.raise_()
    window.activateWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
