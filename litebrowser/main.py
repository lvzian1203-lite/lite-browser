"""程序入口。"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QStyleFactory

from . import icons, logging_setup, theme
from .console import configure_output
from .bookmarks import BookmarkStore
from .browser import MainWindow
from .config import APP_NAME, APP_VERSION, AUTHOR, ORG_NAME, Config, data_dir
from .crypto import CRYPTO_AVAILABLE, DataVault
from .dialogs import PasswordDialog
from .downloads import DownloadManager
from .engine import ENGINE_WEBVIEW2, prepare_engine, resolve_engine
from .history import HistoryStore
from .netsec import SecurityManager
from .performance import PerformanceManager
from .widgets import StartupSplash

from .i18n import apply_language_from_config, tr, trf

log = logging.getLogger(__name__)


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
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
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


class _VaultAbort(Exception):
    """用户在「无法加密」提示里选择了退出，启动流程应中止。"""


def _open_vault() -> DataVault | None:
    """初始化数据保险库；必要时提示输入口令。

    返回 None 表示本次运行不保存书签 / 历史 / 下载记录（口令未解锁）；
    若加密库缺失且用户选择退出，则抛出 :class:`_VaultAbort`。
    """
    vault = DataVault(data_dir())

    if not vault.available:
        # 加密能力缺失时必须让用户明确知情并自行决定，
        # 不允许静默降级为明文存储（数据落盘方式影响隐私）。
        box = QMessageBox()
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(APP_NAME)
        box.setText(tr("当前环境无法启用数据加密"))
        box.setInformativeText(
            "未找到 cryptography 加密库，本次运行中书签、历史记录与下载记录"
            "只能以明文保存，同一台电脑上的其他程序或用户可以读取这些内容。\n\n"
            "如需加密保护，请先安装后重新启动：\n"
            "    pip install cryptography"
        )
        plain_button = box.addButton(tr("继续使用明文(&C)"), QMessageBox.AcceptRole)
        box.addButton(tr("退出(&Q)"), QMessageBox.RejectRole)
        box.setDefaultButton(plain_button)
        box.exec()
        if box.clickedButton() is not plain_button:
            raise _VaultAbort()
        log.warning("cryptography 不可用，用户选择以明文方式继续运行")
        return vault

    if vault.initialize():
        return vault

    # 已有口令保护，需要用户输入
    for _attempt in range(3):
        dialog = PasswordDialog(
            None,
            title=tr("输入加密口令"),
            confirm=False,
            prompt=tr("lite browser 的数据已加密，请输入口令解锁："),
        )
        if dialog.exec() != QDialog.Accepted:
            break
        if vault.unlock(dialog.password()):
            return vault
        QMessageBox.warning(None, APP_NAME, tr("口令不正确，请重试。"))

    QMessageBox.warning(
        None,
        APP_NAME,
        tr("未能解锁加密数据，本次运行不会保存书签、历史记录与下载记录。"),
    )
    return None


def _env_report_requested(argv: list[str]) -> bool:
    return any(arg in ("--env-report", "--env-check", "/env-report") for arg in argv)


def _run_env_report() -> int:
    """`--env-report`：不进界面，直接做一次环境自检并保存报告。

    方便在网页打不开时把报告发给作者排查，也能在打包版里验证诊断模块。
    """
    from .webview2doctor import diagnose, report_text

    config = Config()
    # 语言必须在创建任何界面文字之前定好
    apply_language_from_config(config)
    engine_id = resolve_engine(str(config.get("engine") or "auto"))
    checks = diagnose(engine_id)
    text = report_text(checks) + trf('\n当前内核：{0}\n', engine_id)

    target = data_dir() / "env-report.txt"
    try:
        target.write_text(text, encoding="utf-8")
    except OSError:
        target = Path(tempfile.gettempdir()) / "lite-browser-env-report.txt"
        try:
            target.write_text(text, encoding="utf-8")
        except OSError as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    # 窗口程序没有控制台，能写 stdout 就写，写不了就弹个原生提示框
    written = False
    try:
        if sys.stdout is not None:
            # 输出被重定向时改用 UTF-8，避免英文系统上中文报告编码失败
            configure_output()
            sys.stdout.write(text + trf('\n报告已保存：{0}\n', target))
            written = True
    except Exception as lite_exc:
        log.debug("忽略异常：%s", lite_exc)
        pass
    if not written:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                trf('环境自检完成，报告已保存到：\n{0}\n\n如果网页打不开，可以把这份报告发给作者排查。', target),
                trf('{0} 环境自检', APP_NAME),
                0x40,
            )
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    # 日志：默认不输出；设置 LITE_BROWSER_LOG=1 / LITE_BROWSER_TIMING=1 时写入数据目录
    logging_setup.setup()
    argv = list(sys.argv if argv is None else argv)
    _prepare_environment(argv)
    if _env_report_requested(argv):
        return _run_env_report()
    start_url = _take_start_url(argv)

    config = Config()
    # 语言必须在创建任何界面文字之前定好
    apply_language_from_config(config)
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
    app.setWindowIcon(icons.app_icon())
    # 立刻用主题调色板覆盖 Qt 的默认调色板：Windows 深色模式下默认调色板是深色的，
    # 会让未显式配色的控件（滚动区、分组框等）变成黑底，浅色主题下文字看不清。
    theme.apply_palette(app, theme.spec_for(
        str(config.get("ui_theme") or theme.DEFAULT_THEME),
        str(config.get("ui_mode") or "light"),
        str(config.get("ui_accent") or ""),
    ))

    # 1) 先确定主题（只设定对象，不下发样式表）。
    #    样式表改到界面构造完成后再一次性应用：Qt 只需对整个控件树做一次 polish，
    #    实测比构造期间逐控件 polish 快约 10 倍（约 510ms → 50ms）。
    spec = theme.spec_for(
        str(config.get("ui_theme") or theme.DEFAULT_THEME),
        str(config.get("ui_mode") or "light"),
        str(config.get("ui_accent") or ""),
    )
    theme.set_current(spec)
    app.setWindowIcon(icons.app_icon())

    # 2) 启动画面：立刻给出视觉反馈，掩盖后续准备时间
    splash = StartupSplash(APP_NAME, APP_VERSION, AUTHOR)
    splash.show()
    app.processEvents()
    splash_ms = (time.perf_counter() - started) * 1000

    # 3) 启动画面已经可见，此时开始预热 WebView2 环境：
    #    CLR 加载与环境创建与后面的界面构造并行进行，缩短引擎就绪时间
    if engine_id in (ENGINE_WEBVIEW2, "auto"):
        splash.set_message(tr("正在准备渲染引擎…"))
        try:
            from .wv2engine import prewarm_environment

            prewarm_environment(config)
        except Exception as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    splash.set_message(tr("正在解锁数据…"))
    data_root = data_dir()
    try:
        vault = _open_vault()
    except _VaultAbort:
        # 用户在"无法加密"提示中选择了退出：关闭启动画面并结束启动
        log.warning("用户选择在无加密环境下退出，启动已中止")
        try:
            splash.close()
        except Exception as exc:  # noqa: BLE001 - 关闭启动画面失败不影响退出
            log.debug("关闭启动画面失败：%s", exc)
        return 1
    # vault 为 None（口令未解锁）时，用一个未解锁的保险库占位：
    # 读取返回空、写入被跳过，从而不会把数据写成明文。
    store_vault = vault if vault is not None else DataVault(data_root)

    splash.set_message(tr("正在读取书签与历史…"))
    bookmarks = BookmarkStore(store_vault, data_root)
    history = HistoryStore(store_vault, data_root)
    downloads = DownloadManager(config, store_vault, data_root)
    security = SecurityManager(config, data_root)
    performance = PerformanceManager(config)

    splash.set_message(tr("正在准备界面…"))
    window = MainWindow(
        config,
        bookmarks,
        initial_url=start_url,
        engine_id=engine_id,
        vault=store_vault,
        history=history,
        downloads=downloads,
        security=security,
        performance=performance,
    )
    downloads.folder_asker = window._ask_folder

    # 5) 一次性应用调色板 + 样式表
    theme.apply_theme(app, spec)
    splash.set_message(tr("正在打开首页…"))

    window.show()
    window.raise_()
    window.activateWindow()
    shown_ms = (time.perf_counter() - started) * 1000
    # 只强制重绘主窗口本身：processEvents() 会顺带把 WebView2 初始化也跑完，
    # 让「首帧完成」这个指标失去意义
    window.repaint()
    painted_ms = (time.perf_counter() - started) * 1000

    # 6) 启动画面继续显示到渲染引擎就绪（最多 8 秒）：
    #    否则用户会先看到一个空白标签页，以为程序卡住了
    report = {"splash": splash_ms, "window": shown_ms, "paint": painted_ms}
    _hold_splash_until_ready(window, splash, started, data_root, report)

    if os.environ.get("LITE_BROWSER_TIMING"):
        _trace_startup(window, started, data_root, report)
    return app.exec()


def _hold_splash_until_ready(window, splash, started: float, data_root, report: dict,
                             timeout_ms: int = 8000) -> None:
    """渲染引擎就绪后再关闭启动画面，避免出现「空白窗口」。"""
    from PySide6.QtCore import QTimer

    state = {"done": False}

    def finish() -> None:
        if state["done"]:
            return
        state["done"] = True
        report["ready"] = (time.perf_counter() - started) * 1000
        splash.finish()
        window.note_startup_time(time.perf_counter() - started)

    def poll() -> None:
        if state["done"]:
            return
        engine = window.current_engine()
        if engine is not None and (engine.is_ready() or engine.current_url()):
            # 稍等一拍，让主窗口与网页把首帧画出来
            QTimer.singleShot(120, finish)
            return
        QTimer.singleShot(60, poll)

    QTimer.singleShot(60, poll)
    QTimer.singleShot(timeout_ms, finish)


def _trace_startup(window, started: float, data_root, report: dict) -> None:
    """记录「引擎就绪 / 首页加载完成」的耗时（仅诊断时启用）。"""
    from PySide6.QtCore import QTimer

    state = {"ready": None, "loaded": None, "written": False}

    def write() -> None:
        if state["written"]:
            return
        state["written"] = True

        def fmt(value) -> str:
            return f"{value:.0f}" if isinstance(value, (int, float)) else str(value)

        text = " ".join(f"{key}={fmt(value)}" for key, value in report.items())
        print(f"[timing] {text}", flush=True)
        try:
            (data_root / "startup.log").write_text(text + "\n", encoding="utf-8")
        except OSError as lite_exc:
            log.debug("忽略异常：%s", lite_exc)
            pass

    def on_loaded(_ok: bool) -> None:
        if state["loaded"] is None:
            state["loaded"] = (time.perf_counter() - started) * 1000
            report["page"] = state["loaded"]
            write()

    def poll() -> None:
        engine = window.current_engine()
        if engine is not None and engine.is_ready() and state["ready"] is None:
            state["ready"] = (time.perf_counter() - started) * 1000
            report["engine"] = state["ready"]
            try:
                from .wv2engine import _STATE as _wv2_state

                if _wv2_state.get("clr_ms"):
                    report["clr"] = _wv2_state["clr_ms"]
                if _wv2_state.get("env_ms"):
                    report["env"] = _wv2_state["env_ms"]
                if _wv2_state.get("runtime"):
                    report["rt"] = _wv2_state["runtime"]
                for key in ("t_importnet", "t_load", "t_import", "t_ref", "t_types"):
                    if _wv2_state.get(key):
                        report[key.replace("t_", "clr_")] = _wv2_state[key]
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
            try:
                engine.load_finished.connect(on_loaded)
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass
        QTimer.singleShot(50, poll)

    QTimer.singleShot(100, poll)
    # 最多等 60 秒也要留下记录
    QTimer.singleShot(60000, write)


if __name__ == "__main__":
    raise SystemExit(main())
