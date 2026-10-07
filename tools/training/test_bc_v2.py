"""Batch-2 laws: corpus join, vocab-prefix law, grounding coverage, zone
delta, and the two-lane choose-digest stash. Run::

    pytest tools/training/test_bc_v2.py -q
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path

import pytest

from MTG_bot.core.identity import Handle
from MTG_bot.core.executor import query as query_mod
from MTG_bot.core.executor.decisions import site_digest

from tools.training import bc_data, bc_data_v2 as v2

REPO = Path(__file__).resolve().parents[2]
EPISODES = REPO / "tools" / "training" / "episodes_v2.jsonl"
CORPUS = REPO / "tools" / "audit" / "puzzle_corpus.json"


@pytest.fixture(scope="module")
def episodes():
    return v2.load_episodes(EPISODES)


@pytest.fixture(scope="module")
def vocab(episodes):
    return v2.build_vocab_v2(episodes)


@pytest.fixture(scope="module")
def dataset(episodes, vocab):
    return v2.build_dataset_v2(episodes, vocab)


# ----------------------------------------------------------------- integrity
def test_joins_the_static_corpus_at_155(dataset):
    """Authoritative law: every v2 gold line maps to a corpus item. The OLD
    episodes.jsonl is stale (pre corpus-v2) — join to the corpus is truth."""
    corpus = __import__("json").loads(CORPUS.read_text(encoding="utf-8"))
    assert v2.join_corpus(dataset, corpus["items"]) == 155  # v4 regen 2026-10-07


# ------------------------------------------------------------- schema laws
def test_obs_words_v2_extends_v1_as_a_prefix(episodes):
    """v2 observation words = v1 words, UNTOUCHED, then the zone delta."""
    for ep in episodes:
        for row in ep["asks"]:
            w1 = bc_data.obs_words(row["obs"])
            assert v2.obs_words_v2(row["obs"])[: len(w1)] == w1


def test_vocab_v2_is_a_superset_of_vocab_v1(episodes):
    """Every v1 word survives; ids may SHIFT (zone delta words enter the
    enumeration early), but the v2 encoder is self-consistent and the
    candidate span law is checked in WORD terms elsewhere."""
    v1 = bc_data.build_vocab(episodes)
    v2v = v2.build_vocab_v2(episodes)
    assert set(v1) <= set(v2v)


def test_zone_delta_tags_present(episodes):
    tags = {
        w
        for ep in episodes
        for row in ep["asks"]
        for w in v2.zone_rows_v2(row["obs"])
        if w in ("lib", "gyr", "exl")
    }
    assert tags == {"lib", "gyr", "exl"}, "every delta zone must appear"


def test_cand_ids_keep_the_v1_vocab_prefix(dataset, vocab):
    """Permutation-law safety: inside every grounded candidate span the v2
    ids start with EXACTLY the v1 tokenization; referent rows follow a
    single ``ref`` separator."""
    unk = vocab[bc_data.UNK]
    ref = vocab[v2.REF]
    seen_ref = 0
    for ep in dataset:
        for g in ep["gold"]:
            for c, ids in zip(g["candidates"], g["cand_ids"]):
                base = [
                    vocab.get(w, unk) for w in (bc_data.tokenize(c) or [bc_data.UNK])
                ]
                assert ids[: len(base)] == base, "prefix law violated"
                if len(ids) > len(base):  # grounded span: ref + referent rows
                    seen_ref += 1
                    assert ids[len(base)] == ref
                    assert ref not in ids[len(base) + 1 :], "one ref separator"
    assert seen_ref >= 100, "grounding should light most gold candidates"


# ---------------------------------------------------------------- grounding
def test_handle_grounding_coverage(episodes):
    """Pinned measurements (this file, deterministic replay; v4 regen
    2026-10-07 after FoR/spellgorger un-reclassification): of the 189
    handle-shaped gold candidates, 157 resolve through world.cards;
    66/69 choose-digit candidates recover (was 59/62 pre-v4)."""
    rows_g = [r for e in episodes for r in e["asks"] if r["gold"]]

    def grounded(r, ci):
        g = r.get("ground") or []
        return ci < len(g) and bool(g[ci])

    hs, hs_ok = 0, 0
    ch, ch_ok = 0, 0
    for r in rows_g:
        for ci, c in enumerate(r["candidates"]):
            if v2._handle_of(c) is not None:
                hs += 1
                hs_ok += grounded(r, ci)
            elif c.isdigit() and r["what"].startswith("choose:"):
                ch += 1
                ch_ok += grounded(r, ci)
    assert (hs_ok, hs) == (157, 189), "handle grounding drifted"  # v3 regen 2026-10-07
    assert (ch_ok, ch) == (66, 69), (
        "choose-digit grounding drifted"
    )  # v3 regen 2026-10-07
    assert (
        sum(1 for r in rows_g if any(g for g in (r.get("ground") or []))) == 78
    )  # v3 regen 2026-10-07


def test_content_candidates_stay_bare(episodes):
    """PASS / top / bottom / name-words are their own referent: grounding
    must not invent rows for them."""
    for e in episodes:
        for r in e["asks"]:
            if not r["gold"]:
                continue
            g = r.get("ground") or []
            for ci, c in enumerate(r["candidates"]):
                if c == "PASS" and ci < len(g):
                    assert g[ci] == []


def test_handle_of():
    assert v2._handle_of("card:17") == Handle("card", 17)
    assert v2._handle_of("card:x") is None
    assert v2._handle_of("nocolon") is None
    assert v2._handle_of(":3") is None


# -------------------------------------------------------------- effect words
class Verb(Enum):
    DEATHTOUCH = 1
    LIFELINK = 2


@dataclasses.dataclass
class Atom:
    verb: Verb
    args: tuple = ()


@dataclasses.dataclass
class Set:
    effects: tuple


def test_effect_words_deterministic_dedup_and_cap():
    # mirrors the real option-set bag: a SET wrapping two compiled atoms
    a = Set(
        (
            Atom(Verb.DEATHTOUCH, ("x", Verb.LIFELINK)),
            Atom(Verb.DEATHTOUCH),
        )
    )
    w1, w2 = v2.effect_words(a), v2.effect_words(a)
    assert w1 == w2
    assert w1.count("set") == 1 and w1.count("atom") == 1  # dedup across atoms
    assert "deathtouch" in w1 and "lifelink" in w1
    assert all(w == w.lower() for w in w1)
    assert len(v2.effect_words(a, cap=2)) <= 2


# ------------------------------------------------------------------- stash
class _Opt:
    def __init__(self, idxs, choose):
        self.option_idxs = idxs
        self.choose = choose


def test_stash_wrappers_are_pure_memos(monkeypatch):
    """install -> both lanes memo their pool and return the ORIGINAL object;
    uninstall -> module attributes byte-restored; install is idempotent."""
    v2.uninstall_choose_stash()
    try:
        handles = ((Handle("card", 1),), (Handle("card", 2),))
        # real Choose nodes: ONE option table, each option-set indexes it
        choose = _FakeChoose([Atom(Verb.DEATHTOUCH), Atom(Verb.LIFELINK)])
        opts = [_Opt((0,), choose), _Opt((1,), choose)]
        monkeypatch.setattr(v2, "_ORIG_VCO", lambda ex, at, **k: handles)
        monkeypatch.setattr(v2, "_ORIG_CO_QUERY", lambda ex, ch, **k: opts)
        v2.install_choose_stash()
        assert query_mod.verb_choose_options is v2._stashing_vco
        v2.install_choose_stash()  # idempotent

        assert v2._stashing_vco(None, None) is handles
        atom_key = site_digest(tuple(handles))
        entry = v2.stash_rows_for(f"choose:src:{atom_key}")
        assert entry is not None
        pool, expand = entry
        assert expand and pool == [["card:1"], ["card:2"]]

        assert v2._stashing_choose_options(None, None) is opts
        node_key = site_digest(tuple(o.option_idxs for o in opts))
        entry = v2.stash_rows_for(f"choose:src:{node_key}")
        assert entry is not None
        pool, expand = entry
        assert not expand and pool[0][:2] == ["set", "atom"]
        assert "deathtouch" in pool[0] and "lifelink" not in pool[0]
    finally:
        v2.uninstall_choose_stash()
    assert query_mod.verb_choose_options is v2._ORIG_VCO
    assert v2._executor_pkg.choose_options is v2._ORIG_CO_EXEC


class _FakeChoose:
    def __init__(self, options):
        self.options = options


def test_stash_rows_for_rejects_non_digests():
    assert v2.stash_rows_for("target:creature") is None
    assert v2.stash_rows_for("choose:x:not_hex_00000") is None


def test_seq_stats_over_limit(tmp_path):
    """Owner law 2026-10-06: truncation must be measurable, never silent."""
    from tools.training.train_bc_v2 import _seq_stats

    ds = [{"seq": list(range(50))}, {"seq": list(range(60))}]
    st = _seq_stats(ds, max_len=1024)
    assert st["over_limit"] == 0 and st["max"] == 60
    assert st["cap_headroom"] == 1024 - 60 and st["min"] == 50
    over = ds + [{"seq": list(range(1100))}, {"seq": list(range(2000))}]
    st2 = _seq_stats(over, max_len=1024)
    assert st2["over_limit"] == 2 and st2["max"] == 2000
    assert st2["cap_headroom"] == 1024 - 2000  # negative = over the cap
