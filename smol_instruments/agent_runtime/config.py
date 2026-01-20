"""
Configuration management for smol_instruments.

Loads settings from environment variables with sensible defaults.
"""

import os
from typing import Optional


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean from environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')


def get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable."""
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def get_env_float(key: str, default: float) -> float:
    """Get float from environment variable."""
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


class Config:
    """Central configuration for smol_instruments."""

    # LLM Model Settings
    MODEL_ID: str = os.getenv("MODEL_ID", "ollama_chat/qwen2.5-coder:14b-instruct")
    MODEL_API_BASE: str = os.getenv("MODEL_API_BASE", "http://localhost:11434")
    MODEL_TEMPERATURE: float = get_env_float("MODEL_TEMPERATURE", 0.1)
    MODEL_MAX_TOKENS: int = get_env_int("MODEL_MAX_TOKENS", 1024)

    # Agent Settings
    AGENT_MAX_STEPS: int = get_env_int("AGENT_MAX_STEPS", 25)

    # Phoenix Telemetry
    PHOENIX_ENABLED: bool = get_env_bool("PHOENIX_ENABLED", True)
    PHOENIX_ENDPOINT: str = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")

    # Validation Settings
    VALIDATION_MAX_CHARS: int = get_env_int("VALIDATION_MAX_CHARS", 5000)
    VALIDATION_MAX_LINES: int = get_env_int("VALIDATION_MAX_LINES", 200)
    VALIDATION_MAX_LINE_RANGE: int = get_env_int("VALIDATION_MAX_LINE_RANGE", 1000)

    # Truncation Settings
    TRUNCATION_MAX_CHARS: int = get_env_int("TRUNCATION_MAX_CHARS", 3000)
    TRUNCATION_MAX_LINES: int = get_env_int("TRUNCATION_MAX_LINES", 150)
    TRUNCATION_MAX_LIST_ITEMS: int = get_env_int("TRUNCATION_MAX_LIST_ITEMS", 100)

    # Sandbox Settings
    SANDBOX_IMAGE: str = os.getenv("SANDBOX_IMAGE", "smolagent-sandbox:latest")
    SANDBOX_TIMEOUT: int = get_env_int("SANDBOX_TIMEOUT", 300)

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SUPPRESS_WARNINGS: bool = get_env_bool("SUPPRESS_WARNINGS", True)

    @classmethod
    def load_from_env_file(cls, env_file: str = ".env"):
        """
        Load configuration from .env file.

        Args:
            env_file: Path to .env file
        """
        if not os.path.exists(env_file):
            return

        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    os.environ[key] = value

        # Reload class attributes after env vars are set
        cls.MODEL_ID = os.getenv("MODEL_ID", "ollama_chat/qwen2.5-coder:14b")
        cls.MODEL_API_BASE = os.getenv("MODEL_API_BASE", "http://localhost:11434")
        cls.MODEL_TEMPERATURE = get_env_float("MODEL_TEMPERATURE", 0.1)
        cls.MODEL_MAX_TOKENS = get_env_int("MODEL_MAX_TOKENS", 1024)
        cls.AGENT_MAX_STEPS = get_env_int("AGENT_MAX_STEPS", 25)
        cls.PHOENIX_ENABLED = get_env_bool("PHOENIX_ENABLED", True)
        cls.PHOENIX_ENDPOINT = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")
        cls.VALIDATION_MAX_CHARS = get_env_int("VALIDATION_MAX_CHARS", 5000)
        cls.VALIDATION_MAX_LINES = get_env_int("VALIDATION_MAX_LINES", 200)
        cls.VALIDATION_MAX_LINE_RANGE = get_env_int("VALIDATION_MAX_LINE_RANGE", 1000)
        cls.TRUNCATION_MAX_CHARS = get_env_int("TRUNCATION_MAX_CHARS", 3000)
        cls.TRUNCATION_MAX_LINES = get_env_int("TRUNCATION_MAX_LINES", 150)
        cls.TRUNCATION_MAX_LIST_ITEMS = get_env_int("TRUNCATION_MAX_LIST_ITEMS", 100)
        cls.SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "smolagent-sandbox:latest")
        cls.SANDBOX_TIMEOUT = get_env_int("SANDBOX_TIMEOUT", 300)
        cls.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        cls.SUPPRESS_WARNINGS = get_env_bool("SUPPRESS_WARNINGS", True)

    @classmethod
    def display(cls):
        """Display current configuration."""
        print("Current Configuration:")
        print(f"  MODEL_ID: {cls.MODEL_ID}")
        print(f"  MODEL_API_BASE: {cls.MODEL_API_BASE}")
        print(f"  MODEL_TEMPERATURE: {cls.MODEL_TEMPERATURE}")
        print(f"  MODEL_MAX_TOKENS: {cls.MODEL_MAX_TOKENS}")
        print(f"  AGENT_MAX_STEPS: {cls.AGENT_MAX_STEPS}")
        print(f"  PHOENIX_ENABLED: {cls.PHOENIX_ENABLED}")
        print(f"  PHOENIX_ENDPOINT: {cls.PHOENIX_ENDPOINT}")
        print(f"  LOG_LEVEL: {cls.LOG_LEVEL}")


# Try to load .env file on module import
Config.load_from_env_file()
