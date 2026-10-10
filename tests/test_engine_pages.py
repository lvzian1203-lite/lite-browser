"""内置页面（错误页 / 可疑网址提示页）在多标签页下的文件隔离测试。

背景（v1.7.0 的缺陷）：
``show_error_page()`` 用**实例级**计数器 ``_page_seq`` 生成文件名，
而每个标签页是一个 ``BrowserEngine`` 实例，计数器都从 1 开始 →
两个标签页都写 ``internal-1.html``；
同时它还会 ``glob("internal-*.html")`` **删光共享目录下的所有同名文件**，
包括其它标签页正在显示的那一份。
结果是：A 标签页的错误页会被 B 标签页删掉/覆盖，
刷新后变成「文件不存在」，或显示成别的标签页的内容。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from litebrowser import engine as engine_mod  # noqa: E402
from litebrowser.engine import BrowserEngine  # noqa: E402

# BrowserEngine 是 QWidget 子类，必须用 QApplication（QCoreApplication 不够）
_app = QApplication.instance() or QApplication(sys.argv)


class _PageEngine(BrowserEngine):
    """只记录导航目标，不真正加载页面（避免依赖 WebView2 / QtWebEngine）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.navigations: list[str] = []

    def load(self, url: str) -> None:  # noqa: D102
        self.navigations.append(url)


class ErrorPageIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.pages = Path(self._tmp.name) / "pages"
        self._real_data_dir = engine_mod.data_dir
        engine_mod.data_dir = lambda: Path(self._tmp.name)  # type: ignore[assignment]
        self.engines: list[_PageEngine] = []

    def tearDown(self) -> None:
        for engine in self.engines:
            engine.deleteLater()
        engine_mod.data_dir = self._real_data_dir  # type: ignore[assignment]
        self._tmp.cleanup()

    def _engine(self) -> _PageEngine:
        engine = _PageEngine()
        self.engines.append(engine)
        return engine

    def _path_of(self, engine: _PageEngine) -> Path:
        """从 file:// URL 还原出错页文件路径。"""
        from urllib.parse import unquote, urlsplit

        self_url = engine.navigations[-1]
        self.assertEqual(urlsplit(self_url).scheme, "file")
        return Path(unquote(urlsplit(self_url).path.lstrip("/")))

    # -- 核心回归：两个标签页的文件不能互相影响 ---------------------------- #
    def test_second_tab_does_not_delete_first_tab_page(self) -> None:
        tab_a = self._engine()
        tab_b = self._engine()

        tab_a.show_error_page("<html>A 标签页的错误页</html>", "https://a.example/")
        path_a = self._path_of(tab_a)
        self.assertTrue(path_a.exists(), "A 标签页的错误页文件应存在")

        tab_b.show_error_page("<html>B 标签页的错误页</html>", "https://b.example/")
        path_b = self._path_of(tab_b)

        self.assertTrue(path_a.exists(), "B 打开错误页后，A 的错误页文件不能被删除")
        self.assertEqual(
            path_a.read_text(encoding="utf-8"), "<html>A 标签页的错误页</html>",
            "A 的错误页内容不能被 B 覆盖",
        )
        self.assertNotEqual(path_a, path_b, "两个标签页必须使用不同的文件名")
        self.assertTrue(path_b.exists())

    def test_repeated_pages_in_same_tab_are_distinct(self) -> None:
        engine = self._engine()
        engine.show_error_page("<html>第一次</html>", "https://a.example/")
        first = self._path_of(engine)
        engine.show_error_page("<html>第二次</html>", "https://b.example/")
        second = self._path_of(engine)
        self.assertNotEqual(first, second, "同一标签页多次显示也应换文件")
        self.assertEqual(second.read_text(encoding="utf-8"), "<html>第二次</html>")

    def test_many_tabs_all_keep_their_pages(self) -> None:
        paths = []
        for index in range(5):
            engine = self._engine()
            engine.show_error_page(f"<html>标签 {index}</html>", f"https://t{index}.example/")
            paths.append(self._path_of(engine))
        self.assertEqual(len(set(paths)), 5, "5 个标签页应有 5 个不同文件")
        for index, path in enumerate(paths):
            self.assertTrue(path.exists(), f"标签 {index} 的页面文件被删除了")
            self.assertEqual(path.read_text(encoding="utf-8"), f"<html>标签 {index}</html>")

    def test_page_content_round_trip_chinese(self) -> None:
        """错误页含中文与 emoji，写盘后按 UTF-8 读回必须一致。"""
        html = "<html><body>追鼠标的猫 🐱 ／ 可疑网址</body></html>"
        engine = self._engine()
        engine.show_error_page(html, "https://a.example/")
        self.assertEqual(self._path_of(engine).read_text(encoding="utf-8"), html)

    def test_address_override_is_recorded(self) -> None:
        engine = self._engine()
        engine.show_error_page("<html>x</html>", "https://a.example/path")
        self.assertEqual(engine.address_override, "https://a.example/path")
        self.assertTrue(engine._internal_page)  # noqa: SLF001 - 内部标记，回归需要

    # -- 残留清理：只回收超龄文件 ------------------------------------------ #
    def test_sweep_stale_keeps_fresh_files(self) -> None:
        self.pages.mkdir(parents=True, exist_ok=True)
        fresh = self.pages / "internal-fresh.html"
        fresh.write_text("fresh", encoding="utf-8")
        engine = self._engine()
        engine._sweep_stale(self.pages, max_age=3600.0)  # noqa: SLF001
        self.assertTrue(fresh.exists(), "刚写入的文件不能被清理（含其它标签页正在用的）")

    def test_sweep_stale_removes_old_files(self) -> None:
        self.pages.mkdir(parents=True, exist_ok=True)
        old = self.pages / "internal-old.html"
        old.write_text("old", encoding="utf-8")
        stale_time = time.time() - 7200
        os.utime(old, (stale_time, stale_time))

        engine = self._engine()
        engine._sweep_stale(self.pages, max_age=3600.0)  # noqa: SLF001
        self.assertFalse(old.exists(), "超龄的孤儿页面应被回收")

    def test_sweep_stale_ignores_other_files(self) -> None:
        self.pages.mkdir(parents=True, exist_ok=True)
        keep = self.pages / "swf-player.html"
        keep.write_text("player", encoding="utf-8")
        stale_time = time.time() - 7200
        os.utime(keep, (stale_time, stale_time))

        engine = self._engine()
        engine._sweep_stale(self.pages, max_age=3600.0)  # noqa: SLF001
        self.assertTrue(keep.exists(), "只清理 internal-*.html，不能动 .swf 播放页")

    def test_show_error_page_survives_unwritable_folder(self) -> None:
        """数据目录不可写时应静默放弃（不能抛异常打断标签页）。"""
        engine_mod.data_dir = lambda: Path(self._tmp.name) / "pages"  # type: ignore[assignment]
        blocker = Path(self._tmp.name) / "pages"
        blocker.write_text("我是文件不是目录", encoding="utf-8")
        engine = self._engine()
        engine.show_error_page("<html>x</html>", "https://a.example/")
        self.assertEqual(engine.navigations, [], "写不出文件时不应尝试导航")


if __name__ == "__main__":
    unittest.main(verbosity=2)
