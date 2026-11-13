#!/usr/bin/env bash
# Append one metadata-only JSON line per hook event to audit/events.jsonl.
# Uses python3 (jq is not installed on this machine). Records no tool inputs,
# so tokens and file contents never reach the log.
exec python3 -I -c '
import json, os, sys, datetime
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
keys = ["hook_event_name", "session_id", "agent_id", "agent_type", "tool_name", "tool_use_id", "transcript_path"]
rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
rec.update({k: d.get(k) for k in keys})
root = os.environ.get("CLAUDE_PROJECT_DIR") or d.get("cwd") or "."
os.makedirs(os.path.join(root, "audit"), exist_ok=True)
with open(os.path.join(root, "audit", "events.jsonl"), "a") as f:
    f.write(json.dumps(rec) + "\n")
'
