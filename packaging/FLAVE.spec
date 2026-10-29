# packaging/FLAVE.spec  --  PyInstaller recipe for "FLAVE for Mac.app"
# Build with packaging/build_app.sh (run from anywhere). ASCII only.

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))
sys.path.insert(0, ROOT)
from version import APP_NAME, VERSION

try:
    with open(os.path.join(ROOT, "counter.txt")) as f:
        BUILD = str(int(f.read().strip()))
except (OSError, ValueError):
    BUILD = "0"
NUMERIC_VERSION = VERSION.split("-")[0]       # CFBundleShortVersionString: 0.1.0

a = Analysis(
    [os.path.join(ROOT, "project_manager.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "assets", "FLAVE.png"), "assets"),
           (os.path.join(ROOT, "counter.txt"), ".")],
    hiddenimports=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP_NAME,
          console=False, argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)
app = BUNDLE(
    coll,
    name=APP_NAME + ".app",
    icon=os.path.join(ROOT, "assets", "FLAVE.icns"),
    bundle_identifier="io.github.mtsprout.flave-mac",
    version=NUMERIC_VERSION,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": NUMERIC_VERSION,
        "CFBundleVersion": BUILD,
        "LSApplicationCategoryType": "public.app-category.video",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright":
            "FLAVE (FilmLadd Video Editor). Free to use, modify and share "
            "with attribution; may not be sold.",
    },
)
