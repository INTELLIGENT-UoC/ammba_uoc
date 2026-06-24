# amm-calibration

Offline calibration of the AMMBA sigmoid parameters (`theta`, `steepness`) per
community, from historical measurements. It ports the optimization from the
AMMBA research code (`optimize_parameters_ammba`): find the sigmoid shape that
maximizes the worst-off average return — `min(buyer_utility, seller_profit)` —
across historical slots, with a penalty that makes the price span the full
`[k_lower, k_upper]` band.

This is an **offline job**, run on a slow cadence (seasonal / monthly),
completely decoupled from the 15-minute clearing path. It is not a service.

It is **dependency-free** at the algorithm level (no numpy/scipy/pandas): the 2-D
bounded optimization is a deterministic coarse-to-fine grid search. Only `pyyaml`
is used, for emitting config.

## Run

```bash
uv sync --extra dev
uv run pytest -q

uv run python -m src.calibrate \
  --measurements history.json \
  --community 11111111-1111-4111-8111-111111111111 \
  --k-upper 28.5 --k-lower 8.0 --alpha 0.5 \
  --pool-id AMM_POOL_x --pool-actor-uuid 22222222-2222-4222-8222-222222222222 \
  --out params.yaml
```

`history.json` is a list of `int:Measurement` objects (the GSY DEX ontology
shape). The output is a `communities:` snippet you merge into
`amm-clearing-node/configuration.yaml` (and/or anchor via
`AMMContract.setCommunityParams`).

## Inputs and assumptions (provisional — see ../INTEGRATION_NOTES.md)

- **Measurement sign**: net-load convention — positive `energyKwh` is
  consumption (demand), negative is injection (supply). Flip with
  `--injection-positive` if GSY confirms the opposite.
- **Price bounds**: `k_upper`/`k_lower` are applied flat to every slot (passed
  in). A per-slot tariff series can replace this when one is available.
- **Data needs ratio spread**: meaningful calibration requires history that
  spans scarce → abundant conditions. On the reference dataset the optimizer
  recovers ≈ `theta=1.0, steepness=2.5`, matching the shipped config.

## Note on the price function

`src/pricing.py` is the **unclamped** sigmoid (matching the paper), unlike the
clearing node's clamped `sigmoid.py`. Calibration needs the unclamped form so
the range-usage penalty is meaningful; the clearing node clamps for runtime
safety. Keep the core formula in sync across all three copies.
