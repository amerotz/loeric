import faulthandler
import sys
from pathlib import Path

from loeric.server.server import start_server


log_path = Path.home() / "loeric_error.log"

if sys.stderr is None:
    sys.stderr = open(log_path, "a")

if sys.stdout is None:
    sys.stdout = open(log_path, "a")


faulthandler.enable()

start_server()
