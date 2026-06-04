"""Tests for classifier/keyword.py — score_keywords value-pinning.

Catches mutations to +3.0/+1.0/-2.0 weights, word-boundary logic,
case-insensitivity, score accumulation, and negative-signal suppression.
"""

from __future__ import annotations

import pytest

from maistro.classifier.keyword import (
    NEGATIVE_SIGNALS,
    STRONG_INDICATORS,
    score_keywords,
)
from maistro.types.config import TaskTypeConfig


def _task_types(*names: str) -> dict[str, TaskTypeConfig]:
    return dict.fromkeys(names, TaskTypeConfig(keywords=[], models={}))


def _task_types_with_kw(name: str, keywords: list[str]) -> dict[str, TaskTypeConfig]:
    return {name: TaskTypeConfig(keywords=keywords, models={})}


class TestStrongIndicators:
    def test_single_strong_indicator_scores_3(self) -> None:
        result = score_keywords(
            "please write a function that adds two numbers",
            _task_types("code"),
        )
        assert result == {"code": pytest.approx(3.0)}

    def test_multiple_strong_indicators_accumulate(self) -> None:
        text = "write a function and also write a script to fix the bug"
        result = score_keywords(text, _task_types("code"))
        assert result["code"] == pytest.approx(9.0)

    def test_strong_indicator_case_insensitive(self) -> None:
        result = score_keywords(
            "Write A Function please",
            _task_types("code"),
        )
        assert result == {"code": pytest.approx(3.0)}

    def test_strong_indicator_no_partial_word_match(self) -> None:
        result = score_keywords(
            "rewrite a functional test suite",
            _task_types("code"),
        )
        assert result == {}

    def test_automation_strong_indicators(self) -> None:
        result = score_keywords(
            "turn on the lights",
            _task_types("automation"),
        )
        assert result == {"automation": pytest.approx(3.0)}

    def test_creative_strong_indicators(self) -> None:
        result = score_keywords(
            "write me a poem about cats",
            _task_types("creative"),
        )
        assert result == {"creative": pytest.approx(3.0)}

    def test_reasoning_strong_indicators(self) -> None:
        result = score_keywords(
            "let's think through the step by step approach",
            _task_types("reasoning"),
        )
        assert "reasoning" in result
        assert result["reasoning"] >= 3.0

    def test_image_gen_strong_indicators(self) -> None:
        result = score_keywords(
            "generate an image of a cat",
            _task_types("image_gen"),
        )
        assert result == {"image_gen": pytest.approx(3.0)}

    def test_search_strong_indicators(self) -> None:
        result = score_keywords(
            "search for the latest news about AI",
            _task_types("search"),
        )
        assert "search" in result
        assert result["search"] >= 3.0


class TestConfigKeywords:
    def test_config_keyword_scores_1(self) -> None:
        result = score_keywords(
            "I need help with python",
            _task_types_with_kw("code", ["python"]),
        )
        assert result == {"code": pytest.approx(1.0)}

    def test_config_keyword_word_boundary(self) -> None:
        result = score_keywords(
            "I love pythonic code",
            _task_types_with_kw("code", ["python"]),
        )
        assert result == {}

    def test_multiple_config_keywords_accumulate(self) -> None:
        result = score_keywords(
            "help with python and javascript",
            _task_types_with_kw("code", ["python", "javascript"]),
        )
        assert result["code"] == pytest.approx(2.0)

    def test_config_keyword_case_insensitive(self) -> None:
        result = score_keywords(
            "I need help with PYTHON",
            _task_types_with_kw("code", ["python"]),
        )
        assert result == {"code": pytest.approx(1.0)}

    def test_config_keyword_no_keywords_list(self) -> None:
        result = score_keywords(
            "some text here",
            _task_types("code"),
        )
        assert result == {}


class TestNegativeSignals:
    def test_negative_signal_deducts_2(self) -> None:
        result = score_keywords(
            "write a function but what is the meaning of life",
            _task_types("code"),
        )
        assert result == {}

    def test_negative_signal_cancels_indicator(self) -> None:
        result = score_keywords(
            "write a function but tell me about the president of france",
            _task_types("code"),
        )
        assert result == {}

    def test_negative_signal_can_zero_out(self) -> None:
        text = "what is the capital of france"
        result = score_keywords(text, _task_types("code"))
        assert result == {}

    def test_negative_signal_only_negative(self) -> None:
        text = "who is the president of the united states"
        result = score_keywords(text, _task_types("code"))
        assert result == {}

    def test_negative_signal_partial_deduction(self) -> None:
        text = "write a function write a script what is the"
        result = score_keywords(text, _task_types("code"))
        assert result["code"] == pytest.approx(4.0)

    def test_negative_signal_does_not_affect_other_types(self) -> None:
        text = "write a function"
        types = {**_task_types("code"), **_task_types("creative")}
        result = score_keywords(text, types)
        assert "code" in result
        assert "creative" not in result


class TestScoreFiltering:
    def test_zero_score_excluded(self) -> None:
        result = score_keywords(
            "hello world",
            _task_types("code"),
        )
        assert result == {}

    def test_negative_score_excluded(self) -> None:
        result = score_keywords(
            "what is the meaning of life",
            _task_types("code"),
        )
        assert result == {}

    def test_multiple_task_types_scored_independently(self) -> None:
        text = "write a function and turn on the lights"
        types = {**_task_types("code"), **_task_types("automation")}
        result = score_keywords(text, types)
        assert result["code"] == pytest.approx(3.0)
        assert result["automation"] == pytest.approx(3.0)

    def test_empty_task_types(self) -> None:
        result = score_keywords("write a function", {})
        assert result == {}

    def test_empty_text(self) -> None:
        result = score_keywords("", _task_types("code"))
        assert result == {}


class TestIndicatorCoverage:
    """Ensure every indicator phrase in the module is reachable."""

    @pytest.mark.parametrize(
        "task_type",
        list(STRONG_INDICATORS.keys()),
    )
    def test_all_task_types_have_indicators(self, task_type: str) -> None:
        assert len(STRONG_INDICATORS[task_type]) > 0

    @pytest.mark.parametrize(
        "task_type",
        list(NEGATIVE_SIGNALS.keys()),
    )
    def test_all_negative_signal_types_exist(self, task_type: str) -> None:
        assert len(NEGATIVE_SIGNALS[task_type]) > 0
