"""地址栏行为测试：回车提交、以及页面 URL 变化时不得覆盖用户正在输入的内容。

回归背景（用户实测反馈「输入网址后按回车没反应，只能点转到按钮」）：
``_on_url_changed()`` 会用引擎上报的 URL 覆盖地址栏文本。
用户点进地址栏开始输入后，首页加载完成 / 页面重定向同样会触发 URL 变化，
于是刚输入的网址被悄悄换回旧网址；此时按回车"看起来毫无反应"，
实际是导航到了被覆盖后的旧地址。稍后再点「转到」却正常，因为那时输入已经生效。

关于测试设计：这里用**可控的地址栏替身**（不依赖平台是否真的给得了键盘焦点）。
CI runner 没有交互桌面，真实 ``QLineEdit.hasFocus()`` 会返回 False，
若测试依赖它就会在 CI 上假失败。替身让"有焦点 + 内容被改动"这两个条件
完全确定，逻辑本身仍走 MainWindow 的真实实现。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from litebrowser.browser import MainWindow  # noqa: E402


class _AddressStub:
    """地址栏替身：精确控制 焦点 / 修改标记 / 文本。"""

    def __init__(self, text: str = "", *, focused: bool = True, modified: bool = False) -> None:
        self._text = text
        self._focused = focused
        self._modified = modified
        self.cursor_positions: list[int] = []

    # QLineEdit 上被 MainWindow 使用到的接口
    def text(self) -> str:
        return self._text

    def setText(self, value: str) -> None:
        self._text = value

    def setCursorPosition(self, position: int) -> None:
        self.cursor_positions.append(position)

    def hasFocus(self) -> bool:  # noqa: N802 - 与 Qt 命名保持一致
        return self._focused

    def isModified(self) -> bool:  # noqa: N802
        return self._modified

    def setModified(self, value: bool) -> None:  # noqa: N802
        self._modified = bool(value)

    def setFocus(self, *_args) -> None:
        self._focused = True

    def clearFocus(self) -> None:
        self._focused = False


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

    #: 复用真实实现，避免测试里重复一份逻辑
    normalize_url = staticmethod(MainWindow.normalize_url)
    address_keeps_user_input = staticmethod(MainWindow.address_keeps_user_input)

    def __init__(self, address: _AddressStub, engine: _FakeEngine) -> None:
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


class AddressBarLogicTests(unittest.TestCase):
    """不依赖真实焦点，任何平台都能稳定运行。"""

    def setUp(self) -> None:
        self.address = _AddressStub(text="https://home.example/", focused=False)
        self.engine = _FakeEngine("https://home.example/")
        self.window = _WindowStub(self.address, self.engine)

    def _url_changed(self, url: str) -> None:
        MainWindow._on_url_changed(self.window, self.engine, url)  # noqa: SLF001

    def _navigate_from_address(self) -> None:
        MainWindow.navigate_from_address(self.window)  # noqa: SLF001

    def _type(self, text: str) -> None:
        """模拟用户输入：内容变化 + 获得焦点 + modified 为真。"""
        self.address.setText(text)
        self.address.setFocus()
        self.address.setModified(True)

    # -- 核心回归：输入中不得被覆盖 ---------------------------------------- #
    def test_page_url_does_not_clobber_user_input(self) -> None:
        self._type("baidu.com")
        self._url_changed("https://cn.bing.com/")
        self.assertEqual(self.address.text(), "baidu.com",
                         "页面 URL 变化不得覆盖用户正在输入的网址")

    def test_enter_after_url_change_navigates_to_typed_url(self) -> None:
        """回归主场景：输入 → 页面 URL 变化 → 回车，必须去用户输入的网址。"""
        self._type("baidu.com")
        self._url_changed("https://cn.bing.com/")

        self.window.updated.clear()
        self._navigate_from_address()
        self.assertEqual(self.window.updated, ["https://baidu.com"],
                         "回车必须导航到用户输入的网址，而不是被覆盖后的旧网址")

    def test_repeated_url_changes_during_typing(self) -> None:
        """输入期间连续多次 URL 变化（重定向链）都不能冲掉输入。"""
        self._type("example.org")
        for url in ("https://a.example/", "https://b.example/", "https://c.example/"):
            self._url_changed(url)
        self.assertEqual(self.address.text(), "example.org")

    # -- 正常浏览行为必须保持不变 ------------------------------------------ #
    def test_unmodified_focus_still_follows_page(self) -> None:
        """只是点了一下地址栏（没改内容）时，仍应跟随页面 URL。"""
        self.address.setText("old.example")
        self.address.setFocus()
        self.address.setModified(False)
        self._url_changed("https://new.example/page")
        self.assertEqual(self.address.text(), "https://new.example/page")

    def test_no_focus_follows_page(self) -> None:
        """失焦后（正常浏览）地址栏必须跟随页面 URL。"""
        self.address.setText("stale")
        self.address.setModified(True)
        self.address.clearFocus()
        self._url_changed("https://new.example/")
        self.assertEqual(self.address.text(), "https://new.example/")

    def test_same_text_is_not_treated_as_user_input(self) -> None:
        """输入内容与页面 URL 相同时无需保留。"""
        self.address.setText("https://same.example/")
        self.address.setFocus()
        self.address.setModified(True)
        self._url_changed("https://same.example/")
        self.assertEqual(self.address.text(), "https://same.example/")

    def test_about_blank_protection_kept(self) -> None:
        """原有保护：有焦点时 about:blank 不覆盖地址栏。"""
        self.address.setText("keep.me")
        self.address.setFocus()
        self.address.setModified(False)
        self._url_changed("about:blank")
        self.assertEqual(self.address.text(), "keep.me")

    def test_address_override_still_wins(self) -> None:
        """内置页面（错误页 / 播放页）仍按 address_override 显示。"""
        self.engine.address_override = "https://original.example/"
        self._url_changed("file:///C:/temp/internal-x.html")
        self.assertEqual(self.address.text(), "https://original.example/")

    # -- 提交后允许显示规范化网址 ------------------------------------------ #
    def test_commit_clears_modified_so_page_url_can_update_bar(self) -> None:
        self._type("baidu.com")
        self.assertTrue(self.address.isModified())

        self._navigate_from_address()
        self.assertEqual(self.window.updated, ["https://baidu.com"])
        self.assertFalse(self.address.isModified(), "提交后应清除 modified 标记")

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
        self.assertTrue(keep(self.address, "https://other.example/"))
        self.assertFalse(keep(self.address, "typed.example"))
        self.address.setModified(False)
        self.assertFalse(keep(self.address, "https://other.example/"))
        self.address.setModified(True)
        self.address.clearFocus()
        self.assertFalse(keep(self.address, "https://other.example/"))

    def test_helper_tolerates_non_lineedit(self) -> None:
        """传进来的不是地址栏对象时应保守放行，不抛异常。"""
        self.assertFalse(MainWindow.address_keeps_user_input(object(), "https://a.example/"))


def _real_widget_focus_available() -> bool:
    """当前环境能否给真实控件键盘焦点（CI runner 通常不能）。"""
    try:
        from PySide6.QtWidgets import QApplication, QLineEdit

        app = QApplication.instance() or QApplication(sys.argv)
        widget = QLineEdit()
        widget.show()
        widget.setFocus()
        app.processEvents()
        focused = widget.hasFocus()
        widget.close()
        widget.deleteLater()
        app.processEvents()
        return bool(focused)
    except Exception:  # noqa: BLE001 - 没有可用平台插件时视为不可用
        return False


@unittest.skipUnless(_real_widget_focus_available(), "当前环境无法为控件提供键盘焦点")
class AddressBarRealWidgetTests(unittest.TestCase):
    """在能给焦点的环境（开发机）上，用真实 QLineEdit 再验证一次判定函数。"""

    def test_real_lineedit_predicate(self) -> None:
        from PySide6.QtWidgets import QApplication, QLineEdit

        app = QApplication.instance() or QApplication(sys.argv)
        widget = QLineEdit()
        widget.show()
        widget.setFocus()
        app.processEvents()
        try:
            widget.setText("typed.example")
            widget.setModified(True)
            self.assertTrue(
                MainWindow.address_keeps_user_input(widget, "https://other.example/")
            )
            widget.setModified(False)
            self.assertFalse(
                MainWindow.address_keeps_user_input(widget, "https://other.example/")
            )
        finally:
            widget.close()
            widget.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main(verbosity=2)
