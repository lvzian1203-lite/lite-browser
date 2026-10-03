"""Windows XP (Luna) 风格配色与全局样式表。"""

from __future__ import annotations

# --- 经典 Luna 配色 --------------------------------------------------------- #
FACE = "#ECE9D8"          # 对话框/工具栏底色
FACE_DARK = "#D4D0C8"     # 旧版灰色控件底色
BORDER = "#ACA899"        # 3D 边框的暗色
BORDER_LIGHT = "#FFFFFF"  # 3D 边框的亮色
FIELD_BORDER = "#7F9DB9"  # 输入框边框
HILIGHT = "#316AC5"       # 菜单/列表选中
TEXT = "#000000"
TEXT_DISABLED = "#9A9A9A"

CAPTION_TOP = "#4C9BF7"
CAPTION_MID = "#0B5FE6"
CAPTION_BOTTOM = "#0A46B8"
CAPTION_INACTIVE_TOP = "#A8C2EE"
CAPTION_INACTIVE_MID = "#8EA9DC"
CAPTION_INACTIVE_BOTTOM = "#7E96C8"
CAPTION_TEXT = "#FFFFFF"
CAPTION_BORDER = "#0831A0"

MENU_BG = "#FFFFFF"
TOOLBAR_HOT_TOP = "#FFFDF3"
TOOLBAR_HOT_BOTTOM = "#FFE39B"


def stylesheet() -> str:
    """返回全局 QSS。"""
    return f"""
/* ---------- 全局 ---------- */
QWidget {{
    font-family: "Tahoma", "Microsoft YaHei UI", "Microsoft YaHei", "SimSun", sans-serif;
    font-size: 12px;
    color: {TEXT};
}}
QMainWindow, QDialog {{
    background: {FACE};
}}
QToolTip {{
    background: #FFFFE1;
    color: #000000;
    border: 1px solid #000000;
    padding: 2px 4px;
}}

/* ---------- 菜单栏 ---------- */
QMenuBar {{
    background: {FACE};
    border-bottom: 1px solid {BORDER};
    padding: 0px 2px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 3px 8px;
    margin: 1px 0px;
}}
QMenuBar::item:selected {{
    background: {HILIGHT};
    color: #FFFFFF;
}}
QMenuBar::item:pressed {{
    background: {HILIGHT};
    color: #FFFFFF;
}}

/* ---------- 下拉菜单（XP 白色菜单 + 左侧图标栏） ---------- */
QMenu {{
    background: {MENU_BG};
    border: 1px solid {BORDER};
    padding: 3px 2px;
}}
QMenu::item {{
    padding: 4px 26px 4px 30px;
    background: transparent;
    min-width: 120px;
}}
QMenu::item:selected {{
    background: {HILIGHT};
    color: #FFFFFF;
}}
QMenu::item:disabled {{
    color: {TEXT_DISABLED};
}}
QMenu::separator {{
    height: 1px;
    background: #D6D3CE;
    margin: 3px 6px 3px 30px;
}}
QMenu::icon {{
    padding-left: 8px;
}}
QMenu::indicator {{
    width: 18px;
    height: 18px;
    margin-left: 8px;
}}

/* ---------- 工具栏 ---------- */
QToolBar {{
    background: {FACE};
    border: 0px;
    border-bottom: 1px solid {BORDER};
    spacing: 1px;
    padding: 2px 3px;
}}
QToolBar::separator {{
    width: 1px;
    background: {BORDER};
    margin: 4px 4px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 2px 5px;
    margin: 0px 1px;
    color: {TEXT};
}}
QToolButton:hover {{
    border: 1px solid #B6BDD2;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {TOOLBAR_HOT_TOP}, stop:1 {TOOLBAR_HOT_BOTTOM});
}}
QToolButton:pressed {{
    border: 1px solid #8A9BB8;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #E3D9B0, stop:1 #F5EBC8);
}}
QToolButton:checked {{
    border: 1px solid #B6BDD2;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {TOOLBAR_HOT_TOP}, stop:1 {TOOLBAR_HOT_BOTTOM});
}}
QToolButton:disabled {{
    color: {TEXT_DISABLED};
}}
QToolButton::menu-indicator {{
    image: none;
}}

/* ---------- 输入框 / 下拉框 ---------- */
QLineEdit {{
    background: #FFFFFF;
    border: 1px solid {FIELD_BORDER};
    border-radius: 2px;
    padding: 2px 4px;
    selection-background-color: {HILIGHT};
    selection-color: #FFFFFF;
}}
QLineEdit:focus {{
    border: 1px solid #3C7FB1;
}}
QLineEdit:disabled {{
    background: {FACE};
    color: {TEXT_DISABLED};
}}
QComboBox {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 {FACE});
    border: 1px solid {FIELD_BORDER};
    border-radius: 2px;
    padding: 2px 4px;
}}
QComboBox::drop-down {{
    width: 17px;
    border-left: 1px solid {FIELD_BORDER};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 {FACE});
}}
QComboBox QAbstractItemView {{
    background: #FFFFFF;
    border: 1px solid {FIELD_BORDER};
    selection-background-color: {HILIGHT};
    selection-color: #FFFFFF;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:0.45 #F4F2EC, stop:1 #E2DFD2);
    border: 1px solid #003C74;
    border-radius: 3px;
    padding: 4px 14px;
    min-width: 66px;
    min-height: 17px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFDF5, stop:1 #FFE39B);
}}
QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #DCD7C6, stop:1 #EFEBDD);
}}
QPushButton:default {{
    border: 1px solid #003C74;
}}
QPushButton:disabled {{
    background: #F1EFE7;
    border: 1px solid #B4B0A3;
    color: {TEXT_DISABLED};
}}
QPushButton:focus {{
    outline: none;
}}

/* ---------- 标签页（IE7 on XP 风格） ---------- */
QTabWidget::pane {{
    border: 1px solid #919B9C;
    background: #FFFFFF;
    top: -1px;
}}
QTabBar {{
    background: {FACE};
}}
QTabBar::tab {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #E1DDCE);
    border: 1px solid #919B9C;
    border-bottom: none;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    padding: 3px 8px 3px 8px;
    margin-right: 2px;
    margin-top: 2px;
    min-width: 60px;
}}
QTabBar::tab:selected {{
    background: #FFFFFF;
    border-bottom: none;
    margin-top: 0px;
    padding-bottom: 4px;
}}
QTabBar::tab:hover:!selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #FFF0C2);
}}
QTabBar::close-button {{
    subcontrol-position: right;
}}

/* ---------- 状态栏 ---------- */
QStatusBar {{
    background: {FACE};
    border-top: 1px solid {BORDER_LIGHT};
    color: {TEXT};
}}
QStatusBar::item {{
    border: none;
}}
QStatusBar QLabel {{
    padding: 0px 4px;
}}

/* ---------- 进度条（XP 绿色方块） ---------- */
QProgressBar {{
    background: #FFFFFF;
    border: 1px solid #A0A0A0;
    border-radius: 2px;
    text-align: center;
    color: #3A3A3A;
    font-size: 10px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #C7EFA8, stop:0.5 #7CD24A, stop:1 #47A62A);
    border-radius: 1px;
}}

/* ---------- 列表 / 树 ---------- */
QListWidget, QTreeWidget, QTableWidget {{
    background: #FFFFFF;
    border: 1px solid {FIELD_BORDER};
    border-radius: 0px;
    selection-background-color: {HILIGHT};
    selection-color: #FFFFFF;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 2px 3px;
}}
QHeaderView::section {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 {FACE});
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 3px 5px;
}}

/* ---------- 滚动条（XP 蓝灰） ---------- */
QScrollBar:vertical {{
    background: #F1EFE2;
    width: 16px;
    margin: 16px 0px 16px 0px;
    border-left: 1px solid #D4D0C8;
}}
QScrollBar::handle:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #FFFFFF, stop:0.5 #CDDCF0, stop:1 #9DB6DC);
    border: 1px solid #7F9DB9;
    border-radius: 2px;
    min-height: 20px;
    margin: 0px 1px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #D6D2C2);
    border: 1px solid #B0AC9C;
    height: 15px;
    subcontrol-origin: margin;
}}
QScrollBar::add-line:vertical {{ subcontrol-position: bottom; }}
QScrollBar::sub-line:vertical {{ subcontrol-position: top; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: #F1EFE2;
}}
QScrollBar:horizontal {{
    background: #F1EFE2;
    height: 16px;
    margin: 0px 16px 0px 16px;
    border-top: 1px solid #D4D0C8;
}}
QScrollBar::handle:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:0.5 #CDDCF0, stop:1 #9DB6DC);
    border: 1px solid #7F9DB9;
    border-radius: 2px;
    min-width: 20px;
    margin: 1px 0px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFFFFF, stop:1 #D6D2C2);
    border: 1px solid #B0AC9C;
    width: 15px;
    subcontrol-origin: margin;
}}
QScrollBar::add-line:horizontal {{ subcontrol-position: right; }}
QScrollBar::sub-line:horizontal {{ subcontrol-position: left; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: #F1EFE2;
}}

/* ---------- 复选框 / 单选按钮 ---------- */
QCheckBox, QRadioButton {{
    spacing: 6px;
    padding: 2px 0px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 13px;
    height: 13px;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 3px;
    margin-top: 9px;
    padding: 8px 6px 6px 6px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0px 3px;
    color: #003C74;
}}

/* ---------- 书签栏 ---------- */
QToolBar#bookmarkBar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FBF9F0, stop:1 {FACE});
    border-bottom: 1px solid {BORDER};
    padding: 1px 3px;
}}

/* ---------- 仿 XP 窗口客户区 ---------- */
QWidget#xpClient {{
    background: {FACE};
    border: 1px solid {CAPTION_BORDER};
}}
"""
