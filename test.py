import mido
import tune as tu
import contour as cnt

# create a new tune
tune = tu.Tune("test.mid")

# create a contour
contour = cnt.RandomContour()

# this should trigger an UncomputedContourError
# contour.next()

contour.calculate(tune)

# print messages
for msg in tune:
    print(msg)
    # follow contour
    if tu.is_note_on(msg):
        print(contour.next())

# this should trigger an InvalidIndexError
contour.next()