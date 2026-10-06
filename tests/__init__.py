"""lite browser 测试包。

在这里统一压低日志输出：测试运行时不希望 litebrowser 的日志刷屏，
但也不隐藏错误——需要看日志时设置 LITE_BROWSER_LOG=1 即可。
"""

from __future__ import annotations

import logging
import os

_logger = logging.getLogger("litebrowser")
_logger.addHandler(logging.NullHandler())
if not os.environ.get("LITE_BROWSER_LOG"):
    _logger.propagate = False
