"""AMM settlement engine CLI (skeleton).

Dry-run is the only mode until the settlement environment is available
(frozen contracts and addresses, OPERATOR_ROLE grant, target chain, funded
signer). ``--execute`` exists but exits with a checklist of exactly what is
still missing.

Usage:
    uv run python -m src.main --trades trades.json --orders orders.json \
        --clearing-results results.json

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

    build = build_settlements(trades, orders_by_id, clearing_results)
    violations = validate_batch(build.settlements)

    plan = {
        "markets": len(build.settlements),
        "matches": len(build.matches),
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
            "prerequisites (OPERATOR_ROLE grant for the settlement signer).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
