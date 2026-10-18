"""Stands in for `claude -p ... --output-format stream-json` in the tests: prints the events a short run
would, and writes result.json where geoloc_mcp.py would. FAKE_CLAUDE_MODE picks the behaviour:
  ok (default)  one search, then a verified final answer
  slow          an init event, then 60 s of nothing (for cancel and timeout tests)
  fail          exits 2 with a message on stderr and no result
FAKE_CLAUDE_STEP_S waits that many seconds between events, to watch progress in the app.
"""
import json
import os
import sys
import time
from pathlib import Path


def emit(event):
    print(json.dumps(event), flush=True)
    time.sleep(float(os.environ.get("FAKE_CLAUDE_STEP_S", 0)))


def main():
    argv = sys.argv[1:]
    config = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text(encoding="utf-8"))
    server = config["mcpServers"]["civiclens"]["args"]
    out = Path(server[server.index("--out") + 1])
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    if mode == "fail":
        print("Invalid API key", file=sys.stderr)
        sys.exit(2)
    emit({"type": "system", "subtype": "init", "session_id": "s1", "model": "claude-opus-test",
          "mcp_servers": [{"name": "civiclens", "status": "connected"}]})
    if mode == "slow":
        time.sleep(60)
        return
    emit({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "mcp__civiclens__search_places", "input": {"query": "Highland Hall"}}]}})
    emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": [
        {"type": "text", "text": json.dumps([{"name": "Highland Hall", "lat": 43.78, "lon": -79.18}])}]}]}})
    final = {"lat": 43.7858, "lon": -79.1873, "radius_m": 8.0, "confidence": 0.9, "place_description": "UTSC",
             "evidence": "accepted match", "verified": True}
    (out / "result.json").write_text(json.dumps({"final": final, "audit": {"image_matches_run": 1}, "error_m": 3.0}))
    emit({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t2", "name": "mcp__civiclens__final_answer", "input": final}]}})
    emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "content": "Recorded"}]}})
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "It is at UTSC."}]}})
    emit({"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.01, "num_turns": 3,
          "duration_ms": 1200, "result": "It is at UTSC."})


if __name__ == "__main__":
    main()
