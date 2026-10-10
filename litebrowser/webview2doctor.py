"""WebView2 运行环境自检与一键修复。

「设置 → 内核与环境」里的诊断页用它检查：

* 操作系统与位数是否满足要求；
* 系统是否安装了 **WebView2 运行时**（读注册表，含用户级安装）；
* 随程序分发的 WebView2 SDK 程序集与加载器 DLL 是否齐全；
* 是否具备 pythonnet / clr_loader / cffi 互操作组件；
* .NET 运行时（.NET Framework 或 .NET）是否可用；
* 用户数据目录是否可写。

检测到缺失时可一键下载并运行微软官方的 **WebView2 引导安装器**，
不必自己去官网找。
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from .i18n import tr, trf

#: 微软官方 WebView2 引导安装器（Evergreen Bootstrapper）
DOWNLOAD_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
#: 官方下载页面（备用）
DOWNLOAD_PAGE = "https://developer.microsoft.com/microsoft-edge/webview2/"

#: WebView2 运行时在注册表中的 GUID
_RUNTIME_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_RUNTIME_KEYS = (
    (r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients", "HKLM", tr("系统（64 位视图）")),
    (r"SOFTWARE\Microsoft\EdgeUpdate\Clients", "HKLM", tr("系统")),
    (r"SOFTWARE\Microsoft\EdgeUpdate\Clients", "HKCU", tr("当前用户")),
)

OK = "ok"
WARN = "warn"
BAD = "bad"


@dataclass
class Check:
    """一项检测结果。"""

    key: str
    title: str
    level: str = OK
    detail: str = ""
    advice: str = ""

    @property
    def ok(self) -> bool:
        return self.level == OK

    @property
    def icon_name(self) -> str:
        return {"ok": "lock", "warn": "warn", "bad": "warn"}.get(self.level, "info")


# --------------------------------------------------------------------------- #
# 单项检测
# --------------------------------------------------------------------------- #
def runtime_version() -> tuple[str, str]:
    """返回 (版本号, 来源说明)；未安装返回 ("", "")。"""
    try:
        import winreg  # type: ignore
    except ImportError:
        return "", ""

    roots = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}
    for subkey, root_name, label in _RUNTIME_KEYS:
        root = roots.get(root_name)
        if root is None:
            continue
        try:
            with winreg.OpenKey(root, subkey) as key:
                with winreg.OpenKey(key, _RUNTIME_GUID) as client:
                    version, _kind = winreg.QueryValueEx(client, "pv")
                    if version:
                        return str(version), label
        except OSError:
            continue
    return "", ""


def _check_os() -> Check:
    bits = 64 if sys.maxsize > 2 ** 32 else 32
    release = platform.release() or "Windows"
    version = platform.version() or ""
    if bits != 64:
        return Check("os", tr("操作系统"), BAD, trf('{0}（{1} 位）', release, bits),
                     tr("WebView2 需要 64 位 Windows 10 / 11。"))
    return Check("os", tr("操作系统"), OK, trf('{0}\u3000{1}\u3000{2} 位', release, version, bits))


def _check_runtime() -> Check:
    version, source = runtime_version()
    if version:
        return Check("runtime", tr("WebView2 运行时"), OK, trf('已安装 {0}（{1}）', version, source))
    return Check(
        "runtime", tr("WebView2 运行时"), BAD, tr("未检测到"),
        tr("点击下方「下载并安装 WebView2 运行时」，按提示完成后重新检测。"),
    )


def _check_sdk() -> Check:
    from .config import resource_path

    dll = resource_path("lib", "webview2", "Microsoft.Web.WebView2.Core.dll")
    loader = resource_path(
        "lib", "webview2", "runtimes", "win-x64", "native", "WebView2Loader.dll"
    )
    missing = [path.name for path in (dll, loader) if not path.exists()]
    if missing:
        return Check("sdk", tr("WebView2 组件文件"), BAD, tr("缺少：") + "、".join(missing),
                     tr("程序文件不完整，请重新安装 lite browser。"))
    size = dll.stat().st_size // 1024
    return Check("sdk", tr("WebView2 组件文件"), OK, trf('齐全（Core.dll {0} KB + 加载器）', size))


def _check_pythonnet() -> Check:
    missing = []
    for name in ("pythonnet", "clr_loader", "cffi"):
        try:
            __import__(name)
        except Exception:
            missing.append(name)
    if missing:
        return Check("pythonnet", tr("互操作组件"), BAD, tr("缺少：") + "、".join(missing),
                     tr("这些组件随程序一起分发，缺失说明安装不完整。"))
    return Check("pythonnet", tr("互操作组件"), OK, tr("pythonnet / clr_loader / cffi 正常"))


def _check_dotnet() -> Check:
    netfx = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\clr.dll")
    coreclr_roots = [
        Path(os.environ.get("DOTNET_ROOT", "")) / "host" / "fxr",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "dotnet" / "host" / "fxr",
    ]
    has_coreclr = any(root.is_dir() and any(root.iterdir()) for root in coreclr_roots if str(root))
    used = ""
    try:
        from .wv2engine import _STATE

        used = str(_STATE.get("runtime") or "")
    except Exception:
        used = ""

    if netfx.exists():
        detail = tr(".NET Framework 4.x 可用")
        if used:
            detail += trf('（当前使用：{0}）', used)
        return Check("dotnet", tr(".NET 运行时"), OK, detail)
    if has_coreclr:
        return Check("dotnet", tr(".NET 运行时"), WARN, tr(".NET 可用，但未检测到 .NET Framework 4.x"),
                     tr("程序会回退到 .NET 运行时；如异常可修复系统组件。"))
    return Check("dotnet", tr(".NET 运行时"), BAD, tr("未检测到 .NET Framework 与 .NET"),
                 tr("请在 Windows 功能中启用 .NET Framework 4.8，或安装 .NET 运行时。"))


def _check_datadir() -> Check:
    from .config import data_dir

    try:
        folder = data_dir() / "webview2"
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check("datadir", tr("用户数据目录"), BAD, trf('不可写：{0}', exc),
                     tr("请检查磁盘空间与目录权限，或改用便携版放到可写目录。"))
    return Check("datadir", tr("用户数据目录"), OK, str(data_dir()))


def _check_engine(engine_id: str = "") -> Check:
    label = {
        "webview2": "Edge WebView2（推荐，含 H.264/AAC）",
        "qtwebengine": "QtWebEngine（无专有编解码器）",
    }.get(engine_id, engine_id or "自动选择")

    version = ""
    try:
        from .wv2engine import _STATE

        version = str(_STATE.get("browser_version") or "")
    except Exception:
        pass

    detail = label + (trf('\u3000内核 {0}', version) if version else "")
    if engine_id == "qtwebengine":
        return Check("engine", tr("当前渲染内核"), WARN, detail,
                     "QtWebEngine 不含 H.264/AAC，视频站点可能无法播放；"
                     "也无法提供 Flash 兼容（Ruffle）。"
                     "可在「设置 → 外观 → 渲染引擎」切换为 Edge WebView2。")
    return Check("engine", tr("当前渲染内核"), OK, detail)


def _check_flash() -> Check:
    """检查内置的无广告 Flash 运行时（Ruffle）。"""
    try:
        from . import ruffle

        info = ruffle.info()
    except Exception as exc:  # noqa: BLE001
        return Check("flash", tr("Flash 兼容（Ruffle）"), BAD, trf('不可用：{0}', exc))
    if info["available"]:
        return Check(
            "flash", tr("Flash 兼容（Ruffle）"), OK,
            trf('{0}，{1} MB（开源 Flash 模拟器，无广告）', info['version'], info['size_mb']),
        )
    return Check(
        "flash", tr("Flash 兼容（Ruffle）"), BAD, tr("未找到 lib/ruffle 文件"),
        tr("程序文件不完整，请重新安装 lite browser。"),
    )


def diagnose(engine_id: str = "") -> list[Check]:
    """执行全部检测，返回结果列表。"""
    checks = [_check_os(), _check_runtime(), _check_engine(engine_id), _check_sdk()]
    checks.append(_check_pythonnet())
    checks.append(_check_dotnet())
    checks.append(_check_flash())
    checks.append(_check_datadir())
    return checks


def summary(checks: list[Check]) -> tuple[str, str]:
    """返回 (总体等级, 一句话结论)。"""
    if any(item.level == BAD for item in checks):
        bad = [item.title for item in checks if item.level == BAD]
        return BAD, tr("发现 ") + str(len(bad)) + tr(" 项问题：") + "、".join(bad)
    if any(item.level == WARN for item in checks):
        return WARN, tr("基本可用，但有需要注意的项目")
    return OK, tr("一切正常，WebView2 环境可以正常使用")


def report_text(checks: list[Check]) -> str:
    """生成可复制的诊断报告。"""
    from .config import APP_NAME, APP_VERSION

    lines = [
        trf('{0} {1} 环境诊断报告', APP_NAME, APP_VERSION),
        time.strftime("%Y-%m-%d %H:%M:%S"),
        f"Python {platform.python_version()}　{platform.platform()}",
        "-" * 52,
    ]
    for item in checks:
        mark = {"ok": "[正常]", "warn": "[注意]", "bad": "[异常]"}.get(item.level, "[未知]")
        lines.append(f"{mark} {item.title}：{item.detail}")
        if item.advice:
            lines.append(trf('        建议：{0}', item.advice))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 下载与安装
# --------------------------------------------------------------------------- #
class RuntimeDownloader(QObject):
    """在后台线程下载 WebView2 引导安装器，并汇报进度。"""

    progress = Signal(int, int)        # 已下载, 总数（未知时为 0）
    finished = Signal(str)             # 下载到的文件路径
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        target = Path(tempfile.gettempdir()) / "MicrosoftEdgeWebView2Setup.exe"
        try:
            request = urllib.request.Request(
                DOWNLOAD_URL, headers={"User-Agent": "Mozilla/5.0 lite browser"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                total = int(response.headers.get("Content-Length") or 0)
                received = 0
                with open(target, "wb") as handle:
                    while True:
                        if self._cancelled:
                            self.failed.emit(tr("已取消"))
                            return
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        received += len(chunk)
                        self.progress.emit(received, total)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        if not target.exists() or target.stat().st_size < 100_000:
            self.failed.emit(tr("下载的文件不完整"))
            return
        self.finished.emit(str(target))


def run_installer(path: str) -> tuple[bool, str]:
    """运行下载好的引导安装器（会弹出微软自己的安装界面，可能需要管理员确认）。"""
    try:
        subprocess.Popen([path], close_fds=True)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def open_download_page() -> None:
    """在系统默认浏览器里打开官方下载页。"""
    import webbrowser

    try:
        webbrowser.open(DOWNLOAD_PAGE)
    except Exception:
        pass


def save_report(text: str, path: Path) -> bool:
    try:
        path.write_text(text, encoding="utf-8")
        return True
    except OSError:
        return False


def temp_dir() -> Path:
    return Path(tempfile.gettempdir())


def which(program: str) -> Optional[str]:
    return shutil.which(program)
