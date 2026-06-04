"""Tests pinning the Literal return contracts of complexity helpers.

These helpers feed directly into ``Intent.complexity`` and ``Intent.tier``,
which are typed as Literals. The functions must return values drawn from
exactly those Literal alphabets so the classifier can assign them without an
unsound ``# type: ignore[arg-type]``.
"""

from __future__ import annotations

import typing
from typing import Literal, assert_type

from maistro.classifier.complexity import estimate_complexity, infer_priority
from maistro.types.intent import Intent

# The valid alphabets, taken from the Intent dataclass field annotations.
_COMPLEXITY_VALUES = set(typing.get_args(typing.get_type_hints(Intent)["complexity"]))
_PRIORITY_VALUES = set(typing.get_args(typing.get_type_hints(Intent)["tier"]))


class TestEstimateComplexityContract:
    def test_short_text_is_simple(self) -> None:
        assert estimate_complexity("hi", "chat") == "simple"

    def test_long_text_is_complex(self) -> None:
        assert estimate_complexity("word " * 250, "chat") == "complex"

    def test_complex_signals_bump_to_complex(self) -> None:
        text = (
            "Please refactor and optimize the module and also compare the "
            "trade-offs between the two approaches in a thorough comprehensive "
            "way across several files and functions and components here now"
        )
        assert estimate_complexity(text, "code") == "complex"

    def test_return_value_is_always_a_valid_literal(self) -> None:
        samples = [
            ("hi", "chat"),
            ("word " * 250, "chat"),
            ("word " * 90, "chat"),
            ("write me a function", "code"),
            ("just a normal sentence with some length to it here ok", "chat"),
        ]
        for text, task in samples:
            assert estimate_complexity(text, task) in _COMPLEXITY_VALUES

    def test_static_return_type_is_the_complexity_literal(self) -> None:
        # mypy --strict must see the narrowed Literal, not bare ``str``.
        assert_type(
            estimate_complexity("hi", "chat"),
            Literal["simple", "moderate", "complex"],
        )


class TestAutomationMinTier:
    def test_short_command_returns_base_tier(self) -> None:
        from maistro.classifier.complexity import automation_min_tier

        assert automation_min_tier("turn on lights", "small") == "small"

    def test_short_with_filler_words(self) -> None:
        from maistro.classifier.complexity import automation_min_tier

        assert automation_min_tier("please turn on the lights", "small") == "small"

    def test_long_command_upgrades_small_to_medium(self) -> None:
        from maistro.classifier.complexity import automation_min_tier

        result = automation_min_tier(
            "turn on the kitchen lights and set the thermostat to seventy two degrees",
            "small",
        )
        assert result == "medium"

    def test_long_command_keeps_large(self) -> None:
        from maistro.classifier.complexity import automation_min_tier

        result = automation_min_tier(
            "turn on the kitchen lights and set the thermostat to seventy two degrees",
            "large",
        )
        assert result == "large"

    def test_long_command_keeps_medium(self) -> None:
        from maistro.classifier.complexity import automation_min_tier

        result = automation_min_tier(
            "turn on the kitchen lights and set the thermostat to seventy two degrees",
            "medium",
        )
        assert result == "medium"

    def test_exactly_three_meaningful_words(self) -> None:
        from maistro.classifier.complexity import automation_min_tier

        assert automation_min_tier("turn on lights", "small") == "small"

    def test_four_meaningful_words_upgrades(self) -> None:
        from maistro.classifier.complexity import automation_min_tier

        result = automation_min_tier("turn on kitchen lights", "small")
        assert result == "medium"

    def test_filler_words_filtered(self) -> None:
        from maistro.classifier.complexity import automation_min_tier

        result = automation_min_tier("can you please just turn on the lights ok", "small")
        assert result == "small"

    def test_unknown_base_tier_treated_as_zero(self) -> None:
        from maistro.classifier.complexity import automation_min_tier

        result = automation_min_tier(
            "turn on the kitchen lights and set thermostat high and lock the door",
            "nonexistent",
        )
        assert result == "medium"


class TestEstimateComplexityBoundary:
    def test_14_words_is_simple(self) -> None:
        text = " ".join(["word"] * 14)
        assert estimate_complexity(text, "chat") == "simple"

    def test_15_words_not_simple_without_signals(self) -> None:
        text = " ".join(["word"] * 15)
        result = estimate_complexity(text, "chat")
        assert result == "simple"

    def test_15_words_code_is_moderate(self) -> None:
        text = " ".join(["word"] * 15)
        result = estimate_complexity(text, "code")
        assert result == "moderate"

    def test_200_words_is_complex(self) -> None:
        text = " ".join(["word"] * 201)
        assert estimate_complexity(text, "chat") == "complex"

    def test_80_words_moderate_without_signals(self) -> None:
        text = " ".join(["word"] * 81)
        assert estimate_complexity(text, "chat") == "moderate"

    def test_code_task_type_bumps_to_moderate(self) -> None:
        text = " ".join(["word"] * 20)
        assert estimate_complexity(text, "code") == "moderate"

    def test_reasoning_task_type_bumps_to_moderate(self) -> None:
        text = " ".join(["word"] * 20)
        assert estimate_complexity(text, "reasoning") == "moderate"


class TestInferPriorityCoverage:
    def test_critical_keyword(self) -> None:
        assert infer_priority("this is a critical issue") == "P0"

    def test_emergency_keyword(self) -> None:
        assert infer_priority("emergency server down") == "P0"

    def test_asap_keyword(self) -> None:
        assert infer_priority("need this asap") == "P0"

    def test_down_keyword(self) -> None:
        assert infer_priority("system is down") == "P0"

    def test_deadline_keyword(self) -> None:
        assert infer_priority("deadline is tomorrow") == "P1"

    def test_demo_keyword(self) -> None:
        assert infer_priority("demo is today") == "P1"

    def test_client_keyword(self) -> None:
        assert infer_priority("client is waiting") == "P1"

    def test_just_curious_keyword(self) -> None:
        assert infer_priority("just curious about this") == "P4"

    def test_when_you_get_a_chance(self) -> None:
        assert infer_priority("fix this when you get a chance") == "P4"

    def test_fyi_keyword(self) -> None:
        assert infer_priority("fyi the report is done") == "P4"


class TestInferPriorityContract:
    def test_urgent_is_p0(self) -> None:
        assert infer_priority("this is urgent and broken") == "P0"

    def test_important_is_p1(self) -> None:
        assert infer_priority("important client deadline") == "P1"

    def test_low_urgency_is_p4(self) -> None:
        assert infer_priority("no rush, just curious") == "P4"

    def test_default_is_p2(self) -> None:
        assert infer_priority("what is the weather") == "P2"

    def test_return_value_is_always_a_valid_literal(self) -> None:
        for text in ["urgent", "important", "no rush", "hello", ""]:
            assert infer_priority(text) in _PRIORITY_VALUES

    def test_static_return_type_is_the_priority_literal(self) -> None:
        # mypy --strict must see the narrowed Literal, not bare ``str``.
        assert_type(
            infer_priority("hello"),
            Literal["P0", "P1", "P2", "P3", "P4", "P5"],
        )
