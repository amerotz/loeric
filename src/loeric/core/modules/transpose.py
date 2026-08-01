import loeric.core.element as le
import loeric.core.modules.base as lmb
import loeric.core.paths as lp


class TransposeConfig(lmb.ModuleConfig):
    """Config for :class:`TransposeModule`.

    :param steps: number of semitones to transpose (may be fractional).
    """

    steps: float = 0.0


@lp.expose("_steps", "steps")
class TransposeModule(lmb.LOERICModule):

    config_class = TransposeConfig

    def __init__(self, steps: float, **kwargs):
        super().__init__(**kwargs)

        self._steps = steps
        self._name = "transpose"

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Transpose notes.

        :param element: the element to process.
        """
        if (
            isinstance(element, le.Note)
            or isinstance(element, le.Chord)
            or isinstance(element, le.KeySignature)
        ):
            element.transpose(self._steps)
        return [element]
