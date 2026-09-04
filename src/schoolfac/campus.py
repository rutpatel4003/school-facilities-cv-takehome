from __future__ import annotations

from pathlib import Path
import json
import time

import pandas as pd
from geopy.geocoders import Nominatim
from rapidfuzz.fuzz import token_set_ratio

from .geo import haversine_m


VALID_DECISIONS = {"", "ccd", "candidate", "manual"}


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def prepare_campus_review(
    schools: pd.DataFrame,
    review_csv: str | Path,
    user_agent: str,
    cache_path: str | Path,
) -> pd.DataFrame:
    """Build a review table without replacing CCD coordinates automatically."""

    if not user_agent.strip():
        raise ValueError(
            "SCHOOL_CV_USER_AGENT is required for public Nominatim. "
            "Set an identifiable value in .env."
        )

    review_csv = Path(review_csv)
    cache_path = Path(cache_path)
    cache = _load_cache(cache_path)
    geocoder = Nominatim(user_agent=user_agent, timeout=15)

    existing = None
    if review_csv.exists():
        existing = pd.read_csv(review_csv, dtype={"school_id": "string"})
        existing = existing.set_index("school_id", drop=False)

    rows = []
    for school in schools.to_dict("records"):
        school_id = str(school["school_id"])
        query = f'{school["school_name"]}, {school["city"]}, {school["state"]}, USA'

        raw = cache.get(school_id)
        if raw is None:
            location = geocoder.geocode(query, exactly_one=True, addressdetails=True)
            if location is None:
                raw = None
            else:
                raw = {
                    "latitude": float(location.latitude),
                    "longitude": float(location.longitude),
                    "display_name": location.address,
                }
            cache[school_id] = raw
            _save_cache(cache_path, cache)
            time.sleep(1.1)  # Nominatim allows at most one request per second.

        if raw:
            candidate_lat = raw["latitude"]
            candidate_lon = raw["longitude"]
            display_name = raw["display_name"]
            distance_m = haversine_m(
                float(school["latitude"]),
                float(school["longitude"]),
                candidate_lat,
                candidate_lon,
            )
            similarity = token_set_ratio(
                str(school["school_name"]),
                str(display_name).split(",")[0],
            )
        else:
            candidate_lat = None
            candidate_lon = None
            display_name = None
            distance_m = None
            similarity = None

        previous = (
            existing.loc[school_id]
            if existing is not None and school_id in existing.index
            else None
        )

        def previous_value(column: str, default=None):
            if previous is None:
                return default
            value = previous.get(column, default)
            return default if pd.isna(value) else value

        rows.append(
            {
                "school_id": school_id,
                "school_name": school["school_name"],
                "ccd_latitude": school["latitude"],
                "ccd_longitude": school["longitude"],
                "candidate_latitude": candidate_lat,
                "candidate_longitude": candidate_lon,
                "candidate_distance_m": distance_m,
                "candidate_name_similarity": similarity,
                "candidate_display_name": display_name,
                "decision": str(previous_value("decision", "")),
                "manual_latitude": previous_value("manual_latitude", None),
                "manual_longitude": previous_value("manual_longitude", None),
                "chip_half_size_m": previous_value("chip_half_size_m", 350),
                "notes": str(previous_value("notes", "")),
            }
        )

    result = pd.DataFrame(rows)
    result.to_csv(review_csv, index=False)
    return result


def load_campus_review(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"school_id": "string"})
    if "decision" in df.columns:
        df["decision"] = df["decision"].fillna("").astype(str).str.strip().str.lower()
        bad = sorted(set(df["decision"]) - VALID_DECISIONS)
        if bad:
            raise ValueError(f"Invalid campus-review decisions: {bad}")
    return df


def resolve_center(
    school: dict,
    review_row: dict | None,
    default_half_size_m: float,
) -> dict:
    if not review_row:
        return {
            "latitude": float(school["latitude"]),
            "longitude": float(school["longitude"]),
            "method": "ccd_unreviewed",
            "review_required": True,
            "resolution_confidence": 0.4,
            "half_size_m": default_half_size_m,
        }

    decision = str(review_row.get("decision", "") or "").strip().lower()
    half_size = review_row.get("chip_half_size_m", default_half_size_m)
    if pd.isna(half_size):
        half_size = default_half_size_m
    half_size = float(half_size)

    if decision == "ccd":
        return {
            "latitude": float(school["latitude"]),
            "longitude": float(school["longitude"]),
            "method": "ccd_reviewed",
            "review_required": False,
            "resolution_confidence": 0.9,
            "half_size_m": half_size,
        }
    if decision == "candidate":
        lat = review_row.get("candidate_latitude")
        lon = review_row.get("candidate_longitude")
        if pd.isna(lat) or pd.isna(lon):
            raise ValueError(
                f"Candidate selected but missing coordinates for {school['school_id']}"
            )
        return {
            "latitude": float(lat),
            "longitude": float(lon),
            "method": "nominatim_candidate_reviewed",
            "review_required": False,
            "resolution_confidence": 0.85,
            "half_size_m": half_size,
        }
    if decision == "manual":
        lat = review_row.get("manual_latitude")
        lon = review_row.get("manual_longitude")
        if pd.isna(lat) or pd.isna(lon):
            raise ValueError(f"Manual selected but missing coordinates for {school['school_id']}")
        return {
            "latitude": float(lat),
            "longitude": float(lon),
            "method": "manual_review",
            "review_required": False,
            "resolution_confidence": 0.95,
            "half_size_m": half_size,
        }

    return {
        "latitude": float(school["latitude"]),
        "longitude": float(school["longitude"]),
        "method": "ccd_unreviewed",
        "review_required": True,
        "resolution_confidence": 0.4,
        "half_size_m": half_size,
    }
