import loeric.core.element as le
import loeric.core.tune as tu
from loeric.core.contours.bar import BarLengthContour
from loeric.core.contours.base import Contour, InvalidRecipeError
from loeric.core.contours.note import DurationContour, PitchContour
from loeric.core.contours.operations import (
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
)
from loeric.core.contours.phrase import PhraseContour
from loeric.core.contours.sampled import PatternContour, RandomContour
from loeric.core.contours.score import IntensityContour


def create_contour(
    tune: tu.Tune, contour_program: dict, key=None, parent=None
) -> Contour:
    """Programmatically create a contour given its definition.

    :param tune: the input tune for the contour.
    :param contour_program: the dictionary containing the contour definition.

    :return: the final assembled contour.
    """
    eval_dict = {
        "o_canainn": IntensityContour,
        "pitch": PitchContour,
        "duration": DurationContour,
        "pattern": PatternContour,
        "phrasing": PhraseContour,
        "bar_length": BarLengthContour,
        "random": RandomContour,
    }

    operation_dict = {
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

    if key is not None:
        key = key.split("#")[0]

    # check
    if key is None:
        c = list(contour_program.keys())
        if len(c) != 1:
            raise InvalidRecipeError(
                f"Only one contour can be provided. Make sure that 'recipe' in contour {parent} only has one item in the configuration file."
            )
        c = c[0]
        return create_contour(tune, contour_program[c], key=c, parent=parent)

    # create the contour, leaf
    elif key in eval_dict:
        contour = eval_dict[key]()
        contour.calculate(tune, **contour_program)
        return contour

    # aggregate calculated contours
    elif key in operation_dict:
        all_contours = []

        for c in contour_program["contours"]:
            all_contours.append(
                create_contour(
                    tune, contour_program["contours"][c], key=c, parent=parent
                )
            )

        program = contour_program.copy()
        program["contours"] = all_contours
        print(program)
        return operation_dict[key](**program)

    else:
        raise InvalidRecipeError(
            "Recipe argument {key} is invalid. Check your configuration file."
        )
