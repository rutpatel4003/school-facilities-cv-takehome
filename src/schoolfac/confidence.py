from __future__ import annotations


BASE_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
RANK_TO_CONFIDENCE = {0: 0.10, 1: 0.40, 2: 0.70, 3: 0.90}


def calibrated_band(
    observability: str,
    *,
    ambiguity: bool = False,
    campus_review_required: bool = False,
    imagery_coverage_fraction: float = 1.0,
    absence_or_complete_count: bool = False,
    area_estimate: bool = False,
) -> float:
    """Map evidence quality to one of four confidence bands."""
    if observability not in BASE_RANK:
        raise ValueError(f"Unknown observability: {observability}")

    rank = BASE_RANK[observability]
    penalties = 0

    if ambiguity:
        penalties += 1
    if campus_review_required:
        penalties += 1

    if (
        absence_or_complete_count
        and imagery_coverage_fraction < 0.99
    ):
        penalties += 1
    elif imagery_coverage_fraction < 0.95:
        penalties += 1

    rank = max(0, rank - penalties)

    if area_estimate:
        rank = min(rank, 1)

    return RANK_TO_CONFIDENCE[rank]
