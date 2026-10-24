"""An LLM seat, local first (docs/DESIGN_BENCHMARK.md §3.4, §8).

**Prompt mode.** One completion per ask. The prompt is the system preamble plus, optionally, the
engine primer (``primer.render_primer``), then the seat's view, then the numbered options. The
reply must end with ``ANSWER: <number>``. That works with any model, local or hosted, with or
without tool calling. Tool mode and MCP come next, over the same surfaces.

**Same action space as our bot.** The agent sees exactly the options the router offers every
seat. It does not train an internal representation; it reads.

**Accounting.**
- An unparseable or out-of-range answer is retried with the error, up to ``strikes`` attempts. Then
  the do-nothing option is taken and a forfeit is recorded. Forfeits are reported, never hidden
  (``BEN-F1``), and the 3 strikes are a registered scaffold.
- A transport failure raises ``AgentInfraError``, which voids the game: an outage is not a loss.
- Tokens and latency are counted per agent, for the cost and clock Pareto plots.

**Local first, no surprise bills.** ``OpenAICompatClient`` refuses a non-local endpoint unless
``MTG_BENCH_ALLOW_REMOTE=1`` is set. It uses only the standard library.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlparse

from MTG_bot.bench.agents import InfraError

if TYPE_CHECKING:
    from MTG_bot.bench.agents import Observation
    from MTG_bot.bench.protocol import Ask

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_ANSWER = re.compile(r"ANSWER:\s*\[?\s*(\d+)\s*\]?", re.IGNORECASE)

SYSTEM_PROMPT = """You are playing Magic: The Gathering through a rules engine: two players, 20 life, 60-card decks.
Only the result of the game is scored: a win, a draw, or a loss. Style, speed of thought and explanations score nothing.
Each message shows your view of the game (you never see hidden cards) and one decision with numbered options.
You may reason briefly first. Your reply must end with a final line of the form: ANSWER: <number>"""


class AgentInfraError(InfraError):
    pass


@dataclass(frozen=True)
class ChatResult:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_s: float = 0.0


class ChatClient(Protocol):
    def complete(self, messages: list[dict[str, str]], *, max_tokens: int, temperature: float) -> ChatResult: ...


class ScriptedClient:
    """Replays fixed replies and records every request (tests make no network calls)."""

    def __init__(self, replies: Iterable[str]) -> None:
        self.replies = list(replies)
        self.requests: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int, temperature: float) -> ChatResult:
        self.requests.append([dict(m) for m in messages])
        if not self.replies:
            raise AgentInfraError("scripted client exhausted")
        return ChatResult(self.replies.pop(0), prompt_tokens=10, completion_tokens=2)


class OpenAICompatClient:
    """``POST {base_url}/chat/completions``: vLLM, llama.cpp server, or any compatible endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout_s: float = 120.0,
        allow_remote: bool = False,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        host = urlparse(base_url).hostname or ""
        if host not in LOCAL_HOSTS and not allow_remote:
            raise ValueError(
                f"refusing non-local endpoint {base_url!r}: hosted models cost money; "
                "set MTG_BENCH_ALLOW_REMOTE=1 to allow it deliberately"
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self._open = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> OpenAICompatClient:
        model = os.environ.get("MTG_BENCH_LLM_MODEL")
        if not model:
            raise ValueError("set MTG_BENCH_LLM_MODEL (and MTG_BENCH_LLM_BASE_URL, default http://localhost:8000/v1)")
        return cls(
            os.environ.get("MTG_BENCH_LLM_BASE_URL", "http://localhost:8000/v1"),
            model,
            api_key=os.environ.get("MTG_BENCH_LLM_API_KEY"),
            timeout_s=float(os.environ.get("MTG_BENCH_LLM_TIMEOUT_S", "120")),
            allow_remote=os.environ.get("MTG_BENCH_ALLOW_REMOTE") == "1",
        )

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int, temperature: float) -> ChatResult:
        body = json.dumps(
            {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        ).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(f"{self.base_url}/chat/completions", data=body, headers=headers)
        started = time.monotonic()
        try:
            with self._open(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read())
            text = payload["choices"][0]["message"]["content"] or ""
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError) as error:
            raise AgentInfraError(f"{self.base_url}: {type(error).__name__}: {error}") from error
        usage = payload.get("usage") or {}
        return ChatResult(text, usage.get("prompt_tokens"), usage.get("completion_tokens"), time.monotonic() - started)


def parse_answer(text: str, n_options: int) -> int | None:
    matches = _ANSWER.findall(text or "")
    if not matches:
        return None
    k = int(matches[-1])
    return k if 0 <= k < n_options else None


class LLMAgent:
    def __init__(
        self,
        client: ChatClient,
        *,
        name: str = "llm",
        strikes: int = 3,
        max_tokens: int = 512,
        temperature: float = 0.0,
        primer: str = "",
    ) -> None:
        self.client = client
        self.name = name
        self.strikes = strikes
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system = SYSTEM_PROMPT + (f"\n\n{primer}" if primer else "")
        self.stats: Counter[str] = Counter()

    def decide(self, ask: Ask, obs: Observation) -> int:
        n = len(ask.options)
        messages = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": f"{obs.text}\n\nDecision:\n{ask.render()}\n\nEnd with: ANSWER: <number from 0 to {n - 1}>"},
        ]
        for _ in range(self.strikes):
            result = self.client.complete(messages, max_tokens=self.max_tokens, temperature=self.temperature)
            self.stats["calls"] += 1
            self.stats["prompt_tokens"] += result.prompt_tokens or 0
            self.stats["completion_tokens"] += result.completion_tokens or 0
            self.stats["latency_ms"] += int(result.latency_s * 1000)
            choice = parse_answer(result.text, n)
            if choice is not None:
                self.stats["decisions"] += 1
                return choice
            self.stats["invalid_answers"] += 1
            messages += [
                {"role": "assistant", "content": result.text},
                {"role": "user", "content": f"That is not a valid answer. End with: ANSWER: <number from 0 to {n - 1}>"},
            ]
        self.stats["forfeits"] += 1
        return ask.refuse if ask.refuse is not None else 0
