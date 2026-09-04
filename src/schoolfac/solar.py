from __future__ import annotations

from .schema import SchoolVisualAssessment


def _clip_box(box: list[int]) -> tuple[float, float, float, float]:
    if len(box) != 4:
        raise ValueError(f"Expected 4 bbox coordinates, got {box}")
    x1, y1, x2, y2 = [max(0.0, min(1000.0, float(v))) for v in box]
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid normalized bbox: {box}")
    return x1, y1, x2, y2


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


def estimate_solar_area_m2(
    assessment: SchoolVisualAssessment,
    imagery_meta: dict,
) -> tuple[float | None, list[str]]:
    """Convert localized solar boxes to approximate square meters."""
    solar = assessment.solar
    if solar.present is False:
        return 0.0, []
    if solar.present is None:
        return None, ["Solar presence unmeasurable; area left null."]
    if not solar.arrays:
        return None, ["Solar marked present but no array boxes returned."]

    width = float(imagery_meta["width_px"])
    height = float(imagery_meta["height_px"])
    pixel_area_m2 = float(imagery_meta["pixel_area_m2"])

    boxes = []
    total = 0.0
    issues: list[str] = []
    for array in solar.arrays:
        box = _clip_box(array.bbox_norm)
        boxes.append(box)
        x1, y1, x2, y2 = box
        box_px = ((x2 - x1) / 1000.0 * width) * ((y2 - y1) / 1000.0 * height)
        total += box_px * pixel_area_m2 * float(array.panel_fill_fraction)

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            overlap = _iou(boxes[i], boxes[j])
            if overlap > 0.10:
                issues.append(
                    f"Solar boxes {i} and {j} overlap (IoU={overlap:.2f}); area may double-count."
                )

    return round(total, 1), issues
