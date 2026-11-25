"""Check that the three copies of the AMMBA pricing function agree.

The sigmoid price function exists in three places that cannot import each
other (separate uv projects):

- ``amm-clearing-node/src/sigmoid.py``   clamped, used for clearing
- ``amm-execution-node/src/sigmoid.py``  clamped, counterfactual prices for penalties
- ``amm-calibration/src/pricing.py``     unclamped, used by the optimizer

The sigmoid's value lies inside ``[k_lower, k_upper]``, so the clamped and the
unclamped copies must return the same price. This script evaluates all three
on a grid of supply/demand ratios and parameters, including the degenerate
band and the overflow guards, and exits non-zero on any disagreement.

Standard library only; run from the repository root:

    python3 scripts/check_pricing_copies.py
"""

import importlib.util
import itertools
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COPIES = {
    "clearing-node": (ROOT / "amm-clearing-node/src/sigmoid.py", "sigmoid_price"),
    "execution-node": (ROOT / "amm-execution-node/src/sigmoid.py", "sigmoid_price"),
    "calibration": (ROOT / "amm-calibration/src/pricing.py", "sigmoid_price_unclamped"),
}

RATIOS = [0.0, 1e-6, 0.01, 0.1, 0.25, 0.4, 0.5, 0.75, 0.9, 0.99, 1.0, 1.01, 1.1, 1.5]
RATIOS += [2.0, 3.0, 5.0, 10.0, 100.0, 1e6]
# (k_upper, k_lower) in ct/kWh, including an empty and an inverted band.
BANDS = [(28.5, 8.0), (40.0, 0.0), (12.0, 11.5), (8.0, 8.0), (8.0, 28.5)]
THETAS = [0.5, 1.0, 1.5, 2.0]
# Large steepness values drive the exponent past the overflow guards.
STEEPNESSES = [0.0, 0.1, 1.0, 2.5, 10.0, 100.0, 1000.0, 1e5]

REL_TOL = 1e-12
ABS_TOL = 1e-9  # ct/kWh


def load(name: str, path: Path, func: str):
    spec = importlib.util.spec_from_file_location(f"pricing_copy_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, func)


def main() -> int:
    funcs = {name: load(name, path, func) for name, (path, func) in COPIES.items()}
    reference, *others = funcs
    mismatches = []
    points = 0
    for ratio, (k_upper, k_lower), theta, steepness in itertools.product(
        RATIOS, BANDS, THETAS, STEEPNESSES
    ):
        args = (ratio, k_upper, k_lower, theta, steepness)
        prices = {name: f(*args) for name, f in funcs.items()}
        points += 1
        for name in others:
            if not math.isclose(prices[reference], prices[name], rel_tol=REL_TOL, abs_tol=ABS_TOL):
                mismatches.append((args, prices))
                break

    if mismatches:
        print(f"Pricing copies disagree at {len(mismatches)} of {points} points:")
        for (ratio, k_upper, k_lower, theta, steepness), prices in mismatches[:20]:
            print(
                f"  ratio={ratio} k_upper={k_upper} k_lower={k_lower} "
                f"theta={theta} steepness={steepness}: {prices}"
            )
        print("Keep the formula identical in:")
        for path, _ in COPIES.values():
            print(f"  {path.relative_to(ROOT)}")
        return 1

    print(f"Pricing copies agree at {points} points ({', '.join(funcs)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
