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

pyinstaller --collect-submodules=src --add-data="static:./static" -n=loeric --icon=loeric-icon.png --hidden-import=mido.backends.rtmidi -w src/loeric/server/__main__.py
