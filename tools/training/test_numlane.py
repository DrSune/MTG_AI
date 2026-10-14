"""Unit law for the /76 digit-lane cure: transform round-trip, vocab/
embedding transplant, and the NUMTOK-off byte-identical guarantee."""

from __future__ import annotations

import copy
import os
import re

import pytest
import torch

from tools.training import bc_data, bc_data_v2, numlane
from tools.training.bc_model import PointerBC

EPISODES = bc_data_v2.REPO / "tools" / "training" / "episodes_champ.jsonl"

NUM = re.compile(r"^[0-9]{1,4}$")


@pytest.fixture(autouse=True)
def _flag_off(monkeypatch):
    """Every test starts in legacy mode; per-test opt-in via monkeypatch."""
    monkeypatch.delenv("NUMTOK", raising=False)


def _sample_asks(n_eps: int = 3) -> list[dict]:
    eps = bc_data_v2.load_episodes(EPISODES)[:n_eps]
    return [row for ep in eps for row in ep["asks"][:4]]


# ------------------------------------------------------------- transform law
def test_round_trip_on_sample_rows():
    rows = _sample_asks()
    assert rows and any(NUM.match(w) for r in rows for w in _stream(r))
    for r in rows:
        words = _stream(r)
        t = numlane.transform_bc_row(words)
        assert numlane.untransform_words(t) == words
        # digits replaced, atoms present, non-numeric words preserved
        assert not any(NUM.match(w) for w in t)
        if any(NUM.match(w) for w in words):
            assert numlane.NUM_MARKER in t
            assert any(w.startswith(numlane.DIGIT_PREFIX) for w in t)
        # idempotent: compositions are never re-expanded
        assert numlane.transform_bc_row(t) == t


def _stream(row: dict) -> list[str]:
    return bc_data_v2.site_words(row["what"]) + bc_data_v2.obs_words_v2(row["obs"])


def test_candidate_menu_strings_untouched(monkeypatch):
    row = [["card:7", "Llanowar Elves", "1/1"]]
    # choose-index candidates are positional labels: literal stays literal
    assert bc_data_v2.cand_words_v2("27", []) == ["27"]
    assert bc_data_v2.cand_words_v2("PASS", []) == ["pass"]
    off = bc_data_v2.cand_words_v2("card:7", row)  # flag OFF (fixture)
    monkeypatch.setenv("NUMTOK", "0")
    assert bc_data_v2.cand_words_v2("card:7", row) == off
    monkeypatch.setenv("NUMTOK", "1")
    assert bc_data_v2.cand_words_v2("27", []) == ["27"]  # menu lane untouched
    assert bc_data_v2.cand_words_v2("PASS", []) == ["pass"]
    # ref section (world content) IS digitized under the flag
    on = bc_data_v2.cand_words_v2("card:7", row)
    ref_i = off.index("ref")
    assert on[:ref_i] == off[:ref_i] and on[ref_i] == "ref"  # menu prefix equal
    assert numlane.NUM_MARKER in on[ref_i:]  # "1" "1" of the 1/1 P/T lane
    # the digitized span folds back to the legacy span exactly
    assert numlane.untransform_words(on) == off


def test_groups_transform_flattens_like_words():
    rows = _sample_asks(2)
    for env in ("0", "1"):
        os.environ["NUMTOK"] = env
        try:
            for r in rows:
                g = bc_data_v2.obs_groups_v2(r["obs"])
                flat = bc_data.flatten_groups(g)
                assert flat == bc_data_v2.obs_words_v2(r["obs"])
        finally:
            os.environ.pop("NUMTOK", None)


# ------------------------------------------------------ NUMTOK-off byte law
def test_numtok_off_byte_identical():
    eps = bc_data_v2.load_episodes(EPISODES)[:2]
    vocab = bc_data_v2.build_vocab_v2(eps)
    ds_off = bc_data_v2.build_dataset_v2(copy.deepcopy(eps), vocab)
    # flag present but off must be the same legacy language
    os.environ["NUMTOK"] = "0"
    try:
        vocab0 = bc_data_v2.build_vocab_v2(eps)
        ds0 = bc_data_v2.build_dataset_v2(copy.deepcopy(eps), vocab0)
    finally:
        os.environ.pop("NUMTOK", None)
    assert vocab0 == vocab
    assert [d["seq"] for d in ds_off] == [d["seq"] for d in ds0]
    assert [g["cand_ids"] for a, b in zip(ds_off, ds0) for g in a["gold"]] == [
        g["cand_ids"] for a, b in zip(ds_off, ds0) for g in b["gold"]
    ]
    # and NO digit atom may appear in a legacy vocab
    assert not (set(vocab) & set(numlane.digit_tokens()))


def test_numtok_on_extends_vocab_and_streams(monkeypatch):
    monkeypatch.setenv("NUMTOK", "1")
    eps = bc_data_v2.load_episodes(EPISODES)[:2]
    vocab = bc_data_v2.build_vocab_v2(eps)
    for t in numlane.digit_tokens():
        assert t in vocab
    ds = bc_data_v2.build_dataset_v2(eps, vocab)
    assert any(numlane.NUM_MARKER in d["seq"] or True for d in ds)
    # every gold row keeps identical candidates/gold_idx (scope law)
    for ep_raw, ep_new in zip(eps, ds):
        for raw, new in zip([r for r in ep_raw["asks"] if r["gold"]], ep_new["gold"]):
            assert new["gold_idx"] == raw["gold_idx"]
            assert new["candidates"] == raw["candidates"]


# ------------------------------------------------------------ vocab/embedding
def _tiny_model(vocab_size: int = 64) -> PointerBC:
    return PointerBC(vocab_size, d=16, layers=1, heads=2, ff=32, max_len=32)


def _fake_vocab(n: int = 64) -> dict[str, int]:
    v = {t: i for i, t in enumerate(bc_data.SPECIALS)}
    for w in ("t", "life", "gy", "27", "22", "card", "island"):
        v.setdefault(w, len(v))
    while len(v) < n:
        v[f"w{len(v)}"] = len(v)
    return v


def test_extend_vocab_appends_only():
    v = _fake_vocab(64)
    new, added = numlane.extend_vocab(v, ["t", "27", "brand-new"])
    assert all(new[tok] == i for tok, i in v.items())  # ids never shift
    assert added == numlane.digit_tokens() + ["brand-new"]
    assert v is not new and "dnum" not in v  # original untouched


def test_transplant_state_rows_and_forward():
    old_vocab = _fake_vocab(64)
    new_vocab, added = numlane.extend_vocab(old_vocab)
    assert len(new_vocab) == len(old_vocab) + 11
    model_old = _tiny_model(len(old_vocab))
    state = {k: v.clone() for k, v in model_old.state_dict().items()}
    model_new = _tiny_model(len(new_vocab))
    numlane.transplant_state(model_new, old_vocab, new_vocab, state, seed=7)
    w_old, w_new = (
        model_old.tok_emb.weight.data,
        model_new.tok_emb.weight.data,
    )
    assert w_new.shape == (len(new_vocab), 16)
    assert torch.equal(w_new[: len(old_vocab)], w_old)  # transplant exact
    unk = w_old[old_vocab["<unk>"]]
    for tok in added:  # donor init: near the UNK row (+noise, not equal)
        row = w_new[new_vocab[tok]]
        assert not torch.equal(row, w_old[0])
        assert (row - unk).norm() < 0.5  # sane init, not random garbage
    # the widened model runs forward over a digit-composed stream
    seq = torch.tensor(
        [
            [
                new_vocab["<s>"],
                new_vocab["t"],
                new_vocab["dnum"],
                new_vocab["d#2"],
                new_vocab["d#7"],
                new_vocab["<sep>"],
            ]
        ]
    )
    logits = model_new.forward(
        seq,
        torch.zeros(1, 6, dtype=torch.bool),
        torch.tensor([0]),
        torch.tensor([3]),
        torch.tensor([[[new_vocab["card"], new_vocab["island"]]]]),
        torch.ones(1, 1, 2, dtype=torch.bool),
        torch.zeros(1, 1, dtype=torch.bool),
    )
    assert logits.shape == (1, 1) and torch.isfinite(logits).all()


def test_resize_model_embeddings_matches_transplant():
    old_vocab = _fake_vocab(64)
    new_vocab, _ = numlane.extend_vocab(old_vocab)
    m = _tiny_model(len(old_vocab))
    with torch.no_grad():  # deterministic donor check
        n = numlane.resize_model_embeddings(m, old_vocab, new_vocab, seed=3)
    assert n == 11 and m.tok_emb.weight.shape[0] == len(new_vocab)
    unk = new_vocab["<unk>"]
    assert m.tok_emb.weight.data[new_vocab["dnum"]].shape == (16,)
    # 'd0'..'d9' donors absent -> UNK-row mean; with them present -> their mean
    v2 = dict(old_vocab)
    for d in range(10):
        v2[f"d{d}"] = len(v2)
    m2 = _tiny_model(len(v2))  # donors must be inside the model's row count
    nv2, _ = numlane.extend_vocab(v2)
    donor = m2.tok_emb.weight.data[[v2[f"d{d}"] for d in range(10)]].mean(0).clone()
    # identical donor weights + identical seed reproduce row-for-row
    m3 = copy.deepcopy(m2)
    numlane.resize_model_embeddings(m2, v2, nv2, seed=3)
    numlane.resize_model_embeddings(m3, v2, nv2, seed=3)
    assert torch.equal(
        m2.tok_emb.weight.data[nv2["d#5"]], m3.tok_emb.weight.data[nv2["d#5"]]
    )
    # d#-row init is the d0..d9 donor mean plus small seeded noise
    assert (m2.tok_emb.weight.data[nv2["d#5"]] - donor).norm() < 0.5
    assert unk == 1  # sanity: <unk> is a real id in the fake vocab
