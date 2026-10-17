# Reference data

Most of `toronto/` is generated from the frontend's `src/data.js` and `src/ward-boundaries.js`:

```sh
node scripts/export-analysis-reference.mjs
```

Re-run it whenever the neighbourhoods, wards or infrastructure in `src/data.js` change, so analyzed issues keep the same IDs as the map. The export contains:

- `wards.geojson`: the City's 25 ward boundaries, as the map draws them. An issue gets the ward that contains it.

- `neighbourhoods.geojson`: one point per sample street corner, with `neighbourhood_id` and `neighbourhood_name` (and the corner's sample ward, which the wards file overrides). Issues take the neighbourhood of the nearest corner within 2.5 km. This is approximate, so the file carries `"placeholder": true`, and that marks every output as placeholder.
- `infrastructure.geojson`: the map's assets with `asset_id`, `type` (`TTC`, `Schools` or `Roads`) and `name`, as Point or MultiLineString features.
- `places.json`: the same street corners plus the TTC stations (matched only as their whole name, such as "Queen Station"), for finding places named in post text and for display addresses.

`osm-places.json` comes from OpenStreetMap instead: 2,583 named intersections of arterial roads, 136 rail and transit stations (closed ones too, such as the Line 3 stations, as "Ellesmere Station (closed)") and 311 parks of 5 ha or more. Regenerate it with `python scripts/fetch-osm-places.py`. The two place files are searched together, and on a tie the app's own corner in `places.json` wins, so addresses match the map's names.

## Using official boundaries

Add a `[[stages.locate.areas]]` block to `analysis/config.toml` for each GeoJSON file of Polygon or MultiPolygon features, placed **above** the existing blocks, because the first layer to set a field wins. The ward boundaries are already set up this way. For example, with the City's neighbourhood polygons:

```toml
[[stages.locate.areas]]
file = "neighbourhoods-official.geojson"
match = "contains"
fields = { neighbourhood_id = "AREA_SHORT_CODE", neighbourhood_name = "AREA_NAME" }
```

`fields` maps each output field to the feature property that holds it. Check the property names in the file you download. Keep IDs consistent with the frontend: ward IDs are `"1"` to `"25"`, and neighbourhood IDs must exist in `src/data.js` to appear in the area filter.

## Place file format

`{"places": [{"name", "kind", "lng", "lat", "radius_m", "streets" | "match_all" | "aliases"}]}`, listed in `places_files` in `analysis/config.toml`.

- `kind` is `intersection` or `landmark`.
- An intersection with `streets`, for example `["queen", "spadina"]`, matches when the two names appear together: "Queen and Spadina", "Queen St W & Spadina Ave", "Queen/Spadina". Street types, directions and words such as "at" or "between" may come between them.
- With `match_all`, every phrase only has to appear somewhere in the text.
- The most precise place named wins, and between equally precise places the one named first.
- A landmark matches any phrase in `aliases`.
- The nearest intersection or landmark within 200 m becomes the display address.
