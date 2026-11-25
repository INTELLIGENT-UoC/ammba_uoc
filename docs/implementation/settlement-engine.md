# Settlement engine

> **In development.** The full pipeline of the settlement engine is implemented
> and tested against a mocked chain. Live execution is not yet enabled; it
> needs deployed settlement contracts, the required roles for the engine's
> signer, and the target chain.

In the integrated platform, matching engines do not write trades themselves.
They produce _matches_, pairings of a bid with an offer, which are settled
on-chain through the `settleBatch` function of the GSY DEX `TradeSettlement`
contract; the off-chain storage then records the trades from the settlement
events. `settleBatch` takes one _market settlement_ per market: the market's
matches together with its clearing result, which the contract publishes as a
market clearing event. The settlement engine (`amm-execution-node`) is how
AMMBA's clearing output becomes settled trades.

## Pipeline

The engine consumes the clearing engine's existing output, the trade list, the
orders those trades reference and the clearing result of each market, so the
clearing engine needs no changes for settlement.

1. **Build market settlements.** `match_builder.py` turns each trade into an
   on-chain `Match` between its two participant orders: a preferred match if
   the two orders name each other as preferred trading partners (a direct trade
   of mutual preferred partners), a standard match otherwise. It groups the
   matches by market, together with the market's clearing result. An order
   that a match fills only partly leaves a residual order, which a later match
   of the same order consumes.
2. **Validate.** `validator.py` checks each market against the contract's
   revert conditions before any transaction is sent: every match, and the
   market's traded quantity. The contract reverts the whole transaction on any
   invalid match, so a market with a violation is held back as a whole while
   the other markets go ahead.
3. **Register actor identifiers.** All actors of the batch, including declared
   preferred partners, are registered in the identifier mapping of the
   off-chain storage, so settlement events can be attributed to off-chain
   actors.
4. **Settle.** Whole markets are submitted through `settleBatch` in bounded
   transactions; a market is never split across transactions.

A ledger records settled markets, so re-running the engine never settles a
market twice.

## Bilateral matches

The settlement contract only settles a match if both of its orders are open in
the on-chain order registry. Every trade of the clearing engine pairs two
participant orders, which the community client placed in the registry while
the market was open, so the engine places no orders of its own. Because every
trade is one match, the selected energy of a market's matches sums to its
traded quantity, as the contract requires; the clearing result states the sum
of the trades (see the [data model](../integration/data-model.md#units)).

All matches carry the uniform clearing price. Individual prices, such as
energy-type adjustments, preferred rates and penalties, are to be applied at
this step
([#121](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues/121)).

## Identifiers and units

| Item                                | On-chain encoding                                                                                    |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Order, trade and market identifiers | The 16 bytes of the UUID (or of the storage's `0x`-hex form of it)                                   |
| Actor identifiers (buyer, seller)   | BLAKE2b-128 hash of the actor's off-chain identifier, registered in the storage's identifier mapping |
| Energy and prices                   | Unsigned integers scaled by 10,000; prices in EUR/kWh                                                |
| Energy types                        | `0` unspecified, `1` GREEN, `2` PV, `3` HYDRO, `4` BIOMASS, `5` BATTERY                              |
| Match types                         | `0` standard (matches of the sequential fill), `1` preferred (direct trades of mutual partners)      |
| Clearing status                     | `1` final, `2` partial, `3` rejected, `4` no bid                                                     |

These conventions follow the GSY DEX; see the
[data model](../integration/data-model.md#on-chain-identifiers).

## Known limitations

- **Limit prices.** AMMBA clearing does not use participants' limit prices,
  but the contract enforces them on both sides of every standard match. The
  validator flags such matches explicitly instead of letting them fail
  on-chain ([#122](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues/122)).
- **Self-trades.** An actor with both an offer and a bid in a slot can be
  paired with itself when only its own bids remain in the sequential fill. The
  contract rejects self-trades, and the validator holds such a market back
  ([#125](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues/125)).

## Command-line planner

Until live execution is enabled, the engine runs as a dry-run planner. It reads
the clearing output and reports the markets and matches and the markets held
back pre-flight with their reasons:

```bash
cd amm-execution-node
uv run python -m src.main --trades trades.json --orders orders.json \
  --clearing-results results.json
```

With `--execute`, the planner lists the environment and role prerequisites
that are still missing instead of sending transactions.

## Penalty formulas

The component also contains the formulas of the
[penalty mechanism](../model/incentives.md) in `penalties.py`, together with the
copy of the pricing function they need for counterfactual prices. They are
tested but not yet connected to an operational data flow; the settlement
layer's penalty submission interface is their planned path. See
[incentives and penalties](../model/incentives.md#implementation-status).
