"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import threading
import time

import mido
import numpy as np


inport = mido.get_input_names()[2]
outport = mido.get_output_names()[0]

tempo = 170
last_time = None
deltas = []
max_len = 10
sync_duration = 2


def send_songpos():
    with mido.open_output(outport) as out:
        i = 0
        while True:
            msg = mido.Message("songpos", pos=i)
            i += 1
            out.send(msg)
            print(msg)
            time.sleep(sync_duration * 60 / tempo)


pos_thread = threading.Thread(target=send_songpos)
id = int(time.time())
with mido.open_output(f"HUMAN SYNC #{id}#", virtual=True) as out:
    with mido.open_input(inport) as in_:
        i = 0
        while True:
            msg = in_.receive()
            now = time.time()
            if msg.control != 66:
                continue
            if msg.value == 127:
                continue

            """
            if not pos_thread.is_alive():
                pos_thread.start()
            """

            if last_time is None:
                last_time = now
            else:
                deltas.append(now - last_time)
                if len(deltas) > max_len:
                    deltas = deltas[1:]
                tempo = 60 / (np.mean(deltas) / sync_duration)
                last_time = now
                print(tempo)

            msg = mido.Message("songpos", pos=i)
            out.send(msg)
            i += 1
