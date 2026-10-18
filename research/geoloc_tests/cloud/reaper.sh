#!/bin/bash
# CivicLens dead-man switch, passed to Vultr as cloud-init user-data by gpu_run.py. No fixed lifetime:
# every minute it destroys this server (Vultr bills stopped servers, so DELETE is the only off switch) when
#   - the job wrote /var/lib/civiclens/job.done more than DONE_GRACE_SECONDS ago, or
#   - the server has been idle for IDLE_SECONDS: no job heartbeat and the GPU (if any) below 10% use.
# The controller's job loop touches the heartbeat every minute; GPU use also counts as activity.
# If the API call fails (e.g. this server's IP is not on the key's allowlist) it logs and retries next
# minute; it does not power off, because Vultr would keep billing a guest-halted server and still report it
# as running. vultr_guard.py on the laptop is the backstop.
set -u
mkdir -p /etc/civiclens /var/lib/civiclens
cat > /etc/civiclens/reaper.env <<EOF
VULTR_API_KEY=__VULTR_API_KEY__
API_PATH=__API_PATH__
DONE_GRACE_SECONDS=__DONE_GRACE_SECONDS__
IDLE_SECONDS=__IDLE_SECONDS__
EOF
chmod 600 /etc/civiclens/reaper.env
touch /var/lib/civiclens/heartbeat

cat > /usr/local/bin/civiclens-reaper <<'EOF'
#!/bin/bash
. /etc/civiclens/reaper.env
now=$(date +%s)
if command -v nvidia-smi >/dev/null 2>&1; then
  util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | sort -n | tail -1)
  if [ -n "$util" ] && [ "$util" -ge 10 ]; then touch /var/lib/civiclens/heartbeat; fi
fi
reason=""
if [ -f /var/lib/civiclens/job.done ]; then
  done_at=$(stat -c %Y /var/lib/civiclens/job.done)
  if [ $((now - done_at)) -ge "$DONE_GRACE_SECONDS" ]; then reason="job-done"; fi
fi
beat=$(stat -c %Y /var/lib/civiclens/heartbeat)
if [ -z "$reason" ] && [ $((now - beat)) -ge "$IDLE_SECONDS" ]; then reason="idle"; fi
[ -z "$reason" ] && exit 0
id=$(curl -s http://169.254.169.254/v1.json | python3 -c 'import sys, json; print(json.load(sys.stdin)["instance-v2-id"])')
code=$(curl -s -o /dev/null -w '%{http_code}' -X DELETE -H "Authorization: Bearer $VULTR_API_KEY" \
  "https://api.vultr.com/v2/$API_PATH/$id")
echo "$(date -u +%FT%TZ) reason=$reason delete_http=$code" >> /var/lib/civiclens/reaper.log
logger -t civiclens-reaper "reason=$reason delete_http=$code"
EOF
chmod 700 /usr/local/bin/civiclens-reaper

cat > /etc/systemd/system/civiclens-reaper.service <<'EOF'
[Unit]
Description=CivicLens dead-man switch
[Service]
Type=oneshot
ExecStart=/usr/local/bin/civiclens-reaper
EOF
cat > /etc/systemd/system/civiclens-reaper.timer <<'EOF'
[Unit]
Description=Run the CivicLens dead-man switch every minute
[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
AccuracySec=10s
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now civiclens-reaper.timer
