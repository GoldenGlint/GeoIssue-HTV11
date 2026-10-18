# GeoIssue on one Vultr VM

Ubuntu 24.04, Python 3.12, Caddy, and systemd. The site and the Gemini API listen on `127.0.0.1:5173`. Caddy is the only public HTTP entry. Ingestion is a manual command. `geoissue-ingest.timer` is installed and left **disabled**; turn it on only when a daily run is wanted.

Published issues and photos live in `/var/lib/geoissue/published`, outside the Git checkout, so `git pull` does not touch them.

## Before you start

- A Vultr account and a small Cloud Compute plan (2 GB RAM is the starting size).
- An SSH public key, and a hostname you can point at the VM.
- `GEMINI_API_KEY` and `TIGER_DATABASE_URL`. They go in `/etc/geoissue/env` on the server, never in Git or chat.

In the Vultr firewall and on the VM, allow SSH from the team plus public TCP 80 and 443. Do not expose port 5173.

## Install

```sh
sudo apt-get update
sudo apt-get install -y python3 python3-venv caddy
sudo useradd --system --home-dir /var/lib/geoissue --shell /usr/sbin/nologin geoissue
sudo mkdir -p /opt/geoissue /var/lib/geoissue/published /etc/geoissue
sudo chown geoissue:geoissue /opt/geoissue /var/lib/geoissue /var/lib/geoissue/published
sudo -u geoissue git clone https://github.com/GoldenGlint/HTV-2026-BDO.git /opt/geoissue
sudo -u geoissue python3 -m venv /opt/geoissue/.venv
sudo -u geoissue /opt/geoissue/.venv/bin/pip install \
  -r /opt/geoissue/scraping/requirements.txt \
  -r /opt/geoissue/analysis/requirements-tiger.txt
```

Node is not required on the server. The committed frontend is static.

Write `/etc/geoissue/env` (mode `640`, owner `root`, group `geoissue`):

```
GEMINI_API_KEY=...
TIGER_DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/tsdb?sslmode=require
GEOISSUE_PUBLISHED_DIR=/var/lib/geoissue/published
GEOISSUE_DOMAIN=geoissue.example.com
```

Initialize Tiger Data only when that database has no GeoIssue schema. This keeps existing team data:

```sh
sudo -u geoissue bash -lc 'set -a; . /etc/geoissue/env; set +a; cd /opt/geoissue; .venv/bin/python -m analysis.tiger init'
```

## Seed the site before the first collection

The committed public snapshot is the site until a cloud run succeeds. It is not proof that collection is live.

```sh
sudo -u geoissue mkdir -p /var/lib/geoissue/published/generations/initial/photos
sudo -u geoissue cp /opt/geoissue/data/analyzed/issues.public.json \
  /opt/geoissue/data/analyzed/report.json \
  /opt/geoissue/data/analyzed/areas.json \
  /var/lib/geoissue/published/generations/initial/
sudo -u geoissue cp -a /opt/geoissue/data/analyzed/photos/. \
  /var/lib/geoissue/published/generations/initial/photos/
sudo -u geoissue ln -sfn generations/initial /var/lib/geoissue/published/current
```

Optional: copy local screening and description caches into `scraping/data/` on the server (`issue-details-cache.jsonl` and any `screening.jsonl`) so the first run does not pay again for images that were already assessed.

## Services, DNS, HTTPS

```sh
sudo cp /opt/geoissue/deploy/geoissue.service /etc/systemd/system/
sudo cp /opt/geoissue/deploy/geoissue-ingest.service /etc/systemd/system/
sudo cp /opt/geoissue/deploy/geoissue-ingest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now geoissue.service
```

Do not enable `geoissue-ingest.timer` here.

Point DNS at the VM and install the Caddyfile. Caddy replaces `{$GEOISSUE_DOMAIN}` from its own environment, so the API key and database URL stay out of the Caddy process:

```sh
sudo cp /opt/geoissue/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl edit caddy
```

```
[Service]
Environment=GEOISSUE_DOMAIN=geoissue.example.com
```

```sh
sudo systemctl restart caddy
```

Open `https://geoissue.example.com` from another device. Check that an evidence photo loads and that `https://geoissue.example.com/data/analyzed/issues.json` is 404.

## Ingestion

Defaults are 20 new screening requests and 20 new descriptions. The first manual run can use a larger budget:

```sh
sudo -u geoissue bash -lc 'set -a; . /etc/geoissue/env; set +a; cd /opt/geoissue; \
  .venv/bin/python scripts/ingest.py --max-screen-requests 150 --max-description-requests 60'
```

Confirm the new files under `/var/lib/geoissue/published/current` and the Tiger Data issue count. Later one-off runs can use the service, which keeps the default budget:

```sh
sudo systemctl start geoissue-ingest.service
```

A second run does not overlap: the service is a oneshot, and `ingest.py` takes an exclusive lock. A workflow lock left by a killed process is removed at the start of the next ingest.

### Daily timer, off until you enable it

```sh
sudo systemctl enable --now geoissue-ingest.timer   # once a day; missed days are not replayed
sudo systemctl disable --now geoissue-ingest.timer  # back to manual only
systemctl is-enabled geoissue-ingest.timer          # should print "disabled" after install
```

## Updates

```sh
sudo systemctl stop geoissue-ingest.service
sudo -u geoissue git -C /opt/geoissue pull
sudo -u geoissue /opt/geoissue/.venv/bin/pip install \
  -r /opt/geoissue/scraping/requirements.txt \
  -r /opt/geoissue/analysis/requirements-tiger.txt
sudo systemctl restart geoissue.service
```

Published generations are outside the checkout and stay put. If the timer was enabled, stop it before the pull and start it again only after the web service is healthy. Leave it disabled when it was already disabled.

## Logs

```sh
journalctl -u geoissue.service -u geoissue-ingest.service --since "today"
```

## Rollback

List generations and point the site at the previous one. This swaps files only.

```sh
sudo -u geoissue ls /var/lib/geoissue/published/generations
sudo -u geoissue bash -lc 'set -a; . /etc/geoissue/env; set +a; cd /opt/geoissue; \
  .venv/bin/python scripts/ingest.py --republish GENERATION_NAME'
```

If the database must match that generation again, resync from its saved files (this replaces the pipeline dataset):

```sh
sudo -u geoissue bash -lc 'set -a; . /etc/geoissue/env; set +a; cd /opt/geoissue; .venv/bin/python -' <<'PY'
import json
from pathlib import Path
from analysis.tiger import prepare_sightings, sync
gen = Path("/var/lib/geoissue/published/generations/GENERATION_NAME")
public = json.loads((gen / "issues.public.json").read_text())
issues = json.loads((gen / "issues.json").read_text())
sightings = json.loads((gen / "sightings.json").read_text())
report = json.loads((gen / "report.json").read_text())
areas = json.loads((gen / "areas.json").read_text())
print(sync(public, prepare_sightings(issues, sightings), report, areas))
PY
```

A failed ingest deletes its unpublished candidate and leaves `current` where it was. If the database committed and the file swap failed, the error names the generation; `--republish` finishes the swap.

## Teardown

```sh
sudo systemctl disable --now geoissue.service geoissue-ingest.timer
sudo systemctl stop geoissue-ingest.service
sudo rm /etc/systemd/system/geoissue.service /etc/systemd/system/geoissue-ingest.service /etc/systemd/system/geoissue-ingest.timer
sudo systemctl daemon-reload
sudo rm -rf /opt/geoissue /var/lib/geoissue /etc/geoissue
sudo userdel geoissue
```

Destroy the Vultr instance and remove the DNS record. Tiger Data is separate; delete that service only when the team is finished with it.

## Record after a launch

Fill this in on the server copy or in the team's notes (not secrets):

| | |
| --- | --- |
| Public URL | |
| Deployed commit | `git -C /opt/geoissue rev-parse --short HEAD` |
| Last successful ingest | `curl -s https://HOST/api/status` |
| Web restart | `sudo systemctl restart geoissue.service` |
| File rollback | `python scripts/ingest.py --republish GENERATION_NAME` |
