from __future__ import annotations

from math import radians, sin, cos, asin, sqrt

from pyproj import Geod


WGS84 = Geod(ellps="WGS84")


def make_geodesic_bbox(
    latitude: float,
    longitude: float,
    half_size_m: float,
) -> tuple[float, float, float, float]:
    """Return a meter-buffered WGS84 bounding box."""
    west_lon, _, _ = WGS84.fwd(longitude, latitude, 270, half_size_m)
    east_lon, _, _ = WGS84.fwd(longitude, latitude, 90, half_size_m)
    _, south_lat, _ = WGS84.fwd(longitude, latitude, 180, half_size_m)
    _, north_lat, _ = WGS84.fwd(longitude, latitude, 0, half_size_m)
    return (west_lon, south_lat, east_lon, north_lat)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6_371_008.8
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * earth_radius_m * asin(sqrt(a))


def bbox_overlap_fraction(
    requested: tuple[float, float, float, float],
    available: tuple[float, float, float, float],
) -> float:
    rw, rs, re, rn = requested
    aw, ass, ae, an = available
    iw = max(rw, aw)
    ie = min(re, ae)
    is_ = max(rs, ass)
    in_ = min(rn, an)
    if ie <= iw or in_ <= is_:
        return 0.0
    requested_area = (re - rw) * (rn - rs)
    intersection = (ie - iw) * (in_ - is_)
    return max(0.0, min(1.0, intersection / requested_area))
