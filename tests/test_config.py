"""Tests for autoforge.config."""

import os

from autoforge.config import EVAL_MODEL, CODE_MODEL, PLAN_MODEL, ForgeConfig
import pytest


def test_default_config():
    config = ForgeConfig()
    assert config.max_iterations == 10
    assert config.subprocess_timeout == 60
    assert config.output_dir == "./output"
    assert config.verbose is False
    assert config.skip_review is False


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
    config = ForgeConfig()
    assert config.api_key == "test-key-123"


def test_config_validate_missing_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = ForgeConfig(api_key="")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        config.validate()


def test_config_validate_with_key():
    config = ForgeConfig(api_key="sk-test")
    config.validate()  # Should not raise


def test_model_constants():
    assert "opus" in PLAN_MODEL
    assert "sonnet" in CODE_MODEL
    assert "haiku" in EVAL_MODEL
