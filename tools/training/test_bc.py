"""Batch-1 BC-floor gates: training-step pin, eval-determinism pin, pointer
permutation equivariance, recorder-vs-corpus join, tokenizer binding, and a
binomial-gate arithmetic check.

Cheap by design: CPU, micro models, artifacts already on disk
(``episodes.jsonl``). Only the recorder smoke touches the engine, and it
replays exactly three packs (one with duplicate identical asks) in ~2 s.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import torch

from tools.training import bc_data, bc_model, packrec, train_bc

REPO = Path(__file__).resolve().parents[2]
EPISODES = REPO / "tools" / "training" / "episodes.jsonl"
CORPUS = REPO / "tools" / "audit" / "puzzle_corpus.json"
SCEN = REPO / "tools" / "scenarios"

needs_episodes = pytest.mark.skipif(
    not EPISODES.exists(), reason="run `python -m tools.training.packrec` first"
)


def tiny_model(vocab_size: int) -> bc_model.PointerBC:
    """Micro PointerBC: CPU-fast, same math as the d=512/L=8 training model."""
    torch.manual_seed(0)
    return bc_model.PointerBC(
        vocab_size, d=64, layers=2, heads=4, ff=128, grad_checkpoint=False
    )


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def episodes() -> list[dict[str, Any]]:
    return bc_data.load_episodes(EPISODES)


@pytest.fixture(scope="module")
def vocab(episodes: list[dict[str, Any]]) -> dict[str, int]:
    return bc_data.build_vocab(episodes)


@pytest.fixture(scope="module")
def dataset(
    episodes: list[dict[str, Any]], vocab: dict[str, int]
) -> list[dict[str, Any]]:
    return bc_data.build_dataset(episodes, vocab)


@pytest.fixture(scope="module")
def small_dataset(dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [ep for ep in dataset if ep["gold"]][:4]
    assert out, "no gold episodes on disk"
    return out


# --------------------------------------------------------------- tokenizer
def test_tokenizer_specials_and_handle_split(vocab: dict[str, int]) -> None:
    for tok in ("<pad>", "<unk>", "<s>", "<ask>", "<sep>"):
        assert tok in vocab, tok
    assert bc_data.tokenize("card:17") == ["card", "17"]


@needs_episodes
def test_handle_candidates_bind_to_obs_stream(
    episodes: list[dict[str, Any]], vocab: dict[str, int]
) -> None:
    """Handle candidates ('card:17') must lexically bind to obs rows for the
    overwhelming majority of gold lines, and 100% for the l1-certified packs.
    Known schema gap: candidates referring to library/hand zones are not
    enumerated in obs (cultivate, see_the_truth, garruk_s_harbinger, waker)."""
    l1_packs = {
        "basri_ket_x_rin_and_seri_inseparable.json",
        "tolarian_kraken_tap.json",
        "tolarian_kraken_untap.json",
        "treasure_token_activation.json",
    }
    total = bound = 0
    l1_checked = l1_unbound = 0
    for ep in episodes:
        enc = bc_data.encode_episode(ep, vocab)
        seq_ids = set(enc["seq"])
        for row in ep["asks"]:
            if not row["gold"]:
                continue
            for cand in row["candidates"]:
                if not cand.startswith("card:"):
                    continue
                for w in bc_data.tokenize(cand):
                    hit = vocab[w] in seq_ids
                    total += 1
                    bound += hit
                    if ep["pack"] in l1_packs:
                        l1_checked += 1
                        l1_unbound += not hit
    assert l1_checked > 10 and l1_unbound == 0, "l1 candidates must fully bind"
    rate = bound / total
    assert rate >= 0.80, f"handle binding rate too low: {rate:.3f}"


# ---------------------------------------------------------- training pins
@needs_episodes
def test_training_step_lowers_loss(
    small_dataset: list[dict[str, Any]], vocab: dict[str, int]
) -> None:
    """Overfit-one-batch pin: a few AdamW steps on fixed data must crush CE."""
    device = torch.device("cpu")
    model = tiny_model(len(vocab))
    b = bc_model.collate(small_dataset, len(vocab), device)
    args = (
        b["tokens"],
        b["pad_mask"],
        b["gold_batch"],
        b["gold_pos"],
        b["cand_ids"],
        b["cand_mask"],
        b["is_pass"],
        b["gold_idx"],
    )
    opt = torch.optim.AdamW(model.parameters(), lr=5e-3)
    with torch.no_grad():
        start = float(model.loss(*args))
    last = start
    for _ in range(30):
        opt.zero_grad(set_to_none=True)
        last = model.loss(*args)
        last.backward()
        opt.step()
        last = float(last.detach())
    assert last < 0.5 * start, f"loss {start:.4f} -> {last:.4f} (no learning)"


@needs_episodes
def test_eval_determinism_checkpoint_roundtrip(
    small_dataset: list[dict[str, Any]], vocab: dict[str, int]
) -> None:
    """eval_rows is a pure function of (weights, episodes): identical twice,
    and identical after a state_dict save/load roundtrip."""
    device = torch.device("cpu")
    model = tiny_model(len(vocab))
    rows_a = train_bc.eval_rows(model, small_dataset, device)
    rows_b = train_bc.eval_rows(model, small_dataset, device)
    assert rows_a == rows_b
    clone = tiny_model(len(vocab))  # different random init
    clone.load_state_dict(model.state_dict())
    assert train_bc.eval_rows(clone, small_dataset, device) == rows_a


@needs_episodes
def test_pointer_permutation_equivariance(
    small_dataset: list[dict[str, Any]], vocab: dict[str, int]
) -> None:
    """Candidate-slot order must not change scores: shuffling the candidate
    axis permutes the logits by the same permutation (no positional peek)."""
    device = torch.device("cpu")
    model = tiny_model(len(vocab))
    model.eval()
    b = bc_model.collate(small_dataset[:1], len(vocab), device)
    c = b["cand_ids"].shape[1]
    assert c > 1, "need a multi-candidate episode"
    torch.manual_seed(7)
    perm = torch.randperm(c)
    with torch.no_grad():
        base = model.forward(
            b["tokens"],
            b["pad_mask"],
            b["gold_batch"],
            b["gold_pos"],
            b["cand_ids"],
            b["cand_mask"],
            b["is_pass"],
        )
        shuf = model.forward(
            b["tokens"],
            b["pad_mask"],
            b["gold_batch"],
            b["gold_pos"],
            b["cand_ids"].index_select(1, perm),
            b["cand_mask"].index_select(1, perm),
            b["is_pass"].index_select(1, perm),
        )
    assert torch.allclose(shuf, base.index_select(1, perm), atol=1e-5, rtol=1e-5)


# ---------------------------------------------------- recorder-vs-corpus join
@pytest.fixture(scope="module")
def supply() -> Any:
    from MTG_bot.core.executor.games import get_supply

    return get_supply("all")


@needs_episodes
def test_recorder_join_corpus_duplicate_asks(supply: Any) -> None:
    """Recorder replays gold lines and joins the cert 1:1 even for packs
    whose repeated identical asks collapse puzzle_cert's rec.index() ordinals
    (stormwing_entity, tolarian_kraken_tap): one row per corpus item."""
    packs = [
        "alchemists_gift.json",
        "stormwing_entity.json",
        "tolarian_kraken_tap.json",
    ]
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))["items"]
    items = [it for it in corpus if it["pack"] in packs]
    eps_all = [packrec.record_pack(SCEN / name, supply) for name in packs]
    assert all(ep is not None for ep in eps_all)
    eps = [ep for ep in eps_all if ep is not None]
    enc = bc_data.build_dataset(eps, bc_data.build_vocab(eps))
    joined = bc_data.join_corpus(enc, items)
    n_gold = sum(len(e["gold"]) for e in enc)
    assert joined == n_gold == len(items) >= 7
    counts = {e["pack"]: len(e["gold"]) for e in enc}
    assert counts["stormwing_entity.json"] == 2
    assert counts["tolarian_kraken_tap.json"] == 4


# --------------------------------------------------------------- gate math
def test_binomial_gate_math() -> None:
    sure = train_bc.binomial_stats(119, 119, 0.5)
    assert sure["binom_p_one_sided"] < 1e-30 and sure["beat_margin_se"] > 8
    coin = train_bc.binomial_stats(60, 119, 0.5)
    assert coin["binom_p_one_sided"] > 0.2 and abs(coin["beat_margin_se"]) < 1.5
    zero_floor = train_bc.binomial_stats(3, 4, 0.0)
    assert zero_floor["beat_margin_se"] > 0 and zero_floor["binom_p_one_sided"] <= 1.0
