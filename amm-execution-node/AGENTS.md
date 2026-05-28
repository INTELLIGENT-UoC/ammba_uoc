# AGENTS.md — amm-execution-node

> Component-specific onboarding. See the [repo-root AGENTS.md](../AGENTS.md)
> for the big picture first.

## What this service does

Runs **after delivery**. Reads settled trades and metered measurements,
computes three kinds of penalty, and returns the results.

| Penalty | When it applies | Formula (informal) |
|---|---|---|
| **Seller shortfall** | Seller delivered less than traded | `γ · K_upper · max(0, traded − delivered − η)` |
| **Seller VCG externality** | Supply-limited round, seller withheld supply | `max(0, (clearing_price − p_counterfactual) · traded)` |
| **Buyer VCG externality** | Demand-limited round, buyer under-reported | `max(0, (p_counterfactual − clearing_price) · traded)` |

Counterfactual prices come from the **same sigmoid** as the clearing node —
that's why `sigmoid.py` is duplicated here.

## File map

```
src/
├── main.py         # FastAPI app + --poll autonomous mode
├── execution.py    # run_execution_cycle() orchestration
├── penalties.py    # ★ three penalty formulas
├── sigmoid.py      # copy of clearing-node's sigmoid (intentional)
├── offchain_db.py  # async httpx client (trades + measurements)
└── config.py       # YAML + env-var settings, PenaltyConfig
tests/
└── test_*.py       # 19 tests
```

Start at `penalties.py` for any penalty-formula change.

## Public API

| Endpoint | Method | Body | Returns |
|---|---|---|---|
| `/trigger-execution` | POST | `{community_uuid, time_slot}` | penalty results |
| `/health` | GET | — | `{status: "ok"}` |

Also runs in **polling mode**: `uv run python -m src.main --poll`. The loop
checks for newly-completed delivery slots every `POLLING_INTERVAL_SEC` and
runs penalties autonomously.

## Configuration

| Var | Default | Meaning |
|---|---|---|
| `OFFCHAIN_DB_URL` | `http://offchain-db:8080` | GSY DEX base URL |
| `TIME_SLOT_SEC` | `900` | Market slot length |
| `EXECUTION_OFFSET_MIN` | `-120` | Penalties run this many minutes after delivery |
| `POLLING_INTERVAL_SEC` | `300` | Poll mode cadence |

`PenaltyConfig` (from `configuration.yaml`):
- `gamma` (default `1.1`): shortfall penalty multiplier on `K_upper`
- `eta`   (default `0.0`): tolerance allowance for under-delivery

## Dev loop

```bash
uv sync --extra dev
uv run pytest -v                                        # 19 tests
uv run uvicorn src.main:app --port 8082 --reload        # HTTP mode
uv run python -m src.main --poll                        # polling mode
```

## Patterns

- **Pure functions for each penalty.** `seller_shortfall_penalty`,
  `seller_externality_penalty`, `buyer_externality_penalty` all take numbers
  in, return numbers out. Tests pass concrete values — no mocking needed.
- **`execution.py` is the only place that does I/O.** Same convention as
  the clearing node — keeps algorithms isolated.
- **Round classification matters.** `compute_penalties_for_trades` decides
  whether a slot was supply-limited or demand-limited and applies the right
  externality. If you add a third regime, fork that decision deliberately.

## Conventions to preserve

1. **Sigmoid must match the clearing node.** Any change to `sigmoid.py` here
   must be mirrored in `amm-clearing-node/src/sigmoid.py` and covered by a
   regression test in both. (Yes, duplicated by design — see ARCHITECTURE.md
   decision log.)
2. Penalty result schema (current): per-trade dict with
   `{trade_uuid, area_uuid, penalty_type, amount, components}`. Extending is
   fine; renaming fields is breaking.
3. `compute_previous_timeslot()` is the canonical "which slot do we process
   right now?" function. Don't re-derive that math elsewhere.

## Common change recipes

- **Tweak a penalty formula**: edit `penalties.py`, add cases in
  `tests/test_penalties.py` with hand-computed expected values.
- **Add a new measurement source**: extend `offchain_db.py` with the new
  async method; mock with `respx`.
- **Change the polling interval default**: `config.py` + document in this
  file and in the repo-root README.

## Don'ts

- Don't persist penalty results yet — output schema and storage location are
  still **open items** (see ARCHITECTURE.md §13). Returning them is enough
  for now; an external settlement service will consume them.
- Don't introduce a separate copy of the sigmoid for "execution-specific"
  pricing — counterfactuals must be computed with the **exact** function the
  clearing node used. If you need to vary parameters, pass them in, don't
  fork the function.
