"""内置下载模块：统一下载目录、进度管理、下载记录。"""

from __future__ import annotations

import logging

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from .crypto import DataVault

log = logging.getLogger(__name__)

STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELED = "canceled"

STATE_TEXT = {
    STATE_PENDING: "等待中",
    STATE_RUNNING: "正在下载",
    STATE_DONE: "已完成",
    STATE_FAILED: "失败",
    STATE_CANCELED: "已取消",
}


def human_size(size: float) -> str:
    if size is None or size < 0:
        return "未知"
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def unique_path(folder: Path, name: str) -> Path:
    """避免覆盖已有文件，自动追加 (1)、(2)…"""
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / name
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for index in range(1, 1000):
        candidate = folder / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    return folder / f"{stem} ({int(time.time())}){suffix}"


@dataclass
class DownloadItem:
    """一个下载任务。"""

    id: int
    url: str
    filename: str
    path: Path
    total: int = 0
    received: int = 0
    state: str = STATE_PENDING
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    error: str = ""
    cancel_callback: Optional[Callable[[], None]] = None

    @property
    def progress(self) -> int:
        if self.total > 0:
            return max(0, min(100, int(self.received * 100 / self.total)))
        return 100 if self.state == STATE_DONE else 0

    @property
    def size_text(self) -> str:
        if self.total > 0:
            return f"{human_size(self.received)} / {human_size(self.total)}"
        return human_size(self.received)

    @property
    def state_text(self) -> str:
        return STATE_TEXT.get(self.state, self.state)

    @property
    def started_text(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.started_at))

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "filename": self.filename,
            "path": str(self.path),
            "total": self.total,
            "received": self.received,
            "state": self.state if self.state != STATE_RUNNING else STATE_FAILED,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict, index: int) -> Optional["DownloadItem"]:
        path = str(data.get("path") or "")
        if not path:
            return None
        return cls(
            id=index,
            url=str(data.get("url") or ""),
            filename=str(data.get("filename") or Path(path).name),
            path=Path(path),
            total=int(data.get("total") or 0),
            received=int(data.get("received") or 0),
            state=str(data.get("state") or STATE_DONE),
            started_at=float(data.get("started_at") or 0) or time.time(),
            finished_at=float(data.get("finished_at") or 0),
            error=str(data.get("error") or ""),
        )


class DownloadManager(QObject):
    """下载任务集合 + 下载目录管理。

    下载目录规则：
    * 首次下载时由用户选择目录并保存到配置；
    * 之后默认使用该目录；
    * 用户可以在“设置 → 常规”或下载窗口中随时修改。
    """

    added = Signal(object)
    updated = Signal(object)
    changed = Signal()
    #: 下载完成（文件名, 所在目录）
    completed = Signal(str, str)

    def __init__(
        self,
        config,
        vault: DataVault,
        data_dir: Path,
        folder_asker: Optional[Callable[[str], Optional[str]]] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.vault = vault
        self.data_dir = Path(data_dir)
        self.blob_path = self.data_dir / "data" / "downloads.dat"
        self.legacy_path = self.data_dir / "downloads.json"
        self.folder_asker = folder_asker or (lambda _prompt: None)
        self._items: list[DownloadItem] = []
        self._next_id = 1
        #: 无痕模式：只在内存中保留下载列表，不写入磁盘
        self.incognito = False
        self.load()

    # -- 持久化 ----------------------------------------------------------- #
    def load(self) -> None:
        text = self.vault.read_text(self.blob_path, self.legacy_path)
        items: list[DownloadItem] = []
        if text:
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                payload = payload.get("items")
            if isinstance(payload, list):
                for index, raw in enumerate(payload):
                    if isinstance(raw, dict):
                        item = DownloadItem.from_dict(raw, index)
                        if item is not None:
                            items.append(item)
        self._items = items
        self._next_id = len(items) + 1

    def save(self) -> None:
        if self.incognito:
            return
        payload = {"version": 1, "items": [item.to_dict() for item in self._items]}
        try:
            self.vault.write_text(
                json.dumps(payload, ensure_ascii=False), self.blob_path, self.legacy_path
            )
        except OSError:
            pass

    # -- 下载目录 --------------------------------------------------------- #
    def default_folder(self) -> Path:
        folder = str(self.config.get("download_dir") or "").strip()
        if folder:
            return Path(folder)
        if sys.platform == "win32":
            return Path.home() / "Downloads"
        return Path.home()

    def set_default_folder(self, folder: str) -> None:
        self.config.set("download_dir", folder)

    def resolve_folder(self, *, first_time_hint: bool = True) -> Optional[str]:
        """确定本次下载使用的目录，必要时询问用户。"""
        folder = str(self.config.get("download_dir") or "").strip()
        ask_every = bool(self.config.get("ask_download_dir"))

        if folder and not ask_every:
            Path(folder).mkdir(parents=True, exist_ok=True)
            return folder

        prompt = "请选择下载文件的保存目录："
        if first_time_hint and not folder:
            prompt = "首次下载，请设定默认的下载保存目录："
        chosen = self.folder_asker(prompt)
        if not chosen:
            return None
        Path(chosen).mkdir(parents=True, exist_ok=True)
        self.set_default_folder(chosen)
        return chosen

    # -- 任务 ------------------------------------------------------------- #
    def begin(self, suggested_name: str, url: str) -> Optional[DownloadItem]:
        """开始一个下载任务；返回 None 表示用户取消。"""
        folder = self.resolve_folder()
        if not folder:
            return None
        name = Path(suggested_name or "download").name or "download"
        target = unique_path(Path(folder), name)

        item = DownloadItem(
            id=self._next_id,
            url=url,
            filename=target.name,
            path=target,
            state=STATE_RUNNING,
        )
        self._next_id += 1
        self._items.insert(0, item)
        self.save()
        self.added.emit(item)
        self.changed.emit()
        return item

    def update_progress(self, item: DownloadItem, received: int, total: int) -> None:
        item.received = max(0, int(received))
        if total and int(total) > 0:
            item.total = int(total)
        if item.state != STATE_RUNNING:
            item.state = STATE_RUNNING
        self.updated.emit(item)

    def finish(self, item: DownloadItem, ok: bool, error: str = "") -> None:
        item.finished_at = time.time()
        item.state = STATE_DONE if ok else STATE_FAILED
        item.error = "" if ok else (error or "下载失败")
        if ok and item.total:
            # 下载已成功：进度必须显示 100%，否则界面上会出现
            # "已完成 / 50%" 这类自相矛盾的状态
            item.received = item.total
        self.save()
        self.updated.emit(item)
        self.changed.emit()
        if ok:
            try:
                self.completed.emit(item.filename, str(item.path.parent))
            except Exception as lite_exc:
                log.debug("忽略异常：%s", lite_exc)
                pass

    def cancel(self, item: DownloadItem) -> None:
        if item.state not in (STATE_RUNNING, STATE_PENDING):
            return
        if item.cancel_callback is not None:
            try:
                item.cancel_callback()
            except Exception:
                pass
        item.state = STATE_CANCELED
        item.finished_at = time.time()
        self.save()
        self.updated.emit(item)
        self.changed.emit()

    def remove(self, item: DownloadItem) -> None:
        if item in self._items:
            self._items.remove(item)
            self.save()
            self.changed.emit()

    def clear_finished(self) -> None:
        self._items = [item for item in self._items if item.state in (STATE_RUNNING, STATE_PENDING)]
        self.save()
        self.changed.emit()

    def clear_all(self) -> None:
        for item in list(self._items):
            if item.state in (STATE_RUNNING, STATE_PENDING):
                self.cancel(item)
        self._items.clear()
        self.save()
        self.changed.emit()

    # -- 查询 ------------------------------------------------------------- #
    def items(self) -> list[DownloadItem]:
        return list(self._items)

    def active_count(self) -> int:
        return sum(1 for item in self._items if item.state in (STATE_RUNNING, STATE_PENDING))

    # -- 打开 ------------------------------------------------------------- #
    def open_file(self, item: DownloadItem) -> None:
        if not item.path.exists():
            return
        try:
            os.startfile(str(item.path))  # type: ignore[attr-defined]
        except Exception:
            subprocess.Popen(["explorer", str(item.path)])

    def open_folder(self, item: DownloadItem) -> None:
        folder = item.path.parent
        if not folder.exists():
            return
        if sys.platform == "win32":
            try:
                subprocess.Popen(["explorer", "/select,", str(item.path)])
                return
            except Exception:
                pass
        try:
            os.startfile(str(folder))  # type: ignore[attr-defined]
        except Exception:
            pass
