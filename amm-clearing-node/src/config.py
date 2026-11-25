"""Configuration loader: YAML file with environment variable overrides."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class CommunityConfig(BaseModel):
    k_upper_ct_per_kwh: float
    k_lower_ct_per_kwh: float
    theta: float
    steepness: float
    # Seller-side energy-type differential pricing (zero-sum: green subsidy
    # funded by the grey levy; disabled while both rates are 0). Computed for
    # the clearing summary only; trade prices stay at the clearing price.
    # Unknown keys are ignored, so a configuration that still carries the
    # former pool_id or pool_actor_uuid keeps loading.
    green_subsidy_rate: float = 0.0
    grey_levy_rate: float = 0.0
    levy_cap_ct_per_kwh: float = 5.0


class Settings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8081
    offchain_db_url: str = "http://localhost:8080"
    rpc_url: str = "https://volta-rpc.energyweb.org"
    contract_address: str = ""  # empty disables the optional on-chain step
    audit_anchor_private_key: str = ""
    time_slot_sec: int = 900
    communities: dict[str, CommunityConfig] = {}

    # Off-chain transport: "rest" (direct off-chain DB API / local simulator)
    # or "ewds" (publish/poll via the EW CGW gateway).
    offchain_transport: str = "rest"

    # Self-trigger scheduler: periodically discover closed AMM markets via the
    # market list and clear them (GSY: no market-close event exists). Off by
    # default; POST /trigger-clearing always works regardless.
    scheduler_enabled: bool = False
    scheduler_poll_interval_sec: int = 60
    # Strict: drop inbound orders failing int:Order validation. Lenient (False):
    # log the violation and still attempt conversion — needed against the GSY
    # staging gateway until their DTOs are aligned with the ontology.
    strict_order_validation: bool = True

    # EWDS gateway settings (defaults mirror GSY's EwdsClient).
    ewds_gateway_url: str = "http://ewds-gateway-api:3333"
    ewds_request_fqcn: str = "gsy.intelligent.requests.pub"
    ewds_response_fqcn: str = "gsy.intelligent.responses.sub"
    ewds_topic_owner: str = "integration.apps.intelligent.auth.ewc"
    ewds_topic_version: str = "1.0.0"
    ewds_client_id: str = "ammclearingnode"
    ewds_response_timeout_ms: int = 60000
    ewds_poll_interval_ms: int = 1000  # initial response-poll delay
    ewds_poll_max_interval_ms: int = 5000  # back-off ceiling
    ewds_empty_response_grace_ms: int = 10000  # wait for a non-empty response
    ewds_publish_backoff_ms: int = 2000  # first re-publish delay (undelivered/429)
    ewds_publish_max_backoff_ms: int = 30000  # re-publish back-off ceiling


# Environment variable overrides; they always win over the YAML file. An empty
# variable counts as unset, so ``PORT=`` falls back to the default.
_ENV_FIELDS = {
    "OFFCHAIN_DB_URL": "offchain_db_url",
    "OFFCHAIN_TRANSPORT": "offchain_transport",
    "RPC_URL": "rpc_url",
    "CONTRACT_ADDRESS": "contract_address",
    "TIME_SLOT_SEC": "time_slot_sec",
    "HOST": "host",
    "PORT": "port",
    "EWDS_GATEWAY_URL": "ewds_gateway_url",
    "EWDS_TOPIC_OWNER": "ewds_topic_owner",
    "EWDS_TOPIC_VERSION": "ewds_topic_version",
    "EWDS_RESPONSE_TIMEOUT_MS": "ewds_response_timeout_ms",
    "EWDS_RESPONSE_POLL_INTERVAL_MS": "ewds_poll_interval_ms",
    "EWDS_RESPONSE_POLL_MAX_INTERVAL_MS": "ewds_poll_max_interval_ms",
    "EWDS_EMPTY_RESPONSE_GRACE_MS": "ewds_empty_response_grace_ms",
    "EWDS_RATE_LIMIT_BACKOFF_MS": "ewds_publish_backoff_ms",
    "EWDS_RATE_LIMIT_MAX_BACKOFF_MS": "ewds_publish_max_backoff_ms",
    "SCHEDULER_POLL_INTERVAL_SEC": "scheduler_poll_interval_sec",
}
_INT_FIELDS = {
    "time_slot_sec",
    "port",
    "ewds_response_timeout_ms",
    "ewds_poll_interval_ms",
    "ewds_poll_max_interval_ms",
    "ewds_empty_response_grace_ms",
    "ewds_publish_backoff_ms",
    "ewds_publish_max_backoff_ms",
    "scheduler_poll_interval_sec",
}
# Fallback chains matching GSY's EwdsClient env conventions: the first set
# variable wins.
_ENV_FALLBACK_CHAINS = {
    "ewds_request_fqcn": ("EWDS_REQUEST_PUBLISH_FQCN", "EWDS_REQUEST_FQCN"),
    "ewds_response_fqcn": ("EWDS_RESPONSE_SUBSCRIBE_FQCN", "EWDS_RESPONSE_FQCN"),
    "ewds_client_id": ("EWDS_AMM_CLIENT_ID", "EWDS_RESPONSE_CLIENT_ID"),
    # CLEARING_NODE_PRIVATE_KEY is the former name, still read by existing deployments.
    "audit_anchor_private_key": ("AUDIT_ANCHOR_PRIVATE_KEY", "CLEARING_NODE_PRIVATE_KEY"),
}
_ENV_BOOL_FIELDS = {
    "OFFCHAIN_STRICT_VALIDATION": "strict_order_validation",
    "SCHEDULER_ENABLED": "scheduler_enabled",
}


def _yaml_settings(config_path: Path) -> dict:
    """Settings from the YAML file; empty when the file does not exist."""
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}
    app = raw.get("application", {})
    blockchain = raw.get("blockchain", {})
    return {
        "host": app.get("host", "0.0.0.0"),
        "port": app.get("port", 8081),
        "offchain_db_url": raw.get("offchain_db", {}).get("base_url", "http://localhost:8080"),
        "rpc_url": blockchain.get("rpc_url", "https://volta-rpc.energyweb.org"),
        "contract_address": blockchain.get("contract_address", ""),
        "time_slot_sec": raw.get("market", {}).get("time_slot_sec", 900),
        "communities": {
            cid: CommunityConfig(**cdata) for cid, cdata in raw.get("communities", {}).items()
        },
    }


def _env_bool(key: str) -> bool | None:
    raw = (os.environ.get(key) or "").strip().lower()
    if not raw:
        return None
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{key} must be true/false, got {raw!r}")


def _env_overrides() -> dict:
    """Settings from environment variables."""
    data: dict = {}
    for env_key, field in _ENV_FIELDS.items():
        val = os.environ.get(env_key)
        if val:
            data[field] = int(val) if field in _INT_FIELDS else val
    for field, env_keys in _ENV_FALLBACK_CHAINS.items():
        val = next((os.environ[k] for k in env_keys if os.environ.get(k)), None)
        if val:
            data[field] = val
    for env_key, field in _ENV_BOOL_FIELDS.items():
        flag = _env_bool(env_key)
        if flag is not None:
            data[field] = flag
    return data


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from YAML, then override with environment variables."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "configuration.yaml"
    return Settings(**{**_yaml_settings(config_path), **_env_overrides()})
