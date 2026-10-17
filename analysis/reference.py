"""Toronto reference data: area polygons, infrastructure and named places.

The files are plain GeoJSON / JSON so real Toronto Open Data files can replace the placeholders by
changing [stages.locate] in config.toml. See analysis/refdata/README.md for the formats.
"""
import json
import math
import re
from dataclasses import dataclass, field

from . import geo
from .config import resolve


def normalise_text(text):
    text = str(text).lower().replace("&", " and ").replace("’", "'")
    return " " + re.sub(r"[^a-z0-9']+", " ", text).strip() + " "


@dataclass
class AreaLayer:
    field: str
    features: list  # [(bbox, geometry, name)]
    searchable: bool = False


@dataclass
class Place:
    name: str
    kind: str
    point: list
    radius_m: float
    aliases: list = field(default_factory=list)
    match_all: list = field(default_factory=list)

    def matches(self, normalised):
        if self.match_all and all(f" {token} " in normalised for token in self.match_all):
            return True
        return any(normalise_text(alias) in normalised for alias in self.aliases)


class Reference:
    def __init__(self, settings):
        folder = resolve(settings.get("reference", "analysis/refdata/placeholder"))
        self.placeholder = False
        self.area_layers = []
        for layer in settings.get("areas", []):
            data = self._load(folder / layer["file"])
            features = [(geo.bbox(f["geometry"]), f["geometry"], f["properties"].get(layer["name_property"]))
                        for f in data["features"] if f.get("geometry")]
            self.area_layers.append(AreaLayer(layer["field"], features, layer.get("searchable", False)))

        self.assets = []  # [(type, name, geometry)]
        infra = settings.get("infrastructure")
        if infra:
            data = self._load(folder / infra["file"])
            self.assets = [(f["properties"].get(infra.get("type_property", "type")), f["properties"].get(infra.get("name_property", "name")), f["geometry"])
                           for f in data["features"] if f.get("geometry")]

        self.places = []
        if settings.get("places_file"):
            data = self._load(folder / settings["places_file"])
            for p in data.get("places", []):
                self.places.append(Place(p["name"], p.get("kind", "place"), [p["lng"], p["lat"]], p.get("radius_m", 100),
                                         p.get("aliases", []), [normalise_text(t).strip() for t in p.get("match_all", [])]))
        for layer in self.area_layers:
            if layer.searchable:
                for box, _, name in layer.features:
                    centre = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
                    radius = geo.distance_m(centre, box[2:]) if name else 0
                    self.places.append(Place(name, "area", centre, round(radius), [name, re.sub(r"^the ", "", name, flags=re.I)]))

    def _load(self, path):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        self.placeholder = self.placeholder or bool(data.get("placeholder"))
        return data

    def area_name(self, layer, point):
        for box, geometry, name in layer.features:
            if geo.in_bbox(box, point) and geo.contains(geometry, point):
                return name
        return None

    def nearest_assets(self, point):
        """{type: (name, distance in metres)} for the closest asset of each type."""
        nearest = {}
        for kind, name, geometry in self.assets:
            d = geo.distance_to_geometry_m(point, geometry)
            if kind not in nearest or d < nearest[kind][1]:
                nearest[kind] = (name, d)
        return nearest

    def match_place(self, text):
        """The most precise place named in the text, or None."""
        normalised = normalise_text(text)
        found = [p for p in self.places if p.matches(normalised)]
        return min(found, key=lambda p: p.radius_m) if found else None

    def nearest_place(self, point, kinds, max_m):
        best, best_d = None, math.inf
        for place in self.places:
            if place.kind in kinds:
                d = geo.distance_m(point, place.point)
                if d < best_d:
                    best, best_d = place, d
        return best if best_d <= max_m else None
