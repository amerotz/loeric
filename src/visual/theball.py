import mido
import numpy as np
import processing_py as pr
import time

app = pr.App(600, 400)  # create window: width, height

value = 0
min_value = 127
max_value = 0


def update_control(msg):
    global value, min_value, max_value
    if msg.is_cc(46):
        value = msg.value
        min_value = min(value, min_value)
        max_value = max(value, max_value)
        value = (value - min_value) / (max_value - min_value)


inport = mido.get_input_names()[2]
midi_in = mido.open_input(inport)

midi_in.callback = update_control

old_x = app.width / 2
old_y = app.height / 2
t = 0
while True:
    # app.background(0, 0, 0)  # set background:  red, green, blue
    app.fill(255, 255, 0)  # set color for objects: red, green, blue
    app.filter("BLUR", 0.8)
    x = app.width / 2 + 10 * np.sin(t / 5)
    x = old_x * 0.5 + x * 0.5
    old_x = x

    y = app.height - value * float(app.height)
    y = old_y * 0.5 + y * 0.5
    old_y = y

    app.ellipse(x, y, 50, 50)  # draw a circle: center_x, center_y, size_x, size_y
    app.redraw()  # refresh the window
    t += 1
    time.sleep(1 / 60)
