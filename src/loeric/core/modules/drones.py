import copy
import random
from typing import Any

import numpy as np

import loeric.core.element as le
import loeric.core.modules.base as lmb
import loeric.core.paths as lp
import loeric.core.utils as lu


class DroneModuleConfig(lmb.ModuleConfig):
    """Config for :class:`DroneModule`.

    :param data: mapping of drone names to their individual configs.
    """

    data: dict[str, Any] = {}


@lp.expose("_contour", "bind")
@lp.expose("_whitelist", "whitelis")
@lp.readonly("data")
class DroneModule(lmb.LOERICModule):

    config_class = DroneModuleConfig

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

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Apply drones.

        :param element: the element to process.
        """
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
                        notes_per_bar = self._current_notes_per_bar(drone)
                        drone_interval = (
                            self._time_signature.eighths_per_bar / notes_per_bar
                        )
                        if element.time % drone_interval != 0:
                            continue

                # keep track of notes
                drone_notes = []

                prob = self._contour_values[drone.bind]

                if drone.probability_scale:
                    prob = max((prob - drone.threshold) / (1 - drone.threshold), 0)
                    can_drone = random.random() < prob
                else:
                    can_drone = prob >= drone.threshold

                can_drone = can_drone and drone.last_computed_time != element.time

                if can_drone:
                    drone.last_computed_time = element.time
                    # get pitches
                    drone_pitches = self._get_drone(self._last_pitch, drone)

                    # make pedal active if pedal
                    if drone.type == "pedal" and len(drone_pitches) != 0:
                        drone.activate()

                    else:
                        # create the note events
                        drone_pitches = sorted(
                            drone_pitches, reverse=not drone.ascending
                        )

                    d_notes, delay = self._add_drone(
                        element,
                        drone_pitches,
                        drone,
                        notes_per_bar,
                    )
                    drone_notes.extend(d_notes)

                    removable_delay = min(delay, element.duration)
                    element.time += removable_delay
                    element.duration -= removable_delay

                notes.extend(drone_notes)

        return [element, *notes]

    def _current_notes_per_bar(self, drone):

        options = drone.notes_per_bar
        if options is None:
            return self._time_signature.beat_count

        amount = self._contour_values[drone.notes_per_bar_bind]

        if len(options) != 1:
            index = np.round(
                (len(options) - 1) * (amount - drone.threshold) / (1 - drone.threshold)
            ).astype(int)
            index = max(0, min(len(options) - 1, index))
            return options[index]
        else:
            return options[0]

    def _get_drone(self, reference, drone) -> np.array:

        notes = np.array([-1]).astype(int)
        drone_perc = self._contour_values[drone.bind]
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

    def _add_drone(self, element, pitches, drone, notes_per_bar):
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
                velocity = self._contour_values[drone.velocity_bind]
            else:
                velocity = self._last_velocity

            velocity *= drone.velocity_multiplier

            notes.append(
                le.Note(
                    pitch=p,
                    eighth_duration=(note_duration - delay),
                    velocity=velocity,
                    time=(element.time + delay),
                )
            )
            if drone.type != "pedal":
                val = abs(drone.delay_range)
                mul = 1
                if drone.delay_bind is not None:
                    mul = self._contour_values[drone.delay_bind]

                delay += mul * val

        return notes, delay
