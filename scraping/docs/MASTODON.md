# Mastodon collector

Anonymous media hashtag timelines on a configured instance. No login. Sensitive posts and boosts are skipped. Images go through the shared pipeline, then Gemini screening.

```sh
.venv/bin/python -m scraping.collectors.mastodon \
  --config scraping/config/mastodon.json \
  --output scraping/data/mastodon-live
.venv/bin/python -m scraping.screen --batch scraping/data/mastodon-live
```

Edit tags and caps in [mastodon.json](../config/mastodon.json). Attachment hosts are allowlisted from known Mastodon CDN patterns; unexpected hosts are rejected. Prior access probe: [mastodon-access-results.json](../research/results/mastodon-access-results.json).
