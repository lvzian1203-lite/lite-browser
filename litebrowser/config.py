"""路径、常量与配置读写。

配置保存在 ``%APPDATA%\\LiteBrowser\\settings.json``；
若程序目录下存在 ``portable.txt``，则改为绿色便携模式，
数据写在程序目录的 ``data`` 子目录中。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

APP_NAME = "lite browser"
APP_VERSION = "1.6.95"
BUILD_YEAR = "2026"
AUTHOR = "lvzian"
ORG_NAME = "LiteBrowser"
COPYRIGHT = f"Copyright (C) {BUILD_YEAR} {AUTHOR}"

DEFAULT_HOMEPAGE = "https://cn.bing.com/"

#: 搜索引擎列表（{query} 会被替换为 URL 编码后的关键字）
SEARCH_ENGINES: list[dict[str, str]] = [
    {"id": "bing", "name": "必应 (Bing)", "url": "https://cn.bing.com/search?q={query}"},
    {"id": "baidu", "name": "百度", "url": "https://www.baidu.com/s?wd={query}"},
    {"id": "google", "name": "Google", "url": "https://www.google.com/search?q={query}"},
    {"id": "sogou", "name": "搜狗", "url": "https://www.sogou.com/web?query={query}"},
    {"id": "duckduckgo", "name": "DuckDuckGo", "url": "https://duckduckgo.com/?q={query}"},
]


# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #
def app_root() -> Path:
    """程序所在目录（打包成 exe 后为 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """读取随程序分发的资源（源码运行 / PyInstaller 打包均可用）。"""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else app_root()
    return root.joinpath(*parts)


def data_dir() -> Path:
    """用户数据目录。

    可用环境变量 ``LITE_BROWSER_DATA_DIR`` 指定（测试或自定义数据位置时使用）；
    程序目录下存在 ``portable.txt`` 时改为绿色便携模式。
    """
    override = os.environ.get("LITE_BROWSER_DATA_DIR")
    if override:
        target = Path(override)
    elif (app_root() / "portable.txt").exists():
        target = app_root() / "data"
    else:
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home())
        target = Path(base) / ORG_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def profile_dir() -> Path:
    d = data_dir() / "profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    d = data_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
class Config(QObject):
    """轻量 JSON 配置对象。"""

    changed = Signal()

    DEFAULTS: dict[str, Any] = {
        "homepage": DEFAULT_HOMEPAGE,
        "startup_mode": "home",          # home | blank | last
        "search_engine": "bing",
        "engine": "auto",                # auto | webview2 | qtwebengine
        "show_bookmark_bar": True,
        "show_status_bar": True,
        "native_frame": False,           # True = 使用系统原生窗口边框
        "window_geometry": None,         # [x, y, w, h]
        "window_maximized": False,
        "zoom": 1.0,
        "last_url": "",
        # 下载
        "download_dir": "",              # 首次下载时由用户设定
        "ask_download_dir": False,       # True = 每次下载都询问
        # 历史记录
        "history_enabled": True,
        "history_keep_days": 90,         # 0 = 永久保留
        # 无痕浏览
        "incognito": False,
        # 界面主题
        "ui_theme": "xp",                # xp | win98 | win7 | win81 | win10 | win11 | harmony | cat
        "ui_mode": "light",              # light | dark
        "ui_accent": "",                 # 自定义边框颜色 #RRGGBB，空 = 用主题默认
        # 性能
        "suspend_background_tabs": True, # 后台标签页闲置后自动挂起
        "suspend_after_minutes": 10,
        "restore_session": False,        # 启动时恢复上次的标签页
        "preload_links": False,          # 对页面内链接做 DNS 预解析
        "smooth_scroll": False,
        "load_images": True,
        "cache_size_mb": 0,              # 0 = 由内核决定
        # 网络与安全
        "user_agent": "",                # 空 = 内核默认
        "strict_certificate": False,     # True = 证书有问题直接拒绝
        "certificate_warning": True,     # 证书有问题时弹出提示由用户决定
        "block_malicious": True,         # 恶意网址拦截
        # 广告屏蔽 / Flash 兼容
        "block_popups": True,            # 拦截网页自动弹出的窗口（非用户点击）
        "flash_compat": True,            # 用 Ruffle 运行 Flash 内容（无广告）
        # 会话
        "session_tabs": [],
        "last_startup_seconds": 0.0,     # 上次启动耗时（诊断用）
    }

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.path = data_dir() / "settings.json"
        self._data: dict[str, Any] = dict(self.DEFAULTS)
        self.load()

    # -- 读写 ------------------------------------------------------------- #
    def load(self) -> None:
        try:
            # utf-8-sig：兼容记事本等编辑器写入的 BOM
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            for key, value in raw.items():
                self._data[key] = value

    def save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.path)
        except OSError:
            pass

    # -- 访问 ------------------------------------------------------------- #
    def get(self, key: str, default: Any = None) -> Any:
        if key in self._data:
            return self._data[key]
        if default is not None:
            return default
        return self.DEFAULTS.get(key)

    def set(self, key: str, value: Any, *, save: bool = True) -> None:
        if self._data.get(key) == value:
            return
        self._data[key] = value
        if save:
            self.save()
        self.changed.emit()

    def update(self, values: dict[str, Any], *, save: bool = True) -> None:
        touched = False
        for key, value in values.items():
            if self._data.get(key) != value:
                self._data[key] = value
                touched = True
        if touched:
            if save:
                self.save()
            self.changed.emit()

    # -- 便捷属性 --------------------------------------------------------- #
    @property
    def homepage(self) -> str:
        value = str(self.get("homepage") or "").strip()
        return value or DEFAULT_HOMEPAGE

    def search_url(self, text: str) -> str:
        from urllib.parse import quote_plus

        engine_id = str(self.get("search_engine") or "bing")
        for engine in SEARCH_ENGINES:
            if engine["id"] == engine_id:
                return engine["url"].format(query=quote_plus(text))
        return SEARCH_ENGINES[0]["url"].format(query=quote_plus(text))
