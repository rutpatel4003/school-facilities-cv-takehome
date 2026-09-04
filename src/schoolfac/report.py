from __future__ import annotations

from pathlib import Path
import pandas as pd

from .io_utils import parse_optional_bool


NATIONAL_SCHOOLS = 130_000


def summarize_run(
    diagnostics_csv: str | Path,
    output_txt: str | Path,
    daily_request_limit: int | None = None,
    input_usd_per_1m: float | None = None,
    output_usd_per_1m: float | None = None,
) -> str:
    """Turn measured prototype runtime/cost into an explicit 130k-school estimate."""

    df = pd.read_csv(diagnostics_csv)
    if df.empty:
        raise ValueError("No diagnostics found.")

    median_s = float(df["total_seconds"].median())
    mean_s = float(df["total_seconds"].mean())
    sequential_days = median_s * NATIONAL_SCHOOLS / 86400
    parallel_50_hours = median_s * NATIONAL_SCHOOLS / 50 / 3600
    review_values = df["review_required"].map(parse_optional_bool).dropna()
    review_rate = float(review_values.mean()) if not review_values.empty else float("nan")
    mean_prompt_tokens = pd.to_numeric(df.get("prompt_tokens"), errors="coerce").mean()
    mean_output_tokens = pd.to_numeric(df.get("output_tokens"), errors="coerce").mean()
    visible_output_tokens = pd.to_numeric(df.get("output_tokens"), errors="coerce")
    if "billable_output_tokens" in df.columns:
        billable_output_source = pd.to_numeric(
            df["billable_output_tokens"],
            errors="coerce",
        ).combine_first(visible_output_tokens)
    else:
        billable_output_source = visible_output_tokens
    mean_billable_output_tokens = billable_output_source.mean()

    if daily_request_limit is not None:
        if daily_request_limit <= 0:
            raise ValueError("daily_request_limit must be positive.")
        quota_days = NATIONAL_SCHOOLS / daily_request_limit
        quota_text = (
            f"130k requests at {daily_request_limit:,}/day: at least {quota_days:.1f} days "
            "before retries (account-specific quota)\n"
        )
    else:
        quota_text = (
            "Daily request quota: not supplied; wall-clock parallelism alone is not a scale plan.\n"
        )

    if input_usd_per_1m is not None and output_usd_per_1m is not None:
        prompt_tokens = pd.to_numeric(df.get("prompt_tokens"), errors="coerce")
        output_tokens = pd.to_numeric(billable_output_source, errors="coerce")
        cost_series = (
            prompt_tokens / 1_000_000 * input_usd_per_1m
            + output_tokens / 1_000_000 * output_usd_per_1m
        )
    else:
        cost_series = pd.to_numeric(
            df.get("estimated_api_cost_usd"),
            errors="coerce",
        )
    if cost_series.notna().any():
        mean_cost = float(cost_series.mean())
        scale_cost = mean_cost * NATIONAL_SCHOOLS
        cost_text = (
            f"Mean estimated VLM cost/school: ${mean_cost:.6f}\n"
            f"Estimated VLM cost for 130,000 schools: ${scale_cost:,.2f}\n"
        )
    else:
        cost_text = (
            "VLM dollar cost: not computed because pricing variables were not set.\n"
            "Token counts are in run_diagnostics.csv; set current provider rates "
            "in .env and rerun summarize.\n"
        )

    text = (
        "Prototype scale summary\n"
        "=======================\n"
        f"Schools processed: {len(df)}\n"
        f"Median wall-clock seconds/school: {median_s:.2f}\n"
        f"Mean wall-clock seconds/school: {mean_s:.2f}\n"
        f"130k schools, sequential at median: {sequential_days:.1f} days\n"
        f"130k schools, idealized 50-way parallelism: {parallel_50_hours:.1f} hours\n"
        f"Schools flagged for review: {review_rate:.1%}\n"
        f"Mean prompt tokens/school: {mean_prompt_tokens:.0f}\n"
        f"Mean output tokens/school: {mean_output_tokens:.0f}\n"
        f"Mean billable output tokens/school (including thinking when reported): "
        f"{mean_billable_output_tokens:.0f}\n"
        + quota_text
        + cost_text
        + "\nCaveat: parallel estimate ignores API rate limits, retries, "
        "storage I/O, and manual QA.\n"
    )

    output_txt = Path(output_txt)
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text(text, encoding="utf-8")
    return text
