"""Minimal Vultr API v2 client (stdlib only) plus the spend ledger shared by gpu_run.py and vultr_guard.py.

Vultr bills stopped servers and charges a 1-hour minimum, so the only way to stop paying is DELETE.
Every server we create carries TAG in its label; the guard only ever touches those.
Handles both cloud instances (/instances) and bare metal (/bare-metals, e.g. the GH200).
"""
import json
import math
import os
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.vultr.com/v2"
TAG = "geoissue-gpu"
HERE = Path(__file__).parent
LEDGER = HERE / "ledger.json"
LOCK = HERE / "BUDGET_LOCK"
DEFAULT_CAP_USD = 10.0
KINDS = {"instance": ("/instances", "instance", "instances"),
         "bare-metal": ("/bare-metals", "bare_metal", "bare_metals")}


class BudgetError(RuntimeError):
    pass


# Vultr's API access control is an IP allowlist; a laptop that flips to IPv6 gets 401 "Unauthorized IP".
# Pin api.vultr.com to IPv4 so calls come from the allowlisted v4 address.
_getaddrinfo = socket.getaddrinfo


def _ipv4_for_vultr(host, *args, **kwargs):
    if host == "api.vultr.com":
        return [r for r in _getaddrinfo(host, *args, **kwargs) if r[0] == socket.AF_INET]
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _ipv4_for_vultr


def load_env(path=HERE.parent / ".env"):
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def call(method, path, body=None):
    req = urllib.request.Request(
        API + path, method=method, data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.environ['VULTR_API_KEY']}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"Vultr {method} {path} -> HTTP {err.code}: {err.read().decode()[:300]}") from None


def pending_charges():
    return float(call("GET", "/account")["account"]["pending_charges"])


def plan_hourly(plan_id):
    if plan_id.startswith("vbm-"):
        plans = call("GET", "/plans-metal?per_page=500")["plans_metal"]
    else:
        plans = call("GET", f"/plans?type={plan_id.split('-', 1)[0]}&per_page=500")["plans"]
    for p in plans:
        if p["id"] == plan_id:
            return float(p.get("hourly_cost") or p["monthly_cost"] / 730)
    raise ValueError(f"unknown plan {plan_id}")


def kind_of(plan_id):
    return "bare-metal" if plan_id.startswith("vbm-") else "instance"


def get_server(kind, server_id):
    path, single, _ = KINDS[kind]
    return call("GET", f"{path}/{server_id}")[single]


def tagged_servers():
    """All GeoIssue servers of both kinds, each with a 'kind' key added."""
    found = []
    for kind, (path, _, plural) in KINDS.items():
        for s in call("GET", f"{path}?per_page=500")[plural]:
            if s["label"].startswith(TAG) or TAG in (s.get("tags") or []):
                found.append({**s, "kind": kind})
    return found


def destroy(server_id, kind="instance"):
    call("DELETE", f"{KINDS[kind][0]}/{server_id}")


def parse_ts(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- spend ledger ----------

def ledger():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"cap_usd": float(os.environ.get("VULTR_BUDGET_USD", DEFAULT_CAP_USD)), "baseline_pending": None,
            "runs": []}


def save_ledger(data):
    LEDGER.write_text(json.dumps(data, indent=2))


def record_create(server_id, plan, hourly, label, kind, key_path=None):
    data = ledger()
    if data["baseline_pending"] is None:
        data["baseline_pending"] = pending_charges()
    data["runs"].append({"id": server_id, "kind": kind, "plan": plan, "hourly": hourly, "label": label,
                         "key": str(key_path) if key_path else None, "created": time.time(), "destroyed": None})
    save_ledger(data)


def record_destroy(server_id):
    data = ledger()
    for run in data["runs"]:
        if run["id"] == server_id and run["destroyed"] is None:
            run["destroyed"] = time.time()
    save_ledger(data)


def run_cost(run, at=None):
    """Every started hour is billed in full (Vultr's 1-hour minimum)."""
    end = run["destroyed"] or at or time.time()
    return max(1, math.ceil((end - run["created"]) / 3600)) * run["hourly"]


def estimated_spend(data=None):
    data = data or ledger()
    return sum(run_cost(run) for run in data["runs"])


def spent():
    """The larger of our own estimate and what Vultr reports (Vultr's figure can lag by up to an hour)."""
    data = ledger()
    try:
        reported = pending_charges() - (data["baseline_pending"] or 0.0)
    except Exception:
        reported = 0.0
    return max(estimated_spend(data), reported)


def check_can_start(hourly, est_hours):
    data = ledger()
    if LOCK.exists():
        raise BudgetError(f"budget lock present ({LOCK}); delete it only if you mean to raise the cap")
    projected = spent() + math.ceil(est_hours) * hourly
    if projected > data["cap_usd"]:
        raise BudgetError(f"run would take spend to ${projected:.2f}, over the ${data['cap_usd']:.2f} cap")
    return projected
