"""地址栏行为测试：回车提交、以及页面 URL 变化时不得覆盖用户正在输入的内容。

回归背景（用户实测反馈「输入网址后按回车没反应，只能点转到按钮」）：
``_on_url_changed()`` 会用引擎上报的 URL 覆盖地址栏文本。
用户点进地址栏开始输入后，首页加载完成 / 页面重定向同样会触发 URL 变化，
于是刚输入的网址被悄悄换回旧网址；此时按回车"看起来毫无反应"，
实际是导航到了被覆盖后的旧地址。稍后再点「转到」却正常，因为那时输入已经生效。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from litebrowser.browser import MainWindow  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


class _FakeConfig:
    def __init__(self) -> None:
        self.saved: dict[str, object] = {}

    def set(self, key, value, save=True):  # noqa: A003
        self.saved[key] = value

    def get(self, key, default=None):
        return default

    def search_url(self, text: str) -> str:
        return "https://search.example/?q=" + text.replace(" ", "+")


class _FakeEngine:
    """只保留 _on_url_changed 需要的接口。"""

    def __init__(self, url: str = "") -> None:
        self.address_override = ""
        self.url = url

    def current_url(self) -> str:
        return self.url


class _WindowStub:
    """承载真实 MainWindow 方法的替身（不启动真正的浏览器窗口）。"""

    #: 复用真实实现，避免测试里重复一份 URL 归一化逻辑
    normalize_url = staticmethod(MainWindow.normalize_url)
    address_keeps_user_input = staticmethod(MainWindow.address_keeps_user_input)

    def __init__(self, address: QLineEdit, engine: _FakeEngine) -> None:
        self.address = address
        self.config = _FakeConfig()
        self.engine = engine
        self.updated: list[str] = []

    def current_engine(self):
        return self.engine

    def navigate(self, url: str) -> None:
        self.updated.append(url)

    def _update_navigation(self, engine) -> None:
        return

    def _refresh_zoom_label(self) -> None:
        return

    def _update_security_indicator(self) -> None:
        return


class AddressBarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.address = QLineEdit()
        self.address.show()          # hasFocus 需要可见
        self.engine = _FakeEngine("https://home.example/")
        self.window = _WindowStub(self.address, self.engine)
        self.address.setFocus()
        _app.processEvents()

    def tearDown(self) -> None:
        self.address.deleteLater()

    # -- 真实方法的直接调用 ------------------------------------------------ #
    def _url_changed(self, url: str) -> None:
        MainWindow._on_url_changed(self.window, self.engine, url)  # noqa: SLF001

    def _navigate_from_address(self) -> None:
        MainWindow.navigate_from_address(self.window)  # noqa: SLF001

    # -- 核心回归：输入中不得被覆盖 ---------------------------------------- #
    def test_page_url_does_not_clobber_user_input(self) -> None:
        """用户正在输入时，页面 URL 变化不能替换地址栏内容。"""
        self.address.setText("")
        self.address.setText("baidu.com")
        self.address.setModified(True)          # 模拟真实键入
        self.assertTrue(self.address.hasFocus(), "前置条件：地址栏有焦点")

        self._url_changed("https://cn.bing.com/")

        self.assertEqual(self.address.text(), "baidu.com",
                         "页面 URL 变化不得覆盖用户正在输入的网址")

    def test_enter_after_url_change_navigates_to_typed_url(self) -> None:
        """回归主场景：输入 → 页面 URL 变化 → 回车，必须去用户输入的网址。"""
        self.address.setText("baidu.com")
        self.address.setModified(True)
        self._url_changed("https://cn.bing.com/")

        self.window.updated.clear()
        self._navigate_from_address()

        self.assertEqual(self.window.updated, ["https://baidu.com"],
                         "回车必须导航到用户输入的网址，而不是被覆盖后的旧网址")

    def test_unmodified_focus_still_follows_page(self) -> None:
        """只是点了一下地址栏（没改内容）时，仍应跟随页面 URL。"""
        self.address.setText("old.example")
        self.address.setModified(False)
        self._url_changed("https://new.example/page")
        self.assertEqual(self.address.text(), "https://new.example/page")

    def test_no_focus_follows_page(self) -> None:
        """失焦后（正常浏览）地址栏必须跟随页面 URL。"""
        self.address.clearFocus()
        _app.processEvents()
        self.address.setText("stale")
        self.address.setModified(True)
        self._url_changed("https://new.example/")
        self.assertEqual(self.address.text(), "https://new.example/")

    def test_same_text_is_not_treated_as_user_input(self) -> None:
        """输入内容与页面 URL 相同时无需保留（避免明明一致却不更新）。"""
        self.address.setText("https://same.example/")
        self.address.setModified(True)
        self._url_changed("https://same.example/")
        self.assertEqual(self.address.text(), "https://same.example/")

    # -- 提交后允许显示规范化网址 ------------------------------------------ #
    def test_commit_clears_modified_so_page_url_can_update_bar(self) -> None:
        """按回车/点转到提交后，地址栏应能显示规范化后的网址。"""
        self.address.setText("baidu.com")
        self.address.setModified(True)
        self.assertEqual(self.address.isModified(), True)

        self._navigate_from_address()
        self.assertEqual(self.window.updated, ["https://baidu.com"])
        self.assertFalse(self.address.isModified(), "提交后应清除 modified 标记")

        # 新页面加载完成 → 地址栏更新为规范化网址
        self._url_changed("https://www.baidu.com/")
        self.assertEqual(self.address.text(), "https://www.baidu.com/")

    def test_navigate_from_address_ignores_blank(self) -> None:
        self.address.setText("   ")
        self._navigate_from_address()
        self.assertEqual(self.window.updated, [], "空输入不应触发导航")

    # -- 辅助判定函数 ------------------------------------------------------ #
    def test_helper_predicate(self) -> None:
        keep = MainWindow.address_keeps_user_input
        self.address.setText("typed.example")
        self.address.setModified(True)
        self.address.setFocus()
        _app.processEvents()
        self.assertTrue(keep(self.address, "https://other.example/"))
        self.assertFalse(keep(self.address, "typed.example"))
        self.address.setModified(False)
        self.assertFalse(keep(self.address, "https://other.example/"))
        self.address.setModified(True)
        self.address.clearFocus()
        _app.processEvents()
        self.assertFalse(keep(self.address, "https://other.example/"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
