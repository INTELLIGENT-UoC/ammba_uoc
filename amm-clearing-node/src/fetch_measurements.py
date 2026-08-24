"""Fetch measurement history over the EWDS gateway for offline calibration.

Bridges the gateway to the dependency-free ``amm-calibration`` job: pull the
int:Measurement records for a community and time window, write them to a JSON
file, and feed that file to ``amm-calibration``'s ``--measurements`` input.

Usage:
    uv run python -m src.fetch_measurements \
        --start 2026-07-01T00:00:00Z --end 2026-08-01T00:00:00Z \
        --community 11111111-1111-4111-8111-111111111111 \
        --out measurements.json

``--start``/``--end`` accept unix seconds or ISO-8601. The gateway settings
come from the usual environment variables (``EWDS_GATEWAY_URL`` etc.) unless
``--gateway-url`` overrides them.
"""

import argparse
import asyncio
import json
import sys

from src.adapters import iso_to_unix
from src.config import load_settings
from src.ewds_client import EwdsConfig, EwdsOffchainClient


def _parse_time(value: str) -> int:
    if value.isdigit():
        return int(value)
    return iso_to_unix(value)


async def fetch(args: argparse.Namespace) -> int:
    settings = load_settings()
    config = EwdsConfig(
        gateway_url=args.gateway_url or settings.ewds_gateway_url,
        request_fqcn=settings.ewds_request_fqcn,
        response_fqcn=settings.ewds_response_fqcn,
        topic_owner=settings.ewds_topic_owner,
        topic_version=settings.ewds_topic_version,
        client_id=settings.ewds_client_id,
        timeout_ms=settings.ewds_response_timeout_ms,
        poll_interval_ms=settings.ewds_poll_interval_ms,
    )
    client = EwdsOffchainClient(config)
    try:
        measurements = await client.get_measurements(
            start_time=_parse_time(args.start),
            end_time=_parse_time(args.end),
            community_uuid=args.community,
            facility_id=args.facility,
        )
    finally:
        await client.close()

    with open(args.out, "w") as f:
        json.dump(measurements, f, indent=2)
    print(
        f"Wrote {len(measurements)} measurements to {args.out}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch int:Measurement history over EWDS for calibration"
    )
    parser.add_argument("--start", required=True, help="window start (unix seconds or ISO-8601)")
    parser.add_argument("--end", required=True, help="window end (unix seconds or ISO-8601)")
    parser.add_argument("--community", default=None, help="communityUuid filter")
    parser.add_argument("--facility", default=None, help="facilityId filter")
    parser.add_argument("--gateway-url", default=None, help="override EWDS_GATEWAY_URL")
    parser.add_argument("--out", default="measurements.json", help="output JSON file")
    args = parser.parse_args(argv)
    return asyncio.run(fetch(args))


if __name__ == "__main__":
    raise SystemExit(main())
