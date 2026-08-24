# AGENTS.md — amm-execution-node (settlement engine)

> Component-specific onboarding. See the [repo-root AGENTS.md](../AGENTS.md)
> for the big picture first.

## What this component is

The **AMM execution engine** for v2 of the GSY DEX integration: it takes the
clearing node's output (int:Trade list + the int:Order objects they reference),
transforms it into on-chain `Match` structs, registers the pool's standing
orders, and submits `TradeSettlement.settleBatch` transactions. The off-chain
storage then writes trades from the resulting on-chain events — the engine is
how AMM matches become settled trades.

**Status: skeleton.** The full pipeline (build → validate → place pool orders
→ settle, with idempotency and batching) is implemented and tested against a
mocked chain. Live execution is blocked on the GSY-side environment: frozen
contracts + deployed addresses, `OPERATOR_ROLE` grant, target chain + funded
signer, canonical UUID↔bytes16 utilities, and the currency-unit decision.

The former penalty mechanism (`penalties.py`, `sigmoid.py`) stays in this
component: the contract's `submitPenalties` (`EXECUTION_ENGINE_ROLE`) is its
future path. It is dormant, not wired.

## File map

```
src/
├── engine.py         # ★ orchestration: validate → pool orders → settleBatch; idempotent ledger
├── match_builder.py  # ★ int:Trade + int:Order → Match structs; synthesizes pool orders (option a)
├── validator.py      # pre-flight mirror of TradeSettlement._settleTrade revert conditions
├── structs.py        # OrderData/Match/OrderParams mirrors, ×10000 scaling, energy-type u8 codes
├── ids.py            # UUID ↔ bytes16 (provisional pending GSY utilities)
├── chain.py          # async web3 client for placeOrder/settleBatch (hand-declared ABI fragments)
├── main.py           # CLI: dry-run planner; --execute gated on the missing environment
├── penalties.py      # dormant: shortfall + VCG penalty math (future submitPenalties path)
└── sigmoid.py        # dormant: kept in sync with the clearing node's copy for counterfactuals
tests/
├── test_settlement.py  # ids, structs/ABI encoding, builder, validator, engine (mock chain)
└── test_penalties.py   # dormant penalty math (still green)
```

## Design decisions encoded here (with their sources)

1. **Option (a) pool representation** (GSY, 2026-08-24): the engine registers
   standing pool orders on-chain; the pool holds its own signer key; no
   contract changes.
2. **One pool order per pool match.** `_settleTrade` flips both orders to
   `Executed`, so a pool order can settle exactly once → `match_builder`
   synthesizes a deterministic pool order per trade
   (`pool_settle_order_uuid(trade_id)`).
3. **Pool orders can never cause `PriceMismatch`.** The contract requires
   `bid.energyRate ≥ clearingPrice ≥ offer.energyRate`; pool bids are priced
   at the community ceiling and pool offers at the floor.
4. **Participant limit prices are surfaced, not silently fixed.** AMM clearing
   does not condition on limits, but the contract enforces them at settlement.
   The validator rejects such matches pre-flight with an explicit message —
   resolving this mismatch is an open design point with GSY.
5. **Idempotency by trade id.** The ledger (in-memory for the skeleton;
   persist before production) prevents double-settling across re-runs.

## ⚠ Open constraints (raised with GSY — do not silently "fix")

- `OrderRegistry.placeOrder` requires the market to be **Open** and the actor
  to be **authorized in ActorRegistry** for the sender. AMM matches are only
  known after market close → pool standing orders cannot be placed
  post-clearing under current rules. Needs a GSY-side resolution (settlement
  role exemption or pool-aware path).
- The on-chain energy-type coding **includes GREY (=6)** while the current
  off-chain wire DTO rejects GREY — upstream drift, reported.
- Currency unit for the scaled u64 price fields: consortium decision pending.

## Dev loop

```bash
uv sync --extra dev
uv run pytest -v                 # 31 tests
uv run python -m src.main        # CLI status / dry-run planner
```

## Don'ts

- Don't change `SCALING_FACTOR = 10000` (confirmed shared with GSY).
- Don't replace `ids.py` conventions ad hoc — swap in GSY's canonical
  utilities when published, in that one module only.
- Don't wire `--execute` paths before the contract freeze; the hand-declared
  ABI fragments in `chain.py` must be replaced by GSY's compiled artifacts.
- `sigmoid.py` must stay in sync with `amm-clearing-node/src/sigmoid.py`.
