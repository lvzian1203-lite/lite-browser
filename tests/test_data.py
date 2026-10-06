"""历史记录、下载管理与配置的单元测试。"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from litebrowser.config import Config  # noqa: E402
from litebrowser.crypto import DataVault  # noqa: E402
from litebrowser.downloads import DownloadManager  # noqa: E402
from litebrowser.history import HistoryStore  # noqa: E402

_app = QCoreApplication.instance() or QCoreApplication(sys.argv)


def _vault(root: Path) -> DataVault:
    vault = DataVault(root)
    vault.initialize()
    return vault


class HistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = HistoryStore(_vault(self.root), self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_record_normal_page(self) -> None:
        entry = self.store.record("https://example.com/page", "示例页面")
        self.assertIsNotNone(entry)
        self.assertEqual(len(self.store.entries()), 1)
        # 每条记录都带日期与时间（用户可见的时间标注）
        self.assertTrue(entry.date_text)
        self.assertTrue(entry.time_text)

    def test_duplicate_url_merges_and_counts(self) -> None:
        self.store.record("https://example.com/", "标题 A")
        self.store.record("https://example.com/", "标题 B")
        entries = self.store.entries()
        self.assertEqual(len(entries), 1, "同一地址应合并为一条")
        self.assertEqual(entries[0].visit_count, 2)

    def test_internal_schemes_are_not_recorded(self) -> None:
        for url in ("about:blank", "", "data:text/html,x", "javascript:void(0)"):
            with self.subTest(url=url):
                self.assertIsNone(self.store.record(url, "x"))
        self.assertEqual(self.store.entries(), [])

    def test_search_matches_title_and_url(self) -> None:
        self.store.record("https://www.bilibili.com/video/BV1", "哔哩哔哩视频")
        self.store.record("https://example.com/", "别的页面")
        self.assertEqual(len(self.store.search("bilibili")), 1)
        self.assertEqual(len(self.store.search("视频")), 1)
        self.assertEqual(len(self.store.search("不存在")), 0)

    def test_grouped_by_date(self) -> None:
        self.store.record("https://example.com/1", "一")
        self.store.record("https://example.com/2", "二")
        groups = self.store.grouped("")
        self.assertEqual(len(groups), 1, "同一天的记录应在一组")
        label, entries = groups[0]
        self.assertIn("星期", label)
        self.assertEqual(len(entries), 2)

    def test_retention_purge(self) -> None:
        self.store.record("https://old.example.com/", "旧记录")
        # 把时间改成 400 天前，再按 90 天保留清理
        self.store._entries[0].visited_at = time.time() - 400 * 86400  # noqa: SLF001
        removed = self.store.purge_older_than(90)
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.entries(), [])

    def test_persistence_round_trip(self) -> None:
        self.store.record("https://example.com/", "标题")
        reopened = HistoryStore(_vault(self.root), self.root)
        self.assertEqual(len(reopened.entries()), 1)
        self.assertEqual(reopened.entries()[0].title, "标题")

    def test_clear(self) -> None:
        self.store.record("https://example.com/", "x")
        self.store.clear()
        self.assertEqual(self.store.entries(), [])


class DownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # 用真实构造函数（QObject 子类不能用 __new__ 绕过 __init__），
        # 然后把配置路径指向临时目录，避免污染真实设置。
        self.config = Config()
        self.config.path = self.root / "settings.json"
        self.config._data = dict(Config.DEFAULTS)  # noqa: SLF001
        self.manager = DownloadManager(self.config, _vault(self.root), self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_first_download_asks_for_folder(self) -> None:
        asked: list[str] = []

        def asker(prompt: str):
            asked.append(prompt)
            return str(self.root / "downloads")

        self.manager.folder_asker = asker
        item = self.manager.begin("a.bin", "https://example.com/a.bin")
        self.assertIsNotNone(item)
        self.assertEqual(len(asked), 1, "首次下载应询问保存目录")
        self.assertEqual(str(self.manager.default_folder()), str(self.root / "downloads"))

    def test_second_download_reuses_folder(self) -> None:
        self.manager.set_default_folder(str(self.root / "dl"))
        item = self.manager.begin("b.bin", "https://example.com/b.bin")
        self.assertIsNotNone(item)
        self.assertEqual(item.path.parent, self.root / "dl")

    def test_cancel_when_user_refuses(self) -> None:
        self.manager.folder_asker = lambda _p: None
        self.assertIsNone(self.manager.begin("c.bin", "https://example.com/c.bin"))

    def test_progress_and_finish(self) -> None:
        self.manager.set_default_folder(str(self.root / "dl"))
        item = self.manager.begin("d.bin", "https://example.com/d.bin")
        self.manager.update_progress(item, 50, 100)
        self.assertEqual(item.progress, 50)
        self.manager.finish(item, True)
        self.assertEqual(item.progress, 100)
        self.assertEqual(item.state, "done")

    def test_completed_signal_carries_name_and_folder(self) -> None:
        self.manager.set_default_folder(str(self.root / "dl"))
        item = self.manager.begin("e.bin", "https://example.com/e.bin")
        received: list[tuple[str, str]] = []
        self.manager.completed.connect(lambda name, folder: received.append((name, folder)))
        self.manager.finish(item, True)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "e.bin")
        self.assertTrue(received[0][1].endswith("dl"))

    def test_failed_download_does_not_emit_completed(self) -> None:
        self.manager.set_default_folder(str(self.root / "dl"))
        item = self.manager.begin("f.bin", "https://example.com/f.bin")
        received: list[tuple[str, str]] = []
        self.manager.completed.connect(lambda name, folder: received.append((name, folder)))
        self.manager.finish(item, False, "网络错误")
        self.assertEqual(received, [])
        self.assertEqual(item.state, "failed")

    def test_persistence(self) -> None:
        self.manager.set_default_folder(str(self.root / "dl"))
        item = self.manager.begin("g.bin", "https://example.com/g.bin")
        self.manager.update_progress(item, 10, 100)
        self.manager.save()
        reopened = DownloadManager(self.config, _vault(self.root), self.root)
        self.assertEqual(len(reopened.items()), 1)
        self.assertEqual(reopened.items()[0].filename, "g.bin")


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _config(self) -> Config:
        config = Config()
        config.path = self.root / "settings.json"
        config._data = dict(Config.DEFAULTS)  # noqa: SLF001
        return config

    def test_defaults_include_privacy_relevant_keys(self) -> None:
        config = self._config()
        self.assertFalse(config.get("preload_links"), "DNS 预解析默认必须关闭")
        self.assertTrue(config.get("block_popups"))
        self.assertTrue(config.get("flash_compat"))
        self.assertTrue(config.get("block_malicious"))
        self.assertEqual(config.get("history_keep_days"), 90)

    def test_set_and_persist(self) -> None:
        config = self._config()
        config.set("ui_theme", "cat")
        config.save()
        reopened = Config()
        reopened.path = config.path
        reopened._data = dict(Config.DEFAULTS)  # noqa: SLF001
        reopened.load()
        self.assertEqual(reopened.get("ui_theme"), "cat")

    def test_unknown_keys_are_tolerated(self) -> None:
        config = self._config()
        self.assertEqual(config.get("no_such_key", "fallback"), "fallback")

    def test_search_url_builder(self) -> None:
        config = self._config()
        url = config.search_url("lite browser")
        self.assertTrue(url.startswith("http"))
        self.assertIn("lite", url)

    def test_removed_theme_falls_back(self) -> None:
        """旧配置里的已移除主题（mac）必须回退，不能白屏。"""
        from litebrowser import theme

        spec = theme.spec_for("mac", "light", "")
        self.assertEqual(spec.id, theme.DEFAULT_THEME)


class UrlNormalizationTests(unittest.TestCase):
    """地址栏输入 → URL 的转换规则。"""

    @classmethod
    def setUpClass(cls) -> None:
        from litebrowser.browser import MainWindow

        cls.normalize = staticmethod(MainWindow.normalize_url)

    @staticmethod
    def _search(text: str) -> str:
        return "https://search.example/?q=" + text.replace(" ", "+")

    def _norm(self, text: str) -> str:
        return self.normalize(text, self._search)

    def test_keeps_explicit_schemes(self) -> None:
        for url in ("https://example.com/", "http://example.com/", "file:///C:/x.html",
                    "about:blank", "view-source:https://a.com", "lite:video-check"):
            with self.subTest(url=url):
                self.assertEqual(self._norm(url), url)

    def test_adds_https_to_domains(self) -> None:
        self.assertEqual(self._norm("example.com"), "https://example.com")
        self.assertEqual(self._norm("cn.bing.com/"), "https://cn.bing.com/")
        self.assertEqual(self._norm("example.com:8443/x"), "https://example.com:8443/x")

    def test_adds_http_to_localhost_and_ip(self) -> None:
        self.assertEqual(self._norm("localhost:8000"), "http://localhost:8000")
        self.assertEqual(self._norm("127.0.0.1:5000/x"), "http://127.0.0.1:5000/x")

    def test_plain_words_go_to_search(self) -> None:
        result = self._norm("lite browser")
        self.assertIn("search.example", result)
        self.assertNotIn("https://lite", result)

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(self._norm(""), "")
        self.assertEqual(self._norm("   "), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
