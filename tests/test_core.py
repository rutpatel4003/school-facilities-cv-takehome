from pathlib import Path
import sys

import pandas as pd
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from schoolfac.confidence import calibrated_band
from schoolfac.geo import make_geodesic_bbox
from schoolfac.io_utils import MEASUREMENT_COLUMNS
from schoolfac.quality import apply_quality_control
from schoolfac.report import summarize_run
from schoolfac.schema import SchoolVisualAssessment
from schoolfac.solar import estimate_solar_area_m2
from schoolfac.tiles import create_multiscale_views
from schoolfac.validate import (
    _calibration_error,
    _normalize_value,
    _validate_predictions,
    _validate_truth_labels,
)
from schoolfac.vlm import PROMPT_TEMPLATE, PROMPT_VERSION


def test_geodesic_bbox_contains_center():
    lat, lon = 34.05, -118.25
    west, south, east, north = make_geodesic_bbox(lat, lon, 350)
    assert west < lon < east
    assert south < lat < north


def test_confidence_drops_for_ambiguity():
    clear = calibrated_band("high")
    ambiguous = calibrated_band("high", ambiguity=True)
    assert clear == 0.90
    assert ambiguous == 0.70


def test_unvalidated_solar_area_stays_in_review_band():
    assert calibrated_band("high", area_estimate=True) == 0.40


def test_multiscale_views_include_center_detail(tmp_path):
    overview = tmp_path / "overview.png"
    Image.new("RGB", (100, 80), color=(120, 140, 160)).save(overview)

    views = create_multiscale_views(overview, tmp_path / "views")
    labels = [label for label, _ in views]

    assert labels == ["FULL_OVERVIEW", "CENTER_DETAIL", "NW", "NE", "SW", "SE"]
    with Image.open(tmp_path / "views" / "center.jpg") as center:
        assert center.size == (70, 56)


def test_solar_prompt_requires_positive_rooftop_proof():
    assert PROMPT_VERSION == "2026-09-03-solar-roof-proof-v2"
    assert "ONLY when the entire panel footprint is" in PROMPT_TEMPLATE
    assert "roof boundary cannot be traced" in PROMPT_TEMPLATE
    assert "set solar.present to true ONLY if" in PROMPT_TEMPLATE


def test_solar_area_uses_georeferenced_pixel_area():
    assessment = SchoolVisualAssessment.model_validate(
        {
            "campus_coverage_visible": 1.0,
            "campus_boundary_observability": "high",
            "campus_boundary_ambiguity": False,
            "overall_image_quality": "good",
            "tree_occlusion": "low",
            "solar": {
                "present": True,
                "present_observability": "high",
                "area_observability": "high",
                "arrays": [
                    {
                        "bbox_norm": [100, 100, 300, 200],
                        "panel_fill_fraction": 0.5,
                        "mounting_context": "rooftop",
                        "mounting_observability": "high",
                    }
                ],
                "ambiguity": False,
                "evidence": "test",
            },
            "portables": {
                "count": 0,
                "observability": "high",
                "ambiguity": False,
                "evidence": "test",
            },
            "fence": {
                "extent": "none", "extent_observability": "high",
                "dominant_type": "unknown", "type_observability": "none",
                "ambiguity": False, "evidence": "test"
            },
            "athletics": {
                "track_present": False, "track_observability": "high",
                "sports_fields_count": 0, "fields_observability": "high",
                "hard_courts_count": 0, "courts_observability": "high",
                "pool_present": False, "pool_observability": "high",
                "ambiguity": False, "evidence": "test"
            },
            "global_notes": "",
        }
    )
    area, issues = estimate_solar_area_m2(
        assessment,
        {"width_px": 1000, "height_px": 1000, "pixel_area_m2": 1.0},
    )
    assert area == 10_000.0
    assert issues == []


def _assessment_with_overrides(**overrides):
    payload = {
        "campus_coverage_visible": 1.0,
        "campus_boundary_observability": "low",
        "campus_boundary_ambiguity": True,
        "overall_image_quality": "good",
        "tree_occlusion": "low",
        "solar": {
            "present": False,
            "present_observability": "high",
            "area_observability": "none",
            "arrays": [],
            "ambiguity": False,
            "evidence": "test",
        },
        "portables": {
            "count": 0,
            "observability": "high",
            "ambiguity": False,
            "evidence": "test",
        },
        "fence": {
            "extent": "none",
            "extent_observability": "medium",
            "dominant_type": "unknown",
            "type_observability": "none",
            "ambiguity": True,
            "evidence": "test",
        },
        "athletics": {
            "track_present": False,
            "track_observability": "high",
            "sports_fields_count": 0,
            "fields_observability": "high",
            "hard_courts_count": 0,
            "courts_observability": "high",
            "pool_present": False,
            "pool_observability": "high",
            "ambiguity": False,
            "evidence": "test",
        },
        "global_notes": "",
    }
    payload.update(overrides)
    return SchoolVisualAssessment.model_validate(payload)


def test_fence_none_requires_observable_boundary():
    controlled, notes = apply_quality_control(_assessment_with_overrides())
    assert controlled.fence.extent == "unmeasurable"
    assert controlled.fence.extent_observability == "low"
    assert any("Fence extent" in note for note in notes)


def test_observable_fence_absence_is_retained_but_confidence_is_capped():
    assessment = _assessment_with_overrides(
        campus_boundary_observability="high",
        campus_boundary_ambiguity=False,
        fence={
            "extent": "none",
            "extent_observability": "high",
            "dominant_type": "unknown",
            "type_observability": "none",
            "ambiguity": False,
            "evidence": "Most perimeter segments appear open.",
        },
    )

    controlled, notes = apply_quality_control(assessment)

    assert controlled.fence.extent == "none"
    assert controlled.fence.extent_observability == "low"
    assert any("Fence-absence observability" in note for note in notes)


def test_non_rooftop_solar_is_not_counted_as_rooftop():
    assessment = _assessment_with_overrides(
        solar={
            "present": True,
            "present_observability": "high",
            "area_observability": "high",
            "arrays": [
                {
                    "bbox_norm": [100, 100, 300, 200],
                    "panel_fill_fraction": 0.8,
                    "mounting_context": "canopy",
                    "mounting_observability": "high",
                }
            ],
            "ambiguity": False,
            "evidence": "test",
        }
    )
    controlled, notes = apply_quality_control(assessment)
    assert controlled.solar.present is None
    assert controlled.solar.arrays == []
    assert controlled.solar.present_observability == "low"
    assert any("Rooftop solar" in note for note in notes)


def test_validation_rejects_unsupported_fence_type():
    rows = []
    for index in range(9):
        rows.append(
            {
                "school_id": f"{index:012d}",
                "school_name": f"School {index}",
                "solar_present": "",
                "solar_area_m2": "",
                "portable_count": "",
                "fence_extent": "",
                "fence_type": "mixed" if index == 0 else "",
                "track_present": "",
                "sports_fields_count": "",
                "hard_courts_count": "",
                "pool_present": "",
                "ground_truth_notes": "",
                "excluded_fields": "",
                "evaluation_exclusion_reason": "",
                "sample_role": "seeded_random",
            }
        )

    with pytest.raises(ValueError, match="Invalid fence_type"):
        _validate_truth_labels(pd.DataFrame(rows))


def test_validation_normalizes_wrought_iron_spelling():
    assert _normalize_value("fence_type", "wrought iron") == "wrought-iron"
    assert _normalize_value("fence_type", "wrought-iron") == "wrought-iron"


def test_calibration_error_uses_fixed_confidence_bands():
    observations = pd.DataFrame(
        {
            "confidence": [0.9, 0.9, 0.4, 0.4],
            "correct": [1, 1, 0, 0],
        }
    )
    expected, maximum = _calibration_error(observations)
    assert expected == pytest.approx(0.25)
    assert maximum == pytest.approx(0.40)


def test_prediction_validation_rejects_out_of_range_confidence():
    row = {column: None for column in MEASUREMENT_COLUMNS}
    row.update(
        {
            "school_id": "000000000001",
            "school_name": "Test School",
            "solar_present_confidence": 1.2,
            "solar_area_m2_confidence": 0.4,
            "portable_count_confidence": 0.4,
            "fence_extent_confidence": 0.4,
            "fence_type_confidence": 0.4,
            "track_present_confidence": 0.4,
            "sports_fields_count_confidence": 0.4,
            "hard_courts_count_confidence": 0.4,
            "pool_present_confidence": 0.4,
            "review_required": True,
        }
    )
    with pytest.raises(ValueError, match="solar_present_confidence"):
        _validate_predictions(pd.DataFrame([row]))


def test_validation_exclusions_require_known_labeled_fields_and_a_reason():
    rows = []
    for index in range(9):
        rows.append(
            {
                "school_id": f"{index:012d}",
                "school_name": f"School {index}",
                "solar_present": "TRUE" if index == 0 else "",
                "solar_area_m2": 100 if index == 0 else "",
                "portable_count": "",
                "fence_extent": "",
                "fence_type": "",
                "track_present": "",
                "sports_fields_count": "",
                "hard_courts_count": "",
                "pool_present": "",
                "ground_truth_notes": "",
                "excluded_fields": "solar_present;solar_area_m2" if index == 0 else "",
                "evaluation_exclusion_reason": "Imagery dates do not match." if index == 0 else "",
                "sample_role": "seeded_random",
            }
        )

    _validate_truth_labels(pd.DataFrame(rows))

    rows[0]["evaluation_exclusion_reason"] = ""
    with pytest.raises(ValueError, match="evaluation_exclusion_reason"):
        _validate_truth_labels(pd.DataFrame(rows))

    rows[0]["evaluation_exclusion_reason"] = "Imagery dates do not match."
    rows[0]["excluded_fields"] = "not_a_field"
    with pytest.raises(ValueError, match="Unknown excluded_fields"):
        _validate_truth_labels(pd.DataFrame(rows))


def test_summary_can_price_saved_token_counts(tmp_path):
    diagnostics = tmp_path / "diagnostics.csv"
    pd.DataFrame(
        [
            {
                "total_seconds": 10,
                "review_required": False,
                "prompt_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "estimated_api_cost_usd": 999.0,
            }
        ]
    ).to_csv(diagnostics, index=False)

    text = summarize_run(
        diagnostics,
        tmp_path / "summary.txt",
        input_usd_per_1m=0.75,
        output_usd_per_1m=3.75,
    )

    assert "Mean estimated VLM cost/school: $4.500000" in text


def test_summary_prices_reported_thinking_tokens(tmp_path):
    diagnostics = tmp_path / "diagnostics.csv"
    pd.DataFrame(
        [
            {
                "total_seconds": 10,
                "review_required": False,
                "prompt_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "thinking_tokens": 2_000_000,
                "billable_output_tokens": 3_000_000,
                "estimated_api_cost_usd": None,
            }
        ]
    ).to_csv(diagnostics, index=False)

    text = summarize_run(
        diagnostics,
        tmp_path / "summary.txt",
        input_usd_per_1m=1.0,
        output_usd_per_1m=2.0,
    )

    assert "Mean billable output tokens/school (including thinking when reported): 3000000" in text
    assert "Mean estimated VLM cost/school: $7.000000" in text
