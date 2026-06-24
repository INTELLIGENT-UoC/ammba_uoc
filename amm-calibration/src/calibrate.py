"""Calibration entrypoint: measurements -> optimal sigmoid params -> config.

Offline job, run on a slow cadence (seasonal / monthly), decoupled from the
15-minute clearing path. It reads historical measurements, optimizes the sigmoid
shape per community, and emits parameters in the clearing node's config shape.

Where the output goes (provisional): we emit a YAML snippet that maps onto the
clearing node's ``communities:`` block. For now you merge it into
``amm-clearing-node/configuration.yaml`` (and/or call
``AMMContract.setCommunityParams`` to anchor it on-chain). When an
``int:AmmParameters`` ontology object exists, this becomes a write to the
off-chain DB that the clearing node fetches live — see INTEGRATION_NOTES.md.

Usage:
    uv run python -m src.calibrate \
        --measurements history.json \
        --community 11111111-1111-4111-8111-111111111111 \
        --k-upper 28.5 --k-lower 8.0 --alpha 0.5 \
        --pool-id AMM_POOL_x --pool-actor-uuid <uuid> --out params.yaml
"""

import argparse
import json
import sys

import yaml

from src.measurements import aggregate_slots
from src.optimizer import DEFAULT_ALPHA, optimize_params


def calibrate(
    measurements: list[dict],
    k_upper: float,
    k_lower: float,
    community_uuid: str | None = None,
    alpha: float = DEFAULT_ALPHA,
    positive_is_consumption: bool = True,
) -> dict:
    """Optimize ``(theta, steepness)`` from a measurement history."""
    slots = aggregate_slots(
        measurements,
        k_upper=k_upper,
        k_lower=k_lower,
        community_uuid=community_uuid,
        positive_is_consumption=positive_is_consumption,
    )
    if not slots:
        raise ValueError("No usable market slots aggregated from measurements")
    return optimize_params(slots, alpha=alpha)


def to_config_snippet(
    community_uuid: str,
    k_upper: float,
    k_lower: float,
    params: dict,
    pool_id: str | None = None,
    pool_actor_uuid: str | None = None,
) -> dict:
    """Render a clearing-node ``communities:`` entry for the calibrated params."""
    entry = {
        "k_upper_ct_per_kwh": k_upper,
        "k_lower_ct_per_kwh": k_lower,
        "theta": params["theta"],
        "steepness": params["steepness"],
    }
    if pool_id is not None:
        entry["pool_id"] = pool_id
    if pool_actor_uuid is not None:
        entry["pool_actor_uuid"] = pool_actor_uuid
    return {"communities": {community_uuid: entry}}


def load_measurements(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate AMMBA sigmoid params")
    parser.add_argument("--measurements", required=True, help="JSON list of int:Measurement")
    parser.add_argument("--community", default=None, help="communityUuid filter")
    parser.add_argument("--k-upper", type=float, required=True)
    parser.add_argument("--k-lower", type=float, required=True)
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    parser.add_argument("--pool-id", default=None)
    parser.add_argument("--pool-actor-uuid", default=None)
    parser.add_argument(
        "--injection-positive",
        action="store_true",
        help="energyKwh is positive for injection (flip the default net-load sign)",
    )
    parser.add_argument("--out", default=None, help="write config snippet to this YAML file")
    args = parser.parse_args(argv)

    measurements = load_measurements(args.measurements)
    params = calibrate(
        measurements,
        k_upper=args.k_upper,
        k_lower=args.k_lower,
        community_uuid=args.community,
        alpha=args.alpha,
        positive_is_consumption=not args.injection_positive,
    )
    print(
        f"Calibrated {args.community or '(all)'}: "
        f"theta={params['theta']} steepness={params['steepness']} "
        f"(objective={params['objective']:.4f}, n_slots={params['n_slots']})",
        file=sys.stderr,
    )

    snippet = to_config_snippet(
        args.community or "<community_uuid>",
        args.k_upper,
        args.k_lower,
        params,
        pool_id=args.pool_id,
        pool_actor_uuid=args.pool_actor_uuid,
    )
    rendered = yaml.safe_dump(snippet, sort_keys=False)
    if args.out:
        with open(args.out, "w") as f:
            f.write(rendered)
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
