import loeric.loeric_utils as lu
import mido
import time
import argparse
import numpy as np
from scipy.fftpack import fft, dct, idct
import matplotlib.pyplot as plt


def main() -> None:
    """
    Monitor the velocity of MIDI events on the specified port and send it as a control signal on the given output port.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="the input MIDI port.", type=int)
    args = parser.parse_args()

    inport, outport = lu.get_ports(
        input_number=args.input, output_number=None, list_ports=False
    )
    if inport is None:
        return

    onsets = []
    pitches = []
    velocities = []
    doing_stuff = False
    with mido.open_input(inport) as port:
        for msg in port:

            if msg.type != "note_on" or doing_stuff:
                continue

            t = time.time()
            print(msg, t)
            onsets.append(t)
            pitches.append(msg.note)
            velocities.append(msg.velocity)

            if max(onsets) - min(onsets) > 20:

                doing_stuff = True
                times = np.array(onsets)
                times -= min(times)
                print(times)

                """
                X = times[:-1]
                Y = np.diff(times)
                """
                X = times
                Y = np.array(velocities)
                Y = np.diff(Y, prepend=velocities[0])

                x = np.linspace(0, max(X), 1000)
                y = np.interp(x, X, Y)

                # 2. Compute FFT
                fft_result = np.fft.fft(y)
                frequencies = np.fft.fftfreq(len(x), d=(x[1] - x[0]))  # frequency bins

                # 3. Get magnitude spectrum and ignore DC (index 0)
                magnitude = np.abs(fft_result)
                magnitude[0] = 0  # ignore DC

                # 4. Find dominant frequency
                dominant_index = np.argmax(magnitude)
                dominant_frequency = abs(frequencies[dominant_index])
                estimated_period = 1 / dominant_frequency

                # Output estimated period
                print(f"Estimated period (from FFT): {estimated_period:.4f}")

                # 5. Plot signal and estimated period grid
                plt.figure(figsize=(10, 4))
                plt.plot(x, y, label="Original Signal")
                # plt.step(times, pitches, label="Notes")
                plt.title("Signal with Estimated Period Grid (from FFT)")
                plt.xlabel("x")
                plt.ylabel("Amplitude")
                plt.grid(True)

                # Add vertical lines at multiples of the estimated period
                period_positions = np.arange(x[0], x[-1], estimated_period)
                for px in period_positions:
                    plt.axvline(
                        px,
                        color="red",
                        linestyle="--",
                        alpha=0.5,
                        label="Estimated Period" if px == period_positions[0] else "",
                    )

                plt.legend()
                plt.tight_layout()
                plt.show()
                return


main()
