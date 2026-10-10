"""仿 Windows XP (Luna) 风格的基础控件：标题栏、无边框窗口、对话框。"""

from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .config import APP_NAME

from .i18n import tr, trf

#: 是否使用圆角 + 半透明窗口（仿 XP 的圆角标题栏）
ROUNDED_CORNERS = True
#: 可拖动改变大小的边缘宽度
RESIZE_MARGIN = 5
#: 标题栏高度
CAPTION_HEIGHT = 28


def _rounded_path(rect: QRectF, radius: float, *, top_only: bool = True) -> QPainterPath:
    """构造一个只在顶部圆角的矩形路径。"""
    path = QPainterPath()
    r = min(radius, rect.width() / 2, rect.height() / 2)
    if r <= 0:
        path.addRect(rect)
        return path

    left, top = rect.left(), rect.top()
    right, bottom = rect.right(), rect.bottom()

    path.moveTo(left + r, top)
    path.lineTo(right - r, top)
    path.quadTo(right, top, right, top + r)
    if top_only:
        path.lineTo(right, bottom)
        path.lineTo(left, bottom)
        path.lineTo(left, top + r)
    else:
        path.lineTo(right, bottom - r)
        path.quadTo(right, bottom, right - r, bottom)
        path.lineTo(left + r, bottom)
        path.quadTo(left, bottom, left, bottom - r)
    path.quadTo(left, top, left + r, top)
    path.closeSubpath()
    return path


# --------------------------------------------------------------------------- #
# 标题栏按钮
# --------------------------------------------------------------------------- #
class _CaptionButton(QAbstractButton):
    """XP 风格的“最小化 / 最大化 / 关闭”按钮。"""

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        # 必须显式设为 Fixed：setFixedSize() 只限制 min/max，
        # 尺寸策略仍是 Minimum，水平布局会把按钮撑开来填满标题栏
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(QSize(21, 21) if kind != "close" else QSize(23, 21))
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(
            {"min": "最小化", "max": "最大化", "restore": "向下还原", "close": "关闭"}.get(
                kind, ""
            )
        )

    def apply_theme(self) -> None:
        """主题切换后刷新外观。"""
        self.update()

    def set_kind(self, kind: str) -> None:
        if self.kind != kind:
            self.kind = kind
            self.update()

    def sizeHint(self) -> QSize:
        return self.size()

    def enterEvent(self, event) -> None:  # noqa: D102
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: D102
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: D102
        spec = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        hot = self.underMouse() and self.isEnabled()
        down = self.isDown()

        flat = spec.caption_style in ("flat", "classic") or spec.button_flat
        if self.kind == "close":
            top, bottom = QColor("#F5A08F"), QColor("#C6362B")
            if hot:
                top, bottom = QColor("#FFD3C4"), QColor("#E04A34")
            if down:
                top, bottom = QColor("#B93526"), QColor("#E2877A")
            border = QColor("#FFFFFF") if not flat else QColor("#8A2A20")
            glyph = QColor("#FFFFFF")
        else:
            if flat:
                # Win8.1 / Win10 风格：扁平无边框按钮
                base = QColor(spec.caption_top)
                top = base.lighter(118) if hot else (base.darker(110) if down else base)
                bottom = top
                border = QColor(0, 0, 0, 0)
                glyph = QColor(spec.caption_text)
            else:
                top, bottom = QColor("#6DB2F7"), QColor("#1050C8")
                if hot:
                    top, bottom = QColor("#A8D4FF"), QColor("#1C63E0")
                if down:
                    top, bottom = QColor("#0C3E9E"), QColor("#5E9BE8")
                border = QColor("#FFFFFF")
                glyph = QColor("#FFFFFF")

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bottom)
        p.setBrush(grad)
        radius = 3.5 if spec.rounded else 0.0
        if border.alpha() == 0:
            p.setPen(Qt.NoPen)
        else:
            p.setPen(QPen(border, 1))
        if radius > 0:
            p.drawRoundedRect(rect, radius, radius)
        else:
            p.drawRect(rect)

        pen = QPen(glyph, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        w, h = rect.width(), rect.height()
        if self.kind == "min":
            y = rect.top() + h * 0.66
            p.drawLine(rect.left() + w * 0.28, y, rect.left() + w * 0.72, y)
        elif self.kind == "max":
            p.drawRect(QRectF(rect.left() + w * 0.26, rect.top() + h * 0.28,
                              w * 0.46, h * 0.42))
        elif self.kind == "restore":
            p.drawRect(QRectF(rect.left() + w * 0.22, rect.top() + h * 0.36,
                              w * 0.40, h * 0.34))
            p.drawLine(rect.left() + w * 0.34, rect.top() + h * 0.30,
                       rect.left() + w * 0.76, rect.top() + h * 0.30)
            p.drawLine(rect.left() + w * 0.76, rect.top() + h * 0.30,
                       rect.left() + w * 0.76, rect.top() + h * 0.62)
        else:  # close
            p.drawLine(rect.left() + w * 0.30, rect.top() + h * 0.30,
                       rect.left() + w * 0.70, rect.top() + h * 0.70)
            p.drawLine(rect.left() + w * 0.70, rect.top() + h * 0.30,
                       rect.left() + w * 0.30, rect.top() + h * 0.70)


# --------------------------------------------------------------------------- #
# 标题栏
# --------------------------------------------------------------------------- #
class LunaTitleBar(QWidget):
    """Luna 蓝色渐变标题栏，可拖动窗口、双击最大化。"""

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    system_menu_requested = Signal(QPoint)

    def __init__(
        self,
        window: QWidget,
        title: str = APP_NAME,
        *,
        minimizable: bool = True,
        maximizable: bool = True,
        closable: bool = True,
        show_icon: bool = True,
    ) -> None:
        super().__init__(window)
        self.setObjectName("lunaCaption")
        self._window = window
        self._title = title
        self._active = True
        self._show_icon = show_icon
        self.setFixedHeight(CAPTION_HEIGHT)
        self.setMouseTracking(True)
        self._icon = icons.icon("app", 16)
        theme.notifier.changed.connect(lambda _spec: self._on_theme_changed())

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_system_menu)

        self._minimizable = minimizable
        self._maximizable = maximizable
        self._closable = closable
        self._buttons: list[_CaptionButton] = []
        self._btn_max: _CaptionButton | None = None
        self._layout = QHBoxLayout(self)
        self._build_buttons()

    def _build_buttons(self) -> None:
        """按当前主题决定按钮位置与顺序（macOS 在左侧，红黄绿）。"""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._buttons = []
        self._btn_max = None

        spec = theme.current()
        left = spec.caption_side == "left"
        if left:
            self._layout.setContentsMargins(12, 3, 4, 3)
            self._layout.setSpacing(8)
        else:
            self._layout.setContentsMargins(4, 2, 3, 2)
            self._layout.setSpacing(2)

        min_btn = None
        if self._minimizable:
            min_btn = _CaptionButton("min", self)
            min_btn.clicked.connect(self.minimize_requested.emit)
        max_btn = None
        if self._maximizable:
            max_btn = _CaptionButton("max", self)
            max_btn.clicked.connect(self.maximize_requested.emit)
            self._btn_max = max_btn
        close_btn = None
        if self._closable:
            close_btn = _CaptionButton("close", self)
            close_btn.clicked.connect(self.close_requested.emit)

        if left:
            order = [close_btn, min_btn, max_btn]
        else:
            self._layout.addStretch(1)
            order = [min_btn, max_btn, close_btn]
        for button in order:
            if button is None:
                continue
            self._layout.addWidget(button)
            self._buttons.append(button)
        if left:
            # macOS 风格：圆点靠左，其余留空
            self._layout.addStretch(1)

    # -- 状态 ------------------------------------------------------------- #
    def set_title(self, title: str) -> None:
        if title != self._title:
            self._title = title or APP_NAME
            self.update()

    def set_active(self, active: bool) -> None:
        if active != self._active:
            self._active = active
            for button in self._buttons:
                button.update()
            self.update()

    def set_maximized_state(self, maximized: bool) -> None:
        if self._btn_max is not None:
            self._btn_max.set_kind("restore" if maximized else "max")

    def _on_theme_changed(self) -> None:
        """主题变化：标题栏高度、按钮样式与配色都要跟着更新。"""
        self.setFixedHeight(theme.caption_height())
        self._build_buttons()
        for button in self._buttons:
            button.apply_theme()
        self.update()

    def set_icon(self, icon) -> None:
        self._icon = icon
        self.update()

    # -- 绘制 ------------------------------------------------------------- #
    def paintEvent(self, event) -> None:  # noqa: D102
        spec = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())

        maximized = self._window.isMaximized() or self._window.isFullScreen()
        radius = 0.0 if maximized else float(spec.rounded)

        if self._active:
            top = QColor(spec.caption_top)
            mid = QColor(spec.caption_mid)
            bottom = QColor(spec.caption_bottom)
            text_color = QColor(spec.caption_text)
        else:
            top = QColor(spec.caption_inactive_top)
            mid = QColor(spec.caption_inactive_top)
            bottom = QColor(spec.caption_inactive_bottom)
            text_color = QColor(spec.caption_inactive_text)

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        if spec.caption_style == "gradient":
            grad.setColorAt(0.0, top)
            grad.setColorAt(0.42, mid)
            grad.setColorAt(0.55, mid)
            grad.setColorAt(1.0, bottom)
        elif spec.caption_style == "classic":
            # Win98：上一半深色、下一半渐变到亮色
            grad.setColorAt(0.0, top)
            grad.setColorAt(0.62, top)
            grad.setColorAt(1.0, bottom)
        else:
            grad.setColorAt(0.0, top)
            grad.setColorAt(1.0, bottom)

        path = _rounded_path(rect, radius)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(path)

        # 顶部高光（XP / Aero 的玻璃质感）
        if spec.caption_highlight and self._active:
            p.setClipPath(path)
            highlight = QLinearGradient(
                rect.topLeft(), QPoint(0, int(rect.top() + rect.height() * 0.45))
            )
            highlight.setColorAt(0.0, QColor(255, 255, 255, 150))
            highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(highlight)
            p.drawRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.5))
            p.setClipping(False)

        # 标题栏底部强调线（Win10 / Win11 / HarmonyOS 风格）
        if spec.caption_line:
            p.setPen(QPen(QColor(spec.caption_line), 2))
            p.drawLine(rect.bottomLeft(), rect.bottomRight())

        # 标题文字
        if self._title:
            from .theme import caption_height as _caption_height

            height = _caption_height(spec)
            self.setFixedHeight(height)
            left_pad = 12 if spec.caption_side == "left" else (26 if self._show_icon else 8)
            if spec.caption_badge:
                left_pad += 22
            text_rect = rect.adjusted(left_pad, 0, -12 if spec.caption_side == "left" else -86, 0)
            font = QFont(self.font())
            font.setBold(spec.id in ("xp", "win98", "win7"))
            font.setPointSizeF(9.0)
            p.setFont(font)
            align = Qt.AlignVCenter | (
                Qt.AlignHCenter if spec.title_align == "center" else Qt.AlignLeft
            )
            title = self._elide(p, int(text_rect.width()), self._title)
            if spec.caption_style != "flat" or spec.dark:
                p.setPen(QColor(0, 0, 0, 110))
                p.drawText(text_rect.translated(1, 1), align, title)
            p.setPen(text_color)
            p.drawText(text_rect, align, title)

            # 哈基米 UI：标题左侧画一个猫爪印
            if spec.caption_badge == "paw":
                badge_x = rect.left() + (28 if spec.caption_side == "left" else 8)
                if not spec.caption_side == "left":
                    badge_x = rect.left() + (26 if self._show_icon else 8)
                    if self._show_icon and not self._icon.isNull():
                        badge_x = rect.left() + 26
                paw = icons.icon("paw", 16).pixmap(16, 16)
                p.drawPixmap(int(badge_x), int((self.height() - 16) / 2), paw)

        # 左侧图标
        if self._show_icon and not self._icon.isNull():
            pm = self._icon.pixmap(16, 16)
            p.drawPixmap(6, int((self.height() - 16) / 2), pm)

    def _elide(self, painter: QPainter, width: int, text: str) -> str:
        metrics = painter.fontMetrics()
        return metrics.elidedText(text, Qt.ElideRight, max(10, width))

    # -- 交互 ------------------------------------------------------------- #
    def mousePressEvent(self, event) -> None:  # noqa: D102
        if event.button() == Qt.LeftButton:
            window = self._window
            if not (hasattr(window, "resize_press") and window.resize_press(event)):
                handle = window.windowHandle()
                if window.isMaximized():
                    window.showNormal()
                if handle is not None:
                    handle.startSystemMove()
        elif event.button() == Qt.RightButton:
            self._show_system_menu(event.position().toPoint())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: D102
        if event.button() == Qt.LeftButton:
            self.maximize_requested.emit()
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: D102
        window = self._window
        if hasattr(window, "resize_hover"):
            window.resize_hover(event.globalPosition().toPoint())

    def leaveEvent(self, event) -> None:  # noqa: D102
        self.unsetCursor()

    def _show_system_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        act_restore = menu.addAction(tr("还原(R)"))
        act_min = menu.addAction(tr("最小化(N)"))
        act_max = menu.addAction(tr("最大化(X)"))
        menu.addSeparator()
        act_close = menu.addAction(tr("关闭(C)"))

        maximized = self._window.isMaximized()
        act_restore.setEnabled(maximized)
        act_max.setEnabled(not maximized)

        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is act_restore:
            self._window.showNormal()
        elif chosen is act_min:
            self._window.showMinimized()
        elif chosen is act_max:
            self._window.showMaximized()
        elif chosen is act_close:
            self.close_requested.emit()


# --------------------------------------------------------------------------- #
# 无边框窗口
# --------------------------------------------------------------------------- #
class _ClientFrame(QWidget):
    """窗口客户区：负责绘制 XP 窗口边框，并处理边缘拖拽缩放。"""

    def __init__(self, window: "XPWindow") -> None:
        super().__init__(window)
        self.setObjectName("xpClient")
        self.setMouseTracking(True)
        self._window = window
        theme.notifier.changed.connect(lambda _spec: self.update())

    def paintEvent(self, event) -> None:  # noqa: D102
        if self._window.isFullScreen():
            return
        spec = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        maximized = self._window.isMaximized()
        radius = 0.0 if (maximized or not ROUNDED_CORNERS) else float(spec.rounded)

        path = _rounded_path(rect, radius)
        p.setPen(QPen(QColor(spec.border), 1))
        p.setBrush(QColor(spec.face))
        p.drawPath(path)

    def mouseMoveEvent(self, event) -> None:  # noqa: D102
        self._window.resize_hover(event.globalPosition().toPoint())

    def mousePressEvent(self, event) -> None:  # noqa: D102
        if not self._window.resize_press(event):
            event.ignore()

    def leaveEvent(self, event) -> None:  # noqa: D102
        self.unsetCursor()


class XPWindow(QMainWindow):
    """仿 XP 的无边框主窗口。

    内容请添加到 ``self.body`` 中；``self.client_layout`` 为整体布局。
    """

    def __init__(
        self,
        *,
        title: str = APP_NAME,
        minimizable: bool = True,
        maximizable: bool = True,
        closable: bool = True,
        resizable: bool = True,
        icon=None,
    ) -> None:
        super().__init__(None)
        self._resizable = resizable
        self._chrome_visible = True
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setMinimumSize(480, 320)
        self.setAttribute(Qt.WA_TranslucentBackground, ROUNDED_CORNERS)
        if ROUNDED_CORNERS:
            self.setStyleSheet("QMainWindow { background: transparent; }")

        self.client = _ClientFrame(self)
        self.setCentralWidget(self.client)

        self.client_layout = QVBoxLayout(self.client)
        self.client_layout.setContentsMargins(3, 1, 3, 3)
        self.client_layout.setSpacing(0)

        self.caption = LunaTitleBar(
            self,
            title,
            minimizable=minimizable,
            maximizable=maximizable,
            closable=closable,
        )
        self.caption.minimize_requested.connect(self.showMinimized)
        self.caption.maximize_requested.connect(self._toggle_maximized)
        self.caption.close_requested.connect(self.close)
        self.client_layout.addWidget(self.caption)

        self.body = QWidget(self.client)
        self.body.setObjectName("xpBody")
        self.client_layout.addWidget(self.body, 1)

        if icon is not None:
            self.setWindowIcon(icon)
            self.caption.set_icon(icon)

    # -- 标题 / 状态 ------------------------------------------------------ #
    def setWindowTitle(self, title: str) -> None:  # noqa: N802
        super().setWindowTitle(title)
        if hasattr(self, "caption"):
            self.caption.set_title(title)

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event) -> None:  # noqa: D102
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            self.caption.set_active(self.isActiveWindow())
        elif event.type() == QEvent.Type.WindowStateChange:
            self.caption.set_maximized_state(self.isMaximized())
            self.client.update()

    # -- 缩放 ------------------------------------------------------------- #
    def _edges_at(self, global_pos: QPoint) -> Qt.Edges:
        if self.isMaximized() or self.isFullScreen() or not self._resizable:
            return Qt.Edges()
        local = self.mapFromGlobal(global_pos)
        width, height = self.width(), self.height()
        edges = Qt.Edges()
        if local.x() <= RESIZE_MARGIN:
            edges |= Qt.LeftEdge
        elif local.x() >= width - RESIZE_MARGIN:
            edges |= Qt.RightEdge
        if local.y() <= RESIZE_MARGIN:
            edges |= Qt.TopEdge
        elif local.y() >= height - RESIZE_MARGIN:
            edges |= Qt.BottomEdge
        return edges

    @staticmethod
    def _cursor_for(edges: Qt.Edges) -> Qt.CursorShape | None:
        left = bool(edges & Qt.LeftEdge)
        right = bool(edges & Qt.RightEdge)
        top = bool(edges & Qt.TopEdge)
        bottom = bool(edges & Qt.BottomEdge)
        if (left and top) or (right and bottom):
            return Qt.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return Qt.SizeBDiagCursor
        if left or right:
            return Qt.SizeHorCursor
        if top or bottom:
            return Qt.SizeVerCursor
        return None

    def resize_hover(self, global_pos: QPoint) -> None:
        cursor = self._cursor_for(self._edges_at(global_pos))
        widget = self.sender()
        target = widget if isinstance(widget, QWidget) else self.client
        if cursor is None:
            target.unsetCursor()
        else:
            target.setCursor(cursor)

    def resize_press(self, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        edges = self._edges_at(event.globalPosition().toPoint())
        if not edges:
            return False
        handle = self.windowHandle()
        if handle is None:
            return False
        handle.startSystemResize(edges)
        return True

    # -- 全屏时隐藏窗口装饰 ----------------------------------------------- #
    def set_native_frame(self, enabled: bool) -> None:
        """切换“系统原生边框 / 仿 XP 无边框”。需要重新 show() 才生效。"""
        self.setWindowFlag(Qt.FramelessWindowHint, not enabled)
        self.caption.setVisible(not enabled)
        self.setAttribute(Qt.WA_TranslucentBackground, ROUNDED_CORNERS and not enabled)
        if enabled:
            self.client_layout.setContentsMargins(0, 0, 0, 0)
            self.setStyleSheet("")
        else:
            self.client_layout.setContentsMargins(3, 1, 3, 3)
            if ROUNDED_CORNERS:
                self.setStyleSheet("QMainWindow { background: transparent; }")
        self.client.update()

    def set_window_chrome_visible(self, visible: bool) -> None:
        """进入全屏时隐藏标题栏与边框。"""
        if visible == self._chrome_visible:
            return
        self._chrome_visible = visible
        self.caption.setVisible(visible)
        if visible:
            self.client_layout.setContentsMargins(3, 1, 3, 3)
            self.setAttribute(Qt.WA_TranslucentBackground, ROUNDED_CORNERS)
            self.setStyleSheet(
                "QMainWindow { background: transparent; }" if ROUNDED_CORNERS else ""
            )
        else:
            self.client_layout.setContentsMargins(0, 0, 0, 0)
            self.setAttribute(Qt.WA_TranslucentBackground, False)
            self.setStyleSheet("QMainWindow { background: #000000; }")
        self.client.update()


# --------------------------------------------------------------------------- #
# 对话框
# --------------------------------------------------------------------------- #
class XPDialog(QDialog):
    """仿 XP 的无边框对话框（可拖动，含标题栏与底部按钮区）。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = APP_NAME,
        minimizable: bool = False,
        icon_name: str = "app",
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, ROUNDED_CORNERS)
        if ROUNDED_CORNERS:
            self.setStyleSheet("QDialog { background: transparent; }")
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.client = _ClientFrameDialog(self)
        outer.addWidget(self.client)

        self.client_layout = QVBoxLayout(self.client)
        self.client_layout.setContentsMargins(3, 1, 3, 3)
        self.client_layout.setSpacing(0)

        self.caption = LunaTitleBar(
            self,
            title,
            minimizable=minimizable,
            maximizable=False,
            closable=True,
            show_icon=icon_name is not None,
        )
        if icon_name is not None:
            self.caption.set_icon(icons.icon(icon_name, 16))
        self.caption.close_requested.connect(self.reject)
        self.client_layout.addWidget(self.caption)

        self.body = QWidget(self.client)
        self.client_layout.addWidget(self.body, 1)

    def setWindowTitle(self, title: str) -> None:  # noqa: N802
        super().setWindowTitle(title)
        if hasattr(self, "caption"):
            self.caption.set_title(title)

    def changeEvent(self, event) -> None:  # noqa: D102
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange:
            self.caption.set_active(self.isActiveWindow())


class _ClientFrameDialog(QWidget):
    """对话框客户区背景。"""

    def __init__(self, dialog: QDialog) -> None:
        super().__init__(dialog)
        self.setObjectName("xpClient")
        theme.notifier.changed.connect(lambda _spec: self.update())

    def paintEvent(self, event) -> None:  # noqa: D102
        spec = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = _rounded_path(rect, float(spec.rounded) if ROUNDED_CORNERS else 0.0)
        p.setPen(QPen(QColor(spec.border), 1))
        p.setBrush(QColor(spec.face))
        p.drawPath(path)


class StartupSplash(QWidget):
    """启动画面。

    程序启动到主窗口可见之间有几百毫秒到一两秒的准备时间（解锁数据、
    构造界面、创建渲染引擎），先显示这个画面可以立刻给出视觉反馈，
    避免「点了没反应」的感觉。
    """

    def __init__(self, app_name: str = APP_NAME, version: str = "", author: str = "") -> None:
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(430, 236)
        self._app_name = app_name
        self._version = version
        self._author = author
        self._message = tr("正在启动…")
        self._progress = 6
        self._icon = icons.app_icon()
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._center()

    def _center(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        self.move(rect.center().x() - self.width() // 2,
                  rect.center().y() - self.height() // 2)

    def set_message(self, text: str) -> None:
        self._message = text
        self._progress = min(92, self._progress + 18)
        # 只重绘启动画面本身：processEvents() 会连带处理整棵控件树的样式
        # 重算，实测会让启动慢 300ms 以上
        self.repaint()

    def _tick(self) -> None:
        if self._progress < 90:
            self._progress += 1
            self.update()

    def paintEvent(self, event) -> None:  # noqa: D102
        spec = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # 外框 + 标题栏
        radius = float(max(4, spec.rounded))
        path = _rounded_path(rect, radius)
        p.setPen(QPen(QColor(spec.border), 1))
        p.setBrush(QColor(spec.face))
        p.drawPath(path)

        caption_height = 30.0
        p.setClipPath(path)
        grad = QLinearGradient(rect.topLeft(), QPointF(0, rect.top() + caption_height))
        if spec.caption_style == "gradient":
            grad.setColorAt(0.0, QColor(spec.caption_top))
            grad.setColorAt(0.45, QColor(spec.caption_mid))
            grad.setColorAt(1.0, QColor(spec.caption_bottom))
        else:
            grad.setColorAt(0.0, QColor(spec.caption_top))
            grad.setColorAt(1.0, QColor(spec.caption_bottom))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRect(QRectF(rect.left(), rect.top(), rect.width(), caption_height))
        p.setClipping(False)

        # 标题文字
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(9.5)
        p.setFont(font)
        p.setPen(QColor(spec.caption_text))
        p.drawText(QRectF(rect.left() + 10, rect.top(), rect.width() - 20, caption_height),
                   Qt.AlignVCenter | Qt.AlignLeft, f"{self._app_name}  {self._version}")

        # 图标
        icon_size = 64
        icon_rect = QRectF(rect.left() + 28, rect.top() + caption_height + 22, icon_size, icon_size)
        if not self._icon.isNull():
            p.drawPixmap(int(icon_rect.left()), int(icon_rect.top()),
                         self._icon.pixmap(icon_size, icon_size))

        # 名称与作者
        text_left = icon_rect.right() + 20
        title_font = QFont(self.font())
        title_font.setBold(True)
        title_font.setPointSizeF(15.0)
        p.setFont(title_font)
        p.setPen(QColor(spec.text))
        p.drawText(QRectF(text_left, icon_rect.top() - 4, rect.width() - text_left - 20, 32),
                   Qt.AlignVCenter | Qt.AlignLeft, self._app_name)

        small = QFont(self.font())
        small.setPointSizeF(8.5)
        p.setFont(small)
        p.setPen(QColor(spec.text_dim))
        p.drawText(QRectF(text_left, icon_rect.top() + 28, rect.width() - text_left - 20, 24),
                   Qt.AlignVCenter | Qt.AlignLeft,
                   trf('版本 {0}    作者：{1}', self._version, self._author))

        # 进度条
        bar_rect = QRectF(rect.left() + 24, rect.bottom() - 46, rect.width() - 48, 12)
        p.setPen(QPen(QColor(spec.field_border), 1))
        p.setBrush(QColor(spec.field_bg))
        p.drawRoundedRect(bar_rect, 2, 2)
        inner = bar_rect.adjusted(2, 2, -2, -2)
        width = inner.width() * max(0.0, min(100, self._progress)) / 100.0
        if width > 1:
            chunk = QLinearGradient(inner.topLeft(), QPointF(0, inner.bottom()))
            chunk.setColorAt(0.0, QColor(spec.progress_top))
            chunk.setColorAt(0.5, QColor(spec.progress_mid))
            chunk.setColorAt(1.0, QColor(spec.progress_bottom))
            p.setPen(Qt.NoPen)
            p.setBrush(chunk)
            p.drawRoundedRect(QRectF(inner.left(), inner.top(), width, inner.height()), 1, 1)

        # 状态文字
        p.setFont(small)
        p.setPen(QColor(spec.text_dim))
        p.drawText(QRectF(rect.left() + 24, rect.bottom() - 32, rect.width() - 48, 22),
                   Qt.AlignVCenter | Qt.AlignLeft, self._message)

    def finish(self) -> None:
        self._timer.stop()
        self.close()


class ToastNotification(QWidget):
    """右下角气泡提示。

    下载完成等事件用它提醒用户：可以点右上角的 × 关闭，
    鼠标停在上面时不会消失，移开后继续计时，超时自动关闭。
    """

    _open_toasts: list["ToastNotification"] = []

    def __init__(
        self,
        title: str,
        message: str,
        *,
        icon_name: str = "cat",
        timeout_ms: int = 5000,
        accent: str = "",
        on_click: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedWidth(360)
        self._on_click = on_click
        self._accent = accent or theme.current().highlight
        self._hovering = False

        spec = theme.current()
        self.setStyleSheet(
            f"QWidget#toastCard {{ background: {spec.face};"
            f" border: 1px solid {self._accent}; border-radius: 10px; }}"
            f"QLabel {{ color: {spec.text}; background: transparent; }}"
            f"QToolButton {{ border: none; background: transparent;"
            f" color: {spec.text_dim}; font-size: 15px; }}"
            f"QToolButton:hover {{ color: {self._accent}; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget(self)
        card.setObjectName("toastCard")
        outer.addWidget(card)

        row = QHBoxLayout(card)
        row.setContentsMargins(12, 10, 8, 12)
        row.setSpacing(10)

        icon_label = QLabel(card)
        icon_label.setPixmap(icons.icon(icon_name, 32).pixmap(32, 32))
        icon_label.setFixedSize(36, 36)
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        row.addWidget(icon_label, 0, Qt.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(3)
        title_label = QLabel(title, card)
        title_font = QFont(self.font())
        title_font.setBold(True)
        title_font.setPointSizeF(9.5)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {self._accent};")
        text_box.addWidget(title_label)

        body = QLabel(message, card)
        body.setWordWrap(True)
        body.setMinimumWidth(250)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_box.addWidget(body)
        text_box.addStretch(1)
        row.addLayout(text_box, 1)

        close = QToolButton(card)
        close.setText("✕")
        close.setCursor(Qt.ArrowCursor)
        close.setToolTip(tr("关闭"))
        close.clicked.connect(self.close)
        row.addWidget(close, 0, Qt.AlignTop)

        self.adjustSize()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(800, int(timeout_ms)))
        self._timer.timeout.connect(self.close)
        self._place()
        self._timer.start()

    # ------------------------------------------------------------------ #
    def _place(self) -> None:
        """放在可用桌面右下角，多个气泡自动向上堆叠。"""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 16
        offset = 0
        for other in ToastNotification._open_toasts:
            try:
                offset += other.height() + 8
            except Exception:
                continue
        x = area.right() - self.width() - margin
        y = area.bottom() - self.height() - margin - offset
        self.move(max(area.left(), x), max(area.top(), y))

    def enterEvent(self, event) -> None:  # noqa: D102
        self._hovering = True
        self._timer.stop()          # 鼠标停在上面时不要消失
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: D102
        self._hovering = False
        self._timer.start(2000)     # 移开后 2 秒再自动关闭
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: D102
        if self._on_click is not None and event.button() == Qt.LeftButton:
            try:
                self._on_click()
            except Exception:
                pass
            self.close()
            return
        super().mouseReleaseEvent(event)

    def showEvent(self, event) -> None:  # noqa: D102
        super().showEvent(event)
        if self not in ToastNotification._open_toasts:
            ToastNotification._open_toasts.append(self)
        self._place()
        # 淡入
        try:
            self.setWindowOpacity(0.0)
            self._fade = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade.setDuration(160)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        except Exception:
            self.setWindowOpacity(1.0)

    def closeEvent(self, event) -> None:  # noqa: D102
        self._timer.stop()
        try:
            ToastNotification._open_toasts.remove(self)
        except ValueError:
            pass
        super().closeEvent(event)


class HeadingLabel(QLabel):
    """XP 属性页里的蓝色标题文字。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(9.5)
        self.setFont(font)
        self.setProperty("role", "heading")
