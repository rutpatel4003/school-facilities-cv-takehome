from __future__ import annotations

from pathlib import Path
from PIL import Image


def create_multiscale_views(
    overview_path: str | Path,
    output_dir: str | Path,
    overlap_fraction: float = 0.08,
    center_fraction: float = 0.70,
) -> list[tuple[str, Path]]:
    """Create overview, centered-detail, and four overlapping views."""
    if not 0.0 <= overlap_fraction < 0.5:
        raise ValueError("overlap_fraction must be in [0, 0.5).")
    if not 0.0 < center_fraction <= 1.0:
        raise ValueError("center_fraction must be in (0, 1].")

    overview_path = Path(overview_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(overview_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        mx, my = w // 2, h // 2
        ox, oy = int(w * overlap_fraction), int(h * overlap_fraction)

        center_w = max(1, int(round(w * center_fraction)))
        center_h = max(1, int(round(h * center_fraction)))
        center_left = max(0, (w - center_w) // 2)
        center_top = max(0, (h - center_h) // 2)
        center_box = (
            center_left,
            center_top,
            min(w, center_left + center_w),
            min(h, center_top + center_h),
        )

        boxes = {
            "NW": (0, 0, min(w, mx + ox), min(h, my + oy)),
            "NE": (max(0, mx - ox), 0, w, min(h, my + oy)),
            "SW": (0, max(0, my - oy), min(w, mx + ox), h),
            "SE": (max(0, mx - ox), max(0, my - oy), w, h),
        }

        results: list[tuple[str, Path]] = [("FULL_OVERVIEW", overview_path)]

        center_out = output_dir / "center.jpg"
        img.crop(center_box).save(center_out, format="JPEG", quality=92)
        results.append(("CENTER_DETAIL", center_out))

        for label, box in boxes.items():
            out = output_dir / f"{label.lower()}.jpg"
            img.crop(box).save(out, format="JPEG", quality=92)
            results.append((label, out))

    return results
