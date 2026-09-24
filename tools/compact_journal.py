#!/usr/bin/env python3
"""
Autonomous Knowledge Journal & Prompt Self-Engineering Compactor
Part of the MTG_AI Self-Improving Qwen Architecture.

Workflow:
1. Agents record micro-checkpoints after each turn/mini-milestone into KNOWLEDGE/JOURNAL/.
2. Every 5-10 entries (or via --force), this compactor:
   - Distills new empirical failure modes and appends them to KNOWLEDGE/PITFALLS.md.
   - Synthesizes a dated milestone report in KNOWLEDGE/<date>/NN-journal-compaction.md.
   - Updates KNOWLEDGE/INDEX.md to maintain knowledge graph continuity.
   - Generates an updated subagent prompt contract so future agents inherit the learnings.
   - Archives processed journal notes into KNOWLEDGE/JOURNAL/archive/.
"""

import os
import sys
import re
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

REPO_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = REPO_DIR / "KNOWLEDGE"
JOURNAL_DIR = KNOWLEDGE_DIR / "JOURNAL"
ARCHIVE_DIR = JOURNAL_DIR / "archive"
PITFALLS_FILE = KNOWLEDGE_DIR / "PITFALLS.md"
INDEX_FILE = KNOWLEDGE_DIR / "INDEX.md"
AGENTS_FILE = REPO_DIR / "AGENTS.md"


def init_dirs():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def record_checkpoint(
    task: str,
    scope: str,
    attempted: str,
    outcome: str,
    what_worked: str,
    what_failed: str,
    root_cause: str,
    actionable_rule: str,
    tags: Optional[List[str]] = None,
) -> Path:
    """Record a single atomic micro-checkpoint."""
    init_dirs()
    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    file_prefix = now.strftime("%Y-%m-%d_%H%M%S")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", task.lower()).strip("_")[:40]
    filename = f"{file_prefix}_{slug}.md"
    target_path = JOURNAL_DIR / filename

    content = f"""# Micro-Checkpoint: {task}
- **Timestamp**: {timestamp_str}
- **Scope**: `{scope}`
- **Outcome**: {outcome.upper()}
- **Tags**: {", ".join(tags or ['turn-checkpoint'])}

## Attempted
{attempted.strip()}

## What Worked
{what_worked.strip()}

## What Failed & Root Cause
- **Failure**: {what_failed.strip()}
- **Root Cause**: {root_cause.strip()}

## Actionable Invariant (Rule for Future Prompts)
> **Rule**: {actionable_rule.strip()}
"""
    target_path.write_text(content, encoding="utf-8")
    return target_path


def get_pending_checkpoints() -> List[Path]:
    """Get list of active, uncompacted checkpoint files sorted by creation time."""
    init_dirs()
    return sorted([p for p in JOURNAL_DIR.glob("*.md") if p.is_file()])


def parse_checkpoint(path: Path) -> Dict[str, Any]:
    """Parse a markdown checkpoint into structured fields."""
    text = path.read_text(encoding="utf-8")
    data: Dict[str, Any] = {"file": path.name, "path": path}

    m_time = re.search(r"- \*\*Timestamp\*\*:\s*(.*)", text)
    data["timestamp"] = m_time.group(1).strip() if m_time else ""

    m_scope = re.search(r"- \*\*Scope\*\*:\s*`?(.*?)`?$", text, re.MULTILINE)
    data["scope"] = m_scope.group(1).strip() if m_scope else ""

    m_outcome = re.search(r"- \*\*Outcome\*\*:\s*(.*)", text)
    data["outcome"] = m_outcome.group(1).strip() if m_outcome else "UNKNOWN"

    def get_section(title: str) -> str:
        pattern = rf"## {re.escape(title)}\s*\n(.*?)(?=\n## |\Z)"
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else ""

    data["attempted"] = get_section("Attempted")
    data["what_worked"] = get_section("What Worked")
    data["what_failed"] = get_section("What Failed & Root Cause")
    
    m_rule = re.search(r">\s*\*\*Rule\*\*:\s*(.*)", text)
    data["rule"] = m_rule.group(1).strip() if m_rule else ""

    return data


def update_pitfalls(new_rules: List[Dict[str, str]]):
    """Append newly discovered rules to KNOWLEDGE/PITFALLS.md under today's date."""
    if not PITFALLS_FILE.exists():
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    content = PITFALLS_FILE.read_text(encoding="utf-8")

    # Filter out rules already mentioned in PITFALLS.md
    unique_rules = []
    for r in new_rules:
        rule_text = r["rule"]
        if rule_text and rule_text.lower() not in content.lower():
            unique_rules.append(r)

    if not unique_rules:
        return

    date_header = f"## {today_str}\n"
    new_entries_block = ""
    for r in unique_rules:
        scope_prefix = f"**[{r['scope']}]** " if r.get("scope") else ""
        new_entries_block += f"- {scope_prefix}{r['rule']}\n"

    if date_header in content:
        # Append under existing date header
        idx = content.find(date_header) + len(date_header)
        content = content[:idx] + new_entries_block + content[idx:]
    else:
        # Prepend new date header right after the top title / intro
        header_match = re.search(r"#\s+PITFALLS.*?\n\n", content)
        if header_match:
            insert_pos = header_match.end()
            content = content[:insert_pos] + f"{date_header}{new_entries_block}\n" + content[insert_pos:]
        else:
            content = f"{date_header}{new_entries_block}\n" + content

    PITFALLS_FILE.write_text(content, encoding="utf-8")


def compact_checkpoints(force: bool = False, min_count: int = 5) -> Optional[Dict[str, Any]]:
    """Compact pending checkpoints if threshold met (or force=True)."""
    pending = get_pending_checkpoints()
    if not force and len(pending) < min_count:
        print(f"[Compactor] {len(pending)} pending checkpoints (threshold is {min_count}). Skipping compaction.")
        return None

    parsed_entries = [parse_checkpoint(p) for p in pending]
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_dir = KNOWLEDGE_DIR / today_str
    today_dir.mkdir(parents=True, exist_ok=True)

    # Determine next note sequence number
    existing_notes = list(today_dir.glob("[0-9][0-9]-*.md"))
    next_num = len(existing_notes) + 1
    note_filename = f"{next_num:02d}-journal-compaction.md"
    note_path = today_dir / note_filename

    # Extract distinct rules and learnings
    rules_to_pitfalls = []
    successes = []
    failures = []

    for entry in parsed_entries:
        if entry["rule"]:
            rules_to_pitfalls.append({"scope": entry["scope"], "rule": entry["rule"]})
        if entry["what_worked"]:
            successes.append(f"- **{entry['scope']}**: {entry['what_worked']}")
        if entry["what_failed"]:
            failures.append(f"- **{entry['scope']}**: {entry['what_failed']}")

    # 1. Update PITFALLS.md
    update_pitfalls(rules_to_pitfalls)

    # 2. Write synthesized knowledge note
    synthesis_md = f"""# {today_str} · {next_num:02d} — Journal Compaction Synthesis ({len(pending)} turns)

**Context:** Consolidated {len(pending)} micro-checkpoints from `KNOWLEDGE/JOURNAL/` into standing project knowledge.

## Standing Rules & Invariants Extracted
"""
    for r in rules_to_pitfalls:
        synthesis_md += f"- **{r['scope']}**: {r['rule']}\n"

    synthesis_md += "\n## Empirical What Worked (Validated Solutions)\n"
    synthesis_md += "\n".join(successes) if successes else "- None recorded."

    synthesis_md += "\n\n## Empirical Failure Modes (Addressed & Prevented)\n"
    synthesis_md += "\n".join(failures) if failures else "- None recorded."

    synthesis_md += f"""

## Prompt Engineering Directives
Future subagent prompts in this project MUST incorporate the following synthesized directives:
```markdown
### Mandatory Project Invariants:
{chr(10).join(f"- {r['rule']}" for r in rules_to_pitfalls)}
```
"""
    note_path.write_text(synthesis_md, encoding="utf-8")

    # 3. Update INDEX.md
    if INDEX_FILE.exists():
        index_content = INDEX_FILE.read_text(encoding="utf-8")
        entry_row = f"| `{today_str}/{note_filename}` | {today_str}: Journal compaction synthesis of {len(pending)} micro-turns |\n"
        if "| `NUMBERS.md` |" in index_content and entry_row not in index_content:
            # Find the table end
            table_match = re.search(r"(\|\s*`.*?`\s*\|.*?\n)+", index_content)
            if table_match:
                end_pos = table_match.end()
                index_content = index_content[:end_pos] + entry_row + index_content[end_pos:]
                INDEX_FILE.write_text(index_content, encoding="utf-8")

    # 4. Archive processed checkpoints
    for p in pending:
        shutil.move(str(p), str(ARCHIVE_DIR / p.name))

    print(f"[Compactor] Successfully compacted {len(pending)} checkpoints into {note_path.name}")
    return {
        "compacted_count": len(pending),
        "note_path": str(note_path),
        "rules_count": len(rules_to_pitfalls),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compact KNOWLEDGE/JOURNAL checkpoints")
    parser.add_argument("--force", action="store_true", help="Force compaction even if < 5 entries")
    parser.add_argument("--min", type=int, default=5, help="Minimum entries to trigger compaction (default: 5)")
    args = parser.parse_args()

    compact_checkpoints(force=args.force, min_count=args.min)


if __name__ == "__main__":
    main()
