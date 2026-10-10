"""界面主题与导航按钮重构的测试（v1.7.2）。

覆盖：
* 主题清单（win11 已删除，旧配置回退到哈基米）；
* 每个主题的导航风格字段合法（布局 / 尺寸 / 分组）；
* 分系统导航图标与线描工具图标在**每种风格**下都能画出来且非空白；
* 图标缓存按风格区分（同名图标在不同风格下是不同图形）；
* 每个主题的 QSS 都包含导航按钮规则，连体分组主题包含 navPos 规则。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LITE_BROWSER_DATA_DIR", str(Path(__file__).resolve().parent / "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from litebrowser import icons, theme  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

NAV_STYLES = {"classic", "aero", "flat", "modern", "harmony", "fluent"}
NAV_GROUPS = {"plain", "split", "circle"}


def ink(pixmap) -> int:
    """统计非透明像素数，用来判断图标是不是空白。"""
    image = pixmap.toImage()
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 20
    )


class ThemeRegistryTests(unittest.TestCase):
    def test_theme_count_and_order(self) -> None:
        self.assertEqual(len(theme.THEME_ORDER), 7)
        self.assertEqual(
            theme.THEME_ORDER,
            ["xp", "win98", "win7", "win81", "win10", "harmony", "cat"],
        )
        self.assertEqual(sorted(theme.THEMES), sorted(theme.THEME_ORDER))

    def test_win11_removed_and_falls_back_to_cat(self) -> None:
        self.assertNotIn("win11", theme.THEMES)
        self.assertNotIn("win11", theme.THEME_ORDER)
        self.assertEqual(theme.REMOVED_THEMES.get("win11"), "cat")
        self.assertEqual(theme.spec_for("win11").id, "cat",
                         "旧配置里的 win11 应回退到承载 Win11 风格的哈基米")

    def test_mac_still_falls_back_to_default(self) -> None:
        self.assertEqual(theme.spec_for("mac").id, theme.DEFAULT_THEME)

    def test_unknown_theme_falls_back(self) -> None:
        self.assertEqual(theme.spec_for("no-such-theme").id, theme.DEFAULT_THEME)

    def test_theme_names_are_available(self) -> None:
        pairs = theme.theme_names()
        self.assertEqual([item[0] for item in pairs], theme.THEME_ORDER)
        for _, name in pairs:
            self.assertTrue(name.strip(), "每个主题都要有可显示的名称")

    def test_dark_mode_keeps_nav_style(self) -> None:
        for tid in theme.THEME_ORDER:
            with self.subTest(theme=tid):
                dark = theme.spec_for(tid, "dark")
                self.assertEqual(dark.nav_style, theme.THEMES[tid].nav_style)
                self.assertTrue(dark.dark)


class NavStyleFieldTests(unittest.TestCase):
    def test_fields_are_valid(self) -> None:
        for tid in theme.THEME_ORDER:
            spec = theme.THEMES[tid]
            with self.subTest(theme=tid):
                self.assertIn(spec.nav_style, NAV_STYLES)
                self.assertIn(spec.nav_group, NAV_GROUPS)
                self.assertGreaterEqual(spec.nav_icon_size, 18)
                self.assertLessEqual(spec.nav_icon_size, 32)
                self.assertGreaterEqual(spec.nav_radius, 0)
                self.assertGreaterEqual(spec.nav_height, 0)
                self.assertGreaterEqual(spec.nav_hover_alpha, 0)

    def test_classic_themes_show_text_labels(self) -> None:
        """XP / 98 保留"图标 + 文字"的经典布局，其余主题为纯图标。"""
        for tid in ("xp", "win98"):
            self.assertTrue(theme.THEMES[tid].nav_show_text, tid)
        for tid in ("win7", "win81", "win10", "harmony", "cat"):
            self.assertFalse(theme.THEMES[tid].nav_show_text, tid)

    def test_expected_styles_per_theme(self) -> None:
        expected = {
            "xp": "classic", "win98": "classic", "win7": "aero", "win81": "flat",
            "win10": "modern", "harmony": "harmony", "cat": "fluent",
        }
        for tid, style in expected.items():
            self.assertEqual(theme.THEMES[tid].nav_style, style, tid)

    def test_only_win7_and_cat_use_joined_nav_group(self) -> None:
        joined = [tid for tid in theme.THEME_ORDER if theme.THEMES[tid].nav_group == "split"]
        self.assertEqual(joined, ["win7", "cat"])


class IconRenderingTests(unittest.TestCase):
    def test_nav_icons_render_in_every_style(self) -> None:
        """五颗导航按钮在每种系统风格下都要画得出来（不能是空白图标）。"""
        for style in sorted(NAV_STYLES):
            for name in icons.NAV_ICONS:
                with self.subTest(style=style, icon=name):
                    pixels = ink(icons.pixmap(name, 32, style))
                    self.assertGreater(pixels, 40, f"{style}/{name} 图标几乎是空白")

    def test_tool_icons_render_in_every_style(self) -> None:
        for style in sorted(NAV_STYLES):
            for name in icons._LINE_DRAWERS:  # noqa: SLF001 - 测试内部注册表
                with self.subTest(style=style, icon=name):
                    pixels = ink(icons.pixmap(name, 28, style))
                    self.assertGreater(pixels, 40, f"{style}/{name} 图标几乎是空白")

    def test_paw_style_icons_are_distinct_from_classic(self) -> None:
        """哈基米的导航图标必须有猫爪元素，因此与经典图标不同。"""
        for name in icons.NAV_ICONS:
            with self.subTest(icon=name):
                paw = icons.pixmap(name, 32, "fluent").toImage()
                classic = icons.pixmap(name, 32, "classic").toImage()
                self.assertNotEqual(paw, classic, f"{name} 的哈基米版本应与经典版不同")

    def test_paw_icon_contains_warm_colour(self) -> None:
        """猫爪用暖色（橙系）绘制，这里抽查图标里确实存在暖色像素。"""
        image = icons.pixmap("back", 32, "fluent").toImage()
        warm = 0
        for y in range(image.height()):
            for x in range(image.width()):
                colour = image.pixelColor(x, y)
                if colour.alpha() > 40 and colour.red() > 150 and colour.red() > colour.blue() + 40:
                    warm += 1
        self.assertGreater(warm, 10, "哈基米后退图标里应能看到暖色猫爪")

    def test_cache_is_keyed_by_style(self) -> None:
        icons.clear_cache()
        first = icons.pixmap("back", 24, "classic")
        second = icons.pixmap("back", 24, "modern")
        self.assertNotEqual(first.toImage(), second.toImage())
        self.assertEqual(len(icons._CACHE), 0, "pixmap() 不走缓存")  # noqa: SLF001

        icons.icon("back", 24, "classic")
        icons.icon("back", 24, "modern")
        self.assertEqual(len(icons._CACHE), 2, "icon() 应按 (名称, 尺寸, 风格) 缓存")  # noqa: SLF001

    def test_default_style_follows_current_theme(self) -> None:
        original = theme.current()
        try:
            theme.set_current(theme.CAT)
            cat_icon = icons.pixmap("back", 24)
            theme.set_current(theme.XP)
            xp_icon = icons.pixmap("back", 24)
            self.assertNotEqual(cat_icon.toImage(), xp_icon.toImage(),
                                "不传 style 时应按当前主题选风格")
        finally:
            theme.set_current(original)

    def test_non_themed_icons_stay_uniform(self) -> None:
        """锁 / 信息等非工具栏图标不应随主题变形（保持语义一致）。"""
        for name in ("lock", "info", "warn"):
            base = icons.pixmap(name, 24, "classic").toImage()
            for style in ("modern", "harmony", "fluent"):
                self.assertEqual(
                    icons.pixmap(name, 24, style).toImage(), base,
                    f"{name} 不该随风格变化",
                )


class StylesheetTests(unittest.TestCase):
    def test_every_theme_styles_nav_buttons(self) -> None:
        for tid in theme.THEME_ORDER:
            with self.subTest(theme=tid):
                qss = theme.stylesheet(theme.THEMES[tid])
                self.assertIn("QToolButton#navButton", qss)
                self.assertIn("QToolButton#navButton:hover", qss)
                self.assertIn("QToolButton#navButton:disabled", qss)

    def test_joined_group_styles_present_where_used(self) -> None:
        for tid in ("win7", "cat"):
            qss = theme.stylesheet(theme.THEMES[tid])
            self.assertIn('navPos="first"', qss, tid)
            self.assertIn('navPos="last"', qss, tid)

    def test_cat_theme_uses_translucent_hover(self) -> None:
        qss = theme.stylesheet(theme.THEMES["cat"])
        self.assertIn("rgba(", qss, "哈基米（Win11 风格）用半透明悬停底色")


if __name__ == "__main__":
    unittest.main(verbosity=2)
