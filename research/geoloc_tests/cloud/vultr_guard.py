"""Dynamic guard for CivicLens Vultr servers: there is no fixed lifetime; it destroys a tagged server when
  - budget: total spend has reached the cap, or the server is within 5 minutes of starting another billed
    hour that would push spend past the cap;
  - done or idle: over SSH (key from the ledger), the job wrote job.done more than 2 min ago, or the job
    heartbeat is older than --idle-minutes (reaper.sh also counts GPU use as activity);
  - unreachable: SSH has failed for 15 minutes on a server older than 30 minutes (bare metal boots slowly);
  - stopped: Vultr reports it powered off (it keeps billing stopped servers).
Once the cap is reached it writes BUDGET_LOCK so gpu_run.py refuses new runs.
Spend = max(ledger estimate with every started hour billed, Vultr pending_charges since the ledger baseline).
Without a ledger (e.g. the GitHub Actions copy) it uses pending_charges against --budget-usd and skips SSH.

Usage: python cloud/vultr_guard.py [--loop 60] [--budget-usd 10] [--idle-minutes 20] [--dry-run]
"""
import argparse
import json
import shutil
import subprocess
import time

import vultr

STATE_CMD = ("now=$(date +%s); d=0; [ -f /var/lib/civiclens/job.done ] && d=$(stat -c %Y /var/lib/civiclens/job.done); "
             "b=$(stat -c %Y /var/lib/civiclens/heartbeat 2>/dev/null || echo 0); echo $now $d $b")


def ssh_state(key, ip):
    exe = shutil.which("ssh") or "ssh"
    null = "NUL" if "system32" in exe.lower() else "/dev/null"
    try:
        out = subprocess.run([exe, "-i", key, "-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={null}",
                              "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
                              f"root@{ip}", STATE_CMD], capture_output=True, text=True, timeout=40)
        now, done, beat = map(int, out.stdout.split())
        return {"done_age": now - done if done else None, "beat_age": now - beat}
    except Exception:
        return None


def check(args):
    data = vultr.ledger() if vultr.LEDGER.exists() else None
    cap = args.budget_usd or (data["cap_usd"] if data else vultr.DEFAULT_CAP_USD)
    spend = vultr.spent() if data else vultr.pending_charges()
    runs = {r["id"]: r for r in (data["runs"] if data else [])}
    actions, notes = [], []
    for s in vultr.tagged_servers():
        run = runs.get(s["id"])
        age = time.time() - vultr.parse_ts(s["date_created"])
        hourly = run["hourly"] if run else vultr.plan_hourly(s["plan"])
        to_next_hour = 3600 - age % 3600
        reason = None
        if spend >= cap:
            reason = "over-budget"
        elif to_next_hour <= 300 and spend + hourly > cap:
            reason = "next-hour-over-budget"
        elif s.get("power_status") == "stopped":
            reason = "stopped"
        elif run and run.get("key") and s.get("main_ip") not in (None, "", "0.0.0.0"):
            st = ssh_state(run["key"], s["main_ip"])
            if st is None:
                run.setdefault("ssh_fail_since", time.time())
                if age > 1800 and time.time() - run["ssh_fail_since"] > 900:
                    reason = "unreachable"
            else:
                run.pop("ssh_fail_since", None)
                if st["done_age"] is not None and st["done_age"] >= 120:
                    reason = "job-done"
                elif st["beat_age"] >= args.idle_minutes * 60:
                    reason = "idle"
                notes.append({"label": s["label"], "age_min": round(age / 60), **st})
        if reason:
            if not args.dry_run:
                vultr.destroy(s["id"], s["kind"])
                if run:
                    run["destroyed"] = time.time()
            actions.append({"id": s["id"], "label": s["label"], "kind": s["kind"], "age_min": round(age / 60),
                            "reason": reason})
    if data and not args.dry_run:
        vultr.save_ledger(data)
    if spend >= cap and not args.dry_run:
        vultr.LOCK.write_text(f"spend ${spend:.2f} reached cap ${cap:.2f} at {vultr.now_iso()}\n")
    print(json.dumps({"at": vultr.now_iso(), "spend_usd": round(spend, 3), "cap_usd": cap, "destroyed": actions,
                      "live": notes, "dry_run": args.dry_run}), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--idle-minutes", type=float, default=20)
    ap.add_argument("--loop", type=int, default=0, help="repeat every N seconds")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    vultr.load_env()
    while True:
        try:
            check(args)
        except Exception as err:
            print(json.dumps({"at": vultr.now_iso(), "error": str(err)}), flush=True)
        if not args.loop:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
