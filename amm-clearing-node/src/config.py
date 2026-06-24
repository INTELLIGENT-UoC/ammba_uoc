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
        data["contract_address"] = raw.get("blockchain", {}).get(
            "contract_address", ""
        )
        data["time_slot_sec"] = raw.get("market", {}).get("time_slot_sec", 900)

        communities_raw = raw.get("communities", {})
        communities = {}
        for cid, cdata in communities_raw.items():
            communities[cid] = CommunityConfig(**cdata)
        data["communities"] = communities

    # Environment variable overrides always win
    env_map = {
        "OFFCHAIN_DB_URL": "offchain_db_url",
        "RPC_URL": "rpc_url",
        "CONTRACT_ADDRESS": "contract_address",
        "CLEARING_NODE_PRIVATE_KEY": "clearing_node_private_key",
        "TIME_SLOT_SEC": "time_slot_sec",
        "HOST": "host",
        "PORT": "port",
    }
    for env_key, field in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            if field in ("time_slot_sec", "port"):
                data[field] = int(val)
            else:
                data[field] = val

    return Settings(**data)
