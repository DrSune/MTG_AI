"""RL v2 trainer — PLAN_COMPONENT_TRAINING Step 4, "First make RL work"
(owner, 2026-10-29; KNOWLEDGE 2026-10-29/176).

OFFLINE CORE. Everything that runs on RECORDED episodes: value head, GAE
credit, PPO clipped update with the frozen-anchor KL early-stop, padded
decision batching, value-head warm-start. The ON-POLY collection loop (live
engine, G=50 fresh games per iteration) is OUT OF SCOPE here — tomorrow's
code calls the functions listed under "ON-POLY HOOKS" at the bottom.

Model (spec 1): policy = the anchor checkpoint bit-identically loaded
into :class:`PointerBCValue`; the value head is ONE new scalar linear layer
(``value_head: (d + STATE_FEAT_DIM) -> 1``) on the encoder step state — the
same ``h`` the pointer reads at the SEP position, CONCATENATED with 5 raw
state features (life diff / turn / board diff / hand size / turn
direction) read from the ask's obs. Measured 2026-11-02: the encoder's ``h``
alone carries ~no outcome signal (linear-probe holdout EV ~= 0) while the
raw features carry ~0.26 — the value head must see the state directly; the
policy path is untouched either way. ``forward()`` is inherited untouched,
so with the value head untrained the policy output is BIT-IDENTICAL to the
standalone anchor (load-bearing invariant, unit-tested on cuda AND cpu;
the wrapper adds no ops to the policy path, so there is no float
reordering to fix).

Credit (spec 2): per-decision advantage = GAE over the value head's
predictions, gamma=1, lambda=0.95, terminal value 0 at game end. Reward =
the game outcome placed at the TERMINAL decision only — v1's outcome
semantics exactly: win +1 / loss -1 / draw 0, and CRASH COUNTS AS A LOSS
(rig convention carried over from train_rl_v1 /134 N1: a crashed game is
unwinnable, never silently 0).

Update (spec 3): PPO clipped objective (ratio clip 0.2), Adam policy
lr=3e-4 (standard PPO scale; v1's SGD lr=1e-5 was forced by the F4
zero-variance no-op discriminator and is not comparable), Adam value
lr=1e-3, 3 epochs over each G-game batch in decision-minibatches of 256
(the spec's 64-256 forward band: 256 maximises GPU occupancy for the
7-layer encoder; memory stays in the ~10-15 GB band on the 128 GB machine
at T<=1024, fp32). EARLY-STOP the update when the running mean KL vs the
frozen anchor passes 0.01; gradient norm clip kept as a safety net — raw
norms measured on the 1000g pilot batch (p50 ~0.1-0.4, p99 ~2-3, max
< ~10), so the default clip 5.0 binds on well under 5% of minibatches.

Batching (spec 4): decisions are batched (256 default) per forward with
right-padded token rows (pad_mask) and vocab-menu padding
(cand_mask/is_pass). Unit-tested: a padded batch gives the same chosen
policy logp and value as the unpadded single sample (allclose 1e-6); the
masked slots carry zero gradient.

Warm-start (spec 5): before any policy update the value head is trained
supervised (predict the outcome reward from the obs at every decision —
with gamma=1 the per-decision return is exactly the game's outcome
reward, so warm-start and update share ONE target) on a sample of the
recorded episodes; the explained variance of its predictions vs the
constant-outcome baseline is reported on a HELD-OUT sample and MUST be
> 0 (triage rule #1: a value head that explains nothing is a bug to fix
before any policy tuning).

Episode guard (spec 7): the future ON-POLY mode enforces v1's guard
(--policy must be SHA-256-identical to the episodes' collecting
checkpoint); OFFLINE mode (the default — this trainer) bypasses it with a
loud stderr log line, since the recorded games were collected by the
anchor and the policy is warm-started from that same anchor.

Logging (spec 6): one JSON line per update (stdout + <tag>_updates.jsonl)
with policy_loss, value_loss, value_explained_variance, advantage mean/
std, entropy (per decision), KL per update and cumulative vs the frozen
anchor, gradient norm (pre-clip) and the games/wins/draws/crashes counts.

Checkpoint: <tag>.pt carries the FULL PointerBCValue state (policy +
value_head) — load it with :func:`load_policy` (or
``PointerBCValue.load_state_dict(..., strict=False)``); the policy head
keys are unchanged, only ``value_head.{weight,bias}`` are new.

ON-POLY HOOKS (tomorrow's collection loop calls these):
  * ``load_policy(blob, device, train=True) -> PointerBCValue`` — warm
    start from the anchor OR load a v2 checkpoint;
  * ``build_anchor(blob, device) -> PointerBC`` — the frozen KL anchor
    and opponent;
  * build decision records with ``BcAsk.prepare_ask`` (one fresh BcAsk
    per game, asks in order) into the SAME record schema
    ``encode_episode`` returns (keys: tokens, sep, cand_ids, cand_mask,
    is_pass, idx, logp_recorded, reward, outcome), grouped per game;
  * ``warm_start_value`` on the fresh games before the update;
  * ``ppo_update(policy, anchor, decisions, game_offsets, ...)`` — the
    update; ``compute_gae`` / ``explained_variance`` are the pure helpers.

Run::

    .venv/bin/python tools/training/train_rl_v2.py \
        --episodes /tmp/opencode/rld_n1/episodes_iter1.jsonl \
        --policy tools/training/bsh_S3a_s1_best.pt \
        --anchor tools/training/bsh_S3a_s1_best.pt \
        --device cuda --tag rlv2_off50 --games 50
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import random
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import torch
import torch.nn.functional as F
from torch import nn

from tools.training import bc_data_v2, numlane
from tools.training.ab_duel import BcAsk
from tools.training.bc_model import PointerBC
from tools.training.collector import AskContext

REWARD: dict[str, float] = {
    "win": 1.0,
    "loss": -1.0,
    "draw": 0.0,
    "crash": -1.0,  # v1 rig convention: a crash is a loss, never a 0
}
DEFAULT_KL_STOP = 0.01
DEFAULT_GRAD_CLIP = 5.0  # raw-norm p99 band on 1000g data, binds <5% of mbs
VALUE_KEYS = ("value_head.weight", "value_head.bias")

# Raw state features for the VALUE head input (learner perspective, from
# the ask's obs snapshot). Rationale (measured, _diag_valuehead2 2026-11-02):
# the BC encoder's SEP state h discards outcome information — a linear
# probe on h alone measures holdout EV ~= 0 (10 epochs, 200g train / 100g
# hold), while these raw features alone reach 0.26 (all decisions) /
# 0.50 (late game) on the same pilot episodes (700g/300g). The value head
# must see the state the way it actually is. Fixed normalization
# constants — deterministic, no fitting. The POLICY path is untouched
# (the bit-identity invariant holds: value_head is off that path).
STATE_FEAT_DIM = 5
_STATE_FEAT_SCALE = (20.0, 20.0, 5.0, 8.0)  # life_diff, turn, board, hand


def state_feats_from_obs(obs: dict[str, Any]) -> list[float]:
    """5 raw state features, learner perspective, scaled to ~[-1.6, 1.6]:
    [life_diff, turn, board_diff, hand_size, is_active]."""
    s = int(obs["seat"])
    lives = obs["lives"]
    bf = obs["battlefield"]
    hand = obs["hand"]
    hand_n = len(hand[s]) if isinstance(hand, (list, tuple)) else 0
    return [
        (float(lives[s]) - float(lives[1 - s])) / _STATE_FEAT_SCALE[0],
        float(obs["turn"]) / _STATE_FEAT_SCALE[1],
        (float(len(bf[s])) - float(len(bf[1 - s]))) / _STATE_FEAT_SCALE[2],
        float(hand_n) / _STATE_FEAT_SCALE[3],
        1.0 if int(obs["active"]) == s else -1.0,
    ]


_CKPT_KEY_CACHE: dict[str, str] = {}


def get_available_memory_gib() -> float:
    """Read available unified memory in GiB from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except Exception:
        pass
    return 0.0


def assert_cuda_headroom(required_gib: float = 25.0) -> None:
    """Refuse CUDA allocations if available unified memory is too low (e.g. vLLM resident)."""
    avail = get_available_memory_gib()
    if avail > 0 and avail < required_gib:
        raise RuntimeError(
            f"DGX Spark Unified Memory Safety Guard: Available memory is only {avail:.1f} GiB "
            f"(< {required_gib:.1f} GiB required for CUDA RL operations). "
            f"The vLLM engine (qwen-nvfp4) is resident and occupies ~73 GiB of unified memory. "
            f"Allocating CUDA tensors now would exhaust unified memory, causing NV_ERR_NO_MEMORY "
            f"and a hard machine freeze/reboot. "
            f"Either stop vLLM first ('docker stop qwen-nvfp4' / 'spark_ced.sh free-gpu docker:qwen-nvfp4') "
            f"or run on CPU with device='cpu'."
        )


def _ckpt_key(path_str: str) -> str:
    """Checkpoint identity: SHA-256 when present, resolved-path fallback
    (v1 governance: evidence-by-SHA, never by path). Cached."""
    if path_str not in _CKPT_KEY_CACHE:
        p = Path(path_str)
        if p.is_file():
            _CKPT_KEY_CACHE[path_str] = (
                "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
            )
        else:
            _CKPT_KEY_CACHE[path_str] = "path:" + str(p.resolve())
    return _CKPT_KEY_CACHE[path_str]


# ------------------------------------------------------------------ model
class PointerBCValue(PointerBC):
    """PointerBC + ONE new scalar value head.

    The value head reads the encoder SEP state ``h`` (the same ``h`` the
    pointer reads) CONCATENATED with the raw state features
    (:func:`state_feats_from_obs`, ``STATE_FEAT_DIM``-dim): the encoder's
    decision-tuned readout alone carries ~no outcome information (measured
    holdout EV ~= 0; see module note on STATE_FEAT_DIM), so the value head
    sees the state directly as well. The policy path (inherited
    ``forward``) is untouched: with the value head unused, outputs are
    bit-identical to the standalone anchor — the load-bearing invariant,
    unit-tested on cuda and cpu. New parameters ONLY:
    ``value_head.{weight,bias}``."""

    def __init__(self, **cfg: Any) -> None:
        super().__init__(**cfg)
        self.value_head = nn.Linear(self.d + STATE_FEAT_DIM, 1)

    def forward_with_value(
        self,
        tokens: torch.Tensor,
        pad_mask: torch.Tensor,
        gold_batch: torch.Tensor,
        gold_pos: torch.Tensor,
        cand_ids: torch.Tensor,
        cand_mask: torch.Tensor,
        is_pass: torch.Tensor,
        state_feats: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """One forward -> (pointer logits [G,Cmax], value [G]).
        ``state_feats`` is [G, STATE_FEAT_DIM] (the collated raw state
        features; value path ONLY — the policy logits never touch it)."""
        hidden = self.encode(tokens, pad_mask)
        h = hidden[gold_batch, gold_pos]
        cand_emb = self.candidate_emb(cand_ids, cand_mask)
        logits = self.pointer_logits(h, cand_emb, cand_mask.any(-1), is_pass)
        return logits, self.value_head(torch.cat([h, state_feats], dim=-1)).squeeze(-1)


def load_blob(ckpt: str | Path) -> dict[str, Any]:
    """torch.load the checkpoint (eval_ckpt.py pattern; the blob is a
    PointerBC family: config + state + vocab)."""
    blob = torch.load(Path(ckpt), map_location="cpu", weights_only=False)
    for key in ("config", "state", "vocab"):
        if key not in blob:
            raise RuntimeError(f"train_rl_v2: {ckpt} missing blob key {key!r}")
    return blob


def _value_param_ids(model: PointerBCValue) -> set[int]:
    return {id(p) for p in model.value_head.parameters()}


def load_policy(
    blob: dict[str, Any], device: str, train: bool = True
) -> PointerBCValue:
    """Build the v2 policy from a PointerBC-family blob. The anchor's
    policy weights are copied EXACTLY (load_state_dict's copy_ is a
    bit-wise float copy); the value head keys are new and keep their
    random init (or load from the blob when it is a v2-trainer
    checkpoint). Fail-loud if the blob's state keys do not cover the
    policy exactly — a silently missing policy key would break the
    bit-identity invariant."""
    model = PointerBCValue(**blob["config"])
    have = set(blob["state"].keys())
    need = set(model.state_dict().keys()) - set(VALUE_KEYS)
    missing = need - have
    if missing:
        raise RuntimeError(
            f"train_rl_v2: checkpoint state missing policy keys "
            f"{sorted(missing)} — bit-identity vs the anchor is void"
        )
    extra = have - need - set(VALUE_KEYS)
    if extra:
        raise RuntimeError(
            f"train_rl_v2: checkpoint state carries unexpected keys "
            f"{sorted(extra)} — checkpoint drift, refusing silent load"
        )
    model.load_state_dict(blob["state"], strict=False)
    if str(device).startswith("cuda"):
        assert_cuda_headroom(25.0)
    model.to(device)
    model.eval()  # v1 convention: the collected logp was computed in eval
    # mode (dropout=0.1 in cfg only bites in train mode), so every
    # recompute here runs in eval too.
    for p in model.parameters():
        p.requires_grad_(train)
    return model


def build_anchor(blob: dict[str, Any], device: str) -> PointerBC:
    """The FROZEN anchor: a plain PointerBC, bit-identical weights, never
    trained, eval mode — the KL reference and tomorrow's opponent."""
    model = PointerBC(**blob["config"])
    model.load_state_dict(blob["state"])
    if str(device).startswith("cuda"):
        assert_cuda_headroom(25.0)
    model.to(device)
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    return model


# -------------------------------------------------------------- episodes
def load_episodes(
    episodes: Path, policy: str, offline: bool = True
) -> list[dict[str, Any]]:
    """Stream the jsonl (375 MB — NEVER read whole) and return the
    rl_episode rows with v1's fail-loud shape checks (outcome present,
    ask-row keys, non-empty menu, idx in menu).

    Episode guard: OFFLINE mode (this trainer's default) BYPASSES the v1
    guard — policy==collecting-checkpoint SHA — with a stderr log line,
    because the recorded games were collected by the anchor and the
    policy is warm-started from that same anchor. ON-POLY mode
    (offline=False, tomorrow) enforces the guard exactly as v1 did."""
    if offline:
        print(
            f"train_rl_v2: OFFLINE mode — v1 episode guard BYPASSED "
            f"(policy={policy!r}); the guard (SHA-256 of --policy == "
            "episodes' collecting checkpoint) is enforced in on-policy mode",
            file=sys.stderr,
        )
        want: str | None = None
    else:
        want = _ckpt_key(policy)
    eps: list[dict[str, Any]] = []
    with open(episodes, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("kind") != "rl_episode":
                raise RuntimeError(
                    f"train_rl_v2: row {lineno} is not kind=rl_episode — "
                    "collection format drift"
                )
            if want is not None and _ckpt_key(row.get("policy", "")) != want:
                continue  # not collected by this policy: foreign, skip
            if row.get("outcome") not in REWARD:
                raise RuntimeError(
                    f"train_rl_v2: row {lineno} outcome={row.get('outcome')!r} "
                    "— outcome reward is unanchored (no silent default)"
                )
            asks = row.get("asks")
            if not isinstance(asks, list):
                # RuntimeError, not TypeError: recorded-file data drift,
                # same family as the other fail-loud checks below
                raise RuntimeError(  # noqa: TRY004
                    f"train_rl_v2: row {lineno} asks={asks!r} — shape drift"
                )
            for ai, a in enumerate(asks):
                missing = {"what", "vocab", "idx", "logp", "obs", "choose"} - set(a)
                if missing:
                    raise RuntimeError(
                        f"train_rl_v2: row {lineno} ask#{ai} missing keys "
                        f"{sorted(missing)} — ask-row shape drift"
                    )
                if not a["vocab"]:
                    raise RuntimeError(
                        f"train_rl_v2: row {lineno} ask#{ai} empty menu at "
                        f"{a['what']!r}"
                    )
                if not 0 <= a["idx"] < len(a["vocab"]):
                    raise RuntimeError(
                        f"train_rl_v2: row {lineno} ask#{ai} idx {a['idx']} "
                        f"outside the {len(a['vocab'])}-menu at {a['what']!r}"
                    )
            eps.append(row)
    if want is not None and not eps:
        raise RuntimeError(
            f"train_rl_v2: 0 episodes collected with {policy!r} (SHA-256 "
            "identity) — an update over nothing proves nothing"
        )
    return eps


def reenter_stash(a: dict[str, Any]) -> None:
    """Replay the collector's choose digest-stash exactly as v1 did (null
    stays null: blind stays blind)."""
    if a["what"].startswith("choose:"):
        digest = a["what"].rsplit(":", 1)[-1]
        if a["choose"] is None:
            bc_data_v2.stash_put(digest, None)
        else:
            pool, expand = a["choose"]
            bc_data_v2.stash_put(digest, [list(r) for r in pool], bool(expand))


@contextlib.contextmanager
def numlane_scope(vocab: dict[str, int]) -> Iterator[None]:
    """Per-policy language env swap (KNOWLEDGE/78) — the exact twin of
    BcAsk._forward_menu's swap: a checkpoint whose vocab carries the
    digit lanes must see digitized obs/candidate spans during encoding."""
    prev = os.environ.get(numlane.NUMTOK_ENV)
    if numlane.NUM_MARKER in vocab:
        os.environ[numlane.NUMTOK_ENV] = "1"
    else:
        os.environ.pop(numlane.NUMTOK_ENV, None)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(numlane.NUMTOK_ENV, None)
        else:
            os.environ[numlane.NUMTOK_ENV] = prev


# ---------------------------------------------------------- decision data
def encode_episode(
    ep: dict[str, Any],
    model: Any,
    vocab: dict[str, int],
    max_len: int,
    schema: str,
) -> list[dict[str, Any]]:
    """Replay one game's asks in order through a fresh BcAsk stream,
    encoding each ask with :meth:`BcAsk.prepare_ask` (byte-for-byte the
    inference encoding, no model call). Returns one decision record per
    ask — the SAME record schema the on-policy loop must produce:
    ``tokens [T]``, ``sep``, ``cand_ids [C,L]``, ``cand_mask [C,L]``,
    ``is_pass [C]``, ``idx``, ``logp_recorded``, ``reward``,
    ``outcome``. The stream mechanics (relevance ladder, truncation
    counting) are the collector's, so the encoding is EXACTLY what the
    game produced."""
    ask = BcAsk(model, vocab, max_len, schema)
    out: list[dict[str, Any]] = []
    for a in ep["asks"]:
        ctx = AskContext(vocab=a["what"], candidates=tuple(a["vocab"]), world=a["obs"])
        reenter_stash(a)
        with numlane_scope(vocab):
            t = ask.prepare_ask(torch, ctx)
        out.append(
            {
                "tokens": t["tokens"][0],  # [T]
                "sep": int(t["gold_pos"][0]),
                "cand_ids": t["cand_ids"][0],  # [C,L]
                "cand_mask": t["cand_mask"][0],  # [C,L]
                "is_pass": t["is_pass"][0],  # [C]
                "idx": int(a["idx"]),
                "logp_recorded": float(a["logp"]),
                "reward": REWARD[ep["outcome"]],
                "outcome": ep["outcome"],
                "state_feats": torch.tensor(
                    state_feats_from_obs(a["obs"]), dtype=torch.float32
                ),
            }
        )
    return out


def collate_decisions(
    items: list[dict[str, Any]], device: torch.device
) -> tuple[dict[str, torch.Tensor], list[int]]:
    """Pad a list of 1-row decision records into ONE forward batch:
    token rows right-padded to T_max (pad_mask True on the padding),
    vocab menus padded to C_max x L_max (cand_mask / is_pass False on
    padding). Returns (device tensors, per-row real menu lengths). The
    padding is invisible to the policy: masked candidate slots get
    -finfo.min logits (pointer_logits) -> exact-zero softmax mass and
    zero gradient, and the SEP readout never attends to padding
    (src_key_padding_mask)."""
    m = len(items)
    t_max = max(int(x["tokens"].shape[0]) for x in items)
    c_max = max(int(x["cand_ids"].shape[0]) for x in items)
    l_max = max(int(x["cand_ids"].shape[1]) for x in items)
    tokens = torch.zeros(m, t_max, dtype=torch.long)
    pad_mask = torch.ones(m, t_max, dtype=torch.bool)
    gold_pos = torch.zeros(m, dtype=torch.long)
    cand_ids = torch.zeros(m, c_max, l_max, dtype=torch.long)
    cand_mask = torch.zeros(m, c_max, l_max, dtype=torch.bool)
    is_pass = torch.zeros(m, c_max, dtype=torch.bool)
    k = int(items[0]["state_feats"].shape[0])
    state_feats = torch.zeros(m, k)
    menus: list[int] = []
    for i, x in enumerate(items):
        t = int(x["tokens"].shape[0])
        tokens[i, :t] = x["tokens"]
        pad_mask[i, :t] = False
        gold_pos[i] = x["sep"]
        c = int(x["cand_ids"].shape[0])
        l = int(x["cand_ids"].shape[1])
        menus.append(c)
        cand_ids[i, :c, :l] = x["cand_ids"]
        cand_mask[i, :c, :l] = x["cand_mask"]
        is_pass[i, :c] = x["is_pass"]
        state_feats[i] = x["state_feats"]
    out = {
        "tokens": tokens.to(device),
        "pad_mask": pad_mask.to(device),
        "gold_batch": torch.arange(m, dtype=torch.long, device=device),
        "gold_pos": gold_pos.to(device),
        "cand_ids": cand_ids.to(device),
        "cand_mask": cand_mask.to(device),
        "is_pass": is_pass.to(device),
        "state_feats": state_feats.to(device),
    }
    return out, menus


# ------------------------------------------------------------- GAE / EV
def compute_gae(
    rewards: list[float],
    values: list[float],
    gamma: float = 1.0,
    lam: float = 0.95,
) -> list[float]:
    """GAE with terminal value 0 at game end. ``rewards[t]`` is the
    reward placed AT decision t (v1 semantics: all 0 except the
    terminal decision's game-outcome reward); ``values[t]`` is V(s_t)
    from the value head. Recursion A_t = delta_t + lambda*gamma*A_{t+1}
    with A after the terminal = 0 (terminal value 0). Pure python —
    unit-tested against the closed form."""
    advs: list[float] = [0.0] * len(rewards)
    next_adv = 0.0
    for t in range(len(rewards) - 1, -1, -1):
        v_next = 0.0 if t == len(rewards) - 1 else values[t + 1]
        delta = rewards[t] + gamma * v_next - values[t]
        next_adv = delta + lam * gamma * next_adv
        advs[t] = next_adv
    return advs


def explained_variance(targets: list[float], preds: list[float]) -> float:
    """EV = 1 - Var(target - pred) / Var(target) (the constant-target
    baseline is the best zero-predictor). Returns 0.0 when Var(target)
    is ~0 (a single-outcome batch has nothing to explain)."""
    n = len(targets)
    if n != len(preds) or n == 0:
        raise ValueError("explained_variance: length mismatch")
    mean_t = sum(targets) / n
    var_t = sum((t - mean_t) ** 2 for t in targets) / n
    if var_t < 1e-12:
        return 0.0
    diff = [t - p for t, p in zip(targets, preds)]
    mean_d = sum(diff) / n
    var_d = sum((d - mean_d) ** 2 for d in diff) / n
    return 1.0 - var_d / var_t


def gae_advantages(
    decisions: list[dict[str, Any]],
    game_offsets: list[int],
    values: list[float],
    lam: float = 0.95,
) -> list[float]:
    """GAE per game over a flat decision list. ``game_offsets`` are the
    start indices of each game (decisions are grouped per game, in
    order); the game's outcome reward is placed at its TERMINAL
    decision only, terminal value 0."""
    advs: list[float] = []
    bounds = list(game_offsets) + [len(decisions)]
    for g in range(len(bounds) - 1):
        s, e = bounds[g], bounds[g + 1]
        n = e - s
        rewards = [0.0] * (n - 1) + [decisions[e - 1]["reward"]]
        advs.extend(compute_gae(rewards, values[s:e], gamma=1.0, lam=lam))
    return advs


# --------------------------------------------------------------- forward
def batch_forward(
    model: Any,
    items: list[dict[str, Any]],
    device: torch.device,
    with_value: bool = True,
) -> dict[str, Any]:
    """One no-grad batched forward over prepared decision records.
    Returns logp_chosen [m], menu_logp [m, c_max] (padded slots
    -finfo.min -> exact-zero mass), value [m] (None when with_value is
    False and the model is a plain PointerBC) and entropy [m]."""
    b, menus = collate_decisions(items, device)
    with torch.no_grad():
        if with_value:
            logits, value = model.forward_with_value(
                b["tokens"],
                b["pad_mask"],
                b["gold_batch"],
                b["gold_pos"],
                b["cand_ids"],
                b["cand_mask"],
                b["is_pass"],
                b["state_feats"],
            )
            value = value.float()
        else:
            logits = model.forward(
                b["tokens"],
                b["pad_mask"],
                b["gold_batch"],
                b["gold_pos"],
                b["cand_ids"],
                b["cand_mask"],
                b["is_pass"],
            )
            value = None
    logits = logits.float()
    menu_logp = torch.log_softmax(logits, dim=-1)
    idx = torch.tensor([x["idx"] for x in items], dtype=torch.long, device=device)
    p = menu_logp.exp()
    logp_chosen = menu_logp.gather(1, idx[:, None]).squeeze(1)
    entropy = -(p * menu_logp).sum(-1)
    return {
        "logp_chosen": logp_chosen.detach().cpu(),
        "menu_logp": menu_logp.detach().cpu(),
        "value": (value.detach().cpu() if value is not None else None),
        "entropy": entropy.detach().cpu(),
        "menus": menus,
    }


# ------------------------------------------------------------- warm start
def warm_start_value(
    policy: PointerBCValue,
    episodes: list[dict[str, Any]],
    vocab: dict[str, int],
    max_len: int,
    schema: str,
    device: str,
    lr: float = 1e-3,
    minibatch: int = 256,
    epochs: int = 3,
    seed: int = 1,
) -> dict[str, Any]:
    """Supervised warm-start of the value head ONLY (policy params are
    frozen during this phase and restored afterwards — the warm-start
    must not move the policy off the anchor). Target per decision = the
    game's outcome reward (the gamma=1 return). One Adam over the value
    head; loss is MSE. Returns train-set EV + diagnostics."""
    if str(device).startswith("cuda"):
        assert_cuda_headroom(25.0)
    dev = torch.device(device)
    dec: list[dict[str, Any]] = []
    for ep in episodes:
        dec.extend(encode_episode(ep, policy, vocab, max_len, schema))
    if not dec:
        raise RuntimeError("train_rl_v2: warm-start got zero decisions")
    targets = torch.tensor([d["reward"] for d in dec], dtype=torch.float32)
    vset = _value_param_ids(policy)
    for p in policy.parameters():
        p.requires_grad_(id(p) in vset)
    opt = torch.optim.Adam(policy.value_head.parameters(), lr=lr)
    rng = random.Random(seed)
    idxs = list(range(len(dec)))
    ev_train: float | None = None
    last_mean_mse: float | None = None
    try:
        for ep_i in range(epochs):
            rng.shuffle(idxs)
            losses = []
            for s in range(0, len(idxs), minibatch):
                sl = idxs[s : s + minibatch]
                items = [dec[i] for i in sl]
                b, _ = collate_decisions(items, dev)
                _, value = policy.forward_with_value(
                    b["tokens"],
                    b["pad_mask"],
                    b["gold_batch"],
                    b["gold_pos"],
                    b["cand_ids"],
                    b["cand_mask"],
                    b["is_pass"],
                    b["state_feats"],
                )
                loss = F.mse_loss(value.float(), targets[sl].to(dev))
                opt.zero_grad(set_to_none=True)
                loss.backward()
                opt.step()
                losses.append(float(loss.detach()))
            last_mean_mse = sum(losses) / len(losses)
            if ep_i == epochs - 1:
                with torch.no_grad():
                    vals: list[float] = []
                    for s in range(0, len(dec), minibatch):
                        items = dec[s : s + minibatch]
                        b, _ = collate_decisions(items, dev)
                        _, value = policy.forward_with_value(
                            b["tokens"],
                            b["pad_mask"],
                            b["gold_batch"],
                            b["gold_pos"],
                            b["cand_ids"],
                            b["cand_mask"],
                            b["is_pass"],
                            b["state_feats"],
                        )
                        vals.extend(value.float().cpu().tolist())
                    ev_train = explained_variance([d["reward"] for d in dec], vals)
    finally:
        for p in policy.parameters():
            p.requires_grad_(True)  # never leave the policy frozen
    return {
        "games": len(episodes),
        "decisions": len(dec),
        "epochs": epochs,
        "lr": lr,
        "last_epoch_mean_mse": last_mean_mse,
        "ev_train": ev_train,
    }


def measure_value_ev(
    policy: PointerBCValue,
    episodes: list[dict[str, Any]],
    vocab: dict[str, int],
    max_len: int,
    schema: str,
    device: str,
    minibatch: int = 256,
) -> float:
    """Explained variance of the current value head vs the outcome
    baseline on the given (held-out) episodes. Triage rule #1's number."""
    if str(device).startswith("cuda"):
        assert_cuda_headroom(25.0)
    dev = torch.device(device)
    dec: list[dict[str, Any]] = []
    for ep in episodes:
        dec.extend(encode_episode(ep, policy, vocab, max_len, schema))
    if not dec:
        return 0.0
    vals: list[float] = []
    with torch.no_grad():
        for s in range(0, len(dec), minibatch):
            items = dec[s : s + minibatch]
            b, _ = collate_decisions(items, dev)
            _, value = policy.forward_with_value(
                b["tokens"],
                b["pad_mask"],
                b["gold_batch"],
                b["gold_pos"],
                b["cand_ids"],
                b["cand_mask"],
                b["is_pass"],
                b["state_feats"],
            )
            vals.extend(value.float().cpu().tolist())
    return explained_variance([d["reward"] for d in dec], vals)


# ----------------------------------------------------------------- update
def ppo_update(
    policy: PointerBCValue,
    anchor: PointerBC,
    decisions: list[dict[str, Any]],
    game_offsets: list[int],
    *,
    epochs: int,
    minibatch: int,
    lr: float,
    value_lr: float,
    ratio_clip: float = 0.2,
    kl_stop: float = DEFAULT_KL_STOP,
    grad_clip: float = DEFAULT_GRAD_CLIP,
    value_coef: float = 0.5,
    gae_lambda: float = 0.95,
    seed: int = 1,
    device: str = "cpu",
) -> dict[str, Any]:
    """One PPO update over a batch of decisions (from G games, grouped
    per game with ``game_offsets``).

    old_logp / V0 are recomputed through the CURRENT weights at update
    start (no_grad, batched) — the PPO ratio baseline is the policy as
    it sits, not the recorded logp (which equals it at iteration 0 only).
    GAE uses V0 and is FIXED across epochs (standard PPO); the value
    target is the game's outcome reward (the gamma=1 return). The
    anchor's full-menu logp is cached once (no_grad); per-minibatch KL
    vs that cache drives the early-stop (running mean over the update's
    decisions > kl_stop) and the log.

    Returns the per-update metric dict (the log line) plus raw grad
    norms. Raises on a non-finite loss."""
    if str(device).startswith("cuda"):
        assert_cuda_headroom(25.0)
    dev = torch.device(device)
    m = len(decisions)
    if m == 0:
        raise RuntimeError("train_rl_v2: ppo_update on zero decisions")

    # ---- start-of-update reference forwards (no_grad, batched) ----
    old_logp = torch.zeros(m, dtype=torch.float32)
    v0 = torch.zeros(m, dtype=torch.float32)
    anchor_parts: list[torch.Tensor] = []
    with torch.no_grad():
        for s in range(0, m, minibatch):
            items = decisions[s : s + minibatch]
            r = batch_forward(policy, items, dev, with_value=True)
            old_logp[s : s + len(items)] = r["logp_chosen"]
            v0[s : s + len(items)] = r["value"]
            b, _ = collate_decisions(items, dev)
            anc = anchor.forward(
                b["tokens"],
                b["pad_mask"],
                b["gold_batch"],
                b["gold_pos"],
                b["cand_ids"],
                b["cand_mask"],
                b["is_pass"],
            )
            anchor_parts.append(torch.log_softmax(anc.float(), dim=-1).cpu())
    anchor_lps_t = torch.cat(anchor_parts, 0)

    # ---- GAE per game, then the update ----
    adv = gae_advantages(decisions, game_offsets, v0.tolist(), lam=gae_lambda)
    adv_t = torch.tensor(adv, dtype=torch.float32, device=dev)
    targets = torch.tensor([d["reward"] for d in decisions], dtype=torch.float32)

    vset = _value_param_ids(policy)
    opt_policy = torch.optim.Adam(
        [p for p in policy.parameters() if id(p) not in vset], lr=lr
    )
    opt_value = torch.optim.Adam(policy.value_head.parameters(), lr=value_lr)

    rng = random.Random(seed)
    idxs = list(range(m))
    epoch_losses: list[float] = []
    raw_norms: list[float] = []
    kl_sum = 0.0
    seen = 0
    n_mbs = 0
    early_stopped = False
    entropy_sum = 0.0
    pg_sum = 0.0
    vloss_sum = 0.0
    epochs_run = 0
    for ep_i in range(epochs):
        rng.shuffle(idxs)
        tot = 0.0
        n_in_ep = 0
        for s in range(0, m, minibatch):
            sl = idxs[s : s + minibatch]
            if not sl:
                continue
            sl_cpu = torch.tensor(sl, dtype=torch.long)
            sl_t = sl_cpu.to(dev)
            items = [decisions[i] for i in sl]
            b, _ = collate_decisions(items, dev)
            logits, value = policy.forward_with_value(
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
            menu_logp = torch.log_softmax(logits, dim=-1)
            idx = torch.tensor([d["idx"] for d in items], dtype=torch.long, device=dev)
            logp_chosen = menu_logp.gather(1, idx[:, None]).squeeze(1)
            ratio = torch.exp(logp_chosen - old_logp[sl_cpu].to(dev))
            a = adv_t[sl_t]
            sur1 = ratio * a
            sur2 = torch.clamp(ratio, 1.0 - ratio_clip, 1.0 + ratio_clip) * a
            pg_loss = -torch.min(sur1, sur2).mean()
            v_loss = F.mse_loss(value.float(), targets[sl_cpu].to(dev))
            loss = pg_loss + value_coef * v_loss
            if not torch.isfinite(loss):
                raise RuntimeError(
                    "train_rl_v2: non-finite loss in PPO update — "
                    f"pg={float(pg_loss)} v={float(v_loss)}"
                )
            opt_policy.zero_grad(set_to_none=True)
            opt_value.zero_grad(set_to_none=True)
            loss.backward()
            raw = float(torch.nn.utils.clip_grad_norm_(policy.parameters(), grad_clip))
            opt_policy.step()
            opt_value.step()
            raw_norms.append(raw)
            # KL vs the frozen anchor for this minibatch (no extra forward:
            # current menu logp vs the cached anchor logp, same padding)
            kl_m = (
                (menu_logp.exp() * (menu_logp - anchor_lps_t[sl_cpu].to(dev)))
                .sum(-1)
                .mean()
            )
            kl_sum += float(kl_m) * len(sl)
            seen += len(sl)
            entropy_sum += float((-(menu_logp.exp() * menu_logp)).sum(-1).mean()) * len(
                sl
            )
            pg_sum += float(pg_loss) * len(sl)
            vloss_sum += float(v_loss) * len(sl)
            n_mbs += 1
            tot += float(loss)
            n_in_ep += 1
            # early-stop: running mean KL vs the frozen anchor
            if seen > 0 and (kl_sum / seen) > kl_stop:
                early_stopped = True
                break
        epoch_losses.append(tot / max(n_in_ep, 1))
        epochs_run += 1
        if early_stopped:
            break

    # post-update movement check (v1 /158 discipline: an update that did
    # not move the chosen-action logp is a no-op, not a success)
    dlogp_sum = 0.0
    with torch.no_grad():
        for s in range(0, m, minibatch):
            items = decisions[s : s + minibatch]
            r = batch_forward(policy, items, dev, with_value=False)
            anc_chosen = (
                anchor_lps_t[s : s + len(items)]
                .gather(
                    1,
                    torch.tensor([d["idx"] for d in items], dtype=torch.long)[:, None],
                )
                .squeeze(1)
            )
            dlogp_sum += float((r["logp_chosen"] - anc_chosen).abs().sum())

    n = max(m, 1)
    return {
        "policy_loss": pg_sum / n,
        "value_loss": vloss_sum / n,
        "value_explained_variance": explained_variance(
            [d["reward"] for d in decisions], v0.tolist()
        ),
        "advantage_mean": float(adv_t.mean()),
        "advantage_std": float(adv_t.std()),
        "entropy_mean": entropy_sum / n,
        "kl_per_update": kl_sum / max(seen, 1),
        "chosen_dlogp_post": dlogp_sum / n,
        "grad_norm_preclip": sum(raw_norms) / max(len(raw_norms), 1),
        "grad_norm_max": max(raw_norms) if raw_norms else 0.0,
        "grad_clip_binds_pct": (
            sum(1 for r in raw_norms if r > grad_clip) / max(len(raw_norms), 1)
            if raw_norms
            else 0.0
        ),
        "raw_grad_norms": raw_norms,
        "epochs_planned": epochs,
        "epochs_run": epochs_run,
        "early_stopped": early_stopped,
        "minibatches": n_mbs,
        "decisions": m,
        "epoch_losses": epoch_losses,
    }


# ------------------------------------------------------------------ train
def _carve_games(
    order: list[int], ev_games: int, warm_start_games: int, need: int
) -> tuple[list[int], list[int], list[int]]:
    """Split the shuffled game order into (ev, warm, update-pool) index
    lists. Priority order: the update pool (nothing trains without it),
    then the warm-start sample, then the held-out EV set — each shrinks
    only when there are not enough games. ``warm_start_games<=0`` means
    'all remaining'."""
    n = len(order)
    ev_n = min(ev_games, n)
    warm_n = n - ev_n - need if warm_start_games <= 0 else warm_start_games
    warm_n = max(0, min(warm_n, n - ev_n - need))
    ev_idx = order[:ev_n]
    warm_idx = order[ev_n : ev_n + warm_n]
    pool = order[ev_n + warm_n :]
    return ev_idx, warm_idx, pool


def train(
    episodes: Path,
    policy: str,
    anchor: str | None = None,
    *,
    device: str = "cpu",
    tag: str = "rlv2_i1",
    out_dir: Path | None = None,
    lr: float = 3e-4,
    value_lr: float = 1e-3,
    games: int = 50,
    iterations: int = 1,
    epochs: int = 3,
    minibatch: int = 256,
    gae_lambda: float = 0.95,
    kl_stop: float = DEFAULT_KL_STOP,
    grad_clip: float = DEFAULT_GRAD_CLIP,
    ratio_clip: float = 0.2,
    value_coef: float = 0.5,
    warm_start_games: int = 500,
    ev_games: int = 200,
    seed: int = 1,
    offline: bool = True,
    save: bool = True,
) -> dict[str, Any]:
    """The offline entry point: stream episodes, load the anchor bit-
    identically, warm-start the value head (triage rule #1: held-out EV
    must be > 0 or the run stops), then run ``iterations`` PPO updates
    over fresh G-game batches (no reuse within a run — the on-policy
    batch law, carried into offline debugging). One JSON log line per
    update (stdout + <tag>_updates.jsonl); final diag + checkpoint."""
    anchor = anchor or policy
    blob = load_blob(policy)
    schema = str(blob.get("schema", "v1"))
    if schema == "v2":
        bc_data_v2.install_choose_stash()
    vocab = blob["vocab"]
    max_len = int(blob["config"]["max_len"])
    policy_model = load_policy(blob, device, train=True)
    anchor_model = build_anchor(load_blob(anchor), device)

    eps = load_episodes(episodes, policy, offline=offline)
    if not eps:
        raise RuntimeError("train_rl_v2: 0 episodes loaded — nothing to train")
    rng = random.Random(seed)
    order = list(range(len(eps)))
    rng.shuffle(order)
    ev_idx, warm_idx, pool = _carve_games(
        order, ev_games, warm_start_games, games * iterations
    )
    ev_eps = [eps[i] for i in ev_idx]
    warm_eps = [eps[i] for i in warm_idx]

    ws = warm_start_value(
        policy_model,
        warm_eps,
        vocab,
        max_len,
        schema,
        device,
        lr=value_lr,
        minibatch=minibatch,
        seed=seed,
    )
    ev_holdout = measure_value_ev(
        policy_model, ev_eps, vocab, max_len, schema, device, minibatch
    )
    # triage rule #1: a value head that explains nothing is a bug
    if ev_holdout <= 0.0:
        raise RuntimeError(
            f"train_rl_v2: warm-start value head explained variance "
            f"{ev_holdout:.4f} <= 0 on {len(ev_eps)} held-out games — "
            "triage rule #1: fix the value head before any policy tuning"
        )

    updates: list[dict[str, Any]] = []
    kl_cum = 0.0
    total_decisions = 0
    for it in range(iterations):
        if len(pool) < games:
            raise RuntimeError(
                "train_rl_v2: update pool exhausted before iteration "
                f"{it + 1} ({len(pool)} games left < games={games}) — "
                "not enough recorded games for this run"
            )
        batch_eps = [eps[pool.pop(0)] for _ in range(games)]
        dec: list[dict[str, Any]] = []
        offsets: list[int] = []
        for ep in batch_eps:
            offsets.append(len(dec))
            dec.extend(encode_episode(ep, policy_model, vocab, max_len, schema))
        total_decisions += len(dec)
        if not dec:
            raise RuntimeError(
                f"train_rl_v2: iteration {it + 1}: 0 decisions from "
                f"{len(batch_eps)} games — nothing to update"
            )
        u = ppo_update(
            policy_model,
            anchor_model,
            dec,
            offsets,
            epochs=epochs,
            minibatch=minibatch,
            lr=lr,
            value_lr=value_lr,
            ratio_clip=ratio_clip,
            kl_stop=kl_stop,
            grad_clip=grad_clip,
            value_coef=value_coef,
            gae_lambda=gae_lambda,
            seed=seed + 1000 * (it + 1),
            device=device,
        )
        kl_cum += u["kl_per_update"]
        line = {
            "iter": it + 1,
            "tag": tag,
            "device": device,
            "games": len(batch_eps),
            "wins": sum(1 for ep in batch_eps if ep["outcome"] == "win"),
            "losses": sum(1 for ep in batch_eps if ep["outcome"] == "loss"),
            "draws": sum(1 for ep in batch_eps if ep["outcome"] == "draw"),
            "crashes": sum(1 for ep in batch_eps if ep["outcome"] == "crash"),
            "asks": u["decisions"],
            "policy_loss": u["policy_loss"],
            "value_loss": u["value_loss"],
            "value_explained_variance": u["value_explained_variance"],
            "advantage_mean": u["advantage_mean"],
            "advantage_std": u["advantage_std"],
            "entropy_mean": u["entropy_mean"],
            "kl_per_update": u["kl_per_update"],
            "kl_cumulative": kl_cum,
            "grad_norm_preclip": u["grad_norm_preclip"],
            "grad_norm_max": u["grad_norm_max"],
            "grad_clip_binds_pct": u["grad_clip_binds_pct"],
            "epochs_run": u["epochs_run"],
            "epochs_planned": u["epochs_planned"],
            "early_stopped": u["early_stopped"],
            "minibatches": u["minibatches"],
            "epoch_losses": u["epoch_losses"],
            "chosen_dlogp_post": u["chosen_dlogp_post"],
        }
        updates.append(line)
        print(json.dumps(line), flush=True)

    diag = {
        "tag": tag,
        "policy": str(Path(policy).resolve()),
        "anchor": str(Path(anchor).resolve()),
        "device": device,
        "offline": offline,
        "lr": lr,
        "value_lr": value_lr,
        "games_per_iter": games,
        "iterations": iterations,
        "epochs": epochs,
        "minibatch": minibatch,
        "gae_lambda": gae_lambda,
        "kl_stop": kl_stop,
        "grad_clip": grad_clip,
        "ratio_clip": ratio_clip,
        "value_coef": value_coef,
        "warm_start": ws,
        "value_ev_holdout": ev_holdout,
        "ev_games": len(ev_eps),
        "total_decisions": total_decisions,
        "episodes_owned": len(eps),
        "episodes_used_warm": len(warm_eps),
        "episodes_used_updates": sum(u["games"] for u in updates),
        "kl_cumulative_final": kl_cum,
        "crashes_total": sum(u["crashes"] for u in updates),
        "draws_total": sum(u["draws"] for u in updates),
        "updates": updates,
    }

    if save:
        save_ckpt(policy_model, blob, tag, out_dir or episodes.parent, diag, schema)
    return diag


def save_ckpt(
    policy_model: PointerBCValue,
    blob: dict[str, Any],
    tag: str,
    out_dir: str | Path,
    diag: dict[str, Any],
    schema: str,
) -> None:
    """The checkpoint pair: <tag>.pt (FULL v2 state: policy + value head,
    loaded by :func:`load_policy`) and <tag>_policy.pt (ON-POLY sidecar —
    the collection rig (BcAsk.fresh) strict-loads a plain PointerBC, so
    the inter-iteration checkpoint the next collect must use is the
    POLICY-ONLY copy, value keys stripped, bit-identical policy weights).
    Plus the <tag>_diag.json and <tag>_updates.jsonl when the diag carries
    an 'updates' list."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    full_state = {k: v.cpu() for k, v in policy_model.state_dict().items()}
    torch.save(
        {
            "schema": schema,
            "state": full_state,
            "config": blob["config"],
            "vocab": blob["vocab"],
            "seed": int(blob.get("seed", 0)),
            "train_info": {
                "kind": "rl_v2",
                "iter": tag,
                "diag": diag,
                "value_head": (
                    "value_head.{weight,bias} — scalar linear on the "
                    "encoder SEP state; load with "
                    "train_rl_v2.load_policy or "
                    "PointerBCValue.load_state_dict(strict=False)"
                ),
            },
        },
        out_dir / f"{tag}.pt",
    )
    torch.save(
        {
            "schema": schema,
            "state": {k: v for k, v in full_state.items() if k not in VALUE_KEYS},
            "config": blob["config"],
            "vocab": blob["vocab"],
            "seed": int(blob.get("seed", 0)),
            "train_info": {
                "kind": "rl_v2_policy_sidecar",
                "iter": tag,
                "note": "PointerBC-format copy of the v2 policy for "
                "BcAsk.fresh collection; the value head lives in "
                "<tag>.pt only",
            },
        },
        out_dir / f"{tag}_policy.pt",
    )
    (out_dir / f"{tag}_diag.json").write_text(
        json.dumps(diag, indent=1), encoding="utf-8"
    )
    updates = diag.get("updates")
    if isinstance(updates, list):
        with open(out_dir / f"{tag}_updates.jsonl", "w", encoding="utf-8") as f:
            for line in updates:
                f.write(json.dumps(line) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--episodes", type=Path, required=True)
    ap.add_argument("--policy", required=True, help="checkpoint to train")
    ap.add_argument(
        "--anchor", default=None, help="frozen KL anchor (default: --policy)"
    )
    ap.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    ap.add_argument("--tag", default="rlv2_i1")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument(
        "--lr", type=float, default=3e-4, help="policy Adam lr (PPO default 3e-4)"
    )
    ap.add_argument("--value-lr", type=float, default=1e-3)
    ap.add_argument("--games", type=int, default=50, help="G: games per update batch")
    ap.add_argument("--iterations", type=int, default=1)
    ap.add_argument("--epochs", type=int, default=3, help="PPO epochs per batch (2-4)")
    ap.add_argument(
        "--minibatch", type=int, default=256, help="decisions per forward (64-256 band)"
    )
    ap.add_argument("--gae-lambda", type=float, default=0.95)
    ap.add_argument("--kl-stop", type=float, default=DEFAULT_KL_STOP)
    ap.add_argument("--grad-clip", type=float, default=DEFAULT_GRAD_CLIP)
    ap.add_argument("--ratio-clip", type=float, default=0.2)
    ap.add_argument("--value-coef", type=float, default=0.5)
    ap.add_argument(
        "--warm-start-games",
        type=int,
        default=500,
        help="0 = all remaining after EV/update carve-out",
    )
    ap.add_argument(
        "--ev-games",
        type=int,
        default=200,
        help="held-out games for the value EV report",
    )
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--offline",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="train purely on the recorded episodes (default); --no-offline enforces the v1 episode guard (on-policy mode)",
    )
    args = ap.parse_args(argv)
    diag = train(
        args.episodes,
        args.policy,
        anchor=args.anchor,
        device=args.device,
        tag=args.tag,
        out_dir=args.out_dir,
        lr=args.lr,
        value_lr=args.value_lr,
        games=args.games,
        iterations=args.iterations,
        epochs=args.epochs,
        minibatch=args.minibatch,
        gae_lambda=args.gae_lambda,
        kl_stop=args.kl_stop,
        grad_clip=args.grad_clip,
        ratio_clip=args.ratio_clip,
        value_coef=args.value_coef,
        warm_start_games=args.warm_start_games,
        ev_games=args.ev_games,
        seed=args.seed,
        offline=args.offline,
    )
    last = diag["updates"][-1] if diag["updates"] else {}
    print(
        f"train_rl_v2 [{args.tag}]: {diag['iterations']} iters x "
        f"{diag['games_per_iter']}g | EV={diag['value_ev_holdout']:.4f} "
        f"KL={last.get('kl_per_update', 0):.4g} "
        f"cumKL={diag['kl_cumulative_final']:.4g} "
        f"ent={last.get('entropy_mean', 0):.4g} "
        f"grad={last.get('grad_norm_preclip', 0):.4g} "
        f"clipBinds={last.get('grad_clip_binds_pct', 0):.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
