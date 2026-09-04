from __future__ import annotations

import argparse
from pathlib import Path

from .campus import prepare_campus_review
from .config import load_settings
from .io_utils import load_schools
from .pipeline import fetch_all_imagery, run_extraction
from .report import summarize_run
from .validate import evaluate, prepare_validation_template


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="School Facilities CV take-home pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-data", help="Validate the provided schools_sample.csv")

    p = sub.add_parser(
        "prepare-campus",
        help="Generate candidate campus locations for manual review",
    )
    p.add_argument(
        "--force-refresh",
        action="store_true",
        help="Delete geocoder cache before querying",
    )

    p = sub.add_parser("fetch-imagery", help="Fetch/crop dated NAIP imagery")
    p.add_argument("--limit", type=int)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("extract", help="Run VLM extraction and produce measurements.csv")
    p.add_argument("--provider", choices=["gemini", "mock"], default="gemini")
    p.add_argument("--limit", type=int)
    p.add_argument("--school-id")
    p.add_argument("--force-imagery", action="store_true")

    sub.add_parser(
        "prepare-validation",
        help="Choose 8 schools and create a blank ground-truth template",
    )

    p = sub.add_parser("validate", help="Compare predictions with manually filled ground truth")
    p.add_argument("--solar-area-tolerance", type=float, default=0.25)
    p.add_argument(
        "--predictions-csv",
        type=Path,
        help=(
            "Prediction file to evaluate. Use measurements.csv for the frozen "
            "submission or outputs/measurements.csv for a new Gemini run."
        ),
    )
    p.add_argument(
        "--development-school-id",
        action="append",
        default=[],
        help=(
            "School used to tune the method; repeat for multiple IDs so final "
            "metrics remain separated from the reporting subset"
        ),
    )

    p = sub.add_parser("summarize", help="Summarize runtime/cost and extrapolate to 130k schools")
    p.add_argument(
        "--daily-request-limit",
        type=int,
        help="Optional account-specific request cap used for a quota-bound scale estimate",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    settings = load_settings()

    if args.command == "check-data":
        df = load_schools(settings.schools_csv)
        print(f"OK: {len(df)} schools, {df['state'].nunique()} states")
        print(df["level"].value_counts().to_string())
        return

    if args.command == "prepare-campus":
        if not settings.nominatim_user_agent:
            raise SystemExit(
                "Set SCHOOL_CV_USER_AGENT in .env first. See .env.example and README."
            )
        cache = settings.root / "data" / "geocode_cache.json"
        if args.force_refresh and cache.exists():
            cache.unlink()
        df = prepare_campus_review(
            load_schools(settings.schools_csv),
            settings.campus_review_csv,
            settings.nominatim_user_agent,
            cache,
        )
        print(f"Wrote {settings.campus_review_csv} ({len(df)} rows). Review the decision column.")
        return

    if args.command == "fetch-imagery":
        fetch_all_imagery(settings, force=args.force, limit=args.limit)
        return

    if args.command == "extract":
        df = run_extraction(
            settings,
            provider=args.provider,
            force_imagery=args.force_imagery,
            limit=args.limit,
            school_id=args.school_id,
        )
        filename = "mock_measurements.csv" if args.provider == "mock" else "measurements.csv"
        print(f"Wrote {settings.outputs_dir / filename} ({len(df)} rows)")
        return

    if args.command == "prepare-validation":
        df = prepare_validation_template(
            load_schools(settings.schools_csv),
            settings.validation_labels_csv,
        )
        print(f"Wrote {settings.validation_labels_csv} ({len(df)} validation schools).")
        print(
            "Fill labels manually after saving predictions; "
            "do not overwrite model errors."
        )
        return

    if args.command == "validate":
        if args.predictions_csv:
            predictions_csv = args.predictions_csv
            if not predictions_csv.is_absolute():
                predictions_csv = settings.root / predictions_csv
        else:
            predictions_csv = settings.root / "measurements.csv"
            if not predictions_csv.exists():
                predictions_csv = settings.outputs_dir / "measurements.csv"
        print(f"Using predictions: {predictions_csv}")
        obs, summary, calibration, overview = evaluate(
            predictions_csv,
            settings.validation_labels_csv,
            settings.outputs_dir,
            solar_area_relative_tolerance=args.solar_area_tolerance,
            development_school_ids=set(args.development_school_id),
        )
        print("\nEvaluation overview:\n", overview.to_string(index=False))
        print("\nField summary:\n", summary.to_string(index=False))
        print("\nCalibration:\n", calibration.to_string(index=False))
        return

    if args.command == "summarize":
        text = summarize_run(
            settings.outputs_dir / "run_diagnostics.csv",
            settings.outputs_dir / "scale_summary.txt",
            daily_request_limit=args.daily_request_limit,
            input_usd_per_1m=settings.gemini_input_usd_per_1m,
            output_usd_per_1m=settings.gemini_output_usd_per_1m,
        )
        print(text)
        return
