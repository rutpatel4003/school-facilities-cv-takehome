from __future__ import annotations


def estimate_api_cost_usd(
    prompt_tokens: int | None,
    output_tokens: int | None,
    input_usd_per_1m: float | None,
    output_usd_per_1m: float | None,
) -> float | None:
    if any(
        value is None
        for value in (
            prompt_tokens,
            output_tokens,
            input_usd_per_1m,
            output_usd_per_1m,
        )
    ):
        return None
    cost = (
        prompt_tokens / 1_000_000 * input_usd_per_1m
        + output_tokens / 1_000_000 * output_usd_per_1m
    )
    return float(cost)
