import mido
import threading
import numpy as np
import time

inport = mido.get_input_names()[2]
outport = mido.get_output_names()[0]

tempo = 170
last_time = None
deltas = []
max_len = 10
sync_duration = 2


def send_songpos():
    global tempo
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

            if last_time == None:
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
