"""Generate a test data set for a GSY DEX staging environment.

Staging receives no live orders or metering data, so its off-chain storage is
seeded with test data instead. This module writes one UTC day of AMM markets
for a dedicated test community, the orders of a few synthetic participants for
every market, and metering history for the days before, all as ``int.*``
objects validated against the vendored schemas.

Usage:
    uv run python -m sim.staging_seed --date 2026-11-10 --out staging-seed

The output directory holds ``seed_markets.json``, ``seed_orders.json`` and
``seed_measurements.json`` (the simulator's file names, so ``SIM_SEED_DIR``
can serve the same set locally first) and ``community.yaml``, the block to add
under ``communities:`` in ``configuration.yaml``.

Every market of the day is an AMM market, so markets keep closing while the day
runs and the self-trigger scheduler (which looks back 24 hours) always has work.
Every market carries at least one bid and one offer, and one mutual preferred
pair. The ratio of supply to demand moves from well below the sigmoid midpoint
in the evening peak to the clamped band at midday. Price limits sit outside the
community's price band: AMM clearing ignores them, but on-chain settlement
checks them against the clearing price.

The output is deterministic: IDs are ``uuid5`` values derived from labels and
times, so regenerating a date reproduces the same objects (safe to upsert).
"""

import argparse
import hashlib
import json
import math
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from src.ontology import validate, validate_order

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ammba.uoc/staging-seed")

MARKET_SCHEMA = "int.market.schema.v1.json"
MEASUREMENT_SCHEMA = "int.measurement.schema.v1.json"

SLOT = timedelta(minutes=15)
SLOTS_PER_DAY = 96
ORDER_WINDOW = timedelta(minutes=30)  # a market opens 30 min before delivery

# Community parameters, mirrored into community.yaml (ct/kWh, as in the config).
K_UPPER_CT = 28.5
K_LOWER_CT = 8.0
BID_LIMIT = 0.30  # EUR/kWh, above K_UPPER_CT
OFFER_LIMIT = 0.07  # EUR/kWh, below K_LOWER_CT

# Participants: label, base load (buyers, kWh per slot) or peak output (sellers).
HOUSEHOLDS = (("household-1", 0.45), ("household-2", 0.35), ("household-3", 0.60))
BAKERY = ("bakery", 1.20)
PV = (("pv-roof-1", 3.0), ("pv-roof-2", 2.0))
CHP = ("biomass-chp", 0.80)  # constant output, so every market has an offer
PREFERRED_PAIR = ("household-1", "biomass-chp")
GREEN_BUYER = "household-2"  # bids with energySourcePreference GREEN


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(_NS, label))


def community_uuid() -> str:
    return stable_uuid("community:ammba-staging-test")


def pool_actor_uuid() -> str:
    return stable_uuid("actor:pool")


def actor_uuid(label: str) -> str:
    return stable_uuid(f"actor:{label}")


def facility_uuid(label: str) -> str:
    return stable_uuid(f"facility:{label}")


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _unit(label: str) -> float:
    """Deterministic pseudo-random number in [0, 1) from a label."""
    return int(hashlib.sha256(label.encode()).hexdigest()[:8], 16) / 2**32


def _bump(hour: float, centre: float, width: float) -> float:
    return math.exp(-(((hour - centre) / width) ** 2))


def household_load(base: float, hour: float) -> float:
    """Night base, a morning peak and a stronger evening peak."""
    return base * (0.6 + 0.5 * _bump(hour, 7.5, 1.5) + 0.9 * _bump(hour, 19.0, 2.0))


def bakery_load(base: float, hour: float) -> float:
    """Ovens in the early morning, shop hours until the afternoon."""
    return base * (0.2 + 1.3 * _bump(hour, 5.0, 1.5) + 0.4 * (7.0 <= hour < 15.0))


def pv_output(peak: float, hour: float) -> float:
    """Clear-sky output between 07:00 and 17:00 UTC."""
    if not 7.0 < hour < 17.0:
        return 0.0
    return peak * math.sin(math.pi * (hour - 7.0) / 10.0) ** 1.5


def _slot_quantities(hour: float) -> tuple[dict[str, float], dict[str, float]]:
    """Demand per buyer and supply per seller (kWh) for the slot at ``hour``."""
    demand = {label: household_load(base, hour) for label, base in HOUSEHOLDS}
    demand[BAKERY[0]] = bakery_load(BAKERY[1], hour)
    supply = {label: pv_output(peak, hour) for label, peak in PV}
    supply[CHP[0]] = CHP[1]
    return demand, supply


def _energy_type(seller: str) -> str:
    return "BIOMASS" if seller == CHP[0] else "PV"


def build_market(start: datetime) -> dict:
    opening = start - ORDER_WINDOW
    return {
        "marketId": stable_uuid(f"market:{community_uuid()}:{_iso(start)}"),
        "communityId": community_uuid(),
        "openingTime": _iso(opening),
        "closingTime": _iso(start),
        "deliveryStartTime": _iso(start),
        "deliveryEndTime": _iso(start + SLOT),
        "marketType": "spot",
        "matchingAlgorithm": "amm",
        "createdAt": _iso(opening),
    }


def build_orders(market: dict, start: datetime) -> list[dict]:
    hour = start.hour + start.minute / 60 + 0.125  # slot midpoint
    demand, supply = _slot_quantities(hour)
    opening = start - ORDER_WINDOW
    orders = []
    sides = [(label, "bid", qty) for label, qty in demand.items()]
    sides += [(label, "offer", qty) for label, qty in supply.items()]
    for index, (label, side, quantity) in enumerate(sides):
        quantity = round(quantity, 3)
        if quantity < 0.01:
            continue  # no PV output at night: the producer places no order
        order = {
            "orderId": stable_uuid(f"order:{market['marketId']}:{label}"),
            "marketId": market["marketId"],
            "orderType": side,
            "orderStatus": "submitted",
            "timeSlot": _iso(start),
            "quantity": quantity,
            "priceLimit": BID_LIMIT if side == "bid" else OFFER_LIMIT,
            "createdBy": actor_uuid(label),
            "creationTime": _iso(opening + timedelta(minutes=5 + 3 * index)),
        }
        if side == "offer":
            order["energyType"] = _energy_type(label)
        if label == GREEN_BUYER:
            order["energySourcePreference"] = "GREEN"
        if label in PREFERRED_PAIR:
            partner = PREFERRED_PAIR[1] if label == PREFERRED_PAIR[0] else PREFERRED_PAIR[0]
            order["preferredTradingPartner"] = actor_uuid(partner)
        orders.append(order)
    return orders


def build_measurements(day: date) -> list[dict]:
    """Net-load metering for every participant and slot of ``day``.

    Positive ``energyKwh`` is consumption, negative is injection (the agreed
    convention, see amm-calibration). Cloud cover varies by day, and every
    reading deviates a little from the planned quantities.
    """
    weather = 0.4 + 0.6 * _unit(f"weather:{day.isoformat()}")
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    records = []
    for slot in range(SLOTS_PER_DAY):
        start = midnight + slot * SLOT
        hour = start.hour + start.minute / 60 + 0.125
        demand, supply = _slot_quantities(hour)
        readings = dict(demand)
        for label, quantity in supply.items():
            readings[label] = -quantity * (weather if label != CHP[0] else 1.0)
        for label, energy in readings.items():
            noise = 0.9 + 0.2 * _unit(f"noise:{label}:{_iso(start)}")
            records.append(
                {
                    "facilityId": facility_uuid(label),
                    "communityUuid": community_uuid(),
                    "timeSlot": _iso(start),
                    "creationTime": _iso(start + SLOT),
                    "energyKwh": round(energy * noise, 3) + 0.0,  # + 0.0 drops -0.0
                }
            )
    return records


def build_seed(day: date, history_days: int = 2) -> dict[str, list[dict]]:
    """Markets and orders for ``day`` plus metering for the days before it."""
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    markets, orders = [], []
    for slot in range(SLOTS_PER_DAY):
        start = midnight + slot * SLOT
        market = build_market(start)
        markets.append(market)
        orders.extend(build_orders(market, start))
    measurements = []
    for back in range(history_days, 0, -1):
        measurements.extend(build_measurements(day - timedelta(days=back)))

    for market in markets:
        validate(market, MARKET_SCHEMA)
    for order in orders:
        validate_order(order)
    for measurement in measurements:
        validate(measurement, MEASUREMENT_SCHEMA)
    return {"markets": markets, "orders": orders, "measurements": measurements}


def community_snippet() -> str:
    return (
        "# Test community of sim.staging_seed: add under `communities:` in configuration.yaml.\n"
        f"{community_uuid()}:\n"
        f"  k_upper_ct_per_kwh: {K_UPPER_CT}\n"
        f"  k_lower_ct_per_kwh: {K_LOWER_CT}\n"
        "  theta: 1.0\n"
        "  steepness: 2.5\n"
        '  pool_id: "AMM_POOL_staging_test"\n'
        f'  pool_actor_uuid: "{pool_actor_uuid()}"\n'
    )


def write_seed(seed: dict[str, list[dict]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("markets", "orders", "measurements"):
        with open(out_dir / f"seed_{name}.json", "w") as f:
            json.dump(seed[name], f, indent=2)
            f.write("\n")
    (out_dir / "community.yaml").write_text(community_snippet())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an AMM test data set for staging")
    parser.add_argument("--date", required=True, help="UTC day of the markets (YYYY-MM-DD)")
    parser.add_argument(
        "--history-days", type=int, default=2, help="days of metering before --date"
    )
    parser.add_argument("--out", default="staging-seed", help="output directory")
    args = parser.parse_args(argv)

    day = date.fromisoformat(args.date)
    seed = build_seed(day, args.history_days)
    write_seed(seed, Path(args.out))
    print(
        f"Wrote {len(seed['markets'])} markets, {len(seed['orders'])} orders and "
        f"{len(seed['measurements'])} measurements to {args.out}/ "
        f"(community {community_uuid()})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
