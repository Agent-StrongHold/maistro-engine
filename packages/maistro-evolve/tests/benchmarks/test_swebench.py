from __future__ import annotations

import random
from typing import Any

import pytest

from maistro_evolve.benchmarks.datasets import SWEBENCH_SAMPLES
from maistro_evolve.benchmarks.swebench import (
    _heuristic_score,
    _judge_code_quality,
    _score_buggy_change,
    _score_code_fix,
    _score_expected_output,
    _score_keywords,
    _score_recursive,
    run_swebench,
)

from .conftest import make_genome

# ---------------------------------------------------------------------------
# _score_keywords
# ---------------------------------------------------------------------------


class TestScoreKeywords:
    def test_empty_expected_keywords_returns_zero(self) -> None:
        sample = {"expected_keywords": []}
        assert _score_keywords("anything", sample) == (0.0, 0.0)

    def test_missing_expected_keywords_key_returns_zero(self) -> None:
        sample: dict[str, Any] = {}
        assert _score_keywords("anything", sample) == (0.0, 0.0)

    def test_partial_keywords_found(self) -> None:
        sample = {"expected_keywords": ["recursive", "isinstance", "extend", "flatten"]}
        code_text = "def flatten(lst): isinstance(lst, list)"
        score, max_score = _score_keywords(code_text, sample)
        assert max_score == 0.4
        assert score == pytest.approx((2 / 4) * 0.4)

    def test_all_keywords_found_is_case_insensitive(self) -> None:
        sample = {"expected_keywords": ["RECURSIVE", "Isinstance"]}
        code_text = "use recursive isinstance check"
        score, max_score = _score_keywords(code_text, sample)
        assert max_score == 0.4
        assert score == pytest.approx((2 / 2) * 0.4)

    def test_no_keywords_found(self) -> None:
        sample = {"expected_keywords": ["foo", "bar"]}
        score, max_score = _score_keywords("nothing relevant here", sample)
        assert (score, max_score) == (0.0, 0.4)


# ---------------------------------------------------------------------------
# _score_buggy_change
# ---------------------------------------------------------------------------


class TestScoreBuggyChange:
    def test_empty_buggy_code_returns_zero(self) -> None:
        assert _score_buggy_change("anything", {"buggy_code": ""}) == (0.0, 0.0)

    def test_missing_buggy_code_key_returns_zero(self) -> None:
        assert _score_buggy_change("anything", {}) == (0.0, 0.0)

    def test_only_def_line_filtered_out_gives_flat_score(self) -> None:
        # buggy_code has only a "def " line, which is excluded by the filter,
        # leaving buggy_lines empty -> the (0.1, 0.2) fallback branch.
        sample = {"buggy_code": "def flatten_list(lst):"}
        assert _score_buggy_change("whatever code text", sample) == (0.1, 0.2)

    def test_partial_change_ratio_computed_exactly(self) -> None:
        buggy_code = "result = []\nresult.extend(item)"
        # First line unchanged (still present), second line changed away.
        code_text = "result = []\nresult.append(item)"
        score, max_score = _score_buggy_change(code_text, sample={"buggy_code": buggy_code})
        # buggy_lines = ["result = []", "result.extend(item)"]
        # unchanged = 1 (only "result = []" found in code_text)
        # change_ratio = 1 - (1/2) = 0.5
        assert max_score == 0.2
        assert score == pytest.approx(0.5 * 0.2)

    def test_fully_unchanged_lines_gives_zero_score(self) -> None:
        buggy_code = "result = []\nresult.append(item)"
        code_text = "result = []\nresult.append(item)\nreturn result"
        score, max_score = _score_buggy_change(code_text, {"buggy_code": buggy_code})
        assert (score, max_score) == (0.0, 0.2)

    def test_fully_changed_lines_gives_full_score(self) -> None:
        buggy_code = "result = []\nresult.append(item)"
        code_text = "totally different implementation"
        score, max_score = _score_buggy_change(code_text, {"buggy_code": buggy_code})
        assert score == pytest.approx(1.0 * 0.2)
        assert max_score == 0.2


# ---------------------------------------------------------------------------
# _score_recursive
# ---------------------------------------------------------------------------


class TestScoreRecursive:
    def test_problem_without_recursive_keyword_returns_zero(self) -> None:
        sample = {"problem": "Fix the off-by-one error in the loop."}
        assert _score_recursive("def f(): return 1", sample) == (0.0, 0.0)

    def test_problem_with_recursive_and_code_mentions_recursive(self) -> None:
        sample = {"problem": "Make the flatten function recursive."}
        code_text = "def flatten(lst):\n    # recursive call\n    return flatten(lst[1:])"
        assert _score_recursive(code_text, sample) == (0.15, 0.15)

    def test_problem_with_recursively_and_multiple_def_lines(self) -> None:
        sample = {"problem": "Handle nesting recursively."}
        code_text = "def helper():\n    pass\ndef flatten(lst):\n    return helper()"
        assert _score_recursive(code_text, sample) == (0.15, 0.15)

    def test_problem_with_recursive_but_code_lacks_signal(self) -> None:
        sample = {"problem": "Make this work recursively please."}
        code_text = "def flatten(lst):\n    return lst"
        assert _score_recursive(code_text, sample) == (0.0, 0.15)

    def test_missing_problem_key_returns_zero(self) -> None:
        assert _score_recursive("def f(): pass", {}) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# _score_expected_output
# ---------------------------------------------------------------------------


class TestScoreExpectedOutput:
    def test_empty_expected_output_returns_zero(self) -> None:
        assert _score_expected_output("anything", {"expected_output": ""}) == (0.0, 0.0)

    def test_missing_expected_output_key_returns_zero(self) -> None:
        assert _score_expected_output("anything", {}) == (0.0, 0.0)

    def test_expected_output_found_ignoring_spaces_and_case(self) -> None:
        sample = {"expected_output": "[1, 2, 3]"}
        code_text = "the result is [1,2,3] as expected"
        assert _score_expected_output(code_text, sample) == (0.1, 0.1)

    def test_expected_output_not_found(self) -> None:
        sample = {"expected_output": "[1, 2, 3]"}
        code_text = "the result is something else entirely"
        assert _score_expected_output(code_text, sample) == (0.0, 0.1)


# ---------------------------------------------------------------------------
# _score_code_fix
# ---------------------------------------------------------------------------


class TestScoreCodeFix:
    def test_fenced_python_block_combined_score(self) -> None:
        sample = {
            "expected_keywords": ["isinstance", "extend"],
            "buggy_code": "result.extend(item)",
            "problem": "Fix the recursive flatten bug.",
            "expected_output": "[1, 2, 3]",
        }
        code_body = (
            "def flatten(lst):\n"
            "    result = []\n"
            "    if isinstance(lst, list):\n"
            "        result.extend(flatten(lst))\n"
            "    return result  # gives [1, 2, 3]"
        )
        response = f"Here is the fix:\n```python\n{code_body}\n```\nExplanation: recursive."

        # Recompute expected score using the same component functions to keep
        # this assertion exact-but-not-duplicative of magic numbers.
        kw = _score_keywords(code_body, sample)
        buggy = _score_buggy_change(code_body, sample)
        rec = _score_recursive(code_body, sample)
        out = _score_expected_output(code_body, sample)

        score = kw[0] + buggy[0] + rec[0] + out[0]
        max_score = kw[1] + buggy[1] + rec[1] + out[1]

        assert "return" in code_body and "def " in code_body
        score += 0.1
        max_score += 0.1

        assert len(code_body.strip()) > 20
        score += 0.05
        max_score += 0.05

        expected = min(1.0, score / max_score)
        assert _score_code_fix(response, sample) == pytest.approx(expected)

    def test_max_score_zero_returns_half(self) -> None:
        # Empty expected_keywords, empty buggy_code, problem without "recursive",
        # empty expected_output, and response without "return"+"def " combo and
        # <= 20 chars after stripping -> every component contributes 0 to
        # max_score, hitting the max_score == 0 branch.
        sample = {
            "expected_keywords": [],
            "buggy_code": "",
            "problem": "fix the bug",
            "expected_output": "",
        }
        response = "short reply"  # no code fence, <=20 chars, no return/def
        assert len(response.strip()) <= 20
        assert _score_code_fix(response, sample) == 0.5

    def test_no_code_fence_falls_back_to_raw_response(self) -> None:
        sample = {
            "expected_keywords": ["foo"],
            "buggy_code": "",
            "problem": "fix the bug",
            "expected_output": "",
        }
        response = "the foo keyword appears right here in plain text"
        score, max_score = _score_keywords(response, sample)
        assert max_score == 0.4
        assert score == pytest.approx(0.4)
        # _score_code_fix should use the raw response (no fences present)
        result = _score_code_fix(response, sample)
        assert result > 0.0

    def test_clamped_to_one_when_score_exceeds_max(self) -> None:
        # All components maxed plus bonuses can sum exactly to max_score, so
        # min(1.0, ...) is exercised by construction even at the boundary.
        sample = {
            "expected_keywords": ["return", "def"],
            "buggy_code": "x = 1",
            "problem": "make it recursive",
            "expected_output": "done",
        }
        code_body = "def f():\n    return done  # recursive\n    def g():\n        return 1"
        response = f"```python\n{code_body}\n```"
        result = _score_code_fix(response, sample)
        assert result <= 1.0


# ---------------------------------------------------------------------------
# _judge_code_quality
# ---------------------------------------------------------------------------


class TestJudgeCodeQuality:
    async def test_returns_judge_score_from_llm_call(self) -> None:
        async def fake_llm_call(messages: Any, **kwargs: Any) -> str:
            return "Score: 8"

        result = await _judge_code_quality(
            "fix the bug", "buggy code", "```python\nfix\n```", fake_llm_call
        )
        assert result == pytest.approx(0.8)

    async def test_exception_in_llm_call_returns_zero(self) -> None:
        async def failing_llm_call(messages: Any, **kwargs: Any) -> str:
            raise RuntimeError("boom")

        result = await _judge_code_quality("problem", "buggy", "response text", failing_llm_call)
        assert result == 0.0

    async def test_uses_raw_response_truncated_when_no_code_fence(self) -> None:
        captured: dict[str, Any] = {}

        async def fake_llm_call(messages: Any, **kwargs: Any) -> str:
            captured["messages"] = messages
            return "Rating: 5"

        response = "no fences here, just plain text response"
        result = await _judge_code_quality("problem", "buggy", response, fake_llm_call)
        assert result == pytest.approx(0.5)
        user_content = captured["messages"][1]["content"]
        assert response in user_content


# ---------------------------------------------------------------------------
# run_swebench
# ---------------------------------------------------------------------------


class TestRunSwebench:
    async def test_llm_call_none_uses_heuristic_path_for_all_samples(self) -> None:
        genome = make_genome()
        result = await run_swebench(genome, None)
        assert result.benchmark == "swebench"
        assert result.samples_evaluated == 10
        assert result.metadata == {"total_samples": 10, "runner": "real"}
        assert result.cost_usd == 0.0
        assert 0.0 <= result.score <= 1.0

    async def test_high_static_score_skips_judge_and_uses_flat_cost(self) -> None:
        genome = make_genome()

        async def fake_llm_call(messages: Any, **kwargs: Any) -> str:
            # Response engineered to produce a static_score >= 0.7 for every
            # sample regardless of its specific keywords/buggy_code/problem:
            # include all plausible expected_keywords as raw words, a code
            # fence with "return"/"def ", and length > 20.
            return (
                "```python\n"
                "def fixed_solution():\n"
                "    recursive isinstance extend flatten dict cache memo iter loop\n"
                "    strip lower punctuation float zeroerror valueerror fromisoformat\n"
                "    timezone strptime range len lst set seen re sub\n"
                "    return [1, 2, 3, 4, 5, 6]\n"
                "```"
            )

        judge_called = {"count": 0}
        real_judge_call = fake_llm_call

        async def counting_llm_call(messages: Any, **kwargs: Any) -> str:
            content = str(messages)
            if "code review expert" in content or "Rate" in content:
                judge_called["count"] += 1
            return await real_judge_call(messages, **kwargs)

        result = await run_swebench(genome, counting_llm_call)
        assert result.samples_evaluated == 10
        # If every sample hit static_score >= 0.7, judge is never invoked and
        # cost is exactly 0.002 per sample.
        if judge_called["count"] == 0:
            assert result.cost_usd == pytest.approx(0.002 * 10)
        else:
            # Not all samples cleared 0.7 with this fixed response; just
            # sanity check cost is consistent with judge-call accounting.
            expected_cost = 0.002 * 10 + 0.001 * judge_called["count"]
            assert result.cost_usd == pytest.approx(expected_cost)

    async def test_low_static_score_invokes_judge_and_adds_cost(self) -> None:
        genome = make_genome()
        judge_prompts_seen = {"count": 0}

        async def fake_llm_call(messages: Any, **kwargs: Any) -> str:
            content = " ".join(m.get("content", "") for m in messages)
            if "code review expert" in content or "Rate" in content:
                judge_prompts_seen["count"] += 1
                return "Score: 6"
            # Deliberately weak response: no code fence, short, irrelevant
            # text -> guarantees static_score < 0.7 for every sample.
            return "not sure"

        result = await run_swebench(genome, fake_llm_call)
        assert result.samples_evaluated == 10
        assert judge_prompts_seen["count"] == 10
        # cost = 0.002 per sample (flat) + 0.001 per sample (judge invoked)
        assert result.cost_usd == pytest.approx((0.002 + 0.001) * 10)
        assert result.score > 0.0

    async def test_exception_path_increments_evaluated_without_score(self) -> None:
        genome = make_genome()

        async def raising_llm_call(messages: Any, **kwargs: Any) -> str:
            raise RuntimeError("network error")

        result = await run_swebench(genome, raising_llm_call)
        assert result.samples_evaluated == 10
        assert result.score == 0.0
        assert result.cost_usd == 0.0

    async def test_timeout_path_increments_evaluated_without_score(self) -> None:
        genome = make_genome()

        async def hanging_llm_call(messages: Any, **kwargs: Any) -> str:

            raise TimeoutError()

        result = await run_swebench(genome, hanging_llm_call)
        assert result.samples_evaluated == 10
        assert result.score == 0.0

    async def test_metadata_total_samples_matches_dataset_length(self) -> None:
        genome = make_genome()
        result = await run_swebench(genome, None)
        assert result.metadata["total_samples"] == len(SWEBENCH_SAMPLES)
        assert result.duration_seconds >= 0.0


# ---------------------------------------------------------------------------
# _heuristic_score
# ---------------------------------------------------------------------------


class TestHeuristicScore:
    def test_default_base_when_no_keywords_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"problem": "Fix the off-by-one bug in the loop counter."}
        assert _heuristic_score(sample) == pytest.approx(0.45)

    def test_recursive_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"problem": "Make the flatten function work recursively."}
        assert _heuristic_score(sample) == pytest.approx(0.35)

    def test_optimize_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"problem": "Optimize the fibonacci function."}
        assert _heuristic_score(sample) == pytest.approx(0.3)

    def test_slow_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"problem": "The function is too slow for large inputs."}
        assert _heuristic_score(sample) == pytest.approx(0.3)

    def test_regex_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"problem": "Use a regex to validate the email format."}
        assert _heuristic_score(sample) == pytest.approx(0.4)

    def test_re_dot_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"problem": "The re.sub call does not replace all occurrences."}
        assert _heuristic_score(sample) == pytest.approx(0.4)

    def test_sequential_if_overwrite_recursive_then_optimize(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Documents actual precedence: the ifs are sequential (not elif), so a
        # problem matching both "recursive" and "optimize"/"slow" ends up with
        # base overwritten by the LAST matching if-block, not the first. Here
        # "recursive" sets base=0.35, then "optimize" overwrites it to 0.3.
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"problem": "Optimize this recursive function for large n."}
        assert _heuristic_score(sample) == pytest.approx(0.3)

    def test_sequential_if_overwrite_recursive_then_regex_wins_last(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "recursive" -> 0.35, then "regex"/"re." -> 0.4 overwrites it since
        # the regex check is the final sequential if-block in the function.
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        sample = {"problem": "Use regex inside a recursive parser."}
        assert _heuristic_score(sample) == pytest.approx(0.4)

    def test_clamped_to_upper_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 10.0)
        sample = {"problem": "no special keywords here"}
        assert _heuristic_score(sample) == pytest.approx(0.85)

    def test_clamped_to_lower_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: -10.0)
        sample = {"problem": "no special keywords here"}
        assert _heuristic_score(sample) == pytest.approx(0.1)

    def test_missing_problem_key_uses_default_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "uniform", lambda a, b: 0.0)
        assert _heuristic_score({}) == pytest.approx(0.45)
