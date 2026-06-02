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
    text = "Short. This is longer sentence. Medium here now."
    assert ev({"op": "metric", "name": "avg_sentence_words", "cmp": "lt", "value": 10}, text)
    assert not ev({"op": "metric", "name": "avg_sentence_words", "cmp": "gt", "value": 10}, text)


def test_metric_long_word_ratio():
    text = "cat dog elephant" * 10  # 'elephant' > 10 chars? no, 8. use 'hippopotamus'
    text = "cat dog hippopotamus " * 10
    assert ev({"op": "metric", "name": "long_word_ratio", "cmp": "lt", "value": 0.5}, text)


def test_metric_unique_word_ratio():
    text = "the the the cat sat on the mat"
    assert ev({"op": "metric", "name": "unique_word_ratio", "cmp": "gt", "value": 0.3}, text)


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


def test_metric_max_line_length():
    text = "short line\n" + "x" * 130 + "\nanother short"
    assert ev({"op": "metric", "name": "max_line_length", "cmp": "gt", "value": 120}, text)
    assert not ev({"op": "metric", "name": "max_line_length", "cmp": "lte", "value": 120}, text)


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
