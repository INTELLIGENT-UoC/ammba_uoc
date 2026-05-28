"""Configuration loader for the Execution Node."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class CommunityConfig(BaseModel):
    k_upper_ct_per_kwh: float
    k_lower_ct_per_kwh: float
    theta: float
    steepness: float


class PenaltyConfig(BaseModel):
    gamma: float = 1.1
    eta: float = 0.0


class Settings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8082
    offchain_db_url: str = "http://localhost:8080"
    time_slot_sec: int = 900
    execution_offset_min: int = -120
    polling_interval_sec: int = 300
    penalties: PenaltyConfig = PenaltyConfig()
    communities: dict[str, CommunityConfig] = {}


def load_settings(config_path: Path | None = None) -> Settings:
    data: dict = {}

    if config_path is None:
        config_path = Path(__file__).parent.parent / "configuration.yaml"

    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

        app = raw.get("application", {})
        data["host"] = app.get("host", "0.0.0.0")
        data["port"] = app.get("port", 8082)
        data["offchain_db_url"] = raw.get("offchain_db", {}).get(
            "base_url", "http://localhost:8080"
        )

        market = raw.get("market", {})
        data["time_slot_sec"] = market.get("time_slot_sec", 900)
        data["execution_offset_min"] = market.get("execution_offset_min", -120)
        data["polling_interval_sec"] = market.get("polling_interval_sec", 300)

        penalties_raw = raw.get("penalties", {})
        data["penalties"] = PenaltyConfig(**penalties_raw)

        communities_raw = raw.get("communities", {})
        communities = {}
        for cid, cdata in communities_raw.items():
            communities[cid] = CommunityConfig(**cdata)
        data["communities"] = communities

    # Environment variable overrides
    env_map = {
        "OFFCHAIN_DB_URL": "offchain_db_url",
        "TIME_SLOT_SEC": "time_slot_sec",
        "EXECUTION_OFFSET_MIN": "execution_offset_min",
        "POLLING_INTERVAL_SEC": "polling_interval_sec",
    }
    for env_key, field in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            data[field] = int(val)

    return Settings(**data)
