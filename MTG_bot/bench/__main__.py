"""Command line for the benchmark core.

    python -m MTG_bot.bench duel --a uniform --b pass --deals 20 [--set M21] [--out FILE.jsonl]
    python -m MTG_bot.bench rules --answerer null|oracle|llm [--masked] [--limit N] [--export FILE.jsonl]
    python -m MTG_bot.bench primer [--masked] [--json]

Agents: pass, uniform, random-policy (the engine's hand-weighted RandomPolicy), llm (local
OpenAI-compatible endpoint from MTG_BENCH_LLM_*; remote hosts refused unless
MTG_BENCH_ALLOW_REMOTE=1). Every run calls seed_all first, and the duel manifest records the seed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from MTG_bot.bench import CANARY
from MTG_bot.bench.agents import PassAgent, UniformRandomAgent
from MTG_bot.bench.duel import DealSpec, run_match, summarize
from MTG_bot.bench.view import OracleIndex, ViewOptions
from MTG_bot.core.executor.games import TURN_CAP, RandomPolicy
from MTG_bot.utils import rng


def _primer_text(masked: bool, salt: str) -> str:
    from MTG_bot.bench.masking import NameMasker
    from MTG_bot.bench.primer import attach_pack_evidence, census, render_primer

    entries = census()
    attach_pack_evidence(entries)
    oracle = OracleIndex.for_sets("M21", "ZNR")
    masker = NameMasker(oracle.names, salt, keep=oracle.token_names) if masked else None
    return render_primer(entries, masker)


def _factory(kind: str, args: argparse.Namespace) -> Any:
    if kind == "pass":
        return lambda deal, game, seat: PassAgent()
    if kind == "uniform":
        return lambda deal, game, seat: UniformRandomAgent(rng.substream("bench", deal.seed, game, seat))
    if kind == "random-policy":
        return lambda deal, game, seat: RandomPolicy(rng.substream("bench", deal.seed, game, seat).randrange(2**31))
    if kind == "llm":
        from MTG_bot.bench.llm import LLMAgent, OpenAICompatClient

        primer = _primer_text(args.masked, args.salt) if args.primer else ""
        return lambda deal, game, seat: LLMAgent(OpenAICompatClient.from_env(), primer=primer)
    raise SystemExit(f"unknown agent {kind!r}")


def cmd_duel(args: argparse.Namespace) -> int:
    deals = [
        DealSpec(seed=s, set_code=args.set, pool_mode=args.pool, turn_cap=args.turn_cap)
        for s in range(args.first_deal, args.first_deal + args.deals)
    ]
    rows = run_match(
        _factory(args.a, args), _factory(args.b, args), deals,
        name_a=args.a, name_b=args.b, opts=ViewOptions(mask_names=args.masked, salt=args.salt),
        out=Path(args.out) if args.out else None,
    )
    print(json.dumps(summarize(rows), indent=1))
    return 0


def _extract_json(text: str) -> dict[str, Any]:
    for match in reversed(list(re.finditer(r"\{.*\}", text or "", re.DOTALL))):
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except ValueError:
            continue
    return {}


def cmd_rules(args: argparse.Namespace) -> int:
    from MTG_bot.bench.rules_track import (
        NullAnswerer,
        OracleAnswerer,
        build_items,
        score,
    )
    from MTG_bot.bench.stats import paired_bootstrap

    items, cov = build_items(masked=args.masked, salt=args.salt)
    items = items[: args.limit] if args.limit else items
    if args.export:
        with Path(args.export).open("w", encoding="utf-8") as out:
            out.write(json.dumps({"kind": "manifest", "canary": CANARY, "items": len(items)}) + "\n")
            out.writelines(json.dumps(item.to_json()) + "\n" for item in items)
    if args.answerer == "llm":
        from MTG_bot.bench.llm import OpenAICompatClient

        client = OpenAICompatClient.from_env()
        system = "Answer the Magic: The Gathering rules question. End with the JSON object asked for.\n\n"
        system += _primer_text(args.masked, args.salt) if args.primer else ""

        def answer(item: Any) -> dict[str, Any]:
            reply = client.complete(
                [{"role": "system", "content": system}, {"role": "user", "content": item.prompt}],
                max_tokens=1024, temperature=0.0,
            )
            return _extract_json(reply.text)
    else:
        answerer = OracleAnswerer() if args.answerer == "oracle" else NullAnswerer()
        answer = answerer.answer
    scores = [score(item, answer(item)) for item in items]
    delta = [s["delta"] for s in scores if s["delta"] is not None]
    report = {
        "items": len(items),
        "excluded": dict(cov.excluded),
        "variant": "masked" if args.masked else "real",
        "all_keys": [round(x, 4) for x in paired_bootstrap([s["all_keys"] for s in scores])],
        "delta (headline)": [round(x, 4) for x in paired_bootstrap(delta)] if delta else None,
        "label": "exploratory (no pre-registration file); public development split",
    }
    print(json.dumps(report, indent=1))
    return 0


def cmd_primer(args: argparse.Namespace) -> int:
    from MTG_bot.bench.primer import attach_pack_evidence, census, coverage

    if args.json:
        entries = census()
        attach_pack_evidence(entries)
        print(json.dumps(coverage(entries), indent=1))
    else:
        print(_primer_text(args.masked, args.salt))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m MTG_bot.bench", description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--seed", type=int, default=20261024, help="master seed (recorded in manifests)")
    ap.add_argument("--masked", action="store_true", help="mask card names (the contamination probe)")
    ap.add_argument("--salt", default="public-dev", help="masking salt; keep the private split's secret")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("duel")
    d.add_argument("--a", default="uniform")
    d.add_argument("--b", default="pass")
    d.add_argument("--deals", type=int, default=20)
    d.add_argument("--first-deal", type=int, default=1)
    d.add_argument("--set", default="M21")
    d.add_argument("--pool", default="castable")
    d.add_argument("--turn-cap", type=int, default=TURN_CAP)
    d.add_argument("--primer", action="store_true", help="give llm seats the engine primer")
    d.add_argument("--out")
    r = sub.add_parser("rules")
    r.add_argument("--answerer", choices=("null", "oracle", "llm"), default="null")
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--export")
    r.add_argument("--primer", action="store_true")
    p = sub.add_parser("primer")
    p.add_argument("--json", action="store_true", help="print coverage numbers instead of the primer text")
    args = ap.parse_args(argv)
    rng.seed_all(args.seed, seed_frameworks=False)
    return {"duel": cmd_duel, "rules": cmd_rules, "primer": cmd_primer}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
