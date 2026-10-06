"""统一的日志配置。

窗口程序没有控制台，所以默认**不产生任何输出**（只挂一个 NullHandler），
需要排查问题时设置环境变量：

* ``LITE_BROWSER_LOG=1``      —— 把 DEBUG 级日志写入数据目录的 ``litebrowser.log``
* ``LITE_BROWSER_TIMING=1``   —— 启动计时（原有的启动日志），同时也会打开文件日志

设计原则：可以忽略的异常必须写明"为什么可以忽略"，未预期的异常一律记录，
不允许用 ``except Exception: pass`` 把问题藏起来。
"""

from __future__ import annotations

import logging
import os
import sys

ROOT_LOGGER = "litebrowser"

_configured = False


def setup() -> None:
    """初始化日志（幂等，可重复调用）。"""
    global _configured
    if _configured:
        return
    _configured = True

    logger = logging.getLogger(ROOT_LOGGER)
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.WARNING)

    if not (os.environ.get("LITE_BROWSER_LOG") or os.environ.get("LITE_BROWSER_TIMING")):
        return

    try:
        from .config import data_dir

        path = data_dir() / "litebrowser.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    except OSError as exc:
        # 磁盘只读 / 路径不可写时不影响程序运行：只在有控制台时提示一句
        if sys.stderr is not None:
            try:
                sys.stderr.write(f"[litebrowser] 无法初始化日志文件：{exc}\n")
            except Exception:  # noqa: BLE001 - 连 stderr 都不可用，只能放弃输出
                pass


def logger(name: str) -> logging.Logger:
    """取得子模块 logger（自动挂在 litebrowser 命名空间下）。"""
    if not name.startswith(ROOT_LOGGER):
        name = f"{ROOT_LOGGER}.{name}"
    return logging.getLogger(name)
