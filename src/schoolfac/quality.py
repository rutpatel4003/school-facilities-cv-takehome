from __future__ import annotations

from .schema import SchoolVisualAssessment


OBSERVABILITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _cap_observability(value: str, maximum: str) -> str:
    if OBSERVABILITY_RANK[value] <= OBSERVABILITY_RANK[maximum]:
        return value
    return maximum


def boundary_is_uncertain(assessment: SchoolVisualAssessment) -> bool:
    return (
        assessment.campus_boundary_ambiguity
        or assessment.campus_boundary_observability in {"low", "none"}
    )


def apply_quality_control(
    assessment: SchoolVisualAssessment,
) -> tuple[SchoolVisualAssessment, list[str]]:
    """Remove unsupported claims and record each adjustment."""
    result = assessment.model_copy(deep=True)
    notes: list[str] = []

    if result.solar.present_observability == "none" and result.solar.present is not None:
        result.solar.present = None
        notes.append("Solar presence cleared because observability was none.")
    if result.portables.observability == "none" and result.portables.count is not None:
        result.portables.count = None
        notes.append("Portable count cleared because observability was none.")
    if result.fence.extent_observability == "none" and result.fence.extent != "unmeasurable":
        result.fence.extent = "unmeasurable"
        notes.append("Fence extent changed to unmeasurable because observability was none.")

    athletics = result.athletics
    observable_values = [
        ("track_observability", "track_present", "Track presence"),
        ("fields_observability", "sports_fields_count", "Sports-field count"),
        ("courts_observability", "hard_courts_count", "Hard-court count"),
        ("pool_observability", "pool_present", "Pool presence"),
    ]
    for observability_attr, value_attr, label in observable_values:
        if (
            getattr(athletics, observability_attr) == "none"
            and getattr(athletics, value_attr) is not None
        ):
            setattr(athletics, value_attr, None)
            notes.append(f"{label} cleared because observability was none.")

    # The task asks for rooftop solar only.
    solar = result.solar
    rooftop = [
        array
        for array in solar.arrays
        if array.mounting_context == "rooftop"
        and array.mounting_observability in {"high", "medium"}
    ]
    excluded = [
        array
        for array in solar.arrays
        if array.mounting_context in {"canopy", "ground"}
    ]
    uncertain = [
        array
        for array in solar.arrays
        if array.mounting_context == "uncertain"
        or array.mounting_observability in {"low", "none"}
    ]

    if solar.present is True:
        if rooftop:
            solar.arrays = rooftop
            if excluded:
                notes.append(
                    f"Excluded {len(excluded)} non-rooftop solar candidate(s) from rooftop area."
                )
        else:
            solar.present = None
            solar.arrays = []
            solar.present_observability = _cap_observability(
                solar.present_observability,
                "low",
            )
            solar.area_observability = "none"
            solar.ambiguity = True
            reason = "uncertain mounting context" if uncertain else "no supported rooftop array"
            notes.append(
                f"Rooftop solar changed to unmeasurable: {reason}."
            )
    elif solar.present is False and rooftop:
        solar.present = None
        solar.arrays = []
        solar.present_observability = _cap_observability(
            solar.present_observability,
            "low",
        )
        solar.area_observability = "none"
        solar.ambiguity = True
        notes.append(
            "Rooftop solar changed to unmeasurable because presence and "
            "candidate context conflicted."
        )
    elif solar.present is not True:
        solar.arrays = []

    # Fence absence needs a visible, attributable perimeter.
    if (
        result.fence.extent == "none"
        and (
            boundary_is_uncertain(result)
            or result.fence.ambiguity
            or result.fence.extent_observability != "high"
        )
    ):
        result.fence.extent = "unmeasurable"
        result.fence.extent_observability = _cap_observability(
            result.fence.extent_observability,
            "low",
        )
        result.fence.ambiguity = True
        notes.append(
            "Fence extent changed from none to unmeasurable because the visible "
            "perimeter was insufficient."
        )
    elif result.fence.extent == "none":
        capped_observability = _cap_observability(
            result.fence.extent_observability,
            "low",
        )
        if capped_observability != result.fence.extent_observability:
            result.fence.extent_observability = capped_observability
            notes.append(
                "Fence-absence observability capped at low because thin fencing "
                "may be unresolved in aerial imagery."
            )

    if (
        result.fence.type_observability in {"low", "none"}
        and result.fence.dominant_type != "unknown"
    ):
        result.fence.dominant_type = "unknown"
        notes.append("Fence type changed to unknown because material was not observable.")

    return result, notes
