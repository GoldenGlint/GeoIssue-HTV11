"""Command line: python -m analysis [--input PATH] [--out DIR] [--config FILE] [--now ISO] [--offline]"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from . import config as cfg
from .pipeline import run

SAMPLE_INPUT = Path(__file__).resolve().parent / "samples" / "photo_analysis_output.json"


def main():
    parser = argparse.ArgumentParser(prog="python -m analysis", description=__doc__)
    parser.add_argument("--input", default=SAMPLE_INPUT, help="JSON/JSONL file or folder from the photo analysis (default: the sample)")
    parser.add_argument("--out", help="output folder (default: [output] dir in the config)")
    parser.add_argument("--config", help="config file (default: analysis/config.toml)")
    parser.add_argument("--now", help="ISO time to measure ages and trends from (default: now)")
    parser.add_argument("--offline", action="store_true", help="write template summaries instead of calling Gemini")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    result = run(args.input, cfg.load(args.config), args.out, now, args.offline)
    print_summary(result)


def print_summary(result):
    report, counts = result["report"], result["report"]["counts"]
    print(f"{counts.get('input_records', 0)} input records -> {counts.get('sightings', 0)} sightings -> "
          f"{counts.get('issues', 0)} issues ({counts.get('merged_away', 0)} duplicates merged)")
    skipped = {"not an issue": counts.get("skipped_not_an_issue", 0), "low confidence": counts.get("skipped_low_confidence", 0)}
    for item in report["dropped"]:
        skipped[item["reason"]] = skipped.get(item["reason"], 0) + 1
    if any(skipped.values()):
        print("Skipped: " + ", ".join(f"{n} {reason}" for reason, n in skipped.items() if n))
    print("Stages: " + ", ".join(f"{name} {'on' if on else 'off'}" for name, on in report["stages"].items()))
    for field, labels in report["unrecognised_values"].items():
        print(f"Unrecognised {field} values: " + ", ".join(f"{label!r} x{n}" for label, n in labels.items())
              + f"  (add them under [values.{field}] in analysis/config.toml)")
    if report["unused_input_fields"]:
        print("Input fields not used: " + ", ".join(report["unused_input_fields"]))
    if report["private_fields_dropped"]:
        print("Private fields dropped: " + ", ".join(report["private_fields_dropped"]))
    if result["areas"]:
        methods = {a.get("summary", {}).get("method") for level in result["areas"]["by_area"].values() for a in level} - {None}
        print("Summaries: " + (", ".join(sorted(methods)) or "none"))
    for warning in report["warnings"]:
        print(f"Warning: {warning}")
    if report["reference_data"] == "placeholder":
        print("Reference data: PLACEHOLDER areas and infrastructure (approximate)")
    print(f"Wrote {result['out']}")


if __name__ == "__main__":
    main()
