"""界面主题引擎。

支持多套 UI 风格与浅色/深色模式，并可自定义边框颜色：

============  ==========================================================
``xp``        Windows XP (Luna) —— 蓝色渐变标题栏、圆角、立体按钮
``win98``     Windows 98/2000 经典 —— 灰色 3D 控件、深蓝直角标题栏
``win7``      Windows 7 (Aero) —— 浅蓝通透标题栏、柔和圆角
``win81``     Windows 8.1 —— 扁平纯色标题栏、直角、扁平按钮
``win10``     Windows 10 —— 极简扁平，标题栏与窗口同色 + 强调色底边
============  ==========================================================

颜色全部由 :class:`ThemeSpec` 描述，QSS 与自绘控件（标题栏、窗口边框）
都从同一份描述生成，因此切换主题只需重建 spec 并重新应用。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from PySide6.QtCore import QObject, Signal


class _ThemeNotifier(QObject):
    """主题变化通知：自绘控件（标题栏、窗口边框）与打开的对话框据此重绘。"""

    changed = Signal(object)


#: 全局主题通知器
notifier = _ThemeNotifier()


@dataclass(frozen=True)
class ThemeSpec:
    """一套完整的外观参数。"""

    id: str
    name: str
    dark: bool = False

    # 标题栏
    caption_style: str = "gradient"      # gradient | flat | classic
    caption_top: str = "#4C9BF7"
    caption_mid: str = "#0B5FE6"
    caption_bottom: str = "#0A46B8"
    caption_text: str = "#FFFFFF"
    caption_inactive_top: str = "#A8C2EE"
    caption_inactive_bottom: str = "#7E96C8"
    caption_inactive_text: str = "#F0F4FF"
    caption_highlight: bool = True        # 标题栏顶部高光
    caption_line: str = ""                # 标题栏底部强调线（Win11 风格）
    caption_side: str = "right"           # 标题栏按钮位置：right | left（macOS 风格）
    caption_badge: str = ""               # 标题栏前缀图案："" | "paw"（哈基米 UI）
    title_align: str = "left"             # 标题文字对齐：left | center

    # 窗口
    face: str = "#ECE9D8"
    face_alt: str = "#F5F3EA"
    border: str = "#0831A0"
    rounded: int = 8

    # 文字
    text: str = "#000000"
    text_disabled: str = "#9A9A9A"
    text_dim: str = "#6A6A6A"

    # 输入控件
    field_bg: str = "#FFFFFF"
    field_border: str = "#7F9DB9"
    highlight: str = "#316AC5"
    highlight_text: str = "#FFFFFF"

    # 菜单
    menu_bg: str = "#FFFFFF"
    menu_border: str = "#ACA899"

    # 工具栏按钮热区
    hot_top: str = "#FFFDF3"
    hot_bottom: str = "#FFE39B"
    hot_border: str = "#B6BDD2"

    # 导航按钮（后退 / 前进 / 停止 / 刷新 / 主页）
    # 每个主题按自己系统的真实浏览器做法来决定"布局 + 图标风格"：
    #   classic —— 图标 + 文字（IE6/XP 时代）
    #   aero    —— 图标按钮带玻璃高光，后退/前进合并成一组（IE8/7）
    #   flat    —— 无圆角、纯箭头，悬停方框（IE11/8.1）
    #   modern  —— Fluent 细线箭头、较大图标（Edge/10）
    #   harmony —— 粗线条 + 圆形悬停底（鸿蒙）
    #   fluent  —— Win11 圆角胶囊悬停；图标为"猫爪 + 功能"组合（哈基米）
    nav_style: str = "classic"
    nav_icon_size: int = 22
    nav_show_text: bool = True      # 图标旁是否显示文字
    nav_radius: int = 3             # 导航按钮圆角
    nav_group: str = "plain"        # plain | split（后退/前进连成一体）| circle（圆形悬停）
    nav_height: int = 0             # 0 = 由样式表自动决定
    nav_hover_alpha: int = 0        # >0 时用半透明悬停底色（Win11 风格）

    # 普通按钮
    button_top: str = "#FFFFFF"
    button_mid: str = "#F4F2EC"
    button_bottom: str = "#E2DFD2"
    button_border: str = "#003C74"
    button_hover_top: str = "#FFFDF5"
    button_hover_bottom: str = "#FFE39B"
    button_pressed: str = "#DCD7C6"
    button_disabled_bg: str = "#F1EFE7"
    button_disabled_border: str = "#B4B0A3"
    button_flat: bool = False

    # 标签页
    tab_bg_top: str = "#FFFFFF"
    tab_bg_bottom: str = "#E1DDCE"
    tab_selected_bg: str = "#FFFFFF"
    tab_border: str = "#919B9C"

    # 其它
    statusbar_bg: str = "#ECE9D8"
    progress_top: str = "#C7EFA8"
    progress_mid: str = "#7CD24A"
    progress_bottom: str = "#47A62A"
    scroll_bg: str = "#F1EFE2"
    scroll_thumb_top: str = "#FFFFFF"
    scroll_thumb_bottom: str = "#9DB6DC"
    scroll_thumb_border: str = "#7F9DB9"


# --------------------------------------------------------------------------- #
# 内置主题（浅色）
# --------------------------------------------------------------------------- #
XP = ThemeSpec(
    id="xp",
    name="Windows XP (Luna)",
    nav_style="classic", nav_icon_size=22,
    nav_show_text=True, nav_radius=3, nav_group="plain",
    nav_height=0, nav_hover_alpha=0,
    caption_top="#4C9BF7", caption_mid="#0B5FE6", caption_bottom="#0A46B8",
    face="#ECE9D8", face_alt="#F5F3EA", border="#0831A0", rounded=8,
    text_dim="#4A4A4A", text_disabled="#8A8A8A",
)

WIN98 = ThemeSpec(
    id="win98",
    name="Windows 98 / 2000 经典",
    nav_style="classic", nav_icon_size=22,
    nav_show_text=True, nav_radius=0, nav_group="plain",
    nav_height=0, nav_hover_alpha=0,
    caption_style="classic",
    caption_top="#000080", caption_mid="#000080", caption_bottom="#1084D0",
    caption_inactive_top="#808080", caption_inactive_bottom="#808080",
    caption_inactive_text="#D4D0C8", caption_highlight=False,
    face="#D4D0C8", face_alt="#E4E0D8", border="#404040", rounded=0,
    text_dim="#3F3F3F",
    field_border="#808080", highlight="#000080",
    menu_bg="#D4D0C8", menu_border="#404040",
    hot_top="#E8E5DF", hot_bottom="#D4D0C8", hot_border="#808080",
    button_top="#E8E5DF", button_mid="#D4D0C8", button_bottom="#D4D0C8",
    button_border="#404040", button_hover_top="#F0EDE7", button_hover_bottom="#DCD8D0",
    button_pressed="#C0BCB4", button_disabled_bg="#D4D0C8",
    button_disabled_border="#9A9A9A",
    tab_bg_top="#D4D0C8", tab_bg_bottom="#C0BCB4", tab_selected_bg="#D4D0C8",
    tab_border="#808080", statusbar_bg="#D4D0C8",
    progress_top="#B7DCA0", progress_mid="#6BC24A", progress_bottom="#3E9B34",
    scroll_bg="#D4D0C8", scroll_thumb_top="#E8E5DF", scroll_thumb_bottom="#B8B4AC",
    scroll_thumb_border="#808080",
)

WIN7 = ThemeSpec(
    id="win7",
    name="Windows 7 (Aero)",
    nav_style="aero", nav_icon_size=24,
    nav_show_text=False, nav_radius=4, nav_group="split",
    nav_height=0, nav_hover_alpha=0,
    caption_top="#DCEBFB", caption_mid="#B6D3F0", caption_bottom="#8CB4DE",
    caption_text="#0A2A4A",
    caption_inactive_top="#F2F2F2", caption_inactive_bottom="#DCDCDC",
    caption_inactive_text="#6A6A6A",
    face="#F0F0F0", face_alt="#F8F8F8", border="#5A7EA8", rounded=6,
    text="#1A1A1A", text_disabled="#8F8F8F", text_dim="#4F4F4F",
    field_border="#A5B8CE", highlight="#3C7FB1",
    menu_bg="#F7F7F7", menu_border="#A0A0A0",
    hot_top="#EAF3FB", hot_bottom="#CFE3F5", hot_border="#7EA8D0",
    button_top="#FDFEFE", button_mid="#F0F4F8", button_bottom="#DCE6F0",
    button_border="#8FA8C0", button_hover_top="#F2F9FF", button_hover_bottom="#D3E8FA",
    button_pressed="#C6DCF0", button_disabled_bg="#F2F2F2",
    button_disabled_border="#C4C4C4",
    tab_bg_top="#F2F7FC", tab_bg_bottom="#DCE7F2", tab_selected_bg="#FFFFFF",
    tab_border="#A5B8CE", statusbar_bg="#F0F0F0",
    progress_top="#CDE9BC", progress_mid="#8CD45F", progress_bottom="#57AE3A",
    scroll_bg="#F0F0F0", scroll_thumb_top="#FBFDFF", scroll_thumb_bottom="#C3D6E8",
    scroll_thumb_border="#9DB6CC",
)

WIN81 = ThemeSpec(
    id="win81",
    name="Windows 8.1",
    nav_style="flat", nav_icon_size=22,
    nav_show_text=False, nav_radius=0, nav_group="plain",
    nav_height=0, nav_hover_alpha=0,
    caption_style="flat",
    caption_top="#2B579A", caption_mid="#2B579A", caption_bottom="#1F4278",
    caption_inactive_top="#C8C8C8", caption_inactive_bottom="#B4B4B4",
    caption_inactive_text="#5A5A5A", caption_highlight=False,
    face="#F2F2F2", face_alt="#FAFAFA", border="#1F4278", rounded=0,
    text="#1A1A1A", text_disabled="#8F8F8F", text_dim="#4F4F4F",
    field_border="#A9A9A9", highlight="#2B579A",
    menu_bg="#FFFFFF", menu_border="#C0C0C0",
    hot_top="#E8EFF8", hot_bottom="#D2E0F0", hot_border="#A8C0DC",
    button_top="#FCFCFC", button_mid="#F4F4F4", button_bottom="#EAEAEA",
    button_border="#ADADAD", button_hover_top="#F0F6FD", button_hover_bottom="#DCE8F6",
    button_pressed="#D8E3F0", button_disabled_bg="#F4F4F4",
    button_disabled_border="#CFCFCF", button_flat=True,
    tab_bg_top="#FAFAFA", tab_bg_bottom="#E8E8E8", tab_selected_bg="#FFFFFF",
    tab_border="#C0C0C0", statusbar_bg="#F2F2F2",
    progress_top="#CDE9BC", progress_mid="#8CD45F", progress_bottom="#57AE3A",
    scroll_bg="#F2F2F2", scroll_thumb_top="#FCFCFC", scroll_thumb_bottom="#C8C8C8",
    scroll_thumb_border="#A9A9A9",
)

WIN10 = ThemeSpec(
    id="win10",
    name="Windows 10",
    nav_style="modern", nav_icon_size=24,
    nav_show_text=False, nav_radius=3, nav_group="plain",
    nav_height=0, nav_hover_alpha=0,
    caption_style="flat",
    caption_top="#F3F3F3", caption_mid="#F3F3F3", caption_bottom="#F3F3F3",
    caption_text="#1A1A1A",
    caption_inactive_top="#FAFAFA", caption_inactive_bottom="#FAFAFA",
    caption_inactive_text="#8A8A8A", caption_highlight=False,
    caption_line="#0067C0",
    face="#F3F3F3", face_alt="#FAFAFA", border="#D6D6D6", rounded=0,
    text="#1A1A1A", text_disabled="#8F8F8F", text_dim="#4D4D4D",
    field_border="#B8B8B8", highlight="#0067C0",
    menu_bg="#FBFBFB", menu_border="#D0D0D0",
    hot_top="#E9F1FB", hot_bottom="#D6E6F8", hot_border="#B0C8E0",
    button_top="#FDFDFD", button_mid="#F5F5F5", button_bottom="#EBEBEB",
    button_border="#C6C6C6", button_hover_top="#F2F7FD", button_hover_bottom="#DEEAF8",
    button_pressed="#DAE6F4", button_disabled_bg="#F5F5F5",
    button_disabled_border="#D6D6D6", button_flat=True,
    tab_bg_top="#FAFAFA", tab_bg_bottom="#ECECEC", tab_selected_bg="#FFFFFF",
    tab_border="#D0D0D0", statusbar_bg="#F3F3F3",
    progress_top="#CFE9C0", progress_mid="#8ED162", progress_bottom="#5AAE3E",
    scroll_bg="#F3F3F3", scroll_thumb_top="#FDFDFD", scroll_thumb_bottom="#CACACA",
    scroll_thumb_border="#B8B8B8",
)

HARMONY = ThemeSpec(
    id="harmony",
    name="HarmonyOS（鸿蒙）",
    nav_style="harmony", nav_icon_size=24,
    nav_show_text=False, nav_radius=13, nav_group="circle",
    nav_height=30, nav_hover_alpha=0,
    caption_style="flat",
    caption_top="#FFFFFF", caption_mid="#FFFFFF", caption_bottom="#FAFAFC",
    caption_text="#182431",
    caption_inactive_top="#F7F8FA", caption_inactive_bottom="#F2F3F5",
    caption_inactive_text="#9AA0A6",
    caption_highlight=False, caption_line="#007DFF",
    face="#F1F3F5", face_alt="#F8F9FB", border="#DCE0E5", rounded=8,
    text="#182431", text_disabled="#9AA0A6", text_dim="#4A5560",
    field_bg="#FFFFFF", field_border="#D4D8DE", highlight="#007DFF",
    menu_bg="#FFFFFF", menu_border="#E0E4E9",
    hot_top="#EEF5FF", hot_bottom="#DCEAFF", hot_border="#A8CBFF",
    button_top="#FFFFFF", button_mid="#F7F9FC", button_bottom="#EDF1F6",
    button_border="#D4D8DE", button_hover_top="#F2F7FF", button_hover_bottom="#E0EDFF",
    button_pressed="#D6E6FF", button_disabled_bg="#F4F6F8",
    button_disabled_border="#E0E4E9", button_flat=True,
    tab_bg_top="#F7F9FC", tab_bg_bottom="#EBEFF4", tab_selected_bg="#FFFFFF",
    tab_border="#DCE0E5", statusbar_bg="#F1F3F5",
    progress_top="#CFE4FF", progress_mid="#5AA0FF", progress_bottom="#007DFF",
    scroll_bg="#F1F3F5", scroll_thumb_top="#FFFFFF", scroll_thumb_bottom="#CBD2DA",
    scroll_thumb_border="#D4D8DE",
)

CAT = ThemeSpec(
    id="cat",
    name="哈基米（猫猫）",
    nav_style="fluent", nav_icon_size=26,
    nav_show_text=False, nav_radius=9, nav_group="split",
    nav_height=32, nav_hover_alpha=22,
    caption_style="gradient",
    caption_top="#FFE3B8", caption_mid="#FFC97A", caption_bottom="#F5A94E",
    caption_text="#5A3410",
    caption_inactive_top="#F6E9D8", caption_inactive_bottom="#EBD9C2",
    caption_inactive_text="#9A8570",
    caption_highlight=True, caption_badge="paw",
    face="#FFF6E9", face_alt="#FFFBF4", border="#E0A860", rounded=12,
    text="#4A2F14", text_disabled="#B49A7C", text_dim="#6E4E2C",
    field_bg="#FFFDF8", field_border="#E4C79A", highlight="#FF9A3C",
    highlight_text="#4A2F14",
    menu_bg="#FFFBF3", menu_border="#EBD3AF",
    hot_top="#FFF3DF", hot_bottom="#FFE3B8", hot_border="#E8BC7C",
    button_top="#FFFDF8", button_mid="#FFF4E3", button_bottom="#FFE7C4",
    button_border="#E0A860", button_hover_top="#FFF6E6", button_hover_bottom="#FFDCA6",
    button_pressed="#F7D9A8", button_disabled_bg="#F7EFE2",
    button_disabled_border="#DCC4A2",
    tab_bg_top="#FFF3E0", tab_bg_bottom="#FFE6C4", tab_selected_bg="#FFFDF8",
    tab_border="#E4C79A", statusbar_bg="#FFF6E9",
    progress_top="#FFE0A8", progress_mid="#FFB65C", progress_bottom="#F08A2E",
    scroll_bg="#FFF6E9", scroll_thumb_top="#FFE7C4", scroll_thumb_bottom="#E8BC7C",
    scroll_thumb_border="#D8A96A",
)

THEMES: dict[str, ThemeSpec] = {
    item.id: item
    for item in (XP, WIN98, WIN7, WIN81, WIN10, HARMONY, CAT)
}
THEME_ORDER = ["xp", "win98", "win7", "win81", "win10", "harmony", "cat"]
DEFAULT_THEME = "xp"
#: 已移除的主题 → 回退目标（旧配置里的 mac 自动换成 xp、win11 换成 cat，
#: 避免升级后变成未知主题；哈基米 UI 现在承载 Win11 风格）
REMOVED_THEMES = {"mac": DEFAULT_THEME, "win11": "cat"}


# --------------------------------------------------------------------------- #
# 深色模式
# --------------------------------------------------------------------------- #
def _darken(spec: ThemeSpec) -> ThemeSpec:
    """把一套浅色主题转成深色配色。"""
    dark = replace(
        spec,
        dark=True,
        face="#2B2B2B",
        face_alt="#323232",
        border="#4A4A4A",
        text="#E8E8E8",
        text_disabled="#7A7A7A",
        text_dim="#A8A8A8",
        field_bg="#1E1E1E",
        field_border="#5A5A5A",
        highlight="#2A5BA8",
        highlight_text="#FFFFFF",
        menu_bg="#2B2B2B",
        menu_border="#4A4A4A",
        hot_top="#3D3D3D",
        hot_bottom="#4A4A4A",
        hot_border="#5A5A5A",
        button_top="#3A3A3A",
        button_mid="#343434",
        button_bottom="#2E2E2E",
        button_border="#5A5A5A",
        button_hover_top="#444444",
        button_hover_bottom="#4E4E4E",
        button_pressed="#262626",
        button_disabled_bg="#2E2E2E",
        button_disabled_border="#3E3E3E",
        tab_bg_top="#343434",
        tab_bg_bottom="#2A2A2A",
        tab_selected_bg="#3A3A3A",
        tab_border="#4A4A4A",
        statusbar_bg="#2B2B2B",
        scroll_bg="#2B2B2B",
        scroll_thumb_top="#4A4A4A",
        scroll_thumb_bottom="#3A3A3A",
        scroll_thumb_border="#5A5A5A",
    )

    if spec.id == "win10":
        return replace(
            dark,
            caption_top="#202020", caption_mid="#202020", caption_bottom="#202020",
            caption_text="#F0F0F0",
            caption_inactive_top="#2A2A2A", caption_inactive_bottom="#2A2A2A",
            caption_inactive_text="#8A8A8A",
        )
    if spec.id == "win7":
        return replace(
            dark,
            caption_top="#3E4A57", caption_mid="#333D48", caption_bottom="#2A323B",
            caption_text="#E8EEF5",
            caption_inactive_top="#3A3A3A", caption_inactive_bottom="#303030",
            caption_inactive_text="#9A9A9A",
        )
    return replace(
        dark,
        caption_top="#1B3A6B", caption_mid="#14305C", caption_bottom="#0E2445",
        caption_text="#F0F4FF",
        caption_inactive_top="#3A3A3A", caption_inactive_bottom="#2E2E2E",
        caption_inactive_text="#9A9A9A",
    )


# --------------------------------------------------------------------------- #
# 自定义边框 / 强调色
# --------------------------------------------------------------------------- #
def mix(color: str, other: str, ratio: float) -> str:
    """按比例混合两个 #RRGGBB 颜色。"""
    try:
        a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    except (ValueError, IndexError):
        return color
    mixed = [int(round(a[i] * (1 - ratio) + b[i] * ratio)) for i in range(3)]
    return "#%02X%02X%02X" % tuple(max(0, min(255, item)) for item in mixed)


def with_accent(spec: ThemeSpec, accent: str) -> ThemeSpec:
    """应用自定义边框/标题栏颜色。"""
    if not accent or not accent.startswith("#") or len(accent) != 7:
        return spec

    if spec.caption_style == "gradient":
        caption = dict(
            caption_top=mix(accent, "#FFFFFF", 0.34),
            caption_mid=accent,
            caption_bottom=mix(accent, "#000000", 0.22),
        )
    else:
        caption = dict(
            caption_top=accent,
            caption_mid=accent,
            caption_bottom=mix(accent, "#000000", 0.18),
            caption_text="#FFFFFF",
        )
    return replace(
        spec,
        border=accent,
        caption_line=accent if spec.caption_line else spec.caption_line,
        highlight=accent,
        **caption,
    )


# --------------------------------------------------------------------------- #
# 当前主题
# --------------------------------------------------------------------------- #
_current: ThemeSpec = XP


def apply_palette(app, spec: ThemeSpec) -> None:
    """把主题配色写进 QApplication 调色板。

    Windows 处于深色模式时，Qt 默认调色板本身就是深色的，凡是样式表没有
    显式配色的控件（滚动区视口、分组框、提示框等）都会变成黑底，
    浅色主题下文字就压成了“深灰字 + 黑底”，很难看清。
    这里统一覆盖调色板，保证所有控件底色与主题一致。
    """
    from PySide6.QtGui import QColor, QPalette

    palette = QPalette()
    face = QColor(spec.face)
    text = QColor(spec.text)
    field = QColor(spec.field_bg)
    disabled = QColor(spec.text_disabled)

    palette.setColor(QPalette.Window, face)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, field)
    palette.setColor(QPalette.AlternateBase, QColor(spec.face_alt))
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, face)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.Highlight, QColor(spec.highlight))
    palette.setColor(QPalette.HighlightedText, QColor(spec.highlight_text))
    palette.setColor(QPalette.ToolTipBase, QColor(spec.menu_bg))
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.PlaceholderText, disabled)
    palette.setColor(QPalette.Link, QColor(spec.highlight))
    palette.setColor(QPalette.Mid, QColor(spec.border))
    palette.setColor(QPalette.Midlight, QColor(spec.face_alt))
    palette.setColor(QPalette.Dark, QColor(spec.border))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, disabled)
    app.setPalette(palette)


def apply_theme(app, spec: ThemeSpec) -> None:
    """应用主题：先设调色板（管住未显式配色的控件），再设样式表。"""
    apply_palette(app, spec)
    app.setStyleSheet(stylesheet(spec))


def spec_for(theme_id: str, mode: str = "light", accent: str = "") -> ThemeSpec:
    """根据设置生成最终主题描述。

    :param theme_id: xp / win98 / win7 / win81 / win10 / harmony / cat
        （已移除的 mac 回退到 xp、win11 回退到 cat）
    :param mode: light | dark
    :param accent: 自定义边框颜色（#RRGGBB），空字符串表示使用主题默认
    """
    theme_id = REMOVED_THEMES.get(str(theme_id or ""), theme_id)
    base = THEMES.get(theme_id or DEFAULT_THEME, XP)
    if (mode or "light").lower() == "dark":
        base = _darken(base)
    return with_accent(base, accent)


def current() -> ThemeSpec:
    return _current


def set_current(spec: ThemeSpec) -> None:
    global _current
    _current = spec
    try:
        notifier.changed.emit(spec)
    except Exception:
        pass


def status_colors(spec: Optional[ThemeSpec] = None) -> dict:
    """状态色（随深色/浅色模式调整对比度）。"""
    t = spec or _current
    if t.dark:
        return {
            "ok": "#6FD08C",
            "warn": "#F0C13A",
            "error": "#FF8A80",
            "error_bg": "#4A2320",
            "ok_bg": "#1E3A26",
        }
    return {
        "ok": "#1E7B34",
        "warn": "#8A6A00",
        "error": "#B02A1E",
        "error_bg": "#FDECEA",
        "ok_bg": "#EAF6EC",
    }


def theme_names() -> list[tuple[str, str]]:
    return [(item, THEMES[item].name) for item in THEME_ORDER]


def caption_height(spec: Optional[ThemeSpec] = None) -> int:
    t = spec or _current
    return 30 if t.id == "win10" else 28


# --------------------------------------------------------------------------- #
# 样式表
# --------------------------------------------------------------------------- #
def _grad(*colors: str) -> str:
    stops = []
    count = max(1, len(colors) - 1)
    for index, color in enumerate(colors):
        stops.append(f"stop:{index / count:.3f} {color}")
    return "qlineargradient(x1:0, y1:0, x2:0, y2:1, " + ", ".join(stops) + ")"


def _grad_h(*colors: str) -> str:
    stops = []
    count = max(1, len(colors) - 1)
    for index, color in enumerate(colors):
        stops.append(f"stop:{index / count:.3f} {color}")
    return "qlineargradient(x1:0, y1:0, x2:1, y2:0, " + ", ".join(stops) + ")"


def nav_qss(t: "ThemeSpec") -> str:
    """导航按钮（后退/前进/停止/刷新/主页）的样式：按各系统的真实做法区分。

    These buttons are tagged ``objectName="navButton"`` in the toolbar
    (win7 / 哈基米 additionally wrap 后退/前进 in ``navGroup``), so this block
    only affects the navigation area and leaves other tool buttons alone.
    """
    from PySide6.QtGui import QColor  # 与本文件其它地方一致：延后导入 QtGui

    radius = t.nav_radius
    height = t.nav_height or 0
    height_rule = f"min-height: {height}px; max-height: {height}px;" if height else ""
    style = t.nav_style

    if style == "aero":
        # Win7：玻璃质感，悬停是淡蓝渐变 + 细边框，按下更深
        return f"""
QToolButton#navButton {{
    padding: 1px 5px; margin: 0px; border: 1px solid transparent;
    border-radius: {radius}px; {height_rule}
}}
QToolButton#navButton:hover {{
    border: 1px solid #8FB6DC;
    background: {_grad("#F4FAFF", "#D6E8F8")};
}}
QToolButton#navButton:pressed {{
    border: 1px solid #6E9BC6;
    background: {_grad("#CFE2F5", "#B7D3EE")};
}}
QToolButton#navButton:disabled {{ color: {t.text_disabled}; }}
QToolButton#navButton:checked {{
    border: 1px solid #8FB6DC; background: {_grad("#E6F1FC", "#CFE3F6")};
}}
/* Win7 的 IE8 把"后退/前进"做成一颗左右相连的按钮 */
QToolButton#navButton[navPos="first"] {{
    border-top-right-radius: 0px; border-bottom-right-radius: 0px;
    border-right: 0px; margin-right: 0px;
}}
QToolButton#navButton[navPos="last"] {{
    border-top-left-radius: 0px; border-bottom-left-radius: 0px;
    border-left: 1px solid #A8C4DE; margin-left: 0px;
}}
QToolButton#navButton[navPos="first"]:hover,
QToolButton#navButton[navPos="last"]:hover {{
    border: 1px solid #8FB6DC; background: {_grad("#F4FAFF", "#D6E8F8")};
}}
QToolButton#navButton[navPos="first"]:pressed,
QToolButton#navButton[navPos="last"]:pressed {{
    border: 1px solid #6E9BC6; background: {_grad("#CFE2F5", "#B7D3EE")};
}}
"""

    if style == "flat":
        # Win8.1 / IE11：无圆角，悬停是浅灰方块
        return f"""
QToolButton#navButton {{
    padding: 2px 6px; margin: 0px; border: 1px solid transparent;
    border-radius: 0px; {height_rule}
}}
QToolButton#navButton:hover {{ background: #E6E6E6; border: 1px solid #D0D0D0; }}
QToolButton#navButton:pressed {{ background: #D6D6D6; border: 1px solid #B8B8B8; }}
QToolButton#navButton:checked {{ background: #DEDEDE; border: 1px solid #C4C4C4; }}
QToolButton#navButton:disabled {{ color: {t.text_disabled}; }}
"""

    if style == "modern":
        # Win10 / Edge：细边框浅灰悬停，图标更大
        return f"""
QToolButton#navButton {{
    padding: 2px 7px; margin: 0px 1px; border: 1px solid transparent;
    border-radius: {radius}px; {height_rule}
}}
QToolButton#navButton:hover {{ background: #EDEDED; border: 1px solid #E0E0E0; }}
QToolButton#navButton:pressed {{ background: #DCDCDC; border: 1px solid #C8C8C8; }}
QToolButton#navButton:checked {{ background: #E4E4E4; border: 1px solid #D4D4D4; }}
QToolButton#navButton:disabled {{ color: {t.text_disabled}; }}
"""

    if style == "harmony":
        # 鸿蒙：圆形悬停底 + 淡蓝高亮
        return f"""
QToolButton#navButton {{
    padding: 1px 3px; margin: 0px 2px; border: 1px solid transparent;
    border-radius: {radius}px; {height_rule}
}}
QToolButton#navButton:hover {{ background: #E8F1FF; border: 1px solid #C9DFFF; }}
QToolButton#navButton:pressed {{ background: #D5E6FF; border: 1px solid #A8CBFF; }}
QToolButton#navButton:checked {{ background: #E0EDFF; border: 1px solid #BBD6FF; }}
QToolButton#navButton:disabled {{ color: {t.text_disabled}; }}
"""

    if style == "fluent":
        # 哈基米（Win11 风格）：圆角胶囊 + 半透明暖色悬停；后退/前进合成一颗胶囊
        alpha = t.nav_hover_alpha or 22
        hover = QColor(t.highlight)
        hover.setAlpha(alpha)
        press = QColor(t.highlight)
        press.setAlpha(min(255, alpha + 26))
        return f"""
QToolButton#navButton {{
    padding: 1px 4px; margin: 0px 1px; border: 1px solid transparent;
    border-radius: {radius}px; {height_rule}
}}
QToolButton#navButton:hover {{
    background: rgba({hover.red()}, {hover.green()}, {hover.blue()}, {hover.alpha()});
    border: 1px solid rgba(224, 168, 96, 110);
}}
QToolButton#navButton:pressed {{
    background: rgba({press.red()}, {press.green()}, {press.blue()}, {press.alpha()});
    border: 1px solid rgba(206, 150, 78, 140);
}}
QToolButton#navButton:checked {{
    background: rgba({hover.red()}, {hover.green()}, {hover.blue()}, {hover.alpha() + 14});
    border: 1px solid rgba(224, 168, 96, 130);
}}
QToolButton#navButton:disabled {{ color: {t.text_disabled}; }}
/* 哈基米（Win11 风格）：后退/前进连成一颗暖色胶囊，与 Win11 的圆角一致 */
QToolButton#navButton[navPos="first"] {{
    border-top-right-radius: 0px; border-bottom-right-radius: 0px;
    border-right: 0px; margin-right: 0px;
}}
QToolButton#navButton[navPos="last"] {{
    border-top-left-radius: 0px; border-bottom-left-radius: 0px;
    border-left: 1px solid rgba(224, 168, 96, 90); margin-left: 0px;
}}
QToolButton#navButton[navPos="first"]:hover,
QToolButton#navButton[navPos="last"]:hover {{
    border: 1px solid rgba(224, 168, 96, 110);
    background: rgba({hover.red()}, {hover.green()}, {hover.blue()}, {hover.alpha()});
}}
QToolButton#navButton[navPos="first"]:pressed,
QToolButton#navButton[navPos="last"]:pressed {{
    border: 1px solid rgba(206, 150, 78, 140);
    background: rgba({press.red()}, {press.green()}, {press.blue()}, {press.alpha()});
}}
"""

    # classic（XP / 98）：图标 + 文字 + 经典热区
    return f"""
QToolButton#navButton {{
    padding: 2px 6px; margin: 0px 1px; border: 1px solid transparent;
    border-radius: {radius}px; {height_rule}
}}
QToolButton#navButton:hover {{
    border: 1px solid {t.hot_border}; background: {_grad(t.hot_top, t.hot_bottom)};
}}
QToolButton#navButton:pressed {{
    border: 1px solid {t.button_border}; background: {t.button_pressed};
}}
QToolButton#navButton:checked {{
    border: 1px solid {t.hot_border}; background: {_grad(t.hot_top, t.hot_bottom)};
}}
QToolButton#navButton:disabled {{ color: {t.text_disabled}; }}
"""


def stylesheet(spec: Optional[ThemeSpec] = None) -> str:
    """按主题生成全局 QSS。"""
    t = spec or _current
    status = status_colors(t)
    nav_style_qss = nav_qss(t)
    heading_color = "#003C74" if t.id in ("xp", "win98") else t.highlight

    button_qss = f"""
QPushButton {{
    background: {_grad(t.button_top, t.button_mid, t.button_bottom)};
    border: 1px solid {t.button_border};
    border-radius: {3 if t.rounded else 0}px;
    padding: 4px 14px;
    min-width: 66px;
    min-height: 17px;
    color: {t.text};
}}
QPushButton:hover {{
    background: {_grad(t.button_hover_top, t.button_hover_bottom)};
}}
QPushButton:pressed {{ background: {t.button_pressed}; }}
QPushButton:disabled {{
    background: {t.button_disabled_bg};
    border: 1px solid {t.button_disabled_border};
    color: {t.text_disabled};
}}
QPushButton:focus {{ outline: none; }}
"""

    scroll_qss = f"""
QScrollBar:vertical {{
    background: {t.scroll_bg}; width: 15px; margin: 15px 0px 15px 0px;
    border-left: 1px solid {t.scroll_thumb_border};
}}
QScrollBar::handle:vertical {{
    background: {_grad_h(t.scroll_thumb_top, t.scroll_thumb_bottom)};
    border: 1px solid {t.scroll_thumb_border}; border-radius: {2 if t.rounded else 0}px;
    min-height: 20px; margin: 0px 1px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    background: {_grad(t.scroll_thumb_top, t.scroll_bg)};
    border: 1px solid {t.scroll_thumb_border}; height: 14px;
    subcontrol-origin: margin;
}}
QScrollBar::add-line:vertical {{ subcontrol-position: bottom; }}
QScrollBar::sub-line:vertical {{ subcontrol-position: top; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: {t.scroll_bg}; }}
QScrollBar:horizontal {{
    background: {t.scroll_bg}; height: 15px; margin: 0px 15px 0px 15px;
    border-top: 1px solid {t.scroll_thumb_border};
}}
QScrollBar::handle:horizontal {{
    background: {_grad(t.scroll_thumb_top, t.scroll_thumb_bottom)};
    border: 1px solid {t.scroll_thumb_border}; border-radius: {2 if t.rounded else 0}px;
    min-width: 20px; margin: 1px 0px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    background: {_grad(t.scroll_thumb_top, t.scroll_bg)};
    border: 1px solid {t.scroll_thumb_border}; width: 14px;
    subcontrol-origin: margin;
}}
QScrollBar::add-line:horizontal {{ subcontrol-position: right; }}
QScrollBar::sub-line:horizontal {{ subcontrol-position: left; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: {t.scroll_bg}; }}
"""

    return f"""
/* ---------- 全局 ---------- */
QWidget {{
    font-family: "Tahoma", "Microsoft YaHei UI", "Microsoft YaHei", "SimSun", sans-serif;
    font-size: 12px;
    color: {t.text};
}}
QMainWindow, QDialog {{ background: {t.face}; }}
QToolTip {{
    background: {"#3A3A3A" if t.dark else "#FFFFE1"};
    color: {"#F0F0F0" if t.dark else "#000000"};
    border: 1px solid {"#5A5A5A" if t.dark else "#000000"};
    padding: 2px 4px;
}}

/* ---------- 菜单栏 ---------- */
QMenuBar {{
    background: {t.face};
    border-bottom: 1px solid {t.menu_border};
    padding: 0px 2px;
}}
QMenuBar::item {{ background: transparent; padding: 3px 8px; margin: 1px 0px; }}
QMenuBar::item:selected {{ background: {t.highlight}; color: {t.highlight_text}; }}
QMenuBar::item:pressed {{ background: {t.highlight}; color: {t.highlight_text}; }}

/* ---------- 菜单 ---------- */
QMenu {{ background: {t.menu_bg}; border: 1px solid {t.menu_border}; padding: 3px 2px; }}
QMenu::item {{ padding: 4px 26px 4px 30px; background: transparent; min-width: 120px; }}
QMenu::item:selected {{ background: {t.highlight}; color: {t.highlight_text}; }}
QMenu::item:disabled {{ color: {t.text_disabled}; }}
QMenu::separator {{ height: 1px; background: {t.menu_border}; margin: 3px 6px 3px 30px; }}
QMenu::icon {{ padding-left: 8px; }}
QMenu::indicator {{ width: 18px; height: 18px; margin-left: 8px; }}

/* ---------- 工具栏 ---------- */
QToolBar {{
    background: {t.face};
    border: 0px;
    border-bottom: 1px solid {t.menu_border};
    spacing: 1px;
    padding: 2px 3px;
}}
QToolBar::separator {{ width: 1px; background: {t.menu_border}; margin: 4px 4px; }}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {3 if t.rounded else 0}px;
    padding: 2px 5px;
    margin: 0px 1px;
    color: {t.text};
}}
QToolButton:hover {{
    border: 1px solid {t.hot_border};
    background: {_grad(t.hot_top, t.hot_bottom)};
}}
QToolButton:pressed {{
    border: 1px solid {t.button_border};
    background: {t.button_pressed};
}}
QToolButton:checked {{
    border: 1px solid {t.hot_border};
    background: {_grad(t.hot_top, t.hot_bottom)};
}}
QToolButton:disabled {{ color: {t.text_disabled}; }}
QToolButton::menu-indicator {{ image: none; }}

/* ---------- 导航按钮（随系统风格变化）---------- */
{nav_style_qss}

/* ---------- 输入框 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {t.field_bg};
    border: 1px solid {t.field_border};
    border-radius: {2 if t.rounded else 0}px;
    padding: 2px 4px;
    color: {t.text};
    selection-background-color: {t.highlight};
    selection-color: {t.highlight_text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {t.highlight}; }}
QLineEdit:disabled {{ background: {t.face}; color: {t.text_disabled}; }}
QComboBox {{
    background: {_grad(t.field_bg, t.face)};
    border: 1px solid {t.field_border};
    border-radius: {2 if t.rounded else 0}px;
    padding: 2px 4px;
    color: {t.text};
}}
QComboBox::drop-down {{
    width: 17px;
    border-left: 1px solid {t.field_border};
    background: {_grad(t.button_top, t.button_bottom)};
}}
QComboBox QAbstractItemView {{
    background: {t.menu_bg};
    border: 1px solid {t.field_border};
    selection-background-color: {t.highlight};
    selection-color: {t.highlight_text};
}}

/* ---------- 按钮 ---------- */
{button_qss}

/* ---------- 标签页 ---------- */
QTabWidget::pane {{ border: 1px solid {t.tab_border}; background: {t.tab_selected_bg}; top: -1px; }}
QTabBar {{ background: {t.face}; }}
QTabBar::tab {{
    background: {_grad(t.tab_bg_top, t.tab_bg_bottom)};
    border: 1px solid {t.tab_border};
    border-bottom: none;
    border-top-left-radius: {3 if t.rounded else 0}px;
    border-top-right-radius: {3 if t.rounded else 0}px;
    padding: 3px 8px 3px 8px;
    margin-right: 2px;
    margin-top: 2px;
    min-width: 60px;
    color: {t.text};
}}
QTabBar::tab:selected {{ background: {t.tab_selected_bg}; margin-top: 0px; padding-bottom: 4px; }}
QTabBar::tab:hover:!selected {{ background: {_grad(t.hot_top, t.hot_bottom)}; }}
QTabBar::close-button {{ subcontrol-position: right; }}

/* ---------- 状态栏 ---------- */
QStatusBar {{
    background: {t.statusbar_bg};
    border-top: 1px solid {t.menu_border};
    color: {t.text};
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ padding: 0px 4px; }}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background: {t.field_bg};
    border: 1px solid {t.field_border};
    border-radius: 2px;
    text-align: center;
    color: {t.text};
    font-size: 10px;
}}
QProgressBar::chunk {{
    background: {_grad(t.progress_top, t.progress_mid, t.progress_bottom)};
    border-radius: 1px;
}}

/* ---------- 列表 / 树 / 表格 ---------- */
QListWidget, QTreeWidget, QTableWidget {{
    background: {t.field_bg};
    border: 1px solid {t.field_border};
    selection-background-color: {t.highlight};
    selection-color: {t.highlight_text};
    color: {t.text};
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{ padding: 2px 3px; }}
QHeaderView::section {{
    background: {_grad(t.tab_bg_top, t.tab_bg_bottom)};
    border: none;
    border-right: 1px solid {t.menu_border};
    border-bottom: 1px solid {t.menu_border};
    padding: 3px 5px;
    color: {t.text};
}}
QGroupBox {{
    border: 1px solid {t.menu_border};
    border-radius: {3 if t.rounded else 0}px;
    margin-top: 9px;
    padding: 8px 6px 6px 6px;
    font-weight: bold;
    color: {t.text};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0px 3px;
    color: {t.text if t.dark else t.highlight};
}}
QCheckBox, QRadioButton {{ spacing: 6px; padding: 2px 0px; color: {t.text}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 13px; height: 13px; }}
QLabel {{ color: {t.text}; background: transparent; }}

/* ---------- 文字角色（对话框内的说明文字跟随主题，保证深色模式可读） ---------- */
QLabel[role="hint"] {{ color: {t.text_dim}; }}
QLabel[role="dim"] {{ color: {t.text_dim}; }}
QLabel[role="value"] {{ color: {t.text}; }}
QLabel[role="strong"] {{ color: {t.text}; font-weight: bold; }}
QLabel[role="error"] {{ color: {status["error"]}; }}
QLabel[role="warn"] {{ color: {status["warn"]}; }}
QLabel[role="ok"] {{ color: {status["ok"]}; }}
QLabel[role="info"] {{ color: {t.text_dim}; }}
QLabel[role="heading"] {{
    color: {t.text if t.dark else heading_color};
}}
QLabel[role="card"] {{
    background: {t.field_bg};
    border: 1px solid {t.field_border};
    border-radius: 4px;
    padding: 8px;
    color: {t.text};
}}
QLabel#incognitoBadge {{
    color: #FFFFFF; background: #C6362B; padding: 1px 6px; border-radius: 2px;
}}
QWidget#statusWrap {{ background: transparent; }}
QToolButton#statusVersion {{
    color: {t.text_dim};
    padding: 0px 6px;
    margin: 0px 2px;
    border: 1px solid transparent;
    border-radius: 3px;
    font-weight: bold;
    font-size: 11px;
}}
QToolButton#statusVersion:hover {{
    color: {t.text if t.dark else t.highlight};
    border: 1px solid {t.hot_border};
    background: {_grad(t.hot_top, t.hot_bottom)};
}}
QFrame[role="hline"] {{ background: {t.menu_border}; border: none; max-height: 1px; }}
QTextBrowser, QTextEdit#helpView {{
    background: {t.field_bg};
    border: 1px solid {t.field_border};
    color: {t.text};
    selection-background-color: {t.highlight};
    selection-color: {t.highlight_text};
}}
QTreeWidget#helpTree {{
    background: {t.field_bg};
    border: 1px solid {t.field_border};
    color: {t.text};
}}
QTreeWidget#helpTree::item:selected {{
    background: {t.highlight}; color: {t.highlight_text};
}}

/* ---------- 滚动条 ---------- */
{scroll_qss}

/* ---------- 仿窗口客户区 ---------- */
QWidget#xpClient {{ background: {t.face}; border: 1px solid {t.border}; }}

/* ---------- 查找栏 / 书签栏 ---------- */
QWidget#findBar {{ background: {t.face}; border-bottom: 1px solid {t.menu_border}; }}
QToolBar#bookmarkBar {{
    background: {_grad(t.face_alt, t.face)};
    border-bottom: 1px solid {t.menu_border};
    padding: 1px 3px;
}}
"""


__all__ = [
    "ThemeSpec",
    "THEMES",
    "THEME_ORDER",
    "DEFAULT_THEME",
    "current",
    "set_current",
    "spec_for",
    "stylesheet",
    "theme_names",
    "with_accent",
    "mix",
    "caption_height",
    "status_colors",
    "notifier",
]
