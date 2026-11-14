"""Extract Agent briefs, their results, SendMessage follow-ups and task notifications from a
transcript JSONL, streaming. Emails and account ids are scrubbed. Output: JSON to argv[2]."""
import json
import re
import sys

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
UUIDISH = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


def scrub(s: str) -> str:
    s = EMAIL.sub("<email>", s)
    return s


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    out = []
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    out.append(c.get("text", ""))
                elif c.get("type") == "tool_result":
                    out.append(text_of(c.get("content")))
    return "\n".join(out)


path, outp = sys.argv[1], sys.argv[2]
agents = []
results = {}
sends = []
notes = []
user_prompts = []
with open(path, encoding="utf-8") as f:
    for line in f:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        ts = d.get("timestamp")
        if t == "assistant":
            for c in (d.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    inp = c.get("input") or {}
                    if c.get("name") == "Agent":
                        agents.append({"id": c.get("id"), "ts": ts, "description": inp.get("description"),
                                       "subagent_type": inp.get("subagent_type"),
                                       "isolation": inp.get("isolation"), "model": inp.get("model"),
                                       "run_in_background": inp.get("run_in_background"),
                                       "prompt": scrub(inp.get("prompt", ""))})
                    elif c.get("name") == "SendMessage":
                        sends.append({"id": c.get("id"), "ts": ts, "to": inp.get("to") or inp.get("recipient"),
                                      "message": scrub(str(inp.get("message") or inp.get("content") or inp)[:6000])})
        elif t == "user":
            msg = d.get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        results[c.get("tool_use_id")] = {"ts": ts, "text": scrub(text_of(c.get("content"))[:20000])}
            txt = text_of(content)
            if "<task-notification>" in txt:
                notes.append({"ts": ts, "text": scrub(txt[:20000])})
            elif isinstance(content, str) and not d.get("isMeta"):
                user_prompts.append({"ts": ts, "text": scrub(content[:3000])})
        elif t == "queue-operation":
            txt = str(d.get("content") or "")
            if "task-notification" in txt:
                notes.append({"ts": ts, "text": scrub(txt[:20000]), "queue": True})
json.dump({"agents": agents, "results": results, "sends": sends, "notes": notes,
           "user_prompts": user_prompts}, open(outp, "w"), indent=1)
print(len(agents), "agents;", len(results), "results;", len(sends), "sends;", len(notes), "notes;",
      len(user_prompts), "user prompts")
