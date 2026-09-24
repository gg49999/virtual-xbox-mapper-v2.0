"""Regenerate assets/icon.ico (used for the .exe and the installer) from
the same painted icon the app uses at runtime.

    python tools/make_icon.py
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    from ui import icons
    icon = icons.app_icon()
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    images = []
    for size in sizes:
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        icon.pixmap(size, size).toImage().save(buf, "PNG")
        images.append((size, bytes(data)))
    # ICO container with PNG-compressed entries (supported since Windows Vista).
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    out = os.path.join(ROOT, "assets", "icon.ico")
    with open(out, "wb") as f:
        f.write(header + entries + blobs)
    print(f"Wrote {out}")
    del app


if __name__ == "__main__":
    main()
