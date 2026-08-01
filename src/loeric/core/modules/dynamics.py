import loeric.core.element as le
import loeric.core.modules.base as lmb
import loeric.core.paths as lp


class DynamicsConfig(lmb.ModuleConfig):
    """Config for :class:`DynamicsModule`.

    :param bind: contour name controlling velocity.
    :param pattern: contour name for the velocity pattern multiplier.
    """

    bind: str
    pattern: str | None = None


@lp.expose("_contour", "bind")
@lp.expose("_pattern", "pattern")
class DynamicsModule(lmb.LOERICModule):

    config_class = DynamicsConfig

    def __init__(self, bind: str, pattern: str, **kwargs):
        super().__init__(**kwargs)

        self._contour = bind
        self._pattern = pattern
        self._name = "dynamics"
        self._is_online = True

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Apply dynamics.

        :param element: the element to process.
        """
        if isinstance(element, le.Note):
            element.velocity = self._contour_values[self._contour]
            if self._pattern is not None:
                element.velocity *= self._contour_values[self._pattern]
        return [element]
