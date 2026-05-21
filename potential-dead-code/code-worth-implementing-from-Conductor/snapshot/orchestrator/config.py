"""Orchestrator configuration — loaded from conductor.yaml.

Includes validation to catch configuration errors early.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when configuration is invalid."""

    pass


@dataclass
class ToolchainConfig:
    enabled: bool = False
    package_manager: str = ""
    build_system: str = ""


@dataclass
class TestConfig:
    command: str = "echo 'no test command configured'"


@dataclass
class ConductorConfig:
    project_id: str = "default"
    project_dir: str = "."
    obsidian_vault: str = ""
    gateway_url: str = "http://localhost:9090"
    inference_url: str = "http://localhost:8080"
    max_retries: int = 3
    accept_threshold: float = 7.0
    max_working_memory_tokens: int = 8000
    layer0_path: str = "./constraints.md"
    training_data_dir: str = "./training-data"
    exemplar_library_dir: str = "./exemplars"
    tests: TestConfig = field(default_factory=TestConfig)
    toolchains: dict[str, ToolchainConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self._validate()

    def _validate(self) -> None:
        """Validate configuration values."""
        errors = []

        # Required string fields
        if not self.project_id or not isinstance(self.project_id, str):
            errors.append("project_id must be a non-empty string")

        if not self.project_dir or not isinstance(self.project_dir, str):
            errors.append("project_dir must be a non-empty string")

        # URLs should look like URLs
        for field_name in ("gateway_url", "inference_url"):
            url = getattr(self, field_name)
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                errors.append(f"{field_name} must be a valid HTTP(S) URL")

        # Numeric ranges
        if not isinstance(self.max_retries, int) or self.max_retries < 1:
            errors.append("max_retries must be a positive integer")

        if not isinstance(self.accept_threshold, (int, float)) or not (0 <= self.accept_threshold <= 10):
            errors.append("accept_threshold must be a number between 0 and 10")

        if not isinstance(self.max_working_memory_tokens, int) or self.max_working_memory_tokens < 100:
            errors.append("max_working_memory_tokens must be an integer >= 100")

        if errors:
            raise ConfigError("Configuration errors:\n  - " + "\n  - ".join(errors))

    @classmethod
    def from_yaml(cls, path: str | Path) -> ConductorConfig:
        """Load config from a YAML file.

        Raises:
            ConfigError: If the file is missing, invalid YAML, or fails validation
            FileNotFoundError: If the config file doesn't exist
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        try:
            raw = yaml.safe_load(config_path.read_text())
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config file: {e}")

        if not isinstance(raw, dict):
            raise ConfigError("Config file must contain a YAML mapping")

        # Extract nested configs
        tests_raw = raw.pop("tests", {})
        if not isinstance(tests_raw, dict):
            tests_raw = {}
        tests = TestConfig(**tests_raw)

        toolchains_raw = raw.pop("toolchains", {})
        if not isinstance(toolchains_raw, dict):
            toolchains_raw = {}
        toolchains = {}
        for k, v in toolchains_raw.items():
            if isinstance(v, dict):
                toolchains[k] = ToolchainConfig(**v)

        # Filter out unknown keys to avoid TypeError
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        known_fields -= {"tests", "toolchains"}  # Already handled
        filtered_raw = {k: v for k, v in raw.items() if k in known_fields}

        unknown_keys = set(raw.keys()) - known_fields - {"tests", "toolchains"}
        if unknown_keys:
            import logging
            logging.getLogger(__name__).warning("Unknown config keys ignored: %s", unknown_keys)

        return cls(tests=tests, toolchains=toolchains, **filtered_raw)
