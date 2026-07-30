import logging
import random
from collections import defaultdict
from typing import Any

import numpy as np

import loeric.core.element as le
import loeric.core.module.base as lmb

logger = logging.getLogger(__name__)


class OrnamentModuleConfig(lmb.ModuleConfig):
    """Config for :class:`OrnamentModule`.

    :param bind: contour name controlling ornament probability.
    :param data: mapping of ornament names to their configs.
    :param whitelist: if set, only listed ornaments are active.
    """

    bind: str
    data: dict[str, Any] = {}
    whitelist: list[str] | None = None


class OrnamentModule(lmb.LOERICModule):

    config_class = OrnamentModuleConfig

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

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Apply ornament.

        :param element: the element to process.
        """
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
                self._eighths_to_skip -= element.duration
                return [le.NullEvent(time=element.duration)]

            if self._can_generate_ornament(self._contour_values[self._contour]):
                # choose which ornament
                ornament_type = self._choose_ornament(element, window)

                # generate it
                if ornament_type is not None:
                    notes = self._generate_ornament(element, ornament_type)

                    for a in list(self._accidentals.keys()):
                        notes.insert(
                            0,
                            le.Accidental(
                                pitch=a,
                                alteration=self._accidentals[a],
                                time=element.time,
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

    def _choose_ornament(self, element, window) -> str:
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
            if ornament.probability_contour in self._contour_values:
                prob = self._contour_values[ornament.probability_contour]

            # skip if 0
            if prob == 0:
                logger.debug(
                    f"Skipped ornament {ornament.name} because because probability is 0."
                )
                continue

            # check if this ornament has a dedicated contour
            if ornament.bind in self._contour_values:
                contour_value = self._contour_values[ornament.bind]
            # else use the default
            else:
                contour_value = self._contour_values[self._contour]

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
                time=offset,
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
            ornaments[-1].duration += abs(self._eighths_to_skip)

        if element.has_metadata:
            ornaments.extend(element.metadata)

        return ornaments
