"""Tabulate subagent transcripts: meta, time span, tool counts, final report (scrubbed).
Writes JSON to argv[2]."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
root = Path(sys.argv[1])
out = []
for meta in sorted(root.glob("*.meta.json")):
    m = json.loads(meta.read_text())
    jl = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
    first = last = None
    tools = Counter()
    last_text = ""
    first_user = ""
    cardtool_cmds = Counter()
    n_assist = 0
    if jl.exists():
        with open(jl, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = d.get("timestamp")
                if ts:
                    first = first or ts
                    last = ts
                t = d.get("type")
                msg = d.get("message") or {}
                content = msg.get("content") if isinstance(msg, dict) else None
                if t == "user" and not first_user:
                    if isinstance(content, str):
                        first_user = content[:400]
                    elif isinstance(content, list):
                        first_user = " ".join(c.get("text", "") for c in content if isinstance(c, dict))[:400]
                if t == "assistant" and isinstance(content, list):
                    n_assist += 1
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        if c.get("type") == "tool_use":
                            tools[c.get("name")] += 1
                            if c.get("name") == "SubagentHandback":
                                last_text = str((c.get("input") or {}).get("message", ""))
                            if c.get("name") == "Bash":
                                cmd = str((c.get("input") or {}).get("command", ""))
                                for sub in re.findall(r"cardtool\.py\s+([a-z-]+)", cmd):
                                    cardtool_cmds[sub] += 1
                        elif c.get("type") == "text" and c.get("text", "").strip():
                            last_text = c["text"]
    out.append({"agent": meta.name.split(".")[0], "description": m.get("description"),
                "type": m.get("agentType"), "depth": m.get("spawnDepth"), "parent": m.get("parentAgentId"),
                "toolUseId": m.get("toolUseId"), "first": first, "last": last, "tools": dict(tools),
                "cardtool": dict(cardtool_cmds), "assistant_turns": n_assist,
                "first_user": EMAIL.sub("<email>", first_user),
                "report": EMAIL.sub("<email>", last_text[:12000])})
json.dump(out, open(sys.argv[2], "w"), indent=1)
for o in out:
    print(o["first"][:16] if o["first"] else "-", o["depth"], o["description"], "| bash", o["tools"].get("Bash", 0),
          "| cardtool", sum(o["cardtool"].values()), "| report", len(o["report"]))
