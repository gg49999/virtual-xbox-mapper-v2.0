# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build spec. Run from the repository root:
#     pyinstaller installer/VirtualXboxMapper.spec --distpath build/dist --workpath build/work
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# Single source of truth for the version: src/app_info.py
import re  # noqa: E402
with open(os.path.join(ROOT, "src", "app_info.py"), encoding="utf-8") as _f:
    APP_VERSION = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', _f.read()).group(1)
_parts = [int(x) for x in (APP_VERSION.split(".") + ["0", "0", "0"])[:4]]
with open(os.path.join(SPECPATH, "version_info.txt"), encoding="utf-8") as _f:
    _template = _f.read()
_version_file = os.path.join(workpath, "version_info.generated.txt")
os.makedirs(workpath, exist_ok=True)
with open(_version_file, "w", encoding="utf-8") as _f:
    _f.write(_template.replace("{VERSION_TUPLE}", "(%d, %d, %d, %d)" % tuple(_parts))
                      .replace("{VERSION}", APP_VERSION))

datas = [
    (os.path.join(ROOT, "config"), "config"),
    (os.path.join(ROOT, "profiles"), "profiles"),
]
# assets: everything except the source 3D model (the app only needs the renders)
for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "assets")):
    rel = os.path.relpath(dirpath, ROOT)
    for fn in files:
        if not fn.lower().endswith(".glb"):
            datas.append((os.path.join(dirpath, fn), rel))
binaries = []
hiddenimports = ["pynput.keyboard._win32", "pynput.mouse._win32"]
for pkg in ("vgamepad",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(ROOT, "src", "main.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PyQt6.QtWebEngineCore", "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.Qt3DCore",
              "PyQt6.QtMultimedia", "PyQt6.QtPdf", "PyQt6.QtBluetooth"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = os.path.join(ROOT, "assets", "icon.ico")
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VirtualXboxMapper",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon if os.path.exists(icon) else None,
    version=_version_file,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VirtualXboxMapper")
