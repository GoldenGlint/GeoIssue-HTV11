# Flickr collector

Geographic photo search for Toronto areas. Requires a free application key in `FLICKR_API_KEY` ([.env.example](../.env.example)).

```sh
.venv/bin/python -m scraping.collectors.flickr \
  --config scraping/config/flickr.json \
  --output scraping/data/flickr-live
.venv/bin/python -m scraping.screen --batch scraping/data/flickr-live
```

Capture/`datetaken` values are stored as uncertain `date_evidence` only; `captured_at` stays null because Flickr may default taken time to upload time. Geotags are source location claims, not verified camera positions. Access status: [flickr-access-results.json](../research/results/flickr-access-results.json).
