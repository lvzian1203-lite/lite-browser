"""控制台输出编码防护（**零依赖**，不导入 PySide6）。

背景：在英文 / 其它非中文区域的 Windows 上，当标准输出被**重定向**到文件或管道
（``> out.txt``、IDE 运行面板、CI 捕获 stdout）时，Python 会用系统 ANSI 代码页
（英文系统是 cp1252）编码输出，打印中文就会抛::

    UnicodeEncodeError: 'charmap' codec can't encode characters ...

这对 ``tools/decrypt_data.py`` 尤其致命 —— 它是**数据恢复**工具，用户很可能在
非中文系统上、并且把结果重定向到文件。

``configure_output()`` 的处理原则：

* 输出到真实控制台：交给 Python 的 Unicode 控制台接口，只把 ``errors``
  放宽为 ``replace``，中文照旧正常显示；
* 输出被重定向：统一改用 UTF-8（现代工具与编辑器的通用预期）；
* 任何调整失败都静默跳过，绝不影响主流程。
"""

from __future__ import annotations

import sys
from typing import Optional


def configure_output(stdout=None, stderr=None) -> None:
    """让中文输出在任何区域的 Windows 上都不会导致崩溃。"""
    for stream in (sys.stdout if stdout is None else stdout,
                   sys.stderr if stderr is None else stderr):
        if stream is None:  # pythonw.exe / 窗口程序可能没有标准输出
            continue
        try:
            is_console = bool(stream.isatty())
        except (AttributeError, ValueError, OSError):
            is_console = False
        try:
            if is_console:
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # 特殊流对象（已被替换的 stdout）或极老 Python：放弃调整即可
            continue


def safe_print(text: str, *, stream: Optional[object] = None) -> bool:
    """尽力打印；失败返回 False，不抛异常。"""
    target = sys.stdout if stream is None else stream
    if target is None:
        return False
    try:
        target.write(text)
        return True
    except (UnicodeEncodeError, ValueError, OSError):
        try:
            target.write(text.encode("ascii", "replace").decode("ascii"))
            return True
        except Exception:  # noqa: BLE001 - 连降级输出都失败，只能放弃
            return False
