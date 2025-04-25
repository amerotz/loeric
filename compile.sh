cd client
npm run build
cd ..
rm -r static/site
cp -r client/build static/site

python -m build --no-isolation --wheel
pip install dist/loeric-1.0.0-py2.py3-none-any.whl --force-reinstall
