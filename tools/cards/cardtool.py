"""Map a card onto existing components and check it plays right. docs/PLAN_CARD_ONBOARDING.md.

Run from the repo root (the worktree that carries the card-record loader):

    PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
    $PY tools/cards/cardtool.py status FDN                  # the worklist, cheapest cards first
    $PY tools/cards/cardtool.py status M21 M20 FDN M19      # per set: states, reprints, verified per day
    $PY tools/cards/cardtool.py show FDN "Card Name"        # text, per-sentence parse, tree as Python
    $PY tools/cards/cardtool.py similar "sentence" [-k 8]   # parsed sentences worded like it, with trees
    $PY tools/cards/cardtool.py parse "sentence" [--name N] # what the compiler builds for a wording
    $PY tools/cards/cardtool.py try FDN "Card Name" draft.py      # validate + G0 + G1 probe, no write
    $PY tools/cards/cardtool.py write FDN "Card Name" draft.py --clauses c.json --author NAME
    $PY tools/cards/cardtool.py needs-atom FDN "Card Name" --missing "what no atom expresses"
    $PY tools/cards/cardtool.py probe FDN "Card Name"       # G1 on the current tree
    $PY tools/cards/cardtool.py mutate FDN "Card Name"      # G3 mutation analysis
    $PY tools/cards/cardtool.py packet FDN "Card Name" --out DIR [--plant SEED --key KEYDIR]
    $PY tools/cards/cardtool.py runpack FDN pack.json ... [--card "Card Name" --draft draft.py]
    $PY tools/cards/cardtool.py survivors FDN "Card Name" --verdict v.json  # verifier: lock, then G3's survivors
    $PY tools/cards/cardtool.py verify FDN "Card Name" --verdict v.json --reviewer NAME
    $PY tools/cards/cardtool.py verify M19 "Card Name" --reprint-of M21 --reviewer NAME  # a reprint

A draft is Python. It sets ``abilities`` (and ``keywords`` if they change) using IR constructors;
``compiled`` holds the compiler's abilities and ``compiled_keywords`` its keywords. See
``docs/MAPPER_GUIDE.md``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (REPO, HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import corpus
import gates
import irpy
from probe import Probe

from MTG_bot.core.ability_tree import to_dict
from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.executor.games import compile_supply


def _header(raw: Any, result: Any) -> list[str]:
    card = result.card if result else None
    pt = f" {raw.power_raw}/{raw.toughness_raw}" if raw.power_raw is not None else ""
    loyalty = f" loyalty {raw.loyalty_raw}" if raw.loyalty_raw else ""
    out = [f"== {raw.identity.name}  |  {raw.type_line}  |  {raw.mana_cost_raw or '(no cost)'}{pt}{loyalty}",
           f"oracle id: {raw.identity.oracle_id}"]
    if raw.keywords:
        out.append(f"MTGJSON keywords: {', '.join(raw.keywords)}")
    if card is not None and raw.back_face is not None:
        out.append(f"back face: {raw.back_face.name} | {raw.back_face.type_line}")
    return out


def _state(sc: corpus.SetCompile, oid: str) -> str:
    rec = sc.records.get(oid, {})
    if "needs_atom" in rec:
        return "needs-atom"
    if oid in sc.refused:
        return "refused"
    result = sc.results[oid]
    if card_records.is_verified(result, rec):
        return "verified"
    if result.record is not None:
        return "mapped"
    if result.unparsed or result.back_face_unparsed or result.ambiguities:
        return "partly-compiled"
    return "compiled"


def reprint_sources(sc: corpus.SetCompile, oids: Any) -> dict[str, str]:
    """oracle id -> another set holding a verified record of the same printed card (same
    ``text_sha``): candidates for ``verify --reprint-of``, which checks the tree bytes."""
    homes = {}
    for folder in sorted(p for p in card_records.RECORDS_DIR.iterdir() if p.is_dir() and p.name != sc.code):
        for oid, rec in card_records.load_records(folder.name).items():
            if oid in oids and "verified" in rec and rec.get("text_sha") == card_records.text_sha(sc.raw[oid]):
                homes.setdefault(oid, folder.name)
    return homes


def cmd_status(args: argparse.Namespace) -> int:
    """Per set: the cards by state, the reprints a verified record elsewhere may cover, and the
    verified cards by the date of their (last) stamp, the pace; for one set, the worklist."""
    from collections import Counter

    for code in args.set:
        sc = corpus.compile_set(code)
        states = {oid: _state(sc, oid) for oid in sc.raw if not sc.raw[oid].is_token and not sc.raw[oid].is_emblem}
        print(f"{code}: {len(states)} cards: " + ", ".join(f"{k} {v}" for k, v in Counter(states.values()).most_common()))
        homes = reprint_sources(sc, {oid for oid, st in states.items() if st != "verified"})
        if homes:
            names = sorted(f"{sc.raw[o].identity.name} ({h})" for o, h in homes.items())
            print(f"  reprints verified elsewhere ({len(homes)}; cardtool verify {code} CARD --reprint-of SET): "
                  + ", ".join(names[:6]) + (", ..." if len(names) > 6 else ""))
        days = Counter(sc.records[oid]["verified"].get("date") for oid, st in states.items() if st == "verified")
        if days:
            print("  verified, by the date of the last stamp: " + ", ".join(f"{d} {n}" for d, n in sorted(days.items())))
    if len(args.set) != 1:
        return 0
    todo = []  # the one set's worklist (sc and states are its own)
    for oid, st in states.items():
        if st in ("partly-compiled", "refused"):
            res = sc.results.get(oid)
            n = len(res.unparsed) + len(res.back_face_unparsed) if res else len(sc.raw[oid].sentences)
            todo.append((n, sc.raw[oid].identity.name, st))
    todo.sort()
    print(f"worklist ({len(todo)} cards, fewest unparsed sentences first):")
    for n, name, st in todo[: args.limit]:
        print(f"  {n}  {name}  [{st}]")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    sc = corpus.compile_set(args.set)
    oid = sc.by_name(args.card)
    raw = sc.raw[oid]
    result = sc.results.get(oid)
    print("\n".join(_header(raw, result)))
    print(f"state: {_state(sc, oid)}" + (f" ({sc.refused[oid]})" if oid in sc.refused else ""))
    registry = build_full_registry()
    print("sentences:")
    for i, s in enumerate(raw.sentences, 1):
        status = corpus.sentence_status(raw, result, s, registry) if result else "card refused"
        print(f"  {i}. [{status}] {s}")
    if raw.back_face is not None:
        for i, s in enumerate(raw.back_face.sentences, 1):
            print(f"  face {i}. {s}")
    base = result if result is not None else corpus.printed_only(raw)
    print("compiled tree:" if result is not None else "printed facts only (the card is refused):")
    print(irpy.render_card(base.card.keywords, base.card.abilities))
    return 0


def cmd_similar(args: argparse.Namespace) -> int:
    ex = corpus.Exemplars.load(rebuild=args.rebuild)
    for score, row in ex.search(args.sentence, args.k):
        print(f"--- {score:.2f}  [{row['tid']}]  {row['set']} {row['card']}: {row['sentence']}")
        print("    " + row["tree"].replace("\n", "\n    "))
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    """Run the compiler's sentence layer on any wording: template matches, then the frame fallback."""
    registry = build_full_registry()
    sentence = args.sentence.replace("~", args.name) if args.name else args.sentence
    if corpus.normalize(sentence, args.name) in corpus.masked_shapes():
        print("no parse: no template or frame matches this wording")
        return 1
    matches = list(registry.match(sentence))
    how = "template"
    if not matches:
        from MTG_bot.core.compiler.frames import compose

        matches = list(compose(sentence, registry))
        how = "frame"
    if not matches:
        print("no parse: no template or frame matches this wording")
        return 1
    for m in matches[:3]:
        outcome = m.outcome
        tree = next((getattr(outcome, a) for a in ("effect", "ability", "cost") if hasattr(outcome, a)), outcome)
        print(f"--- {how} {m.template.tid} ({type(outcome).__name__})")
        print("    " + irpy.render(tree, 4).replace("\n", "\n    "))
    return 0


def _draft_record(sc: corpus.SetCompile, oid: str, draft_path: Path) -> tuple[dict, Any, Any]:
    raw = sc.raw[oid]
    result = sc.results.get(oid)
    if result is not None and result.record is None:
        base = result  # the compiler's tree
    else:
        try:  # re-mapping a card that has a record: start from the compiler's own tree
            base = compile_card(raw, build_full_registry())
        except (StateCorruptionError, ValueError):
            base = corpus.printed_only(raw)  # a refused card: its printed facts only
    keywords, abilities = irpy.run_draft(draft_path.read_text(), base.card.abilities, base.card.keywords)
    record = {"schema": card_records.SCHEMA, "set": sc.code, "oracle_id": oid, "name": raw.identity.name,
              "text_sha": card_records.text_sha(raw),
              "ir": {"keywords": [to_dict(k) for k in keywords], "abilities": [to_dict(a) for a in abilities]}}
    card = card_records.build_card(raw, base.card, record["ir"])
    return record, base, card


def _check(sc: corpus.SetCompile, oid: str, draft: Path, clauses: list | None) -> tuple[dict, Any, list, list, Any]:
    record, base, card = _draft_record(sc, oid, draft)
    ex = corpus.Exemplars.load()
    fails, warns = gates.g0(sc.raw[oid], base.card, card, clauses=clauses, known_signatures=ex.signatures)
    supply = compile_supply("all", sc.code, records={**sc.records, oid: record}, require_verified=False)
    rep = Probe(supply, sc.code, oid).report()
    return record, card, fails, warns, rep


def cmd_try(args: argparse.Namespace, write: bool = False) -> int:
    sc = corpus.compile_set(args.set)
    oid = sc.by_name(args.card)
    clauses = json.loads(Path(args.clauses).read_text()) if getattr(args, "clauses", None) else None
    record, card, fails, warns, rep = _check(sc, oid, Path(args.draft), clauses)
    print("\n".join(_header(sc.raw[oid], None)))
    print("canonical tree (what the engine will run):")
    print(irpy.render_card(card.keywords, card.abilities))
    print(f"G0: {len(fails)} failure(s), {len(warns)} warning(s)")
    for f in fails:
        print(f"  FAIL {f}")
    for w in warns:
        print(f"  warn {w}")
    print(f"G1: {len(rep.errors)} engine error(s); trace sha {rep.sha()[:16]}")
    out = Path(args.out) if getattr(args, "out", None) else None
    text = rep.text()
    if out:
        out.write_text(text)
        print(f"probe trace written to {out}")
    else:
        print(text)
    if not write:
        return 1 if fails or rep.errors else 0
    if fails or rep.errors:
        print("NOT WRITTEN: fix the G0 failures and engine errors first.")
        return 1
    if clauses is None:
        print("NOT WRITTEN: --clauses is required (every oracle clause, with the tree path that implements it).")
        return 1
    record["mapping"] = {"author": args.author, "date": dt.datetime.now(dt.UTC).date().isoformat(),
                         "draft_py": Path(args.draft).read_text(), "clauses": clauses,
                         "g0_warnings": warns, "notes": args.notes or ""}
    record["probe"] = {"sha": rep.sha()}
    # Calibration cards are written exactly like every other card (a diverted record told mappers
    # which cards were calibration items); round.py score-mappers reads and then removes them.
    folder = card_records.RECORDS_DIR / sc.code
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{oid}.json"
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    print(f"written: record for {sc.raw[oid].identity.name} (unverified: gates G2-G4 decide)")
    return 0


def cmd_needs_atom(args: argparse.Namespace) -> int:
    sc = corpus.compile_set(args.set)
    oid = sc.by_name(args.card)
    raw = sc.raw[oid]
    record = {"schema": card_records.SCHEMA, "set": sc.code, "oracle_id": oid, "name": raw.identity.name,
              "text_sha": card_records.text_sha(raw),
              "needs_atom": {"missing": args.missing, "author": args.author, "date": dt.datetime.now(dt.UTC).date().isoformat()}}
    folder = card_records.RECORDS_DIR / sc.code
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{oid}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    print(f"needs-atom recorded for {raw.identity.name}: {args.missing}")
    return 0


def _supply_and_oid(code: str, card: str) -> tuple[Any, str]:
    sc = corpus.compile_set(code)
    oid = sc.by_name(card)
    return compile_supply("all", code, require_verified=False), oid


def cmd_probe(args: argparse.Namespace) -> int:
    supply, oid = _supply_and_oid(args.set, args.card)
    if oid not in supply.pool.results:
        print("the card is not in the supply (refused, no record)")
        return 1
    rep = Probe(supply, args.set, oid).report()
    text = rep.text()
    if args.out:
        Path(args.out).write_text(text)
        print(f"{len(rep.errors)} engine error(s); trace sha {rep.sha()[:16]}; written to {args.out}")
    else:
        print(text)
    return 1 if rep.errors else 0


def cmd_mutate(args: argparse.Namespace) -> int:
    supply, oid = _supply_and_oid(args.set, args.card)
    res = gates.g3(supply, args.set, oid, limit=args.limit)
    print(f"mutants {res['mutants']}, killed {res['killed']}, score {res['score']}")
    critical = [s for s in res["survived"] if gates.is_critical(s[0])]
    for op, where in res["survived"]:
        print(f"  SURVIVED{' (critical)' if (op, where) in critical else ''}: {op} at {where}")
    return 1 if critical else 0


def _oracle_text(raw: Any) -> str:
    lines = list(raw.sentences)
    if raw.back_face is not None:
        lines += [f"// {raw.back_face.name} ({raw.back_face.type_line})", *raw.back_face.sentences]
    return "\n".join(lines)


def cmd_packet(args: argparse.Namespace) -> int:
    """A blind review packet (gate G2): the printed card, the tree the engine runs, the G1 trace.
    No mapper notes. With --plant SEED the tree is a fault-model mutant the probe can see, and
    the answer key goes to --key (never to the verifier)."""
    from MTG_bot.utils import rng

    supply, oid = _supply_and_oid(args.set, args.card)
    sc = corpus.compile_set(args.set)
    raw = sc.raw[oid]
    card = supply.pool.results[oid].card
    planted = None
    if args.plant is not None:
        base_sha = Probe(supply, args.set, oid).report().sha()
        cands = []
        for op, where, mutant in gates.mutants(card):
            if not gates.is_critical(op):
                continue
            with gates.swapped(supply, oid, mutant):
                if Probe(supply, args.set, oid).report().sha() != base_sha:
                    cands.append((op, where, mutant))
        if not cands:
            print("no observable critical mutant to plant for this card")
            return 1
        pick = rng.substream("scenario", "plant", args.set, oid, args.plant).randrange(len(cands))
        planted = cands[pick]
        card = planted[2]
    with gates.swapped(supply, oid, card) if planted else _null():
        rep = Probe(supply, args.set, oid).report()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pid = args.id or f"{args.set}-{oid[:8]}"
    text = "\n".join([
        f"# Review packet {pid}",
        *_header(raw, None),
        "", "## Oracle text (printed)", _oracle_text(raw),
        "", "## The tree the engine runs (Python IR)", "```python",
        irpy.render_card(card.keywords, card.abilities), "```",
        "", f"## G1 behaviour probe (trace sha {rep.sha()})", rep.text(),
    ])
    (out / f"{pid}.md").write_text(text + "\n")
    if planted and args.key:
        key = Path(args.key)
        key.mkdir(parents=True, exist_ok=True)
        (key / f"{pid}.json").write_text(json.dumps({"id": pid, "set": args.set, "oracle_id": oid,
                                                     "planted": planted[0], "where": planted[1]}) + "\n")
    print(f"packet {pid}: {out / f'{pid}.md'}" + (" (planted)" if planted else ""))
    return 0


class _null:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


def cmd_runpack(args: argparse.Namespace) -> int:
    """Run spec packs against the set's supply WITH unverified card records applied (the tree a
    verifier is reviewing). tools/run_scenarios.py itself only sees verified trees."""
    from run_scenarios import run_pack

    records = None
    if args.draft:
        if not args.card:
            print("--draft needs --card")
            return 2
        sc = corpus.compile_set(args.set)
        oid = sc.by_name(args.card)
        record, _base, _card = _draft_record(sc, oid, Path(args.draft))
        records = {**sc.records, oid: record}
    supply = compile_supply("all", args.set, records=records, require_verified=False)
    bad_total = 0
    for path in map(Path, args.packs):
        bad = run_pack(path, supply)
        print(("FAIL " if bad else "PASS ") + path.name)
        for line in bad:
            print(f"     {line}")
        bad_total += bool(bad)
    return 1 if bad_total else 0


def next_pack_path(dest: Path, stem: str) -> Path:
    """The first ``<stem>_<i>.json`` in ``dest`` not yet taken. A re-verification adds its spec
    packs beside the earlier ones, never over them: they stay regression tests (wave 1 found a
    re-verification overwriting them, KNOWLEDGE 201)."""
    i = 1
    while (dest / f"{stem}_{i}.json").exists():
        i += 1
    return dest / f"{stem}_{i}.json"


def kept_pack_path(dest: Path, stem: str, text: str) -> Path:
    """Where a verified spec pack goes: this card's existing pack with the same text, so a
    re-verification that carries a pack again keeps one copy of it; else the next free index."""
    i = 1
    while (dest / f"{stem}_{i}.json").exists():
        if (dest / f"{stem}_{i}.json").read_text() == text:
            return dest / f"{stem}_{i}.json"
        i += 1
    return dest / f"{stem}_{i}.json"


def judgments(verdict: dict) -> str:
    """The sha256 of what a review judged: the verdict, the trace it read, and each clause's status
    and issue. Evidence and packs stay out: the verifier adds to them after the lock."""
    body = {"verdict": verdict.get("verdict"), "probe_sha": verdict.get("probe_sha"),
            "clauses": [[c.get("clause", ""), c.get("status", ""), c.get("issue", "")]
                        for c in verdict.get("clauses", [])]}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


LEDGER = "locks.jsonl"


def lock_problem(path: Path, verdict: dict) -> str | None:
    """Why a locked verdict cannot stand: its judgments changed after the lock, or it was locked
    again (the ledger beside it keeps every lock, the first one counts)."""
    lock = verdict.get("lock")
    if lock is None:
        return None
    if lock.get("sha") != judgments(verdict):
        return "G2: the judgments changed after the review was locked (the survivors were shown then)"
    ledger = path.parent / LEDGER
    if ledger.exists():
        first = next((e for e in map(json.loads, ledger.read_text().splitlines())
                      if e.get("id") == verdict.get("id")), None)
        if first is not None and first.get("sha") != lock.get("sha"):
            return f"G2: the verdict was locked again after a change ({LEDGER} keeps the first lock)"
    return None


def uncovered_survivors(supply: Any, set_code: str, oid: str, packs: list[Path],
                        limit: int) -> tuple[dict, list[tuple[str, str, Any]]]:
    """G3, then every critical survivor that no pack tells apart from the card (the pack fails on
    the mutant), as (operator, where, mutant)."""
    from run_scenarios import run_pack

    card = supply.pool.results[oid].card
    g3 = gates.g3(supply, set_code, oid, limit=limit)
    out = []
    for op, where in g3["survived"]:
        if not gates.is_critical(op):
            continue
        mutant = next(m for o, w, m in gates.mutants(card) if (o, w) == (op, where))
        with gates.swapped(supply, oid, mutant):
            killed = any(run_pack(pack, supply) for pack in packs)
        if not killed:
            out.append((op, where, mutant))
    return g3, out


#: The pack that told each kind of survivor apart in the waves' follow-ups (KNOWLEDGE 207).
PACK_HINTS = (
    ("amount", ("pin the exact number with more on offer than the text names: two Vampire cards in "
                "hand for 'a Vampire', three cards for 'two'; for P/T, toughness as well as power")),
    ("until-end", "end the turn (advance_turn) and show the effect gone on the next turn"),
    ("permanent->", "end the turn and show the effect still there"),
    ("controller", ("let only one side qualify and pin that it is the printed one: both players' "
                    "creatures on the board, only the opponent casting the spell, the opponent's "
                    "library left untouched")),
    ("zone", "follow the card into the printed zone, and assert the other zone empty"),
    ("drop cost", ("activate without the cost (\"expect_raise\") or pin the cost paid: the mana spent, "
                   "the sacrificed permanent in the graveyard")),
    ("target->all", ("two eligible objects, only the targeted one changes; for 'up to one', also a run "
                     "with no target chosen")),
    ("optional", "decline the 'may' (its NONE word) and pin that nothing happens"),
    ("trigger scope", "make the event happen on the opponent's turn, or for the other player, and show no trigger"),
    ("each occurrence", ("one event holding two objects (two attackers, two creatures entering at once) "
                         "and the number of triggers: respond_to_triggers can counter one waiting "
                         "trigger with a verified card such as Tale's End")),
    ("trigger count", "one event holding two objects, and the number of triggers"),
    ("library order", ("two or more cards into the library and their order pinned: a seeded shuffle "
                       "for 'random', the owner's arrange ask for 'any order'")),
    ("trigger timing", "change the condition between the trigger and its resolution"),
)


def cmd_survivors(args: argparse.Namespace) -> int:
    """The verifier's last step, after the verdict file is written: lock its judgments, then list
    the critical mutants that none of its spec packs tells apart from the card, each with the
    kind of pack that did in earlier waves. Write those packs from the printed text, add them to
    the verdict's "packs", and run this again until nothing is listed; then report. The first run
    writes the lock (into the verdict and the ledger beside it); a later change to the judgments
    makes this and ``verify`` refuse."""
    path = Path(args.verdict)
    verdict = json.loads(path.read_text())
    if verdict.get("lock") is None:
        verdict["lock"] = {"sha": judgments(verdict), "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
        path.write_text(json.dumps(verdict, indent=1, ensure_ascii=False) + "\n")
        with (path.parent / LEDGER).open("a") as ledger:
            ledger.write(json.dumps({"id": verdict.get("id"), "file": path.name, **verdict["lock"]}) + "\n")
        print(f"locked {verdict.get('id')}: judgments {verdict['lock']['sha'][:16]} (change no status now)")
    elif problem := lock_problem(path, verdict):
        print(f"REFUSED: {problem}")
        return 1
    if verdict.get("verdict") != "OK":
        print("the verdict is not OK: no survivors to cover")
        return 0
    supply, oid = _supply_and_oid(args.set, args.card)
    if oid not in supply.pool.results:
        print("the card is not in the supply")
        return 1
    packs = [Path(x) for x in verdict.get("packs", [])]
    g3, uncovered = uncovered_survivors(supply, args.set, oid, packs, args.limit)
    print(f"G3: {g3['mutants']} mutants, {len(g3['survived'])} survive the probe; "
          f"{len(uncovered)} critical survive your {len(packs)} pack(s)")
    card = supply.pool.results[oid].card
    nodes = {"/".join(map(str, p)): n for p, n in gates._paths((card.keywords, card.abilities))}
    for op, where, _mutant in uncovered:
        hint = next((h for prefix, h in PACK_HINTS if op.startswith(prefix)), "")
        steps = where.split("/")
        part = next((nodes[k] for k in ("/".join(steps[:i]) for i in range(len(steps), 1, -1))
                     if type(nodes.get(k)).__name__ in ("Atom", "Cost", "TriggeredAbility")), nodes.get(where))
        shown = irpy.render(part, 4).splitlines()
        print(f"- {op} at {where}\n  a pack that kills it: {hint}\n  in: "
              + "\n      ".join(shown[:10]) + ("\n      ..." if len(shown) > 10 else ""))
    return 1 if uncovered else 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Stamp a card verified when every gate agrees: G0 clean, G1 no engine error and the trace the
    reviewer read, G2 verdict OK (and unchanged since its lock), G3 no critical survivor that no
    spec pack kills, G4 packs pass."""
    from run_scenarios import run_pack

    sc = corpus.compile_set(args.set)
    oid = sc.by_name(args.card)
    raw = sc.raw[oid]
    home, hrec, records = getattr(args, "reprint_of", None), None, None  # round.py apply passes none
    if home:
        hrec = card_records.load_records(home).get(oid)
        if not hrec or "verified" not in hrec or hrec.get("text_sha") != card_records.text_sha(raw):
            print(f"REFUSED: {home} holds no verified record of this card with the same printed text")
            return 1
        records = {**sc.records, oid: {k: v for k, v in hrec.items() if k != "verified"} | {"set": args.set}}
    supply = compile_supply("all", args.set, records=records, require_verified=False)
    if oid not in supply.pool.results:
        print("REFUSED: the card is not in the supply")
        return 1
    result = supply.pool.results[oid]
    card = result.card
    problems: list[str] = []
    pack_supply, pack_set = supply, args.set
    rep = Probe(supply, args.set, oid).report()
    if hrec is not None:
        # A reprint: the same tree bytes as a card its home set verified, so that review stands here
        # (Decision 3). Its evidence lives in the home set: the packs and G3 run again there, where
        # their supporting cards are, and the home stamp must still hold. The trace here differs
        # only where the probe's stimuli use this set's own cards; it must raise nothing.
        pack_supply, pack_set = compile_supply("all", home, require_verified=False), home
        if not card_records.is_verified(pack_supply.pool.results[oid], hrec):
            print(f"REFUSED: the {home} stamp no longer matches {home}'s tree")
            return 1
        if card_records.tree_sha(card) != hrec["verified"]["tree_sha"]:
            problems.append(f"G0: the tree here differs from the one {home} verified")
        verdict = {"verdict": "OK", "probe_sha": rep.sha(), "clauses": hrec["verified"].get("clauses", []),
                   "packs": [str(REPO / p) for p in hrec["verified"].get("packs", [])]}
    else:
        if not args.verdict:
            print("verify needs --verdict (or --reprint-of SET)")
            return 2
        verdict = json.loads(Path(args.verdict).read_text())
    base = corpus.printed_only(raw).card if oid in sc.refused else card
    fails, _warns = gates.g0(raw, base, card, clauses=None, known_signatures=None)
    problems += [f"G0: {f}" for f in fails]
    if rep.errors:
        problems.append(f"G1: {len(rep.errors)} engine error(s)")
    if verdict.get("probe_sha") != rep.sha():
        problems.append("G1: the reviewer read a different trace (re-run the packet)")
    if verdict.get("verdict") != "OK" or any(c.get("status") == "WRONG" for c in verdict.get("clauses", [])):
        problems.append("G2: the review did not pass")
    if not home and (problem := lock_problem(Path(args.verdict), verdict)):
        problems.append(problem)
    packs = [Path(x) for x in verdict.get("packs", [])]
    if any(c.get("status") == "NOT_EXERCISED" for c in verdict.get("clauses", [])) and not packs:
        problems.append("G2/G4: clauses NOT_EXERCISED and no spec pack")
    for pack in packs:
        bad = run_pack(pack, pack_supply)
        if bad:
            problems.append(f"G4: pack {pack.name} fails: {bad[0][:120]}")
    g3, uncovered = uncovered_survivors(pack_supply, pack_set, oid, packs, args.limit)
    problems += [f"G3: critical mutant survives every check: {op} at {where}" for op, where, _m in uncovered]
    if problems:
        print("NOT VERIFIED:")
        for pr in problems:
            print(f"  {pr}")
        return 1
    kept = []
    if hrec is not None:
        kept = list(hrec["verified"].get("packs", []))  # they run in the suite on the home set's pool
    else:
        dest = REPO / "tools" / "scenarios" / "cards" / args.set
        stem = raw.identity.name.lower().replace(' ', '_').replace(',', '')
        dest.mkdir(parents=True, exist_ok=True)
        for pack in packs:
            text = pack.read_text()
            target = kept_pack_path(dest, stem, text)
            if not target.exists():
                target.write_text(text)
            kept.append(str(target.relative_to(REPO)))
    path = card_records.RECORDS_DIR / args.set / f"{oid}.json"
    earlier = json.loads(path.read_text()).get("verified", {}).get("packs", []) if path.exists() else []
    for gone in sorted(set(earlier) - set(kept)):
        print(f"  no longer listed (still in the suite until removed): {gone}")
    record = json.loads(path.read_text()) if path.exists() else {
        "schema": card_records.SCHEMA, "set": args.set, "oracle_id": oid, "name": raw.identity.name,
        "text_sha": card_records.text_sha(raw)}
    if hrec is not None:  # the tree is the home record's: its ir, or the compiler's when it has none
        record.pop("needs_atom", None)
        if "ir" in hrec:
            record["ir"] = hrec["ir"]
        else:
            record.pop("ir", None)
    record["verified"] = {
        "tree_sha": card_records.tree_sha(card), "probe_sha": rep.sha(), "date": dt.datetime.now(dt.UTC).date().isoformat(),
        "reviewer": args.reviewer, "clauses": verdict.get("clauses", []), "packs": kept,
        "mutation": {"mutants": g3["mutants"], "killed": g3["killed"], "score": g3["score"],
                     "survived": [f"{o} at {w}" for o, w in g3["survived"]]},
    }
    if hrec is not None:
        record["verified"]["reprint_of"] = home
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    print(f"VERIFIED {raw.identity.name}: mutation score {g3['score']}, packs {len(kept)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status")
    p.add_argument("set", nargs="+")
    p.add_argument("--limit", type=int, default=60)
    p = sub.add_parser("show")
    p.add_argument("set")
    p.add_argument("card")
    p = sub.add_parser("similar")
    p.add_argument("sentence")
    p.add_argument("-k", type=int, default=6)
    p.add_argument("--rebuild", action="store_true")
    for name in ("try", "write"):
        p = sub.add_parser(name)
        p.add_argument("set")
        p.add_argument("card")
        p.add_argument("draft")
        p.add_argument("--clauses")
        p.add_argument("--out")
        if name == "write":
            p.add_argument("--author", required=True)
            p.add_argument("--notes")
    p = sub.add_parser("parse")
    p.add_argument("sentence")
    p.add_argument("--name", default="", help="the card name, substituted for ~")
    p = sub.add_parser("needs-atom")
    p.add_argument("set")
    p.add_argument("card")
    p.add_argument("--missing", required=True)
    p.add_argument("--author", default="")
    p = sub.add_parser("packet")
    p.add_argument("set")
    p.add_argument("card")
    p.add_argument("--out", required=True)
    p.add_argument("--id")
    p.add_argument("--plant", type=int)
    p.add_argument("--key")
    p = sub.add_parser("runpack")
    p.add_argument("set")
    p.add_argument("packs", nargs="+")
    p.add_argument("--card", help="with --draft: the card the draft is for")
    p.add_argument("--draft", help="run the packs against this unwritten draft of --card")
    p = sub.add_parser("survivors")
    p.add_argument("set")
    p.add_argument("card")
    p.add_argument("--verdict", required=True)
    p.add_argument("--limit", type=int, default=80)
    p = sub.add_parser("verify")
    p.add_argument("set")
    p.add_argument("card")
    p.add_argument("--verdict")
    p.add_argument("--reprint-of", metavar="SET", help="the set whose verified record of this card stands here")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--limit", type=int, default=80)
    for name in ("probe", "mutate"):
        p = sub.add_parser(name)
        p.add_argument("set")
        p.add_argument("card")
        p.add_argument("--out")
        p.add_argument("--limit", type=int, default=80)
    args = ap.parse_args(argv)
    from MTG_bot.utils import rng

    rng.seed_all(20261029)  # the tool's master seed; a plant is keyed by (set, card, --plant)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "show":
        return cmd_show(args)
    if args.cmd == "similar":
        return cmd_similar(args)
    if args.cmd == "parse":
        return cmd_parse(args)
    if args.cmd == "try":
        return cmd_try(args)
    if args.cmd == "write":
        return cmd_try(args, write=True)
    if args.cmd == "needs-atom":
        return cmd_needs_atom(args)
    if args.cmd == "probe":
        return cmd_probe(args)
    if args.cmd == "packet":
        return cmd_packet(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "survivors":
        return cmd_survivors(args)
    if args.cmd == "runpack":
        return cmd_runpack(args)
    return cmd_mutate(args)


if __name__ == "__main__":
    sys.exit(main())
