"""性能管理：后台标签页挂起、内存与缓存统计。

* **挂起**：后台标签页闲置一段时间后调用内核的挂起接口
  （WebView2 的 ``TrySuspendAsync`` / QtWebEngine 的 ``Frozen`` 生命周期），
  内核会释放该页面的渲染进程与 JS 堆，重新切回时自动恢复；
* **统计**：主进程内存占用、磁盘缓存占用、挂起标签页数量，
  用于在「设置 → 性能」里直观看到优化效果。
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from .config import cache_dir, data_dir, profile_dir


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _load_memory_api():
    """加载 Windows 进程内存统计接口（必须声明 argtypes，否则句柄会被截断）。"""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        function = kernel32.K32GetProcessMemoryInfo
        function.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        function.restype = wintypes.BOOL
        return kernel32.GetCurrentProcess, function
    except Exception:
        return None, None


_GET_CURRENT_PROCESS, _QUERY_MEMORY = _load_memory_api()


def process_memory() -> tuple[int, int]:
    """返回 (工作集, 提交大小)，单位字节。"""
    if _QUERY_MEMORY is None:
        return 0, 0
    try:
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        handle = _GET_CURRENT_PROCESS()
        if not _QUERY_MEMORY(handle, ctypes.byref(counters), counters.cb):
            return 0, 0
        return int(counters.WorkingSetSize), int(counters.PagefileUsage)
    except Exception:
        return 0, 0


def folder_size(path: Path | str) -> int:
    """递归统计目录大小（字节）。"""
    total = 0
    try:
        for root, _dirs, files in os.walk(str(path)):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    continue
    except OSError:
        pass
    return total


def format_size(size: int) -> str:
    """人类可读的体积。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def format_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 1:
        return f"{seconds * 1000:.0f} 毫秒"
    if seconds < 60:
        return f"{seconds:.2f} 秒"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes} 分 {rest} 秒"


class PerformanceManager(QObject):
    """后台标签页挂起 + 统计。"""

    stats_changed = Signal(dict)

    def __init__(self, config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        #: 由主窗口注入：返回所有标签页引擎
        self.tabs_provider: Optional[Callable[[], list]] = None
        #: 由主窗口注入：返回当前标签页引擎
        self.current_provider: Optional[Callable[[], object]] = None
        self._last_active: dict[int, float] = {}
        self._started_at = time.time()
        self._timer = QTimer(self)
        self._timer.setInterval(20_000)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def note_active(self, engine) -> None:
        """记录某个标签页刚刚被激活。"""
        if engine is None:
            return
        self._last_active[id(engine)] = time.time()
        try:
            if engine.is_suspended():
                engine.resume()
        except Exception:
            pass

    def note_closed(self, engine) -> None:
        self._last_active.pop(id(engine), None)

    @property
    def enabled(self) -> bool:
        try:
            return bool(self.config.get("suspend_background_tabs"))
        except Exception:
            return False

    @property
    def delay_seconds(self) -> float:
        try:
            minutes = float(self.config.get("suspend_after_minutes") or 10)
        except Exception:
            minutes = 10.0
        return max(1.0, minutes) * 60.0

    def _tick(self) -> None:
        if not self.enabled or self.tabs_provider is None:
            return
        current = None
        try:
            current = self.current_provider() if self.current_provider else None
        except Exception:
            current = None

        now = time.time()
        delay = self.delay_seconds
        for engine in self.tabs_provider() or []:
            if engine is None:
                continue
            if engine is current:
                self.note_active(engine)
                continue
            last = self._last_active.get(id(engine))
            if last is None:
                self._last_active[id(engine)] = now
                continue
            if now - last < delay:
                continue
            # 正在播放音频/视频的标签页不挂起，否则会打断播放
            try:
                if engine.is_playing_audio():
                    self._last_active[id(engine)] = now
                    continue
            except Exception:
                pass
            try:
                if not engine.is_suspended():
                    engine.suspend()
            except Exception:
                continue
        self.emit_stats()

    def suspend_all_background(self) -> int:
        """立即挂起所有后台标签页，返回挂起数量（跳过正在播放的标签页）。"""
        current = None
        try:
            current = self.current_provider() if self.current_provider else None
        except Exception:
            current = None
        count = 0
        for engine in (self.tabs_provider() or []) if self.tabs_provider else []:
            if engine is None or engine is current:
                continue
            try:
                if engine.is_playing_audio():
                    continue
                if not engine.is_suspended():
                    engine.suspend()
                    count += 1
            except Exception:
                continue
        self.emit_stats()
        return count

    def resume_all(self) -> None:
        for engine in (self.tabs_provider() or []) if self.tabs_provider else []:
            try:
                engine.resume()
            except Exception:
                continue

    # ------------------------------------------------------------------ #
    # 统计
    # ------------------------------------------------------------------ #
    def cache_size(self) -> int:
        """磁盘缓存占用（两个内核的缓存目录之和）。"""
        return folder_size(cache_dir()) + folder_size(data_dir() / "webview2")

    def profile_size(self) -> int:
        return folder_size(profile_dir())

    def stats(self) -> dict:
        working_set, commit = process_memory()
        suspended = 0
        total = 0
        for engine in (self.tabs_provider() or []) if self.tabs_provider else []:
            total += 1
            try:
                if engine.is_suspended():
                    suspended += 1
            except Exception:
                continue
        return {
            "memory": working_set,
            "commit": commit,
            "cache": self.cache_size(),
            "profile": self.profile_size(),
            "tabs": total,
            "suspended": suspended,
            "uptime": time.time() - self._started_at,
        }

    def emit_stats(self) -> None:
        try:
            self.stats_changed.emit(self.stats())
        except Exception:
            pass
