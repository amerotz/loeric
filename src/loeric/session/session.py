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

import json
import random
import threading
import time
from collections import defaultdict

import numpy as np

import loeric
import loeric.core.tune as tu


class Session:

    def __init__(self, config: dict):

        self._players = {}

        self._config = config

        for p in self._config["players"]:

            # load player config
            with open(self._config[p]["config"], "r") as f:
                player_config = json.load(f)

            # create player
            self._players[p] = loeric.LOERIC(player_config)

            # load player part
            tune = tu.Tune(self._config[p]["part"], self._config[p]["repeats"])

            # set player part
            self._players[p].set_tune(tune)

    def start(self, wait_for_prompt=False):
        """Start all LOERIC instances."""
        for p in self._players:
            self._players[p].start(wait_for_prompt=wait_for_prompt)


class OldSession:

    def __init__(self, config):

        with open(config, "r") as f:
            self._config = json.load(f)

        # create dictionaries
        self._loeric_positions = {}
        self._was_updated = defaultdict(bool)
        self._loeric_tempos = {}
        self._sleepers = []
        self._sleepers_lock = threading.Lock()
        self._position_lock = threading.Lock()
        # self._out = out

        self._intensity_dict = defaultdict(int)
        self._human_impact_dict = defaultdict(int)
        self._action_dict = {}

    @property
    def sync_interval(self):
        return 2 * self._config["tempo_policy"]["sync_interval_quarters"]

    def set_tempo(self, tempo):
        self._last_tempo = tempo

        if self._config["tempo_policy"]["absolute_time"]:
            self._fix_sync_duration = (
                self._config["tempo_policy"]["fix_sync_millis"] / 1000
            )
            self._stop_sync_duration = (
                self._config["tempo_policy"]["stop_sync_millis"] / 1000
            )
        else:
            self._fix_sync_duration = (
                self._config["tempo_policy"]["fix_sync_quarters"]
                * 60
                / self._last_tempo
            )
            self._stop_sync_duration = (
                self._config["tempo_policy"]["stop_sync_quarters"]
                * 60
                / self._last_tempo
            )

        self._songpos_wait = (
            self._config["tempo_policy"]["sync_interval_quarters"]
            * 60
            / self._last_tempo
        )

        self._switch_timer = (
            self._config["attention_policy"]["switch_every_quarters"]
            * 60
            / self._last_tempo
        )

    def session_loop(self):

        # all_dead.acquire()
        print("[LOOP] Session loop thread started.")
        while not stop_event.is_set():

            # now = time.time()
            # handle sleep/awakening
            with self._sleepers_lock:

                # awake sleeping loerics
                new_sleepers = []
                for s in self._sleepers:

                    # get info
                    groover, start_time, wait_time, sleeper_position = s

                    # if enough time has passed
                    current_time = time.time()
                    if current_time - start_time >= wait_time:
                        # wakey wakey!

                        # unflag stopped
                        with groover.lock:
                            groover.stopped.clear()
                        with self._position_lock:
                            # update  position
                            self._loeric_positions[groover.loeric_id] = (
                                current_time,
                                sleeper_position,
                            )

                        # awake thread
                        groover.playback_resumed.set()

                        print(
                            f"[LOOP] {groover.loeric_id} AWKN at {sleeper_position} ({current_time - program_start})"
                        )
                    else:
                        # nevermind, keep sleeping
                        new_sleepers.append(s)

                self._sleepers = new_sleepers

            # no need to run all the time
            time.sleep(1 / 50)

        # all_dead.release()

    def handle_human_pos(self, human_id, position):
        # don't sync the human
        # but record positions
        now = time.time()
        if (
            # if first time
            human_id not in self._loeric_positions
            # or human skipped a beat
            or now - self._loeric_positions[human_id][0] > 2 * self._songpos_wait
        ):
            # get loeric positions
            with self._position_lock:
                positions = [t[1] for t in self._loeric_positions.values()]

            # assume human to be following the fastest loeric
            value = 0
            if len(positions) != 0:
                value = max(positions)

            with self._position_lock:
                self._loeric_positions[human_id] = (now, value)

        # only advance human position
        else:
            with self._position_lock:
                self._loeric_positions[human_id] = (
                    now,
                    self._loeric_positions[human_id][1] + 1,
                )

        """
        print(
            f"[SYNC] {human_id} SENT {self._loeric_positions[human_id][1]} {(self._loeric_positions[human_id][0] - program_start)}"
        )
        """

    def _calculate_position(self, loeric_id):

        with self._position_lock:
            positions = np.array(
                [
                    self._loeric_positions[t][1]
                    for t in self._loeric_positions
                    if t not in self._sleepers
                    # if t != loeric_id
                ]
            )
            times = np.array(
                [
                    self._loeric_positions[t][0]
                    for t in self._loeric_positions
                    if t not in self._sleepers
                    # if t != loeric_id
                ]
            )

            if len(positions) == 0:
                return self._loeric_positions[loeric_id]

        # agree on which position
        algorithm = self._config["tempo_policy"]["position"]
        if algorithm == "max":
            calculated_position = max(positions)
            timestamp = np.max(times[positions == calculated_position])
        elif algorithm == "min":
            calculated_position = min(positions)
            timestamp = np.min(times[positions == calculated_position])
        elif algorithm == "mode":
            vals, counts = np.unique(
                positions,
                return_counts=True,
            )
            calculated_position = vals[np.argmax(counts)]
            timestamp = np.mean(times[positions == calculated_position])

        return timestamp, calculated_position

    def _put_to_sleep(self, groover, start_time, wait_time, position):
        with self._sleepers_lock:
            self._sleepers.append(
                # in (songpos wait - diff) the reference will be at p+1
                # (now, later, groover, position)
                (groover, start_time, wait_time, position)
            )

    def _hard_fix(self, groover, position):
        with groover.lock:
            # tell groover to wait
            groover.stopped.set()

            # tell groover to start at next songpos
            groover.jump_to_pos(int(position))

    def _calculate_new_tempo(self, now, expected_timestamp):
        """Q = self._songpos_wait
        v0 = self._last_tempo
        v1 = self._last_tempo
        t0 = now
        t1 = expected_timestamp
        f1t1 = v1 * t1
        q1 = (f1t1 + Q) / v1
        f1q1 = v1 * q1
        f0t0 = v0 * t0
        w = (f1q1 - f0t0) / (q1 - t0)
        """
        multiplier = self._songpos_wait / (
            expected_timestamp + self._songpos_wait - now
        )
        w = self._last_tempo * multiplier

        return w

    def handle_loeric_pos(self, groover: gr.Groover, player: pl.Player, position: int):
        # obtain timestamp
        now = time.time()

        # who sent this?
        loeric_id = groover.loeric_id

        # print(loeric_id, "SENT", position)

        with self._position_lock:
            # store a tuple (time, position) for each
            self._loeric_positions[loeric_id] = (now, position)

        # obtain sync position
        timestamp, calculated_position = self._calculate_position(loeric_id)

        # print(f"[SYNC]\t{loeric_id} SENT {position} ({now-program_start})")

        # expected timestamp
        expected_songpos_timestamp = (
            timestamp + (position - calculated_position) * self._songpos_wait
        )

        # calculate difference in timestamp
        diff = abs(now - expected_songpos_timestamp)
        fix_thr = self._fix_sync_duration
        stop_thr = self._stop_sync_duration
        # print(diff, fix_thr, stop_thr, self._songpos_wait)

        # if tempo was updated before
        # we need to reset it to the original
        if self._was_updated[loeric_id]:
            with groover.lock:
                groover.set_tempo(self._last_tempo)
                player.set_tempo_scale(groover.tempo_scale)
            self._was_updated[loeric_id] = False

        # hard fix
        # stop and continue from next beat
        if diff > stop_thr:

            # add it to the sleepers queue
            # to be awaken at next position
            wake_position = calculated_position + 1
            if position > calculated_position:
                wake_position = position

            # tell groover to start at next songpos
            self._hard_fix(groover, wake_position)

            self._put_to_sleep(
                groover=groover,
                start_time=now,
                wait_time=self._songpos_wait - (now - timestamp),
                position=wake_position,
            )

            print(
                f"[SYNC]\t{loeric_id} SLEP at {calculated_position}",
                self._songpos_wait + timestamp - program_start,
            )

            with self._position_lock:
                self._loeric_positions[loeric_id] = (
                    expected_songpos_timestamp,
                    position,
                )

        # soft fix
        # send a tempo bump
        elif diff >= fix_thr:

            # calculate the new tempo
            # so that we synchronize on the next beat
            new_tempo = self._calculate_new_tempo(now, expected_songpos_timestamp)
            if new_tempo > 200:
                print(new_tempo, calculated_position, position)

            with groover.lock:
                groover.set_tempo(new_tempo)
                player.set_tempo_scale(groover.tempo_scale)
            self._was_updated[loeric_id] = True

            print(
                f"[SYNC]\t{loeric_id} BUMP at {calculated_position}",
                np.round(new_tempo, 2),
            )

            with self._position_lock:
                self._loeric_positions[loeric_id] = (
                    expected_songpos_timestamp,
                    position,
                )

    def handle_human_intensity(self, human_id, control, value):

        # keep track of intensity
        if control == self._config["intensity_control_out"]:
            self._intensity_dict[human_id] = value
            print("[INSY]:\t", np.round(value, 2))

        # keep track of human_impact
        if control == self._config["human_impact_control_out"]:
            self._human_impact_dict[human_id] = value
            print("[HUIP]:\t", np.round(value, 2))

    def handle_loeric_intensity(self, groover: gr.Groover):

        now = time.time()

        # who sent this?
        loeric_id = groover.loeric_id

        # keep track of intensity
        self._intensity_dict[loeric_id] = np.mean(
            groover.get_control_value(self._config["intensity_control_out"])
        )

        # keep track of human_impact
        self._human_impact_dict[loeric_id] = np.mean(
            groover.get_control_value(self._config["human_impact_control_out"])
        )

        # choose new action
        if (
            loeric_id not in self._action_dict
            or now - self._action_dict[loeric_id][0] >= self._switch_timer
        ):

            players = [p for p in self._intensity_dict.keys() if str(p) != loeric_id]
            # backoff or
            # match
            # any group of players
            # action = random.choice(["backoff", "match", "lead"])
            action = random.choice(
                list(self._config["attention_policy"]["behaviors"].keys())
            )
            n = 1
            if len(players) < 1:
                return
            elif len(players) > 1:
                n = random.randint(
                    min(
                        self._config["attention_policy"]["attention_group_min_size"],
                        len(players),
                    ),
                    min(
                        self._config["attention_policy"]["attention_group_max_size"],
                        len(players),
                    ),
                )

            if self._config["attention_policy"]["human_only"]:
                candidates = [p for p in players if "HUMAN" in p]
                if len(candidates) < 1:
                    return
                group = random.sample(candidates, min(n, len(candidates)))
            else:
                group = random.sample(players, n)

            self._action_dict[loeric_id] = (now, action, group)
            print(f"[SESS]\t{loeric_id:10}\t{action}\t{group}")

        _, action, group = self._action_dict[loeric_id]
        if type(group) is not list:
            group = [group]

        # intensity
        int_value = 0
        algorithm = self._config["attention_policy"]["behaviors"][action][
            "intensity_aggregator"
        ]
        if algorithm == "mean":
            int_value = np.mean([self._intensity_dict[p] for p in group])
        elif algorithm == "min":
            int_value = np.min([self._intensity_dict[p] for p in group])
        elif algorithm == "max":
            int_value = np.max([self._intensity_dict[p] for p in group])
        elif algorithm == "constant":
            pass

        int_value *= self._config["attention_policy"]["behaviors"][action][
            "intensity_multiplier"
        ]
        int_value += self._config["attention_policy"]["behaviors"][action][
            "intensity_constant"
        ]

        hi_value = 0
        algorithm = self._config["attention_policy"]["behaviors"][action][
            "human_impact_aggregator"
        ]
        if algorithm == "mean":
            hi_value = np.mean([self._human_impact_dict[p] for p in group])
        elif algorithm == "min":
            hi_value = np.min([self._human_impact_dict[p] for p in group])
        elif algorithm == "max":
            hi_value = np.max([self._human_impact_dict[p] for p in group])
        elif algorithm == "constant":
            pass

        hi_value *= self._config["attention_policy"]["behaviors"][action][
            "human_impact_multiplier"
        ]
        hi_value += self._config["attention_policy"]["behaviors"][action][
            "human_impact_constant"
        ]

        int_value = min(int_value, 1)
        int_value = max(int_value, 0)

        hi_value = min(hi_value, 1)
        hi_value = max(hi_value, 0)

        groover.set_control_value(self._config["intensity_control_in"], int_value)

        groover.set_control_value(self._config["human_impact_control_in"], hi_value)
