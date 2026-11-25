# AGENTS.md — amm-execution-node (settlement engine)

> Component-specific onboarding. See the [repo-root AGENTS.md](../AGENTS.md)
> for the big picture first.
>
> Public documentation: `docs/implementation/settlement-engine.md` and `docs/model/incentives.md`. Update these pages
> together with behaviour changes.

## What this component is

The **AMM execution engine** for settlement on the GSY DEX: it takes the
clearing node's output (int:Trade list, the int:Order objects they reference
and the int:ClearingResult of each market), transforms it into one on-chain
`MarketSettlement` per market (its `Match` structs plus its `ClearingResult`),
and submits `TradeSettlement.settleBatch` transactions. The off-chain
storage then writes trades from the resulting on-chain events — the engine is
how AMM matches become settled trades.

**Status: skeleton.** The full pipeline (build → validate → settle, with
idempotency and batching) is implemented against the
`settleBatch(MarketSettlement[])` interface of GSYDEXv2 `f0ea6c8` and tested
against a mocked chain. Live execution needs the production settlement
environment (deployed contract address, the `OPERATOR_ROLE` for the engine's
signer, the target chain with a funded signer). The identifier conventions are
implemented in `ids.py`.

The penalty formulas (`penalties.py`, `sigmoid.py`) live in this component: the
contract's `submitPenalties` (`EXECUTION_ENGINE_ROLE`) is their planned path.
They are tested but not yet wired into a data flow.

## File map

```
src/
├── engine.py         # ★ orchestration: validate → register actors → settleBatch; per-market ledger
├── match_builder.py  # ★ int:Trade/Order/ClearingResult → MarketSettlement; match types, residuals
├── validator.py      # pre-flight mirror of settleBatch: per-match rules + traded-quantity check
├── structs.py        # OrderParams/Match/ClearingResult/MarketSettlement mirrors, ×10000, u8 codes
├── ids.py            # GSY id conventions: UUID bytes for order/trade/market, blake2b-128 for actors
├── chain.py          # async web3 client for settleBatch (hand-declared ABI fragment)
├── main.py           # CLI: dry-run planner; --execute gated on the missing environment
├── penalties.py      # dormant: shortfall + VCG penalty math (future submitPenalties path)
└── sigmoid.py        # dormant: kept in sync with the clearing node's copy for counterfactuals
tests/
├── test_settlement.py  # ids, structs/ABI encoding, builder, validator, engine (mock chain)
└── test_penalties.py   # dormant penalty math (still green)
```

## Design notes

1. **Bilateral matches only.** Every `int:Trade` of the clearing node pairs two
   participant orders that the community client registered during the open
   market; the engine places no orders and needs no contract changes.
2. **One trade = one match.** A market's matches therefore sum to its traded
   quantity (the clearing node derives `tradeQuantity` from the rounded
   trades), so the `TradedQuantityMismatch` check passes by construction.
3. **All matches carry the uniform clearing price.** Individual prices
   (energy-type adjustments, preferred rates, penalties) are to be applied at
   this step (issue #121); they are not in `tradePrice`.
4. **Participant limit prices are surfaced, not silently fixed.** AMM clearing
   does not condition on limits, but the contract enforces them at settlement.
   The validator rejects such matches pre-flight with an explicit message
   instead of letting them fail on-chain (convention: issue #122).
5. **The market is the unit.** `settleBatch` reverts the whole transaction on
   any invalid match, so the validator holds back a whole market, the ledger
   (in-memory for the skeleton; persist before production) is keyed by market,
   and a transaction packs whole markets (`batch_size` counts matches; a larger
   market goes alone).
6. **Residual chaining.** An order that a match fills only partly leaves a
   residual (`residual_order_uuid(order_id, trade_id)`); the next match of the
   same order references the residual, as `settleOrder` requires.
7. **Match types.** A trade whose two orders name each other as preferred
   partners (`match_builder.is_mutual_pair`) is `Preferred`, priced against
   `preferredEnergyRate` when set; every other trade is `Standard`.
8. **Two id conventions, following the GSY DEX.**
   Order/trade/market ids are the UUID's 16 bytes (`parse_uuid_or_hex_bytes16`
   parity). Actor ids are _mapped_, not converted: `blake2b-128(offchain_id)`,
   computed locally in `ids.actor_onchain_id`. The engine hands every actor to
   an `IdRegistrar` so the storage can attribute settlement events back
   off-chain; the registrar is an interface only (no implementation yet), and
   the clearing node's `ewds_client.get_or_create_onchain_id` is the client
   call it will wrap (`ids.query` / `POST /ids`).

## ⚠ Known limitations (do not work around silently)

- Participant limit prices vs the uniform AMM price: see design note 4.
- Self-trades: the clearing node's fill can pair an actor with itself when
  only its own bids remain; the contract rejects it and the validator holds
  the market back (issue #125).
- `settleBatch` reverts with `TradedQuantityMismatch` unless a market's
  matches sum to its traded quantity. Bilateral output satisfies this; if the
  validator flags it, the clearing output is inconsistent — don't "fix" it by
  adjusting the reported traded quantity.

## Dev loop

```bash
uv sync --extra dev
uv run pytest -v                 # 57 tests
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
