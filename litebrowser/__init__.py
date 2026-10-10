"""lite browser —— 基于 Chromium 内核的仿 Windows XP 风格浏览器。

作者：lvzian
"""

from __future__ import annotations

__all__ = ["APP_NAME", "APP_VERSION", "AUTHOR"]


def __getattr__(name: str):
    """惰性导出包级常量，避免 ``import litebrowser`` 时连带加载 PySide6。

    ``config`` 模块依赖 ``PySide6.QtCore``（QObject / Signal），而 ``crypto``、
    ``safefetch`` 等纯 Python 模块本身并不需要 Qt。原先 ``__init__`` 直接
    ``from .config import ...``，导致只要导入本包的任何子模块都会拉起 PySide6：

        tools/decrypt_data.py → litebrowser.crypto → litebrowser/__init__
                              → litebrowser.config → PySide6 ✗

    而解密工具是**数据恢复**用途——用户往往正是浏览器出问题、想抢救书签和
    历史记录的时候才会用到它，此时不应再要求先安装 200MB+ 的 Qt。

    改为惰性导入后：
        * ``import litebrowser.crypto`` 在没有 PySide6 的环境下可用；
        * ``litebrowser.APP_NAME`` / ``from litebrowser import APP_VERSION``
          之类写法保持完全兼容（首次访问时才加载 config）。
    """
    if name in __all__ or name == "__author__":
        # 常量来自零依赖的 version 模块，因此即使没有 PySide6 也能取到；
        # 更完整的常量（ORG_NAME / COPYRIGHT 等）在 config 里，需要 Qt。
        from . import version

        return version.AUTHOR if name == "__author__" else getattr(version, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__, "__author__"})
