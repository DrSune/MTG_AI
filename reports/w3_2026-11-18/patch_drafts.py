"""Patch rendered record drafts (render_records.py) into the one encoding of each reveal
(DESIGN_ATOM_ONTOLOGY §19), REVEAL atom by REVEAL atom, nothing else touched:
- "<player> reveals their hand" (a target player's REVEAL of count QUnbounded) is
  reveal_hand(<that player>);
- "reveal a <card> from among them and put it into your hand" (a top-1 REVEAL after a LOOK_AT,
  before the MOVE_ZONE that picks) moves after that MOVE_ZONE as reveal_result();
- "reveal it|them|those cards" after a search (your REVEAL of count 1 or QUnbounded) is
  reveal_result().

    patch_drafts.py <drafts dir> <stem>...
"""
import re
import sys
from pathlib import Path

REVEAL = re.compile(
    r"A\(Verb\.REVEAL, \{\s*'controller': ControllerRef\.(?P<who>\w+),\s*"
    r"'count': (?P<count>QConst\(value=\d+\)|QUnbounded\(\)),?\s*\}\)"
)


def close(text: str, start: int) -> int:
    """The index just past the bracket closing the one opened at ``start``."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] in "([{":
            depth += 1
        elif text[i] in ")]}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError("unbalanced")


def patch(text: str) -> tuple[str, list[str]]:
    done: list[str] = []
    while (m := REVEAL.search(text)) is not None:
        who, count = m.group("who"), m.group("count")
        after = text[m.end():]
        if who.startswith("TARGET_") and count == "QUnbounded()":
            text = text[: m.start()] + f"reveal_hand(ControllerRef.{who})" + after
            done.append("hand")
        elif "LOOK_AT" in text[: m.start()] and re.match(r",\s*A\(Verb\.MOVE_ZONE", after):
            line_start = text.rfind("\n", 0, m.start()) + 1
            indent = text[line_start: m.start()]
            end = m.end() + after.index(",") + 1  # the REVEAL step and its comma
            nl = text.index("\n", end) + 1 if text[end: text.index("\n", end)].strip() == "" else end
            text = text[:line_start] + text[nl:]
            mv = text.index("A(Verb.MOVE_ZONE", line_start)
            stop = close(text, text.index("(", mv))
            assert text[stop] == ","
            text = text[: stop + 1] + f"\n{indent}reveal_result()," + text[stop + 1:]
            done.append("pick")
        else:
            text = text[: m.start()] + "reveal_result()" + after
            done.append("searched")
    return text, done


folder = Path(sys.argv[1])
for stem in sys.argv[2:]:
    path = folder / f"{stem}.py"
    text, done = patch(path.read_text())
    path.write_text("# Patched by gate round W3 (DESIGN_ATOM_ONTOLOGY §19): REVEAL names the cards it shows.\n"
                    + text)
    print(stem, done or "no reveal of the old forms (the compiler's tree supplies it)")
