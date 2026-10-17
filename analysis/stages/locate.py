"""Map-ready stage: place each record and attach its area and nearest infrastructure.

Values the input already has are kept unless [stages.locate] overwrite = true. Each step is
recorded in geo_trace, which the issue panel shows as "How this location was estimated".
"""
from ..record import fill, is_missing, point

NAME = "locate"


def run(records, settings, ref, report):
    overwrite = settings.get("overwrite", False)
    for record in records:
        trace = record.setdefault("geo_trace", [])
        if point(record) is None:
            trace.append({"stage": "Coordinates", "result": "None supplied with the photo or post", "status": "skip"})
            _from_text(record, settings, ref)
        elif record.get("provenance", {}).get("geometry") == "input":
            trace.append({"stage": "Coordinates", "result": "Supplied with the photo or post", "status": "match"})
            fill(record, "location_radius_m", settings.get("default_radius_m", 50), NAME)
            fill(record, "geo_confidence", settings.get("gps_geo_confidence"), NAME)
        p = point(record)
        if p is None:
            continue
        report["counts"]["located"] += 1

        for layer in ref.area_layers:
            # Area fields go together (an ID with its name), so input values for any of them keep the layer out.
            if not overwrite and any(not is_missing(record.get(f)) for f in layer.fields):
                continue
            found = ref.area_at(layer, p)
            if found:
                props, d = found
                for field, prop in layer.fields.items():
                    fill(record, field, props.get(prop), NAME, overwrite)
                where = f"Inside {layer.describe(props)}" if layer.match == "contains" else f"Nearest mapped place is in {layer.describe(props)} ({round(d)} m)"
                trace.append({"stage": "Area", "result": where, "status": "info"})

        # A nearest asset or street corner means nothing when the location is only known to the neighbourhood.
        if (record.get("location_radius_m") or 0) > settings.get("context_max_radius_m", 250):
            trace.append({"stage": "Nearby infrastructure", "result": "Location too coarse to measure distances", "status": "skip"})
            continue
        nearby = ref.nearest_assets(p)
        if nearby:
            fill(record, "nearby_assets", nearby, NAME, overwrite)
            if overwrite or is_missing(record.get("asset_name")):
                near = nearby[0]
                for field, key in (("infrastructure_type", "type"), ("asset_id", "asset_id"), ("asset_name", "name"), ("distance_m", "distance_m")):
                    fill(record, field, near[key], NAME, overwrite=True)
                trace.append({"stage": "Nearby infrastructure", "result": f"{near['name']} ({near['type']}) {near['distance_m']} m away", "status": "info"})
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
            record["geo_method"] = f"Place name in {label}"
            record["geo_trace"].append({"stage": "Place name", "result": f"“{place.name}” found in the {label}", "status": "match"})
            fill(record, "location_radius_m", place.radius_m, NAME)
            fill(record, "geo_confidence", settings.get("text_geo_confidence"), NAME)
            if place.kind != "area":
                fill(record, "address", place.name, NAME)
            return
    record["geo_trace"].append({"stage": "Place name", "result": "No known place named in the text", "status": "skip"})
