"""Tests for secret redaction in logs, prompts, and error messages."""

from __future__ import annotations

import pytest

from maistro.security.redact import redact


class TestRedactNoneAndEmpty:
    def test_none_returns_none(self):
        assert redact(None) is None

    @pytest.mark.ac("ADR-064/AC-40")
    def test_empty_string_returns_empty(self):
        assert redact("") == ""

    def test_whitespace_only_unchanged(self):
        assert redact("   \n\t  ") == "   \n\t  "


class TestRedactAPIKeys:
    @pytest.mark.ac("ADR-064/AC-1")
    def test_sk_prefix(self):
        key = "sk-" + "TESTFAKEVALUE12345"
        result = redact(f"use key {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    @pytest.mark.ac("ADR-064/AC-6")
    def test_sk_ant_prefix(self):
        key = "sk-" + "ant-TESTFAKEVALUE12345"
        result = redact(f"key is {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    @pytest.mark.ac("ADR-064/AC-7")
    def test_sk_live_prefix(self):
        key = "sk_" + "live_TESTFAKEVALUE12345"
        result = redact(f"key={key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    def test_sk_test_prefix(self):
        key = "sk_" + "test_TESTFAKEVALUE12345"
        result = redact(f"key={key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    @pytest.mark.ac("ADR-064/AC-2")
    def test_ghp_prefix(self):
        key = "ghp_TESTFAKEVALUE12345"
        result = redact(f"key is {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    @pytest.mark.ac("ADR-064/AC-3")
    def test_aiza_prefix(self):
        key = "AIzaTESTFAKEVALUE1234567890"
        result = redact(f"google key {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    @pytest.mark.ac("ADR-064/AC-4")
    def test_xoxb_prefix(self):
        key = "xoxb-TESTFAKEVALUE12345"
        result = redact(f"slack bot {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    @pytest.mark.ac("ADR-064/AC-5")
    def test_pplx_prefix(self):
        key = "pplx-TESTFAKEVALUE12345"
        result = redact(f"perplexity {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result


class TestRedactAWSKeys:
    @pytest.mark.ac("ADR-064/AC-8")
    def test_aws_key(self):
        prefix = "AKIA"
        key = prefix + "FAKE1234567890AB"
        result = redact(f"aws_access_key_id={key}")
        assert "[REDACTED_AWS_KEY]" in result
        assert "FAKE1234567890AB" not in result

    @pytest.mark.ac("ADR-064/AC-8")
    def test_aws_key_in_context(self):
        prefix = "AKIA"
        key = prefix + "FAKE1234567890AB"
        result = redact(f"credentials: access_key={key} region=us-east-1")
        assert "[REDACTED_AWS_KEY]" in result
        assert "us-east-1" in result


class TestRedactENV:
    @pytest.mark.ac("ADR-064/AC-9")
    def test_secret_key(self):
        result = redact("SECRET_KEY=FAKE_VALUE_123")
        assert "[REDACTED_ENV]" in result
        assert "FAKE_VALUE" not in result

    @pytest.mark.ac("ADR-064/AC-10")
    def test_api_key(self):
        result = redact("API_KEY=FAKE_API_VALUE")
        assert "[REDACTED_ENV]" in result
        assert "FAKE_API_VALUE" not in result

    def test_password(self):
        result = redact("PASSWORD=FAKE_PASS_123")
        assert "[REDACTED_ENV]" in result
        assert "FAKE_PASS" not in result

    @pytest.mark.ac("ADR-064/AC-9")
    def test_case_insensitive(self):
        result = redact("secret_key=FAKE_VALUE")
        assert "[REDACTED_ENV]" in result
        assert "FAKE_VALUE" not in result

    def test_mixed_case_password(self):
        result = redact("Password=FAKE_VALUE")
        assert "[REDACTED_ENV]" in result
        assert "FAKE_VALUE" not in result

    def test_spaces_around_equals(self):
        result = redact("SECRET_KEY = FAKE_VALUE_123")
        assert "[REDACTED_ENV]" in result
        assert "FAKE_VALUE" not in result

    @pytest.mark.ac("ADR-064/AC-11")
    @pytest.mark.ac("ADR-064/AC-29")
    def test_multiline_env(self):
        text = "DEBUG=true\nSECRET_KEY=FAKE_VALUE\nPORT=3000"
        result = redact(text)
        assert "[REDACTED_ENV]" in result
        assert "DEBUG=true" in result
        assert "PORT=3000" in result
        assert "FAKE_VALUE" not in result


class TestRedactAuthHeaders:
    @pytest.mark.ac("ADR-064/AC-15")
    def test_bearer(self):
        result = redact("Authorization: Bearer FAKE_TOKEN_12345")
        assert "[REDACTED_AUTH_HEADER]" in result
        assert "FAKE_TOKEN" not in result

    @pytest.mark.ac("ADR-064/AC-16")
    def test_basic(self):
        result = redact("Authorization: Basic FAKECREDS123")
        assert "[REDACTED_AUTH_HEADER]" in result
        assert "FAKECREDS" not in result

    def test_token(self):
        result = redact("Authorization: Token FAKE_TOKEN_12345")
        assert "[REDACTED_AUTH_HEADER]" in result
        assert "FAKE_TOKEN" not in result

    def test_case_insensitive_bearer(self):
        result = redact("auth: bearer FAKE_TOKEN_12345")
        assert "[REDACTED_AUTH_HEADER]" in result


class TestRedactPrivateKeys:
    @pytest.mark.ac("ADR-064/AC-17")
    def test_rsa_private_key(self):
        key_block = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "FAKEKEYDATA1234567890==\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = redact(key_block)
        assert "[REDACTED_PRIVATE_KEY]" in result
        assert "FAKEKEYDATA" not in result

    def test_ec_private_key(self):
        key_block = "-----BEGIN EC PRIVATE KEY-----\nFAKEECKEYDATA==\n-----END EC PRIVATE KEY-----"
        result = redact(key_block)
        assert "[REDACTED_PRIVATE_KEY]" in result
        assert "FAKEECKEYDATA" not in result

    def test_generic_private_key(self):
        key_block = "-----BEGIN PRIVATE KEY-----\nFAKEGENERICKEY==\n-----END PRIVATE KEY-----"
        result = redact(key_block)
        assert "[REDACTED_PRIVATE_KEY]" in result
        assert "FAKEGENERICKEY" not in result

    @pytest.mark.ac("ADR-064/AC-30")
    def test_private_key_in_context(self):
        key_block = (
            "config:\n"
            "  key: |\n"
            "    -----BEGIN RSA PRIVATE KEY-----\n"
            "    FAKEKEYDATA==\n"
            "    -----END RSA PRIVATE KEY-----\n"
            "  host: example.com"
        )
        result = redact(key_block)
        assert "[REDACTED_PRIVATE_KEY]" in result
        assert "example.com" in result


class TestRedactDBConnections:
    @pytest.mark.ac("ADR-064/AC-19")
    def test_postgres(self):
        result = redact("postgres://fakeuser:fakepass@fakedb.example.com:5432/mydb")
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "fakepass" not in result

    @pytest.mark.ac("ADR-064/AC-20")
    def test_mysql(self):
        result = redact("mysql://fakeuser:fakepass@fakedb.example.com:3306/mydb")
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "fakepass" not in result

    @pytest.mark.ac("ADR-064/AC-21")
    def test_mongodb(self):
        result = redact("mongodb://fakeuser:fakepass@fakedb.example.com:27017/mydb")
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "fakepass" not in result


class TestRedactJWTs:
    @pytest.mark.ac("ADR-064/AC-22")
    def test_jwt_long_enough(self):
        # Real JWT shape: 3 base64url segments separated by dots
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = redact(f"token={token}")
        assert "[REDACTED_JWT]" in result
        assert token not in result

    def test_jwt_too_short(self):
        # Single segment without dots — not a JWT
        token = "eyJ" + "A" * 46
        result = redact(f"token={token}")
        assert "[REDACTED_JWT]" not in result

    def test_jwt_in_auth_header(self):
        token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIn0.signatureAAAAAAAAAAAAAAAAAAAAAAAAA"
        result = redact(f"Authorization: Bearer {token}")
        assert token not in result

    @pytest.mark.ac("ADR-064/AC-22")
    def test_jwt_with_dashes_and_underscores(self):
        token = "eyJhbGciOiJIUzI1NiJ9.eyJuYW1lIjoiSm9obiJ9.A_a-1B_b-2C_c-3D_d-4E_e-5F"
        result = redact(f"jwt: {token}")
        assert token not in result


class TestRedactURLUserinfo:
    @pytest.mark.ac("ADR-064/AC-24")
    def test_https_url_with_creds(self):
        result = redact("https://fakeuser:fakepass@example.com/path")
        assert "[REDACTED_URL_USERINFO]" in result
        assert "fakepass" not in result

    def test_ftp_url_with_creds(self):
        result = redact("ftp://fakeuser:fakepass@ftp.example.com")
        assert "[REDACTED_URL_USERINFO]" in result
        assert "fakepass" not in result

    @pytest.mark.ac("ADR-064/AC-39")
    def test_url_without_creds_unchanged(self):
        url = "https://example.com/path/to/resource"
        assert redact(url) == url


class TestRedactQueryParams:
    @pytest.mark.ac("ADR-064/AC-26")
    def test_api_key_param(self):
        result = redact("https://example.com/api?api_key=FAKE_VALUE_123")
        assert "[REDACTED_QUERY_PARAM]" in result
        assert "FAKE_VALUE" not in result

    def test_secret_param(self):
        result = redact("https://example.com/callback?secret=FAKE_SECRET")
        assert "[REDACTED_QUERY_PARAM]" in result
        assert "FAKE_SECRET" not in result

    @pytest.mark.ac("ADR-064/AC-27")
    def test_token_param(self):
        result = redact("https://example.com/auth?token=FAKE_TOKEN&redirect=ok")
        assert "[REDACTED_QUERY_PARAM]" in result
        assert "FAKE_TOKEN" not in result
        assert "redirect=ok" in result

    def test_key_param(self):
        result = redact("https://example.com?key=FAKE_KEY_VALUE")
        assert "[REDACTED_QUERY_PARAM]" in result
        assert "FAKE_KEY_VALUE" not in result

    @pytest.mark.ac("ADR-064/AC-28")
    @pytest.mark.ac("ADR-064/AC-39")
    def test_non_secret_param_unchanged(self):
        url = "https://example.com?page=2&sort=name"
        assert redact(url) == url


class TestRedactMultipleSecrets:
    @pytest.mark.ac("ADR-064/AC-44")
    def test_multiple_secrets_in_one_text(self):
        text = (
            f"db=postgres://fu:fp@host/db key={'sk-' + 'FAKE12345678'} auth=Bearer FAKE_TOKEN_VALUE"
        )
        result = redact(text)
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "[REDACTED_API_KEY]" in result
        assert "[REDACTED_AUTH_HEADER]" in result

    @pytest.mark.ac("ADR-064/AC-29")
    def test_multiline_with_mixed_secrets(self):
        sk_key = "sk-" + "FAKEVALUE12345"
        text = f"connecting to db...\npostgres://fu:fp@host/db\nusing key {sk_key}\nall good"
        result = redact(text)
        assert result.count("[REDACTED_") >= 2
        assert "all good" in result


class TestRedactNoFalsePositives:
    @pytest.mark.ac("ADR-064/AC-37")
    def test_plain_text_unchanged(self):
        text = "Hello world, this is a normal message."
        assert redact(text) == text

    @pytest.mark.ac("ADR-064/AC-38")
    def test_code_snippet_unchanged(self):
        code = "def hello(name: str) -> str:\n    return f'Hello {name}'"
        assert redact(code) == code

    def test_random_eyj_not_redacted(self):
        text = "the word eyjafjallajokull is a volcano"
        assert redact(text) == text


class TestRedactCompiledAtImportTime:
    def test_patterns_are_compiled(self):
        import re

        from maistro.security.redact import _PATTERNS

        for pattern, _ in _PATTERNS:
            assert isinstance(pattern, re.Pattern)


class TestNestedPatternSafety:
    """ADR-064 section 4 — a secret wrapped in another syntax must still die.

    Each of these embeds one already-supported secret shape inside JSON or a
    URL. No JSON-aware pattern exists; the claim is that the inner pattern
    fires regardless of what surrounds it, with no partial leakage.

    Secret-shaped literals are assembled by concatenation, matching the rest of
    this file. A contiguous `sk-proj-<40 chars>` in the source is a real
    gitleaks hit even though the value is invented — the scanner reads the
    diff, not our intent — so the split keeps the runtime string identical
    while leaving nothing secret-shaped on any single line.

    Note when mutation-testing these: emptying `_PATTERNS` does not make them
    pass vacuously *and* does not make them all fail, because
    `_HIGH_ENTROPY_RE` is a second, independent redaction path. The named
    pattern is what fires in normal operation (the marker is
    `[REDACTED_API_KEY]`, not `[REDACTED_HIGH_ENTROPY]`); the entropy
    heuristic is defence in depth behind it.
    """

    @pytest.mark.ac("ADR-064/AC-31")
    def test_api_key_inside_json_value_no_partial_leakage(self):
        key = "sk-" + "proj-" + "FAKEabc123def456ghi789jkl012mno345pqr678"
        result = redact('{"token": "' + key + '"}')
        assert key not in result
        assert "abc123" not in result
        assert "[REDACTED" in result

    @pytest.mark.ac("ADR-064/AC-32")
    def test_url_with_credentials_inside_json_field(self):
        dsn = "postgres://fakeadmin:" + "FAKEs3cret" + "@db.example.com/app"
        result = redact('{"connection_string": "' + dsn + '"}')
        assert "FAKEs3cret" not in result
        assert "fakeadmin:" not in result

    @pytest.mark.ac("ADR-064/AC-33")
    def test_query_param_value_with_api_key_prefix(self):
        key = "sk-" + "proj-" + "FAKE1234567890abcdef"
        result = redact("https://api.example.com?api_key=" + key)
        assert key not in result
        assert "1234567890" not in result

    @pytest.mark.ac("ADR-064/AC-23")
    @pytest.mark.ac("ADR-064/AC-34")
    def test_jwt_in_auth_header_fully_consumed_with_marker(self):
        token = "eyJ" + "hbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.FAKEsig123"
        result = redact("Authorization: Bearer " + token)
        assert "hbGciOiJSUzI1NiJ9" not in result
        assert "FAKEsig123" not in result
        assert "[REDACTED_AUTH_HEADER]" in result
