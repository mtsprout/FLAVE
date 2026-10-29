# Packaging FLAVE for Mac

`packaging/build_app.sh` builds `dist/FLAVE for Mac.app` (about 155 MB,
PyInstaller, signed ad hoc). Run it from the project folder with the venv
set up (`pip install PySide6 numpy pillow pyinstaller pyobjc-framework-Cocoa`).

What the app does differently from `python project_manager.py`
- Settings (`globalsettings.db`) and the Whisper model cache live in
  `~/Library/Application Support/FLAVE for Mac/` (code inside a signed app is
  read-only). From source nothing moves: they stay next to the .py files.
  `FLAVE_DATA_DIR` overrides the folder.
- `/opt/homebrew/bin` and `/usr/local/bin` are added to PATH so ffmpeg and
  ffprobe are found when the app is started from Finder.
- ffmpeg / ffprobe are not inside the app: install them (`brew install ffmpeg`).
  Bundling a build is possible later (licence and size to decide).

Running the ad hoc build on another Mac
- Gatekeeper blocks it ("cannot be opened"): right-click the app, Open. Or
  `xattr -dr com.apple.quarantine "FLAVE for Mac.app"`.

A build others can double-click needs (not done, needs an Apple Developer
ID, about 99 USD per year)
1. Sign with a Developer ID: `codesign --force --deep --options runtime
   --timestamp --sign "Developer ID Application: NAME (TEAMID)" "FLAVE for Mac.app"`
2. Zip it and notarize: `xcrun notarytool submit FLAVE.zip --keychain-profile
   PROFILE --wait`, then `xcrun stapler staple "FLAVE for Mac.app"`.
3. Ship it in a .dmg.
Related files: `FLAVE.spec` (bundle metadata: name, identifier
io.github.mtsprout.flave-mac, version, icon), `assets/make_icon.py`.
