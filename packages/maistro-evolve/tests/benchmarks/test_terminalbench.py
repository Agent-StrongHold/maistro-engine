from __future__ import annotations

import random
from typing import Any

import pytest

from maistro_evolve.benchmarks.terminalbench import (
    _alt_score,
    _commands_from_code_blocks,
    _commands_from_lines,
    _heuristic_score,
    _judge_command,
    _score_command,
    run_terminalbench,
)

from .conftest import make_genome


class TestCommandsFromCodeBlocks:
    def test_extracts_non_comment_lines_from_bash_fence(self):
        response = "```bash\n# a comment\nls -la\n\ngrep foo bar.txt\n```"
        assert _commands_from_code_blocks(response) == ["ls -la", "grep foo bar.txt"]

    def test_no_fence_returns_empty_list(self):
        assert _commands_from_code_blocks("just plain text, no fences here") == []

    def test_plain_fence_without_language_tag_still_matches(self):
        response = "```\ncat file.txt\n```"
        assert _commands_from_code_blocks(response) == ["cat file.txt"]


class TestCommandsFromLines:
    def test_dollar_and_gt_prefixed_lines_stripped(self):
        response = "$ ls -la\n> docker ps\n"
        assert _commands_from_lines(response) == ["ls -la", "docker ps"]

    def test_hint_lines_included_without_prefix(self):
        response = "please grep the logs\nnothing useful here\nrun docker compose up"
        result = _commands_from_lines(response)
        assert result == ["please grep the logs", "run docker compose up"]

    def test_lines_without_prefix_or_hint_excluded(self):
        response = "no hints here\nstill nothing"
        assert _commands_from_lines(response) == []

    def test_empty_lines_skipped(self):
        response = "$ ls\n\n> docker ps"
        assert _commands_from_lines(response) == ["ls", "docker ps"]


class TestAltScore:
    def test_full_match_short_circuits_to_one(self):
        alternatives = ["kill $(lsof -ti:8080)", "fuser -k 8080/tcp"]
        all_text = "some text containing kill $(lsof -ti:8080) right here"
        assert _alt_score(alternatives, all_text) == 1.0

    def test_partial_overlap_computes_exact_fraction_and_takes_max(self):
        # alt1: 1/3 parts found, alt2: 2/3 parts found -> max should be alt2's score
        alternatives = ["aaa bbb ccc", "xxx yyy zzz"]
        all_text = "aaa zzz yyy"  # alt1: only 'aaa' found (1/3); alt2: 'yyy','zzz' found (2/3)
        result = _alt_score(alternatives, all_text)
        assert result == pytest.approx(2 / 3)

    def test_empty_string_alternative_short_circuits_via_substring_match(self):
        # "" is trivially `in` any string, so the full-match branch returns 1.0
        # immediately without ever reaching the `if alt_parts else 0.0` guard.
        alternatives = [""]
        all_text = "anything at all"
        assert _alt_score(alternatives, all_text) == 1.0

    def test_whitespace_only_alternative_exercises_empty_parts_guard(self):
        # "   ".split() == [] (no substring match since all_text has no triple-space),
        # so alt_parts is genuinely empty and the `if alt_parts else 0.0` guard fires,
        # contributing 0.0 without raising ZeroDivisionError.
        alternatives = ["   "]
        all_text = "no triple space in here"
        assert _alt_score(alternatives, all_text) == 0.0

    def test_partial_overlap_beats_whitespace_only_alternative_via_max(self):
        alternatives = ["   ", "foo bar"]
        all_text = "foo something"
        result = _alt_score(alternatives, all_text)
        assert result == pytest.approx(0.5)


class TestScoreCommand:
    def _sample(self, **kwargs: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "task": "t",
            "expected_command_keywords": [],
            "accept_alternatives": [],
        }
        base.update(kwargs)
        return base

    def test_no_commands_extracted_returns_zero(self):
        sample = self._sample(expected_command_keywords=["grep"])
        # response has no fence and no command hints/$/> prefixes
        assert _score_command("nothing useful at all", sample) == 0.0

    def test_keyword_score_greater_than_alt_score_returns_max_keyword(self):
        # keyword_score will be 1.0 (both keywords found), alt_score partial/lower
        sample = self._sample(
            expected_command_keywords=["grep", "todo"],
            accept_alternatives=["zzz yyy"],
        )
        response = "```bash\ngrep -r TODO .\n```"
        score = _score_command(response, sample)
        assert score == 1.0

    def test_alt_score_greater_than_keyword_score_returns_max_alt(self):
        # keyword_score partial (1/2), alt_score full match (1.0)
        sample = self._sample(
            expected_command_keywords=["grep", "nonexistentkeyword"],
            accept_alternatives=["rg todo --type py"],
        )
        response = "```bash\nrg todo --type py\n```"
        score = _score_command(response, sample)
        assert score == 1.0

    def test_keyword_positive_alt_zero_due_to_no_alternatives_short_circuits(self):
        sample = self._sample(expected_command_keywords=["grep"], accept_alternatives=[])
        response = "```bash\ngrep foo\n```"
        score = _score_command(response, sample)
        assert score == 1.0

    def test_keyword_zero_alt_positive_returns_alt_score(self):
        sample = self._sample(
            expected_command_keywords=["nonexistentkw"],
            accept_alternatives=["docker ps -a"],
        )
        response = "```bash\ndocker ps -a\n```"
        score = _score_command(response, sample)
        assert score == 1.0

    def test_both_zero_returns_zero(self):
        sample = self._sample(
            expected_command_keywords=["nonexistentkw"],
            accept_alternatives=["totally unrelated phrase"],
        )
        response = "```bash\nls -la\n```"
        score = _score_command(response, sample)
        assert score == 0.0

    def test_empty_expected_keywords_keeps_keyword_score_zero(self):
        # expected_command_keywords falsy -> keyword_score stays 0.0; alt covers the score
        sample = self._sample(expected_command_keywords=[], accept_alternatives=["ls -la"])
        response = "```bash\nls -la\n```"
        score = _score_command(response, sample)
        assert score == 1.0


class TestJudgeCommand:
    @pytest.mark.asyncio
    async def test_returns_judge_score_from_llm_response(self):
        captured: list[list[dict[str, str]]] = []

        async def fake_llm(messages, **kwargs):
            captured.append(messages)
            return "score: 8"

        result = await _judge_command("do the thing", "```bash\nls\n```", ["ls -la"], fake_llm)
        assert result == pytest.approx(0.8)
        # verify prompt content reflects non-empty alternatives capped/joined
        prompt = captured[0][1]["content"]
        assert "Reference commands: ls -la" in prompt
        assert "Linux command expert" in captured[0][0]["content"]
        assert "Rate 0-10" in prompt

    @pytest.mark.asyncio
    async def test_empty_alternatives_produces_na_reference_text(self):
        captured: list[list[dict[str, str]]] = []

        async def fake_llm(messages, **kwargs):
            captured.append(messages)
            return "score: 5"

        await _judge_command("do the thing", "ls -la", [], fake_llm)
        prompt = captured[0][1]["content"]
        assert "Reference commands: N/A" in prompt

    @pytest.mark.asyncio
    async def test_alternatives_capped_at_first_three_joined_with_or(self):
        captured: list[list[dict[str, str]]] = []

        async def fake_llm(messages, **kwargs):
            captured.append(messages)
            return "score: 5"

        alts = ["one", "two", "three", "four"]
        await _judge_command("task", "resp", alts, fake_llm)
        prompt = captured[0][1]["content"]
        assert "Reference commands: one or two or three" in prompt
        assert "four" not in prompt

    @pytest.mark.asyncio
    async def test_exception_in_llm_call_returns_zero(self):
        async def failing_llm(messages, **kwargs):
            raise RuntimeError("boom")

        result = await _judge_command("task", "resp", ["ls"], failing_llm)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_uses_code_block_as_proposed_command_when_present(self):
        captured: list[list[dict[str, str]]] = []

        async def fake_llm(messages, **kwargs):
            captured.append(messages)
            return "score: 5"

        response = "preamble text\n```bash\nls -la\n```\ntrailer text"
        await _judge_command("task", response, [], fake_llm)
        prompt = captured[0][1]["content"]
        assert "Proposed command(s):\nls -la" in prompt

    @pytest.mark.asyncio
    async def test_uses_truncated_response_when_no_code_block(self):
        captured: list[list[dict[str, str]]] = []

        async def fake_llm(messages, **kwargs):
            captured.append(messages)
            return "score: 5"

        response = "x" * 500
        await _judge_command("task", response, [], fake_llm)
        prompt = captured[0][1]["content"]
        assert ("x" * 300) in prompt
        assert ("x" * 301) not in prompt


class TestHeuristicScore:
    def test_few_keywords_uses_low_base_with_zero_jitter_clamped(self, monkeypatch):
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"expected_command_keywords": ["a", "b", "c"]}
        assert _heuristic_score(sample) == pytest.approx(0.55)

    def test_mid_keywords_uses_mid_base(self, monkeypatch):
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"expected_command_keywords": ["a", "b", "c", "d"]}
        assert _heuristic_score(sample) == pytest.approx(0.4)

    def test_many_keywords_uses_lowest_base(self, monkeypatch):
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"expected_command_keywords": ["a", "b", "c", "d", "e", "f"]}
        assert _heuristic_score(sample) == pytest.approx(0.3)

    def test_clamped_to_upper_bound(self, monkeypatch):
        monkeypatch.setattr(random, "uniform", lambda a, b: 10.0)
        sample = {"expected_command_keywords": ["a"]}
        assert _heuristic_score(sample) == pytest.approx(0.85)

    def test_clamped_to_lower_bound(self, monkeypatch):
        monkeypatch.setattr(random, "uniform", lambda a, b: -10.0)
        sample = {"expected_command_keywords": ["a", "b", "c", "d", "e", "f"]}
        assert _heuristic_score(sample) == pytest.approx(0.1)


class TestRunTerminalbench:
    @pytest.mark.asyncio
    async def test_heuristic_path_when_llm_call_none(self):
        genome = make_genome()
        result = await run_terminalbench(genome, None)
        assert result.benchmark == "terminalbench"
        assert result.samples_evaluated == 12
        assert result.metadata == {"total_samples": 12, "runner": "real"}
        assert result.cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_static_score_above_threshold_skips_judge_and_costs_per_sample(self):
        from maistro_evolve.benchmarks.datasets import TERMINALBENCH_SAMPLES

        # Build a response per call that exactly echoes that sample's first
        # accept_alternatives entry, guaranteeing a full alt-score match (1.0 >= 0.6)
        # so the judge branch is never taken.
        call_index = {"i": 0}

        async def fake_llm(messages, **kwargs):
            idx = call_index["i"]
            call_index["i"] += 1
            alt = TERMINALBENCH_SAMPLES[idx]["accept_alternatives"][0]
            return f"```bash\n{alt}\n```"

        genome = make_genome()
        result = await run_terminalbench(genome, fake_llm)
        assert result.samples_evaluated == 12
        # cost should be a multiple of 0.001 with no judge calls (0.0005 increments)
        assert result.cost_usd == pytest.approx(round(0.001 * 12, 4))
        assert result.score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_low_static_score_triggers_judge_and_extra_cost(self):
        call_log: list[str] = []

        async def fake_llm(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            if "Linux command expert" in content:
                call_log.append("judge")
                return "score: 7"
            call_log.append("main")
            # response with no commands at all -> static score 0.0, forces judge path
            return "I am not sure how to do this."

        genome = make_genome()
        result = await run_terminalbench(genome, fake_llm)
        assert result.samples_evaluated == 12
        assert call_log.count("judge") == 12
        # each sample: 0.001 (main) + 0.0005 (judge) = 0.0015
        assert result.cost_usd == pytest.approx(round(0.0015 * 12, 4))
        # all samples scored via judge: score 0.7 each (since static=0.0, judged=0.7 -> max=0.7)
        assert result.score == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_exception_path_increments_evaluated_without_score(self):
        async def failing_llm(messages, **kwargs):
            raise RuntimeError("network down")

        genome = make_genome()
        result = await run_terminalbench(genome, failing_llm)
        assert result.samples_evaluated == 12
        assert result.score == 0.0
        assert result.cost_usd == 0.0
