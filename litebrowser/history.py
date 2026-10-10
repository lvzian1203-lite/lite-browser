"""浏览历史记录（加密存储，按日期归档）。"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from .crypto import DataVault

log = logging.getLogger(__name__)

WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


@dataclass
class HistoryEntry:
    """一条历史记录。"""

    url: str
    title: str
    visited_at: float
    visit_count: int = 1

    @property
    def moment(self) -> datetime:
        return datetime.fromtimestamp(self.visited_at)

    @property
    def date_key(self) -> str:
        """用于分组的日期，例如 2026-10-03。"""
        return self.moment.strftime("%Y-%m-%d")

    @property
    def date_text(self) -> str:
        """带星期的日期，例如 2026-10-03 星期六。"""
        moment = self.moment
        return f"{moment.strftime('%Y-%m-%d')} {WEEKDAYS[moment.weekday()]}"

    @property
    def time_text(self) -> str:
        return self.moment.strftime("%H:%M:%S")

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "visited_at": self.visited_at,
            "visit_count": self.visit_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Optional["HistoryEntry"]:
        url = str(data.get("url") or "").strip()
        if not url:
            return None
        try:
            visited_at = float(data.get("visited_at") or 0)
        except (TypeError, ValueError):
            visited_at = 0.0
        return cls(
            url=url,
            title=str(data.get("title") or url),
            visited_at=visited_at or time.time(),
            visit_count=int(data.get("visit_count") or 1),
        )


class HistoryStore(QObject):
    """历史记录集合，写入加密文件 ``data/history.dat``。

    写盘策略：``record()`` 只标记脏数据并启动合并定时器，不立即写盘。
    原因是每次访问都要 O(n) 去重 + 序列化全部记录 + AES-256-GCM 加密 + 同步写盘，
    而这一切都发生在 UI 线程；记录越多、使用越久就越慢。
    程序退出路径会调用 :meth:`flush_now` 保证不丢数据。
    """

    changed = Signal()

    #: 写盘合并窗口（毫秒）：这段时间内的多次记录只写一次盘
    FLUSH_DELAY_MS = 2000

    def __init__(self, vault: DataVault, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.blob_path = Path(data_dir) / "data" / "history.dat"
        self.legacy_path = Path(data_dir) / "history.json"
        self.max_entries = 20000
        self._entries: list[HistoryEntry] = []
        #: 是否有尚未落盘的改动
        self._dirty = False
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(self.FLUSH_DELAY_MS)
        self._flush_timer.timeout.connect(self._flush)
        self.load()

    # -- 持久化 ----------------------------------------------------------- #
    def load(self) -> None:
        text = self.vault.read_text(self.blob_path, self.legacy_path)
        entries: list[HistoryEntry] = []
        if text:
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                payload = payload.get("entries")
            if isinstance(payload, list):
                for raw in payload:
                    if isinstance(raw, dict):
                        entry = HistoryEntry.from_dict(raw)
                        if entry is not None:
                            entries.append(entry)
        entries.sort(key=lambda item: item.visited_at, reverse=True)
        self._entries = entries[: self.max_entries]

    def save(self) -> None:
        """立即写入磁盘（数据格式保持 {"version":1,"entries":[...]} + AES 不变）。"""
        payload = {
            "version": 1,
            "entries": [entry.to_dict() for entry in self._entries],
        }
        try:
            self.vault.write_text(
                json.dumps(payload, ensure_ascii=False), self.blob_path, self.legacy_path
            )
        except OSError as exc:
            log.warning("保存历史记录失败：%s", exc)
            return
        self._dirty = False

    def mark_dirty(self) -> None:
        """标记有改动，合并到稍后一次性写盘（避免每次导航都全量加密写盘）。"""
        self._dirty = True
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush(self) -> None:
        if not self._dirty:
            return
        self.save()

    def flush_now(self) -> None:
        """立刻落盘：程序退出等关键节点必须调用，否则会丢掉最后几秒的记录。"""
        self._flush_timer.stop()
        self._flush()

    def has_pending_writes(self) -> bool:
        """是否有尚未落盘的改动（诊断 / 测试用）。"""
        return self._dirty

    # -- 记录 ------------------------------------------------------------- #
    def record(self, url: str, title: str) -> Optional[HistoryEntry]:
        """记录一次访问；同一地址只保留一条，累加访问次数并刷新时间。"""
        url = (url or "").strip()
        if not url or url in ("about:blank",) or url.startswith(("data:", "javascript:")):
            return None

        now = time.time()
        for entry in self._entries:
            if entry.url == url:
                entry.title = title or entry.title
                entry.visited_at = now
                entry.visit_count += 1
                self._sort()
                self.mark_dirty()
                self.changed.emit()
                return entry

        entry = HistoryEntry(url=url, title=(title or url).strip(), visited_at=now)
        self._entries.insert(0, entry)
        if len(self._entries) > self.max_entries:
            del self._entries[self.max_entries:]
        self.mark_dirty()
        self.changed.emit()
        return entry

    def _sort(self) -> None:
        self._entries.sort(key=lambda item: item.visited_at, reverse=True)

    # -- 查询 ------------------------------------------------------------- #
    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> list[HistoryEntry]:
        return list(self._entries)

    def grouped(self, keyword: str = "") -> list[tuple[str, list[HistoryEntry]]]:
        """按日期分组返回，日期最新的在前。"""
        keyword = (keyword or "").strip().lower()
        groups: dict[str, list[HistoryEntry]] = {}
        for entry in self._entries:
            if keyword and keyword not in entry.url.lower() and keyword not in entry.title.lower():
                continue
            groups.setdefault(entry.date_key, []).append(entry)
        return [
            (f"{key} {WEEKDAYS[datetime.strptime(key, '%Y-%m-%d').weekday()]}", groups[key])
            for key in sorted(groups.keys(), reverse=True)
        ]

    def search(self, keyword: str) -> list[HistoryEntry]:
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return list(self._entries)
        return [
            entry
            for entry in self._entries
            if keyword in entry.url.lower() or keyword in entry.title.lower()
        ]

    # -- 维护 ------------------------------------------------------------- #
    def remove_urls(self, urls: Iterable[str]) -> int:
        targets = set(urls)
        before = len(self._entries)
        self._entries = [entry for entry in self._entries if entry.url not in targets]
        removed = before - len(self._entries)
        if removed:
            self.save()
            self.changed.emit()
        return removed

    def clear(self) -> None:
        if not self._entries:
            return
        self._entries.clear()
        self.save()
        self.changed.emit()

    def purge_before(self, limit: float) -> int:
        """删除访问时间早于 ``limit`` 的记录。"""
        before = len(self._entries)
        self._entries = [entry for entry in self._entries if entry.visited_at >= limit]
        removed = before - len(self._entries)
        if removed:
            self.save()
            self.changed.emit()
        return removed

    def purge_older_than(self, days: int) -> int:
        """删除早于 N 天的记录（days <= 0 表示清空）。"""
        if days <= 0:
            count = len(self._entries)
            self.clear()
            return count
        return self.purge_before(time.time() - days * 86400)
