"""历史记录「合并写盘」行为测试。

背景：``record()`` 原本每次访问都做一次「O(n) 去重 + 全量 json 序列化 +
AES-256-GCM 加密 + 同步写盘」，而它跑在 UI 线程上；记录越多越慢，
是唯一一个会随使用时间必然变差的问题。改为防抖后必须保证：

* 数据**不会丢**（flush_now / 退出时落盘）；
* 数据**格式不变**（``{"version":1,"entries":[...]}`` + AES），老数据能读；
* 不脏时不重复写盘。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from litebrowser.crypto import DataVault  # noqa: E402
from litebrowser.history import HistoryEntry, HistoryStore  # noqa: E402

_app = QCoreApplication.instance() or QCoreApplication(sys.argv)


def _vault(root: Path) -> DataVault:
    vault = DataVault(root)
    vault.initialize()
    return vault


class _CountingVault(DataVault):
    """统计写盘次数，用于验证防抖确实减少了写操作。"""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.writes = 0

    def write_text(self, text, blob_path, legacy_path=None):  # noqa: D102
        self.writes += 1
        return super().write_text(text, blob_path, legacy_path)


class DebouncedWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.vault = _CountingVault(self.root)
        self.vault.initialize()
        self.store = HistoryStore(self.vault, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_record_does_not_write_immediately(self) -> None:
        """record() 只置脏，不立即写盘（这正是性能修复的要点）。"""
        self.store.record("https://a.example/", "A")
        self.assertFalse((self.root / "data" / "history.dat").exists(),
                         "record() 不应立即落盘")
        self.assertTrue(self.store.has_pending_writes())

    def test_many_records_write_once(self) -> None:
        """连续 20 次访问只应产生一次写盘（防抖生效）。"""
        for index in range(20):
            self.store.record(f"https://site{index}.example/", f"站点 {index}")
        self.assertEqual(self.vault.writes, 0, "record 期间不应写盘")

        self.store.flush_now()
        self.assertEqual(self.vault.writes, 1, "多次记录合并为一次写盘")

    def test_flush_now_persists_everything(self) -> None:
        urls = [f"https://site{index}.example/" for index in range(5)]
        for index, url in enumerate(urls):
            self.store.record(url, f"站点 {index}")
        self.store.flush_now()

        reopened = HistoryStore(_vault(self.root), self.root)
        self.assertEqual(len(reopened.entries()), 5)
        self.assertEqual({entry.url for entry in reopened.entries()}, set(urls))
        self.assertFalse(self.store.has_pending_writes(), "flush 后不应仍是脏的")

    def test_flush_when_clean_does_not_write_again(self) -> None:
        self.store.record("https://a.example/", "A")
        self.store.flush_now()
        writes_after_first = self.vault.writes
        self.store.flush_now()
        self.store.flush_now()
        self.assertEqual(self.vault.writes, writes_after_first,
                         "没有改动时 flush_now 不应重复写盘")

    def test_save_directly_clears_dirty(self) -> None:
        self.store.record("https://a.example/", "A")
        self.assertTrue(self.store.has_pending_writes())
        self.store.save()
        self.assertFalse(self.store.has_pending_writes(), "save() 之后不应仍是脏的")

    def test_duplicate_url_merges_and_flushes(self) -> None:
        for _ in range(3):
            self.store.record("https://same.example/", "同一个站点")
        self.store.flush_now()
        reopened = HistoryStore(_vault(self.root), self.root)
        self.assertEqual(len(reopened.entries()), 1)
        self.assertEqual(reopened.entries()[0].visit_count, 3)

    def test_flush_timer_is_configured(self) -> None:
        self.assertTrue(self.store._flush_timer.isSingleShot())  # noqa: SLF001
        self.assertEqual(self.store._flush_timer.interval(), HistoryStore.FLUSH_DELAY_MS)
        self.assertGreaterEqual(HistoryStore.FLUSH_DELAY_MS, 1000)

    def test_destructive_ops_still_write_immediately(self) -> None:
        """删除 / 清空属于用户主动操作，仍应立即落盘。"""
        self.store.record("https://a.example/", "A")
        self.store.flush_now()
        before = self.vault.writes

        removed = self.store.remove_urls(["https://a.example/"])
        self.assertEqual(removed, 1)
        self.assertGreater(self.vault.writes, before, "删除记录应立刻写盘")
        self.assertFalse(self.store.has_pending_writes())


class FormatCompatibilityTests(unittest.TestCase):
    """数据格式必须与 v1.7.0 完全一致，老用户数据能直接读。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.vault = _vault(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_payload_shape_unchanged(self) -> None:
        store = HistoryStore(self.vault, self.root)
        store.record("https://example.com/", "示例")
        store.flush_now()

        blob = self.root / "data" / "history.dat"
        self.assertTrue(blob.exists())
        text = self.vault.read_text(blob)
        payload = json.loads(text)
        self.assertEqual(payload["version"], 1, "版本号必须保持 1")
        self.assertIsInstance(payload["entries"], list)
        entry = payload["entries"][0]
        for key in ("url", "title", "visited_at", "visit_count"):
            self.assertIn(key, entry, f"字段 {key} 不能改名/缺失")

    def test_reads_data_written_by_older_version(self) -> None:
        """模拟 v1.7.0 写出的 history.dat（立即写盘、格式相同），新版本可读。"""
        legacy_payload = {
            "version": 1,
            "entries": [
                {"url": "https://old.example/", "title": "旧记录",
                 "visited_at": time.time() - 100, "visit_count": 7},
            ],
        }
        blob = self.root / "data" / "history.dat"
        self.vault.write_text(json.dumps(legacy_payload, ensure_ascii=False), blob)

        store = HistoryStore(self.vault, self.root)
        self.assertEqual(len(store.entries()), 1)
        self.assertEqual(store.entries()[0].url, "https://old.example/")
        self.assertEqual(store.entries()[0].visit_count, 7)

    def test_reads_legacy_plaintext_json(self) -> None:
        """更老的明文 history.json 仍应能迁移读入。"""
        legacy = self.root / "history.json"
        legacy.write_text(json.dumps({
            "version": 1,
            "entries": [{"url": "https://plain.example/", "title": "明文",
                         "visited_at": time.time() - 500, "visit_count": 1}],
        }, ensure_ascii=False), encoding="utf-8")
        store = HistoryStore(self.vault, self.root)
        self.assertEqual([entry.url for entry in store.entries()], ["https://plain.example/"])

    def test_entry_dict_round_trip(self) -> None:
        entry = HistoryEntry(url="https://a.example/", title="A", visited_at=time.time())
        self.assertEqual(HistoryEntry.from_dict(entry.to_dict()).url, "https://a.example/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
