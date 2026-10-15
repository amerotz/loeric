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

import loeric.core.tune as tu
from loeric.core.contours.bar import BarLengthContour, BarLengthContourConfig
from loeric.core.contours.base import (
    LOERICContour,
    LOERICContourConfig,
    NotewiseContour,
)
from loeric.core.contours.note import (
    DurationContour,
    DurationContourConfig,
    PitchContour,
    PitchContourConfig,
)
from loeric.core.contours.operations import (
    ClampOperationContour,
    ClampOperationContourConfig,
    DivideOperationContour,
    DivideOperationContourConfig,
    LinearTransformOperationContour,
    LinearTransformOperationContourConfig,
    MultiplyOperationContour,
    MultiplyOperationContourConfig,
    PowerOperationContour,
    PowerOperationContourConfig,
    ScaleOperationContour,
    ScaleOperationContourConfig,
    ShiftOperationContour,
    ShiftOperationContourConfig,
    SmoothOperationContour,
    SmoothOperationContourConfig,
    ToMeanOperationContour,
    ToMeanOperationContourConfig,
    WeightedSumOperationContour,
    WeightedSumOperationContourConfig,
)
from loeric.core.contours.phrase import (
    ArchPhraseContour,
    ArchPhraseContourConfig,
    GesturePhraseContour,
    GesturePhraseContourConfig,
)
from loeric.core.contours.sampled import (
    PatternContour,
    PatternContourConfig,
    RandomContour,
    RandomContourConfig,
)
from loeric.core.contours.score import IntensityContour, IntensityContourConfig

__all__ = [
    LOERICContour,
    LOERICContourConfig,
    BarLengthContour,
    DurationContour,
    PitchContour,
    ClampOperationContour,
    DivideOperationContour,
    LinearTransformOperationContour,
    MultiplyOperationContour,
    PowerOperationContour,
    ScaleOperationContour,
    ShiftOperationContour,
    SmoothOperationContour,
    ToMeanOperationContour,
    WeightedSumOperationContour,
    ArchPhraseContour,
    GesturePhraseContour,
    RandomContour,
    IntensityContour,
]


def validate_config(config: dict):

    _registry = {
        "o_canainn": IntensityContour,
        "pitch": PitchContour,
        "duration": DurationContour,
        "pattern": PatternContour,
        "phrase_arch": ArchPhraseContour,
        "phrase_gesture": GesturePhraseContour,
        "bar_length": BarLengthContour,
        "random": RandomContour,
        "weighted_sum": WeightedSumOperationContour,
        "multiply": MultiplyOperationContour,
        "divide": DivideOperationContour,
        "linear": LinearTransformOperationContour,
        "shift": ShiftOperationContour,
        "to_mean": ToMeanOperationContour,
        "power": PowerOperationContour,
        "clamp": ClampOperationContour,
        "scale": ScaleOperationContour,
        "smooth": SmoothOperationContour,
    }
    # only one top level contour
    assert len(config) == 1

    key = list(config.keys())[0]
    cls_key = key.split("#")[0]
    cls = _registry.get(cls_key)

    if cls is None:
        raise ValueError(f"Invalid contour name '{cls_key}'.")

    # is it a leaf contour or operation?
    if issubclass(cls, NotewiseContour):
        # create leaf
        config = cls.config_class.model_validate(config[key])
        return config

    else:
        # create operation
        obj_configs = []
        items = config[key]["contours"].items()
        for obj_key, obj_val in items:
            obj_cfg = validate_config({obj_key: obj_val})
            obj_configs.append(obj_cfg)

        config[key]["contours"] = obj_configs
        config = cls.config_class.model_validate(config[key])

        return config


def create_contour(tune: tu.Tune, contour_program: dict) -> LOERICContour:
    """Programmatically create a contour given its definition.

    :param tune: the input tune for the contour.
    :param contour_program: the dictionary containing the contour definition.

    :return: the final assembled contour.
    """
    _registry = {
        IntensityContourConfig: IntensityContour,
        PitchContourConfig: PitchContour,
        DurationContourConfig: DurationContour,
        PatternContourConfig: PatternContour,
        ArchPhraseContourConfig: ArchPhraseContour,
        GesturePhraseContourConfig: GesturePhraseContour,
        BarLengthContourConfig: BarLengthContour,
        RandomContourConfig: RandomContour,
        WeightedSumOperationContourConfig: WeightedSumOperationContour,
        MultiplyOperationContourConfig: MultiplyOperationContour,
        DivideOperationContourConfig: DivideOperationContour,
        ShiftOperationContourConfig: ShiftOperationContour,
        ToMeanOperationContourConfig: ToMeanOperationContour,
        PowerOperationContourConfig: PowerOperationContour,
        ClampOperationContourConfig: ClampOperationContour,
        ScaleOperationContourConfig: ScaleOperationContour,
        SmoothOperationContourConfig: SmoothOperationContour,
        LinearTransformOperationContourConfig: LinearTransformOperationContour,
    }

    # validate
    cls = _registry.get(type(contour_program))
    if cls is None:
        raise ValueError(f"Invalid contour name '{contour_program}'.")

    # is it a leaf contour or operation?
    if issubclass(cls, NotewiseContour):
        # create leaf
        obj = cls(**contour_program.model_dump())
        obj.calculate(tune)
        return obj

    else:
        # create operation
        objs = []
        for c in contour_program.contours:
            obj = create_contour(tune, c)
            objs.append(obj)

        contour_program = contour_program.model_dump()
        contour_program["contours"] = objs

        return cls(**contour_program)
