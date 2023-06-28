import mido
import numpy as np
import matplotlib.pyplot as plt

import loeric.tune as tu
import loeric.contour as cnt


def main():
    # create a new tune
    tune = tu.Tune("test.mid")

    # create a contour
    # contour = cnt.RandomContour()
    contour = cnt.IntensityContour()

    # this should trigger an UncomputedContourError
    # contour.next()

    contour.calculate(tune, random_weight=0.5)
    """
    min_contour = np.ones(contour._contour.shape)
    max_contour = np.zeros(contour._contour.shape)
    avg_contour = np.zeros(contour._contour.shape)
    for i in range(10):
        contour.calculate(tune, random_weight=0.5)
        min_contour = np.minimum(min_contour, contour._contour)
        max_contour = np.maximum(max_contour, contour._contour)
        avg_contour += contour._contour
    plt.plot(range(len(contour._contour)), min_contour)
    plt.plot(range(len(contour._contour)), max_contour)
    plt.plot(range(len(contour._contour)), avg_contour / 10)
    """
    plt.plot(contour._contour)
    plt.show()

    # print messages
    for msg in tune:
        print(msg)
        # follow contour
        if tu.is_note_on(msg):
            print(contour.next())

    # this should trigger an InvalidIndexError
    contour.next()


if __name__ == "__main__":
    main()
