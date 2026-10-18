"""Run one job on a fresh Vultr server (cloud instance or bare metal) and always destroy it afterwards.

No fixed lifetime: the server lives exactly as long as the job. Flow: budget check -> per-run SSH key ->
create tagged server with the reaper.sh dead-man switch -> start vultr_guard.py --loop in the background ->
wait for SSH -> push files (+ a .env holding only --env-keys) -> run setup + job with a heartbeat ->
pull results -> mark job.done -> destroy. Destroy runs in `finally`; if this process dies anyway, the guard
(budget, done, idle, unreachable) and reaper.sh (done, idle) finish the job.

Paths in --push/--pull are relative to research/geoloc_tests.

Usage:
  python cloud/gpu_run.py --plan vc2-1c-1gb --region yto --job "hostname > out.txt" --pull out.txt:results/cloud_smoke
  python cloud/gpu_run.py --plan vbm-72c-480gb-gh200-gpu --region atl --est-hours 2 \
      --push geoloc_agent.py --push images ... --setup "bash cloud/setup_gpu.sh" --job "..." --pull results/agent:results/vultr
"""
import argparse
import base64
import io
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import vultr

HERE = Path(__file__).parent
ROOT = HERE.parent
KEYS = HERE / "keys"
UBUNTU_24_04 = 2284


def ssh_cmd(key, ip):
    exe = shutil.which("ssh") or "ssh"
    null = "NUL" if "system32" in exe.lower() else "/dev/null"
    return [exe, "-i", str(key), "-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={null}",
            "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30", f"root@{ip}"]


def user_data(kind, idle_minutes, done_grace_s):
    script = (HERE / "reaper.sh").read_text()
    key = os.environ.get("VULTR_REAPER_KEY") or os.environ["VULTR_API_KEY"]
    for token, value in {"__VULTR_API_KEY__": key, "__API_PATH__": vultr.KINDS[kind][0].strip("/"),
                         "__DONE_GRACE_SECONDS__": done_grace_s, "__IDLE_SECONDS__": idle_minutes * 60}.items():
        script = script.replace(token, str(value))
    return base64.b64encode(script.encode()).decode()


def wait_for_ip(kind, server_id, timeout_s):
    start = time.time()
    while time.time() - start < timeout_s:
        s = vultr.get_server(kind, server_id)
        if s["status"] == "active" and s["main_ip"] not in ("", "0.0.0.0"):
            return s["main_ip"]
        time.sleep(15)
    raise TimeoutError("server never became active")


def wait_for_ssh(base, timeout_s):
    start = time.time()
    while time.time() - start < timeout_s:
        if subprocess.run(base + ["cloud-init status --wait >/dev/null 2>&1; systemctl is-active geoissue-reaper.timer"],
                          capture_output=True, text=True).stdout.strip() == "active":
            return
        time.sleep(15)
    raise TimeoutError("SSH or the dead-man switch never came up")


def push(base, paths, env_keys):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in paths:
            tar.add(ROOT / p, arcname=p)
        env = "".join(f'{k}="{os.environ[k]}"\n' for k in env_keys if k in os.environ).encode()
        info = tarfile.TarInfo(".env")
        info.size = len(env)
        info.mode = 0o600
        tar.addfile(info, io.BytesIO(env))
    print(f"[push] {len(buf.getvalue()) / 1e6:.1f} MB")
    subprocess.run(base + ["mkdir -p /root/work && tar xzf - -C /root/work"], input=buf.getvalue(), check=True)


def pull(base, remote, local):
    out = subprocess.run(base + [f"tar czf - -C /root/work {shlex.quote(remote)}"], capture_output=True, check=True)
    dest = ROOT / local
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(out.stdout), mode="r:gz") as tar:
        tar.extractall(dest, filter="data")


def run_remote(base, setup, job, log_path):
    body = " && ".join(c for c in (setup, job) if c)
    # the cd must not share a list with the backgrounded heartbeat loop, or it only happens in that subshell
    remote = ("mkdir -p /root/work; cd /root/work || exit 1; "
              "(while sleep 60; do touch /var/lib/geoissue/heartbeat; done) >/dev/null 2>&1 & HB=$!; "
              f"bash -c {shlex.quote(body)}; rc=$?; kill $HB; exit $rc")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(base + [remote], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace")
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
        return proc.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--os-id", type=int, default=UBUNTU_24_04)
    ap.add_argument("--est-hours", type=float, default=1, help="for the up-front budget check only; not a timer")
    ap.add_argument("--idle-minutes", type=int, default=20)
    ap.add_argument("--push", action="append", default=[])
    ap.add_argument("--env-keys", default="MAPILLARY_TOKEN", help="comma list of .env keys copied to the server")
    ap.add_argument("--pull", action="append", default=[], help="remote_path:local_dir")
    ap.add_argument("--setup", default="")
    ap.add_argument("--job", required=True)
    ap.add_argument("--no-guard", action="store_true", help="don't start the background vultr_guard.py loop")
    ap.add_argument("--leave-for-reaper", action="store_true",
                    help="test mode: skip the controller's destroy so the dead-man switch and guard must do it")
    ap.add_argument("--attach", help="id of a server deployed by hand in the console (label must start with "
                                     f"{vultr.TAG}); skips creation but still runs, pulls and destroys")
    ap.add_argument("--key", default=str(KEYS / "geoissue-gpu-manual"), help="private key for --attach")
    args = ap.parse_args()
    vultr.load_env()

    kind = vultr.kind_of(args.plan)
    hourly = vultr.plan_hourly(args.plan)
    if not args.attach:
        projected = vultr.check_can_start(hourly, args.est_hours)
        print(f"[budget] {args.plan} ({kind}) ${hourly:.3f}/h; if it runs ~{args.est_hours}h, spend reaches "
              f"${projected:.2f} of ${vultr.ledger()['cap_usd']:.2f}. No fixed shutdown time: it ends with the job.")

    KEYS.mkdir(exist_ok=True)
    ssh_key_id = None
    if args.attach:
        label = vultr.get_server(kind, args.attach)["label"]
        key = Path(args.key)
    else:
        label = f"{vultr.TAG}-{time.strftime('%Y%m%d-%H%M%S')}"
        key = KEYS / label
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        ssh_key_id = vultr.call("POST", "/ssh-keys", {"name": label, "ssh_key": key.with_suffix(".pub").read_text().strip()})["ssh_key"]["id"]

    server_id, guard = None, None
    started = time.time()
    log_dir = ROOT / "results" / "cloud_runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        if args.attach:
            server_id = args.attach
            created_at = vultr.parse_ts(vultr.get_server(kind, server_id)["date_created"])
            vultr.record_create(server_id, args.plan, hourly, label, kind, key)
            data = vultr.ledger()
            data["runs"][-1]["created"] = created_at  # bill from the console deploy time, not from now
            vultr.save_ledger(data)
            print(f"[attach] {label} id={server_id}, deployed {(time.time() - created_at) / 60:.0f} min ago")
        else:
            body = {"region": args.region, "plan": args.plan, "os_id": args.os_id, "label": label, "hostname": label,
                    "sshkey_id": [ssh_key_id], "user_data": user_data(kind, args.idle_minutes, done_grace_s=60),
                    "tags": [vultr.TAG]}
            if kind == "instance":
                body["backups"] = "disabled"
            created = vultr.call("POST", vultr.KINDS[kind][0], body)[vultr.KINDS[kind][1]]
            server_id = created["id"]
            vultr.record_create(server_id, args.plan, hourly, label, kind, key)
            print(f"[create] {label} id={server_id}")
        if not args.no_guard:
            guard = subprocess.Popen([sys.executable, str(HERE / "vultr_guard.py"), "--loop", "60",
                                      "--idle-minutes", str(args.idle_minutes)],
                                     stdout=open(log_dir / f"{label}_guard.log", "w"), stderr=subprocess.STDOUT)
        ip = wait_for_ip(kind, server_id, timeout_s=3600 if kind == "bare-metal" else 1200)
        base = ssh_cmd(key, ip)
        wait_for_ssh(base, timeout_s=2400 if kind == "bare-metal" else 900)
        print(f"[ready] {ip} after {time.time() - started:.0f}s; dead-man switch active")
        if args.push:
            push(base, args.push, [k for k in args.env_keys.split(",") if k])
        rc = run_remote(base, args.setup, args.job, log_dir / f"{label}.log")
        print(f"[job] exit code {rc} after {time.time() - started:.0f}s")
        for spec in args.pull:
            remote, local = spec.split(":", 1)
            try:
                pull(base, remote, local)
                print(f"[pull] {remote} -> {local}")
            except subprocess.CalledProcessError as err:
                print(f"[pull] FAILED {remote}: {err.stderr.decode(errors='replace').strip()[:200]}")
        subprocess.run(base + ["touch /var/lib/geoissue/job.done"])
    finally:
        if server_id and not args.leave_for_reaper:
            try:
                vultr.destroy(server_id, kind)
                vultr.record_destroy(server_id)
                print(f"[destroy] {server_id}")
            except Exception as err:
                print(f"[destroy] FAILED ({err}); the guard will retry")
        elif server_id:
            print(f"[left for reaper/guard] {server_id}")
        if guard and not args.leave_for_reaper:
            guard.terminate()
        if ssh_key_id:
            try:
                vultr.call("DELETE", f"/ssh-keys/{ssh_key_id}")
            except Exception:
                pass
        print(f"[done] wall {time.time() - started:.0f}s, spend so far ~${vultr.spent():.2f}")


if __name__ == "__main__":
    main()
