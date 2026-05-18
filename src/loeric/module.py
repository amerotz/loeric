# This file is part of LOERIC.
#
# LOERIC is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LOERIC is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LOERIC. If not, see <https://www.gnu.org/licenses/>.

import copy
import logging
import random
from collections import defaultdict

import nanoid as nid
import numpy as np

import loeric.element as le
import loeric.utils as lu

logger = logging.getLogger(__name__)


class LOERICModule:
    """A performance module implementing a series of performance rules."""

    def __init__(self, bypass=False):

        self._signature = nid.generate()
        self._name = "module"
        self._lookahead_size = 0
        self._lookback_size = 0
        self._window_size = 0
        self._bypass = bypass

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Process an element (only if not seen by this module already).

        :param element: the element to process.
        :param contour_values: the contour values to use.
        :param window: an optional window of events in the future.
        """
        return [element]

    def __call__(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        # if I saw this already, don't run again
        if element.has_signature(self._signature) or self._bypass:
            return [element]
        else:
            # process it
            out = self.process(element, contour_values, window=window)

            # sign it
            for o in out:
                o.add_signature(self._signature)
                o.copy_signatures(element)

            return out

    @property
    def name(self):
        return self._name + "::" + self._signature

    @property
    def lookahead_size(self):
        return self._lookahead_size

    @property
    def window_size(self):
        return self._window_size

    @staticmethod
    def create_module(module: str, **kwargs):

        module_name = module.split("#")[0]
        if module_name == "legato":
            return LegatoModule(**kwargs)
        elif module_name == "swing":
            return SwingModule(**kwargs)
        elif module_name == "dynamics":
            return DynamicsModule(**kwargs)
        elif module_name == "transpose":
            return TransposeModule(**kwargs)
        elif module_name == "timing":
            return TimingModule(**kwargs)
        elif module_name == "delay_buffer":
            return DelayBufferModule(**kwargs)
        elif module_name == "history_buffer":
            return HistoryBufferModule(**kwargs)
        elif module_name == "ornament":
            return OrnamentModule(**kwargs)
        elif module_name == "drones":
            return DroneModule(**kwargs)
        elif module_name == "harmony":
            return HarmonyModule(**kwargs)
        elif module_name == "logger":
            return LoggerModule(**kwargs)
        else:
            raise ValueError(f"Invalid module name '{module_name}'.")


class TransposeModule(LOERICModule):
    def __init__(self, steps: float, **kwargs):
        super().__init__(**kwargs)

        self._steps = steps
        self._name = "transpose"

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Transpose notes.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        if (
            isinstance(element, le.Note)
            or isinstance(element, le.Chord)
            or isinstance(element, le.KeySignature)
        ):
            element.transpose(self._steps)
        return [element]


class HarmonyModule(LOERICModule):
    def __init__(
        self, chord_score: list[float], chords_per_bar: float, weights: dict, **kwargs
    ):
        super().__init__(**kwargs)

        self._name = "harmony"
        self._time_signature = None
        self._key_signature = None
        self._last_computation_time = -np.inf

        self._chords_per_bar = chords_per_bar
        self._chord_score = np.array(chord_score)
        self._weights = weights
        for w in self._weights:
            self._weights[w] = np.array(self._weights[w])

        # 0 = major
        # 1 = minor
        # 2 = diminished
        # 3 = augmented
        # ####################### C C#  D Eb  E  F F#  G G#  A A#  B
        self._chord_qualities = np.array([0, 2, 1, 2, 1, 0, 2, 0, 2, 1, 0, 2])
        self._last_forced_chord = None

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Transpose notes.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        if isinstance(element, le.TimeSignature):
            self._time_signature = copy.copy(element)
            self._window_size = (
                self._time_signature.eighths_per_bar / self._chords_per_bar
            )
        elif isinstance(element, le.KeySignature):
            self._key_signature = copy.copy(element)
        elif isinstance(element, le.Chord):
            self._last_forced_chord = copy.copy(element)
            # filter out the null chord
            if not element.is_valid:
                element = le.NullEvent(time=element.time.eighth_duration)

        # only compute when reaching the interval
        should_compute = (
            element.time % self._window_size == 0
            and element.is_performable
            and (
                self._last_forced_chord is None or not self._last_forced_chord.is_valid
            )
        )
        if should_compute:
            self._last_computation_time = element.time.eighth_duration
            self._last_forced_chord = None

            # filter out elements outside required time frame
            window = [
                el
                for el in window
                if el.is_performable
                and el.time >= element.time
                and el.time < element.time + self._window_size
            ]
            chord = self._calculate_chord(window)
            chord.time = element.time.eighth_duration

            return [chord, element]

        return [element]

    @property
    def _allowed_chords(self):
        if self._key_signature is None or self._key_signature.mode not in self._weights:
            return self._weights["default"]
        else:
            return self._weights[self._key_signature.mode]

    def _calculate_chord(self, window):

        pitches = np.array([el.pitch for el in window])
        bar_notes = (pitches % 12).astype(int)
        bar_lengths = np.array([el.duration.eighth_duration for el in window])

        # init counts
        chords = np.zeros(12)
        note_count = np.zeros(12)

        # add chord score for each note
        for i, n in enumerate(bar_notes):
            chords += np.roll(self._chord_score, n) * bar_lengths[i]
            note_count[n % 12] += 1

        # filter out chords that are not allowed
        chords_filtered = np.multiply(
            chords,
            np.roll(self._allowed_chords, self._key_signature.root),
        )

        # choose the chord with the highest score
        root = np.random.choice(
            np.argwhere(chords_filtered == chords_filtered.max())[0]
        )

        # check if the selected chord should be major according to the mode
        chord_quality = np.roll(self._chord_qualities, self._key_signature.major_root)[
            root
        ]

        harmony_value = root

        # check if the note score suggests major chord
        if note_count[(root + 4) % 12] > note_count[(root + 3) % 12]:
            chord_quality = 0
        # check if the note score suggests minor chord
        elif note_count[(root + 3) % 12] > note_count[(root + 4) % 12]:
            chord_quality = 1

        # check if the note score suggests diminished chord
        if (
            note_count[(root + 6) % 12] > 2 * note_count[(root + 7) % 12]
            and chord_quality == 1
        ):
            chord_quality = 2

        # check if the note score suggests augmented chord
        elif (
            note_count[(root + 8) % 12] > 2 * note_count[(root + 7) % 12]
            and chord_quality == 0
        ):
            chord_quality = 3

        # check if the note score suggests minor seventh chord
        elif (
            note_count[(root + 10) % 12] > 2 * np.mean(note_count)
            and note_count[(root + 10) % 12] > note_count[(root + 11) % 12]
        ):
            chord_quality += 4

        # check if the note score suggests major seventh chord
        elif (
            note_count[(root + 11) % 12] > 2 * np.mean(note_count)
            and note_count[(root + 11) % 12] > note_count[(root + 10) % 12]
        ):
            chord_quality += 6

        harmony_value = root + 12 * chord_quality
        return le.Chord.from_harmony(harmony_value)


class DynamicsModule(LOERICModule):
    def __init__(self, bind: str, pattern: str, **kwargs):
        super().__init__(**kwargs)

        self._contour = bind
        self._pattern = pattern
        self._name = "dynamics"

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Apply dynamics.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        if isinstance(element, le.Note):
            element.velocity = contour_values[self._contour]
            if self._pattern is not None:
                element.velocity *= contour_values[self._pattern]
        return [element]


class OrnamentModule(LOERICModule):
    class OrnamentConfig:
        def __init__(self, name: str, config: dict):

            self.name = name

            for key in config:
                setattr(self, key, config[key])

            if "probability_bind" in config:
                self.probability_contour = config["bind"]
            else:
                self.probability_contour = None

            if "bind" in config:
                self.bind = config["bind"]
            else:
                self.bind = None

        def __repr__(self):
            return f"(Ornament {self.name} slide={self.slide} thr={self.threshold} p={self.probability})"

    def __init__(self, bind: str, data: dict, whitelist: list[str], **kwargs):
        super().__init__(**kwargs)

        self._name = "ornament"
        self._contour = bind
        self._ornaments = [self.OrnamentConfig(o, data[o]) for o in data]
        self._window_size = 0

        if len(self._ornaments) != 0:
            self._window_size = max([o.length for o in self._ornaments])

        if whitelist is None:
            self._whitelist = [o.name for o in self._ornaments]
        else:
            self._whitelist = whitelist

        self._time_signature = None
        self._key_signature = None
        self._accidentals = defaultdict(int)
        self._eighths_to_skip = 0

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Apply ornament.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        if isinstance(element, le.TimeSignature):
            self._time_signature = copy.copy(element)
        elif isinstance(element, le.KeySignature):
            self._key_signature = copy.copy(element)

        # create ornaments
        elif isinstance(element, le.Note):
            # check if accidental
            deg, acc = self._key_signature.degree_from_root(element.pitch)
            if acc != 0 or deg in self._accidentals:
                self._accidentals[deg] = acc

            # skip notes to allow for the ornament to be executed
            if self._eighths_to_skip >= element.duration:
                self._eighths_to_skip -= element.duration.eighth_duration
                return [le.NullEvent(time=element.duration.eighth_duration)]

            if self._can_generate_ornament(contour_values[self._contour]):
                # choose which ornament
                ornament_type = self._choose_ornament(element, contour_values, window)

                # generate it
                if ornament_type is not None:
                    notes = self._generate_ornament(element, ornament_type)

                    for a in list(self._accidentals.keys()):
                        notes.insert(
                            0,
                            le.Accidental(
                                pitch=a,
                                alteration=self._accidentals[a],
                                time=element.time.eighth_duration,
                            ),
                        )
                        # delete it if zero
                        # avoid sending every accidental every time
                        if self._accidentals[a] == 0:
                            del self._accidentals[a]
                    return notes

        return [element]

    def _can_generate_ornament(self, prob) -> bool:
        """:return: whether or not to generate an ornament given the current ornament contour."""
        return random.choices([True, False], weights=[prob, 1 - prob], k=1)[0]

    def _choose_ornament(self, element, contour_values, window) -> str:
        """Evaluate the ornament specific rules and chooose how the note will be ornamented.

        :return: the chosen ornament type.
        """
        options = []
        options_prob = []

        is_beat = (
            element.time
            % (self._time_signature.eighths_per_bar / self._time_signature.beat_count)
            == 0
        )

        first_pitch = element.pitch

        window = [w for w in window if isinstance(w, le.Note)]
        # for each ornament
        for ornament in self._ornaments:
            # only check if whitelist
            if ornament.name not in self._whitelist:
                logger.debug(
                    f"Skipped ornament {ornament.name} because not whitelisted."
                )
                continue
            prob = ornament.probability

            # check if probability can be updated via contour
            if ornament.probability_contour in contour_values:
                prob = contour_values[ornament.probability_contour]

            # skip if 0
            if prob == 0:
                logger.debug(
                    f"Skipped ornament {ornament.name} because because probability is 0."
                )
                continue

            # check if this ornament has a dedicated contour
            if ornament.bind in contour_values:
                contour_value = contour_values[ornament.bind]
            # else use the default
            else:
                contour_value = contour_values[self._contour]

            # skip if below threshold
            if contour_value <= ornament.threshold:
                logger.debug(
                    f"Skipped ornament {ornament.name} because {self._contour} contour value is below threshold {ornament.threshold}."
                )
                continue

            # check elegibility for every listed case
            for c in ornament.cases:
                elegible = True
                # on a beat
                if c == "beat":
                    elegible = elegible and is_beat
                elif c == "not beat":
                    elegible = elegible and not is_beat
                else:
                    case_notes = c

                    window_i = 0
                    for note in case_notes:
                        # check duration
                        if window_i >= len(window):
                            message_length = 0
                            pitch_difference = 100
                            logger.debug(
                                f"Skipped ornament {o.name} because window is too small."
                            )
                            break

                        # target pitch
                        pitch = note[0]

                        # target duration
                        duration = note[1]

                        if ornament.diatonic:
                            # pitch diff in diatonic steps
                            pitch_difference, is_chromatic = (
                                self._key_signature.degree_difference(
                                    first_pitch, window[window_i].pitch
                                )
                            )
                            if is_chromatic:
                                deg, acc = self._key_signature.degree_from_root(
                                    window[window_i].pitch
                                )
                                self._accidentals[deg] = acc
                            # elegible = elegible and not is_chromatic
                        else:
                            # pitch diff in chromatic steps
                            pitch_difference = window[window_i].pitch - first_pitch

                        message_length = window[window_i].duration

                        window_i += 1

                        # check
                        if pitch != "*":
                            elegible = elegible and pitch_difference == pitch

                            if not elegible:
                                logger.debug(
                                    f"Skipped ornament {ornament.name} because pitch difference is {pitch_difference}, not {pitch}."
                                )
                                break

                        elegible = elegible and message_length - duration == 0
                        if not elegible:
                            logger.debug(
                                f"Skipped ornament {ornament.name} because duration is {message_length}, not {duration}."
                            )
                            break

                # if found a case, move to next ornament
                if elegible:
                    options.append(ornament)
                    options_prob.append(prob)
                    break
                # else check another case

        prob_sum = sum(options_prob)
        if prob_sum == 0:
            return None
        elif prob_sum < 1:
            options.append(None)
            options_prob.append(1 - prob_sum)
        else:
            options_prob = np.array(options_prob).astype(float)
            options_prob /= options_prob.sum()

        # print(options)
        return np.random.choice(options, p=options_prob)

    def _generate_ornament(self, element, ornament) -> list[le.LOERICElement]:
        """Generate the sequence of notes corresponding to the chosen ornament.

        :param message: the midi message to ornament.
        :param ornament_type: the type of ornament to generate.
        :return: the list of midi events corresponding to the chosen ornament.
        """
        logger.info(f"{ornament.name}")

        # sample pitches
        p_std = ornament.pitches_std
        if p_std is None:
            p_std = np.zeros_like(ornament.pitches_mean)

        pitches = np.random.normal(
            loc=ornament.pitches_mean, scale=p_std, size=len(ornament.pitches_mean)
        )

        # sample velocities
        v_std = ornament.velocities_std
        if v_std is None:
            v_std = np.zeros_like(ornament.velocities_mean)

        velocities = np.random.normal(
            loc=ornament.velocities_mean,
            scale=v_std,
            size=len(ornament.velocities_mean),
        )

        # sample durations
        d_std = ornament.durations_std
        if d_std is None:
            d_std = np.zeros_like(ornament.durations_mean)

        durations = np.random.normal(
            loc=ornament.durations_mean, scale=d_std, size=len(ornament.durations_mean)
        )
        # normalize durations
        durations /= durations.sum()
        durations *= ornament.length

        ornaments = []
        offset = element.time
        for i, (p, v, d) in enumerate(zip(pitches, velocities, durations)):
            if ornament.diatonic:
                new_note = self._key_signature.degree_add(
                    element.pitch, np.round(p).astype(int)
                )

                # change accidentals
                deg, acc = self._key_signature.degree_from_root(new_note)
                if acc == 0:
                    new_note += self._accidentals[deg]

                # microtonal as fractional part
                new_note += p - np.round(p)
            else:
                new_note = element.pitch + p

            # if not sliding, quantize
            # slides can be microtonal
            if not ornament.slide:
                new_note = int(new_note)

            # limit velocity in allowed range
            if v != 0:
                vel = min(1, max(0, element.velocity * v))
            else:
                vel = 0

            orn_note = le.Note(
                pitch=new_note,
                eighth_duration=d,
                velocity=vel,
                time=offset.eighth_duration,
                slide=ornament.slide and len(ornaments) == 0,
            )
            if ornament.slide and len(ornaments) != 0:
                ornaments[-1].add_slide_target_pitch(orn_note)

            else:
                ornaments.append(orn_note)

            offset += orn_note.duration

        self._eighths_to_skip = -element.duration + ornament.length

        ornaments[-1].duration = element.time + ornament.length - ornaments[-1].time
        if self._eighths_to_skip < 0:
            ornaments[-1].duration += abs(self._eighths_to_skip.eighth_duration)

        if element.has_metadata:
            ornaments.extend(element.metadata)

        return ornaments


class DroneModule(LOERICModule):
    class DroneConfig:
        def __init__(self, name, config):

            self._name = name

            for key in config:
                setattr(self, key, config[key])

            if "probability_scale" not in config:
                self.probability_scale = False

            if "delay_bind" not in config:
                self.delay_bind = None

            if "velocity_bind" not in config:
                self.velocity_bind = None

            self.last_computed_time = -np.inf
            self._is_running = False

        def is_running(self):
            return self._is_running

        def activate(self):
            self._is_running = True

        def __repr__(self):
            return f"(Drone {self.type})"

    def __init__(self, data: dict, **kwargs):
        super().__init__(**kwargs)

        self._name = "drones"
        self._drone_sets = [self.DroneConfig(d, data[d]) for d in data]
        self._last_pitch = None
        self._last_velocity = None
        self._time_signature = None
        self._key_signature = None
        self._current_chord = None
        self._all_drones = np.array(
            [n for d in self._drone_sets for n in d.notes]
        ).flatten()

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Apply drones.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        if isinstance(element, le.TimeSignature):
            self._time_signature = copy.copy(element)
        elif isinstance(element, le.KeySignature):
            self._key_signature = copy.copy(element)
        elif isinstance(element, le.Chord):
            self._current_chord = copy.copy(element)
        elif isinstance(element, le.Note):
            self._last_pitch = element.pitch
            self._last_velocity = element.velocity

        # add drone
        if self._current_chord is None or self._last_pitch is None:
            return [element]

        notes = []
        for drone in self._drone_sets:
            if not drone.is_active:
                continue

            # pedals can't be triggered twice
            if drone.type == "pedal" and drone.is_running():
                continue

            notes_per_bar = None
            if drone.type != "pedal":
                notes_per_bar = self._current_notes_per_bar(drone, contour_values)
                drone_interval = self._time_signature.eighths_per_bar / notes_per_bar
                if element.time % drone_interval != 0:
                    continue

            # keep track of notes
            drone_notes = []

            prob = contour_values[drone.bind]

            if drone.probability_scale:
                prob = max((prob - drone.threshold) / (1 - drone.threshold), 0)
                can_drone = random.choices(
                    [True, False], weights=[prob, 1 - prob], k=1
                )[0]
            else:
                can_drone = prob >= drone.threshold

            can_drone = can_drone and drone.last_computed_time != element.time

            if can_drone:
                drone.last_computed_time = element.time.eighth_duration
                # get pitches
                drone_pitches = self._get_drone(self._last_pitch, drone, contour_values)

                # make pedal active if pedal
                if drone.type == "pedal" and len(drone_pitches) != 0:
                    drone.activate()

                else:
                    # create the note events
                    drone_pitches = sorted(drone_pitches, reverse=drone.ascending)

                d_notes, delay = self._add_drone(
                    element, drone_pitches, drone, notes_per_bar, contour_values
                )
                drone_notes.extend(d_notes)

                removable_delay = min(delay, element.duration)
                element.time += removable_delay
                element.duration -= removable_delay

            notes.extend(drone_notes)

        return [element, *notes]

    def _current_notes_per_bar(self, drone, contour_values):

        options = drone.notes_per_bar
        amount = contour_values[drone.notes_per_bar_bind]

        if len(options) != 1:
            index = np.round(
                (len(options) - 1) * (amount - drone.threshold) / (1 - drone.threshold)
            ).astype(int)
            index = max(0, min(len(options) - 1, index))
            return options[index]
        else:
            return options[0]

    def _get_drone(self, reference, drone, contour_values) -> np.array:

        notes = np.array([-1]).astype(int)
        drone_perc = contour_values[drone.bind]
        drone_perc = (drone_perc - drone.threshold) / (1 - drone.threshold)

        harmony = int(self._current_chord.root)
        allowed_harmony = self._current_chord.pitches

        # append root
        if drone.allow_root:
            allowed_harmony = np.append(
                allowed_harmony,
                (24 + self._key_signature.root - harmony) % 12,
            )

        # check on what string the note could be played
        available_notes = np.array(drone.notes) + drone.transpose

        index = []

        if drone.type == "bowed":
            distances = reference - available_notes
            distances[distances < 0] = 127
            # string note is being played on
            string = np.argmin(distances)

            # add lower string if there
            if string > 0:
                index.append(string - 1)

            # add upper string if there
            if string < len(available_notes) - 1:
                index.append(string + 1)

            index = np.array(index)

        elif drone.type in ["free", "pedal"]:
            index = np.arange(len(available_notes))

        else:
            raise Exception(f"Unknown drone type {drone.type}.")

        available_notes = available_notes[index]
        available_notes = available_notes[
            np.isin(
                np.round((12 + available_notes - harmony) % 12),
                allowed_harmony,
            )
        ]

        possible_bases = np.array([*available_notes, reference])
        # old harmony sort
        # index = np.argsort(0.1 * np.arange(len(available_notes))
        # + (7 * (available_notes - harmony)) % 12)

        # sort based on harmony
        # magic function time

        if self._current_chord.is_user:
            base = self._current_chord.bass + 12 * np.floor(
                min(np.min(self._all_drones), reference) / 12
            )

        else:
            frequencies = lu.midi_to_freq(possible_bases)
            reference_frequency = lu.midi_to_freq(reference)
            reference_to_notes_ratio = reference_frequency / frequencies

            harmony_frequency = lu.midi_to_freq(harmony)
            notes_to_harmony_ratio = frequencies / harmony_frequency

            reference_score = abs(
                reference_to_notes_ratio - np.round(reference_to_notes_ratio)
            )
            harmony_score = abs(
                notes_to_harmony_ratio - np.round(notes_to_harmony_ratio)
            )
            options = 0.75 * harmony_score + 0.25 * reference_score

            if len(options) == 0:
                base = harmony + 12 * np.round(
                    min(np.min(self._all_drones), reference) / 12
                )
                if harmony > 6:
                    base -= 12
            else:
                base = possible_bases[np.argmin(options)]

        frequencies = lu.midi_to_freq(available_notes)
        base_frequency = lu.midi_to_freq(base)
        frequencies_to_base_ratio = frequencies / base_frequency

        score = (
            np.round(
                10
                * abs(frequencies_to_base_ratio - np.round(frequencies_to_base_ratio))
            )
            / 10
        )
        """
        fb_2 = frequencies - base_frequency / 2
        score = (
            -np.nan_to_num(fb_2 / abs(fb_2), nan=1)
            * (1 / frequencies**0.01)
            * abs((2 * (2 * frequencies % base_frequency) / base_frequency) - 1)
        )
        """
        index = np.argsort(score)

        if len(index) != 0:
            # number of strings changes with intensity of signal
            drone_num = np.round(
                drone.polyphony_min * (1 - drone_perc)
                + drone_perc * drone.polyphony_max,
            ).astype(int)

            notes = np.concatenate((notes, available_notes[index[:drone_num]]))

        return notes[1:]

    def _add_drone(self, element, pitches, drone, notes_per_bar, contour_values):
        """Add drones to each note in input.

        :param notes: the notes to add a drone to.
        :param drone: the drone notes to add.

        :return: the input notes, with an added drone.
        """
        if drone.type == "pedal":
            note_duration = le.TimeDelta(np.inf)
        else:
            note_duration = self._time_signature.eighths_per_bar / notes_per_bar

        notes = []
        delay = 0

        for p in pitches:
            if drone.velocity_bind is not None:
                velocity = contour_values[drone.velocity_bind]
            else:
                velocity = self._last_velocity

            velocity *= drone.velocity_multiplier

            notes.append(
                le.Note(
                    pitch=p,
                    eighth_duration=(note_duration - delay).eighth_duration,
                    velocity=velocity,
                    time=(element.time + delay).eighth_duration,
                )
            )
            if drone.type != "pedal":
                val = drone.delay_range
                mul = 1
                if drone.delay_bind is not None:
                    mul = contour_values[drone.delay_bind]

                delay += mul * val

        return notes, delay


class TimingModule(LOERICModule):
    def __init__(
        self, bind: str, pattern: str, qpm_amount: float, only_increase: bool, **kwargs
    ):
        super().__init__(**kwargs)

        self._name = "timing"
        self._contour = bind
        self._pattern = pattern
        self._amount_qpm = qpm_amount
        self._only_increase = only_increase

        self._internal_offset = 0
        self._last_computation_time = le.TimeDelta(0)
        self._offset_snapshot = 0

        self._tempo = le.Tempo(qpm=120)
        self._first_tempo = None
        self._user_tempo_to_original_ratio = 1

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Apply timing.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        if isinstance(element, le.Tempo):
            if isinstance(element, le.UserTempo):
                self._user_tempo_to_original_ratio = element.qpm / self._first_tempo.qpm
            else:
                if self._first_tempo is None:
                    self._first_tempo = element
                self._tempo = element

        elif not isinstance(element, le.NullEvent):
            element = self._process_element(element, contour_values)

        # always update tempo
        qpm = self._process_tempo(contour_values)
        return [le.Tempo(qpm=qpm, time=element.time.eighth_duration), element]

    def _process_element(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
    ):
        current_time = copy.deepcopy(element.time)

        # all simultaneous notes share same offset
        update_offset = (
            element.is_performable and self._last_computation_time != current_time
        )

        if update_offset:
            self._last_computation_time = current_time
            self._offset_snapshot = self._internal_offset

        # keep original duration
        old_duration = element.duration.eighth_duration
        new_duration = old_duration * contour_values[self._pattern]

        # apply timing
        element.duration = new_duration

        # apply offset
        element.time -= self._offset_snapshot

        # only integrate once per score-time
        if update_offset:
            self._internal_offset += old_duration - new_duration

        return element

    def _process_tempo(self, contour_values):

        bpm = self._tempo.qpm * self._user_tempo_to_original_ratio
        value = 2 * self._amount_qpm * (contour_values[self._contour] - 0.5)

        calculated_tempo = bpm + value

        if self._only_increase:
            tempo = max(self._tempo.qpm, calculated_tempo)
        else:
            tempo = calculated_tempo

        # tempo /= contour_values[self._pattern]
        return tempo


class HistoryBufferModule(LOERICModule):
    def __init__(self, size: float, **kwargs):

        super().__init__(**kwargs)

        self._name = "buffer"
        assert size > 0, "Buffer size cannot be 0 or negative"
        self._lookahead_size = 0
        self._lookback_size = size
        self._buffer = []

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):

        current_time = element.time

        # update buffer
        self._buffer.append(element)

        self._buffer = [
            el for el in self._buffer if current_time - el.time < self._lookback_size
        ]

        return [element]


class DelayBufferModule(LOERICModule):
    def __init__(self, size: float, **kwargs):

        super().__init__(**kwargs)

        self._name = "buffer"
        assert size > 0, "Buffer size cannot be 0 or negative"
        self._lookahead_size = size
        self._lookback_size = 0
        self._buffer = []

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):

        current_time = element.time

        # update buffer
        self._buffer.append(element)

        # get all events now
        ret_val = [
            el for el in self._buffer if current_time - el.time >= self._lookahead_size
        ]
        # filter them out from buffer
        self._buffer = [
            el for el in self._buffer if current_time - el.time < self._lookahead_size
        ]

        # if nothing to return, make it up
        if len(ret_val) == 0:
            ret_val = [le.NullEvent(time=current_time.eighth_duration)]

        return ret_val


class LoggerModule(LOERICModule):

    def __init__(
        self,
        chords: bool,
        notes: bool,
        time_signatures: bool,
        key_signatures: bool,
        tempos: bool,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._do_chords = chords
        self._do_notes = notes
        self._do_time_s = time_signatures
        self._do_key_s = key_signatures
        self._do_tempo = tempos

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):

        if self._do_chords and isinstance(element, le.Chord):
            if element.is_user:
                logger.info(f"Forcing chord {element}")
            else:
                logger.info(f"Playing chord {element}")

        elif self._do_notes and isinstance(element, le.Note):
            logger.info(element)
        elif self._do_time_s and isinstance(element, le.TimeSignature):
            logger.info(element)
        elif self._do_key_s and isinstance(element, le.KeySignature):
            logger.info(element)
        elif self._do_tempo and isinstance(element, le.Tempo):
            logger.info(element)

        return [element]


class SwingModule(LOERICModule):
    def __init__(
        self, min: float, max: float, bind: str, locations: list[int], **kwargs
    ):
        super().__init__(**kwargs)

        self._name = "swing"
        self._min_swing = min
        self._max_swing = max
        self._contour = bind
        self._locations = locations
        self._time_signature = None

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Apply swing.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        if isinstance(element, le.TimeSignature):
            self._time_signature = copy.copy(element)

        elif isinstance(element, le.Note) or isinstance(element, le.Pause):
            x = element.time

            # is it an eight note?
            right_duration = element.duration == 1

            # is it the right place?
            current_location = int(
                (x % (self._time_signature.eighths_per_bar)).eighth_duration
            )
            right_location = current_location in self._locations

            perc = contour_values[self._contour]
            swing = self._min_swing * (1 - perc) + self._max_swing * perc

            # make this shorter
            if right_duration and right_location:
                multiplier = 2 / (swing + 1)
            # if next one is shorter, make this longer
            elif right_duration and current_location + 1 in self._locations:
                multiplier = 2 * swing / (swing + 1)
            # don't change anything
            else:
                multiplier = 1

            original_duration = element.duration
            new_duration = element.duration * multiplier

            if multiplier < 1:
                element.time = element.time + original_duration - new_duration

            element.duration = new_duration.eighth_duration

        return [element]


class LegatoModule(LOERICModule):
    def __init__(self, min: float, max: float, bind: str, **kwargs):
        super().__init__(**kwargs)

        self._name = "legato"
        self._legato_amount = max - min
        self._min_legato = min
        self._contour = bind

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Apply legato.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        if isinstance(element, le.Note):
            element.duration *= (
                self._min_legato + self._legato_amount * contour_values[self._contour]
            )
        return [element]
