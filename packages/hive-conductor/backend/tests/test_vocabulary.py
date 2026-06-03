"""Unit tests for the ADR-060 declarative check vocabulary."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # hive-conductor/

from eval.vocabulary import evaluate


def ev(spec, output, ctx=None):
    return evaluate(spec, output, ctx or {})


# ---------------------------------------------------------------------------
# keywords_any / keywords_none
# ---------------------------------------------------------------------------


def test_keywords_any_hit():
    assert ev({"op": "keywords_any", "words": ["hello", "world"]}, "say hello there")


def test_keywords_any_miss():
    assert not ev({"op": "keywords_any", "words": ["foo", "bar"]}, "nothing here")


def test_keywords_none_pass():
    assert ev({"op": "keywords_none", "words": ["bad", "evil"]}, "all good")


def test_keywords_none_fail():
    assert not ev({"op": "keywords_none", "words": ["bad"]}, "this is bad")


def test_keywords_case_insensitive():
    assert ev({"op": "keywords_any", "words": ["Hello"]}, "say HELLO")


def test_keywords_slice_end():
    long = "start " + "x " * 100 + "end"
    assert ev({"op": "keywords_any", "words": ["start"], "slice_end": 20}, long)
    assert not ev({"op": "keywords_any", "words": ["end"], "slice_end": 20}, long)


def test_keywords_slice_start():
    long = "start " + "x " * 100 + "end"
    assert ev({"op": "keywords_any", "words": ["end"], "slice_start": -10}, long)
    assert not ev({"op": "keywords_any", "words": ["start"], "slice_start": -10}, long)


# ---------------------------------------------------------------------------
# regex / regex_absent
# ---------------------------------------------------------------------------


def test_regex_match():
    assert ev({"op": "regex", "pattern": r"\d+"}, "there are 42 items")


def test_regex_no_match():
    assert not ev({"op": "regex", "pattern": r"\d+"}, "no digits here")


def test_regex_absent_pass():
    assert ev({"op": "regex_absent", "pattern": r"\d+"}, "no digits here")


def test_regex_absent_fail():
    assert not ev({"op": "regex_absent", "pattern": r"\d+"}, "42 is here")


def test_regex_flags_ignorecase():
    assert ev({"op": "regex", "pattern": r"hello", "flags": "i"}, "HELLO world")


def test_regex_flags_multiline():
    assert ev({"op": "regex", "pattern": r"^\d+", "flags": "m"}, "text\n42 items")


def test_regex_slice():
    text = "CITY, Date — " + "filler " * 50
    assert ev({"op": "regex", "pattern": r"^[A-Z]{2,}[\s,]"}, text)
    # without slice the pattern still matches; test slice_end restricts region
    short_text = "filler " * 50 + "CITY, Date"
    assert not ev({"op": "regex", "pattern": r"^[A-Z]{2,}[\s,]", "slice_end": 5}, short_text)


# ---------------------------------------------------------------------------
# regex_count
# ---------------------------------------------------------------------------


def test_regex_count_min():
    assert ev({"op": "regex_count", "pattern": r"\[\d+\]", "min": 3}, "[1] see [2] also [3]")
    assert not ev({"op": "regex_count", "pattern": r"\[\d+\]", "min": 3}, "[1] only one")


def test_regex_count_max():
    assert ev({"op": "regex_count", "pattern": "!", "max": 4}, "yes! ok! fine!")
    assert not ev({"op": "regex_count", "pattern": "!", "max": 4}, "!!!!! too many")


def test_regex_count_min_and_max():
    spec = {"op": "regex_count", "pattern": r"\?", "min": 1, "max": 3}
    assert ev(spec, "really? maybe? ok?")
    assert not ev(spec, "no questions")
    assert not ev(spec, "? ? ? ? ? five")


# ---------------------------------------------------------------------------
# word_count
# ---------------------------------------------------------------------------


def test_word_count_min():
    assert ev({"op": "word_count", "min": 3}, "one two three four")
    assert not ev({"op": "word_count", "min": 5}, "one two three")


def test_word_count_max():
    assert ev({"op": "word_count", "max": 5}, "one two three")
    assert not ev({"op": "word_count", "max": 2}, "one two three four")


# ---------------------------------------------------------------------------
# metric
# ---------------------------------------------------------------------------


def test_metric_avg_sentence_words():
    # "One." → 1 word, "Two words." → 2 words, "Three word sentence." → 3 words → avg ≈ 2.0
    text = "One. Two words. Three word sentence."
    assert ev({"op": "metric", "name": "avg_sentence_words", "cmp": "lt", "value": 10}, text)
    assert not ev({"op": "metric", "name": "avg_sentence_words", "cmp": "gt", "value": 10}, text)


def test_metric_avg_sentence_words_pinned_value():
    from eval.vocabulary import _avg_sentence_words

    # "Hello world. This is fine." → 2 sentences: ["Hello world", "This is fine"] → avg = 2.5
    result = _avg_sentence_words("Hello world. This is fine.")
    assert result == pytest.approx(2.5, abs=0.1)
    # Non-empty text must return a positive value
    assert _avg_sentence_words("Any non-empty sentence.") > 0.0
    # Empty returns 0
    assert _avg_sentence_words("") == 0.0


def test_metric_long_word_ratio():
    # "cat" (3), "dog" (3), "hippopotamus" (12 > 10) → 1/3 ≈ 0.33
    text = "cat dog hippopotamus"
    assert ev({"op": "metric", "name": "long_word_ratio", "cmp": "lt", "value": 0.5}, text)
    assert ev({"op": "metric", "name": "long_word_ratio", "cmp": "gt", "value": 0.2}, text)


def test_metric_long_word_ratio_pinned_value():
    from eval.vocabulary import _long_word_ratio

    # "cat" (3), "dog" (3), "hippopotamus" (12) → 1/3
    assert _long_word_ratio("cat dog hippopotamus") == pytest.approx(1 / 3, abs=0.01)
    # All long: "catastrophizing imagination" → 2/2 = 1.0
    assert _long_word_ratio("catastrophizing imagination") == pytest.approx(1.0)
    # All short: no long words → 0.0
    assert _long_word_ratio("cat dog fox") == pytest.approx(0.0)
    # Empty → 0.0
    assert _long_word_ratio("") == pytest.approx(0.0)


def test_metric_unique_word_ratio():
    text = "the the the cat sat on the mat"
    assert ev({"op": "metric", "name": "unique_word_ratio", "cmp": "gt", "value": 0.3}, text)


def test_metric_unique_word_ratio_pinned_value():
    from eval.vocabulary import _unique_word_ratio

    # "a b c" → 3 unique / 3 total = 1.0
    assert _unique_word_ratio("a b c") == pytest.approx(1.0)
    # "a a a" → 1/3
    assert _unique_word_ratio("a a a") == pytest.approx(1 / 3, abs=0.01)
    assert _unique_word_ratio("") == pytest.approx(0.0)


def test_metric_sentence_length_variety():
    text = "Hi. Hello there friend. This is a much longer sentence than the others."
    assert ev({"op": "metric", "name": "sentence_length_variety", "cmp": "gte", "value": 3}, text)
    assert not ev(
        {"op": "metric", "name": "sentence_length_variety", "cmp": "gte", "value": 10}, text
    )


def test_metric_list_density():
    text = "- item one\n- item two\n- item three\nsome prose here"
    assert ev({"op": "metric", "name": "list_density", "cmp": "lt", "value": 0.9}, text)
    all_list = "- one\n- two\n- three\n- four"
    assert ev({"op": "metric", "name": "list_density", "cmp": "gte", "value": 0.9}, all_list)


def test_metric_list_density_pinned_value():
    from eval.vocabulary import _list_density

    # 3 list lines + 1 prose = 0.75
    text = "- one\n- two\n- three\nprose"
    assert _list_density(text) == pytest.approx(0.75)
    # All list → 1.0
    assert _list_density("- a\n- b\n- c") == pytest.approx(1.0)
    # No list lines → 0.0
    assert _list_density("prose only\nmore prose") == pytest.approx(0.0)


def test_metric_max_line_length():
    text = "short line\n" + "x" * 130 + "\nanother short"
    assert ev({"op": "metric", "name": "max_line_length", "cmp": "gt", "value": 120}, text)
    assert not ev({"op": "metric", "name": "max_line_length", "cmp": "lte", "value": 120}, text)


def test_metric_max_line_length_pinned_value():
    from eval.vocabulary import _max_line_length

    text = "short\n" + "x" * 50 + "\ntiny"
    assert _max_line_length(text) == pytest.approx(50.0)
    # Empty → 0
    assert _max_line_length("") == pytest.approx(0.0)
    # Single line
    assert _max_line_length("hello world") == pytest.approx(11.0)


def test_metric_unknown_raises():
    with pytest.raises(ValueError, match="Unknown metric"):
        ev({"op": "metric", "name": "nonexistent", "cmp": "lt", "value": 1}, "text")


# ---------------------------------------------------------------------------
# any / all composition
# ---------------------------------------------------------------------------


def test_any_short_circuit_true():
    spec = {
        "op": "any",
        "of": [{"op": "keywords_any", "words": ["yes"]}, {"op": "keywords_any", "words": ["no"]}],
    }
    assert ev(spec, "yes please")
    assert ev(spec, "no thanks")
    assert not ev(spec, "maybe")


def test_all_requires_all():
    spec = {
        "op": "all",
        "of": [
            {"op": "keywords_any", "words": ["as a"]},
            {"op": "keywords_any", "words": ["i want"]},
        ],
    }
    assert ev(spec, "as a user I want this feature")
    assert not ev(spec, "as a user, I need something")
    assert not ev(spec, "I want things")


# ---------------------------------------------------------------------------
# registered predicates
# ---------------------------------------------------------------------------


def test_registered_active_voice_ratio_pass():
    text = "The party will start at 8. The guests will arrive by 7. We will have fun."
    assert ev({"op": "registered", "name": "active_voice_ratio"}, text)


def test_registered_active_voice_ratio_fail():
    text = "The party shall be held at 8. The guests shall be invited by 7."
    assert not ev({"op": "registered", "name": "active_voice_ratio"}, text)


def test_registered_latin_phrase_count_pass():
    assert ev(
        {"op": "registered", "name": "latin_phrase_count", "args": {"max": 1}},
        "We note inter alia the following.",
    )


def test_registered_latin_phrase_count_fail():
    text = "inter alia we find that mutatis mutandis the rule applies ipso facto."
    assert not ev({"op": "registered", "name": "latin_phrase_count", "args": {"max": 1}}, text)


def test_registered_keyword_count_max_pass():
    spec = {
        "op": "registered",
        "name": "keyword_count_max",
        "args": {"words": ["sign up", "buy now"], "max": 1},
    }
    assert ev(spec, "sign up today for great savings!")


def test_registered_keyword_count_max_fail():
    spec = {
        "op": "registered",
        "name": "keyword_count_max",
        "args": {"words": ["sign up", "buy now"], "max": 1},
    }
    assert not ev(spec, "sign up now and buy now while stocks last!")


def test_unknown_op_raises():
    with pytest.raises(ValueError, match="Unknown check op"):
        ev({"op": "magic_op"}, "text")


def test_unknown_registered_raises():
    with pytest.raises(ValueError, match="Unknown registered predicate"):
        ev({"op": "registered", "name": "does_not_exist"}, "text")


# ---------------------------------------------------------------------------
# Mutation killers — pin exact values for registered predicates + flag logic
# ---------------------------------------------------------------------------


def test_latin_phrase_count_max_default_is_1():
    """Default max=1: exactly 1 known phrase passes, 2 fails."""
    from eval.vocabulary import _latin_phrase_count

    # phrases from the list: "inter alia", "mutatis mutandis", "ipso facto", "prima facie"
    assert _latin_phrase_count("inter alia this applies") is True  # 1 phrase ≤ 1
    assert _latin_phrase_count("inter alia and mutatis mutandis") is False  # 2 phrases > 1


def test_latin_phrase_count_zero_passes():
    from eval.vocabulary import _latin_phrase_count

    assert _latin_phrase_count("No latin phrases at all") is True


def test_latin_phrase_count_custom_max():
    from eval.vocabulary import _latin_phrase_count

    # 2 phrases, max=2 → passes
    assert _latin_phrase_count("inter alia and ipso facto", max=2) is True
    # 3 phrases, max=2 → fails
    assert _latin_phrase_count("inter alia, ipso facto, prima facie", max=2) is False


def test_active_voice_ratio_returns_bool():
    from eval.vocabulary import _active_voice_ratio

    result = _active_voice_ratio("The cat sat on the mat.")
    assert isinstance(result, bool)


def test_active_voice_ratio_uses_lowercase():
    """Mutation: lo = None → crashes because None has no .count() method."""
    from eval.vocabulary import _active_voice_ratio

    # Both cases should produce identical results (case-insensitive)
    lower_result = _active_voice_ratio("this shall be done")
    upper_result = _active_voice_ratio("THIS SHALL BE DONE")
    assert lower_result == upper_result


def test_active_voice_ratio_active_text_passes():
    """Active text (will > shall be) should pass the check."""
    from eval.vocabulary import _active_voice_ratio

    assert _active_voice_ratio("I will do this and I will do that") is True


def test_active_voice_ratio_passive_text_fails():
    """Heavy passive text (shall be) should fail the check."""
    from eval.vocabulary import _active_voice_ratio

    assert _active_voice_ratio("it shall be done and it shall be finished") is False


def test_parse_flags_none_returns_zero():
    """Mutation: if flags vs if not flags → returns re.I instead of 0."""
    from eval.vocabulary import _parse_flags

    assert _parse_flags(None) == 0
    assert _parse_flags("") == 0


def test_parse_flags_i_returns_re_ignorecase():
    import re

    from eval.vocabulary import _parse_flags

    assert _parse_flags("i") == re.IGNORECASE


def test_eval_regex_count_uses_flags():
    """Mutation: flags=None → case-sensitive when it should be insensitive."""
    # regex_count with flags="i" should match case-insensitively
    spec = {"op": "regex_count", "pattern": "WORD", "flags": "i", "min": 1}
    assert ev(spec, "word appears here")  # "word" matches "WORD" with i flag
    # Without flags, "WORD" would NOT match "word"
    spec_no_flags = {"op": "regex_count", "pattern": "WORD", "min": 1}
    assert not ev(spec_no_flags, "word appears here")  # case-sensitive, no match


def test_eval_count_min_boundary():
    """Mutation: word count min off-by-one."""
    spec_min = {"op": "word_count", "min": 3}
    assert ev(spec_min, "one two three")  # exactly 3 = pass
    assert not ev(spec_min, "one two")  # 2 < 3 = fail


def test_eval_count_max_boundary():
    spec_max = {"op": "word_count", "max": 3}
    assert ev(spec_max, "one two three")  # exactly 3 = pass
    assert not ev(spec_max, "one two three four")  # 4 > 3 = fail


# ---------------------------------------------------------------------------
# Gap-fillers from 89% mutation scan — boundary / equivalence class pins
# ---------------------------------------------------------------------------


def test_active_voice_ratio_boundary_equal_counts():
    """shall_be == will: will+1 > shall_be → True (passes at equality)."""
    from eval.vocabulary import _active_voice_ratio

    # 1 "shall be", 1 "will" → count("shall be")=1 < count("will")+1=2 → True
    assert _active_voice_ratio("it shall be done, and we will do it") is True


def test_active_voice_ratio_boundary_will_zero():
    """0 'will', 1 'shall be' → 1 < 0+1=1 is False → fails check."""
    from eval.vocabulary import _active_voice_ratio

    assert _active_voice_ratio("it shall be finished") is False


def test_active_voice_ratio_both_zero():
    """No markers → 0 < 0+1=1 → True."""
    from eval.vocabulary import _active_voice_ratio

    assert _active_voice_ratio("the cat sat on the mat") is True


def test_active_voice_ratio_multiple_shall_be():
    """Multiple 'shall be' with 0 'will' → False."""
    from eval.vocabulary import _active_voice_ratio

    assert _active_voice_ratio("it shall be done and it shall be finished") is False


def test_list_density_empty_input_returns_zero():
    """Empty/whitespace-only → 0.0 (not 1.0 or other)."""
    from eval.vocabulary import _list_density

    assert _list_density("") == pytest.approx(0.0)
    assert _list_density("   ") == pytest.approx(0.0)
    assert _list_density("\n\n") == pytest.approx(0.0)


def test_list_density_bullet_markers():
    """All three bullet markers are counted: -, *, •"""
    from eval.vocabulary import _list_density

    dash = _list_density("- one\n- two")
    star = _list_density("* one\n* two")
    bullet = _list_density("• one\n• two")
    assert dash == pytest.approx(1.0)
    assert star == pytest.approx(1.0)
    assert bullet == pytest.approx(1.0)


def test_list_density_exact_fraction():
    """3 list + 1 prose = exactly 0.75."""
    from eval.vocabulary import _list_density

    assert _list_density("- a\n- b\n- c\nprose") == pytest.approx(0.75)


def test_parse_flags_unknown_returns_zero_flag():
    """Unknown flag string returns re.RegexFlag(0), not an error."""
    import re

    from eval.vocabulary import _parse_flags

    assert _parse_flags("z") == re.RegexFlag(0)
    assert _parse_flags("xyz") == re.RegexFlag(0)


def test_parse_flags_combined_si_and_is():
    """Both 'si' and 'is' map to IGNORECASE|DOTALL."""
    import re

    from eval.vocabulary import _parse_flags

    expected = re.IGNORECASE | re.DOTALL
    assert _parse_flags("si") == expected
    assert _parse_flags("is") == expected


def test_parse_flags_multiline():
    import re

    from eval.vocabulary import _parse_flags

    assert _parse_flags("m") == re.MULTILINE
    assert _parse_flags("im") == re.IGNORECASE | re.MULTILINE
    assert _parse_flags("mi") == re.IGNORECASE | re.MULTILINE


def test_eval_metric_lt_boundary():
    """lt: strictly less than — ratio 0.5 (a a) passes lt=1.0, fails lt=0.4."""
    assert ev({"op": "metric", "name": "unique_word_ratio", "cmp": "lt", "value": 1.0}, "a a")
    assert not ev({"op": "metric", "name": "unique_word_ratio", "cmp": "lt", "value": 0.4}, "a a")


def test_eval_metric_lte_includes_equal():
    """lte: equal value passes, above fails."""
    # unique_word_ratio("a a") = 0.5 exactly
    assert ev({"op": "metric", "name": "unique_word_ratio", "cmp": "lte", "value": 0.5}, "a a")
    assert not ev({"op": "metric", "name": "unique_word_ratio", "cmp": "lte", "value": 0.4}, "a a")


def test_eval_metric_gte_includes_equal():
    assert ev({"op": "metric", "name": "unique_word_ratio", "cmp": "gte", "value": 0.5}, "a a")
    assert not ev({"op": "metric", "name": "unique_word_ratio", "cmp": "gte", "value": 0.6}, "a a")


def test_eval_metric_eq():
    # unique_word_ratio("a a") = 0.5
    assert ev({"op": "metric", "name": "unique_word_ratio", "cmp": "eq", "value": 0.5}, "a a")


def test_eval_metric_invalid_comparator_raises():
    with pytest.raises(ValueError, match="Unknown comparator"):
        ev({"op": "metric", "name": "unique_word_ratio", "cmp": "neq", "value": 0.5}, "a b")


def test_eval_simple_returns_none_for_unknown_op():
    """_eval_simple must return None (not raise) for ops it doesn't handle."""
    from eval.vocabulary import _eval_simple

    assert _eval_simple("metric", {}, "") is None
    assert _eval_simple("any", {}, "") is None
    assert _eval_simple("registered", {}, "") is None
    assert _eval_simple(None, {}, "") is None


def test_eval_simple_all_handled_ops():
    """Each op _eval_simple owns returns bool, not None."""
    from eval.vocabulary import _eval_simple

    assert isinstance(_eval_simple("keywords_any", {"words": ["x"]}, "x"), bool)
    assert isinstance(_eval_simple("keywords_none", {"words": ["x"]}, "y"), bool)
    assert isinstance(_eval_simple("regex", {"pattern": "x"}, "y"), bool)
    assert isinstance(_eval_simple("regex_absent", {"pattern": "x"}, "y"), bool)
    assert isinstance(_eval_simple("regex_count", {"pattern": "x", "min": 0}, "y"), bool)
    assert isinstance(_eval_simple("word_count", {"max": 10}, "hello world"), bool)


def test_long_word_ratio_boundary_exactly_10_chars():
    """len(w) > 10: word of 10 chars does NOT count as long."""
    from eval.vocabulary import _long_word_ratio

    # "abcdefghij" = 10 chars → not long
    assert _long_word_ratio("abcdefghij") == pytest.approx(0.0)
    # "abcdefghijk" = 11 chars → long
    assert _long_word_ratio("abcdefghijk") == pytest.approx(1.0)
