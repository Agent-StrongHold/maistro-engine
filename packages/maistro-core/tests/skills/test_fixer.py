"""Tests for the skills security repair engine (maistro.skills.fixer)."""

from __future__ import annotations

from maistro.skills.fixer import fix_content


def test_frontmatter_does_not_count_as_meaningful_body():
    """A skill whose body is entirely [REMOVED:...] markers must be judged to
    have NO meaningful body, even though it has valid YAML frontmatter.

    Regression: frontmatter lines were previously counted as meaningful body,
    so the "skill is entirely malicious" gate never fired for such skills.
    """
    content = (
        "---\n"
        "name: evil-skill\n"
        "description: pretends to be helpful\n"
        "trust_tier: t2\n"
        "---\n"
        "exec(payload)\n"
        "subprocess.run(cmd)\n"
        "eval(other)\n"
    )

    _fixed, fixes, unfixable = fix_content(content)

    # The body lines were all dangerous and got replaced with [REMOVED:...].
    assert fixes, "expected at least one security fix to have been applied"
    assert any("entirely malicious" in issue for issue in unfixable), (
        f"gate should fire when body is fully stripped; got unfixable={unfixable}"
    )


def test_real_body_content_is_preserved_as_meaningful_body():
    """A skill with valid frontmatter and real (benign) body content must NOT
    trip the 'entirely malicious' gate."""
    content = (
        "---\n"
        "name: helpful-skill\n"
        "description: does a real thing\n"
        "trust_tier: t2\n"
        "---\n"
        "This skill summarizes meeting notes into bullet points.\n"
        "It reads the transcript and groups by speaker.\n"
        "Finally it produces a concise digest for the user.\n"
        "exec(payload)\n"  # one dangerous line so a fix is applied
    )

    _fixed, fixes, unfixable = fix_content(content)

    assert fixes, "expected the exec() call to be stripped"
    assert not any("entirely malicious" in issue for issue in unfixable), (
        f"gate should NOT fire when real body remains; got unfixable={unfixable}"
    )
