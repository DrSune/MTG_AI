#!/usr/bin/env python3
"""PZL certificate harness (pipeline step ①) — the honest puzzle census.

Answers "how many real puzzles do we actually have today": every pack in
``tools/scenarios`` that carries scripted ``decisions`` gold words is replayed
through the REAL executor; each ask whose answer came from the script becomes
one PUZZLE ITEM — (position, candidate vocabulary at the ask, gold answer,
binary terminal from the pack's ``expect`` block). Each item then ships a
family-PZL certificate per docs/METRICS.md §10 rule 3:

* ``null_score``   — the do-nothing policy: from the puzzle position every ask
  answers with its pass word (PASS/NONE/DECLINE/skip when the vocabulary
  carries one, else the engine's first legal word — the conservative C15
  canonical); score = 1.0 iff the promised ``expect`` outcome still lands.
* ``random_score`` — mean over N uniform-random rollouts (default 200); D9:
  every rollout draws its own rotated seed sha256(world_seed|item|rollout),
  the engine replay itself is deterministic (decisions.py: the provider is a
  pure consumer of the CALLER's rng).
* ``oracle_score`` — the scripted gold line (the pack as written).

Scoring is BINARY (PZL rule 2: no proximity — the 0.900 failure class); the
zeroth bit of ladder health is the punish-inaction flag (rule 4): an item with
``null_score == 0`` punishes inaction; ``null_score >= 0.5`` is a
NO-DISCRIMINATION flag — the pack's expect lanes simply do not care whether
the gold call was made. Those are ladder gaps to author against, reported
loud, not harness failures.

Instrumentation is MONKEY-PATCHING ONLY — tools/run_scenarios.py and the
engine are never edited. All three decision lanes (per-op pool, FIFO,
ask-time provider) funnel through the single choke point
:meth:`MTG_bot.core.executor.quantity.ExecCtx.take_decision`, so one wrapper
sees every ask with its exact vocabulary: in EXTRACTION mode it records
(what, vocab, answer, lane); in REPLAY mode a policy short-circuits every ask
from the puzzle item's global ordinal onward (prefix asks delegate to the
vanilla engine, so the puzzle position is reached byte-identically; scripted
world ops — opponent steps, casts, planning-lane designations — keep running:
null passes ASKS, it does not stop the world).

Honesty (corpus header): oracle bias — the gold line defines correct, the
item can never measure more than the script knows; D10 — certificates are
computed on the CURRENT target surfaces, recompute after the geyser-sweep arc
before pinning baseline 0; random>0.05 items are rejected ladder candidates
(PZL rule 3), which this harness marks as ``l1_ready = False``.

Usage:
    .venv/bin/python tools/audit/puzzle_cert.py [--rollouts 200]
        [--dir tools/scenarios] [--out tools/audit/puzzle_corpus.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.executor.quantity import ExecCtx
from tools.run_scenarios import ScenarioRunner

#: the ladder gate on random_score (PZL rule 3: reject at build time)
RANDOM_CEILING = 0.05

#: null-policy preference, first member present in the vocabulary wins
PASS_WORDS = ("PASS", "NONE", "DECLINE", "skip")


def null_word(vocab: tuple[str, ...]) -> str:
    """The do-nothing answer for one vocabulary: an explicit pass word when
    the site carries one, else the engine's first legal word (the same
    conservative canonical the harness provider itself falls back to)."""
    for w in PASS_WORDS:
        if w in vocab:
            return w
    return vocab[0]


# --------------------------------------------------------------------------
# single-choke-point instrumentation (patch from HERE; files stay untouched)
# --------------------------------------------------------------------------

_take_decision = ExecCtx.take_decision
_run_step = ScenarioRunner.run_step

#: active replay policy {"n", "ordinal", "answer"} or None (vanilla)
_policy: dict | None = None
#: active extraction recorder (list of AskRec) or None
_recorder: list | None = None
#: index of the step currently inside ScenarioRunner.run_step
_step_idx = [0]


@dataclass(frozen=True)
class AskRec:
    """One answered demand seen by the engine: site tag, the EXACT vocabulary,
    the answer, the pack step it happened in, and whether the per-op pool
    lane (a scripted ``decisions`` word) answered it."""

    what: str
    vocab: tuple[str, ...]
    answer: str
    step: int
    pool: bool


def _take_patched(self: ExecCtx, vocab: tuple, what: str) -> str:
    pol = _policy
    if pol is not None:
        i = pol["n"]
        pol["n"] = i + 1
        if i >= pol["ordinal"]:  # the puzzle ask AND everything after it
            ans = pol["answer"](tuple(vocab))
            if self.stream is not None:
                self.stream.ask_log.append((what, ans))
            return ans
        return _take_decision(self, vocab, what)  # gold prefix, byte-exact
    if _recorder is not None:
        pre_i, pre_n, pool_words = (
            self.decision_idx,
            len(self.decisions),
            self.decisions,
        )
        ans = _take_decision(self, vocab, what)
        _recorder.append(
            AskRec(
                what=what,
                vocab=tuple(vocab),
                answer=ans,
                step=_step_idx[0],
                pool=pre_i < pre_n and pool_words[pre_i] == ans,
            )
        )
        return ans
    return _take_decision(self, vocab, what)


_step_count: weakref.WeakKeyDictionary[ScenarioRunner, int] = (
    weakref.WeakKeyDictionary()
)


def _run_step_patched(self: ScenarioRunner, step: dict) -> None:
    n = _step_count.get(self, -1) + 1
    _step_count[self] = n
    _step_idx[0] = n
    _run_step(self, step)


ExecCtx.take_decision = _take_patched  # type: ignore[method-assign]
ScenarioRunner.run_step = _run_step_patched  # type: ignore[method-assign]


# --------------------------------------------------------------------------
# replay engine
# --------------------------------------------------------------------------


def _drive(
    pack: dict,
    supply: Any,
    ordinal: int | None = None,
    answer: Callable[[tuple[str, ...]], str] | None = None,
) -> tuple[ScenarioRunner | None, bool]:
    """Replay a pack; from ask ``ordinal`` onward every ask is answered by
    ``answer(vocab)`` (prefix asks stay the scripted gold line). Returns
    (runner or None on setup failure, binary success = every expect lane
    holds and no step errors outside its expect_raise contract)."""
    global _policy
    policy = None if answer is None else {"n": 0, "ordinal": ordinal, "answer": answer}
    try:
        runner = ScenarioRunner(pack, supply)
    except Exception:  # noqa: BLE001 — a broken pack is a failed rollout
        return None, False
    _policy = policy
    try:
        for step in pack["steps"]:
            want = step.get("expect_raise")
            try:
                runner.run_step(step)
            except Exception as e:  # noqa: BLE001
                if want is None or want not in f"{type(e).__name__}: {e}":
                    return runner, False
                continue
            if want is not None:
                return runner, False  # the refusal the pack promised never came
        return runner, not runner.check()
    finally:
        _policy = None


def replay(pack: dict, supply: Any) -> bool:
    """The gold line, exactly as the pack is written (= oracle rollout)."""
    return _drive(pack, supply)[1]


# --------------------------------------------------------------------------
# extraction: which asks were answered by a scripted decisions word
# --------------------------------------------------------------------------


def _scripted_for_step(
    step: dict, recs: list[AskRec], handles: dict[str, Any]
) -> list[tuple[AskRec, str]]:
    """The asks of one step whose answer was CONSUMED from the step's
    ``decisions`` script, mirrored lane-exactly against run_scenarios:
    non-combat providers pop one queue word per provider call; combat
    consults the answer maps/queues first and pops the generic script only
    for sites no map claims (r22a). Pool-lane asks consumed a scripted word
    by construction."""
    d = list(step.get("decisions", ()))
    out: list[tuple[AskRec, str]] = []
    if step["op"] == "combat":
        answers: dict[str, str] = {}
        queues: dict[str, list[str]] = {}
        for k, go in step.get("attack", {}).items():
            answers[f"attack:{handles[k]}"] = "ATTACK" if go else "DECLINE"
        for k, go in step.get("may", {}).items():
            answers[f"may:{handles[k]}"] = "fire" if go else "skip"
        for k, go in step.get("block", {}).items():
            answers[f"block:{handles[k]}"] = "NONE" if go is None else str(handles[go])
        for k, picks in step.get("order", {}).items():
            queues[f"order:{handles[k]}"] = [str(p) for p in picks]
        for k, amounts in step.get("trample", {}).items():
            queues[f"trample:{handles[k]}"] = [str(a) for a in amounts]
        for k, word in step.get("policy", {}).items():
            answers[f"policy:{handles[k]}"] = word
        script = list(d)
        for r in recs:
            if r.pool:
                out.append((r, r.answer))
                continue
            if any(r.what == k or r.what.startswith(k + ":") for k in answers):
                continue
            claimed = False
            for k, q in queues.items():
                if r.what == k or r.what.startswith(k + ":"):
                    claimed = True
                    if q:
                        q.pop(0)
                    break
            if claimed:
                continue
            if script:
                w = script.pop(0)
                res = str(handles[w]) if w in handles else w
                if res == r.answer:
                    out.append((r, w))
        return out
    queue = list(d)
    for r in recs:
        if r.pool:
            out.append((r, r.answer))
            continue
        if queue:
            w = queue.pop(0)
            res = str(handles[w]) if w in handles else w
            if res == r.answer:
                out.append((r, w))
    return out


def extract_items(pack: dict, supply: Any) -> list[dict]:
    """Run the gold line once and return one puzzle-item spec per scripted
    ask: {ordinal, step, what, vocab, gold (the resolved vocabulary token),
    gold_script (as written in the pack), ask_kind}."""
    global _recorder
    rec: list[AskRec] = []
    _recorder = rec
    try:
        runner, _ok = _drive(pack, supply)
    finally:
        _recorder = None
    if runner is None:
        return []
    by_step: dict[int, list[AskRec]] = {}
    for r in rec:
        by_step.setdefault(r.step, []).append(r)
    items: list[dict] = []
    for i, step in enumerate(pack["steps"]):
        for r, w in _scripted_for_step(step, by_step.get(i, []), runner.handles):
            items.append(
                {
                    "ordinal": rec.index(r),
                    "step": i,
                    "what": r.what,
                    "vocab": list(r.vocab),
                    "gold": r.answer,
                    "gold_script": w,
                    "ask_kind": r.what.split(":", 1)[0],
                }
            )
    return items


# --------------------------------------------------------------------------
# certification
# --------------------------------------------------------------------------


def _stable_int(key: str) -> int:
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def certify_pack(
    path: Path, pack: dict, supply: Any, rollouts: int = 200
) -> list[dict]:
    """The full PZL-1 certificate triple for every puzzle item of one pack."""
    card = next(
        (
            c.get("real") or c.get("name")
            for c in pack.get("cards", [])
            if c.get("real") or c.get("name")
        ),
        path.stem,
    )
    world_seed = pack.get("world", {}).get("seed", 7)
    oracle = 1.0 if replay(pack, supply) else 0.0
    pack_reclass = pack.get("eval_reclassification")
    out: list[dict] = []
    for spec in extract_items(pack, supply):
        vocab = tuple(spec["vocab"])
        item_id = f"{path.stem}:{spec['step']}:{spec['ordinal']}"
        null_ok = _drive(pack, supply, spec["ordinal"], null_word)[1]
        null_score = 1.0 if null_ok else 0.0
        n_random = 0
        for r_i in range(rollouts):
            rng = random.Random(_stable_int(f"{world_seed}|{item_id}|{r_i}"))
            ok = _drive(pack, supply, spec["ordinal"], rng.choice)[1]
            n_random += int(ok)
        random_score = n_random / rollouts if rollouts else 0.0
        npass = null_word(vocab)
        why = ""
        if null_score > 0:
            why = (
                "null-pick-equals-gold"
                if npass == spec["gold"]
                else "expect-insensitive (gold call not needed by any lane)"
            )
        # Honest reclassification (eval-granularity batch 2026-10-05): a pack
        # step — or the whole pack — may be DECLARED a branch-coverage twin /
        # structurally-unobservable ask via ``eval_reclassification``. The
        # item stays in the corpus for auditability, keeps its measured
        # scores, but leaves the offender ledger and the ladder/E budget:
        # it was never a candidate decision-ladder item. The reason is
        # mandatory and must name the pack or lane that carries the verdict.
        step_reclass = pack["steps"][spec["step"]].get("eval_reclassification")
        reclass = step_reclass or pack_reclass
        if isinstance(reclass, dict):
            if "reason" in reclass:
                reclass = reclass.get("reason", "unspecified")
            else:
                # item-level granularity: {"by_ask_kind": {"choose": ...}}
                reclass = reclass.get("by_ask_kind", {}).get(spec["ask_kind"], "")
        reclass = str(reclass) if reclass else ""
        out.append(
            {
                "card": card,
                "pack": path.name,
                "ask_kind": spec["ask_kind"],
                "ask_site": spec["what"],
                "step": spec["step"],
                "candidates_n": len(vocab),
                "candidates": list(vocab),
                "gold": spec["gold"],
                "gold_script": spec["gold_script"],
                "null": null_score,
                "null_pick": npass,
                "random": round(random_score, 4),
                "oracle": oracle,
                "rollouts": rollouts,
                "punish_inaction": null_score == 0.0,
                "no_discrimination": null_score >= 0.5 and not reclass,
                "reclassified": bool(reclass),
                "reclass_reason": reclass,
                "null_gt0_reason": why,
                "l1_ready": bool(
                    null_score == 0.0
                    and oracle == 1.0
                    and random_score <= RANDOM_CEILING
                    and len(vocab) >= 2
                    and not reclass
                ),
            }
        )
    return out


# --------------------------------------------------------------------------
# corpus emit
# --------------------------------------------------------------------------


def certify_dir(
    packs_dir: Path, supply: Any, rollouts: int = 200
) -> tuple[list[dict], dict]:
    """Certify every pack in a directory; returns (items, summary)."""
    items: list[dict] = []
    packs = sorted(packs_dir.glob("*.json"))
    with_decisions = 0
    broken: list[str] = []
    designation_lane: list[str] = []
    for p in packs:
        try:
            pack = json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001
            broken.append(f"{p.name}: {e}")
            continue
        scripted = any(s.get("decisions") for s in pack.get("steps", []))
        if scripted:
            with_decisions += 1
        its = certify_pack(p, pack, supply, rollouts)
        if scripted and not its:
            # every scripted word answered a CAST-time slot (designated
            # targets / declared modes consumed by the planning lane,
            # stack.py _plan_cast_designation) — a gold line, but the
            # harness never EXPOSED a menu ask, so no puzzle item exists
            designation_lane.append(p.name)
        items.extend(its)
    n = len(items)
    rand = [i["random"] for i in items]
    summary = {
        "packs_scanned": len(packs),
        "packs_with_decisions": with_decisions,
        "items": n,
        "punish_inaction": sum(i["punish_inaction"] for i in items),
        "l1_ready": sum(i["l1_ready"] for i in items),
        "no_discrimination": sum(i["no_discrimination"] for i in items),
        "reclassified": sum(i.get("reclassified", False) for i in items),
        "null_gt0_offenders": [
            {
                "card": i["card"],
                "pack": i["pack"],
                "ask_kind": i["ask_kind"],
                "gold": i["gold"],
                "null_pick": i["null_pick"],
                "why": i["null_gt0_reason"],
            }
            for i in items
            if i["null"] > 0 and not i.get("reclassified")
        ],
        "broken_packs": broken,
        "designation_lane_packs": designation_lane,
        "random_vs_oracle": {
            "mean_random": round(sum(rand) / n, 4) if n else None,
            "max_random": max(rand) if rand else None,
            "items_random_le_0.05": sum(r <= RANDOM_CEILING for r in rand),
            "histogram_random": {
                b: sum(
                    lo <= r < hi for r in rand
                )  # buckets [0,.05),[.05,.25),[.25,.5),[.5,1]
                for b, (lo, hi) in (
                    ("0-0.05", (0.0, 0.05)),
                    ("0.05-0.25", (0.05, 0.25)),
                    ("0.25-0.5", (0.25, 0.5)),
                    ("0.5-1.0", (0.5, 1.0001)),
                )
            },
        },
        "rollouts_per_item": rollouts,
        "seed_rotation": "sha256(world_seed|item|rollout) — D9 rotated rollout seeds",
    }
    return items, summary


CORPUS_NOTES = [
    "oracle bias (PZL rule 4 note): the scripted gold line defines correct; a",
    "certificate measures the pack's discrimination, never the ceiling of",
    "Magic skill. null/random/oracle are BINARY same-episode outcomes (PZL",
    "rule 2, no proximity). l1_ready additionally enforces PZL rule 3",
    "(random <= 0.05 at build). null>0 items are LADDER GAPS: the expect",
    "lanes do not punish inaction — author against them, do not delete them.",
    "D10 caveat: computed on current target surfaces; recompute after the",
    "geyser-sweep arc before pinning any baseline theta.",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--dir", default=str(REPO / "tools" / "scenarios"))
    ap.add_argument(
        "--out", default=str(REPO / "tools" / "audit" / "puzzle_corpus.json")
    )
    ap.add_argument("--rollouts", type=int, default=200)
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    supply = get_supply("all")
    items, summary = certify_dir(Path(args.dir), supply, args.rollouts)
    corpus = {
        "header": {
            "produced_by": "tools/audit/puzzle_cert.py",
            "rollouts_per_item": args.rollouts,
            "notes": " ".join(CORPUS_NOTES),
        },
        "summary": summary,
        "items": items,
    }
    Path(args.out).write_text(json.dumps(corpus, indent=1) + "\n")
    dt = time.perf_counter() - t0
    s = summary
    print(
        f"items={s['items']} l1_ready={s['l1_ready']} "
        f"punish_inaction={s['punish_inaction']} "
        f"no_discrimination={s['no_discrimination']} "
        f"mean_random={s['random_vs_oracle']['mean_random']} "
        f"({dt:.1f}s, {s['rollouts_per_item']} rollouts/item)"
    )
    for off in s["null_gt0_offenders"]:
        print(f"NULL>0 {off['pack']} [{off['ask_kind']}] {off['why']}")
    for b in s["broken_packs"]:
        print(f"BROKEN {b}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
