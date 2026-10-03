#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""lite browser —— 基于 Chromium 内核的仿 Windows XP 风格浏览器。

作者：lvzian

用法：
    python lite_browser.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from litebrowser.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
