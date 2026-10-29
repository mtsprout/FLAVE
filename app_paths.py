# app_paths.py
# Where FLAVE reads and writes its own files. From source (python
# project_manager.py) everything stays next to the .py files, as always. In a
# packaged macOS app (PyInstaller sets sys.frozen) the code lives read-only
# inside the .app, so settings and model caches go to
# ~/Library/Application Support/FLAVE for Mac, and read-only resources
# (icon, build number) come from the bundle. FLAVE_DATA_DIR overrides the
# data folder (tests). ASCII only.

import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SUPPORT_NAME = "FLAVE for Mac"


def bundled():
    return bool(getattr(sys, "frozen", False))


def data_dir():
    # Folder for globalsettings.db and the models cache (created if missing)
    d = os.environ.get("FLAVE_DATA_DIR")
    if not d and bundled() and sys.platform == "darwin":
        d = os.path.join(os.path.expanduser("~/Library/Application Support"),
                         SUPPORT_NAME)
    d = d or APP_DIR
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def resource(*parts):
    # A read-only file that ships with the app (assets/FLAVE.png, counter.txt)
    base = getattr(sys, "_MEIPASS", None) or APP_DIR
    return os.path.join(base, *parts)


def ensure_tool_path():
    # An app started from Finder / the Dock does not get the shell's PATH,
    # so ffmpeg and ffprobe (Homebrew) would not be found
    if sys.platform != "darwin":
        return
    extra = ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"]
    cur = os.environ.get("PATH", "").split(os.pathsep)
    add = [p for p in extra if p not in cur and os.path.isdir(p)]
    if add:
        os.environ["PATH"] = os.pathsep.join(cur + add)


def set_mac_app_name(name):
    # The application menu and Dock title come from the bundle's Info.plist;
    # a plain script has none ("Python"), so set the name at run time
    # (needs pyobjc-framework-Cocoa; harmless without it)
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle
        info = (NSBundle.mainBundle().localizedInfoDictionary()
                or NSBundle.mainBundle().infoDictionary())
        if info is not None:
            info["CFBundleName"] = name
    except Exception:
        pass
