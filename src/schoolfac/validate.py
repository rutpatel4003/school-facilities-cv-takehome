from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .io_utils import LABEL_COLUMNS, MEASUREMENT_COLUMNS, parse_optional_bool


DISCRETE_FIELDS = [
    "solar_present",
    "portable_count",
    "fence_extent",
    "fence_type",
    "track_present",
    "sports_fields_count",
    "hard_courts_count",
    "pool_present",
]

BOOL_FIELDS = {"solar_present", "track_present", "pool_present"}
COUNT_FIELDS = {"portable_count", "sports_fields_count", "hard_courts_count"}
MINIMUM_VALIDATION_SCHOOLS = 8
ALLOWED_SAMPLE_ROLES = {"seeded_random", "targeted_solar_challenge"}
ALLOWED_CATEGORICAL_VALUES = {
    "fence_extent": {"full", "partial", "none", "unmeasurable"},
    "fence_type": {"chain-link", "wrought-iron", "wall", "other", "unknown"},
}
EVALUATED_FIELDS = set(DISCRETE_FIELDS) | {"solar_area_m2"}
CONFIDENCE_COLUMNS = [
    column for column in MEASUREMENT_COLUMNS if column.endswith("_confidence")
]


def prepare_validation_template(
    schools: pd.DataFrame,
    output_csv: str | Path,
    seed: int = 42,
) -> pd.DataFrame:
    """Choose 8 schools before manual labeling: 3 primary, 2 middle, 3 high."""

    target = {"Primary": 3, "Middle": 2, "High": 3}
    selected = []
    for level, n in target.items():
        group = schools[schools["level"] == level]
        if len(group) < n:
            raise ValueError(f"Need {n} {level} schools, only found {len(group)}")
        selected.append(group.sample(n=n, random_state=seed))

    sample = pd.concat(selected).sort_values("school_id")
    template = pd.DataFrame({
        "school_id": sample["school_id"].astype(str),
        "school_name": sample["school_name"],
    })
    for col in LABEL_COLUMNS[2:]:
        template[col] = ""
    template["sample_role"] = "seeded_random"

    output_csv = Path(output_csv)
    if output_csv.exists():
        raise FileExistsError(
            f"{output_csv} already exists. Refusing to overwrite manual labels."
        )
    template.to_csv(output_csv, index=False)
    return template


def _normalize_value(field: str, value):
    if pd.isna(value) or str(value).strip() == "":
        return None
    if field in BOOL_FIELDS:
        return parse_optional_bool(value)
    if field in COUNT_FIELDS:
        return int(float(value))
    normalized = str(value).strip().lower()
    if field == "fence_type" and normalized == "wrought iron":
        return "wrought-iron"
    return normalized


def _excluded_fields(row: pd.Series) -> set[str]:
    value = row.get("excluded_fields", "")
    if pd.isna(value) or not str(value).strip():
        return set()
    return {field.strip() for field in str(value).split(";") if field.strip()}


def _validate_truth_labels(truth: pd.DataFrame) -> None:
    """Reject malformed labels before they silently become evaluation errors."""

    missing_columns = [column for column in LABEL_COLUMNS if column not in truth.columns]
    if missing_columns:
        raise ValueError(f"Validation labels are missing columns: {missing_columns}")

    if len(truth) < MINIMUM_VALIDATION_SCHOOLS:
        raise ValueError(
            f"Expected at least {MINIMUM_VALIDATION_SCHOOLS} validation-school "
            f"rows, found {len(truth)}. Restore the seeded template rows rather "
            "than silently shrinking the validation set."
        )

    duplicate_ids = truth.loc[
        truth["school_id"].astype(str).duplicated(keep=False),
        "school_id",
    ].astype(str).tolist()
    if duplicate_ids:
        raise ValueError(f"Duplicate validation school_id values: {duplicate_ids}")

    for _, row in truth.iterrows():
        school_id = str(row["school_id"])
        sample_role = str(row["sample_role"]).strip().lower()
        if sample_role not in ALLOWED_SAMPLE_ROLES:
            raise ValueError(
                f"Invalid sample_role for school {school_id}: "
                f"{row['sample_role']!r}. Allowed values: "
                f"{sorted(ALLOWED_SAMPLE_ROLES)}"
            )
        excluded_fields = _excluded_fields(row)
        unknown_exclusions = sorted(excluded_fields - EVALUATED_FIELDS)
        if unknown_exclusions:
            raise ValueError(
                f"Unknown excluded_fields for school {school_id}: "
                f"{unknown_exclusions}. Allowed fields: {sorted(EVALUATED_FIELDS)}"
            )
        exclusion_reason = row.get("evaluation_exclusion_reason", "")
        if excluded_fields and (
            pd.isna(exclusion_reason) or not str(exclusion_reason).strip()
        ):
            raise ValueError(
                f"An evaluation_exclusion_reason is required for excluded_fields "
                f"at school {school_id}"
            )
        for field in excluded_fields:
            value = row[field]
            if pd.isna(value) or not str(value).strip():
                raise ValueError(
                    f"Excluded field {field!r} has no reference value for school "
                    f"{school_id}"
                )

        for field in BOOL_FIELDS:
            value = row[field]
            if pd.isna(value) or str(value).strip() == "":
                continue
            try:
                parse_optional_bool(value)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid {field} label for school {school_id}: {value!r}"
                ) from exc

        for field in COUNT_FIELDS:
            value = row[field]
            if pd.isna(value) or str(value).strip() == "":
                continue
            number = float(value)
            if number < 0 or not number.is_integer():
                raise ValueError(
                    f"{field} must be a non-negative integer for school "
                    f"{school_id}; got {value!r}"
                )

        for field, allowed in ALLOWED_CATEGORICAL_VALUES.items():
            value = row[field]
            if pd.isna(value) or str(value).strip() == "":
                continue
            normalized = str(value).strip().lower()
            if normalized not in allowed:
                raise ValueError(
                    f"Invalid {field} label for school {school_id}: {value!r}. "
                    f"Allowed values: {sorted(allowed)}"
                )

        solar_present = parse_optional_bool(row["solar_present"])
        area_value = row["solar_area_m2"]
        if not (pd.isna(area_value) or str(area_value).strip() == ""):
            area = float(area_value)
            if area < 0:
                raise ValueError(
                    f"solar_area_m2 must be non-negative for school {school_id}"
                )
            if solar_present is False and area != 0:
                raise ValueError(
                    f"solar_area_m2 must be 0 or blank when solar_present is "
                    f"FALSE for school {school_id}"
                )


def _validate_predictions(pred: pd.DataFrame) -> None:
    """Validate the submitted prediction contract before scoring it."""

    missing_columns = [
        column for column in MEASUREMENT_COLUMNS if column not in pred.columns
    ]
    if missing_columns:
        raise ValueError(f"Measurements are missing columns: {missing_columns}")

    if pred["school_id"].isna().any() or (
        pred["school_id"].astype(str).str.strip() == ""
    ).any():
        raise ValueError("Measurements contain a missing school_id.")
    duplicate_ids = pred.loc[
        pred["school_id"].astype(str).duplicated(keep=False),
        "school_id",
    ].astype(str).tolist()
    if duplicate_ids:
        raise ValueError(f"Duplicate measurement school_id values: {duplicate_ids}")

    for column in CONFIDENCE_COLUMNS:
        values = pd.to_numeric(pred[column], errors="coerce")
        if values.isna().any() or not values.between(0.0, 1.0).all():
            raise ValueError(
                f"{column} must contain numeric values between 0 and 1."
            )

    for value in pred["review_required"]:
        try:
            parsed = parse_optional_bool(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid review_required value in measurements: {value!r}"
            ) from exc
        if parsed is None:
            raise ValueError("review_required cannot be blank in measurements.")


def _calibration_error(group: pd.DataFrame) -> tuple[float, float]:
    """Return fixed-bin expected and maximum calibration error."""

    if group.empty:
        return np.nan, np.nan
    bands = group.groupby("confidence").agg(
        n=("correct", "size"),
        observed_accuracy=("correct", "mean"),
    )
    absolute_gaps = (bands.index.to_series() - bands["observed_accuracy"]).abs()
    expected = float((absolute_gaps * bands["n"]).sum() / bands["n"].sum())
    return expected, float(absolute_gaps.max())


def evaluate(
    measurements_csv: str | Path,
    labels_csv: str | Path,
    output_dir: str | Path,
    solar_area_relative_tolerance: float = 0.25,
    development_school_ids: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Evaluate exact correctness, count error, solar-area error, and calibration."""

    pred = pd.read_csv(measurements_csv, dtype={"school_id": "string"})
    truth = pd.read_csv(labels_csv, dtype={"school_id": "string"})
    _validate_predictions(pred)
    _validate_truth_labels(truth)
    development_school_ids = {
        str(school_id) for school_id in (development_school_ids or set())
    }
    truth_ids = set(truth["school_id"].astype(str))
    unknown_development_ids = sorted(development_school_ids - truth_ids)
    if unknown_development_ids:
        raise ValueError(
            "Development school IDs are not in the validation template: "
            f"{unknown_development_ids}"
        )

    merged = pred.merge(
        truth,
        on="school_id",
        suffixes=("_pred", "_true"),
        validate="one_to_one",
        how="right",
        indicator=True,
    )

    missing_predictions = merged.loc[
        merged["_merge"] == "right_only",
        "school_id",
    ].tolist()

    if missing_predictions:
        raise ValueError(
            "Validation schools missing from predictions: "
            f"{missing_predictions}"
        )

    merged = merged.drop(columns="_merge")

    observations = []
    exclusions = []
    for _, row in merged.iterrows():
        sid = row["school_id"]
        name = row.get("school_name_pred", row.get("school_name_true", ""))
        evaluation_split = (
            "development" if str(sid) in development_school_ids else "reporting"
        )
        sample_role = str(row["sample_role"]).strip().lower()
        excluded_fields = _excluded_fields(row)
        exclusion_reason = str(row.get("evaluation_exclusion_reason", "")).strip()
        school_review_required = bool(parse_optional_bool(row["review_required"]))

        for field in DISCRETE_FIELDS:
            pred_value = _normalize_value(field, row.get(f"{field}_pred"))
            true_value = _normalize_value(field, row.get(f"{field}_true"))
            if true_value is None:
                continue  # unlabeled / genuinely unmeasurable ground truth
            if field in excluded_fields:
                exclusions.append(
                    {
                        "school_id": sid,
                        "school_name": name,
                        "evaluation_split": evaluation_split,
                        "sample_role": sample_role,
                        "field": field,
                        "prediction": pred_value,
                        "reference_value": true_value,
                        "confidence": float(row[f"{field}_confidence"]),
                        "reason": exclusion_reason,
                    }
                )
                continue
            correct = pred_value == true_value
            obs = {
                "school_id": sid,
                "school_name": name,
                "evaluation_split": evaluation_split,
                "sample_role": sample_role,
                "field": field,
                "prediction": pred_value,
                "truth": true_value,
                "correct": int(correct),
                "confidence": float(row[f"{field}_confidence"]),
                "school_review_required": school_review_required,
                "absolute_error": None,
                "relative_error": None,
            }
            if field in COUNT_FIELDS and pred_value is not None:
                obs["absolute_error"] = abs(int(pred_value) - int(true_value))
            observations.append(obs)

        true_solar = _normalize_value("solar_present", row.get("solar_present_true"))
        true_area_raw = row.get("solar_area_m2_true")
        if true_solar is True and not pd.isna(true_area_raw) and str(true_area_raw).strip() != "":
            true_area = float(true_area_raw)
            pred_area_raw = row.get("solar_area_m2_pred")
            pred_area = None if pd.isna(pred_area_raw) else float(pred_area_raw)
            if "solar_area_m2" in excluded_fields:
                exclusions.append(
                    {
                        "school_id": sid,
                        "school_name": name,
                        "evaluation_split": evaluation_split,
                        "sample_role": sample_role,
                        "field": "solar_area_m2",
                        "prediction": pred_area,
                        "reference_value": true_area,
                        "confidence": float(row["solar_area_m2_confidence"]),
                        "reason": exclusion_reason,
                    }
                )
                continue
            if pred_area is None:
                abs_err = None
                rel_err = None
                correct = False
            else:
                abs_err = abs(pred_area - true_area)
                rel_err = (
                    abs_err / true_area
                    if true_area > 0
                    else (0.0 if pred_area == 0 else np.inf)
                )
                correct = rel_err <= solar_area_relative_tolerance
            observations.append(
                {
                    "school_id": sid,
                    "school_name": name,
                    "evaluation_split": evaluation_split,
                    "sample_role": sample_role,
                    "field": "solar_area_m2",
                    "prediction": pred_area,
                    "truth": true_area,
                    "correct": int(correct),
                    "confidence": float(row["solar_area_m2_confidence"]),
                    "school_review_required": school_review_required,
                    "absolute_error": abs_err,
                    "relative_error": rel_err,
                }
            )

    obs_df = pd.DataFrame(observations)
    if obs_df.empty:
        raise ValueError("No filled ground-truth fields found in validation_labels.csv")

    exclusions_df = pd.DataFrame(
        exclusions,
        columns=[
            "school_id",
            "school_name",
            "evaluation_split",
            "sample_role",
            "field",
            "prediction",
            "reference_value",
            "confidence",
            "reason",
        ],
    )

    summary_rows = []
    for evaluation_split in ["all", "development", "reporting"]:
        split_obs = (
            obs_df
            if evaluation_split == "all"
            else obs_df[obs_df["evaluation_split"] == evaluation_split]
        )
        for field, group in split_obs.groupby("field"):
            positive_n = np.nan
            positive_recall = np.nan
            negative_n = np.nan
            negative_specificity = np.nan
            zero_truth_n = np.nan
            zero_truth_accuracy = np.nan
            nonzero_truth_n = np.nan
            nonzero_truth_accuracy = np.nan
            if field in BOOL_FIELDS:
                positive = group[group["truth"].map(lambda value: value is True)]
                negative = group[group["truth"].map(lambda value: value is False)]
                positive_n = len(positive)
                negative_n = len(negative)
                if positive_n:
                    positive_recall = positive["correct"].mean()
                if negative_n:
                    negative_specificity = negative["correct"].mean()
            elif field in COUNT_FIELDS:
                truth_numeric = pd.to_numeric(group["truth"], errors="coerce")
                zero_truth = group[truth_numeric == 0]
                nonzero_truth = group[truth_numeric > 0]
                zero_truth_n = len(zero_truth)
                nonzero_truth_n = len(nonzero_truth)
                if zero_truth_n:
                    zero_truth_accuracy = zero_truth["correct"].mean()
                if nonzero_truth_n:
                    nonzero_truth_accuracy = nonzero_truth["correct"].mean()

            summary_rows.append(
                {
                    "evaluation_split": evaluation_split,
                    "field": field,
                    "n": len(group),
                    "accuracy": group["correct"].mean(),
                    "positive_n": positive_n,
                    "positive_recall": positive_recall,
                    "negative_n": negative_n,
                    "negative_specificity": negative_specificity,
                    "zero_truth_n": zero_truth_n,
                    "zero_truth_accuracy": zero_truth_accuracy,
                    "nonzero_truth_n": nonzero_truth_n,
                    "nonzero_truth_accuracy": nonzero_truth_accuracy,
                    "mean_confidence": group["confidence"].mean(),
                    "calibration_gap_conf_minus_acc": (
                        group["confidence"].mean() - group["correct"].mean()
                    ),
                    "mae": pd.to_numeric(
                        group["absolute_error"], errors="coerce"
                    ).mean(),
                    "mean_relative_error": pd.to_numeric(
                        group["relative_error"], errors="coerce"
                    ).replace([np.inf, -np.inf], np.nan).mean(),
                }
            )
    summary_df = pd.DataFrame(summary_rows).sort_values(
        ["evaluation_split", "field"]
    )

    calibration_frames = []
    for split_name in ["all", "development", "reporting"]:
        split_obs = (
            obs_df
            if split_name == "all"
            else obs_df[obs_df["evaluation_split"] == split_name]
        )
        if split_obs.empty:
            continue
        frame = (
            split_obs.groupby("confidence", dropna=False)
            .agg(
                n=("correct", "size"),
                schools=("school_id", "nunique"),
                observed_accuracy=("correct", "mean"),
            )
            .reset_index()
        )
        frame.insert(0, "evaluation_split", split_name)
        calibration_frames.append(frame)
    calibration = pd.concat(calibration_frames, ignore_index=True).sort_values(
        ["evaluation_split", "confidence"]
    )
    calibration["gap_conf_minus_accuracy"] = (
        calibration["confidence"] - calibration["observed_accuracy"]
    )
    calibration["absolute_calibration_gap"] = calibration[
        "gap_conf_minus_accuracy"
    ].abs()

    truth_with_split = truth.copy()
    truth_with_split["evaluation_split"] = truth_with_split["school_id"].map(
        lambda sid: "development" if str(sid) in development_school_ids else "reporting"
    )

    overview_rows = []
    for split_name in ["all", "development", "reporting"]:
        split_truth = (
            truth_with_split
            if split_name == "all"
            else truth_with_split[
                truth_with_split["evaluation_split"] == split_name
            ]
        )
        split_obs = (
            obs_df
            if split_name == "all"
            else obs_df[obs_df["evaluation_split"] == split_name]
        )
        split_exclusions = (
            exclusions_df
            if split_name == "all"
            else exclusions_df[exclusions_df["evaluation_split"] == split_name]
        )

        labeled_discrete_cells = sum(
            split_truth[field].apply(
                lambda value: not (pd.isna(value) or str(value).strip() == "")
            ).sum()
            for field in DISCRETE_FIELDS
        )
        possible_discrete_cells = len(split_truth) * len(DISCRETE_FIELDS)
        labeled_school_mask = split_truth[DISCRETE_FIELDS].apply(
            lambda column: column.map(
                lambda value: not (pd.isna(value) or str(value).strip() == "")
            )
        ).any(axis=1)

        if split_obs.empty:
            overall_accuracy = np.nan
            mean_confidence = np.nan
            calibration_gap = np.nan
            brier_score = np.nan
        else:
            overall_accuracy = float(split_obs["correct"].mean())
            mean_confidence = float(split_obs["confidence"].mean())
            calibration_gap = mean_confidence - overall_accuracy
            brier_score = float(
                ((split_obs["confidence"] - split_obs["correct"]) ** 2).mean()
            )
        expected_calibration_error, maximum_calibration_error = _calibration_error(
            split_obs
        )

        overview_rows.append(
            {
                "evaluation_split": split_name,
                "selected_validation_schools": len(split_truth),
                "schools_with_any_labels": int(labeled_school_mask.sum()),
                "labeled_observations": len(split_obs),
                "excluded_reference_comparisons": len(split_exclusions),
                "total_filled_reference_comparisons": (
                    len(split_obs) + len(split_exclusions)
                ),
                "overall_exact_accuracy": overall_accuracy,
                "mean_confidence": mean_confidence,
                "calibration_gap_conf_minus_accuracy": calibration_gap,
                "brier_score_for_correctness": brier_score,
                "expected_calibration_error": expected_calibration_error,
                "maximum_calibration_error": maximum_calibration_error,
                "discrete_label_completion_rate": (
                    float(labeled_discrete_cells / possible_discrete_cells)
                    if possible_discrete_cells
                    else np.nan
                ),
            }
        )

    overview = pd.DataFrame(overview_rows)

    sample_rows = []
    for sample_role, role_truth in truth.groupby("sample_role"):
        role_obs = obs_df[obs_df["sample_role"] == sample_role]
        role_exclusions = exclusions_df[
            exclusions_df["sample_role"] == sample_role
        ]
        accuracy = float(role_obs["correct"].mean())
        mean_confidence = float(role_obs["confidence"].mean())
        sample_rows.append(
            {
                "sample_role": sample_role,
                "schools": len(role_truth),
                "scored_observations": len(role_obs),
                "excluded_reference_comparisons": len(role_exclusions),
                "exact_accuracy": accuracy,
                "mean_confidence": mean_confidence,
                "calibration_gap_conf_minus_accuracy": (
                    mean_confidence - accuracy
                ),
                "brier_score_for_correctness": float(
                    ((role_obs["confidence"] - role_obs["correct"]) ** 2).mean()
                ),
            }
        )
    sample_summary = pd.DataFrame(sample_rows)

    review_rows = []
    for split_name in ["all", "development", "reporting"]:
        split_obs = (
            obs_df
            if split_name == "all"
            else obs_df[obs_df["evaluation_split"] == split_name]
        )
        for policy, mask in {
            "existing_school_review_required": split_obs["school_review_required"],
            "field_confidence_le_0.7": split_obs["confidence"] <= 0.7,
            "field_confidence_le_0.4": split_obs["confidence"] <= 0.4,
        }.items():
            total_errors = int((split_obs["correct"] == 0).sum())
            flagged = split_obs[mask]
            retained = split_obs[~mask]
            caught_errors = int((flagged["correct"] == 0).sum())
            review_rows.append(
                {
                    "evaluation_split": split_name,
                    "policy": policy,
                    "total_observations": len(split_obs),
                    "total_errors": total_errors,
                    "flagged_observations": len(flagged),
                    "flagged_observation_rate": (
                        len(flagged) / len(split_obs) if len(split_obs) else np.nan
                    ),
                    "caught_errors": caught_errors,
                    "error_recall": (
                        caught_errors / total_errors if total_errors else np.nan
                    ),
                    "correct_observations_also_reviewed": int(
                        (flagged["correct"] == 1).sum()
                    ),
                    "review_precision": (
                        caught_errors / len(flagged) if len(flagged) else np.nan
                    ),
                    "retained_observations": len(retained),
                    "retained_observation_rate": (
                        len(retained) / len(split_obs) if len(split_obs) else np.nan
                    ),
                    "retained_accuracy": (
                        retained["correct"].mean() if len(retained) else np.nan
                    ),
                    "retained_error_rate": (
                        1.0 - retained["correct"].mean()
                        if len(retained)
                        else np.nan
                    ),
                }
            )
    review_summary = pd.DataFrame(review_rows)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    obs_df.to_csv(output_dir / "validation_observations.csv", index=False)
    summary_df.to_csv(output_dir / "validation_summary.csv", index=False)
    calibration.to_csv(output_dir / "calibration_summary.csv", index=False)
    overview.to_csv(output_dir / "validation_overview.csv", index=False)
    exclusions_df.to_csv(output_dir / "validation_exclusions.csv", index=False)
    review_summary.to_csv(output_dir / "validation_review_summary.csv", index=False)
    sample_summary.to_csv(output_dir / "validation_sample_summary.csv", index=False)
    return obs_df, summary_df, calibration, overview
