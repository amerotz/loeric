#!/bin/bash

SOUNDFONT_URL="https://keymusician01.s3.amazonaws.com/FluidR3_GM.zip"
ACCORDION_SOUNDFONT_URL="http://sonimusicae.free.fr/Banques/SoniMusicae-Diato-sf2.zip"
TARGET_DIR="static/sound"
TEMP_ZIP_FILE="static/sound/tmp.zip"

if [ ! -f "$TARGET_DIR/FluidR3_GM.sf2" ]; then
  echo "SoundFont not found. Downloading and unzipping..."
  mkdir -p "$TARGET_DIR"
  curl -L "$SOUNDFONT_URL" -o "$TEMP_ZIP_FILE"
  unzip "$TEMP_ZIP_FILE" -d "$TARGET_DIR"
  rm "$TEMP_ZIP_FILE"
  echo "SoundFont downloaded and unzipped successfully."
fi

if [ ! -f "$TARGET_DIR/Diato.sf2" ]; then
  echo "Accordion soundfont not found. Downloading and unzipping..."
  mkdir -p "$TARGET_DIR"
  curl -L "$ACCORDION_SOUNDFONT_URL" -o "$TEMP_ZIP_FILE"
  unzip "$TEMP_ZIP_FILE" -d "$TARGET_DIR"
  sfarkxtc "$TARGET_DIR/Sonimusicae-diato-sf2/Diato.sfArk"
  mv "$TARGET_DIR/Sonimusicae-diato-sf2/Diato.sf2" "$TARGET_DIR"
  rm "$TEMP_ZIP_FILE"
  rm "$TARGET_DIR/Sonimusicae-diato-sf2" -fr
  echo "Accordion soundfont downloaded and unzipped successfully."
fi

mkdir client/build
mkdir static/midi
mkdir static/site

echo "Building LOERIC WebUI"
cd client
npm run build
cd ..
rm -r static/site
cp -r client/build static/site

echo "Building LOERIC CLI"
python -m build --no-isolation --wheel
pip install dist/loeric-2.0.0-py2.py3-none-any.whl --force-reinstall

# detect os
OS="$(uname -s)"
case "$OS" in
  Linux*)   PLATFORM="linux"; ADD_DATA_SEP=":"; EXT="";;
  Darwin*)  PLATFORM="macos"; ADD_DATA_SEP=":"; EXT="";;
  MINGW*|MSYS*|CYGWIN*|Windows*) PLATFORM="windows"; ADD_DATA_SEP=";"; EXT=".exe";;
  *) echo "Unsupported OS: $OS"; exit 1;;
esac

echo "Detected platform: $PLATFORM"

# pyinstaller
echo "Building LOERIC executable with PyInstaller..."
PYINSTALLER_CMD="pyinstaller \
  --collect-submodules=src \
  --add-data static${ADD_DATA_SEP}static \
  --add-data src/loeric/loeric_config/performance${ADD_DATA_SEP}loeric/loeric_config/performance \
  --add-data src/loeric/loeric_config/session${ADD_DATA_SEP}loeric/loeric_config/session \
  --add-data src/loeric/loeric_config/shell${ADD_DATA_SEP}loeric/loeric_config/shell \
  --hidden-import mido.backends.rtmidi \
  -n loeric${EXT} \
  --icon loeric-icon.png \
  -w src/loeric/server/__main__.py"

eval $PYINSTALLER_CMD

echo "Build finished: dist/loeric/loeric${EXT}"
