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
    pool_id: str
    # Actor identity (UUID) the AMM pool trades as on the int:Trade wire. The
    # pool is a virtual counterparty; this is the FK used as buyerId/sellerId for
    # pool trades. Provisional pending GSY's pool-registration decision.
    pool_actor_uuid: str


class Settings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8081
    offchain_db_url: str = "http://localhost:8080"
    rpc_url: str = "https://volta-rpc.energyweb.org"
    contract_address: str = "0x0000000000000000000000000000000000000000"
    clearing_node_private_key: str = ""
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
    ewds_poll_interval_ms: int = 400


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from YAML, then override with environment variables."""
    data: dict = {}

    if config_path is None:
        config_path = Path(__file__).parent.parent / "configuration.yaml"

    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

        app = raw.get("application", {})
        data["host"] = app.get("host", "0.0.0.0")
        data["port"] = app.get("port", 8081)
        data["offchain_db_url"] = raw.get("offchain_db", {}).get(
            "base_url", "http://localhost:8080"
        )
        data["rpc_url"] = raw.get("blockchain", {}).get(
            "rpc_url", "https://volta-rpc.energyweb.org"
        )
        data["contract_address"] = raw.get("blockchain", {}).get("contract_address", "")
        data["time_slot_sec"] = raw.get("market", {}).get("time_slot_sec", 900)

        communities_raw = raw.get("communities", {})
        communities = {}
        for cid, cdata in communities_raw.items():
            communities[cid] = CommunityConfig(**cdata)
        data["communities"] = communities

    # Environment variable overrides always win
    env_map = {
        "OFFCHAIN_DB_URL": "offchain_db_url",
        "OFFCHAIN_TRANSPORT": "offchain_transport",
        "RPC_URL": "rpc_url",
        "CONTRACT_ADDRESS": "contract_address",
        "CLEARING_NODE_PRIVATE_KEY": "clearing_node_private_key",
        "TIME_SLOT_SEC": "time_slot_sec",
        "HOST": "host",
        "PORT": "port",
        "EWDS_GATEWAY_URL": "ewds_gateway_url",
        "EWDS_TOPIC_OWNER": "ewds_topic_owner",
        "EWDS_TOPIC_VERSION": "ewds_topic_version",
        "EWDS_RESPONSE_TIMEOUT_MS": "ewds_response_timeout_ms",
        "EWDS_RESPONSE_POLL_INTERVAL_MS": "ewds_poll_interval_ms",
    }
    int_fields = {"time_slot_sec", "port", "ewds_response_timeout_ms", "ewds_poll_interval_ms"}
    for env_key, field in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            data[field] = int(val) if field in int_fields else val

    # Fallback chains matching GSY's EwdsClient env conventions.
    fallback_chains = {
        "ewds_request_fqcn": ("EWDS_REQUEST_PUBLISH_FQCN", "EWDS_REQUEST_FQCN"),
        "ewds_response_fqcn": ("EWDS_RESPONSE_SUBSCRIBE_FQCN", "EWDS_RESPONSE_FQCN"),
        "ewds_client_id": ("EWDS_AMM_CLIENT_ID", "EWDS_RESPONSE_CLIENT_ID"),
    }
    for field, env_keys in fallback_chains.items():
        for env_key in env_keys:
            val = os.environ.get(env_key)
            if val:
                data[field] = val
                break

    def _env_bool(key: str) -> bool | None:
        raw = os.environ.get(key)
        if raw is None:
            return None
        return raw.strip().lower() not in ("0", "false", "no")

    strict = _env_bool("OFFCHAIN_STRICT_VALIDATION")
    if strict is not None:
        data["strict_order_validation"] = strict

    sched = _env_bool("SCHEDULER_ENABLED")
    if sched is not None:
        data["scheduler_enabled"] = sched
    interval = os.environ.get("SCHEDULER_POLL_INTERVAL_SEC")
    if interval is not None:
        data["scheduler_poll_interval_sec"] = int(interval)

    return Settings(**data)
