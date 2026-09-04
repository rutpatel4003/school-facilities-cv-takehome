from __future__ import annotations

from pathlib import Path
import json
from typing import Any

import pandas as pd


REQUIRED_SCHOOL_COLUMNS = [
    "school_id",
    "school_name",
    "district",
    "city",
    "state",
    "level",
    "enrollment_2024",
    "latitude",
    "longitude",
]

MEASUREMENT_COLUMNS = [
    "school_id",
    "school_name",
    "imagery_date",
    "solar_present",
    "solar_present_confidence",
    "solar_area_m2",
    "solar_area_m2_confidence",
    "portable_count",
    "portable_count_confidence",
    "fence_extent",
    "fence_extent_confidence",
    "fence_type",
    "fence_type_confidence",
    "track_present",
    "track_present_confidence",
    "sports_fields_count",
    "sports_fields_count_confidence",
    "hard_courts_count",
    "hard_courts_count_confidence",
    "pool_present",
    "pool_present_confidence",
    "review_required",
    "failure_notes",
]

LABEL_COLUMNS = [
    "school_id",
    "school_name",
    "solar_present",
    "solar_area_m2",
    "portable_count",
    "fence_extent",
    "fence_type",
    "track_present",
    "sports_fields_count",
    "hard_courts_count",
    "pool_present",
    "ground_truth_notes",
    "excluded_fields",
    "evaluation_exclusion_reason",
    "sample_role",
]


def load_schools(path: str | Path) -> pd.DataFrame:
    """Load and validate the school sample."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Missing input CSV: {path}")

    df = pd.read_csv(
        path,
        dtype={
            "school_id": "string",
            "school_name": "string",
            "district": "string",
            "city": "string",
            "state": "string",
            "level": "string",
        },
    )

    missing = [c for c in REQUIRED_SCHOOL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required school columns: {missing}")

    df = df[REQUIRED_SCHOOL_COLUMNS].copy()
    for col in ["school_id", "school_name", "district", "city", "state", "level"]:
        df[col] = df[col].str.strip()

    df["latitude"] = pd.to_numeric(df["latitude"], errors="raise")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="raise")
    df["enrollment_2024"] = pd.to_numeric(df["enrollment_2024"], errors="raise")

    if df[REQUIRED_SCHOOL_COLUMNS].isna().any().any():
        raise ValueError("Input sample contains missing required values.")
    if df["school_id"].duplicated().any():
        dupes = df.loc[df["school_id"].duplicated(keep=False), "school_id"].tolist()
        raise ValueError(f"school_id must be unique. Duplicates: {dupes}")
    if not df["latitude"].between(-90, 90).all():
        raise ValueError("Latitude outside [-90, 90].")
    if not df["longitude"].between(-180, 180).all():
        raise ValueError("Longitude outside [-180, 180].")

    allowed = {"Primary", "Middle", "High"}
    unexpected = sorted(set(df["level"]) - allowed)
    if unexpected:
        raise ValueError(f"Unexpected school levels: {unexpected}")

    return df


def write_json(path: str | Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_optional_bool(value: Any) -> bool | None:
    if pd.isna(value) or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "t", "1", "yes", "y"}:
        return True
    if text in {"false", "f", "0", "no", "n"}:
        return False
    raise ValueError(f"Cannot interpret boolean value: {value!r}")
