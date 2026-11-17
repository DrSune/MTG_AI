"""Every card of the 19 sets as the network reads it, with its state. Run from the repo root
(CPU only, gently):

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python \
        reports/component_review_2026-11-17/dump.py [out.pkl]

(default ``.cache/component_review/dump.pkl``, gitignored, where the other scripts read it).

Per card (tokens and emblems left out), from ``corpus.compile_set`` (card records applied, the
supply's compile) and ``cardtool._state``:
- set, oracle id, name, state (verified, mapped, needs-atom, compiled, partly-compiled, refused),
  whether a verified stamp is a reprint's (``verified.reprint_of``), text_sha, tree_sha;
- ``tokens``: ``features.card_tokens`` untruncated (the network keeps the first ``max_ir`` = 128);
- ``face``: the face tokens (types, subtypes, mana value) and ``abilities``: each ability's own
  ``ir_tokens`` (keywords as one entry each), so an ability's tokens can be told apart;
- ``tree``: the ``to_dict`` abilities and keywords (structure analyses);
- the unparsed sentences of the card (front and back) with the compiler's bucket hint, its
  printed sentences, and a needs-atom record's text.
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "tools" / "cards"):
    sys.path.insert(0, str(p))
import MTG_bot

assert MTG_bot.__file__.startswith(str(REPO)), MTG_bot.__file__

import corpus
from cardtool import _state

from MTG_bot.core.ability_tree import to_dict
from MTG_bot.core.compiler import card_records
from tools.selfplay import features as FT


def main(out: str) -> None:
    rows = []
    for code in corpus.SETS:
        t = time.time()
        sc = corpus.compile_set(code)
        n = 0
        for oid, raw in sc.raw.items():
            if raw.is_token or raw.is_emblem:
                continue
            n += 1
            rec = sc.records.get(oid, {})
            state = _state(sc, oid)
            row = {
                "set": code, "oid": oid, "name": raw.identity.name, "state": state,
                "reprint_of": (rec.get("verified") or {}).get("reprint_of"),
                "text_sha": card_records.text_sha(raw),
                "sentences": list(raw.sentences),
                "back_sentences": list(raw.back_face.sentences) if raw.back_face else [],
                "needs_atom": rec.get("needs_atom"),
                "record": "ir" in rec,
                "refused": sc.refused.get(oid),
            }
            if oid not in sc.refused:
                res = sc.results[oid]
                card = res.card
                row["tree_sha"] = card_records.tree_sha(card)
                row["tokens"] = FT.card_tokens(card)
                row["face"] = ([f"type:{x}" for x in card.types] + [f"sub:{x}" for x in card.subtypes]
                               + [f"mv:{FT._bucket(card.mana_value)}"])
                # each ability's own tokens (the card's are face + "@abilities" + these + "@keywords"
                # + the keywords'); kind "kw" or "ab" first
                row["abilities"] = ([("ab", FT.ir_tokens(to_dict(a))) for a in card.abilities]
                                    + [("kw", FT.ir_tokens(to_dict(k))) for k in card.keywords])
                row["tree"] = {"keywords": [to_dict(k) for k in card.keywords],
                               "abilities": [to_dict(a) for a in card.abilities]}
                row["unparsed"] = [list(u) for u in res.unparsed]
                row["back_unparsed"] = [list(u) for u in res.back_face_unparsed]
                row["ambiguities"] = len(res.ambiguities)
            rows.append(row)
        print(code, n, f"{time.time() - t:.1f}s", file=sys.stderr, flush=True)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(pickle.dumps(rows))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(REPO / ".cache" / "component_review" / "dump.pkl"))
