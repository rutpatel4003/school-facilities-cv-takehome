from __future__ import annotations

from datetime import date
from pathlib import Path
import json
from time import perf_counter

import pandas as pd

from .campus import load_campus_review, resolve_center
from .confidence import calibrated_band
from .costs import estimate_api_cost_usd
from .imagery import fetch_naip_chip
from .io_utils import MEASUREMENT_COLUMNS, load_schools
from .quality import apply_quality_control, boundary_is_uncertain
from .solar import estimate_solar_area_m2
from .tiles import create_multiscale_views
from .vlm import GeminiExtractor, MockExtractor


def _imagery_age_years(acquisition_date: str, as_of: date | None = None) -> float:
    acquired = date.fromisoformat(acquisition_date)
    reference = as_of or date.today()
    return max(0.0, (reference - acquired).days / 365.2425)


def _review_lookup(review_df: pd.DataFrame) -> dict[str, dict]:
    if review_df.empty:
        return {}
    return {
        str(row["school_id"]): row
        for row in review_df.to_dict("records")
    }


def _failure_row(school_id: str, school_name: str, error_msg: str) -> dict:
    return {
        "school_id": school_id,
        "school_name": school_name,
        "imagery_date": None,
        "solar_present": None,
        "solar_present_confidence": 0.10,
        "solar_area_m2": None,
        "solar_area_m2_confidence": 0.10,
        "portable_count": None,
        "portable_count_confidence": 0.10,
        "fence_extent": "unmeasurable",
        "fence_extent_confidence": 0.10,
        "fence_type": "unknown",
        "fence_type_confidence": 0.10,
        "track_present": None,
        "track_present_confidence": 0.10,
        "sports_fields_count": None,
        "sports_fields_count_confidence": 0.10,
        "hard_courts_count": None,
        "hard_courts_count_confidence": 0.10,
        "pool_present": None,
        "pool_present_confidence": 0.10,
        "review_required": True,
        "failure_notes": f"Pipeline error: {error_msg}",
    }


def fetch_all_imagery(settings, force: bool = False, limit: int | None = None) -> None:
    schools = load_schools(settings.schools_csv)
    review = _review_lookup(load_campus_review(settings.campus_review_csv))
    if limit:
        schools = schools.head(limit)

    for school in schools.to_dict("records"):
        sid = str(school["school_id"])
        center = resolve_center(
            school,
            review.get(sid),
            settings.default_chip_half_size_m,
        )
        school_dir = settings.imagery_dir / sid
        print(f"[{sid}] fetching NAIP around {center['method']} center...")
        meta = fetch_naip_chip(
            center["latitude"],
            center["longitude"],
            center["half_size_m"],
            school_dir / "overview.png",
            school_dir / "overview.json",
            max_side_px=settings.max_image_side_px,
            force=force,
        )
        print(
            f"    {meta['acquisition_date']} | {meta['width_px']}x{meta['height_px']} | "
            f"coverage={meta['stac_bbox_coverage_fraction']:.2f}"
        )


def _make_extractor(settings, provider: str):
    if provider == "gemini":
        return GeminiExtractor(settings.gemini_api_key, settings.gemini_model)
    if provider == "mock":
        return MockExtractor()
    raise ValueError(f"Unsupported provider: {provider}")


def _process_one_school(
    school: dict,
    sid: str,
    settings,
    extractor,
    review: dict[str, dict],
    force_imagery: bool,
    raw_dir: Path,
) -> tuple[dict, dict]:
    failure_notes: list[str] = []

    center = resolve_center(
        school,
        review.get(sid),
        settings.default_chip_half_size_m,
    )
    print(
        "  Campus:"
        f" method={center['method']},"
        f" lat={center['latitude']:.6f},"
        f" lon={center['longitude']:.6f},"
        f" half_size={center['half_size_m']:.0f}m",
        flush=True,
    )
    if center["review_required"]:
        failure_notes.append("Campus coordinate was not manually reviewed; confidences capped.")

    school_dir = settings.imagery_dir / sid
    print("  Imagery: loading/fetching NAIP chip...", flush=True)
    imagery_t0 = perf_counter()
    meta = fetch_naip_chip(
        center["latitude"],
        center["longitude"],
        center["half_size_m"],
        school_dir / "overview.png",
        school_dir / "overview.json",
        max_side_px=settings.max_image_side_px,
        force=force_imagery,
    )
    imagery_seconds = perf_counter() - imagery_t0
    print(
        f"  Imagery: done in {imagery_seconds:.1f}s"
        f" | date={meta['acquisition_date']}"
        f" | coverage={meta.get('stac_bbox_coverage_fraction', 1.0):.2f}",
        flush=True,
    )
    imagery_age_years = _imagery_age_years(meta["acquisition_date"])
    imagery_is_stale = imagery_age_years > settings.stale_imagery_years
    if imagery_is_stale:
        failure_notes.append(
            f"Imagery is {imagery_age_years:.1f} years old; current facilities may differ."
        )

    print(
        "  Views: creating overview + centered detail + quadrant crops...",
        flush=True,
    )
    views = create_multiscale_views(
        school_dir / "overview.png",
        school_dir / "views",
    )
    print(f"  Views: prepared {len(views)} image view(s)", flush=True)

    model_name = getattr(extractor, "model", "unknown")
    print(f"  VLM: calling {model_name}...", flush=True)
    vlm_t0 = perf_counter()
    result = extractor.extract(school, views, meta)
    vlm_seconds = perf_counter() - vlm_t0
    print(
        f"  VLM: completed in {vlm_seconds:.1f}s"
        f" | input_tokens={result.usage.prompt_tokens}"
        f" | output_tokens={result.usage.output_tokens}"
        f" | thinking_tokens={result.usage.thinking_tokens}",
        flush=True,
    )
    model_assessment = result.assessment
    a, quality_notes = apply_quality_control(model_assessment)
    failure_notes.extend(quality_notes)

    solar_area, solar_issues = estimate_solar_area_m2(a, meta)
    failure_notes.extend(solar_issues)

    coverage = min(
        float(meta.get("stac_bbox_coverage_fraction", 1.0)),
        float(a.campus_coverage_visible),
    )
    campus_review_required = bool(center["review_required"])
    campus_boundary_uncertain = boundary_is_uncertain(a)

    solar_present_conf = calibrated_band(
        a.solar.present_observability,
        ambiguity=a.solar.ambiguity,
        campus_review_required=campus_review_required,
        imagery_coverage_fraction=coverage,
        absence_or_complete_count=(a.solar.present is False),
    )
    # Positive solar still needs mounting-context review.
    if a.solar.present is True:
        solar_present_conf = min(solar_present_conf, 0.70)
    if a.solar.present is False:
        solar_area_conf = solar_present_conf
    else:
        solar_area_conf = calibrated_band(
            a.solar.area_observability,
            ambiguity=a.solar.ambiguity or bool(solar_issues),
            campus_review_required=campus_review_required,
            imagery_coverage_fraction=coverage,
            area_estimate=True,
        )
    portable_conf = calibrated_band(
        a.portables.observability,
        ambiguity=a.portables.ambiguity or campus_boundary_uncertain,
        campus_review_required=campus_review_required,
        imagery_coverage_fraction=coverage,
        absence_or_complete_count=True,
    )
    fence_extent_conf = calibrated_band(
        a.fence.extent_observability,
        ambiguity=a.fence.ambiguity or campus_boundary_uncertain,
        campus_review_required=campus_review_required,
        imagery_coverage_fraction=coverage,
        absence_or_complete_count=True,
    )
    fence_type_conf = calibrated_band(
        a.fence.type_observability,
        ambiguity=a.fence.ambiguity or a.fence.dominant_type == "unknown",
        campus_review_required=campus_review_required,
        imagery_coverage_fraction=coverage,
    )

    ath = a.athletics
    track_conf = calibrated_band(
        ath.track_observability,
        ambiguity=ath.ambiguity or campus_boundary_uncertain,
        campus_review_required=campus_review_required,
        imagery_coverage_fraction=coverage,
        absence_or_complete_count=ath.track_present is False,
    )
    fields_conf = calibrated_band(
        ath.fields_observability,
        ambiguity=ath.ambiguity or campus_boundary_uncertain,
        campus_review_required=campus_review_required,
        imagery_coverage_fraction=coverage,
        absence_or_complete_count=True,
    )
    fields_conf = min(fields_conf, 0.70)
    courts_conf = calibrated_band(
        ath.courts_observability,
        ambiguity=ath.ambiguity or campus_boundary_uncertain,
        campus_review_required=campus_review_required,
        imagery_coverage_fraction=coverage,
        absence_or_complete_count=True,
    )
    courts_conf = min(courts_conf, 0.70)
    pool_conf = calibrated_band(
        ath.pool_observability,
        ambiguity=ath.ambiguity or campus_boundary_uncertain,
        campus_review_required=campus_review_required,
        imagery_coverage_fraction=coverage,
        absence_or_complete_count=ath.pool_present is False,
    )

    core_confidences = [
        solar_present_conf,
        portable_conf,
        fence_extent_conf,
        fence_type_conf,
        track_conf,
        fields_conf,
        courts_conf,
        pool_conf,
    ]

    if a.solar.present is True:
        core_confidences.append(solar_area_conf)

    review_required = (
        campus_review_required
        or campus_boundary_uncertain
        or imagery_is_stale
        or a.solar.present is True
        or any(c <= 0.40 for c in core_confidences)
    )
    if a.solar.present is True:
        failure_notes.append(
            "Positive rooftop-solar detection requires mounting-context review."
        )
    if campus_boundary_uncertain:
        failure_notes.append(
            "Campus boundary/feature ownership was not clearly observable."
        )
    if a.tree_occlusion == "high":
        failure_notes.append("High tree occlusion reported by VLM.")
    if coverage < 0.95:
        failure_notes.append(f"Estimated usable campus coverage only {coverage:.2f}.")

    row = {
        "school_id": sid,
        "school_name": school["school_name"],
        "imagery_date": meta["acquisition_date"],
        "solar_present": a.solar.present,
        "solar_present_confidence": solar_present_conf,
        "solar_area_m2": solar_area,
        "solar_area_m2_confidence": solar_area_conf,
        "portable_count": a.portables.count,
        "portable_count_confidence": portable_conf,
        "fence_extent": a.fence.extent,
        "fence_extent_confidence": fence_extent_conf,
        "fence_type": a.fence.dominant_type,
        "fence_type_confidence": fence_type_conf,
        "track_present": ath.track_present,
        "track_present_confidence": track_conf,
        "sports_fields_count": ath.sports_fields_count,
        "sports_fields_count_confidence": fields_conf,
        "hard_courts_count": ath.hard_courts_count,
        "hard_courts_count_confidence": courts_conf,
        "pool_present": ath.pool_present,
        "pool_present_confidence": pool_conf,
        "review_required": review_required,
        "failure_notes": " | ".join(dict.fromkeys(n for n in failure_notes if n)),
    }

    api_cost = estimate_api_cost_usd(
        result.usage.prompt_tokens,
        result.usage.billable_output_tokens,
        settings.gemini_input_usd_per_1m,
        settings.gemini_output_usd_per_1m,
    )
    diagnostic = {
        "school_id": sid,
        "school_name": school["school_name"],
        "resolved_latitude": center["latitude"],
        "resolved_longitude": center["longitude"],
        "campus_resolution_method": center["method"],
        "campus_review_required": center["review_required"],
        "campus_resolution_confidence": center["resolution_confidence"],
        "imagery_item": meta["stac_item_id"],
        "imagery_date": meta["acquisition_date"],
        "imagery_age_years": round(imagery_age_years, 2),
        "imagery_is_stale": imagery_is_stale,
        "stac_bbox_coverage_fraction": meta["stac_bbox_coverage_fraction"],
        "vlm_campus_coverage_visible": a.campus_coverage_visible,
        "campus_boundary_observability": a.campus_boundary_observability,
        "campus_boundary_ambiguity": a.campus_boundary_ambiguity,
        "black_pixel_fraction": meta["black_pixel_fraction"],
        "tree_occlusion": a.tree_occlusion,
        "overall_image_quality": a.overall_image_quality,
        "model": result.model,
        "prompt_version": getattr(extractor, "prompt_version", None),
        "prompt_tokens": result.usage.prompt_tokens,
        "output_tokens": result.usage.output_tokens,
        "thinking_tokens": result.usage.thinking_tokens,
        "billable_output_tokens": result.usage.billable_output_tokens,
        "total_tokens": result.usage.total_tokens,
        "estimated_api_cost_usd": api_cost,
        "imagery_seconds": imagery_seconds,
        "vlm_seconds": vlm_seconds,
        "total_seconds": None,  # filled by caller
        "review_required": review_required,
    }

    raw_payload = {
        "school": school,
        "center": center,
        "imagery_metadata": meta,
        "assessment": model_assessment.model_dump(),
        "quality_controlled_assessment": a.model_dump(),
        "quality_control_notes": quality_notes,
        "final_measurement": row,
        "diagnostic": diagnostic,
    }
    (raw_dir / f"{sid}.json").write_text(
        json.dumps(raw_payload, indent=2, default=str),
        encoding="utf-8",
    )

    return row, diagnostic


def run_extraction(
    settings,
    provider: str = "gemini",
    force_imagery: bool = False,
    limit: int | None = None,
    school_id: str | None = None,
) -> pd.DataFrame:
    """Run the end-to-end measurement stage and save CSV + raw diagnostics."""

    schools = load_schools(settings.schools_csv)
    if school_id:
        schools = schools[schools["school_id"].astype(str) == str(school_id)]
        if schools.empty:
            raise ValueError(f"Unknown school_id: {school_id}")
    if limit:
        schools = schools.head(limit)

    review = _review_lookup(load_campus_review(settings.campus_review_csv))
    extractor = _make_extractor(settings, provider)

    raw_dir = settings.outputs_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    diagnostic_rows: list[dict] = []
    total_schools = len(schools)

    print(
        f"\nStarting extraction: {total_schools} school(s), provider={provider}",
        flush=True,
    )

    for school_index, school in enumerate(schools.to_dict("records"), start=1):
        sid = str(school["school_id"])
        t0 = perf_counter()
        print(
            f"\n[{school_index}/{total_schools}] "
            f"{school['school_name']} ({sid})",
            flush=True,
        )

        try:
            row, diagnostic = _process_one_school(
                school, sid, settings, extractor, review,
                force_imagery, raw_dir,
            )
            total_seconds = perf_counter() - t0
            diagnostic["total_seconds"] = total_seconds
            rows.append(row)
            diagnostic_rows.append(diagnostic)
            print(
                f"  Done: {total_seconds:.1f}s, "
                f"review_required={row['review_required']}",
                flush=True,
            )

        except Exception as exc:
            total_seconds = perf_counter() - t0
            error_msg = f"{type(exc).__name__}: {str(exc)[:300]}"
            print(f"  *** FAILED ({total_seconds:.1f}s): {error_msg}", flush=True)
            rows.append(_failure_row(sid, school["school_name"], error_msg))
            diagnostic_rows.append({
                "school_id": sid,
                "school_name": school["school_name"],
                "total_seconds": total_seconds,
                "review_required": True,
            })

    measurements = pd.DataFrame(rows, columns=MEASUREMENT_COLUMNS)
    diagnostics = pd.DataFrame(diagnostic_rows)

    prefix = "mock_" if provider == "mock" else ""
    measurements_path = settings.outputs_dir / f"{prefix}measurements.csv"
    diagnostics_path = settings.outputs_dir / f"{prefix}run_diagnostics.csv"
    if school_id:
        sid = str(school_id)

        if measurements_path.exists():
            existing = pd.read_csv(
                measurements_path,
                dtype={"school_id": "string"},
            )
            existing = existing[
                existing["school_id"].astype(str) != sid
            ]

            measurements = pd.DataFrame.from_records(
                existing.to_dict("records") + measurements.to_dict("records"),
                columns=MEASUREMENT_COLUMNS,
            )
            measurements = measurements.sort_values("school_id").reset_index(drop=True)

        if diagnostics_path.exists():
            existing_diag = pd.read_csv(
                diagnostics_path,
                dtype={"school_id": "string"},
            )
            existing_diag = existing_diag[
                existing_diag["school_id"].astype(str) != sid
            ]

            diagnostics = pd.DataFrame.from_records(
                existing_diag.to_dict("records") + diagnostics.to_dict("records"),
            )
            diagnostics = diagnostics.sort_values("school_id").reset_index(drop=True)

    measurements.to_csv(measurements_path, index=False)
    diagnostics.to_csv(diagnostics_path, index=False)

    return measurements
