# Settlement engine

> **In development.** The full pipeline of the settlement engine is implemented
> and tested against a mocked chain. Live execution is not yet enabled; it
> needs deployed settlement contracts, the required roles for the engine's
> signer, and the target chain.

In the integrated platform, matching engines do not write trades themselves.
They produce _matches_, pairings of a bid with an offer, which are settled
on-chain through the `settleBatch` function of the GSY DEX `TradeSettlement`
contract; the off-chain storage then records the trades from the settlement
events. The settlement engine (`amm-execution-node`) is how AMMBA's clearing
output becomes settled trades.

## Pipeline

The engine consumes the clearing engine's existing output, the trade list and
the orders those trades reference, so the clearing engine needs no changes for
settlement.

1. **Build matches.** `match_builder.py` turns each trade into an on-chain
   `Match`.
2. **Validate.** `validator.py` checks each match against the contract's revert
   conditions before any transaction is sent, so one invalid match cannot fail
   a whole batch.
3. **Register actor identifiers.** All actors of the batch, including the
   pool, are registered in the identifier mapping of the off-chain storage, so
   settlement events can be attributed to off-chain actors.
4. **Place pool orders.** The pool's counter-orders are placed in the on-chain
   order registry.
5. **Settle.** Matches are submitted in bounded batches through `settleBatch`.

A ledger records settled trades, so re-running the engine never settles a trade
twice.

## Representing the pool on-chain

The settlement contract only settles a match if both of its orders are open in
the on-chain order registry, but the AMMBA pool has no orders of its own. The
engine therefore registers standing orders for the pool:

- **One pool order per trade.** Settlement marks both orders of a match as
  executed, so a pool order can settle exactly one match. The engine derives a
  deterministic pool order from each trade's identifier.
- **Priced at the band.** The contract requires the bid's limit to be at least
  the clearing price and the offer's limit at most the clearing price. Pool
  bids are priced at the community's retail price and pool offers at its
  feed-in tariff, so the pool side can never violate this check.

## Identifiers and units

| Item                                    | On-chain encoding                                                                                                                            |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Order, trade and market identifiers     | The 16 bytes of the UUID                                                                                                                     |
| Actor identifiers (buyer, seller, pool) | BLAKE2b-128 hash of the actor's off-chain identifier, registered in the storage's identifier mapping                                         |
| Energy and prices                       | Unsigned integers scaled by 10,000; the price currency unit is not fixed yet ([#30](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues/30)) |
| Energy types                            | `0` unspecified, `1` GREEN, `2` PV, `3` HYDRO, `4` BIOMASS, `5` BATTERY, `6` GREY                                                            |

These conventions follow the GSY DEX; see the
[data model](../integration/data-model.md#on-chain-identifiers).

## Known limitations

- **Placement timing.** The order registry accepts new orders only while a
  market is open, but AMM matches are known only after the market closes.
  Placing pool orders after clearing is therefore not yet supported.
- **Actor authorisation.** Placing orders for the pool requires the engine's
  signer to be authorised for the pool's actor identifier in the actor
  registry.
- **Limit prices.** AMMBA clearing does not use participants' limit prices,
  but the contract enforces them at settlement. The validator flags such
  matches explicitly instead of letting them fail on-chain.

## Command-line planner

Until live execution is enabled, the engine runs as a dry-run planner. It reads
the clearing output and reports the matches, the pool orders to place, and any
pre-flight rejections:

```bash
cd amm-execution-node
uv run python -m src.main --trades trades.json --orders orders.json \
  --pool-actor <pool-actor-uuid> --k-upper 0.285 --k-lower 0.08
```

`--k-upper` and `--k-lower` are the community's price band in the unit of the
trades' `tradePrice`, EUR/kWh (here 28.5 and 8.0 ct/kWh). With `--execute`,
the planner lists the environment and role prerequisites that are still
missing instead of sending transactions.

## Penalty formulas

The component also contains the formulas of the
[penalty mechanism](../model/incentives.md) in `penalties.py`, together with the
copy of the pricing function they need for counterfactual prices. They are
tested but not yet connected to an operational data flow; the settlement
layer's penalty submission interface is their planned path. See
[incentives and penalties](../model/incentives.md#implementation-status).
