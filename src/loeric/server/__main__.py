import faulthandler

from loeric.server.server import start_server


faulthandler.enable()

start_server()
