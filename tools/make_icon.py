"""生成 assets/lite_browser.ico（供 exe 与快捷方式使用）。

用法：
    python tools/make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from litebrowser import icons  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(name: str, size: int) -> bytes:
    pixmap = icons.pixmap(name, size)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(entries: list[tuple[int, bytes]], target: Path) -> None:
    """按 ICO 格式写入多尺寸 PNG 图标。"""
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = b""
    payload = b""
    for size, blob in entries:
        dimension = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(blob), offset
        )
        offset += len(blob)
        payload += blob
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(header + directory + payload)


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841

    ico_path = ROOT / "assets" / "lite_browser.ico"
    write_ico([(size, png_bytes("app", size)) for size in SIZES], ico_path)
    print(f"已生成 {ico_path}  ({ico_path.stat().st_size} 字节)")

    preview_dir = ROOT / "assets"
    for size in (32, 256):
        (preview_dir / f"lite_browser_{size}.png").write_bytes(png_bytes("app", size))
    print(f"已生成预览图：{preview_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
