"""Engine mutants of the one-event change: each removes one mechanism, and the test modules must kill
it (some test fails). Each mutated file is restored from HEAD after its run, so commit first.

    mutants.py <worktree>
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
E = "MTG_bot/core/executor/"
MUTANTS = [
    # the binder: one event at a time, look-back first (CR 603.10a), then the rest (CR 603.10)
    ("lifecycle before the look-back phase", E + "binding.py",
     "            for event in rows:\n                self._match(event, True, triggers, arrived, left)\n"
     "            for event in moves:\n                self._lifecycle(event)\n",
     "            for event in moves:\n                self._lifecycle(event)\n"
     "            triggers = self._triggers(arrived)\n"
     "            for event in rows:\n                self._match(event, True, triggers, arrived, left)\n"),
    ("newcomers not left out looking back", E + "binding.py",
     "*(kv for kv in self.attached.items() if kv[0][0] not in arrived),", "*self.attached.items(),"),
    ("a departed source's controller read on another row", E + "binding.py",
     "left.get(handle, event))", "event)"),
    ("an enters ability from a graveyard looks back", E + "binding.py",
     "if not isinstance(node, ZoneChangeEvent) or node.to_zone.kind is ZoneKind.BATTLEFIELD:",
     "if not isinstance(node, ZoneChangeEvent):"),
    ("113.6m exception dropped", E + "binding.py",
     "    if dies is not None and _filter_names_the_source(dies):\n        return False\n", ""),
    # the layers, brought up to date for the triggers that do not look back
    ("layers never brought up to date", E + "binding.py",
     "        if self._after_event and self._layers_stale:", "        if False:"),
    ("not stale as a drain begins", E + "binding.py",
     "        if self._seen_journal_len < end:\n            self._layers_stale = True\n", ""),
    ("not stale after an event's moves", E + "binding.py",
     "            self._layers_stale = self._layers_stale or bool(moves)\n", ""),
    ("no recompute at a filter read", E + "binding.py",
     "        self._layers_now()  # a trigger's filter is about to be read (CR 603.10)\n", ""),
    ("no recompute before the granted triggers", E + "binding.py",
     "        if not look_back and layers.grants_triggers:\n            self._layers_now()\n", ""),
    ("no recompute before the keyword triggers", E + "binding.py",
     "            self._layers_now()\n            for family in", "            for family in"),
    # departed objects: last known information looking back, the new object after the event
    ("look-back triggers of a departed host: the live granted map", E + "binding.py",
     "            if lki is not None:\n                granted[host] = lki.granted\n",
     "            pass\n"),
    ("KEYWORD_HAS on a departed object: the live map", E + "quantity.py",
     "return atom.keyword.name in lki.keywords", "pass"),
    ("type words of a departed object: the live overlay", E + "quantity.py",
     "    if lki is not None:\n        words.update(lki.types)\n    elif", "    if"),
    ("matching context without after_event", E + "binding.py",
     "            after_event=self._after_event,\n", ""),
    ("departed_lki ignores after_event", E + "quantity.py",
     "    if ctx.after_event:\n        return None\n    found = departure_lki",
     "    found = departure_lki"),
    # CR 400.7: "it" and "they"
    ("no CR 400.7 cut of the event referent", E + "selectors.py",
     'if sel.referent == "event" and not info:', "if False:"),
    ("role_players cut", E + "selectors.py",
     "handles = sorted(resolve_selector(value, ctx, info=True))",
     "handles = sorted(resolve_selector(value, ctx))"),
    ("last_known ignores gone", E + "quantity.py",
     ' or handle in (ctx.binding_handles("gone") or ())', ""),
    ("_gone ignores the hidden zones", E + "binding.py", "            or h in hidden\n", ""),
    ("_gone keeps tokens off the battlefield", E + "binding.py",
     "            or (cards[h].identity.is_token and self.world.zone_of(h).kind != ZONE_BATTLEFIELD)\n",
     ""),
    # one event: EachPlayer (CR 101.4), replacements (CR 614.6), returns after it (CR 610.3)
    ("EachPlayer: no shared event", E + "__init__.py",
     "            with self._one_event():\n                for player in players_for",
     "            if True:\n                for player in players_for"),
    ("state check: replaced deaths their own event", E + "__init__.py",
     "            with self._one_event(new_events):\n                self._on_zone_changes(new_events)\n"
     "                for card, repl in replaced:",
     "            if True:\n                self._on_zone_changes(new_events)\n"
     "                for card, repl in replaced:"),
    ("instruction: replacements their own event", E + "__init__.py",
     "            with self._one_event(new_events):\n                # The zone-change bookkeeping",
     "            if True:\n                # The zone-change bookkeeping"),
    ("returns not deferred", E + "__init__.py",
     "        if self.journal.event_open():\n            self._returns_due.setdefault(",
     "        if False:\n            self._returns_due.setdefault("),
    ("returns not kept per depth", E + "__init__.py",
     "            due = self._returns_due.pop(depth, []) if opened else []",
     "            due = [r for k in list(self._returns_due) for r in self._returns_due.pop(k)] "
     "if opened else []"),
    ("returns stranded when a step of the event raises", E + "__init__.py",
     "        try:\n            with self.journal.one_event(after) as opened:\n                yield\n"
     "        finally:\n",
     "        if True:\n            with self.journal.one_event(after) as opened:\n                yield\n"
     "        if True:\n"),
]
TESTS = ["MTG_bot/core/test_executor_one_event.py", "MTG_bot/core/test_executor_one_or_more.py"]
killed = 0
for name, rel, old, new in MUTANTS:
    path = ROOT / rel
    text = path.read_text()
    if text.count(old) != 1:
        print(f"!! {name}: pattern found {text.count(old)} times")
        continue
    path.write_text(text.replace(old, new))
    try:
        out = subprocess.run([sys.executable, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider",
                              "--tb=no", "-rf"], cwd=ROOT, capture_output=True, text=True, check=False)
    finally:
        subprocess.run(["git", "checkout", "--", rel], cwd=ROOT, check=True)
    failed = [line.split("::", 1)[1] for line in out.stdout.splitlines() if line.startswith("FAILED")]
    killed += bool(failed)
    print(f"{'KILLED' if failed else 'SURVIVED'}: {name}: {len(failed)} failing", failed[:3])
print(f"{killed} of {len(MUTANTS)} killed")
