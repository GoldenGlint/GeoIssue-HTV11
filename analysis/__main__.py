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
    parser.add_argument("--tiger", action="store_true", help="also synchronize this complete handoff to Tiger Data")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    result = run(args.input, cfg.load(args.config), args.out, now, args.offline)
    print_summary(result)
    if args.tiger:
        from . import tiger
        try:
            metadata = tiger.sync(result["public"], result["events"], result["report"], result["areas"])
            print(f"Tiger Data: {metadata['reports']} independent reports synchronized")
        except tiger.Unavailable as error:
            parser.exit(1, f"{error}\nAnalysis files were saved; the database import did not finish.\n")
        except Exception:
            parser.exit(1, "Tiger Data import did not finish. Analysis files were saved. Check schema setup and handoff dates, then retry.\n")


def print_summary(result):
    report, counts = result["report"], result["report"]["counts"]
    print(f"{counts.get('input_records', 0)} input records -> {counts.get('sightings', 0)} sightings -> "
          f"{counts.get('issues', 0)} issues ({counts.get('merged_away', 0)} duplicates merged)")
    skipped = {"not an issue": counts.get("skipped_not_an_issue", 0), "low confidence": counts.get("skipped_low_confidence", 0)}
    # [input] skip_when rules count as skipped_<field>=<value>.
    skipped.update({key.removeprefix("skipped_"): n for key, n in counts.items() if "=" in key and key.startswith("skipped_")})
    for item in report["dropped"]:
        skipped[item["reason"]] = skipped.get(item["reason"], 0) + 1
    if any(skipped.values()):
        print("Skipped: " + ", ".join(f"{n} {reason}" for reason, n in skipped.items() if n))
    print("Stages: " + ", ".join(f"{name} {'on' if on else 'off'}" for name, on in report["stages"].items()))
    for field, labels in report["unrecognised_values"].items():
        print(f"Unrecognised {field} values: " + ", ".join(f"{label!r} x{n}" for label, n in labels.items())
              + f"  (add them under [values.{field}] in analysis/config.toml)")
    unused = list(report["unused_input_fields"])
    if unused:
        more = f" and {len(unused) - 12} more (see report.json)" if len(unused) > 12 else ""
        print("Input fields not used: " + ", ".join(unused[:12]) + more)
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
