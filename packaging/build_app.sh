#!/bin/zsh
# Builds dist/"FLAVE for Mac.app" (needs the project venv: PySide6, numpy,
# pillow, pyinstaller) and signs it ad hoc so it runs on this Mac. A build
# for other Macs needs a Developer ID signature and notarization (see
# packaging/README.md).
set -e
cd "$(dirname "$0")/.."
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"
"$PY" assets/make_icon.py > /dev/null          # icon files up to date
"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build \
      packaging/FLAVE.spec
codesign --force --deep --sign - "dist/FLAVE for Mac.app"
codesign --verify --deep --strict "dist/FLAVE for Mac.app" && echo "signature ok (ad hoc)"
echo "built: dist/FLAVE for Mac.app"
