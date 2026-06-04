"""Tests for turing/self_model/types.py — guess_node_kind.

Pins all 6 prefix mappings + default fallback + edge cases.
"""

from __future__ import annotations

import pytest

from maistro_turing.self_model.types import NodeKind, guess_node_kind


class TestGuessNodeKind:
    def test_facet_prefix(self) -> None:
        assert guess_node_kind("facet:honesty_humility.sincerity") == NodeKind.PERSONALITY_FACET

    def test_passion_prefix(self) -> None:
        assert guess_node_kind("passion_music") == NodeKind.PASSION

    def test_hobby_prefix(self) -> None:
        assert guess_node_kind("hobby_cooking") == NodeKind.HOBBY

    def test_interest_prefix(self) -> None:
        assert guess_node_kind("interest_ai") == NodeKind.INTEREST

    def test_pref_prefix(self) -> None:
        assert guess_node_kind("pref_dark_mode") == NodeKind.PREFERENCE

    def test_skill_prefix(self) -> None:
        assert guess_node_kind("skill_python") == NodeKind.SKILL

    def test_unknown_defaults_to_personality_facet(self) -> None:
        assert guess_node_kind("unknown_node_id") == NodeKind.PERSONALITY_FACET

    def test_empty_string_defaults(self) -> None:
        assert guess_node_kind("") == NodeKind.PERSONALITY_FACET

    def test_exact_prefix_passion(self) -> None:
        assert guess_node_kind("passion") == NodeKind.PASSION

    def test_exact_prefix_skill(self) -> None:
        assert guess_node_kind("skill") == NodeKind.SKILL

    def test_exact_prefix_hobby(self) -> None:
        assert guess_node_kind("hobby") == NodeKind.HOBBY

    def test_exact_prefix_interest(self) -> None:
        assert guess_node_kind("interest") == NodeKind.INTEREST

    def test_pref_prefix_precedence_over_other(self) -> None:
        assert guess_node_kind("preferred_option") == NodeKind.PREFERENCE

    @pytest.mark.parametrize(
        "node_id, expected",
        [
            ("facet:trait.thing", NodeKind.PERSONALITY_FACET),
            ("passion_123", NodeKind.PASSION),
            ("hobby_test", NodeKind.HOBBY),
            ("interest_xyz", NodeKind.INTEREST),
            ("pref_abc", NodeKind.PREFERENCE),
            ("skill_def", NodeKind.SKILL),
            ("random_node", NodeKind.PERSONALITY_FACET),
        ],
    )
    def test_all_mappings(self, node_id: str, expected: NodeKind) -> None:
        assert guess_node_kind(node_id) == expected
