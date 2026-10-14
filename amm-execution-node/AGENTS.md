# AGENTS.md — amm-execution-node (settlement engine)

> Component-specific onboarding. See the [repo-root AGENTS.md](../AGENTS.md)
> for the big picture first.
>
> Public documentation: `docs/implementation/settlement-engine.md` and `docs/model/incentives.md`. Update these pages
> together with behaviour changes.

## What this component is

The **AMM execution engine** for settlement on the GSY DEX: it takes the
clearing node's output (int:Trade list + the int:Order objects they reference),
transforms it into on-chain `Match` structs, registers the pool's standing
orders, and submits `TradeSettlement.settleBatch` transactions. The off-chain
storage then writes trades from the resulting on-chain events — the engine is
how AMM matches become settled trades.

**Status: skeleton.** The full pipeline (build → validate → place pool orders
→ settle, with idempotency and batching) is implemented and tested against a
mocked chain. Live execution needs the production settlement environment:
deployed contract addresses, the `OPERATOR_ROLE` for the engine's signer, the
target chain with a funded signer, and a fixed currency unit (issue #30). The
identifier conventions are implemented in `ids.py`.

The penalty formulas (`penalties.py`, `sigmoid.py`) live in this component: the
contract's `submitPenalties` (`EXECUTION_ENGINE_ROLE`) is their planned path.
They are tested but not yet wired into a data flow.

## File map

```
src/
├── engine.py         # ★ orchestration: validate → pool orders → settleBatch; idempotent ledger
├── match_builder.py  # ★ int:Trade + int:Order → Match structs; synthesizes pool orders (option a)
├── validator.py      # pre-flight mirror of TradeSettlement._settleTrade revert conditions
├── structs.py        # OrderData/Match/OrderParams mirrors, ×10000 scaling, energy-type u8 codes
├── ids.py            # GSY id conventions: UUID bytes for order/trade/market, blake2b-128 for actors
├── chain.py          # async web3 client for placeOrder/settleBatch (hand-declared ABI fragments)
├── main.py           # CLI: dry-run planner; --execute gated on the missing environment
├── penalties.py      # dormant: shortfall + VCG penalty math (future submitPenalties path)
└── sigmoid.py        # dormant: kept in sync with the clearing node's copy for counterfactuals
tests/
├── test_settlement.py  # ids, structs/ABI encoding, builder, validator, engine (mock chain)
└── test_penalties.py   # dormant penalty math (still green)
```

## Design notes

1. **Pool representation:** the engine registers standing pool orders
   on-chain; the pool holds its own signer key; no contract changes.
2. **One pool order per pool match.** `_settleTrade` flips both orders to
   `Executed`, so a pool order can settle exactly once → `match_builder`
   synthesizes a deterministic pool order per trade
   (`pool_settle_order_uuid(trade_id)`).
3. **Pool orders can never cause `PriceMismatch`.** The contract requires
   `bid.energyRate ≥ clearingPrice ≥ offer.energyRate`; pool bids are priced
   at the community ceiling and pool offers at the floor.
4. **Participant limit prices are surfaced, not silently fixed.** AMM clearing
   does not condition on limits, but the contract enforces them at settlement.
   The validator rejects such matches pre-flight with an explicit message
   instead of letting them fail on-chain.
5. **Idempotency by trade id.** The ledger (in-memory for the skeleton;
   persist before production) prevents double-settling across re-runs.
6. **Two id conventions, following the GSY DEX.**
   Order/trade/market ids are the UUID's 16 bytes (`parse_uuid_or_hex_bytes16`
   parity). Actor ids are _mapped_, not converted: `blake2b-128(offchain_id)`,
   computed locally in `ids.actor_onchain_id` and registered with the storage
   through the engine's `IdRegistrar` (`ids.query` / `POST /ids`) so
   settlement events can be attributed back off-chain.

## ⚠ Known limitations (do not work around silently)

- `OrderRegistry.placeOrder` requires the market to be **Open** and the actor
  to be **authorized in ActorRegistry** for the sender. AMM matches are only
  known after market close → pool standing orders cannot be placed
  post-clearing under current rules; this needs a pool-aware path in the
  settlement contracts.
- The on-chain energy-type coding **includes GREY (=6)** while the current
  off-chain wire DTO rejects GREY.
- Currency unit for the scaled u64 price fields: not yet fixed (issue #30).

## Dev loop

```bash
uv sync --extra dev
uv run pytest -v                 # 37 tests
uv run python -m src.main        # CLI status / dry-run planner
```

## Don'ts

- Don't change `SCALING_FACTOR = 10000` (shared with the GSY DEX).
- Don't encode an actor id as UUID bytes — actors go through the blake2b
  mapping in `ids.py`; only order/trade/market ids are raw UUID bytes.
- Don't wire `--execute` paths before the settlement contracts are final; the
  hand-declared ABI fragments in `chain.py` must then be replaced by the
  compiled contract artifacts.
- `sigmoid.py` must stay in sync with `amm-clearing-node/src/sigmoid.py`.
