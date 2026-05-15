"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
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
