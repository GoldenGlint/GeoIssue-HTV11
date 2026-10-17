"""Map-ready stage: place each record and attach its area and nearest infrastructure.

Values the input already has are kept unless [stages.locate] overwrite = true.
"""
from ..record import fill, is_missing, point

NAME = "locate"


def run(records, settings, ref, report):
    overwrite = settings.get("overwrite", False)
    for record in records:
        if point(record) is None:
            _from_text(record, settings, ref)
        p = point(record)
        if p is None:
            continue
        if record.get("provenance", {}).get("geometry") == "input":
            fill(record, "location_radius_m", settings.get("default_radius_m", 50), NAME)
            fill(record, "geo_confidence", settings.get("gps_geo_confidence"), NAME)
        report["counts"]["located"] += 1

        for layer in ref.area_layers:
            fill(record, layer.field, ref.area_name(layer, p), NAME, overwrite)

        # A nearest asset or street corner means nothing when the location is only known to the neighbourhood.
        if (record.get("location_radius_m") or 0) > settings.get("context_max_radius_m", 250):
            continue
        nearby = ref.nearest_assets(p)
        if nearby:
            record["nearby_assets"] = {kind: {"name": name, "distance_m": round(d)} for kind, (name, d) in sorted(nearby.items())}
            if overwrite or is_missing(record.get("asset_name")):
                kind, (name, d) = min(nearby.items(), key=lambda item: item[1][1])
                for field, value in (("infrastructure_type", kind), ("asset_name", name), ("distance_m", round(d))):
                    fill(record, field, value, NAME, overwrite=True)
        place = ref.nearest_place(p, ("intersection", "landmark"), settings.get("address_max_distance_m", 200))
        fill(record, "address", place.name if place else None, NAME, overwrite)


def _from_text(record, settings, ref):
    sources = [("location text", record.get("location_text")), ("location clues", record.get("location_clues"))]
    if settings.get("use_post_text", True):
        sources.append(("post text", record.get("post_text")))
    for label, text in sources:
        place = ref.match_place(text) if text else None
        if place:
            record["geometry"] = {"type": "Point", "coordinates": [round(c, 6) for c in place.point]}
            record["provenance"]["geometry"] = NAME
            record["geo_method"] = f"place named in {label}: {place.name}"
            fill(record, "location_radius_m", place.radius_m, NAME)
            fill(record, "geo_confidence", settings.get("text_geo_confidence"), NAME)
            if place.kind != "area":
                fill(record, "address", place.name, NAME)
            return
