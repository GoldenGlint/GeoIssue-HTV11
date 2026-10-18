# CivicLens on one Vultr VM

Ubuntu 24.04, Python 3.12, Caddy, and systemd. The site and the Gemini API listen on `127.0.0.1:5173`. Caddy is the only public HTTP entry. Ingestion is a manual command. `civiclens-ingest.timer` is installed and left **disabled**; turn it on only when a daily run is wanted.

Published issues and photos live in `/var/lib/civiclens/published`, outside the Git checkout, so `git pull` does not touch them.

## Before you start

- A Vultr account and a small Cloud Compute plan (2 GB RAM is the starting size).
- An SSH public key, and a hostname you can point at the VM.
- `GEMINI_API_KEY` and `TIGER_DATABASE_URL`. They go in `/etc/civiclens/env` on the server, never in Git or chat.

In the Vultr firewall and on the VM, allow SSH from the team plus public TCP 80 and 443. Do not expose port 5173.

## Install

```sh
sudo apt-get update
sudo apt-get install -y python3 python3-venv caddy
sudo useradd --system --home-dir /var/lib/civiclens --shell /usr/sbin/nologin civiclens
sudo mkdir -p /opt/civiclens /var/lib/civiclens/published /etc/civiclens
sudo chown civiclens:civiclens /opt/civiclens /var/lib/civiclens /var/lib/civiclens/published
sudo -u civiclens git clone https://github.com/GoldenGlint/HTV-2026-BDO.git /opt/civiclens
sudo -u civiclens python3 -m venv /opt/civiclens/.venv
sudo -u civiclens /opt/civiclens/.venv/bin/pip install \
  -r /opt/civiclens/scraping/requirements.txt \
  -r /opt/civiclens/analysis/requirements-tiger.txt
```

Node is not required on the server. The committed frontend is static.

Write `/etc/civiclens/env` (mode `640`, owner `root`, group `civiclens`):

```
GEMINI_API_KEY=...
TIGER_DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/tsdb?sslmode=require
CIVICLENS_PUBLISHED_DIR=/var/lib/civiclens/published
CIVICLENS_DOMAIN=civiclens.example.com
```

Initialize Tiger Data only when that database has no CivicLens schema. This keeps existing team data:

```sh
sudo -u civiclens bash -lc 'set -a; . /etc/civiclens/env; set +a; cd /opt/civiclens; .venv/bin/python -m analysis.tiger init'
```

## Seed the site before the first collection

The committed public snapshot is the site until a cloud run succeeds. It is not proof that collection is live.

```sh
sudo -u civiclens mkdir -p /var/lib/civiclens/published/generations/initial/photos
sudo -u civiclens cp /opt/civiclens/data/analyzed/issues.public.json \
  /opt/civiclens/data/analyzed/report.json \
  /opt/civiclens/data/analyzed/areas.json \
  /var/lib/civiclens/published/generations/initial/
sudo -u civiclens cp -a /opt/civiclens/data/analyzed/photos/. \
  /var/lib/civiclens/published/generations/initial/photos/
sudo -u civiclens ln -sfn generations/initial /var/lib/civiclens/published/current
```

Optional: copy local screening and description caches into `scraping/data/` on the server (`issue-details-cache.jsonl` and any `screening.jsonl`) so the first run does not pay again for images that were already assessed.

## Services, DNS, HTTPS

```sh
sudo cp /opt/civiclens/deploy/civiclens.service /etc/systemd/system/
sudo cp /opt/civiclens/deploy/civiclens-ingest.service /etc/systemd/system/
sudo cp /opt/civiclens/deploy/civiclens-ingest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now civiclens.service
```

Do not enable `civiclens-ingest.timer` here.

Point DNS at the VM and install the Caddyfile. Caddy replaces `{$CIVICLENS_DOMAIN}` from its own environment, so the API key and database URL stay out of the Caddy process:

```sh
sudo cp /opt/civiclens/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl edit caddy
```

```
[Service]
Environment=CIVICLENS_DOMAIN=civiclens.example.com
```

```sh
sudo systemctl restart caddy
```

Open `https://civiclens.example.com` from another device. Check that an evidence photo loads and that `https://civiclens.example.com/data/analyzed/issues.json` is 404.

## Ingestion

Defaults are 20 new screening requests and 20 new descriptions. The first manual run can use a larger budget:

```sh
sudo -u civiclens bash -lc 'set -a; . /etc/civiclens/env; set +a; cd /opt/civiclens; \
  .venv/bin/python scripts/ingest.py --max-screen-requests 150 --max-description-requests 60'
```

Confirm the new files under `/var/lib/civiclens/published/current` and the Tiger Data issue count. Later one-off runs can use the service, which keeps the default budget:

```sh
sudo systemctl start civiclens-ingest.service
```

A second run does not overlap: the service is a oneshot, and `ingest.py` takes an exclusive lock. A workflow lock left by a killed process is removed at the start of the next ingest.

### Daily timer, off until you enable it

```sh
sudo systemctl enable --now civiclens-ingest.timer   # once a day; missed days are not replayed
sudo systemctl disable --now civiclens-ingest.timer  # back to manual only
systemctl is-enabled civiclens-ingest.timer          # should print "disabled" after install
```

## Updates

```sh
sudo systemctl stop civiclens-ingest.service
sudo -u civiclens git -C /opt/civiclens pull
sudo -u civiclens /opt/civiclens/.venv/bin/pip install \
  -r /opt/civiclens/scraping/requirements.txt \
  -r /opt/civiclens/analysis/requirements-tiger.txt
sudo systemctl restart civiclens.service
```

Published generations are outside the checkout and stay put. If the timer was enabled, stop it before the pull and start it again only after the web service is healthy. Leave it disabled when it was already disabled.

## Logs

```sh
journalctl -u civiclens.service -u civiclens-ingest.service --since "today"
```

## Rollback

List generations and point the site at the previous one. This swaps files only.

```sh
sudo -u civiclens ls /var/lib/civiclens/published/generations
sudo -u civiclens bash -lc 'set -a; . /etc/civiclens/env; set +a; cd /opt/civiclens; \
  .venv/bin/python scripts/ingest.py --republish GENERATION_NAME'
```

If the database must match that generation again, resync from its saved files (this replaces the pipeline dataset):

```sh
sudo -u civiclens bash -lc 'set -a; . /etc/civiclens/env; set +a; cd /opt/civiclens; .venv/bin/python -' <<'PY'
import json
from pathlib import Path
from analysis.tiger import prepare_sightings, sync
gen = Path("/var/lib/civiclens/published/generations/GENERATION_NAME")
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
sudo systemctl disable --now civiclens.service civiclens-ingest.timer
sudo systemctl stop civiclens-ingest.service
sudo rm /etc/systemd/system/civiclens.service /etc/systemd/system/civiclens-ingest.service /etc/systemd/system/civiclens-ingest.timer
sudo systemctl daemon-reload
sudo rm -rf /opt/civiclens /var/lib/civiclens /etc/civiclens
sudo userdel civiclens
```

Destroy the Vultr instance and remove the DNS record. Tiger Data is separate; delete that service only when the team is finished with it.

## Record after a launch

Fill this in on the server copy or in the team's notes (not secrets):

| | |
| --- | --- |
| Public URL | |
| Deployed commit | `git -C /opt/civiclens rev-parse --short HEAD` |
| Last successful ingest | `curl -s https://HOST/api/status` |
| Web restart | `sudo systemctl restart civiclens.service` |
| File rollback | `python scripts/ingest.py --republish GENERATION_NAME` |
