"""The LLM seat, with no network: scripted replies and a fake HTTP opener."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from MTG_bot.bench.agents import AgentForfeitError, PassAgent
from MTG_bot.bench.duel import DealSpec, run_match, summarize
from MTG_bot.bench.llm import (
    AgentInfraError,
    ChatResult,
    LLMAgent,
    OpenAICompatClient,
    ScriptedClient,
    parse_answer,
)
from MTG_bot.bench.protocol import Ask, Option

ASK = Ask(
    seat=0,
    kind="attack",
    site="attack:card:1:3",
    prompt="Attack?",
    options=(Option("ATTACK", "attack"), Option("DECLINE", "do not attack")),
    refuse=1,
)
# A forced-target ask: every option commits, there is no do-nothing option.
FORCED = Ask(
    seat=0,
    kind="target",
    site="pick:card:1:0",
    prompt="Pick.",
    options=(Option("card:1", "creature A"),),
    refuse=None,
)


class _Obs:
    text = "Turn 3. (view)"


def test_parse_answer_takes_the_last_valid_line() -> None:
    assert parse_answer("thinking... ANSWER: 1", 2) == 1
    assert parse_answer("ANSWER: 0\nno wait\nANSWER: [1]", 2) == 1
    assert parse_answer("ANSWER: 7", 2) is None
    assert parse_answer("attack!", 2) is None


def test_a_valid_reply_is_one_call() -> None:
    agent = LLMAgent(ScriptedClient(["ANSWER: 0"]))
    assert agent.decide(ASK, _Obs()) == 0
    assert agent.stats["calls"] == 1 and agent.stats["forfeits"] == 0


def test_an_invalid_reply_is_retried_with_the_error() -> None:
    client = ScriptedClient(["I attack", "ANSWER: 0"])
    agent = LLMAgent(client)
    assert agent.decide(ASK, _Obs()) == 0
    assert agent.stats["invalid_answers"] == 1
    assert "not a valid answer" in client.requests[1][-1]["content"]


def test_strikes_end_in_a_recorded_forfeit_of_the_do_nothing_option() -> None:
    agent = LLMAgent(ScriptedClient(["?", "??", "???"]), strikes=3)
    assert agent.decide(ASK, _Obs()) == ASK.refuse
    assert agent.stats["forfeits"] == 1


def test_the_primer_rides_in_the_system_prompt() -> None:
    client = ScriptedClient(["ANSWER: 1"])
    LLMAgent(client, primer="ENGINE PRIMER: test").decide(ASK, _Obs())
    assert "ENGINE PRIMER: test" in client.requests[0][0]["content"]


def test_remote_endpoints_are_refused_unless_allowed() -> None:
    with pytest.raises(ValueError, match="non-local"):
        OpenAICompatClient("https://api.example.com/v1", "m")
    OpenAICompatClient("https://api.example.com/v1", "m", allow_remote=True)


def test_the_client_speaks_openai_chat_and_counts_usage() -> None:
    sent = {}

    def opener(request, timeout):
        sent["url"], sent["body"] = request.full_url, json.loads(request.data)
        reply = {
            "choices": [{"message": {"content": "ANSWER: 1"}}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 3},
        }
        return io.BytesIO(json.dumps(reply).encode())

    result = OpenAICompatClient(
        "http://localhost:8000/v1", "qwen", opener=opener
    ).complete([{"role": "user", "content": "hi"}], max_tokens=8, temperature=0.0)
    assert sent["url"] == "http://localhost:8000/v1/chat/completions"
    assert sent["body"]["model"] == "qwen" and sent["body"]["max_tokens"] == 8
    assert (result.text, result.prompt_tokens, result.completion_tokens) == (
        "ANSWER: 1",
        42,
        3,
    )


def test_a_transport_failure_is_an_infra_error() -> None:
    def opener(request, timeout):
        raise urllib.error.URLError("connection refused")

    with pytest.raises(AgentInfraError):
        OpenAICompatClient("http://localhost:1/v1", "m", opener=opener).complete(
            [], max_tokens=1, temperature=0
        )


def test_an_outage_mid_game_voids_the_pair() -> None:
    # A scripted client that runs dry is an outage: the game is void-infra, never a loss.
    rows = run_match(
        lambda d, g, s: LLMAgent(ScriptedClient(["ANSWER: 0"] * 3)),
        lambda d, g, s: PassAgent(),
        [DealSpec(seed=1, turn_cap=20)],
        name_a="llm",
        name_b="pass",
    )
    games = [r for r in rows if r["kind"] == "game"]
    assert {r["outcome"] for r in games} == {"void-infra"}
    assert summarize(rows)["pairs"] == 0


class _NoUsageClient:
    """Always answers validly, but never reports a usage block."""

    def complete(
        self, messages: list[dict[str, str]], *, max_tokens: int, temperature: float
    ) -> ChatResult:
        return ChatResult("ANSWER: 0")


def test_missing_usage_is_counted_and_never_filled_with_silent_zeros() -> None:
    agent = LLMAgent(_NoUsageClient())
    assert agent.decide(ASK, _Obs()) == 0
    assert agent.stats["usage_missing"] == 1
    assert agent.stats["prompt_tokens"] == 0  # counted as 0, but the gap is flagged


def test_strikes_exhausted_without_a_refuse_raise_instead_of_playing() -> None:
    agent = LLMAgent(ScriptedClient(["?", "??", "???"]), strikes=3)
    with pytest.raises(AgentForfeitError, match="forfeit-no-refuse"):
        agent.decide(FORCED, _Obs())
    assert agent.stats["forfeits"] == 1


def test_strikes_exhausted_with_a_refuse_still_takes_the_do_nothing_option() -> None:
    agent = LLMAgent(ScriptedClient(["?", "?", "?"]), strikes=3)
    assert agent.decide(ASK, _Obs()) == ASK.refuse
    assert agent.stats["forfeits"] == 1


def test_identity_carries_the_seat_configuration() -> None:
    client = OpenAICompatClient(
        "http://localhost:8000/v1", "qwen-test", timeout_s=600.0
    )
    ident = LLMAgent(client, primer="P", masked=True).identity()
    assert ident == {
        "model": "qwen-test",
        "base_url": "http://localhost:8000/v1",
        "timeout_s": 600.0,
        "temperature": 0.0,
        "max_tokens": 512,
        "strikes": 3,
        "primer": True,
        "masked": True,
        "usage_missing": 0,
        "transient_retries": 0,
    }


def test_the_summary_flags_token_stats_invalid_when_usage_is_missing() -> None:
    # The summary reads per-game agent_stats; missing usage blocks in any seat invalidate tokens.
    rows = [
        {
            "kind": "game",
            "deal": 1,
            "a_seat": 0,
            "outcome": "win",
            "score_a": 1.0,
            "pair_void": False,
            "agent_stats": [{"calls": 3, "usage_missing": 2}, {}],
        },
        {
            "kind": "game",
            "deal": 1,
            "a_seat": 1,
            "outcome": "loss",
            "score_a": 0.0,
            "pair_void": False,
            "agent_stats": [{}, {"calls": 4, "usage_missing": 1}],
        },
    ]
    summary = summarize(rows)
    assert summary["token_stats"] == "invalid"
    assert summary["usage_missing"] == 3
    assert (
        summarize([{**r, "agent_stats": [{}, {}]} for r in rows])["token_stats"] == "ok"
    )


# ---------------------------------------------------------- transient 5xx
def test_transient_5xx_retried_then_succeeds(monkeypatch) -> None:
    import io
    import json

    calls = {"n": 0}

    def opener(request, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(
                "http://x", 503, "Service Unavailable", None, None
            )
        body = json.dumps(
            {
                "choices": [{"message": {"content": "ANSWER: 0"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            }
        ).encode()
        return io.BytesIO(body)

    from MTG_bot.bench import llm as llm_mod

    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    client = OpenAICompatClient("http://localhost:1/v1", "m", opener=opener)
    result = client.complete(
        [{"role": "user", "content": "x"}], max_tokens=10, temperature=0.0
    )
    assert calls["n"] == 3 and client.transient_retries == 2
    assert result.text == "ANSWER: 0"


def test_4xx_fail_loud_first_try() -> None:
    calls = {"n": 0}

    def opener(request, timeout):
        calls["n"] += 1
        raise urllib.error.HTTPError("http://x", 400, "Bad Request", None, None)

    client = OpenAICompatClient("http://localhost:1/v1", "m", opener=opener)
    with pytest.raises(AgentInfraError, match="400"):
        client.complete(
            [{"role": "user", "content": "x"}], max_tokens=10, temperature=0.0
        )
    assert calls["n"] == 1 and client.transient_retries == 0
