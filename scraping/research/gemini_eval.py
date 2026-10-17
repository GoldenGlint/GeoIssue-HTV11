"""One-time automatic check of Gemini screening against human labels.

No new human labelling. Screens combined-demo once, compares with labels.json,
and writes a sanitized report. Does not print captions, image bytes, or keys.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from ..media import read_jsonl, write_json
from ..paths import DATA, ROOT
from .. import screen

KNOWN_TRAPS = {
    # Seattle bike-lane posts labelled outside_toronto / noise in the review set.
    "outside_toronto",
    "poster",
    "screenshot",
    "food",
}


def human_useful(label):
    return label.get("scene_label") == "useful" and label.get("draft") is not True


def load_labels(path):
    data = json.loads(Path(path).read_text())
    items = data["labels"] if isinstance(data, dict) else data
    return {item["key"]: item for item in items}


def evaluate(batch, *, max_requests=200, model=None):
    batch = Path(batch)
    labels = load_labels(batch / "labels.json")
    report = screen.screen_batch(batch, model=model, max_requests=max_requests, prefilter=False)
    screening = {row["key"]: row for row in read_jsonl(batch / "screening.jsonl")}
    media = {row["key"]: row for row in read_jsonl(batch / "media.jsonl")}

    compared = agreement = false_keep = false_reject = 0
    trap_keeps = []
    drain_hits = []
    for key, label in labels.items():
        if label.get("draft") is True or key not in screening or key not in media:
            continue
        result = screening[key]
        compared += 1
        model_keep = result["decision"] == "keep"
        human_keep = human_useful(label)
        if model_keep == human_keep:
            agreement += 1
        elif model_keep:
            false_keep += 1
        else:
            false_reject += 1
        if label.get("noise_reason") in KNOWN_TRAPS and model_keep:
            trap_keeps.append({"key_hash": key.split(":")[-1][:12],
                               "noise_reason": label.get("noise_reason"),
                               "toronto": (result.get("assessment") or {}).get("toronto", {}).get("verdict")})
        caption = (media[key].get("caption") or "") + " " + (media[key].get("alt_text") or "")
        if "misaligned" in caption.lower() or "alignment tab" in caption.lower() or "storm drain" in caption.lower():
            drain_hits.append({
                "issue_candidate": result.get("issue_candidate"),
                "locatability": result.get("locatability"),
                "issue_present": (result.get("assessment") or {}).get("issue", {}).get("present"),
            })

    rate = (agreement / compared) if compared else 0.0
    drain_ok = any(item.get("issue_candidate") and item.get("locatability") in ("high", "medium")
                   for item in drain_hits)
    gate = {
        "agreement_rate": round(rate, 4),
        "agreement_target": 0.90,
        "agreement_pass": rate >= 0.90,
        "trap_keeps": len(trap_keeps),
        "traps_pass": len(trap_keeps) == 0,
        "drain_detected": drain_ok,
        "drain_pass": drain_ok,
    }
    gate["passed"] = gate["agreement_pass"] and gate["traps_pass"] and gate["drain_pass"]
    summary = {
        "evaluated_at": report.get("completed_at"),
        "scope": ("Automatic one-time Gemini check against existing human labels. "
                  "No new human review. No captions or image paths retained."),
        "model": report.get("model"),
        "prompt_version": screen.PROMPT_VERSION,
        "screening_status": report.get("status"),
        "requests": report.get("requests"),
        "cache_hits": report.get("cache_hits"),
        "compared_labels": compared,
        "agreement": agreement,
        "false_keep": false_keep,
        "false_reject": false_reject,
        "scene_counts": dict(Counter(row["decision"] for row in screening.values())),
        "gate": gate,
        "trap_keep_examples": trap_keeps[:10],
        "drain_checks": drain_hits,
        "out_of_pocket_usd": 0,
        "free_tier_note": report.get("free_tier_note"),
    }
    out = ROOT / "research" / "results" / "gemini-eval-results.json"
    write_json(out, summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=DATA / "combined-demo")
    parser.add_argument("--max-requests", type=int, default=200)
    parser.add_argument("--model")
    args = parser.parse_args(argv)
    out = ROOT / "research" / "results" / "gemini-eval-results.json"
    try:
        summary = evaluate(args.batch, max_requests=args.max_requests, model=args.model)
    except (ValueError, OSError) as exc:
        blocked = {
            "evaluated_at": None,
            "scope": ("Automatic one-time Gemini check against existing human labels. "
                      "No new human review."),
            "status": "blocked",
            "detail": str(exc)[:300],
            "gate": {"passed": False},
            "out_of_pocket_usd": 0,
            "next_step": "Add GEMINI_API_KEY to scraping/.env, then rerun this command.",
        }
        write_json(out, blocked)
        parser.exit(1, f"Gemini eval stopped: {exc}\n")
    print(json.dumps(summary, indent=2))
    return 0 if summary["gate"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
