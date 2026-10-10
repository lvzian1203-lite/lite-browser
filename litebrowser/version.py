"""版本、作者与版权信息（**零依赖**，不导入 PySide6 或任何第三方库）。

为什么单独成一个模块：这些常量需要被纯命令行工具使用。
典型场景是 ``tools/decrypt_data.py`` —— 它是**数据恢复**工具，
用户往往正是在浏览器出问题、想抢救书签和历史记录的时候才用它，
此时不应该再要求先安装 200MB+ 的 Qt。

``config`` 模块会重新导出这些常量（``from .version import ...``），
因此 ``from litebrowser.config import APP_VERSION`` 之类的既有写法完全不受影响。
"""

from __future__ import annotations

APP_NAME = "lite browser"
APP_VERSION = "1.7.2"
BUILD_YEAR = "2026"
AUTHOR = "lvzian"
ORG_NAME = "LiteBrowser"
COPYRIGHT = f"Copyright (C) {BUILD_YEAR} {AUTHOR}"

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "BUILD_YEAR",
    "AUTHOR",
    "ORG_NAME",
    "COPYRIGHT",
]
