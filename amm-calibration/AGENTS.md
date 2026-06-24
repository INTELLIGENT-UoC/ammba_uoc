# AGENTS.md — amm-calibration

> Component-specific onboarding. See the [repo-root AGENTS.md](../AGENTS.md)
> for the big picture first.

## What this component does

Offline calibration of the per-community sigmoid parameters (`theta`,
`steepness`) from historical `int:Measurement` data. Ported from the AMMBA
research optimizer (`optimize_parameters_ammba`). Run on a slow cadence
(seasonal / monthly), decoupled from the clearing service — it is a job, not a
server.

## File map

```
src/
├── pricing.py       # UNCLAMPED sigmoid (paper version; differs from clearing node — see below)
├── optimizer.py     # ★ objective() + optimize_params() coarse-to-fine grid search
├── measurements.py  # int:Measurement[] -> per-slot Slot(supply, demand, k_upper, k_lower)
└── calibrate.py     # orchestration + CLI + YAML config snippet output
tests/               # objective/optimizer + measurement aggregation tests
```

## The objective (keep faithful to the paper)

Minimise `-mean(min(buyer_utility, seller_profit)) + alpha * range_usage_penalty`
over valid slots, where `buyer_utility = k_upper - price`,
`seller_profit = price - k_lower`, and the penalty pushes the price to `k_lower`
at the max supply/demand ratio and to `k_upper` at the min. On data with a real
ratio spread the optimizer recovers ≈ `theta=1.0, steepness=2.5` (the shipped
defaults), which is the regression anchor.

## Conventions to preserve

1. **Dependency-free algorithm.** No numpy/scipy/pandas — a deterministic grid
   search. Only `pyyaml` (config emit). Don't add heavy deps.
2. **Unclamped sigmoid here, clamped in the clearing node.** `pricing.py` must
   NOT clamp to `[k_lower, k_upper]` (the penalty term needs the unclamped
   shape). The clearing node's `sigmoid.py` clamps for runtime safety. The core
   `K_upper - (K_upper-K_lower)/(1+exp(...))` formula must match across both.
3. **Output is the clearing node's config shape** (`communities:` block). The
   publish path (config merge vs on-chain `setCommunityParams` vs a future
   `int:AmmParameters` write) is provisional — see ../INTEGRATION_NOTES.md.

## Provisional assumptions (revisit with GSY)

- Measurement sign convention (net-load: positive = consumption). Configurable.
- Flat per-community price bounds (no per-slot tariff series yet).

## Dev loop

```bash
uv sync --extra dev
uv run pytest -v
```
