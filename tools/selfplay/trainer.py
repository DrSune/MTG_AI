"""The trainer process: PPO updates (ppo.py) in their own process and CUDA context.

The learner keeps answering the workers on the current weights while this process trains on
the previous batch; the GPU time-slices between the two contexts, so the workers never wait for
an update. Protocol (one Pipe): learner -> ("update", payload) | ("stop",); trainer ->
("done", state, stats) | ("error", text).
"""

from __future__ import annotations

import traceback
from types import SimpleNamespace
from typing import Any


def _mem_available_gib() -> float:
    with open("/proc/meminfo") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1048576
    return float("nan")


def trainer_main(conn: Any, ckpt: dict, args: dict) -> None:
    import torch

    from tools.selfplay import features as FT
    from tools.selfplay import model as M
    from tools.selfplay.ppo import ppo_train

    a = SimpleNamespace(**args)
    device = torch.device("cuda" if torch.cuda.is_available() and a.device != "cpu" else "cpu")
    table = FT.CardTable.from_json(ckpt["table"])
    cfg = {k: v for k, v in ckpt["config"].items() if k not in ("n_cards", "n_ir")}

    def build(state: dict) -> torch.nn.Module:
        net = M.build(table, **cfg).to(device)
        net.load_state_dict(state)
        return net.eval()

    model = build(ckpt["state"])
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, betas=(0.9, 0.99), eps=1e-6,
                            weight_decay=a.wd)

    def check() -> None:
        avail = _mem_available_gib()
        if avail < a.mem_floor_gib:
            raise MemoryError(f"trainer: MemAvailable {avail:.1f} GiB < floor {a.mem_floor_gib}")

    def release() -> None:
        if device.type == "cuda":
            torch.cuda.empty_cache()

    try:
        while True:
            msg = conn.recv()
            if msg[0] == "stop":
                return
            _, payload = msg
            stats = ppo_train(model, opt, a=a, device=device, check=check, release=release,
                              **payload)
            state = {k: v.detach().to("cpu") for k, v in model.state_dict().items()}
            conn.send(("done", state, stats))
    except BaseException as error:  # noqa: BLE001 - reported to the learner, which stops
        try:
            conn.send(("error", f"{type(error).__name__}: {error}\n{traceback.format_exc()[-1500:]}"))
        except (BrokenPipeError, OSError):
            pass
