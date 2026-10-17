"""Regenerates analysis/refdata/toronto/osm-places.json from OpenStreetMap via the Overpass API.

The analysis finds places named in post text and location guesses with this gazetteer:
named intersections of Toronto's arterial roads ("Queen St W & Spadina Ave"), rail and
transit stations, including closed ones such as the Line 3 Scarborough stations, and parks
of at least 5 ha. See analysis/refdata/README.md for the format.

Usage:  python scripts/fetch-osm-places.py
Data:   © OpenStreetMap contributors, ODbL 1.0 — https://www.openstreetmap.org/copyright
"""
import datetime, json, math, pathlib, re, time, urllib.error, urllib.parse, urllib.request
from collections import Counter, defaultdict

BBOX = "43.58,-79.64,43.86,-79.11"  # south, west, north, east: City of Toronto
QUERY = f"""
[out:json][timeout:180];
way["highway"~"^(trunk|primary|secondary|tertiary)$"]["name"]({BBOX});
out body geom;
(
  nwr["railway"="station"]({BBOX});
  nwr["disused:railway"="station"]({BBOX});
  nwr["railway"="disused_station"]({BBOX});
  nwr["leisure"="park"]["name"]({BBOX});
);
out tags center bb;
"""
OUT = pathlib.Path(__file__).resolve().parent.parent / "analysis" / "refdata" / "toronto" / "osm-places.json"

# Trailing words dropped to get the name people use: "Queen Street West" -> "queen".
STREET_TYPES = {"street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd", "drive", "dr", "crescent", "cres",
                "court", "crt", "ct", "place", "pl", "lane", "ln", "way", "trail", "trl", "parkway", "pkwy", "circle",
                "terrace", "square", "sq", "gate", "grove", "gardens", "heights", "line", "expressway", "highway", "hwy",
                "esplanade", "mews", "path", "promenade", "quay", "row", "walk"}
DIRECTIONS = {"east", "west", "north", "south", "e", "w", "n", "s"}
ABBREVIATIONS = {"Street": "St", "Avenue": "Ave", "Road": "Rd", "Boulevard": "Blvd", "Drive": "Dr", "Crescent": "Cres",
                 "Court": "Crt", "Place": "Pl", "Lane": "Ln", "Parkway": "Pkwy", "Trail": "Trl", "Square": "Sq",
                 "Gardens": "Gdns", "Heights": "Hts", "Expressway": "Expy", "East": "E", "West": "W", "North": "N", "South": "S"}
CLUSTER_M = 250        # nodes of one intersection (dual carriageways, wide junctions) lie within this
INTERSECTION_RADIUS_M = 75  # as the app's own corners in places.json, which win a tie and keep the app's names
STATION_RADIUS_M = 150
MIN_PARK_HA = 5


def distance_m(a, b):
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * 111320 * k, (a[1] - b[1]) * 110540)


def words(name):
    return re.sub(r"[^a-z0-9']+", " ", name.lower().replace("’", "'")).split()


def base_name(name):
    """The words of a street name without its type and direction, or the whole name when nothing distinctive is left."""
    full = words(name)
    w = list(full)
    while len(w) > 1 and (w[-1] in STREET_TYPES or w[-1] in DIRECTIONS):
        w.pop()
    if len(w) > 1 and w[0] == "the":
        w.pop(0)
    if w == ["the"] or w[-1] in STREET_TYPES or w[-1] in DIRECTIONS:
        # "The Esplanade" -> "esplanade"; "Avenue Road" and "East Avenue" keep both words, or "Lawrence East" would
        # read as Lawrence and East Avenue.
        w = [x for x in full if x != "the"]
    return " ".join(w)


def short_name(name):
    """Abbreviates street types after the first word and a direction at the end: "Queen Street West" -> "Queen St W",
    "East Avenue" -> "East Ave", "The West Mall" stays."""
    parts = name.split()
    return " ".join(word if i == 0 or (word.lower() in DIRECTIONS and i < len(parts) - 1) else ABBREVIATIONS.get(word, word)
                    for i, word in enumerate(parts))


def display_street(names):
    """One label for the OSM names of a street at a junction; Dundas St E and Dundas St W at Yonge become Dundas St."""
    if len(set(names)) == 1:
        return short_name(names[0])
    plain = [" ".join(w for w in short_name(n).split() if w not in ("E", "W", "N", "S")) for n in names]
    return Counter(plain).most_common(1)[0][0]


def intersections(ways):
    by_node = defaultdict(dict)  # node id -> {base name: full name}
    position = {}
    for way in ways:
        name = way["tags"]["name"].strip()
        for node, g in zip(way.get("nodes", []), way.get("geometry", [])):
            by_node[node].setdefault(base_name(name), []).append(name)
            position[node] = (g["lon"], g["lat"])

    pairs = defaultdict(list)  # (base a, base b) -> [(point, names a, names b)]
    for node, streets in by_node.items():
        bases = sorted(streets)
        for i, a in enumerate(bases):
            for b in bases[i + 1:]:
                pairs[(a, b)].append((position[node], streets[a], streets[b]))

    places, ambiguous = [], 0
    for (a, b), hits in pairs.items():
        clusters = []
        for hit in hits:
            for cluster in clusters:
                if distance_m(cluster[0][0], hit[0]) <= CLUSTER_M:
                    cluster.append(hit)
                    break
            else:
                clusters.append([hit])
        if len(clusters) > 1:
            # Two streets that cross more than once can't be placed from their names alone.
            ambiguous += 1
            continue
        cluster = clusters[0]
        lng = sum(h[0][0] for h in cluster) / len(cluster)
        lat = sum(h[0][1] for h in cluster) / len(cluster)
        name = f"{display_street([n for h in cluster for n in h[1]])} & {display_street([n for h in cluster for n in h[2]])}"
        places.append({"name": name, "kind": "intersection", "streets": [a, b],
                       "lng": round(lng, 5), "lat": round(lat, 5), "radius_m": INTERSECTION_RADIUS_M})
    return places, ambiguous


def stations(elements):
    found = {}
    for el in elements:
        tags = el.get("tags", {})
        if "station" not in (tags.get("railway"), tags.get("disused:railway")) and tags.get("railway") != "disused_station":
            continue
        name = re.sub(r"\s+(Station|Subway Station|GO Station|RT Station)$", "", tags.get("name", "").strip())
        point = (el.get("lon"), el.get("lat")) if el["type"] == "node" else (el.get("center", {}).get("lon"), el.get("center", {}).get("lat"))
        if not name or point[0] is None or name in found:
            continue
        closed = tags.get("railway") != "station"
        label = f"{name} Station" + (" (closed)" if closed else "")
        # "Ellesmere Station", "Ellesmere RT Station", "Union GO Station"... but never the bare name, which is often a street.
        aliases = [f"{name} {kind}station".replace("  ", " ") for kind in ("", "RT ", "SRT ", "subway ", "TTC ", "LRT ", "GO ", "UP Express ")]
        found[name] = {"name": label, "kind": "landmark", "aliases": aliases,
                       "lng": round(point[0], 5), "lat": round(point[1], 5), "radius_m": STATION_RADIUS_M}
    return list(found.values())


def parks(elements):
    found = {}
    for el in elements:
        tags, box = el.get("tags", {}), el.get("bounds")
        if tags.get("leisure") != "park" or not box or not tags.get("name"):
            continue
        sw, ne = (box["minlon"], box["minlat"]), (box["maxlon"], box["maxlat"])
        width, height = distance_m(sw, (ne[0], sw[1])), distance_m(sw, (sw[0], ne[1]))
        if width * height * 0.6 < MIN_PARK_HA * 10_000:  # a park fills roughly 60% of its bounding box
            continue
        name = tags["name"].strip()
        aliases = [name]
        short = re.sub(r"\s+Park$", "", name)
        if short != name and len(short.split()) >= 2:
            aliases.append(short)  # "Trinity Bellwoods", but not "High" from "High Park"
        radius = round(min(1000, max(150, math.hypot(width, height) / 2)))
        if name not in found or radius > found[name]["radius_m"]:
            found[name] = {"name": name, "kind": "landmark", "aliases": aliases,
                           "lng": round((sw[0] + ne[0]) / 2, 5), "lat": round((sw[1] + ne[1]) / 2, 5), "radius_m": radius}
    return list(found.values())


def main():
    request = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "CivicLens-HTV-prototype/0.1 (hackathon demo)"},
    )
    for attempt in range(3):  # the public Overpass server answers 429 / 502 / 504 when it is busy
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                elements = json.load(response)["elements"]
            break
        except urllib.error.HTTPError as error:
            if error.code not in (429, 502, 503, 504) or attempt == 2:
                raise
            print(f"Overpass is busy ({error.code}), retrying in {30 * (attempt + 1)} s")
            time.sleep(30 * (attempt + 1))

    ways = [el for el in elements if el["type"] == "way" and el.get("tags", {}).get("highway")]
    crossings, ambiguous = intersections(ways)
    station_places, park_places = stations(elements), parks(elements)
    write([p for group in (crossings, station_places, park_places) for p in sorted(group, key=lambda p: p["name"])])
    print(f"{len(ways)} road ways -> {len(crossings)} intersections ({ambiguous} street pairs crossing more than once left out), "
          f"{len(station_places)} stations, {len(park_places)} parks -> {OUT}")


def write(places):
    """One place per line, so a regenerated file diffs readably."""
    note = (f"Generated by scripts/fetch-osm-places.py on {datetime.date.today()} from OpenStreetMap "
            "(© OpenStreetMap contributors, ODbL 1.0). Do not edit by hand.")
    rows = ",\n  ".join(json.dumps(p, ensure_ascii=False, separators=(",", ":")) for p in places)
    OUT.write_text(f'{{\n "note": {json.dumps(note, ensure_ascii=False)},\n "places": [\n  {rows}\n ]\n}}\n', encoding="utf-8")


if __name__ == "__main__":
    main()
