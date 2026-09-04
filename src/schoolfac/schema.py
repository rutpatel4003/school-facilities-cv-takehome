from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


Observability = Literal["high", "medium", "low", "none"]
FenceExtent = Literal["full", "partial", "none", "unmeasurable"]
FenceType = Literal["chain-link", "wrought iron", "wall", "other", "unknown"]
SolarMountingContext = Literal["rooftop", "canopy", "ground", "uncertain"]


class SolarArray(BaseModel):
    """One visually distinct solar candidate localized on the FULL overview."""

    bbox_norm: list[int] = Field(
        description=(
            "[x_min, y_min, x_max, y_max] on the FULL_OVERVIEW image, each "
            "integer from 0 to 1000. Boxes should be non-overlapping."
        ),
        min_length=4,
        max_length=4,
    )
    panel_fill_fraction: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Approximate fraction of the bounding rectangle actually covered "
            "by solar panels, discounting gaps and empty roof."
        ),
    )
    mounting_context: SolarMountingContext = Field(
        description=(
            "Physical support under the panels: rooftop, canopy/carport, "
            "ground-mounted, or uncertain."
        )
    )
    mounting_observability: Observability = Field(
        description="How clearly the imagery distinguishes the mounting context."
    )


class SolarAssessment(BaseModel):
    present: bool | None = Field(
        description=(
            "Whether rooftop solar is present. Canopy/carport and ground-mounted "
            "solar do not count. Use null if mounting context is unresolved."
        )
    )
    present_observability: Observability
    area_observability: Observability
    arrays: list[SolarArray] = Field(default_factory=list)
    ambiguity: bool = False
    evidence: str


class PortablesAssessment(BaseModel):
    count: int | None = Field(
        ge=0,
        description="Distinct portable/modular classroom-type buildings.",
    )
    observability: Observability
    ambiguity: bool = False
    evidence: str


class FenceAssessment(BaseModel):
    extent: FenceExtent
    extent_observability: Observability
    dominant_type: FenceType
    type_observability: Observability
    ambiguity: bool = False
    evidence: str


class AthleticsAssessment(BaseModel):
    track_present: bool | None
    track_observability: Observability
    sports_fields_count: int | None = Field(ge=0)
    fields_observability: Observability
    hard_courts_count: int | None = Field(ge=0)
    courts_observability: Observability
    pool_present: bool | None
    pool_observability: Observability
    ambiguity: bool = False
    evidence: str


class SchoolVisualAssessment(BaseModel):
    campus_coverage_visible: float = Field(
        ge=0.0,
        le=1.0,
        description="Estimated fraction of the apparent school campus visible in the imagery.",
    )
    campus_boundary_observability: Observability = Field(
        description=(
            "How clearly the target school's campus perimeter/ownership can be "
            "distinguished from neighboring parcels and shared facilities."
        )
    )
    campus_boundary_ambiguity: bool = Field(
        description=(
            "True when one or more crop features cannot be confidently attributed "
            "to the target school because campus extent is uncertain."
        )
    )
    overall_image_quality: Literal["good", "moderate", "poor"]
    tree_occlusion: Literal["low", "medium", "high"]
    solar: SolarAssessment
    portables: PortablesAssessment
    fence: FenceAssessment
    athletics: AthleticsAssessment
    global_notes: str = ""
