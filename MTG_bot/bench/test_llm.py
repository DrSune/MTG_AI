"""The LLM seat, with no network: scripted replies and a fake HTTP opener."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from MTG_bot.bench.agents import PassAgent
from MTG_bot.bench.duel import DealSpec, run_match, summarize
from MTG_bot.bench.llm import (
    AgentInfraError,
    LLMAgent,
    OpenAICompatClient,
    ScriptedClient,
    parse_answer,
)
from MTG_bot.bench.protocol import Ask, Option

ASK = Ask(seat=0, kind="attack", site="attack:card:1:3", prompt="Attack?",
          options=(Option("ATTACK", "attack"), Option("DECLINE", "do not attack")), refuse=1)


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
        reply = {"choices": [{"message": {"content": "ANSWER: 1"}}], "usage": {"prompt_tokens": 42, "completion_tokens": 3}}
        return io.BytesIO(json.dumps(reply).encode())

    result = OpenAICompatClient("http://localhost:8000/v1", "qwen", opener=opener).complete(
        [{"role": "user", "content": "hi"}], max_tokens=8, temperature=0.0
    )
    assert sent["url"] == "http://localhost:8000/v1/chat/completions"
    assert sent["body"]["model"] == "qwen" and sent["body"]["max_tokens"] == 8
    assert (result.text, result.prompt_tokens, result.completion_tokens) == ("ANSWER: 1", 42, 3)


def test_a_transport_failure_is_an_infra_error() -> None:
    def opener(request, timeout):
        raise urllib.error.URLError("connection refused")

    with pytest.raises(AgentInfraError):
        OpenAICompatClient("http://localhost:1/v1", "m", opener=opener).complete([], max_tokens=1, temperature=0)


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
