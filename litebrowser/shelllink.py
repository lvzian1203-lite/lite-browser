"""Windows 快捷方式（.lnk）创建。

用于「工具 → 创建桌面快捷方式」，让便携版用户也能得到桌面图标。
通过系统自带的 WScript.Shell COM 组件创建，无需第三方库。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _powershell(script: str) -> tuple[bool, str]:
    """执行一段 PowerShell（不捕获管道输出，避免受限环境下的问题）。"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if completed.returncode != 0:
        return False, (completed.stderr or "").strip() or "创建失败"
    return True, ""


def desktop_dir() -> Path:
    return Path(os.path.expanduser("~")) / "Desktop"


def start_menu_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def launch_target() -> tuple[str, str]:
    """返回 (要指向的目标, 工作目录)。

    * 打包后：指向 exe 本身；
    * 源码运行：指向 pythonw.exe，并让快捷方式以脚本为参数。
    """
    if getattr(sys, "frozen", False):
        return sys.executable, str(Path(sys.executable).parent)
    script = Path(sys.argv[0]).resolve()
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else python
    return str(launcher), str(script.parent)


def create_shortcut(
    name: str,
    *,
    folder: str = "desktop",
    arguments: str = "",
    description: str = "",
    icon: str = "",
) -> tuple[bool, str]:
    """创建快捷方式，返回 (是否成功, 位置或错误信息)。"""
    target, workdir = launch_target()
    if not getattr(sys, "frozen", False):
        script = Path(sys.argv[0]).resolve()
        arguments = f'"{script}"' + (f" {arguments}" if arguments else "")

    directory = desktop_dir() if folder == "desktop" else start_menu_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, str(exc)

    link = directory / f"{name}.lnk"
    icon_location = icon or target
    script = (
        "$w = New-Object -ComObject WScript.Shell;"
        f"$s = $w.CreateShortcut('{link}');"
        f"$s.TargetPath = '{target}';"
        f"$s.WorkingDirectory = '{workdir}';"
        f"$s.IconLocation = '{icon_location}';"
        f"$s.Description = '{description or name}';"
        + (f"$s.Arguments = '{arguments}';" if arguments else "")
        + "$s.Save()"
    )
    ok, error = _powershell(script)
    if ok and not link.exists():
        return False, "快捷方式未生成"
    return (True, str(link)) if ok else (False, error)


def shortcut_path(name: str, folder: str = "desktop") -> Path:
    directory = desktop_dir() if folder == "desktop" else start_menu_dir()
    return directory / f"{name}.lnk"
