if [ "$VIRTUAL_ENV" != "" ];
then
	deactivate
fi
python3 -m build
source ~/loeric-env/bin/activate
pip install dist/loeric-1.0.0-py2.py3-none-any.whl --force-reinstall
