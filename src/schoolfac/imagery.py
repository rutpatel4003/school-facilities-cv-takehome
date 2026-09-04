from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import numpy as np
from PIL import Image
from affine import Affine
import planetary_computer
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from pyproj import CRS

from .geo import bbox_overlap_fraction, make_geodesic_bbox


STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


def _item_datetime(item) -> datetime:
    if getattr(item, "datetime", None) is not None:
        value = item.datetime
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    for key in ("datetime", "start_datetime", "end_datetime"):
        value = item.properties.get(key)
        if value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _choose_item(items, requested_bbox):
    scored = []
    for item in items:
        if not item.bbox:
            coverage = 0.0
        else:
            coverage = bbox_overlap_fraction(requested_bbox, tuple(item.bbox))
        scored.append((coverage, _item_datetime(item), item))

    full = [row for row in scored if row[0] >= 0.98]
    if full:
        return max(full, key=lambda x: x[1])
    if not scored:
        raise RuntimeError("No NAIP item intersects the requested campus box.")
    return max(scored, key=lambda x: (x[0], x[1]))


def fetch_naip_chip(
    latitude: float,
    longitude: float,
    half_size_m: float,
    output_png: str | Path,
    output_json: str | Path,
    max_side_px: int = 1800,
    force: bool = False,
) -> dict:
    """Fetch a dated, georeferenced NAIP campus chip."""
    output_png = Path(output_png)
    output_json = Path(output_json)
    output_png.parent.mkdir(parents=True, exist_ok=True)

    requested_bbox = make_geodesic_bbox(latitude, longitude, half_size_m)

    if output_png.exists() and output_json.exists() and not force:
        cached = json.loads(output_json.read_text(encoding="utf-8"))
        cached_bbox = cached.get("requested_bbox_wgs84")

        if (
            cached_bbox is not None
            and np.allclose(
                cached_bbox,
                requested_bbox,
                rtol=0.0,
                atol=1e-10,
            )
        ):
            return cached

    catalog = pystac_client.Client.open(
        STAC_URL,
        modifier=planetary_computer.sign_inplace,
    )
    search = catalog.search(collections=["naip"], bbox=list(requested_bbox), max_items=100)
    items = list(search.item_collection())
    coverage_fraction, acquisition_dt, item = _choose_item(items, requested_bbox)

    if "image" not in item.assets:
        raise RuntimeError(f"NAIP item {item.id} has no 'image' asset.")

    href = item.assets["image"].href

    with rasterio.open(href) as src:
        raster_bbox = transform_bounds(
            "EPSG:4326",
            src.crs,
            *requested_bbox,
            densify_pts=21,
        )
        window = from_bounds(*raster_bbox, transform=src.transform)

        native_width = max(1, int(round(window.width)))
        native_height = max(1, int(round(window.height)))
        downscale = max(native_width / max_side_px, native_height / max_side_px, 1.0)
        out_width = max(1, int(round(native_width / downscale)))
        out_height = max(1, int(round(native_height / downscale)))

        image = src.read(
            indexes=[1, 2, 3],
            window=window,
            out_shape=(3, out_height, out_width),
            resampling=Resampling.bilinear,
            boundless=True,
            fill_value=0,
        )

        native_transform = src.window_transform(window)
        output_transform = native_transform * Affine.scale(
            window.width / out_width,
            window.height / out_height,
        )

        rgb = np.moveaxis(image, 0, -1)
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        Image.fromarray(rgb, mode="RGB").save(output_png)

        crs = CRS.from_user_input(src.crs)
        unit_factor = 1.0
        if crs.axis_info and crs.axis_info[0].unit_conversion_factor:
            unit_factor = float(crs.axis_info[0].unit_conversion_factor)
        determinant = abs(
            output_transform.a * output_transform.e
            - output_transform.b * output_transform.d
        )
        pixel_area_m2 = determinant * (unit_factor ** 2)

        black_pixel_fraction = float(np.mean(np.all(rgb == 0, axis=2)))

        metadata = {
            "source": "NAIP via Microsoft Planetary Computer STAC",
            "stac_item_id": item.id,
            "acquisition_date": acquisition_dt.date().isoformat(),
            "requested_bbox_wgs84": list(requested_bbox),
            "item_bbox_wgs84": list(item.bbox) if item.bbox else None,
            "stac_bbox_coverage_fraction": round(float(coverage_fraction), 4),
            "source_crs": str(src.crs),
            "source_crs_linear_unit_to_m": unit_factor,
            "width_px": out_width,
            "height_px": out_height,
            "pixel_area_m2": pixel_area_m2,
            "black_pixel_fraction": black_pixel_fraction,
            "affine_transform": [
                output_transform.a,
                output_transform.b,
                output_transform.c,
                output_transform.d,
                output_transform.e,
                output_transform.f,
            ],
            "center_latitude": latitude,
            "center_longitude": longitude,
            "half_size_m": half_size_m,
        }

    output_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
