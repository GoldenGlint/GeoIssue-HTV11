# Reference data

`toronto/` is generated from the frontend's `src/data.js`:

```sh
node scripts/export-analysis-reference.mjs
```

Re-run it whenever the neighbourhoods, wards or infrastructure in `src/data.js` change, so analyzed issues keep the same IDs as the map. The export contains:

- `neighbourhoods.geojson`: one point per sample street corner, with `neighbourhood_id`, `neighbourhood_name`, `ward_id` and `ward_name`. Issues take the values of the nearest corner within 2.5 km. This is approximate, so the file carries `"placeholder": true`, and that marks every output as placeholder.
- `infrastructure.geojson`: the map's assets with `asset_id`, `type` (`TTC`, `Schools` or `Roads`) and `name`, as Point or MultiLineString features.
- `places.json`: the same street corners plus the TTC stations (matched only as their whole name, such as "Queen Station"), for finding places named in post text and for display addresses.

## Using official boundaries

Add a `[[stages.locate.areas]]` block to `analysis/config.toml` for each GeoJSON file of Polygon or MultiPolygon features, placed **above** the existing block, because the first layer to set a field wins. For example, with the City's ward boundaries:

```toml
[[stages.locate.areas]]
file = "wards.geojson"
match = "contains"
fields = { ward_id = "AREA_SHORT_CODE", ward_name = "AREA_NAME" }
```

`fields` maps each output field to the feature property that holds it. Check the property names in the file you download. Keep IDs consistent with the frontend: ward IDs are `"1"` to `"25"`, and neighbourhood IDs must exist in `src/data.js` to appear in the area filter.

## places.json format

`{"places": [{"name", "kind", "lng", "lat", "radius_m", "match_all" | "aliases"}]}`

- `kind` is `intersection` or `landmark`.
- An intersection matches when every phrase in `match_all` appears in the text, for example `["queen", "spadina"]`.
- A landmark matches any phrase in `aliases`.
- The nearest intersection or landmark within 200 m becomes the display address.
