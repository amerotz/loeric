# ============================================================
# SCORE FOLLOWER (vectorised subsequence alignment)
# ============================================================


class ScoreFollower:

    def __init__(self, score):
        self.score = score
        score_length = self.score_length = score.n
        self.history = deque()
        self.base_window = score.history_window_seconds()
        self.speed_hint = 1.0

        # precalculate pitch class kernel distances
        pitch_classes = np.arange(12)
        dist = np.abs(pitch_classes[:, None] - pitch_classes[None, :])
        dist = np.minimum(dist, 12 - dist)
        pitch_class_kernel = np.exp(-0.5 * (dist / PITCH_DISTANCE_SIGMA) ** 2).astype(
            np.float32
        )
        self.pitch_class_kernel = pitch_class_kernel

        # precompute the inverse of the number of
        # pitch classes per score position
        score_matrix = np.zeros((score_length, 12), dtype=np.float32)
        score_top_voice = np.zeros(score_length, dtype=np.intp)
        for i, e in enumerate(score.events):
            for p in e.pitches:
                score_matrix[i, p % 12] = 1.0
            score_top_voice[i] = max(e.pitches) % 12
        inverse_pitch_class_count = (1.0 / score_matrix.sum(axis=1)).astype(np.float32)

        # precompute the matrix of which pitch class
        # would match a given score event best
        # best_pitch_to_event_match[a, j] = best kernel match of pitch class `a` against score event j.
        best_pitch_to_event_match = np.empty((12, score_length), dtype=np.float32)
        for a in range(12):
            best_pitch_to_event_match[a] = (
                score_matrix * pitch_class_kernel[a][None, :]
            ).max(axis=1)

        # topline_pitch_class_kernel[a, j] = K[a, top_j]
        # pitch class kernel for top voice only
        topline_pitch_class_kernel = np.ascontiguousarray(
            pitch_class_kernel[:, score_top_voice]
        )
        score_matrix_T = np.ascontiguousarray(score_matrix.T)
        (
            self.best_pitch_to_event_match,
            self.topline_pitch_class_kernel,
            self.score_matrix_T,
            self.inverse_pitch_class_count,
        ) = (
            best_pitch_to_event_match,
            topline_pitch_class_kernel,
            score_matrix_T,
            inverse_pitch_class_count,
        )

        # Circularly extended copies so a match may wrap past the end of the score.
        self.circular_extension_amount = min(
            score_length,
            MAX_HISTORY_EVENTS * MAX_ALIGNMENT_MULTIPLIER + MAX_ALIGNMENT_EXTRA,
        )
        cols = np.arange(score_length + self.circular_extension_amount) % score_length
        self.best_pitch_to_event_match_x = np.ascontiguousarray(
            best_pitch_to_event_match[:, cols]
        )
        self.topline_pitch_class_kernel_x = np.ascontiguousarray(
            topline_pitch_class_kernel[:, cols]
        )
        self.score_matrix_T_x = np.ascontiguousarray(score_matrix_T[:, cols])
        self.inverse_pitch_class_count_x = np.ascontiguousarray(
            inverse_pitch_class_count[cols]
        )

        # preallocate dynamic programming matrices
        max_c = (
            max(
                score_length + self.circular_extension_amount, 2 * LOCAL_HALF_WINDOW + 1
            )
            + 1
        )
        self._D = np.empty((MAX_HISTORY_EVENTS + 1, max_c), dtype=np.float64)
        self._tr = np.zeros((MAX_HISTORY_EVENTS + 1, max_c), dtype=np.uint8)
        self._tmp = np.empty(max_c, dtype=np.float64)
        self._jdel = np.arange(max_c, dtype=np.float64) * DELETION_COST

    # ---------------------------------------------------- history

    def reset(self):
        self.history.clear()

    def ready(self):
        return len(self.history) >= MIN_HISTORY

    def add(self, ev):
        h = self.history
        h.append(ev)
        while len(h) > MAX_HISTORY_EVENTS:
            h.popleft()
        speed = min(max(self.speed_hint, MIN_PLAYBACK_SPEED), MAX_PLAYBACK_SPEED)
        cutoff = ev.timestamp - self.base_window / speed
        keep = MIN_HISTORY + 2
        while len(h) > keep and h[0].timestamp < cutoff:
            h.popleft()
        for i in range(len(h) - 1, 0, -1):
            if h[i].timestamp - h[i - 1].timestamp > HISTORY_GAP_RESET:
                for _ in range(i):
                    h.popleft()
                break

    # ---------------------------------------------------- alignment core

    def _dp(self, cost):
        """Free-start / free-end subsequence alignment.

        D[i, j]: best cost of aligning the first i played events to a score
        segment ending at column j. Moves: match (diag), played-event
        insertion (up), score-event deletion (left). The left moves are
        resolved for a whole row at once with a prefix-minimum scan.
        """
        m, C = cost.shape
        D = self._D[: m + 1, : C + 1]
        tr = self._tr[: m + 1, : C + 1]
        jdel = self._jdel[: C + 1]
        tmp = self._tmp[: C + 1]
        D[0, :] = 0.0
        for i in range(1, m + 1):
            prev = D[i - 1]
            row = D[i]
            diag = prev[:-1] + cost[i - 1]
            ins = prev[1:] + INSERTION_COST
            use_ins = ins < diag
            np.minimum(diag, ins, out=diag)
            tr[i, 1:] = use_ins
            row[0] = prev[0] + INSERTION_COST
            row[1:] = diag
            np.subtract(row, jdel, out=tmp)
            np.minimum.accumulate(tmp, out=tmp)
            np.add(tmp, jdel, out=row)
            np.putmask(tr[i, 1:], row[1:] < diag - 1e-9, 2)
        return D, tr

    @staticmethod
    def _rhythm(t_in, t_sc):
        """Robust tempo (score s / wall s) and timing consistency of matched pairs."""
        k = len(t_in)
        if k < 4:
            return None, 0.5
        iu = np.triu_indices(k, 1)
        dt = (t_in[None, :] - t_in[:, None])[iu]
        ds = (t_sc[None, :] - t_sc[:, None])[iu]
        ok = (dt >= MIN_SLOPE_SPAN) & (ds > 0)
        if ok.sum() < 2:
            return None, 0.5
        slopes = ds[ok] / dt[ok]
        slopes = slopes[(slopes >= MIN_PLAYBACK_SPEED) & (slopes <= MAX_PLAYBACK_SPEED)]
        if len(slopes) < 2:
            return None, 0.3
        speed = float(np.median(slopes))
        resid = t_sc - speed * t_in
        resid = np.abs(resid - np.median(resid))
        return speed, float(math.exp(-float(np.median(resid)) / RHYTHM_SIGMA))

    def align(self, expected=None, windowed=False):
        history = list(self.history)
        history_length = len(history)
        if history_length < MIN_HISTORY:
            return None
        score_length = self.score_length

        if (
            windowed
            and expected is not None
            and score_length
            > 2 * LOCAL_HALF_WINDOW + 1 + self.circular_extension_amount
        ):
            start = (expected - LOCAL_HALF_WINDOW) % score_length
            extended_score_length = 2 * LOCAL_HALF_WINDOW + 1
            idx = (start + np.arange(extended_score_length)) % score_length
            (
                best_pitch_to_event_match,
                topline_pitch_class_kernel,
                score_matrix_T,
                inverse_pitch_class_count,
            ) = (
                self.best_pitch_to_event_match[:, idx],
                self.topline_pitch_class_kernel[:, idx],
                self.score_matrix_T[:, idx],
                self.inverse_pitch_class_count[idx],
            )
        else:
            start = 0
            extended_score_length = score_length + self.circular_extension_amount
            (
                best_pitch_to_event_match,
                topline_pitch_class_kernel,
                score_matrix_T,
                inverse_pitch_class_count,
            ) = (
                self.best_pitch_to_event_match_x,
                self.topline_pitch_class_kernel_x,
                self.score_matrix_T_x,
                self.inverse_pitch_class_count_x,
            )

        observed_pitch_classes = np.stack([e.pc for e in history])
        observed_pitch_classes_topline = np.fromiter(
            (e.top_pc for e in history), dtype=np.intp, count=history_length
        )
        co = observed_pitch_classes.sum(axis=1)
        best_pitch_to_event_match_observed = (
            observed_pitch_classes[:, :, None] * self.pitch_class_kernel[None, :, :]
        ).max(axis=1)
        P = (observed_pitch_classes @ best_pitch_to_event_match) / co[
            :, None
        ]  # played notes explained by the score chord
        R = (
            best_pitch_to_event_match_observed @ score_matrix_T
        ) * inverse_pitch_class_count[
            None, :
        ]  # score chord notes that were played
        M = topline_pitch_class_kernel[
            observed_pitch_classes_topline
        ]  # top voice agreement
        sim = (
            (HARMONY_WEIGHT * PRECISION_SHARE) * P
            + (HARMONY_WEIGHT * (1.0 - PRECISION_SHARE)) * R
            + MELODY_WEIGHT * M
        )
        cost = 1.0 - sim

        D, tr = self._dp(cost)
        raw = (
            D[history_length, 1 : extended_score_length + 1] / history_length
        )  # normalised cost for each end column
        cols = np.arange(extended_score_length)
        s_idx = (start + cols) % score_length

        selection = raw
        if expected is not None:
            d = np.abs(s_idx - expected)
            d = np.minimum(d, score_length - d)
            selection = raw + PRIOR_WEIGHT * np.minimum(d / PRIOR_SCALE_EVENTS, 1.0)
        c_best = int(np.argmin(selection))
        best_cost = float(raw[c_best])

        # ---- traceback
        po, pc_ = [], []
        i, j = history_length, c_best + 1
        while i > 0:
            if j == 0:
                i -= 1
                continue
            op = tr[i, j]
            if op == 2:
                j -= 1
            elif op == 1:
                i -= 1
            else:
                po.append(i - 1)
                pc_.append(j - 1)
                i -= 1
                j -= 1
        if not po:
            return None
        po.reverse()
        pc_.reverse()
        po = np.asarray(po, dtype=np.intp)
        ext_idx = start + np.asarray(pc_, dtype=np.int64)

        t_obs = np.fromiter(
            (e.timestamp for e in history), dtype=np.float64, count=history_length
        )
        t_in = t_obs[po]
        t_sc = np.asarray(self.score.time_for_index(ext_idx), dtype=np.float64)
        speed, rhythm = self._rhythm(t_in, t_sc)

        position = int(ext_idx[-1] % score_length)
        matched = len(po)
        combined = best_cost + RHYTHM_WEIGHT * (1.0 - rhythm)
        confidence = math.exp(-2.0 * combined) * (matched / history_length)

        # ---- ambiguity: best rival alignment at a different place
        dd = np.abs(s_idx - int(s_idx[c_best]))
        dd = np.minimum(dd, score_length - dd)
        rival = dd > SECOND_BEST_GUARD
        if rival.any():
            second = float(raw[rival].min())
            margin = (second - best_cost) / max(second, 1e-9)
            confidence *= 0.80 + 0.20 * min(1.0, max(0.0, margin))

        return MatchResult(
            position=position,
            confidence=confidence,
            cost=combined,
            matched_events=matched,
            tempo_ratio=speed,
            rhythm_score=rhythm,
            timestamp=float(t_in[-1]),
            n_observed=history_length,
        )
