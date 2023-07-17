import mido
import math
import time

# generate a fake control signal
port_num = 0

with mido.open_output(mido.get_output_names()[port_num]) as out:
    while True:
        # send a message every 0.25 seconds
        value = round(127 * (math.sin(time.time()) + 1) / 2)
        out.send(
            mido.Message(
                "control_change",
                channel=0,
                control=42,
                value=value,
            )
        )
        time.sleep(0.25)
