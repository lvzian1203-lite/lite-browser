"""用 QPainter 现场绘制仿 Windows XP 风格的小图标。

全部图标都是代码绘制，不依赖外部图片文件，方便打包成单个 exe。
每个绘制函数的坐标都基于 ``size`` 归一化，因此同一份代码可以渲染任意尺寸。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

_CACHE: dict[tuple[str, int], QIcon] = {}

# XP（Luna）常用配色
XP_BLUE_DARK = QColor("#0A246A")
XP_GREEN = QColor("#2E8B2E")
XP_GREEN_LIGHT = QColor("#7CC96A")
XP_RED = QColor("#C6362B")
XP_RED_LIGHT = QColor("#F07A6E")
XP_YELLOW = QColor("#FFD34A")
XP_FOLDER = QColor("#F0C14B")


def icon(name: str, size: int = 16) -> QIcon:
    """取得指定名称的图标（带缓存，自动附带 2x/3x 高清版本）。"""
    key = (name, size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    result = QIcon()
    for factor in (1, 2, 3):
        result.addPixmap(_render(name, size * factor))
    _CACHE[key] = result
    return result


def pixmap(name: str, size: int) -> QPixmap:
    return _render(name, size)


def app_icon() -> QIcon:
    """程序图标：一个仿 XP 的小浏览器窗口。"""
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(_render("app", size))
    return result


def _render(name: str, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    drawer = _DRAWERS.get(name)
    if drawer is not None:
        try:
            drawer(painter, float(size))
        except Exception:  # 图标绘制失败不应影响程序运行
            pass
    painter.end()
    return pm


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def _vgrad(rect: QRectF, top: QColor, bottom: QColor) -> QBrush:
    grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    grad.setColorAt(0.0, top)
    grad.setColorAt(1.0, bottom)
    return QBrush(grad)


def _shade(color: QColor, factor: float) -> QColor:
    """factor < 1 变暗，> 1 变亮。"""
    if factor <= 1.0:
        return color.darker(int(100 / max(factor, 0.05)))
    return color.lighter(int(100 * factor))


def _star_polygon(cx: float, cy: float, outer: float, inner: float, points: int = 5) -> QPolygonF:
    poly = QPolygonF()
    start = -math.pi / 2
    for i in range(points * 2):
        radius = outer if i % 2 == 0 else inner
        angle = start + i * math.pi / points
        poly.append(QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return poly


def _arrow_polygon(size: float, direction: int) -> QPolygonF:
    """direction: 1 向右, -1 向左。"""
    y = size * 0.5
    tip = size * 0.94
    head = size * 0.52
    hh = size * 0.30
    sh = size * 0.145
    tail = size * 0.12
    pts = [
        (tip, y),
        (tip - head, y - hh),
        (tip - head, y - sh),
        (tail, y - sh),
        (tail, y + sh),
        (tip - head, y + sh),
        (tip - head, y + hh),
    ]
    poly = QPolygonF()
    for x, py in pts:
        poly.append(QPointF(size - x if direction < 0 else x, py))
    return poly


# --------------------------------------------------------------------------- #
# 具体图标
# --------------------------------------------------------------------------- #
def _draw_back(p: QPainter, s: float) -> None:
    poly = _arrow_polygon(s, -1)
    rect = poly.boundingRect()
    p.setBrush(_vgrad(rect, XP_GREEN_LIGHT, XP_GREEN))
    p.setPen(QPen(QColor("#1B5E20"), max(1.0, s * 0.06)))
    p.drawPolygon(poly)


def _draw_forward(p: QPainter, s: float) -> None:
    poly = _arrow_polygon(s, 1)
    rect = poly.boundingRect()
    p.setBrush(_vgrad(rect, XP_GREEN_LIGHT, XP_GREEN))
    p.setPen(QPen(QColor("#1B5E20"), max(1.0, s * 0.06)))
    p.drawPolygon(poly)


def _draw_stop(p: QPainter, s: float) -> None:
    rect = QRectF(s * 0.08, s * 0.08, s * 0.84, s * 0.84)
    p.setBrush(_vgrad(rect, XP_RED_LIGHT, XP_RED))
    p.setPen(QPen(QColor("#7B1A12"), max(1.0, s * 0.06)))
    p.drawEllipse(rect)
    pen = QPen(QColor("#FFFFFF"), max(1.4, s * 0.16))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.33, s * 0.33), QPointF(s * 0.67, s * 0.67))
    p.drawLine(QPointF(s * 0.67, s * 0.33), QPointF(s * 0.33, s * 0.67))


def _draw_refresh(p: QPainter, s: float) -> None:
    rect = QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72)
    pen = QPen(QColor("#1E7A32"), max(1.4, s * 0.15))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(rect, 55 * 16, 265 * 16)

    # 箭头
    angle = math.radians(55)
    cx = cy = s * 0.5
    rx = ry = s * 0.36
    x = cx + rx * math.cos(angle)
    y = cy - ry * math.sin(angle)
    head = s * 0.17
    tri = QPolygonF(
        [
            QPointF(x + head * 0.9, y - head * 0.35),
            QPointF(x - head * 0.55, y - head * 0.75),
            QPointF(x + head * 0.15, y + head * 0.85),
        ]
    )
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1E7A32"))
    p.drawPolygon(tri)


def _draw_home(p: QPainter, s: float) -> None:
    body = QRectF(s * 0.17, s * 0.45, s * 0.66, s * 0.43)
    p.setPen(QPen(QColor("#8A7A55"), max(1.0, s * 0.05)))
    p.setBrush(_vgrad(body, QColor("#FBF3DC"), QColor("#E3D3AC")))
    p.drawRect(body)

    roof = QPolygonF(
        [
            QPointF(s * 0.5, s * 0.08),
            QPointF(s * 0.95, s * 0.47),
            QPointF(s * 0.05, s * 0.47),
        ]
    )
    p.setBrush(_vgrad(QRectF(s * 0.05, s * 0.08, s * 0.9, s * 0.39), QColor("#D9614B"), QColor("#A63A28")))
    p.setPen(QPen(QColor("#7E2C1E"), max(1.0, s * 0.05)))
    p.drawPolygon(roof)

    door = QRectF(s * 0.41, s * 0.61, s * 0.18, s * 0.27)
    p.setBrush(QColor("#8A5A2B"))
    p.setPen(QPen(QColor("#5C3A17"), max(1.0, s * 0.04)))
    p.drawRect(door)

    win = QRectF(s * 0.23, s * 0.55, s * 0.12, s * 0.12)
    p.setBrush(QColor("#BFE3FF"))
    p.drawRect(win)
    win2 = QRectF(s * 0.65, s * 0.55, s * 0.12, s * 0.12)
    p.drawRect(win2)


def _draw_star(p: QPainter, s: float) -> None:
    poly = _star_polygon(s * 0.5, s * 0.53, s * 0.47, s * 0.19)
    p.setPen(QPen(QColor("#B07C10"), max(1.0, s * 0.06)))
    p.setBrush(_vgrad(QRectF(s * 0.05, s * 0.06, s * 0.9, s * 0.9), QColor("#FFE98A"), XP_YELLOW))
    p.drawPolygon(poly)


def _draw_star_add(p: QPainter, s: float) -> None:
    poly = _star_polygon(s * 0.46, s * 0.46, s * 0.42, s * 0.17)
    p.setPen(QPen(QColor("#B07C10"), max(1.0, s * 0.06)))
    p.setBrush(_vgrad(QRectF(s * 0.05, s * 0.05, s * 0.85, s * 0.85), QColor("#FFE98A"), XP_YELLOW))
    p.drawPolygon(poly)

    badge = QRectF(s * 0.52, s * 0.52, s * 0.46, s * 0.46)
    p.setBrush(_vgrad(badge, QColor("#8FD97A"), QColor("#2E8B2E")))
    p.setPen(QPen(QColor("#14521B"), max(1.0, s * 0.06)))
    p.drawEllipse(badge)
    pen = QPen(QColor("#FFFFFF"), max(1.2, s * 0.10))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.75, s * 0.62), QPointF(s * 0.75, s * 0.88))
    p.drawLine(QPointF(s * 0.62, s * 0.75), QPointF(s * 0.88, s * 0.75))


def _draw_bookmarks(p: QPainter, s: float) -> None:
    body = QRectF(s * 0.08, s * 0.30, s * 0.84, s * 0.48)
    p.setPen(QPen(QColor("#C08A18"), max(1.0, s * 0.05)))
    p.setBrush(_vgrad(body, QColor("#FFE9A8"), XP_FOLDER))
    p.drawRect(body)

    tab = QPolygonF(
        [
            QPointF(s * 0.08, s * 0.30),
            QPointF(s * 0.34, s * 0.16),
            QPointF(s * 0.60, s * 0.16),
            QPointF(s * 0.60, s * 0.30),
        ]
    )
    p.setBrush(QColor("#FFDE8A"))
    p.drawPolygon(tab)

    mini = _star_polygon(s * 0.60, s * 0.54, s * 0.20, s * 0.085)
    p.setPen(QPen(QColor("#B07C10"), max(1.0, s * 0.04)))
    p.setBrush(QColor("#FFFFFF"))
    p.drawPolygon(mini)


def _draw_settings(p: QPainter, s: float) -> None:
    cx = cy = s * 0.5
    p.save()
    p.translate(cx, cy)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#8C9AA8"))
    for i in range(8):
        p.save()
        p.rotate(i * 45)
        p.drawRoundedRect(QRectF(-s * 0.075, -s * 0.48, s * 0.15, s * 0.22), s * 0.04, s * 0.04)
        p.restore()
    ring = QRectF(-s * 0.34, -s * 0.34, s * 0.68, s * 0.68)
    p.setBrush(_vgrad(ring, QColor("#D7DEE6"), QColor("#7C8B99")))
    p.drawEllipse(ring)
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    p.drawEllipse(QRectF(-s * 0.14, -s * 0.14, s * 0.28, s * 0.28))
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    p.restore()


def _draw_fullscreen(p: QPainter, s: float) -> None:
    pen = QPen(QColor("#1E5FA8"), max(1.4, s * 0.13))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    a = s * 0.16
    b = s * 0.40
    c = s * 0.84
    d = s * 0.60
    # 左上
    p.drawPolyline(QPolygonF([QPointF(a, b), QPointF(a, a), QPointF(b, a)]))
    # 右上
    p.drawPolyline(QPolygonF([QPointF(d, a), QPointF(c, a), QPointF(c, b)]))
    # 右下
    p.drawPolyline(QPolygonF([QPointF(c, d), QPointF(c, c), QPointF(d, c)]))
    # 左下
    p.drawPolyline(QPolygonF([QPointF(b, c), QPointF(a, c), QPointF(a, d)]))


def _draw_plus(p: QPainter, s: float) -> None:
    rect = QRectF(s * 0.10, s * 0.10, s * 0.80, s * 0.80)
    p.setPen(QPen(QColor("#14521B"), max(1.0, s * 0.06)))
    p.setBrush(_vgrad(rect, QColor("#9CDF85"), QColor("#3E9B34")))
    p.drawEllipse(rect)
    pen = QPen(QColor("#FFFFFF"), max(1.3, s * 0.13))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.5, s * 0.26), QPointF(s * 0.5, s * 0.74))
    p.drawLine(QPointF(s * 0.26, s * 0.5), QPointF(s * 0.74, s * 0.5))


def _draw_close(p: QPainter, s: float) -> None:
    pen = QPen(QColor("#5A5A5A"), max(1.3, s * 0.15))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.28, s * 0.28), QPointF(s * 0.72, s * 0.72))
    p.drawLine(QPointF(s * 0.72, s * 0.28), QPointF(s * 0.28, s * 0.72))


def _draw_info(p: QPainter, s: float) -> None:
    rect = QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88)
    p.setPen(QPen(QColor("#123C7A"), max(1.0, s * 0.05)))
    p.setBrush(_vgrad(rect, QColor("#8FC4FF"), QColor("#1E5FA8")))
    p.drawEllipse(rect)

    font = QFont("Times New Roman")
    font.setPixelSize(max(6, int(s * 0.66)))
    font.setBold(True)
    font.setItalic(True)
    p.setFont(font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(rect, Qt.AlignCenter, "i")


def _draw_globe(p: QPainter, s: float) -> None:
    rect = QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88)
    p.setPen(QPen(QColor("#1B5E8A"), max(1.0, s * 0.05)))
    p.setBrush(_vgrad(rect, QColor("#BFE9FF"), QColor("#3E9BD6")))
    p.drawEllipse(rect)

    pen = QPen(QColor("#1B5E8A"), max(0.7, s * 0.045))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(s * 0.34, s * 0.06, s * 0.32, s * 0.88))
    p.drawLine(QPointF(s * 0.06, s * 0.5), QPointF(s * 0.94, s * 0.5))
    p.drawArc(QRectF(s * 0.02, s * 0.24, s * 0.96, s * 0.52), 20 * 16, 140 * 16)
    p.drawArc(QRectF(s * 0.02, s * 0.24, s * 0.96, s * 0.52), 200 * 16, 140 * 16)


def _draw_go(p: QPainter, s: float) -> None:
    poly = _arrow_polygon(s, 1)
    rect = poly.boundingRect()
    p.setBrush(_vgrad(rect, QColor("#7CD4F0"), QColor("#1E7FB8")))
    p.setPen(QPen(QColor("#0F4C73"), max(1.0, s * 0.06)))
    p.drawPolygon(poly)


def _draw_exit(p: QPainter, s: float) -> None:
    # 一扇门 + 向外的箭头
    body = QRectF(s * 0.10, s * 0.10, s * 0.45, s * 0.80)
    p.setPen(QPen(QColor("#7A6A45"), max(1.0, s * 0.05)))
    p.setBrush(_vgrad(body, QColor("#FBF3DC"), QColor("#E0D0A8")))
    p.drawRect(body)

    pen = QPen(QColor("#C6362B"), max(1.4, s * 0.13))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.52, s * 0.5), QPointF(s * 0.92, s * 0.5))
    tri = QPolygonF(
        [QPointF(s * 0.95, s * 0.5), QPointF(s * 0.68, s * 0.30), QPointF(s * 0.68, s * 0.70)]
    )
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#C6362B"))
    p.drawPolygon(tri)


def _draw_tab_new(p: QPainter, s: float) -> None:
    _draw_plus(p, s)


def _draw_zoom_in(p: QPainter, s: float) -> None:
    _draw_zoom(p, s, plus=True)


def _draw_zoom_out(p: QPainter, s: float) -> None:
    _draw_zoom(p, s, plus=False)


def _draw_zoom(p: QPainter, s: float, *, plus: bool) -> None:
    rect = QRectF(s * 0.08, s * 0.08, s * 0.66, s * 0.66)
    p.setPen(QPen(QColor("#3C3C3C"), max(1.2, s * 0.10)))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(rect)
    p.drawLine(QPointF(s * 0.66, s * 0.66), QPointF(s * 0.94, s * 0.94))
    pen = QPen(QColor("#1E5FA8"), max(1.2, s * 0.11))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.24, s * 0.41), QPointF(s * 0.58, s * 0.41))
    if plus:
        p.drawLine(QPointF(s * 0.41, s * 0.24), QPointF(s * 0.41, s * 0.58))


def _draw_find(p: QPainter, s: float) -> None:
    _draw_zoom(p, s, plus=False)


def _draw_app(p: QPainter, s: float) -> None:
    """程序大图标：仿 XP 窗口 + 地球。"""
    body = QRectF(s * 0.04, s * 0.12, s * 0.92, s * 0.78)
    p.setPen(QPen(QColor("#0A3E8C"), max(1.0, s * 0.02)))
    p.setBrush(QColor("#ECE9D8"))
    p.drawRoundedRect(body, s * 0.09, s * 0.09)

    caption = QRectF(s * 0.04, s * 0.12, s * 0.92, s * 0.21)
    path = QPainterPath()
    path.addRoundedRect(body, s * 0.09, s * 0.09)
    p.setClipPath(path)
    grad = QLinearGradient(caption.topLeft(), caption.bottomLeft())
    grad.setColorAt(0.0, QColor("#4C9BF7"))
    grad.setColorAt(0.45, QColor("#0B5FE6"))
    grad.setColorAt(1.0, QColor("#0A46B8"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRect(caption)

    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    p.drawRoundedRect(QRectF(s * 0.74, s * 0.16, s * 0.15, s * 0.10), s * 0.02, s * 0.02)
    p.setClipping(False)

    globe = QRectF(s * 0.22, s * 0.38, s * 0.56, s * 0.56)
    p.setBrush(_vgrad(globe, QColor("#CFEEFF"), QColor("#2E8BC0")))
    p.setPen(QPen(QColor("#123F63"), max(1.0, s * 0.028)))
    p.drawEllipse(globe)

    # 经纬线（裁剪在地球内部，避免出现杂线）
    p.save()
    clip = QPainterPath()
    clip.addEllipse(globe.adjusted(s * 0.012, s * 0.012, -s * 0.012, -s * 0.012))
    p.setClipPath(clip)
    p.setPen(QPen(QColor("#1B5E8A"), max(0.8, s * 0.022)))
    p.setBrush(Qt.NoBrush)
    equator = globe.center().y()
    p.drawLine(QPointF(globe.left(), equator), QPointF(globe.right(), equator))
    p.drawEllipse(QRectF(globe.center().x() - s * 0.11, globe.top(), s * 0.22, globe.height()))
    p.drawEllipse(QRectF(globe.left(), globe.center().y() - s * 0.11,
                         globe.width(), s * 0.22))
    p.drawArc(QRectF(globe.left(), globe.top() + s * 0.04,
                     globe.width(), globe.height() * 0.62), 20 * 16, 140 * 16)
    p.drawArc(QRectF(globe.left(), globe.bottom() - s * 0.04 - globe.height() * 0.62,
                     globe.width(), globe.height() * 0.62), 200 * 16, 140 * 16)
    p.restore()


def _draw_download(p: QPainter, s: float) -> None:
    """下载：向下的箭头 + 托盘。"""
    pen = QPen(QColor("#1E5FA8"), max(1.3, s * 0.13))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(s * 0.5, s * 0.10), QPointF(s * 0.5, s * 0.56))

    tri = QPolygonF(
        [
            QPointF(s * 0.5, s * 0.68),
            QPointF(s * 0.28, s * 0.44),
            QPointF(s * 0.72, s * 0.44),
        ]
    )
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2E8B2E"))
    p.drawPolygon(tri)

    pen = QPen(QColor("#7A6A45"), max(1.3, s * 0.12))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.18, s * 0.84), QPointF(s * 0.82, s * 0.84))


def _draw_history(p: QPainter, s: float) -> None:
    """历史记录：时钟。"""
    rect = QRectF(s * 0.08, s * 0.08, s * 0.84, s * 0.84)
    p.setPen(QPen(QColor("#1B5E8A"), max(1.0, s * 0.07)))
    p.setBrush(_vgrad(rect, QColor("#FFFDF0"), QColor("#E8E2C8")))
    p.drawEllipse(rect)

    pen = QPen(QColor("#2E4A66"), max(1.2, s * 0.09))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.5, s * 0.5), QPointF(s * 0.5, s * 0.26))
    p.drawLine(QPointF(s * 0.5, s * 0.5), QPointF(s * 0.69, s * 0.60))


def _draw_incognito(p: QPainter, s: float) -> None:
    """无痕浏览：礼帽 + 眼镜。"""
    brim = QRectF(s * 0.10, s * 0.44, s * 0.80, s * 0.13)
    p.setPen(QPen(QColor("#2B2B2B"), max(1.0, s * 0.05)))
    p.setBrush(QColor("#4A4A4A"))
    p.drawRoundedRect(brim, s * 0.05, s * 0.05)

    crown = QPainterPath()
    crown.moveTo(s * 0.28, s * 0.44)
    crown.lineTo(s * 0.32, s * 0.12)
    crown.lineTo(s * 0.68, s * 0.12)
    crown.lineTo(s * 0.72, s * 0.44)
    crown.closeSubpath()
    p.setBrush(QColor("#5C5C5C"))
    p.drawPath(crown)

    band = QRectF(s * 0.28, s * 0.34, s * 0.44, s * 0.10)
    p.setBrush(QColor("#C9A227"))
    p.setPen(Qt.NoPen)
    p.drawRect(band)

    p.setPen(QPen(QColor("#1F1F1F"), max(1.0, s * 0.045)))
    p.setBrush(QColor("#8FB8E0"))
    p.drawEllipse(QRectF(s * 0.14, s * 0.60, s * 0.30, s * 0.24))
    p.drawEllipse(QRectF(s * 0.56, s * 0.60, s * 0.30, s * 0.24))
    p.drawLine(QPointF(s * 0.44, s * 0.70), QPointF(s * 0.56, s * 0.70))


def _draw_folder_open(p: QPainter, s: float) -> None:
    _draw_bookmarks(p, s)


def _draw_lock(p: QPainter, s: float) -> None:
    """安全连接：挂锁。"""
    body = QRectF(s * 0.22, s * 0.44, s * 0.56, s * 0.46)
    p.setPen(QPen(QColor("#1B5E20"), max(1.0, s * 0.05)))
    p.setBrush(_vgrad(body, QColor("#B9E8A8"), QColor("#4CAE2A")))
    p.drawRoundedRect(body, s * 0.09, s * 0.09)

    pen = QPen(QColor("#2E6B2E"), max(1.2, s * 0.10))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(s * 0.32, s * 0.16, s * 0.36, s * 0.46), 0, 180 * 16)

    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(QRectF(s * 0.45, s * 0.58, s * 0.10, s * 0.16))


def _draw_warn(p: QPainter, s: float) -> None:
    """不安全：黄色三角警告。"""
    tri = QPolygonF(
        [
            QPointF(s * 0.5, s * 0.08),
            QPointF(s * 0.96, s * 0.88),
            QPointF(s * 0.04, s * 0.88),
        ]
    )
    p.setPen(QPen(QColor("#8A6A00"), max(1.0, s * 0.06)))
    p.setBrush(_vgrad(QRectF(0, s * 0.08, s, s * 0.8), QColor("#FFE98A"), QColor("#F0C13A")))
    p.drawPolygon(tri)

    pen = QPen(QColor("#5A4400"), max(1.4, s * 0.13))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.5, s * 0.36), QPointF(s * 0.5, s * 0.62))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#5A4400"))
    p.drawEllipse(QRectF(s * 0.455, s * 0.70, s * 0.09, s * 0.09))


def _draw_print(p: QPainter, s: float) -> None:
    """打印。"""
    paper = QRectF(s * 0.24, s * 0.08, s * 0.52, s * 0.30)
    p.setPen(QPen(QColor("#5A5A5A"), max(1.0, s * 0.05)))
    p.setBrush(QColor("#FFFFFF"))
    p.drawRect(paper)

    body = QRectF(s * 0.10, s * 0.36, s * 0.80, s * 0.34)
    p.setBrush(_vgrad(body, QColor("#D8D8D8"), QColor("#9A9A9A")))
    p.drawRoundedRect(body, s * 0.05, s * 0.05)

    out = QRectF(s * 0.24, s * 0.60, s * 0.52, s * 0.30)
    p.setBrush(QColor("#FFFFFF"))
    p.drawRect(out)
    pen = QPen(QColor("#7A7A7A"), max(0.8, s * 0.035))
    p.setPen(pen)
    for index in range(3):
        y = s * (0.68 + index * 0.07)
        p.drawLine(QPointF(s * 0.30, y), QPointF(s * 0.70, y))

    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2E8B2E"))
    p.drawEllipse(QRectF(s * 0.72, s * 0.42, s * 0.10, s * 0.10))


def _draw_save(p: QPainter, s: float) -> None:
    """保存网页：软盘。"""
    body = QRectF(s * 0.10, s * 0.10, s * 0.80, s * 0.80)
    p.setPen(QPen(QColor("#2A3A5A"), max(1.0, s * 0.055)))
    p.setBrush(_vgrad(body, QColor("#6E8CC0"), QColor("#2E4A80")))
    p.drawRoundedRect(body, s * 0.06, s * 0.06)

    p.setBrush(QColor("#E8E8E8"))
    p.setPen(Qt.NoPen)
    p.drawRect(QRectF(s * 0.28, s * 0.12, s * 0.44, s * 0.26))

    p.setBrush(QColor("#F5F5F5"))
    p.setPen(QPen(QColor("#8A8A8A"), max(0.7, s * 0.03)))
    p.drawRect(QRectF(s * 0.24, s * 0.52, s * 0.52, s * 0.34))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#9AA6B8"))
    p.drawRect(QRectF(s * 0.34, s * 0.60, s * 0.32, s * 0.05))
    p.drawRect(QRectF(s * 0.34, s * 0.70, s * 0.32, s * 0.05))


def _draw_paw(p: QPainter, s: float) -> None:
    """猫爪印（哈基米 UI 与下载提示用）。"""
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#E8892E"))
    # 掌心
    p.drawEllipse(QRectF(s * 0.24, s * 0.50, s * 0.52, s * 0.42))
    # 三个脚趾
    for cx, cy, r in ((0.22, 0.34, 0.13), (0.50, 0.24, 0.14), (0.78, 0.34, 0.13)):
        p.drawEllipse(QPointF(s * cx, s * cy), s * r, s * r * 1.08)


def _draw_cat(p: QPainter, s: float) -> None:
    """猫猫头（下载完成提示图标）。"""
    head = QRectF(s * 0.12, s * 0.22, s * 0.76, s * 0.66)
    p.setPen(QPen(QColor("#B4701E"), max(1.0, s * 0.05)))
    p.setBrush(_vgrad(head, QColor("#FFCE85"), QColor("#F09A38")))
    p.drawRoundedRect(head, s * 0.22, s * 0.22)

    # 耳朵
    p.setBrush(QColor("#F09A38"))
    for points in (
        (QPointF(s * 0.20, s * 0.30), QPointF(s * 0.26, s * 0.06), QPointF(s * 0.44, s * 0.22)),
        (QPointF(s * 0.80, s * 0.30), QPointF(s * 0.74, s * 0.06), QPointF(s * 0.56, s * 0.22)),
    ):
        p.drawPolygon(QPolygonF(list(points)))

    # 眼睛
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#3A2410"))
    p.drawEllipse(QRectF(s * 0.30, s * 0.44, s * 0.11, s * 0.14))
    p.drawEllipse(QRectF(s * 0.59, s * 0.44, s * 0.11, s * 0.14))
    # 鼻子与嘴
    p.setBrush(QColor("#C25A4A"))
    p.drawEllipse(QRectF(s * 0.455, s * 0.60, s * 0.09, s * 0.07))
    pen = QPen(QColor("#8A4A18"), max(0.8, s * 0.035))
    p.setPen(pen)
    p.drawArc(QRectF(s * 0.34, s * 0.62, s * 0.16, s * 0.14), 200 * 16, 140 * 16)
    p.drawArc(QRectF(s * 0.50, s * 0.62, s * 0.16, s * 0.14), 200 * 16, 140 * 16)


_DRAWERS = {
    "back": _draw_back,
    "forward": _draw_forward,
    "stop": _draw_stop,
    "refresh": _draw_refresh,
    "home": _draw_home,
    "star": _draw_star,
    "star_add": _draw_star_add,
    "bookmarks": _draw_bookmarks,
    "settings": _draw_settings,
    "fullscreen": _draw_fullscreen,
    "plus": _draw_plus,
    "close": _draw_close,
    "info": _draw_info,
    "globe": _draw_globe,
    "go": _draw_go,
    "exit": _draw_exit,
    "tab_new": _draw_tab_new,
    "zoom_in": _draw_zoom_in,
    "zoom_out": _draw_zoom_out,
    "find": _draw_find,
    "download": _draw_download,
    "history": _draw_history,
    "incognito": _draw_incognito,
    "folder": _draw_folder_open,
    "lock": _draw_lock,
    "warn": _draw_warn,
    "print": _draw_print,
    "save": _draw_save,
    "paw": _draw_paw,
    "cat": _draw_cat,
    "app": _draw_app,
}
