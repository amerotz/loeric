import sys
from pathlib import Path


if getattr(sys, "frozen", False):
    log_file = Path.home() / "loeric.log"

    if sys.stdout is None:
        sys.stdout = open(log_file, "a")

    if sys.stderr is None:
        sys.stderr = open(log_file, "a")


import faulthandler

from loeric.server.server import start_server


faulthandler.enable()
start_server()
