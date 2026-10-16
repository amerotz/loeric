#!/bin/bash

echo "Building LOERIC CLI"
python -m build --no-isolation --wheel
pip install dist/loeric-3.0.0-py2.py3-none-any.whl --force-reinstall

# pyinstaller
echo "Building LOERIC executable with PyInstaller..."
PYINSTALLER_CMD="pyinstaller \
  --onefile \
  --collect-submodules=src \
  --add-data static:static \
  --add-data src/loeric/config/performance:loeric/config/performance \
  --hidden-import mido.backends.rtmidi \
  -n loeric \
  --icon loeric-icon.png \
  -w src/loeric/server/__main__.py"

eval $PYINSTALLER_CMD

echo "Build finished."
