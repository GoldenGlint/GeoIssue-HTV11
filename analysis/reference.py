"""Toronto reference data: areas, infrastructure and named places.

The files are plain GeoJSON / JSON. The default set in analysis/refdata/toronto/ is exported from the
frontend (scripts/export-analysis-reference.mjs) so issues use the same neighbourhood, ward and asset
IDs as the map. See analysis/refdata/README.md for the formats and how to use official boundaries.
"""
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

from . import geo
from .config import resolve


def normalise_text(text):
    text = str(text).lower().replace("&", " and ").replace("’", "'")
    return " " + re.sub(r"[^a-z0-9']+", " ", text).strip() + " "


@dataclass
class AreaLayer:
    fields: dict      # output field -> feature property
    features: list    # [(bbox, geometry, properties)]
    match: str = "contains"
    max_distance_m: float = math.inf

    def describe(self, properties):
        return next((str(properties[p]) for p in self.fields.values() if "name" in p and properties.get(p)), "the area")


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
        folder = resolve(settings.get("reference", "analysis/refdata/toronto"))
        self.placeholder = False
        self.area_layers = []
        self.places = []
        for layer in settings.get("areas", []):
            data = self._load(folder / layer["file"])
            features = [(geo.bbox(f["geometry"]), f["geometry"], f.get("properties") or {}) for f in data["features"] if f.get("geometry")]
            area = AreaLayer(layer["fields"], features, layer.get("match", "contains"), layer.get("max_distance_m", math.inf))
            self.area_layers.append(area)
            if layer.get("search_name"):
                self._add_area_places(area, layer["search_name"])

        self.assets = []  # [(type, asset_id, name, geometry)]
        infra = settings.get("infrastructure")
        if infra:
            data = self._load(folder / infra["file"])
            for f in data["features"]:
                props = f.get("properties") or {}
                self.assets.append((props.get(infra.get("type_property", "type")), props.get(infra.get("id_property", "asset_id")),
                                    props.get(infra.get("name_property", "name")), f["geometry"]))

        if settings.get("places_file"):
            for p in self._load(folder / settings["places_file"]).get("places", []):
                self.places.append(Place(p["name"], p.get("kind", "place"), [p["lng"], p["lat"]], p.get("radius_m", 100),
                                         p.get("aliases", []), [normalise_text(t).strip() for t in p.get("match_all", [])]))

    def _load(self, path):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        self.placeholder = self.placeholder or bool(data.get("placeholder"))
        return data

    def _add_area_places(self, layer, name_property):
        """Makes area names findable in text: one place per name, centred on its features."""
        groups = defaultdict(list)
        for box, _, props in layer.features:
            if props.get(name_property):
                groups[props[name_property]].append(box)
        for name, boxes in groups.items():
            corners = [[b[0], b[1]] for b in boxes] + [[b[2], b[3]] for b in boxes]
            centre = [sum(c[0] for c in corners) / len(corners), sum(c[1] for c in corners) / len(corners)]
            radius = max(geo.distance_m(centre, c) for c in corners) + (400 if layer.match == "nearest" else 0)
            self.places.append(Place(name, "area", centre, round(max(radius, 500)), [name, re.sub(r"^the ", "", name, flags=re.I)]))

    def area_at(self, layer, point):
        """(feature properties, metres to the feature) for the area containing or nearest the point, or None."""
        if layer.match == "nearest":
            best = min(((props, geo.distance_to_geometry_m(point, geometry)) for _, geometry, props in layer.features),
                       key=lambda item: item[1], default=None)
            return best if best and best[1] <= layer.max_distance_m else None
        for box, geometry, props in layer.features:
            if geo.in_bbox(box, point) and geo.contains(geometry, point):
                return props, 0.0
        return None

    def nearest_assets(self, point):
        """The closest asset of each type as [{type, asset_id, name, distance_m}], nearest first."""
        nearest = {}
        for kind, asset_id, name, geometry in self.assets:
            d = geo.distance_to_geometry_m(point, geometry)
            if kind not in nearest or d < nearest[kind]["distance_m"]:
                nearest[kind] = {"type": kind, "asset_id": asset_id, "name": name, "distance_m": d}
        assets = sorted(nearest.values(), key=lambda a: a["distance_m"])
        for asset in assets:
            asset["distance_m"] = round(asset["distance_m"])
        return assets

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
