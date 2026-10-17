# Reddit collector (Arctic Shift)

Updated October 17, 2026. Collects recent photo posts from Toronto subreddits through the [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift) API. It needs no key, no Reddit login and no paid service.

```sh
.venv/bin/python -m scraping.probe_queries reddit          # rank subreddits, no downloads
.venv/bin/python -m scraping.collectors.reddit --output scraping/data/reddit-live
.venv/bin/python -m scraping.screen --batch scraping/data/reddit-live --max-requests 150
```

Configuration is in [config/reddit.json](../config/reddit.json): subreddits, a 1–7 day window for the live pool, and caps on posts per subreddit, images per post and images per run.

## What it keeps

- Single-image posts and galleries hosted on `i.redd.it`. Gallery order is preserved, and animated images are skipped.
- Caption = title plus body text, with links and `u/` names redacted. The post flair (for example "Picture") goes in `alt_text`.
- Skipped: NSFW or spoiler posts, posts already removed by moderators or Reddit, crossposts, link posts, and posts outside the window.
- `found_by` records the subreddit, so `probe_queries` and screening results can be compared per source.

## Measured on October 17, 2026 (7-day window)

| Subreddit | Posts | Photo posts | Images | Problem-word images |
| --- | ---: | ---: | ---: | ---: |
| r/toronto | 499 | 106 | 203 | 50 |
| r/TTC | 55 | 22 | 41 | 3 |
| r/scarborough | 21 | 5 | 10 | 1 |
| r/etobicoke | 60 | 4 | 7 | 0 |

r/TorontoDriving, r/askTO, r/bikeTO, r/northyork and r/Mississauga had almost no photo posts. The newest archived r/toronto post was minutes old, so the archive is close to real time.

About one in five image links returned 404 at download time. Those are mostly photos deleted after posting, and they are recorded as `download_failed`.

Arctic Shift sometimes answers with HTTP 422; the collector retries up to three times.

## Terms

Arctic Shift is a third-party archive of Reddit. Reddit's terms restrict reuse of its data, especially for AI training. Treat this as hackathon prototype input, and check the terms before any product use.
