"""书签（收藏夹）存储：加密持久化。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from .crypto import DataVault
from .i18n import tr

#: 首次运行时预置的书签
SEED_BOOKMARKS: list[tuple[str, str]] = [
    ("必应搜索", "https://cn.bing.com/"),
    ("百度", "https://www.baidu.com/"),
    ("GitHub", "https://github.com/"),
]


class BookmarkStore(QObject):
    """书签集合，任何修改都会立即写入磁盘并发出 ``changed`` 信号。

    数据保存在 ``data/bookmarks.dat``（AES-256-GCM 加密）；
    旧版本的 ``bookmarks.json`` 会在首次读取时自动迁移。
    """

    changed = Signal()

    def __init__(self, vault: DataVault, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.blob_path = Path(data_dir) / "data" / "bookmarks.dat"
        self.legacy_path = Path(data_dir) / "bookmarks.json"
        self._items: list[dict[str, Any]] = []
        self.load()

    # -- 持久化 ----------------------------------------------------------- #
    def load(self) -> None:
        items: list[dict[str, Any]] = []
        text = self.vault.read_text(self.blob_path, self.legacy_path)

        raw = None
        if text:
            try:
                raw = json.loads(text)
            except ValueError:
                raw = None

        if isinstance(raw, dict):
            raw = raw.get("bookmarks")
        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                url = str(entry.get("url") or "").strip()
                if not url:
                    continue
                items.append(
                    {
                        "title": str(entry.get("title") or url).strip(),
                        "url": url,
                        "added": entry.get("added") or time.time(),
                    }
                )

        first_run = not self.blob_path.exists() and not self.legacy_path.exists()
        if not items and first_run:
            now = time.time()
            # 默认书签按当前界面语言生成（英文环境下列表也是英文）
            items = [
                {"title": tr(title), "url": url, "added": now}
                for title, url in SEED_BOOKMARKS
            ]
        self._items = items
        if first_run:
            self.save()

    def save(self) -> None:
        payload = {"version": 1, "bookmarks": self._items}
        try:
            self.vault.write_text(
                json.dumps(payload, ensure_ascii=False), self.blob_path, self.legacy_path
            )
        except OSError:
            pass

    # -- 查询 ------------------------------------------------------------- #
    def __len__(self) -> int:
        return len(self._items)

    def items(self) -> list[dict[str, Any]]:
        return list(self._items)

    def at(self, index: int) -> dict[str, Any] | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def index_of(self, url: str) -> int:
        for index, item in enumerate(self._items):
            if item["url"] == url:
                return index
        return -1

    def is_bookmarked(self, url: str) -> bool:
        return self.index_of(url) >= 0

    # -- 修改 ------------------------------------------------------------- #
    def add(self, title: str, url: str, index: int | None = None) -> int:
        """添加书签；已存在则更新标题，返回其下标。"""
        url = (url or "").strip()
        title = (title or url).strip() or url
        if not url:
            return -1

        existing = self.index_of(url)
        if existing >= 0:
            self._items[existing]["title"] = title
            self.save()
            self.changed.emit()
            return existing

        entry = {"title": title, "url": url, "added": time.time()}
        if index is None or not (0 <= index <= len(self._items)):
            self._items.append(entry)
            position = len(self._items) - 1
        else:
            self._items.insert(index, entry)
            position = index
        self.save()
        self.changed.emit()
        return position

    def remove(self, index: int) -> bool:
        if 0 <= index < len(self._items):
            del self._items[index]
            self.save()
            self.changed.emit()
            return True
        return False

    def update(self, index: int, title: str, url: str) -> bool:
        if not (0 <= index < len(self._items)):
            return False
        url = (url or "").strip()
        if not url:
            return False
        self._items[index]["title"] = (title or url).strip() or url
        self._items[index]["url"] = url
        self.save()
        self.changed.emit()
        return True

    def move(self, index: int, delta: int) -> int:
        target = index + delta
        if 0 <= index < len(self._items) and 0 <= target < len(self._items):
            self._items[index], self._items[target] = (
                self._items[target],
                self._items[index],
            )
            self.save()
            self.changed.emit()
            return target
        return index

    def clear(self) -> None:
        self._items.clear()
        self.save()
        self.changed.emit()
