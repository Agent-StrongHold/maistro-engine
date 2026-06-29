from __future__ import annotations

import random
from typing import Any

import pytest

from maistro_evolve.benchmarks.osworld import (
    _action_from_dict,
    _heuristic_score,
    _judge_os_actions,
    _parse_actions,
    _parse_json_actions,
    _score_action_sequence,
    run_osworld,
)

from .conftest import make_empty_genome, make_genome  # noqa: F401


class TestActionFromDict:
    def test_action_and_target(self) -> None:
        item = {"action": "click", "target": "File menu"}
        assert _action_from_dict(item) == "click:File menu"

    def test_type_only_no_target(self) -> None:
        item = {"type": "press_enter"}
        assert _action_from_dict(item) == "press_enter"

    def test_missing_action_keys_returns_none(self) -> None:
        item = {"foo": "bar"}
        assert _action_from_dict(item) is None


class TestParseJsonActions:
    def test_fenced_json_list_of_dicts(self) -> None:
        response = '```json\n[{"action": "click", "target": "OK"}, {"type": "type"}]\n```'
        result = _parse_json_actions(response)
        assert result == ["click:OK", "type"]

    def test_bare_list_no_fence(self) -> None:
        response = 'Here is the plan: [{"action": "open"}, {"action": "close"}]'
        result = _parse_json_actions(response)
        assert result == ["open", "close"]

    def test_list_of_plain_strings(self) -> None:
        response = '```json\n["open the menu", "click save"]\n```'
        result = _parse_json_actions(response)
        assert result == ["open the menu", "click save"]

    def test_invalid_json_in_fence_falls_through_to_empty(self) -> None:
        response = "```json\n{not valid json at all}\n```"
        result = _parse_json_actions(response)
        assert result == []

    def test_list_with_no_usable_items_returns_empty(self) -> None:
        # ints are neither dict nor str, so the inner loop never appends anything;
        # `actions` stays empty so `if actions: return actions` doesn't fire, and the
        # second pattern (bare list) also matches the same text but yields the same result.
        response = "```json\n[1, 2, 3]\n```"
        result = _parse_json_actions(response)
        assert result == []

    def test_json_parses_but_not_a_list_continues_to_empty(self) -> None:
        response = '```json\n{"action": "click"}\n```'
        result = _parse_json_actions(response)
        assert result == []


class TestParseActions:
    def test_short_circuits_when_json_actions_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "maistro_evolve.benchmarks.osworld._parse_json_actions",
            lambda response: ["json_action_1", "json_action_2"],
        )
        result = _parse_actions("irrelevant text")
        assert result == ["json_action_1", "json_action_2"]

    def test_falls_back_to_regex_pattern_with_two_matches(self) -> None:
        response = "Step 1: open the file manager\nStep 2: click on Documents"
        result = _parse_actions(response)
        assert result == ["open the file manager", "click on Documents"]

    def test_falls_back_to_line_walk_when_no_pattern_matches_enough(self) -> None:
        # No json, no step/numbered/bullet/keyword patterns matching >=2 times.
        # Final fallback strips leading "0123456789.-) " and keeps lines > 3 chars.
        response = "1) click the button\nxy\nsave the document now"
        result = _parse_actions(response)
        assert result == ["click the button", "save the document now"]


class TestScoreActionSequence:
    def test_empty_proposed_returns_zero(self) -> None:
        # response that parses to nothing: blank/short lines only
        assert _score_action_sequence("   \n  \n", ["open_file"]) == 0.0

    def test_empty_expected_actions_recall_defaults_to_one(self) -> None:
        response = "1. open the file manager\n2. click on Documents"
        result = _score_action_sequence(response, [])
        assert result == min(1.0, 1.0)
        assert result == 1.0

    def test_colon_expected_action_and_target_both_found(self) -> None:
        response = "Step 1: navigate_to Documents now\nStep 2: open it"
        expected = ["navigate_to:documents"]
        result = _score_action_sequence(response, expected)
        # matched = 1.0 (action_part "navigate_to" found, target_part "documents" found)
        assert result == min(1.0, 1.0 / 1)
        assert result == 1.0

    def test_colon_expected_action_found_target_not_found(self) -> None:
        response = "Step 1: navigate_to somewhere else\nStep 2: open it"
        expected = ["navigate_to:documents"]
        result = _score_action_sequence(response, expected)
        # action_part "navigate_to" found, target_part "documents" not found -> +0.5
        assert result == min(1.0, 0.5 / 1)
        assert result == 0.5

    def test_colon_expected_neither_found(self) -> None:
        response = "Step 1: click somewhere\nStep 2: open it"
        expected = ["navigate_to:documents"]
        result = _score_action_sequence(response, expected)
        assert result == min(1.0, 0.0 / 1)
        assert result == 0.0

    def test_no_colon_exact_substring_match(self) -> None:
        response = "Step 1: open_file_manager now\nStep 2: do other stuff"
        expected = ["open_file_manager"]
        result = _score_action_sequence(response, expected)
        assert result == min(1.0, 1.0 / 1)
        assert result == 1.0

    def test_no_colon_partial_word_match_via_underscore_split(self) -> None:
        # "open_file_manager" split by "_" -> ["open", "file", "manager"]; response contains "open"
        response = "Step 1: open the thing\nStep 2: do other stuff"
        expected = ["open_file_manager"]
        result = _score_action_sequence(response, expected)
        assert result == min(1.0, 0.4 / 1)
        assert result == 0.4

    def test_no_colon_no_match(self) -> None:
        response = "Step 1: click something\nStep 2: do other stuff"
        expected = ["zzz_totally_unrelated"]
        result = _score_action_sequence(response, expected)
        assert result == min(1.0, 0.0 / 1)
        assert result == 0.0

    def test_mixed_expected_actions_exact_recall_value(self) -> None:
        # Construct expected_actions with known matches:
        # 1. "navigate_to:documents" -> action+target found -> +1.0
        # 2. "open_file_manager" (no colon) -> exact substring found -> +1.0
        # 3. "select_file:report.pdf" -> action found, target not found -> +0.5
        # 4. "zzz_qux_blorp" (no colon) -> partial via "_" split, none of zzz/qux/blorp found -> +0.0
        response = (
            "Step 1: open_file_manager and navigate_to documents folder\n"
            "Step 2: select_file something else entirely"
        )
        expected = [
            "navigate_to:documents",
            "open_file_manager",
            "select_file:report.pdf",
            "zzz_qux_blorp",
        ]
        result = _score_action_sequence(response, expected)
        matched = 1.0 + 1.0 + 0.5 + 0.0
        expected_recall = min(1.0, matched / len(expected))
        assert result == expected_recall
        assert result == 0.625


class TestJudgeOsActions:
    async def test_returns_judge_score_from_llm_response(self) -> None:
        async def fake_llm_call(messages: list[dict[str, Any]], **kwargs: Any) -> str:
            assert "Rate 0-10" in messages[1]["content"]
            return "Score: 8"

        result = await _judge_os_actions(
            "do the task", "Step 1: open\nStep 2: close", ["open", "close"], fake_llm_call
        )
        assert result == 0.8

    async def test_inner_exception_returns_zero(self) -> None:
        async def failing_llm_call(messages: list[dict[str, Any]], **kwargs: Any) -> str:
            raise RuntimeError("boom")

        result = await _judge_os_actions("do the task", "Step 1: open", ["open"], failing_llm_call)
        assert result == 0.0

    async def test_timeout_returns_zero(self) -> None:
        import asyncio as asyncio_module

        async def slow_llm_call(messages: list[dict[str, Any]], **kwargs: Any) -> str:
            raise TimeoutError()

        result = await _judge_os_actions("do the task", "Step 1: open", ["open"], slow_llm_call)
        assert result == 0.0
        # sanity: ensure the module's own asyncio is what's exercised internally
        assert asyncio_module is not None


class TestHeuristicScore:
    def test_base_low_action_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"expected_actions": ["a", "b"]}
        assert _heuristic_score(sample) == 0.6

    def test_base_mid_action_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"expected_actions": ["a", "b", "c"]}
        assert _heuristic_score(sample) == 0.45

    def test_base_high_action_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"expected_actions": ["a", "b", "c", "d"]}
        assert _heuristic_score(sample) == 0.3

    def test_clamp_lower_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: -10.0)
        sample = {"expected_actions": ["a", "b", "c", "d"]}
        assert _heuristic_score(sample) == 0.1

    def test_clamp_upper_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 10.0)
        sample = {"expected_actions": ["a", "b"]}
        assert _heuristic_score(sample) == 0.85


class TestRunOsworld:
    async def test_heuristic_path_when_llm_call_is_none(self, genome: Any) -> None:
        result = await run_osworld(genome, None)
        assert result.benchmark == "osworld"
        assert result.samples_evaluated == 10
        assert result.metadata == {"total_samples": 10, "runner": "real"}
        assert result.cost_usd == 0.0

    async def test_static_score_high_skips_judge(self, genome: Any) -> None:
        call_count = {"n": 0}

        async def fake_llm_call(messages: list[dict[str, Any]], **kwargs: Any) -> str:
            call_count["n"] += 1
            # Craft a response that scores >= 0.6 against any expected_actions:
            # join all colon-targets and bare actions generically by emitting a
            # generic high-coverage action listing using the task text itself
            # is unreliable; instead exploit the recall formula: if proposed_text
            # contains every "action" and "target" substring from the dataset
            # samples, score across all of them will be high. We just need >=0.6
            # for THIS sample's expected_actions, since run_osworld evaluates one
            # sample per call.
            return (
                "Step 1: open_file_manager Documents Desktop Projects open_settings "
                "navigate_to wallpaper select_category nature open_terminal "
                "create_folder Projects "
                "run_command sudo apt install python3 navigate_to Downloads "
                "select_file report.pdf copy paste open_browser "
                "type_in_search_bar climate change statistics press_enter "
                "open_network_settings select_wifi HomeNetwork enter_password "
                "press_key print_screen save_to Pictures unzip archive.zip "
                "open_volume_control set_volume 50"
            )

        result = await run_osworld(genome, fake_llm_call)
        assert call_count["n"] == 10
        assert result.samples_evaluated == 10
        # only the 0.001/sample cost should accrue, no 0.0005 judge cost
        assert result.cost_usd == round(0.001 * 10, 4)

    async def test_static_score_low_triggers_judge_and_extra_cost(self, genome: Any) -> None:
        async def fake_llm_call(messages: list[dict[str, Any]], **kwargs: Any) -> str:
            content = messages[-1]["content"]
            if "Does the proposed sequence" in content or "Rate 0-10" in content:
                return "Score: 9"
            # Deliberately irrelevant action text -> static score will be low (0.0)
            return "Step 1: do something totally unrelated\nStep 2: another irrelevant step"

        result = await run_osworld(genome, fake_llm_call)
        assert result.samples_evaluated == 10
        # cost: 0.001 per sample (always) + 0.0005 per sample (judge always triggered, since
        # static score for fully irrelevant text is 0.0 < 0.6 for every sample)
        assert result.cost_usd == round((0.001 + 0.0005) * 10, 4)
        # judge score of 0.9 wins over static 0.0 for every sample
        assert result.score == 0.9

    async def test_timeout_exception_path_increments_evaluated_no_score(self, genome: Any) -> None:
        async def raising_llm_call(messages: list[dict[str, Any]], **kwargs: Any) -> str:
            raise TimeoutError()

        result = await run_osworld(genome, raising_llm_call)
        assert result.samples_evaluated == 10
        assert result.score == 0.0
        assert result.cost_usd == 0.0

    async def test_empty_genome_falls_back_to_default_prompt(self, empty_genome: Any) -> None:
        result = await run_osworld(empty_genome, None)
        assert result.benchmark == "osworld"
        assert result.samples_evaluated == 10
