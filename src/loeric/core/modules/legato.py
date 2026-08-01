import loeric.core.element as le
import loeric.core.modules.base as lmb


class LegatoConfig(lmb.ModuleConfig):
    """Config for :class:`LegatoModule`.

    :param bind: contour name controlling legato amount.
    :param min: minimum legato multiplier.
    :param max: maximum legato multiplier.
    """

    bind: str
    min: float
    max: float


class LegatoModule(lmb.LOERICModule):

    config_class = LegatoConfig

    def __init__(self, min: float, max: float, bind: str, **kwargs):
        super().__init__(**kwargs)

        self._name = "legato"
        self._legato_amount = max - min
        self._min_legato = min
        self._contour = bind
        self._is_online = True

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Apply legato.

        :param element: the element to process.
        """
        if isinstance(element, le.Note):
            element.duration *= (
                self._min_legato
                + self._legato_amount * self._contour_values[self._contour]
            )
        return [element]
