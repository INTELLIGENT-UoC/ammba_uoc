"""Tests for the YAML + environment-variable settings loader."""

from pathlib import Path

import pytest
from src.config import load_settings

REPO_CONFIG = Path(__file__).parent.parent / "configuration.yaml"

ENV_KEYS = (
    "OFFCHAIN_DB_URL",
    "OFFCHAIN_TRANSPORT",
    "CONTRACT_ADDRESS",
    "CLEARING_NODE_PRIVATE_KEY",
    "PORT",
    "TIME_SLOT_SEC",
    "OFFCHAIN_STRICT_VALIDATION",
    "SCHEDULER_ENABLED",
    "SCHEDULER_POLL_INTERVAL_SEC",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_shipped_configuration_keeps_the_on_chain_step_off():
    settings = load_settings(REPO_CONFIG)
    assert settings.contract_address == ""
    assert "11111111-1111-4111-8111-111111111111" in settings.communities


def test_environment_overrides_yaml(monkeypatch):
    monkeypatch.setenv("OFFCHAIN_DB_URL", "http://offchain-db-sim:8080")
    monkeypatch.setenv("PORT", "9090")
    settings = load_settings(REPO_CONFIG)
    assert settings.offchain_db_url == "http://offchain-db-sim:8080"
    assert settings.port == 9090


def test_empty_variables_count_as_unset(monkeypatch):
    monkeypatch.setenv("PORT", "")
    monkeypatch.setenv("TIME_SLOT_SEC", "")
    monkeypatch.setenv("SCHEDULER_ENABLED", "")
    settings = load_settings(REPO_CONFIG)
    assert settings.port == 8081
    assert settings.time_slot_sec == 900
    assert settings.scheduler_enabled is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("1", True), ("ON", True), ("false", False), ("0", False), ("off", False)],
)
def test_boolean_flags(monkeypatch, raw, expected):
    monkeypatch.setenv("SCHEDULER_ENABLED", raw)
    assert load_settings(REPO_CONFIG).scheduler_enabled is expected


def test_unrecognised_boolean_is_rejected(monkeypatch):
    monkeypatch.setenv("OFFCHAIN_STRICT_VALIDATION", "maybe")
    with pytest.raises(ValueError, match="OFFCHAIN_STRICT_VALIDATION"):
        load_settings(REPO_CONFIG)
