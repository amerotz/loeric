import loeric.core.element as le
import loeric.core.module.base as lmb


class SwingConfig(lmb.ModuleConfig):
    """Config for :class:`SwingModule`.

    :param bind: contour name controlling swing ratio.
    :param min: minimum swing ratio.
    :param max: maximum swing ratio.
    :param locations: beat positions (in eighths) where swing is applied.
    """

    bind: str
    min: float = 1.0
    max: float = 1.0
    locations: list[int] = [0]


class SwingModule(lmb.LOERICModule):

    config_class = SwingConfig

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

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Apply swing.

        :param element: the element to process.
        """
        if isinstance(element, le.Note) or isinstance(element, le.Pause):
            x = element.time

            # is it an eight note?
            right_duration = element.duration == 1

            # is it the right place?
            current_location = int(
                (x % (self._time_signature.eighths_per_bar)).eighth_duration
            )
            right_location = current_location in self._locations

            perc = self._contour_values[self._contour]
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

            element.duration = new_duration

        return [element]
