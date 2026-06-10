"""Tests for secret redaction in logs, prompts, and error messages."""

from __future__ import annotations

from maistro.security.redact import redact


class TestRedactNoneAndEmpty:
    def test_none_returns_none(self):
        assert redact(None) is None

    def test_empty_string_returns_empty(self):
        assert redact("") == ""

    def test_whitespace_only_unchanged(self):
        assert redact("   \n\t  ") == "   \n\t  "


class TestRedactAPIKeys:
    def test_sk_prefix(self):
        key = "sk-" + "TESTFAKEVALUE12345"
        result = redact(f"use key {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    def test_sk_ant_prefix(self):
        key = "sk-" + "ant-TESTFAKEVALUE12345"
        result = redact(f"key is {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

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

    def test_ghp_prefix(self):
        key = "ghp_TESTFAKEVALUE12345"
        result = redact(f"key is {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    def test_aiza_prefix(self):
        key = "AIzaTESTFAKEVALUE1234567890"
        result = redact(f"google key {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    def test_xoxb_prefix(self):
        key = "xoxb-TESTFAKEVALUE12345"
        result = redact(f"slack bot {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result

    def test_pplx_prefix(self):
        key = "pplx-TESTFAKEVALUE12345"
        result = redact(f"perplexity {key}")
        assert "[REDACTED_API_KEY]" in result
        assert "TESTFAKEVALUE" not in result


class TestRedactAWSKeys:
    def test_aws_key(self):
        prefix = "AKIA"
        key = prefix + "FAKE1234567890AB"
        result = redact(f"aws_access_key_id={key}")
        assert "[REDACTED_AWS_KEY]" in result
        assert "FAKE1234567890AB" not in result

    def test_aws_key_in_context(self):
        prefix = "AKIA"
        key = prefix + "FAKE1234567890AB"
        result = redact(f"credentials: access_key={key} region=us-east-1")
        assert "[REDACTED_AWS_KEY]" in result
        assert "us-east-1" in result


class TestRedactENV:
    def test_secret_key(self):
        result = redact("SECRET_KEY=FAKE_VALUE_123")
        assert "[REDACTED_ENV]" in result
        assert "FAKE_VALUE" not in result

    def test_api_key(self):
        result = redact("API_KEY=FAKE_API_VALUE")
        assert "[REDACTED_ENV]" in result
        assert "FAKE_API_VALUE" not in result

    def test_password(self):
        result = redact("PASSWORD=FAKE_PASS_123")
        assert "[REDACTED_ENV]" in result
        assert "FAKE_PASS" not in result

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

    def test_multiline_env(self):
        text = "DEBUG=true\nSECRET_KEY=FAKE_VALUE\nPORT=3000"
        result = redact(text)
        assert "[REDACTED_ENV]" in result
        assert "DEBUG=true" in result
        assert "PORT=3000" in result
        assert "FAKE_VALUE" not in result


class TestRedactAuthHeaders:
    def test_bearer(self):
        result = redact("Authorization: Bearer FAKE_TOKEN_12345")
        assert "[REDACTED_AUTH_HEADER]" in result
        assert "FAKE_TOKEN" not in result

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
    def test_postgres(self):
        result = redact("postgres://fakeuser:fakepass@fakedb.example.com:5432/mydb")
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "fakepass" not in result

    def test_mysql(self):
        result = redact("mysql://fakeuser:fakepass@fakedb.example.com:3306/mydb")
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "fakepass" not in result

    def test_mongodb(self):
        result = redact("mongodb://fakeuser:fakepass@fakedb.example.com:27017/mydb")
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "fakepass" not in result


class TestRedactJWTs:
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

    def test_jwt_with_dashes_and_underscores(self):
        token = "eyJhbGciOiJIUzI1NiJ9.eyJuYW1lIjoiSm9obiJ9.A_a-1B_b-2C_c-3D_d-4E_e-5F"
        result = redact(f"jwt: {token}")
        assert token not in result


class TestRedactURLUserinfo:
    def test_https_url_with_creds(self):
        result = redact("https://fakeuser:fakepass@example.com/path")
        assert "[REDACTED_URL_USERINFO]" in result
        assert "fakepass" not in result

    def test_ftp_url_with_creds(self):
        result = redact("ftp://fakeuser:fakepass@ftp.example.com")
        assert "[REDACTED_URL_USERINFO]" in result
        assert "fakepass" not in result

    def test_url_without_creds_unchanged(self):
        url = "https://example.com/path/to/resource"
        assert redact(url) == url


class TestRedactQueryParams:
    def test_api_key_param(self):
        result = redact("https://example.com/api?api_key=FAKE_VALUE_123")
        assert "[REDACTED_QUERY_PARAM]" in result
        assert "FAKE_VALUE" not in result

    def test_secret_param(self):
        result = redact("https://example.com/callback?secret=FAKE_SECRET")
        assert "[REDACTED_QUERY_PARAM]" in result
        assert "FAKE_SECRET" not in result

    def test_token_param(self):
        result = redact("https://example.com/auth?token=FAKE_TOKEN&redirect=ok")
        assert "[REDACTED_QUERY_PARAM]" in result
        assert "FAKE_TOKEN" not in result
        assert "redirect=ok" in result

    def test_key_param(self):
        result = redact("https://example.com?key=FAKE_KEY_VALUE")
        assert "[REDACTED_QUERY_PARAM]" in result
        assert "FAKE_KEY_VALUE" not in result

    def test_non_secret_param_unchanged(self):
        url = "https://example.com?page=2&sort=name"
        assert redact(url) == url


class TestRedactMultipleSecrets:
    def test_multiple_secrets_in_one_text(self):
        text = f"db=postgres://fu:fp@host/db key={'sk-' + 'FAKE12345678'} auth=Bearer FAKE_TOKEN_VALUE"
        result = redact(text)
        assert "[REDACTED_DB_CONNECTION]" in result
        assert "[REDACTED_API_KEY]" in result
        assert "[REDACTED_AUTH_HEADER]" in result

    def test_multiline_with_mixed_secrets(self):
        sk_key = "sk-" + "FAKEVALUE12345"
        text = f"connecting to db...\npostgres://fu:fp@host/db\nusing key {sk_key}\nall good"
        result = redact(text)
        assert result.count("[REDACTED_") >= 2
        assert "all good" in result


class TestRedactNoFalsePositives:
    def test_plain_text_unchanged(self):
        text = "Hello world, this is a normal message."
        assert redact(text) == text

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
