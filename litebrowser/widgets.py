"""仿 Windows XP (Luna) 风格的基础控件：标题栏、无边框窗口、对话框。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, Signal
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
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .config import APP_NAME

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
        self.setFixedSize(QSize(21, 21)
                          if kind != "close" else QSize(23, 21))
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(
            {"min": "最小化", "max": "最大化", "restore": "向下还原", "close": "关闭"}.get(
                kind, ""
            )
        )

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
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        hot = self.underMouse() and self.isEnabled()
        down = self.isDown()

        if self.kind == "close":
            top, bottom = QColor("#F5A08F"), QColor("#C6362B")
            if hot:
                top, bottom = QColor("#FFD3C4"), QColor("#E04A34")
            if down:
                top, bottom = QColor("#B93526"), QColor("#E2877A")
        else:
            top, bottom = QColor("#6DB2F7"), QColor("#1050C8")
            if hot:
                top, bottom = QColor("#A8D4FF"), QColor("#1C63E0")
            if down:
                top, bottom = QColor("#0C3E9E"), QColor("#5E9BE8")

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bottom)
        p.setBrush(grad)
        p.setPen(QPen(QColor("#FFFFFF"), 1))
        p.drawRoundedRect(rect, 3.5, 3.5)

        pen = QPen(QColor("#FFFFFF"), 1.6)
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

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_system_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 3, 2)
        layout.setSpacing(2)
        layout.addStretch(1)

        self._buttons: list[_CaptionButton] = []
        if minimizable:
            btn = _CaptionButton("min", self)
            btn.clicked.connect(self.minimize_requested.emit)
            layout.addWidget(btn)
            self._buttons.append(btn)
        if maximizable:
            self._btn_max = _CaptionButton("max", self)
            self._btn_max.clicked.connect(self.maximize_requested.emit)
            layout.addWidget(self._btn_max)
            self._buttons.append(self._btn_max)
        else:
            self._btn_max = None
        if closable:
            btn = _CaptionButton("close", self)
            btn.clicked.connect(self.close_requested.emit)
            layout.addWidget(btn)
            self._buttons.append(btn)

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

    def set_icon(self, icon) -> None:
        self._icon = icon
        self.update()

    # -- 绘制 ------------------------------------------------------------- #
    def paintEvent(self, event) -> None:  # noqa: D102
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())

        maximized = self._window.isMaximized() or self._window.isFullScreen()
        radius = 0.0 if maximized else 7.0

        if self._active:
            top, mid, bottom = (
                QColor(theme.CAPTION_TOP),
                QColor(theme.CAPTION_MID),
                QColor(theme.CAPTION_BOTTOM),
            )
        else:
            top, mid, bottom = (
                QColor(theme.CAPTION_INACTIVE_TOP),
                QColor(theme.CAPTION_INACTIVE_MID),
                QColor(theme.CAPTION_INACTIVE_BOTTOM),
            )

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, top)
        grad.setColorAt(0.42, mid)
        grad.setColorAt(0.55, mid)
        grad.setColorAt(1.0, bottom)

        path = _rounded_path(rect, radius)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(path)

        # 顶部高光，营造 Luna 的立体感
        p.setClipPath(path)
        highlight = QLinearGradient(rect.topLeft(), QPoint(0, int(rect.top() + rect.height() * 0.45)))
        highlight.setColorAt(0.0, QColor(255, 255, 255, 150))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(highlight)
        p.drawRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height() * 0.5))
        p.setClipping(False)

        # 标题文字
        if self._title:
            text_rect = rect.adjusted(26 if self._show_icon else 8, 0, -80, 0)
            font = QFont(self.font())
            font.setBold(True)
            font.setPointSizeF(9.0)
            p.setFont(font)
            p.setPen(QColor(0, 0, 0, 110))
            p.drawText(text_rect.translated(1, 1), Qt.AlignVCenter | Qt.AlignLeft,
                       self._elide(p, text_rect.width(), self._title))
            p.setPen(QColor(theme.CAPTION_TEXT if self._active else "#F0F4FF"))
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                       self._elide(p, text_rect.width(), self._title))

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
        act_restore = menu.addAction("还原(R)")
        act_min = menu.addAction("最小化(N)")
        act_max = menu.addAction("最大化(X)")
        menu.addSeparator()
        act_close = menu.addAction("关闭(C)")

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

    def paintEvent(self, event) -> None:  # noqa: D102
        if self._window.isFullScreen():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        maximized = self._window.isMaximized()
        radius = 0.0 if (maximized or not ROUNDED_CORNERS) else 8.0

        path = _rounded_path(rect, radius)
        p.setPen(QPen(QColor(theme.CAPTION_BORDER), 1))
        p.setBrush(QColor(theme.FACE))
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

    def paintEvent(self, event) -> None:  # noqa: D102
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = _rounded_path(rect, 8.0 if ROUNDED_CORNERS else 0.0)
        p.setPen(QPen(QColor(theme.CAPTION_BORDER), 1))
        p.setBrush(QColor(theme.FACE))
        p.drawPath(path)


class HeadingLabel(QLabel):
    """XP 属性页里的蓝色标题文字。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(9.5)
        self.setFont(font)
        self.setStyleSheet("color: #003C74;")
