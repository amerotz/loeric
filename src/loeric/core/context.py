from contextlib import contextmanager
from contextvars import ContextVar

import loeric.core.element as le


class LOERICContext:

    def __init__(self):
        self.tick = le.TimeDelta(0)
        self.tune = None
        self.tempo = None


_CURRENT_CONTEXT = ContextVar("loeric_context", default=None)


def get_context():
    context = _CURRENT_CONTEXT.get()

    if context is None:
        raise RuntimeError("No active LOERIC context.")

    return context


@contextmanager
def activate_context(context):
    token = _CURRENT_CONTEXT.set(context)
    try:
        yield
    finally:
        _CURRENT_CONTEXT.reset(token)


##################################################


class PerformanceClock:

    @staticmethod
    def set(tick):
        get_context().tick = le.TimeDelta(tick)

    @staticmethod
    def now() -> le.TimeDelta:
        return get_context().tick


class CurrentTune:

    @staticmethod
    def set(tune):
        get_context().tune = tune

    @staticmethod
    def get():
        return get_context().tune


class TempoKeeper:

    @staticmethod
    def set(tempo):
        get_context().tempo = tempo

    @staticmethod
    def get() -> le.Tempo:
        context = get_context()
        return le.Tempo(qpm=context.tempo, time=context.tick)
