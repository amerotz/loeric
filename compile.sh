cd client
npm run build
cd ..
rm -r static/site
cp -r client/build static/site

python -m build --no-isolation --wheel
pip install dist/loeric-1.0.0-py2.py3-none-any.whl --force-reinstall

pyinstaller --collect-submodules=src --add-data="static:./static" -n=loeric --icon=loeric-icon.png --hidden-import=mido.backends.rtmidi -w src/loeric/server/__main__.py