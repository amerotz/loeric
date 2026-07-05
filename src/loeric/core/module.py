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
from functools import cached_property

import nanoid as nid
import numpy as np

import loeric.core.element as le
import loeric.core.paths as lp
import loeric.core.utils as lu

logger = logging.getLogger(__name__)


@lp.expose("_bypass", "bypass")
class LOERICModule:
    """A performance module implementing a series of performance rules."""

    _bypass: bool

    def __init__(
        self, bypass: bool = False, tag: str = None, required_tags: list[str] = None
    ):
        """A module to process note events.

        :param bypass: activate or deactivate the module.
        :param tag: apply a tag to the element.
        :param required_tags: tags required for the element to be processed.
        """
        self._signature = nid.generate()
        self._name = "module"

        self._lookahead_size = 0
        self._lookback_size = 0
        self._window_size = 0

        self._bypass = bypass
        self._tag = tag
        self._required_tags = required_tags
        self._is_online = False

        self._key_signature = None
        self._time_signature = None
        self._tempo = None

    def reset(self):
        """Reset all module attributes"""
        self._key_signature = None
        self._time_signature = None
        self._tempo = None

    def set_key_signature(self, key: le.KeySignature):
        self._key_signature = key

    def set_time_signature(self, meter: le.TimeSignature):
        self._time_signature = meter

    def set_tempo(self, tempo: le.Tempo):
        self._tempo = tempo

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
        if isinstance(element, le.TimeSignature):
            self._time_signature = copy.copy(element)
        elif isinstance(element, le.KeySignature):
            self._key_signature = copy.copy(element)
        elif isinstance(element, le.Tempo):
            self._tempo = copy.copy(element)

        return [element]

    def __call__(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        # if I saw this already, don't run again
        if (
            self._bypass
            or element.has_signature(self._signature)
            or not self._contains_required_tags(element)
            or isinstance(element, le.EndOfScore)
        ):
            return [element]

        # process it
        out = self.process(element, contour_values, window=window)

        # sign it
        for o in out:
            o.add_signature(self._signature, is_online=self._is_online)
            # propagate offline signatures of the original element
            o.copy_offline_signatures(element)
            # tag it
            if self._tag is not None:
                o.add_tag(self._tag)

        return out

    def _contains_required_tags(self, element: le.LOERICElement) -> bool:
        """Check if an element contains all required tags."""
        if self._required_tags is None:
            return True

        return all(element.has_tag(t) for t in self._required_tags)

    @cached_property
    def is_online(self):
        return self._is_online

    @cached_property
    def name(self):
        return self._name + "::" + self._signature

    @property
    def lookahead_size(self):
        return self._lookahead_size

    @property
    def window_size(self):
        return self._window_size

    @staticmethod
    def create_module(module_name: str, **kwargs):
        module_name = module_name.split("#")[0]
        _registry = {
            "legato": LegatoModule,
            "swing": SwingModule,
            "dynamics": DynamicsModule,
            "transpose": TransposeModule,
            "timing": TimingModule,
            "delay_buffer": DelayBufferModule,
            "history_buffer": HistoryBufferModule,
            "ornament": OrnamentModule,
            "drones": DroneModule,
            "harmony": HarmonyModule,
            "logger": LoggerModule,
            "conditional": ConditionalModule,
            "tagger": TaggerModule,
        }
        cls = _registry.get(module_name)
        if cls is None:
            raise ValueError(f"Invalid module name '{module_name}'.")
        return cls(**kwargs)


class LOERICCondition:

    def __init__(self, **kwargs):

        self._operation_dict = {
            "==": lambda x, y: x == y,
            "<": lambda x, y: x < y,
            ">": lambda x, y: x > y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "!=": lambda x, y: x != y,
        }

        self._attribute = kwargs["attribute"]
        self._value = kwargs["value"]

        assert (
            kwargs["operation"] in self._operation_dict
        ), f"Unknown operator {kwargs["operation"]}"
        self._operation = self._operation_dict[kwargs["operation"]]

    def eval(self, element):

        if hasattr(element, self._attribute):
            return self._operation(getattr(element, self._attribute), self._value)

        else:
            logger.warning(f"{element} has no attribute {self._attribute}.")
            return False

    def __call__(self, element):
        return self.eval(element)


class ConditionalModule(LOERICModule):
    def __init__(self, condition: dict, module: dict, **kwargs):
        super().__init__(**kwargs)

        self._name = "conditional"

        name = list(module.keys())[0]
        self._module = LOERICModule.create_module(name, **module[name])
        self._condition = LOERICCondition(**condition)

        self._is_online = self._module.is_online

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Execute the module if the condition is met.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        element = super().process(element, contour_values, window)[0]

        if not element.is_performable:
            val = self._module(element, contour_values, window)

        if self._condition(element):
            if element.is_performable:
                val = self._module(element, contour_values, window)
            return val
        else:
            return [element]


class TaggerModule(LOERICModule):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._name = "tagger"

    def process(
        self,
        element: le.LOERICElement,
        contour_values: np.array,
        window: list[le.LOERICElement] = None,
    ):
        """Tags notes.

        :param element: the element to process.
        :param contour_values: the contour values to use.
        """
        return [element]


@lp.expose("_steps", "steps")
class TransposeModule(LOERICModule):
    _steps: float

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
        element = super().process(element, contour_values, window)[0]

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
        self._last_computation_time = -np.inf
        self._window_size = None

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

    def reset(self):
        super().reset()

        self._window_size = None

    @property
    def window_size(self):
        if self._time_signature is not None:
            c_per_bar = self._chords_per_bar
            if c_per_bar is None:
                c_per_bar = self._time_signature.beat_count
            self._window_size = self._time_signature.eighths_per_bar / c_per_bar
            return self._window_size
        else:
            return None

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
        element = super().process(element, contour_values, window)[0]

        accidentals = []
        if isinstance(element, le.Chord):
            self._last_forced_chord = copy.copy(element)

            if self._last_forced_chord.is_valid:

                accidentals = self._obtain_accidentals(element)

            else:
                # filter out the null chord
                element = le.NullEvent(time=element.time.eighth_duration)

        # only compute when reaching the interval
        should_compute = (
            self.window_size is not None
            and element.time % self._window_size == 0
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

            return [*accidentals, chord, element]

        return [*accidentals, element]

    @property
    def _allowed_chords(self):
        if self._key_signature is None or self._key_signature.mode not in self._weights:
            return self._weights["default"]
        else:
            return self._weights[self._key_signature.mode]

    def _obtain_accidentals(self, element):
        accidentals = []
        chord_quality = np.roll(self._chord_qualities, self._key_signature.major_root)[
            self._last_forced_chord.root
        ]

        # propagate accidentals
        if self._last_forced_chord.quality != chord_quality:
            mode_chord = le.Chord.create_chord(
                self._last_forced_chord.root, chord_quality
            )
            # some chords are triads, some are sevenths
            chord_len = min(
                len(mode_chord.pitches), len(self._last_forced_chord.pitches)
            )
            # check degrees that are flat/sharp
            differences = (
                self._last_forced_chord.pitches[:chord_len]
                - mode_chord.pitches[:chord_len]
            )
            # create accidentals
            for alteration, degree in zip(differences, mode_chord.pitches[:chord_len]):
                if alteration == 0:
                    continue
                p = (self._last_forced_chord.root + degree) % 12
                accidentals.append(
                    le.Accidental(
                        pitch=p,
                        alteration=alteration,
                        time=element.time.eighth_duration,
                    )
                )
        return accidentals

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

        # check chord quality according to mode
        chord_quality = np.roll(self._chord_qualities, self._key_signature.major_root)[
            root
        ]

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

        return le.Chord.create_chord(root, chord_quality)


@lp.expose("_contour", "bind")
@lp.expose("_pattern", "pattern")
class DynamicsModule(LOERICModule):

    _contour: str
    _pattern: str

    def __init__(self, bind: str, pattern: str, **kwargs):
        super().__init__(**kwargs)

        self._contour = bind
        self._pattern = pattern
        self._name = "dynamics"
        self._is_online = True

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
        element = super().process(element, contour_values, window)[0]

        if isinstance(element, le.Note):
            element.velocity = contour_values[self._contour]
            if self._pattern is not None:
                element.velocity *= contour_values[self._pattern]
        return [element]


@lp.expose("_contour", "bind")
@lp.expose("_whitelist", "whitelis")
@lp.readonly("data")
class OrnamentModule(LOERICModule):

    _contour: str
    _whitelist: list[str]

    class OrnamentConfig:

        __slots__ = (
            "name",
            "probability_contour",
            "bind",
            "cases",
            "pitches_mean",
            "pitches_std",
            "velocities_mean",
            "velocities_std",
            "durations_mean",
            "durations_std",
            "probability",
            "length",
            "diatonic",
            "threshold",
            "slide",
        )

        def __init__(self, name: str, config: dict):

            self.name = name

            for key in config:
                setattr(self, key, config[key])

            self.probability_contour = config.get("bind")
            self.bind = config.get("bind")

        def __repr__(self):
            return f"(Ornament {self.name} slide={self.slide} thr={self.threshold} p={self.probability})"

    def __init__(self, bind: str, data: dict, whitelist: list[str], **kwargs):
        super().__init__(**kwargs)

        self._name = "ornament"
        self._contour = bind
        self._ornaments = [self.OrnamentConfig(o, data[o]) for o in data]
        self._window_size = 0
        self._is_online = True

        if len(self._ornaments) != 0:
            self._window_size = max([o.length for o in self._ornaments])

        if whitelist is None:
            self._whitelist = [o.name for o in self._ornaments]
        else:
            self._whitelist = whitelist

        self._whitelist = set(self._whitelist)

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
        element = super().process(element, contour_values, window)[0]

        if isinstance(element, le.Accidental):
            self._accidentals[element.pitch] = element.alteration
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
        return random.random() < prob

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
                                f"Skipped ornament {ornament.name} because window is too small."
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

        __slots__ = (
            "probability_scale",
            "delay_bind",
            "velocity_bind",
            "sync_with_notes",
            "_name",
            "harmony_weight",
            "reference_weight",
            "last_computed_time",
            "_is_running",
            "allow_root",
            "type",
            "is_active",
            "notes",
            "polyphony_min",
            "polyphony_max",
            "threshold",
            "bind",
            "velocity_multiplier",
            "notes_per_bar",
            "notes_per_bar_bind",
            "transpose",
            "delay_range",
            "ascending",
        )

        def __init__(self, name, config):

            self._name = name
            self.harmony_weight = 0.75
            self.reference_weight = 0.25

            for key in config:
                setattr(self, key, config[key])

            self.probability_scale = config.get("probability_scale")
            self.delay_bind = config.get("delay_bind")
            self.velocity_bind = config.get("velocity_bind")

            if "sync_with_notes" not in config:
                self.sync_with_notes = False

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
        self._is_online = True

        self._drone_sets = [self.DroneConfig(d, data[d]) for d in data]
        self._last_pitch = None
        self._last_velocity = None
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
        element = super().process(element, contour_values, window)[0]

        if isinstance(element, le.Chord):
            self._current_chord = copy.copy(element)
        elif isinstance(element, le.Note):
            self._last_pitch = element.pitch
            self._last_velocity = element.velocity

        # add drone
        notes = []
        if (
            self._current_chord is not None
            and self._last_pitch is not None
            and (element.is_performable or isinstance(element, le.NullEvent))
        ):

            for drone in self._drone_sets:
                if not drone.is_active:
                    continue

                # pedals can't be triggered twice
                if drone.type == "pedal" and drone.is_running():
                    continue

                notes_per_bar = None
                if drone.type != "pedal":
                    if drone.sync_with_notes:
                        # if this is not a note
                        # but we want drones only with score notes
                        # skip
                        if not isinstance(element, le.Note):
                            continue
                        else:
                            notes_per_bar = (
                                self._time_signature.eighths_per_bar / element.duration
                            )
                        drone_interval = (
                            self._time_signature.eighths_per_bar / notes_per_bar
                        )
                    else:
                        notes_per_bar = self._current_notes_per_bar(
                            drone, contour_values
                        )
                        drone_interval = (
                            self._time_signature.eighths_per_bar / notes_per_bar
                        )
                        if element.time % drone_interval != 0:
                            continue

                # keep track of notes
                drone_notes = []

                prob = contour_values[drone.bind]

                if drone.probability_scale:
                    prob = max((prob - drone.threshold) / (1 - drone.threshold), 0)
                    can_drone = random.random() < prob
                else:
                    can_drone = prob >= drone.threshold

                can_drone = can_drone and drone.last_computed_time != element.time

                if can_drone:
                    drone.last_computed_time = element.time.eighth_duration
                    # get pitches
                    drone_pitches = self._get_drone(
                        self._last_pitch, drone, contour_values
                    )

                    # make pedal active if pedal
                    if drone.type == "pedal" and len(drone_pitches) != 0:
                        drone.activate()

                    else:
                        # create the note events
                        drone_pitches = sorted(
                            drone_pitches, reverse=not drone.ascending
                        )

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
        if options is None:
            return self._time_signature.beat_count

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
            options = (
                drone.harmony_weight * harmony_score
                + drone.reference_weight * reference_score
            )

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
                val = abs(drone.delay_range)
                mul = 1
                if drone.delay_bind is not None:
                    mul = contour_values[drone.delay_bind]

                delay += mul * val

        return notes, delay


@lp.expose("_contour", "bind")
@lp.expose("_pattern", "pattern")
@lp.expose("_amount_qpm", "amount_qpm")
@lp.expose("_only_increase", "only_increase")
class TimingModule(LOERICModule):

    _contour: str
    _pattern: str
    _amount_qpm: float
    _only_increase: bool

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
        self._is_online = True

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
        element = super().process(element, contour_values, window)[0]

        if isinstance(element, le.UserTempo):
            self._user_tempo_to_original_ratio = element.qpm / self._first_tempo.qpm
        elif isinstance(element, le.Tempo):
            if self._first_tempo is None:
                self._first_tempo = element

        elif not isinstance(element, le.NullEvent) and element.is_performable:
            element = self._process_element(element, contour_values)

        ret_val = [element]
        # always update tempo
        if self._tempo is not None:
            qpm = self._process_tempo(contour_values)
            ret_val.insert(0, le.Tempo(qpm=qpm, time=element.time.eighth_duration))
        return ret_val

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

        element = super().process(element, contour_values, window)[0]

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

    def process(self, element, contour_values, window=None):
        element = super().process(element, contour_values, window)[0]

        current_time = element.time
        self._buffer.append(element)

        ready = []
        pending = []
        for el in self._buffer:
            if current_time - el.time >= self._lookahead_size:
                ready.append(el)
            else:
                pending.append(el)
        self._buffer = pending

        if not ready:
            return [le.NullEvent(time=current_time.eighth_duration)]
        return ready


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

        element = super().process(element, contour_values, window)[0]

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
        self._locations = set(locations)
        self._is_online = True

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
        element = super().process(element, contour_values, window)[0]

        if isinstance(element, le.Note) or isinstance(element, le.Pause):
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
        self._is_online = True

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
        element = super().process(element, contour_values, window)[0]

        if isinstance(element, le.Note):
            element.duration *= (
                self._min_legato + self._legato_amount * contour_values[self._contour]
            )
        return [element]
