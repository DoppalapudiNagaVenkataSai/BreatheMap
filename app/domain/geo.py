"""Geographic calculation functions without external GIS dependencies."""

import math

EARTH_RADIUS_M = 6371000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in meters."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
BASE32_MAP = {c: i for i, c in enumerate(BASE32)}


def geohash_encode(lat: float, lon: float, precision: int = 5) -> str:
    """Encode latitude and longitude into geohash string."""
    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    geohash: list[str] = []
    bits = [16, 8, 4, 2, 1]
    bit = 0
    ch = 0
    even = True

    while len(geohash) < precision:
        if even:
            mid = (lon_interval[0] + lon_interval[1]) / 2.0
            if lon > mid:
                ch |= bits[bit]
                lon_interval[0] = mid
            else:
                lon_interval[1] = mid
        else:
            mid = (lat_interval[0] + lat_interval[1]) / 2.0
            if lat > mid:
                ch |= bits[bit]
                lat_interval[0] = mid
            else:
                lat_interval[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            geohash.append(BASE32[ch])
            bit = 0
            ch = 0

    return "".join(geohash)


def geohash_decode_bbox(geohash: str) -> tuple[float, float, float, float]:
    """Decode geohash to (min_lat, min_lon, max_lat, max_lon)."""
    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    even = True
    for c in geohash:
        cd = BASE32_MAP[c]
        for mask in [16, 8, 4, 2, 1]:
            if even:
                mid = (lon_interval[0] + lon_interval[1]) / 2.0
                if cd & mask:
                    lon_interval[0] = mid
                else:
                    lon_interval[1] = mid
            else:
                mid = (lat_interval[0] + lat_interval[1]) / 2.0
                if cd & mask:
                    lat_interval[0] = mid
                else:
                    lat_interval[1] = mid
            even = not even
    return lat_interval[0], lon_interval[0], lat_interval[1], lon_interval[1]


def geohash_neighbors(gh: str) -> list[str]:
    """Return 8 adjacent neighbor geohashes."""
    min_lat, min_lon, max_lat, max_lon = geohash_decode_bbox(gh)
    lat_step = max_lat - min_lat
    lon_step = max_lon - min_lon
    center_lat = (min_lat + max_lat) / 2.0
    center_lon = (min_lon + max_lon) / 2.0
    prec = len(gh)

    neighbors = []
    for d_lat in [-1, 0, 1]:
        for d_lon in [-1, 0, 1]:
            if d_lat == 0 and d_lon == 0:
                continue
            n_lat = center_lat + d_lat * lat_step
            n_lon = center_lon + d_lon * lon_step
            # Wrap lon if needed, clamp lat
            n_lat = max(-90.0, min(90.0, n_lat))
            if n_lon > 180.0:
                n_lon -= 360.0
            elif n_lon < -180.0:
                n_lon += 360.0
            neighbors.append(geohash_encode(n_lat, n_lon, prec))
    return sorted(list(set(neighbors)))


def point_to_segment_distance_m(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """Distance from point (px, py) to line segment (x1, y1)-(x2, y2) in meters."""
    # Convert lat/lon degrees to meters using equidistant projection around (x1, y1)
    cos_lat = math.cos(math.radians(x1))
    deg_lat_m = 111320.0
    deg_lon_m = 111320.0 * cos_lat

    vx = (x2 - x1) * deg_lat_m
    vy = (y2 - y1) * deg_lon_m
    wx = (px - x1) * deg_lat_m
    wy = (py - y1) * deg_lon_m

    seg_len_sq = vx * vx + vy * vy
    if seg_len_sq == 0.0:
        return math.hypot(wx, wy)

    t = max(0.0, min(1.0, (wx * vx + wy * vy) / seg_len_sq))
    proj_x = t * vx
    proj_y = t * vy

    return math.hypot(wx - proj_x, wy - proj_y)


def resample_line(
    coords: list[tuple[float, float]], step_m: float = 200.0
) -> list[tuple[float, float]]:
    """Resample a polyline coordinates with uniform step distance."""
    if len(coords) < 2:
        return list(coords)

    resampled = [coords[0]]
    dist_accum = 0.0

    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        seg_dist = haversine_m(p1[0], p1[1], p2[0], p2[1])
        if seg_dist == 0.0:
            continue

        while dist_accum + seg_dist >= step_m:
            fraction = (step_m - dist_accum) / seg_dist
            new_lat = p1[0] + fraction * (p2[0] - p1[0])
            new_lon = p1[1] + fraction * (p2[1] - p1[1])
            resampled.append((new_lat, new_lon))
            seg_dist -= step_m - dist_accum
            p1 = (new_lat, new_lon)
            dist_accum = 0.0

        dist_accum += seg_dist

    if len(resampled) < 2 or resampled[-1] != coords[-1]:
        resampled.append(coords[-1])
    return resampled


def simplify_line(
    coords: list[tuple[float, float]], max_points: int = 300
) -> list[tuple[float, float]]:
    """Simplify polyline using Douglas-Peucker up to max_points count."""
    if len(coords) <= max_points:
        return coords

    def dp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
        if len(points) <= 2:
            return points
        dmax = 0.0
        index = 0
        start = points[0]
        end = points[-1]
        for idx in range(1, len(points) - 1):
            d = point_to_segment_distance_m(
                points[idx][0], points[idx][1], start[0], start[1], end[0], end[1]
            )
            if d > dmax:
                index = idx
                dmax = d
        if dmax > epsilon:
            rec1 = dp(points[: index + 1], epsilon)
            rec2 = dp(points[index:], epsilon)
            return rec1[:-1] + rec2
        return [points[0], points[-1]]

    # Binary search for tolerance epsilon
    low = 1.0
    high = 1000.0
    best_result = coords
    for _ in range(10):
        mid = (low + high) / 2.0
        simplified = dp(coords, mid)
        if len(simplified) <= max_points:
            best_result = simplified
            high = mid
        else:
            low = mid

    return best_result


def line_midpoint(coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Find midpoint coordinate along the polyline."""
    if not coords:
        raise ValueError("Cannot find midpoint of empty line")
    if len(coords) == 1:
        return coords[0]

    total_dist = sum(
        haversine_m(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        for i in range(len(coords) - 1)
    )
    half = total_dist / 2.0
    accum = 0.0

    for i in range(len(coords) - 1):
        seg = haversine_m(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        if accum + seg >= half:
            frac = (half - accum) / seg if seg > 0 else 0.0
            return (
                coords[i][0] + frac * (coords[i + 1][0] - coords[i][0]),
                coords[i][1] + frac * (coords[i + 1][1] - coords[i][1]),
            )
        accum += seg
    return coords[-1]
