from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """All paths and small prototype-level configuration in one place"""
    root: Path
    schools_csv: Path
    campus_review_csv: Path
    validation_labels_csv: Path
    imagery_dir: Path
    outputs_dir: Path
    gemini_api_key: str | None
    gemini_model: str
    nominatim_user_agent: str | None
    gemini_input_usd_per_1m: float | None
    gemini_output_usd_per_1m: float | None
    default_chip_half_size_m: float = 350.0
    max_image_side_px: int = 1800
    stale_imagery_years: float = 5.0


def _optional_float(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return float(raw)


def load_settings(root: str | Path | None = None) -> Settings:
    root_path = (
        Path(root).resolve()
        if root is not None
        else Path(__file__).resolve().parents[2]
    )

    load_dotenv(root_path / ".env")

    outputs = root_path / "outputs"
    imagery = root_path / "data" / "imagery"
    outputs.mkdir(parents=True, exist_ok=True)
    imagery.mkdir(parents=True, exist_ok=True)

    return Settings(
        root=root_path,
        schools_csv=root_path / "data" / "schools_sample.csv",
        campus_review_csv=root_path / "data" / "campus_review.csv",
        validation_labels_csv=root_path / "data" / "validation_labels.csv",
        imagery_dir=imagery,
        outputs_dir=outputs,
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip() or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip(),
        nominatim_user_agent=os.getenv("SCHOOL_CV_USER_AGENT", "").strip() or None,
        gemini_input_usd_per_1m=_optional_float("GEMINI_INPUT_USD_PER_1M"),
        gemini_output_usd_per_1m=_optional_float("GEMINI_OUTPUT_USD_PER_1M"),
    )
