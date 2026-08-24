"""Objects representing LOERIC's mapper rule nodes."""

from dataclasses import dataclass

import pydantic as pdt


@dataclass(frozen=True)
class LOERICRuleObject(pdt.BaseModel):
    """Base object."""

    pass


######## Base Cases ########


@dataclass(frozen=True)
class MapperRange(LOERICRuleObject):
    """A range of values."""

    a: float
    b: float


@dataclass(frozen=True)
class Source(LOERICRuleObject):
    """A value source."""

    pass


@dataclass(frozen=True)
class Target(LOERICRuleObject):
    """A target for values."""

    pass


@dataclass(frozen=True)
class ContourSource(Source):
    """A contour source."""

    name: str


@dataclass(frozen=True)
class ContourTarget(Target):
    """A contour target."""

    name: str


@dataclass(frozen=True)
class Constant(LOERICRuleObject):
    """A constant value."""

    value: float


######## Nested Objects ########


@dataclass(frozen=True)
class HumanImpactTarget(Target):
    """A target which is the human impact value (autonomy) of a source."""

    source: ContourSource


@dataclass(frozen=True)
class ProcessedSource(Source):
    """A contour source which has been modulated."""

    source: ContourSource


@dataclass(frozen=True)
class LOERICPreProcessRule(LOERICRuleObject):
    """A preprocessing rule."""

    pass


@dataclass(frozen=True)
class MapperSelector(LOERICPreProcessRule):
    """A range selection rule."""

    source: ContourSource
    range: MapperRange


@dataclass(frozen=True)
class MapperRemapper(LOERICPreProcessRule):
    """A range remapping rule."""

    source: Source | LOERICPreProcessRule
    source_range: MapperRange
    target_range: MapperRange


@dataclass(frozen=True)
class MapperModulator(LOERICRuleObject):
    """A modulation rule."""

    source: Source | MapperSelector
    targets: list[ContourTarget]


@dataclass(frozen=True)
class MapperRouter(LOERICRuleObject):
    """A routing rule."""

    source: Source | Constant
    targets: list[Target]
