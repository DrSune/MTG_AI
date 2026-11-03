"""Unit tests for the RL v2 offline trainer core (train_rl_v2).

Covers the spec's exit-criteria tests:
  (a) bit-identity of the v2 policy vs the standalone anchor on sampled
      asks — cuda AND cpu (the load-bearing invariant);
  (b) GAE closed-form checks on synthetic sequences (lambda=1 limit,
      terminal-0 property, recursion);
  (c) warm-start EV > 0 on a 1000g sample (the measured number is
      printed);
  (d) PPO update on a 50-game batch: KL > 0, no NaNs, loss decreases
      across epochs;
  (e) padded batch == unpadded single sample (policy logp + value,
      1e-6; padding invisible to gradients);
  (f) logging keys present + cumulative KL monotone.

The heavy tests use the pilot anchor
(/home/sune/Desktop/MTG_AI/tools/training/bsh_S3a_s1_best.pt) and the
recorded pilot episodes (/tmp/opencode/rld_n1/episodes_iter1.jsonl) —
both are read-only inputs; skip if absent. GPU memory stays modest
(10-15 MB models on cuda, minibatch <= 256).
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest
import torch

from tools.training import train_rl_v2 as T
from tools.training.ab_duel import BcAsk
from tools.training.bc_model import PointerBC
from tools.training.collector import AskContext

EPISODES = Path("/tmp/opencode/rld_n1/episodes_iter1.jsonl")
ANCHOR = Path("/home/sune/Desktop/MTG_AI/tools/training/bsh_S3a_s1_best.pt")
HAS_CUDA = torch.cuda.is_available()
HAS_SAFE_CUDA = HAS_CUDA and (T.get_available_memory_gib() >= 30.0)

needs_inputs = pytest.mark.skipif(
    not (EPISODES.is_file() and ANCHOR.is_file()),
    reason="pilot episodes/anchor not present",
)
needs_cuda = pytest.mark.skipif(not HAS_CUDA, reason="no cuda")
needs_safe_cuda = pytest.mark.skipif(
    not HAS_SAFE_CUDA,
    reason="insufficient unified memory headroom on DGX Spark (>=30 GiB needed while vLLM is resident)",
)

DEVICE = "cuda" if HAS_SAFE_CUDA else "cpu"


# --------------------------------------------------------------- fixtures
def read_games(n: int) -> list[dict]:
    """Stream the first n rl_episode rows (never read the 375 MB whole)."""
    out = []
    with open(EPISODES, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "rl_episode":
                out.append(row)
                if len(out) >= n:
                    break
    return out


@pytest.fixture(scope="module")
def blob():
    return T.load_blob(ANCHOR)


@pytest.fixture(scope="module")
def games200():
    return read_games(200)


@pytest.fixture(scope="module")
def games300():
    return read_games(300)


def build_small(seed: int = 0, device: str = "cpu") -> T.PointerBCValue:
    """A small PointerBCValue for synthetic-batch tests (no anchor)."""
    torch.manual_seed(seed)
    model = T.PointerBCValue(
        vocab_size=128,
        d=32,
        layers=2,
        heads=2,
        ff=64,
        dropout=0.0,
        max_len=64,
        grad_checkpoint=False,
    )
    model.to(device)
    model.eval()
    for p in model.parameters():
        p.requires_grad_(True)
    return model


def fake_record(seed: int, t: int, menu: list[str], idx: int) -> dict:
    """A synthetic 1-row decision record with the encode_episode schema."""
    rng = random.Random(seed)
    tokens = torch.tensor([rng.randrange(1, 127) for _ in range(t)], dtype=torch.long)
    cand = torch.zeros(len(menu), 2, dtype=torch.long)
    for i, m in enumerate(menu):
        cand[i, 0] = 1 + rng.randrange(120)
        cand[i, 1] = 1 + rng.randrange(120)
    return {
        "tokens": tokens,
        "sep": t - 1,
        "cand_ids": cand,
        "cand_mask": torch.ones(len(menu), 2, dtype=torch.bool),
        "is_pass": torch.tensor([m == "PASS" for m in menu], dtype=torch.bool),
        "idx": idx,
        "logp_recorded": -0.5,
        "reward": 1.0,
        "outcome": "win",
        "state_feats": torch.tensor(
            [0.1 * i for i in range(T.STATE_FEAT_DIM)], dtype=torch.float32
        ),
    }


# ----------------------------------------------------------- (b) GAE / EV
def test_gae_lambda1_limit():
    """lambda=1, gamma=1: A_t == R - V_t (the telescoping identity)."""
    rng = random.Random(3)
    Tn = 25
    vals = [rng.uniform(-0.9, 0.9) for _ in range(Tn)]
    R = 1.0
    rewards = [0.0] * (Tn - 1) + [R]
    advs = T.compute_gae(rewards, vals, gamma=1.0, lam=1.0)
    for t in range(Tn):
        assert abs(advs[t] - (R - vals[t])) < 1e-12


def test_gae_terminal_zero_recursion():
    """With V=0 the advantage must be the damped future reward sum —
    the terminal-0 property — and the recursion must match the direct
    double sum on a random sequence."""
    rng = random.Random(7)
    Tn = 30
    vals = [rng.uniform(-1.0, 1.0) for _ in range(Tn)]
    rewards = [0.0] * (Tn - 1) + [1.0]
    lam = 0.95
    advs = T.compute_gae(rewards, vals, gamma=1.0, lam=lam)
    # direct evaluation of A_t = sum_{k>=t} lam^(k-t) * (r_k + V_{k+1} - V_k)
    for t in range(Tn):
        s = 0.0
        for k in range(t, Tn):
            v_next = 0.0 if k == Tn - 1 else vals[k + 1]
            s += lam ** (k - t) * (rewards[k] + v_next - vals[k])
        assert abs(advs[t] - s) < 1e-9
    # V=0 specialisation: A_t == lam**(T-1-t) * R
    advs0 = T.compute_gae(rewards, [0.0] * Tn, gamma=1.0, lam=lam)
    for t in range(Tn):
        assert abs(advs0[t] - lam ** (Tn - 1 - t)) < 1e-12


def test_gae_edges():
    # single decision: A = R - V
    assert abs(T.compute_gae([1.0], [0.3], 1.0, 0.95)[0] - 0.7) < 1e-12
    # all-zero value, terminal reward only: A_last == R exactly
    a = T.compute_gae([0.0, 0.0, -1.0], [0.0, 0.0, 0.0], 1.0, 0.5)
    assert abs(a[2] - (-1.0)) < 1e-12
    assert abs(a[1] - (-0.5)) < 1e-12
    assert abs(a[0] - (-0.25)) < 1e-12


def test_gae_per_game_placement():
    """The game outcome reward sits at the TERMINAL decision only."""
    dec = [
        {"reward": 1.0},
        {"reward": 1.0},
        {"reward": 1.0},
        {"reward": -1.0},
        {"reward": -1.0},
    ]
    advs = T.gae_advantages(dec, [0, 3], [0.0] * 5, lam=1.0)
    # game 1: A_t = 1 - V_t = 1; game 2: A_t = -1 - V_t = -1
    assert all(abs(x - 1.0) < 1e-12 for x in advs[:3])
    assert all(abs(x + 1.0) < 1e-12 for x in advs[3:])


def test_explained_variance():
    # perfect prediction -> 1
    assert T.explained_variance(
        [1.0, -1.0, 1.0, -1.0], [1.0, -1.0, 1.0, -1.0]
    ) == pytest.approx(1.0)
    # constant predictor (the baseline) -> 0
    assert T.explained_variance(
        [1.0, -1.0, 1.0, -1.0], [0.0, 0.0, 0.0, 0.0]
    ) == pytest.approx(0.0)
    # worse than the baseline -> negative
    assert T.explained_variance([1.0, -1.0], [-1.0, 1.0]) < 0.0
    # zero-variance targets: nothing to explain -> 0
    assert T.explained_variance([1.0, 1.0], [0.5, 0.5]) == 0.0
    with pytest.raises(ValueError):
        T.explained_variance([1.0], [0.0, 0.0])


def test_reward_semantics():
    """v1 outcome semantics: win +1 / loss -1 / draw 0; crash counts as
    a loss (rig convention carried from v1 /134 N1)."""
    assert T.REWARD == {"win": 1.0, "loss": -1.0, "draw": 0.0, "crash": -1.0}


# ------------------------------------------------- (e) padded batch == 1-row
@pytest.mark.parametrize("device", ("cuda" if HAS_SAFE_CUDA else "cpu", "cpu"))
def test_padded_batch_matches_single(device):
    model = build_small(device=device)
    r1 = fake_record(1, 10, ["PASS", "card:1", "card:2"], 1)
    r2 = fake_record(
        2, 22, ["PASS", "card:3", "card:4", "card:5", "card:6", "card:7"], 3
    )
    dev = torch.device(device)

    with torch.no_grad():
        b1, _ = T.collate_decisions([r1], dev)
        logits1, v1 = model.forward_with_value(
            b1["tokens"],
            b1["pad_mask"],
            b1["gold_batch"],
            b1["gold_pos"],
            b1["cand_ids"],
            b1["cand_mask"],
            b1["is_pass"],
            b1["state_feats"],
        )
        lp1 = torch.log_softmax(logits1.float(), dim=-1)[0, r1["idx"]]

    # the same decision inside a padded batch (different T and menu size)
    with torch.no_grad():
        b2, _ = T.collate_decisions([r1, r2], dev)
        logits2, v2 = model.forward_with_value(
            b2["tokens"],
            b2["pad_mask"],
            b2["gold_batch"],
            b2["gold_pos"],
            b2["cand_ids"],
            b2["cand_mask"],
            b2["is_pass"],
            b2["state_feats"],
        )
        lp2 = torch.log_softmax(logits2.float(), dim=-1)[0, r1["idx"]]

    assert torch.allclose(lp1, lp2, atol=1e-6, rtol=1e-6)
    assert torch.allclose(v1, v2[:1], atol=1e-6, rtol=1e-6)

    # padding is invisible to gradients: the row-1-only gradient in the
    # batch must equal the single-row gradient
    model.zero_grad(set_to_none=True)
    model.zero_grad(set_to_none=True)
    b1, _ = T.collate_decisions([r1], dev)
    _, v_s = model.forward_with_value(
        b1["tokens"],
        b1["pad_mask"],
        b1["gold_batch"],
        b1["gold_pos"],
        b1["cand_ids"],
        b1["cand_mask"],
        b1["is_pass"],
        b1["state_feats"],
    )
    g_s = torch.autograd.grad(v_s[0], model.value_head.weight, retain_graph=False)[0]
    model.zero_grad(set_to_none=True)
    b2, _ = T.collate_decisions([r1, r2], dev)
    _, v_b = model.forward_with_value(
        b2["tokens"],
        b2["pad_mask"],
        b2["gold_batch"],
        b2["gold_pos"],
        b2["cand_ids"],
        b2["cand_mask"],
        b2["is_pass"],
        b2["state_feats"],
    )
    g_b = torch.autograd.grad(v_b[0], model.value_head.weight)[0]
    assert torch.allclose(g_s, g_b, atol=1e-5, rtol=1e-5)


def test_padded_batch_masked_slots_zero_gradient():
    """Masked candidate slots (menu padding) carry zero gradient."""
    model = build_small(device="cpu")
    r1 = fake_record(1, 10, ["PASS", "card:1"], 1)
    r2 = fake_record(2, 12, ["PASS"], 0)
    dev = torch.device("cpu")
    b, _ = T.collate_decisions([r1, r2], dev)
    logits, _ = model.forward_with_value(
        b["tokens"],
        b["pad_mask"],
        b["gold_batch"],
        b["gold_pos"],
        b["cand_ids"],
        b["cand_mask"],
        b["is_pass"],
        b["state_feats"],
    )
    logits = logits.float()
    lp = torch.log_softmax(logits, dim=-1)
    loss = lp[1, 0]  # row 2's single real candidate
    loss.backward()
    # b_pass drives row 2's PASS score; its gradient is finite
    assert torch.isfinite(model.b_pass.grad).all()
    # the padded menu slot of row 2 (column 1) contributed nothing: its
    # logit was -finfo.min, so the loss is independent of row-2 cand-1
    # content — verify by perturbing that slot's tokens and re-running
    b2, _ = T.collate_decisions([r1, r2], dev)
    b2["cand_ids"][1, 1, 0] = 55  # padding slot token (cand_mask False)
    logits2, _ = model.forward_with_value(
        b2["tokens"],
        b2["pad_mask"],
        b2["gold_batch"],
        b2["gold_pos"],
        b2["cand_ids"],
        b2["cand_mask"],
        b2["is_pass"],
        b2["state_feats"],
    )
    lp2 = torch.log_softmax(logits2.float(), dim=-1)
    assert torch.allclose(lp[1, 0].detach(), lp2[1, 0], atol=1e-6, rtol=1e-6)


# ----------------------------------------------- (a) bit-identity, anchor
@needs_inputs
@pytest.mark.parametrize("device", ("cuda" if HAS_SAFE_CUDA else "cpu", "cpu"))
def test_bit_identity_wrapper_vs_anchor(blob, device):
    """The v2 wrapper's policy output is BIT-IDENTICAL to the standalone
    anchor on the same asks (cuda and cpu) — the load-bearing invariant.
    The wrapper adds no ops to the policy path, so this must hold
    exactly, not allclose."""
    schema = str(blob.get("schema", "v1"))
    anchor = PointerBC(**blob["config"])
    anchor.load_state_dict(blob["state"])
    anchor.to(device)
    anchor.eval()
    for p in anchor.parameters():
        p.requires_grad_(False)
    wrapper = T.PointerBCValue(**blob["config"])
    wrapper.load_state_dict(blob["state"], strict=False)
    wrapper.to(device)
    wrapper.eval()
    for p in wrapper.parameters():
        p.requires_grad_(False)
    # the value head is the ONLY new parameter set
    extra = set(wrapper.state_dict()) - set(anchor.state_dict())
    assert extra == {"value_head.weight", "value_head.bias"}

    games = read_games(1)
    ep = games[0]
    a1 = BcAsk(anchor, blob["vocab"], anchor.max_len, schema)
    a2 = BcAsk(wrapper, blob["vocab"], wrapper.max_len, schema)
    dev = torch.device(device)
    with torch.no_grad():
        for ai, a in enumerate(ep["asks"]):
            ctx1 = AskContext(
                vocab=a["what"], candidates=tuple(a["vocab"]), world=a["obs"]
            )
            ctx2 = AskContext(
                vocab=a["what"], candidates=tuple(a["vocab"]), world=a["obs"]
            )
            T.reenter_stash(a)
            with T.numlane_scope(blob["vocab"]):
                l1 = a1._forward_menu(torch, ctx1)
            T.reenter_stash(a)
            with T.numlane_scope(blob["vocab"]):
                l2 = a2._forward_menu(torch, ctx2)
            assert torch.equal(l1, l2), (
                f"ask #{ai} {a['what']!r} ({device}): wrapper != anchor "
                f"(max diff {float((l1 - l2).abs().max())})"
            )
    # perturbing the value head must not move the policy
    wrapper.value_head.weight.data.add_(1.0)
    a3 = BcAsk(wrapper, blob["vocab"], wrapper.max_len, schema)
    a4 = BcAsk(anchor, blob["vocab"], anchor.max_len, schema)
    a = ep["asks"][3]
    with torch.no_grad():
        ctx3 = AskContext(vocab=a["what"], candidates=tuple(a["vocab"]), world=a["obs"])
        ctx4 = AskContext(vocab=a["what"], candidates=tuple(a["vocab"]), world=a["obs"])
        T.reenter_stash(a)
        with T.numlane_scope(blob["vocab"]):
            l3 = a3._forward_menu(torch, ctx3)
        T.reenter_stash(a)
        with T.numlane_scope(blob["vocab"]):
            l4 = a4._forward_menu(torch, ctx4)
    assert torch.equal(l3, l4)
    # value head is a live, new, scalar output
    with torch.no_grad():
        ctx = AskContext(
            vocab=ep["asks"][3]["what"],
            candidates=tuple(ep["asks"][3]["vocab"]),
            world=ep["asks"][3]["obs"],
        )
        T.reenter_stash(ep["asks"][3])
        with T.numlane_scope(blob["vocab"]):
            t = a3.prepare_ask(torch, ctx)
        sf = torch.tensor(T.state_feats_from_obs(ep["asks"][3]["obs"])).to(dev)
        sf = sf.reshape(1, -1)
        _, v = wrapper.forward_with_value(
            t["tokens"].to(dev),
            t["pad_mask"].to(dev),
            t["gold_batch"].to(dev),
            t["gold_pos"].to(dev),
            t["cand_ids"].to(dev),
            t["cand_mask"].to(dev),
            t["is_pass"].to(dev),
            sf,
        )
    assert v.shape == (1,)


# ------------------------------------------------------- (c) warm-start EV
@needs_inputs
@needs_safe_cuda
def test_warm_start_ev_positive(blob, games300):
    """Warm-start the value head on 200 recorded games; the HELD-OUT
    explained variance on the next 100 games must be > 0 (triage rule
    #1). Prints the measured number."""
    policy = T.load_policy(blob, "cuda", train=True)
    anchor = T.build_anchor(T.load_blob(ANCHOR), "cuda")
    schema = str(blob.get("schema", "v1"))
    warm = T.warm_start_value(
        policy,
        games300[:200],
        blob["vocab"],
        1024,
        schema,
        "cuda",
        lr=1e-3,
        minibatch=256,
        epochs=3,
        seed=11,
    )
    ev = T.measure_value_ev(
        policy,
        games300[200:300],
        blob["vocab"],
        1024,
        schema,
        "cuda",
        minibatch=256,
    )
    print(
        f"\nwarm-start: games={warm['games']} decisions={warm['decisions']} "
        f"ev_train={warm['ev_train']:.4f} holdout_EV={ev:.4f}"
    )
    assert ev > 0.0, (
        f"triage rule #1 broken: holdout EV {ev:.4f} <= 0 — the value "
        "head explains nothing; fix before any policy tuning"
    )
    # the warm-start must NOT have moved the policy off the anchor
    # (policy params frozen during the warm phase)
    a1 = BcAsk(policy, blob["vocab"], 1024, schema)
    a2 = BcAsk(anchor, blob["vocab"], 1024, schema)
    a = games300[0]["asks"][0]
    with torch.no_grad():
        c1 = AskContext(vocab=a["what"], candidates=tuple(a["vocab"]), world=a["obs"])
        c2 = AskContext(vocab=a["what"], candidates=tuple(a["vocab"]), world=a["obs"])
        T.reenter_stash(a)
        with T.numlane_scope(blob["vocab"]):
            l1 = a1._forward_menu(torch, c1)
        T.reenter_stash(a)
        with T.numlane_scope(blob["vocab"]):
            l2 = a2._forward_menu(torch, c2)
    assert torch.equal(l1, l2)


# ------------------------------------------------------------ (d) PPO update
@needs_inputs
@needs_safe_cuda
def test_ppo_update_50_games(blob):
    """One PPO update over a 50-game batch: KL > 0, no NaNs, loss
    decreases across epochs, and the update actually moved the
    chosen-action logp."""
    games = read_games(50)
    policy = T.load_policy(blob, "cuda", train=True)
    anchor = T.build_anchor(T.load_blob(ANCHOR), "cuda")
    schema = str(blob.get("schema", "v1"))
    dec: list[dict] = []
    offsets: list[int] = []
    for ep in games:
        offsets.append(len(dec))
        dec.extend(T.encode_episode(ep, policy, blob["vocab"], 1024, schema))
    assert len(dec) > 2000, f"expected >2000 asks in 50 games, got {len(dec)}"
    u = T.ppo_update(
        policy,
        anchor,
        dec,
        offsets,
        epochs=3,
        minibatch=256,
        lr=3e-4,
        value_lr=1e-3,
        ratio_clip=0.2,
        kl_stop=T.DEFAULT_KL_STOP,
        grad_clip=5.0,
        value_coef=0.5,
        gae_lambda=0.95,
        seed=21,
        device="cuda",
    )
    print(
        f"\nppo50: kl={u['kl_per_update']:.4g} dlogp_post="
        f"{u['chosen_dlogp_post']:.4g} ent={u['entropy_mean']:.4g} "
        f"ev={u['value_explained_variance']:.4g} "
        f"losses={u['epoch_losses']} grad="
        f"{[round(x, 3) for x in u['raw_grad_norms']]} "
        f"early_stop={u['early_stopped']}"
    )
    # no NaNs anywhere
    for k, v in u.items():
        if k == "raw_grad_norms":
            assert all(math.isfinite(x) for x in v), "NaN in grad norms"
        elif isinstance(v, float):
            assert math.isfinite(v), f"NaN in {k}"
    assert u["kl_per_update"] > 0.0, "KL vs anchor is 0 — the update is a no-op"
    assert u["chosen_dlogp_post"] > 0.0, "policy did not move at all"
    assert u["advantage_std"] > 0.0
    assert 0.0 <= u["entropy_mean"] < 5.0
    # loss decreases across epochs
    assert len(u["epoch_losses"]) >= 2
    assert u["epoch_losses"][-1] < u["epoch_losses"][0], (
        f"loss did not decrease across epochs: {u['epoch_losses']}"
    )
    # the policy moved off the anchor but the value head saw the batch
    assert u["value_explained_variance"] < 1.0


# ---------------------------------------------- (d2) PPO update: synthetic
def test_ppo_update_synthetic_cpu_chunked():
    """CPU regression for the anchor-cache chunking bug: with different
    menu sizes per row, each collate chunk gets a different C_max, so the
    per-chunk anchor-logp tensors cannot be concatenated into one
    (torch.cat size mismatch — the fault that killed the first offline
    run). Random small models, fake records, minibatch=4 over 9 decisions
    => chunks of widths 6/10/11. No anchor blob needed, runs everywhere."""
    torch.manual_seed(0)
    anchor = PointerBC(
        vocab_size=128,
        d=32,
        layers=2,
        heads=2,
        ff=64,
        dropout=0.0,
        max_len=64,
        grad_checkpoint=False,
    )
    policy = T.PointerBCValue(
        vocab_size=128,
        d=32,
        layers=2,
        heads=2,
        ff=64,
        dropout=0.0,
        max_len=64,
        grad_checkpoint=False,
    )
    policy.load_state_dict(anchor.state_dict(), strict=False)
    anchor.eval()
    policy.train()

    # 9 decisions, menu sizes 3..11 (varying per chunk), one per "game"
    dec: list[dict] = []
    offsets: list[int] = []
    for i in range(9):
        menu = ["PASS"] + [f"card:{k}" for k in range(2 + i)]
        offsets.append(len(dec))
        dec.append(fake_record(i, 8 + 2 * (i % 3), menu, i % len(menu)))
    u = T.ppo_update(
        policy,
        anchor,
        dec,
        offsets,
        epochs=2,
        minibatch=4,
        lr=3e-4,
        value_lr=1e-3,
        ratio_clip=0.2,
        kl_stop=T.DEFAULT_KL_STOP,
        grad_clip=5.0,
        value_coef=0.5,
        gae_lambda=0.95,
        seed=21,
        device="cpu",
    )
    for k, v in u.items():
        if k == "raw_grad_norms":
            assert all(math.isfinite(x) for x in v), "NaN in grad norms"
        elif isinstance(v, float):
            assert math.isfinite(v), f"NaN in {k}"
    assert u["kl_per_update"] > 0.0, "KL vs anchor is 0 — the update is a no-op"
    assert u["chosen_dlogp_post"] > 0.0, "policy did not move at all"


# ------------------------------------------------------- (f) logging keys
LOG_KEYS = (
    "iter",
    "games",
    "wins",
    "losses",
    "draws",
    "crashes",
    "asks",
    "policy_loss",
    "value_loss",
    "value_explained_variance",
    "advantage_mean",
    "advantage_std",
    "entropy_mean",
    "kl_per_update",
    "kl_cumulative",
    "grad_norm_preclip",
)


@needs_inputs
@needs_safe_cuda
def test_logging_keys_and_cumulative_kl(blob, tmp_path, capsys):
    """Two iterations through train(): every spec-6 key present on each
    JSON line; cumulative KL monotone non-decreasing and >= 0."""
    diag = T.train(
        EPISODES,
        str(ANCHOR),
        device="cuda",
        tag="rlv2_testlog",
        out_dir=tmp_path,
        games=20,
        iterations=2,
        epochs=2,
        minibatch=256,
        warm_start_games=30,
        ev_games=20,
        seed=5,
        save=True,
    )
    lines = [
        json.loads(l)
        for l in (tmp_path / "rlv2_testlog_updates.jsonl").read_text().splitlines()
    ]
    assert len(lines) == 2
    for line in lines:
        for k in LOG_KEYS:
            assert k in line, f"missing log key {k}"
    c0, c1 = lines[0]["kl_cumulative"], lines[1]["kl_cumulative"]
    assert c0 >= 0.0 and c1 >= c0, f"cumulative KL not monotone: {c0}, {c1}"
    assert lines[1]["kl_cumulative"] == pytest.approx(diag["kl_cumulative_final"])
    # checkpoint saved with the value head
    ck = torch.load(
        tmp_path / "rlv2_testlog.pt", map_location="cpu", weights_only=False
    )
    assert "value_head.weight" in ck["state"]
    assert "train_info" in ck and ck["train_info"]["kind"] == "rl_v2"
    # the saved policy is NOT the anchor anymore (the update moved it)
    blob2 = T.load_blob(ANCHOR)
    anchor = T.PointerBC(**blob2["config"])
    anchor.load_state_dict(blob2["state"])
    moved = any(
        not torch.equal(
            ck["state"][k].float(),
            anchor.state_dict()[k].float(),
        )
        for k in anchor.state_dict()
    )
    assert moved, "checkpoint policy is still bit-identical to the anchor — "
    "the update did not land"
    # diag file written
    assert (tmp_path / "rlv2_testlog_diag.json").is_file()


# ---------------------------------------------------------- episode guard
def test_episode_guard_offline_bypass(tmp_path, capsys):
    """Offline mode bypasses the v1 SHA guard with a log line; on-policy
    mode enforces it (foreign checkpoint -> 0 episodes -> fail-loud)."""
    p = tmp_path / "eps.jsonl"
    row = {
        "kind": "rl_episode",
        "game_seed": 1,
        "swap": False,
        "seat": 0,
        "policy": "/nonexistent/coll.pt",
        "rng_seed": 2,
        "outcome": "win",
        "asks": [
            {
                "what": "act:main",
                "vocab": ["PASS", "card:1"],
                "idx": 1,
                "logp": -0.3,
                "obs": {"turn": 1, "lives": [20, 20]},
                "choose": None,
            }
        ],
    }
    p.write_text(json.dumps(row) + "\n")
    eps = T.load_episodes(p, "/nonexistent/policy.pt", offline=True)
    assert len(eps) == 1
    err = capsys.readouterr().err
    assert "BYPASSED" in err

    with pytest.raises(RuntimeError, match="0 episodes collected"):
        T.load_episodes(p, "/nonexistent/other.pt", offline=False)

    # on-policy with the MATCHING collecting checkpoint passes the guard
    row2 = dict(row, policy="/nonexistent/policy.pt")
    p2 = tmp_path / "eps2.jsonl"
    p2.write_text(json.dumps(row2) + "\n")
    eps2 = T.load_episodes(p2, "/nonexistent/policy.pt", offline=False)
    assert len(eps2) == 1


def test_episode_shape_drift_fails_loud(tmp_path):
    p = tmp_path / "bad.jsonl"
    row = {
        "kind": "rl_episode",
        "policy": "x",
        "outcome": "win",
        "asks": [
            {
                "what": "act:main",
                "vocab": ["PASS"],
                "idx": 5,
                "logp": 0.0,
                "obs": {},
                "choose": None,
            }
        ],
    }
    p.write_text(json.dumps(row) + "\n")
    with pytest.raises(RuntimeError, match="outside the"):
        T.load_episodes(p, "x", offline=True)
    row["asks"][0]["idx"] = 0
    row["outcome"] = "stall"
    p.write_text(json.dumps(row) + "\n")
    with pytest.raises(RuntimeError, match="unanchored"):
        T.load_episodes(p, "x", offline=True)


# -------------------------------------------------- (a) bit-identity, small
def test_bit_identity_small_synthetic():
    """Wrapper vs standalone on a synthetic model (no anchor needed):
    covers the cpu path even when the pilot anchor is absent."""
    torch.manual_seed(0)
    anchor = PointerBC(
        vocab_size=128,
        d=32,
        layers=2,
        heads=2,
        ff=64,
        dropout=0.0,
        max_len=64,
        grad_checkpoint=False,
    )
    wrapper = T.PointerBCValue(
        vocab_size=128,
        d=32,
        layers=2,
        heads=2,
        ff=64,
        dropout=0.0,
        max_len=64,
        grad_checkpoint=False,
    )
    wrapper.load_state_dict(anchor.state_dict(), strict=False)
    anchor.eval()
    wrapper.eval()
    for m in (anchor, wrapper):
        for p in m.parameters():
            p.requires_grad_(False)
    torch.manual_seed(1)
    for _ in range(4):
        t = torch.randint(1, 128, (1, 30))
        cand = torch.randint(1, 128, (1, 3, 2))
        mask = torch.ones(1, 3, 2, dtype=torch.bool)
        is_pass = torch.tensor([[True, False, False]])
        pad = torch.zeros_like(t, dtype=torch.bool)
        with torch.no_grad():
            la = anchor.forward(
                t,
                pad,
                torch.zeros(1, dtype=torch.long),
                torch.tensor([29]),
                cand,
                mask,
                is_pass,
            )
            lw, v = wrapper.forward_with_value(
                t,
                pad,
                torch.zeros(1, dtype=torch.long),
                torch.tensor([29]),
                cand,
                mask,
                is_pass,
                torch.zeros(1, T.STATE_FEAT_DIM),
            )
        assert torch.equal(la, lw)
        assert v.shape == (1,)
