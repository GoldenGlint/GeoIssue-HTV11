"""Source-independent image records, downloads, screening, and review exports."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import calendar
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit, urljoin

from PIL import Image, ImageOps
import requests

from .paths import REVIEW_TEMPLATE


@dataclass
class MediaRecord:
    platform: str
    collector: str
    post_id: str
    media_index: int
    media_url: str
    posted_at: str | None
    caption: str = ""
    alt_text: str = ""
    media_id: str | None = None
    location_evidence: list = field(default_factory=list)
    captured_at: str | None = None
    found_by: list = field(default_factory=list)
    schema_version: int = 1
    post_url: str | None = None

    def __post_init__(self):
        if (self.schema_version != 1 or not isinstance(self.platform, str)
                or not re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", self.platform)
                or not isinstance(self.collector, str) or not self.collector
                or not isinstance(self.post_id, str) or not self.post_id
                or not isinstance(self.media_url, str)
                or type(self.media_index) is not int or self.media_index < 0):
            raise ValueError("Invalid media identity or unsupported schema version.")
        if self.posted_at is not None:
            parse_time(self.posted_at)
        if self.captured_at is not None:
            parse_time(self.captured_at)

    @property
    def key(self):
        return f"{self.platform}:{self.post_id}:{self.media_index}"


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("Timestamps must be timezone-aware ISO strings.")
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Timestamps must include a timezone.")
    return date.astimezone(timezone.utc)


def assess_freshness(row, *, since=None, now=None):
    """Posting recency is not proof of current conditions; hints require review."""
    now = now or datetime.now(timezone.utc)
    since = since or now - timedelta(days=7)
    posted = parse_time(row["posted_at"]) if row.get("posted_at") else None
    captured = parse_time(row["captured_at"]) if row.get("captured_at") else None
    text = str(row.get("caption") or "")
    historical = bool(re.search(
        r"\b(?:throwback|tbt|archive[sd]?|historical|old photo|last (?:year|summer|winter)|(?:a|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+years?\s+ago)\b",
        text, re.I))
    # ponytail: explicit English date hints only; ambiguous text stays age-unknown, never verified fresh.
    for match in re.finditer(
            r"\b(Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|Sep\w*|Oct\w*|Nov\w*|Dec\w*)\.?,?\s+(?:['’](\d{2})|((?:19|20)\d{2}))\b", text, re.I):
        month = [name.lower() for name in calendar.month_abbr].index(match[1][:3].lower())
        year = 2000 + int(match[2]) if match[2] else int(match[3])
        if 1 <= year <= 9999:
            historical |= datetime(year, month, calendar.monthrange(year, month)[1], tzinfo=timezone.utc) < since
    if re.search(r"\b(?:taken|shot|captured|photographed)\b[^.!?\n]{0,45}\b(?:19|20)\d{2}\b", text, re.I):
        historical |= any(int(year) < since.year for year in re.findall(r"\b(?:19|20)\d{2}\b", text))
    if any(date and date > now + timedelta(minutes=5) for date in (posted, captured)):
        status = "future_timestamp_review"
    elif (captured and captured < since) or (posted and posted < since):
        status = "outside_window"
    elif historical:
        status = "historical_caption_review"
    elif not posted:
        status = "posting_time_unknown"
    else:
        status = "capture_time_recorded" if captured else "capture_time_unknown"
    return {"status": status, "assessed_at": now.isoformat(), "window_start": since.isoformat(), "alert_eligible": False,
            "alert_block_reason": "Current condition and location require verification."}


ISSUE_WORDS = re.compile(
    r"\b(?:pothole|sinkhole|sidewalk|bike ?lanes?|construct|closure|closed|block|obstruct|flood|"
    r"drain|sewer|overflow|spill|leak|garbage|trash|litter|dump|graffiti|vandal|shelter|broken|"
    r"damage|repair|crack|collapse|detour|collision|crash|hazard|unsafe|danger|remov|tear|demoli|"
    r"fire|stuck|outage|out of service|not working|abandon|encampment|scaffold|barrier|pylon|"
    r"cones?|311)", re.I)


def has_issue_words(row):
    """Free text check before Gemini: does the caption or alt text mention a problem?"""
    return bool(ISSUE_WORDS.search(f"{row.get('caption') or ''} {row.get('alt_text') or ''}"))


def redact_text(text):
    text = re.sub(r"https?://\S+", "[link]", str(text or ""))
    return re.sub(r"(?<!\w)@[\w.]+", "[account]", text)[:4000]


def read_jsonl(path):
    # Captions may contain U+2028/U+0085, which str.splitlines() would treat as record breaks.
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").split("\n") if line.strip()]


def source_post_url(row):
    """Turn the current collectors' native identities into browser links."""
    hosts = {
        "instagram": ("instagram.com",), "facebook": ("facebook.com",),
        "threads": ("threads.com", "threads.net"),
    }.get(row.get("platform"))
    explicit = row.get("post_url")
    if hosts and isinstance(explicit, str) and allowed_url(explicit, hosts):
        return explicit
    post_id = row.get("post_id") or ""
    if row.get("platform") == "bluesky":
        match = re.fullmatch(r"at://(did:[A-Za-z0-9:._-]+)/app\.bsky\.feed\.post/([A-Za-z0-9._~-]+)", post_id)
        return f"https://bsky.app/profile/{match[1]}/post/{match[2]}" if match else None
    if row.get("platform") in ("reddit", "mastodon"):
        parsed = urlsplit(post_id)
        if parsed.hostname and allowed_url(post_id, (parsed.hostname,)):
            return post_id
    return None


def _write_text(path, value):
    path = Path(path)
    # Readers must see a complete old or new manifest, including while a run saves progress.
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=f".{path.name}-") as folder:
        staged = Path(folder) / "content"
        staged.write_text(value, encoding="utf-8")
        staged.replace(path)


def write_json(path, value):
    _write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def write_jsonl(path, rows):
    _write_text(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def allowed_url(url, hosts):
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443) and any(
                parsed.hostname == host or (parsed.hostname or "").endswith("." + host)
                for host in hosts))


def fetch_image(url, hosts, max_bytes=8_000_000):
    for _ in range(4):
        if not allowed_url(url, hosts):
            raise ValueError("Image URL is outside the source's permitted HTTPS hosts.")
        with requests.get(url, timeout=(10, 20), stream=True, allow_redirects=False) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            if response.status_code != 200:
                raise ValueError(f"Image download returned HTTP {response.status_code}.")
            chunks, size = [], 0
            for chunk in response.iter_content(64_000):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Image exceeds the 8 MB download limit.")
                chunks.append(chunk)
            return b"".join(chunks)
    raise ValueError("Too many image redirects.")


def image_derivative(data):
    """Decode safely; retain dimensions/hash but discard EXIF and other metadata."""
    with Image.open(BytesIO(data)) as image:
        if image.format not in ("JPEG", "PNG", "WEBP", "AVIF"):
            raise ValueError("Unsupported photo format.")
        if image.width * image.height > 20_000_000:
            raise ValueError("Image exceeds the 20 megapixel decode limit.")
        image = ImageOps.exif_transpose(image).convert("RGB")
        dimensions = (image.width, image.height)
        exact_hash = hashlib.sha256(image.tobytes() + str(dimensions).encode()).hexdigest()
        small = image.convert("L").resize((9, 8)).tobytes()
        difference_hash = sum((small[y * 9 + x] > small[y * 9 + x + 1]) << (y * 8 + x)
                              for y in range(8) for x in range(8))
        image.thumbnail((1280, 1280))
        output = BytesIO()
        image.save(output, format="JPEG", quality=85, exif=b"")
    return output.getvalue(), dimensions, exact_hash, f"{difference_hash:016x}"


def process_media(records, output, *, hosts, since=None):
    """All adapters feed this same stage. It does not call a social-media API."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "images").mkdir(exist_ok=True)
    seen_keys, seen_pixels, hashes, rows = set(), {}, [], []
    for record in records:
        if record.key in seen_keys:
            continue
        seen_keys.add(record.key)
        row = {**asdict(record), "key": record.key, "fetched_at": None,
               "auto_status": "ready", "reasons": [],
               "local_path": None, "sha256": None, "dhash": None}
        row["caption"] = redact_text(row["caption"])
        row["alt_text"] = redact_text(row["alt_text"])
        row["freshness"] = assess_freshness(row, since=since)
        if since and record.captured_at and parse_time(record.captured_at) < since:
            row.update(auto_status="excluded", reasons=["capture_older_than_window"])
        elif since and record.posted_at and parse_time(record.posted_at) < since:
            row.update(auto_status="excluded", reasons=["older_than_posting_window"])
        else:
            try:
                data = fetch_image(record.media_url, hosts)
                jpeg, dimensions, digest, dhash = image_derivative(data)
                row.update(width=dimensions[0], height=dimensions[1], sha256=digest, dhash=dhash,
                           fetched_at=datetime.now(timezone.utc).isoformat())
                if digest in seen_pixels:
                    row.update(auto_status="excluded", reasons=["duplicate_image"],
                               duplicate_of=seen_pixels[digest])
                else:
                    seen_pixels[digest] = record.key
                    if min(dimensions) < 160:
                        row["reasons"].append("small_image_review")
                    if any((int(dhash, 16) ^ previous).bit_count() <= 4 for previous in hashes):
                        row["reasons"].append("similar_image_review")
                    hashes.append(int(dhash, 16))
                    row["local_path"] = f"images/{digest}.jpg"
                    (output / row["local_path"]).write_bytes(jpeg)
            except (ValueError, OSError, Image.DecompressionBombError, requests.RequestException) as exc:
                row.update(auto_status="download_failed", reasons=["image_download_failed"],
                           error_type=type(exc).__name__)
        rows.append(row)
    write_jsonl(output / "media.jsonl", rows)
    return rows


def export_reviewed(rows, labels):
    """Require explicit human approval; a downloaded image is never auto-approved."""
    if not isinstance(labels, list):
        raise ValueError("Review file must contain a list of labels.")
    indexed = {row["key"]: row for row in rows}
    accepted, seen = [], set()
    for label in labels:
        key = label.get("key")
        if key not in indexed or key in seen:
            raise ValueError("Review contains an unknown or repeated image key.")
        seen.add(key)
        if label.get("scene_label") not in ("useful", "noise", "uncertain", "unreviewed"):
            raise ValueError("Unsupported scene label.")
        if label.get("issue_label") not in ("visible", "none", "uncertain"):
            raise ValueError("Unsupported issue label.")
        if label.get("people", "") not in ("", "yes", "no"):
            raise ValueError("Unsupported people label.")
        if (label["scene_label"] == "useful" and indexed[key]["auto_status"] == "ready"
                and label.get("draft") is not True):
            # Identifiable people stay in the private set but must be blurred before external use.
            accepted.append({**indexed[key], "freshness": assess_freshness(indexed[key]), "review": label,
                             "blur_required": label.get("people") == "yes"})
    return accepted


def gallery_screening(item):
    """Fields the read-only viewer needs, from either a full or compact screening row."""
    if not isinstance(item, dict):
        return None
    assessment = item.get("assessment") or {}
    issue = assessment.get("issue") or {}
    place = assessment.get("locatability") or {}
    toronto = assessment.get("toronto") or {}
    return {
        "passed": bool(item.get("passed")),
        "issue_type": item.get("issue_type") or issue.get("type") or "",
        "issue_evidence": item.get("issue_evidence") or issue.get("evidence") or "",
        "location_guess": item.get("location_guess") or place.get("location_guess") or "",
        "clues": item.get("clues") if isinstance(item.get("clues"), list) else (place.get("clues") or []),
        "toronto_evidence": item.get("toronto_evidence") if isinstance(item.get("toronto_evidence"), list)
                            else (toronto.get("evidence") or []),
        "locatability": item.get("locatability") or place.get("level") or "",
    }


def write_gallery(output, rows, metadata, *, post_groups=None):
    output = Path(output)
    screening = {}
    screening_path = output / "screening.jsonl"
    if screening_path.is_file():
        for item in read_jsonl(screening_path):
            if item.get("key"):
                screening[item["key"]] = gallery_screening(item)
    shown = []
    for row in rows:
        attached = row.get("screening") or screening.get(row.get("key"))
        if not attached or not attached.get("passed"):
            continue
        # Handoff rows are shown verbatim so the preview matches the model input.
        shown.append(row if row.get("screening") else
                     {**row, "freshness": assess_freshness(row), "screening": attached})
    unscreened = not screening and not any((row.get("screening") or {}).get("passed") for row in rows)
    metadata = {**metadata, "unscreened": unscreened, "passed": len(shown)}
    # Private local viewer. Rejected images are not included.
    payload = {"records": shown, "metadata": metadata}
    if post_groups is not None:
        payload["post_groups"] = post_groups
    text = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    (output / "data.js").write_text("window.REVIEW_DATA = " + text + ";\n", encoding="utf-8")
    (output / "index.html").write_text(REVIEW_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(output / "report.json", {
        **metadata, "images": len(rows),
        "ready": sum(row["auto_status"] == "ready" for row in rows),
        "excluded": sum(row["auto_status"] == "excluded" for row in rows),
        "download_failed": sum(row["auto_status"] == "download_failed" for row in rows),
        "downloaded": sum(bool(row.get("fetched_at")) for row in rows),
        "unknown_posted_at": sum(not row.get("posted_at") for row in rows),
        "with_place_tag": sum(bool(row.get("location_evidence")) for row in rows),
        "unique_image_posts": len({(row["platform"], row["post_id"]) for row in rows}),
    })
