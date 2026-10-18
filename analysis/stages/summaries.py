"""Summaries stage: a short, neutral paragraph per area, written only from the area's stats.

Uses Gemini when GEMINI_API_KEY is set (environment or one of env_files) and falls back to a plain
template otherwise or on any error. Gemini results are cached by prompt so re-runs cost nothing.
"""
import hashlib
import json
import os
import urllib.request

from ..config import resolve

NAME = "summaries"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
LEVEL_LABELS = {"ward_id": "ward", "neighbourhood_id": "neighbourhood"}


def run(area_stats, settings, report, cache_path, offline=False, placeholder_areas=False):
    trend_days = area_stats.get("trend_days", 7)
    key = None if offline or not settings.get("use_gemini", True) else api_key(settings.get("env_files", []))
    cache = _read_cache(cache_path)
    for level in settings.get("levels", ["ward_id"]):
        for area in area_stats.get("by_area", {}).get(level, []):
            if area["total"] < settings.get("min_issues", 1):
                continue
            label = LEVEL_LABELS.get(level, "area")
            text, method = None, "template"
            if key:
                prompt = build_prompt(area, label, settings.get("max_words", 90), placeholder_areas, trend_days)
                digest = hashlib.sha256(f"{settings['model']}\n{prompt}".encode()).hexdigest()
                text = cache.get(digest)
                if text is None:
                    try:
                        text = call_gemini(prompt, settings["model"], key, settings.get("timeout_s", 30))
                        cache[digest] = text
                    except Exception as error:  # any failure falls back to the template
                        report["warnings"].append(f"Gemini summary for {label} {area['name']} failed: {type(error).__name__}")
                if text:
                    method = f"gemini:{settings['model']}"
            area["summary"] = {"text": text or template(area, label, placeholder_areas, trend_days), "method": method}
    _write_cache(cache_path, cache)


def display_name(area, label):
    if label == "ward" and str(area["name"]).isdigit():
        return f"Ward {area['name']}" + (f" ({area['label']})" if area.get("label") not in (None, str(area["name"])) else "")
    return str(area.get("label") or area["name"])


def build_prompt(area, label, max_words, placeholder_areas, trend_days):
    facts = {k: v for k, v in area.items() if k != "summary"}
    return (
        f"Write a short, neutral summary of civic infrastructure issues for residents of the Toronto {label} "
        f"\"{display_name(area, label)}\".\n"
        "Rules:\n"
        "- Use only the facts in the JSON below. Do not guess causes or add numbers that are not there.\n"
        "- Do not mention politicians, candidates, parties or the election, and do not tell people how to vote.\n"
        "- Say that the counts cover issues found in public photos and community submissions, not every issue in the area.\n"
        + ("- Say that the area boundaries are approximate.\n" if placeholder_areas else "")
        + f"- Plain text, at most {max_words} words, no lists or headings.\n"
        f"'new_recent' counts issues first seen in the last {trend_days} days and 'new_previous' the "
        "same length of time before that.\n\n"
        f"JSON:\n{json.dumps(facts, indent=1)}"
    )


def call_gemini(prompt, model, key, timeout_s):
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2}}
    request = urllib.request.Request(
        GEMINI_URL.format(model=model), data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        data = json.load(response)
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise ValueError("empty response")
    return text


def template(area, label, placeholder_areas, trend_days):
    name = display_name(area, label)
    types = ", ".join(f"{t.lower()} ({n})" for t, n in list(area["by_type"].items())[:3])
    parts = [f"{name} has {area['total']} {'issue' if area['total'] == 1 else 'issues'} in GeoIssue data, "
             f"{area['open']} still open. By type: {types}."]
    parts.append(f"{area['new_recent']} first seen in the last {trend_days} days, compared with {area['new_previous']} "
                 f"in the {trend_days} days before.")
    if area.get("top_priority"):
        top = area["top_priority"][0]
        parts.append(f"Highest priority: {top['issue_type'].lower()} at {top['address'] or 'an approximate location'}.")
    parts.append("Counts cover issues found in public photos and community submissions, not every issue in the area.")
    if placeholder_areas:
        parts.append("Area boundaries are approximate placeholders.")
    return " ".join(parts)


def api_key(env_files):
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    for file in env_files:
        path = resolve(file)
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                name, sep, value = line.partition("=")
                if sep and name.strip().removeprefix("export ").strip() == "GEMINI_API_KEY":
                    return value.strip().strip("'\"") or None
    return None


def _read_cache(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_cache(path, cache):
    if cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=1), encoding="utf-8")
