"""Tests for the YAML + environment-variable settings loader."""

from pathlib import Path

import pytest
from src.config import load_settings

REPO_CONFIG = Path(__file__).parent.parent / "configuration.yaml"

ENV_KEYS = (
    "OFFCHAIN_DB_URL",
    "OFFCHAIN_TRANSPORT",
    "CONTRACT_ADDRESS",
    "AUDIT_ANCHOR_PRIVATE_KEY",
    "CLEARING_NODE_PRIVATE_KEY",
    "PORT",
    "TIME_SLOT_SEC",
    "OFFCHAIN_STRICT_VALIDATION",
    "SCHEDULER_ENABLED",
    "SCHEDULER_POLL_INTERVAL_SEC",
    "EWDS_EMPTY_RESPONSE_GRACE_MS",
    "EWDS_RATE_LIMIT_BACKOFF_MS",
    "EWDS_RATE_LIMIT_MAX_BACKOFF_MS",
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


def test_ewds_delivery_settings(monkeypatch):
    defaults = load_settings(REPO_CONFIG)
    assert defaults.ewds_empty_response_grace_ms == 10000
    assert defaults.ewds_publish_backoff_ms == 2000
    assert defaults.ewds_publish_max_backoff_ms == 30000
    monkeypatch.setenv("EWDS_EMPTY_RESPONSE_GRACE_MS", "0")  # "0" is a value, not unset
    monkeypatch.setenv("EWDS_RATE_LIMIT_BACKOFF_MS", "500")
    monkeypatch.setenv("EWDS_RATE_LIMIT_MAX_BACKOFF_MS", "8000")
    settings = load_settings(REPO_CONFIG)
    assert settings.ewds_empty_response_grace_ms == 0
    assert settings.ewds_publish_backoff_ms == 500
    assert settings.ewds_publish_max_backoff_ms == 8000


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


def test_audit_anchor_key_is_read_from_its_variable(monkeypatch):
    monkeypatch.setenv("AUDIT_ANCHOR_PRIVATE_KEY", "0x" + "11" * 32)
    monkeypatch.setenv("CLEARING_NODE_PRIVATE_KEY", "0x" + "22" * 32)
    settings = load_settings(REPO_CONFIG)
    assert settings.audit_anchor_private_key == "0x" + "11" * 32


def test_former_audit_anchor_key_name_is_still_accepted(monkeypatch):
    monkeypatch.setenv("CLEARING_NODE_PRIVATE_KEY", "0x" + "22" * 32)
    settings = load_settings(REPO_CONFIG)
    assert settings.audit_anchor_private_key == "0x" + "22" * 32


def test_configuration_with_the_former_pool_actor_key_still_loads(tmp_path):
    """pool_actor_uuid was removed; an existing file that still carries it loads."""
    config = tmp_path / "configuration.yaml"
    config.write_text(
        "communities:\n"
        "  11111111-1111-4111-8111-111111111111:\n"
        "    k_upper_ct_per_kwh: 28.5\n"
        "    k_lower_ct_per_kwh: 8.0\n"
        "    theta: 1.0\n"
        "    steepness: 2.5\n"
        '    pool_id: "AMM_POOL_x"\n'
        '    pool_actor_uuid: "22222222-2222-4222-8222-222222222222"\n'
    )
    community = load_settings(config).communities["11111111-1111-4111-8111-111111111111"]
    assert community.k_upper_ct_per_kwh == 28.5
    assert not hasattr(community, "pool_actor_uuid")
