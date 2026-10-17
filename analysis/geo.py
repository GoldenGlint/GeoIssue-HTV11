"""Geometry helpers on [lng, lat] coordinates. Flat-earth approximations are fine at city scale."""
import math

EARTH_RADIUS_M = 6_371_008.8
METRES_PER_DEGREE = 111_320


def distance_m(a, b):
    """Great-circle distance between two [lng, lat] points."""
    lng1, lat1, lng2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _metres_from(origin, p):
    k = math.cos(math.radians(origin[1]))
    return ((p[0] - origin[0]) * METRES_PER_DEGREE * k, (p[1] - origin[1]) * METRES_PER_DEGREE)


def distance_to_line_m(p, line):
    best = math.inf
    for a, b in zip(line, line[1:]):
        ax, ay = _metres_from(p, a)
        bx, by = _metres_from(p, b)
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def _in_ring(p, ring):
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _polygons(geometry):
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    return []


def contains(geometry, p):
    """Whether a Polygon or MultiPolygon contains the point. Holes are respected."""
    return any(_in_ring(p, rings[0]) and not any(_in_ring(p, hole) for hole in rings[1:])
               for rings in _polygons(geometry))


def distance_to_geometry_m(p, geometry):
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "Point":
        return distance_m(p, coords)
    if kind == "MultiPoint":
        return min(distance_m(p, c) for c in coords)
    if kind == "LineString":
        return distance_to_line_m(p, coords)
    if kind == "MultiLineString":
        return min(distance_to_line_m(p, line) for line in coords)
    if kind in ("Polygon", "MultiPolygon"):
        if contains(geometry, p):
            return 0.0
        return min(distance_to_line_m(p, ring) for rings in _polygons(geometry) for ring in rings)
    raise ValueError(f"Unsupported geometry type {kind}")


def bbox(geometry):
    """[min lng, min lat, max lng, max lat] of any geometry."""
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for item in c:
                walk(item)

    walk(geometry["coordinates"])
    return [min(xs), min(ys), max(xs), max(ys)]


def in_bbox(box, p, margin_m=0):
    dx = margin_m / (METRES_PER_DEGREE * math.cos(math.radians(p[1])))
    dy = margin_m / METRES_PER_DEGREE
    return box[0] - dx <= p[0] <= box[2] + dx and box[1] - dy <= p[1] <= box[3] + dy


def snap_to_grid(p, grid_m):
    """Centre of the grid cell containing the point, so nearby points share one coarse location."""
    lat_step = grid_m / METRES_PER_DEGREE
    lat = (math.floor(p[1] / lat_step) + 0.5) * lat_step
    lng_step = grid_m / (METRES_PER_DEGREE * math.cos(math.radians(lat)))
    lng = (math.floor(p[0] / lng_step) + 0.5) * lng_step
    return [round(lng, 5), round(lat, 5)]
