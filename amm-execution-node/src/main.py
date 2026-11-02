"""AMM settlement engine CLI (skeleton).

Dry-run is the only mode until the settlement environment is available
(frozen contracts and addresses, OPERATOR_ROLE grant, target chain, funded
signer). ``--execute`` exists but exits with a checklist of exactly what is
still missing.

Usage:
    uv run python -m src.main --trades trades.json --orders orders.json \
        --clearing-results results.json \
        --pool-actor <uuid> --k-upper 0.285 --k-lower 0.08

``trades.json``: int:Trade list (the clearing node's output).
``orders.json``: int:Order list (the orders the trades reference).
``results.json``: int:ClearingResult list, one per market the trades belong to.
"""

import argparse
import json
import os
import sys

from src.match_builder import build_settlements
from src.validator import validate_batch

EXECUTION_ENV = [
    "SETTLEMENT_RPC_URL",
    "ORDER_REGISTRY_ADDRESS",
    "TRADE_SETTLEMENT_ADDRESS",
    "SETTLEMENT_PRIVATE_KEY",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AMM settlement engine (skeleton)")
    parser.add_argument("--trades", help="int:Trade JSON list from the clearing node")
    parser.add_argument("--orders", help="int:Order JSON list referenced by the trades")
    parser.add_argument(
        "--clearing-results", help="int:ClearingResult JSON list, one per market of the trades"
    )
    parser.add_argument("--pool-actor", help="pool actor UUID")
    parser.add_argument(
        "--k-upper", type=float, help="community price ceiling, in the unit of tradePrice (EUR/kWh)"
    )
    parser.add_argument(
        "--k-lower", type=float, help="community price floor, in the unit of tradePrice (EUR/kWh)"
    )
    parser.add_argument("--execute", action="store_true", help="submit transactions (needs env)")
    args = parser.parse_args(argv)

    if not args.trades:
        parser.print_help()
        print(
            "\nSkeleton status: dry-run planning works; --execute is blocked on "
            "the settlement environment (contracts freeze, role grant, chain, "
            "funded key).",
            file=sys.stderr,
        )
        return 0

    with open(args.trades) as f:
        trades = json.load(f)
    with open(args.orders) as f:
        orders = json.load(f)
    orders_by_id = {o["orderId"]: o for o in orders}
    with open(args.clearing_results) as f:
        clearing_results = json.load(f)

    build = build_settlements(
        trades,
        orders_by_id,
        clearing_results,
        pool_actor_uuid=args.pool_actor,
        k_upper=args.k_upper,
        k_lower=args.k_lower,
    )
    violations = validate_batch(build.settlements)

    plan = {
        "markets": len(build.settlements),
        "matches": len(build.matches),
        "pool_orders_to_place": [p.order_id for p in build.pool_orders],
        "preflight_rejections": {
            market: [f"{v.subject} {v.code}: {v.detail}" for v in vs]
            for market, vs in violations.items()
        },
        "settleable_markets": [
            s.market_id for s in build.settlements if s.market_id not in violations
        ],
    }
    print(json.dumps(plan, indent=2))

    if args.execute:
        missing = [key for key in EXECUTION_ENV if not os.environ.get(key)]
        print(
            "\n--execute unavailable: missing environment "
            f"({', '.join(missing) if missing else 'none'}) and the upstream "
            "prerequisites (OPERATOR_ROLE grant, ActorRegistry authorization for "
            "the pool actor, market-open placement rule for pool orders).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
