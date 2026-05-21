"""Tests for ConductorConfig — validation and loading."""

from __future__ import annotations

import pytest
from pathlib import Path

from orchestrator.config import ConductorConfig, ConfigError


@pytest.fixture
def valid_config_yaml(tmp_path: Path) -> Path:
    """Create a valid config file."""
    config_file = tmp_path / "conductor.yaml"
    config_file.write_text("""
project_id: "test-project"
project_dir: "/tmp/test"
obsidian_vault: "/tmp/vault"
gateway_url: "http://localhost:9090"
inference_url: "http://localhost:8080"
max_retries: 3
accept_threshold: 7.5
max_working_memory_tokens: 8000
layer0_path: "./constraints.md"

tests:
  command: "pytest"

toolchains:
  python:
    enabled: true
    package_manager: "pip"
""")
    return config_file


@pytest.fixture
def minimal_config_yaml(tmp_path: Path) -> Path:
    """Create a minimal valid config file."""
    config_file = tmp_path / "minimal.yaml"
    config_file.write_text("""
project_id: "minimal"
project_dir: "/tmp/minimal"
""")
    return config_file


class TestConfigLoading:
    """Config loading tests."""

    def test_loads_valid_config(self, valid_config_yaml: Path):
        """Should load a valid config file."""
        config = ConductorConfig.from_yaml(valid_config_yaml)
        assert config.project_id == "test-project"
        assert config.accept_threshold == 7.5
        assert config.tests.command == "pytest"
        assert config.toolchains["python"].enabled is True

    def test_loads_minimal_config(self, minimal_config_yaml: Path):
        """Should load minimal config with defaults."""
        config = ConductorConfig.from_yaml(minimal_config_yaml)
        assert config.project_id == "minimal"
        # Should have default values
        assert config.max_retries > 0
        assert config.accept_threshold > 0

    def test_raises_on_missing_file(self, tmp_path: Path):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            ConductorConfig.from_yaml(tmp_path / "nonexistent.yaml")

    def test_raises_on_invalid_yaml(self, tmp_path: Path):
        """Should raise ConfigError for invalid YAML."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("project_id: [unclosed")

        with pytest.raises(ConfigError, match="Invalid YAML"):
            ConductorConfig.from_yaml(bad_yaml)

    def test_raises_on_empty_file(self, tmp_path: Path):
        """Should raise ConfigError for empty file."""
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("")

        with pytest.raises(ConfigError):
            ConductorConfig.from_yaml(empty_yaml)


class TestConfigValidation:
    """Config validation tests."""

    def test_rejects_empty_project_id(self):
        """Should reject empty project_id."""
        with pytest.raises(ConfigError, match="project_id"):
            ConductorConfig(project_id="")

    def test_rejects_invalid_max_retries(self):
        """Should reject non-positive max_retries."""
        with pytest.raises(ConfigError, match="max_retries"):
            ConductorConfig(max_retries=0)

    def test_rejects_negative_max_retries(self):
        """Should reject negative max_retries."""
        with pytest.raises(ConfigError, match="max_retries"):
            ConductorConfig(max_retries=-1)

    def test_rejects_out_of_range_threshold(self):
        """Should reject accept_threshold outside 0-10."""
        with pytest.raises(ConfigError, match="accept_threshold"):
            ConductorConfig(accept_threshold=15)

    def test_rejects_negative_threshold(self):
        """Should reject negative accept_threshold."""
        with pytest.raises(ConfigError, match="accept_threshold"):
            ConductorConfig(accept_threshold=-1)

    def test_rejects_invalid_url(self):
        """Should reject invalid gateway_url."""
        with pytest.raises(ConfigError, match="gateway_url"):
            ConductorConfig(gateway_url="not-a-url")

    def test_accepts_valid_config(self):
        """Should accept valid configuration."""
        config = ConductorConfig(
            project_id="test",
            project_dir="/tmp",
            gateway_url="http://localhost:9090",
            inference_url="http://localhost:8080",
            max_retries=3,
            accept_threshold=7.0,
        )
        assert config.project_id == "test"


class TestBoundaryValues:
    """Boundary value tests."""

    def test_accepts_threshold_zero(self):
        """Should accept accept_threshold of 0."""
        config = ConductorConfig(
            project_id="test",
            project_dir="/tmp",
            accept_threshold=0,
        )
        assert config.accept_threshold == 0

    def test_accepts_threshold_ten(self):
        """Should accept accept_threshold of 10."""
        config = ConductorConfig(
            project_id="test",
            project_dir="/tmp",
            accept_threshold=10,
        )
        assert config.accept_threshold == 10

    def test_accepts_max_retries_one(self):
        """Should accept max_retries of 1."""
        config = ConductorConfig(
            project_id="test",
            project_dir="/tmp",
            max_retries=1,
        )
        assert config.max_retries == 1

    def test_accepts_high_max_retries(self):
        """Should accept high max_retries."""
        config = ConductorConfig(
            project_id="test",
            project_dir="/tmp",
            max_retries=100,
        )
        assert config.max_retries == 100


class TestUnknownKeys:
    """Unknown key handling tests."""

    def test_ignores_unknown_keys(self, tmp_path: Path):
        """Should ignore unknown keys with a warning."""
        config_file = tmp_path / "conductor.yaml"
        config_file.write_text("""
project_id: "test"
project_dir: "/tmp"
unknown_key: "ignored"
another_unknown: 123
""")
        # Should not raise, just warn
        config = ConductorConfig.from_yaml(config_file)
        assert config.project_id == "test"

    def test_nested_keys_parsed(self, tmp_path: Path):
        """Should parse nested keys correctly."""
        config_file = tmp_path / "conductor.yaml"
        config_file.write_text("""
project_id: "test"
project_dir: "/tmp"
tests:
  command: "pytest -v"
toolchains:
  python:
    enabled: true
    package_manager: "pip"
""")
        config = ConductorConfig.from_yaml(config_file)
        assert config.tests.command == "pytest -v"
        assert config.toolchains["python"].enabled is True
        assert config.toolchains["python"].package_manager == "pip"


class TestURLValidation:
    """URL validation tests."""

    @pytest.mark.parametrize(
        "valid_url",
        [
            "http://localhost:8080",
            "https://api.example.com",
            "http://127.0.0.1:9090",
            "http://my-server:8000",
        ],
    )
    def test_accepts_valid_urls(self, valid_url: str):
        """Should accept various valid URLs."""
        config = ConductorConfig(
            project_id="test",
            project_dir="/tmp",
            gateway_url=valid_url,
        )
        assert config.gateway_url == valid_url

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "not-a-url",
            "ftp://example.com",  # Only http/https
            "",
            "localhost:8080",  # Missing scheme
        ],
    )
    def test_rejects_invalid_urls(self, invalid_url: str):
        """Should reject various invalid URLs."""
        with pytest.raises(ConfigError):
            ConductorConfig(
                project_id="test",
                project_dir="/tmp",
                gateway_url=invalid_url,
            )
