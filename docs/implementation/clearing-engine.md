# Clearing engine

The clearing engine (`amm-clearing-node`) implements the
[market mechanism](../model/index.md) for operation. It clears one market slot
at a time, either on request or autonomously.

## Clearing procedure

`run_clearing()` in `src/clearing.py` executes the following steps for one
market slot.

| Step | Function                                                                                                                                                                |
| ---: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|    0 | Idempotency check: skip the slot if trades already exist for the market.                                                                                                |
|    1 | Read the open orders of the market and validate them against the ontology schemas. Orders in status `submitted` or `expired` are matchable (see below).                 |
|    2 | Aggregate the supply $E_t$ and the demand $D_t$.                                                                                                                        |
|    3 | Compute the clearing price with [Eq. (1)](../model/pricing.md#the-pricing-function) on the ratio $E_t / D_t$. If one side of the market is empty, finish without trade. |
|    4 | Optionally record the result with the [audit anchor](smart-contract.md). Skipped when no contract is configured.                                                        |
|    5 | Allocate the quantities pro rata with [Eq. (2)](../model/allocation.md#pro-rata-allocation), in steps of 0.0001 kWh (see below).                                        |
|    6 | Serve mutual preferred partners first. The optional [differential pricing](../model/extensions.md) is computed for the summary only.                                    |
|    7 | Generate the trades: direct trades for preference pairs, then the [bilateral decomposition](#bilateral-decomposition) of the remaining allocations.                     |
|    8 | Publish the trades and the clearing result to the off-chain store.                                                                                                      |

The GSY DEX off-chain storage sets every `submitted` order to `expired` once
its time slot has started. A market closes no later than the start of its
delivery slot, and the engine clears it only after the close, so its orders
may already be expired by then. The engine therefore treats `expired` orders
like `submitted` ones and ignores orders in any other status.

Before allocating, the engine sorts the orders by actor identifier and then by
order identifier, so the result does not depend on the order in which the
orders arrive. Trade identifiers are deterministic UUIDs derived from the
trade's inputs, so re-running a clearing reproduces them. The
[data model](../integration/data-model.md) describes the wire objects.

### Quantised allocation

Quantities are allocated in steps of 0.0001 kWh, the resolution of the
on-chain encoding. Each side's share of the traded quantity $Q_t$ is rounded
down to a whole step, and the steps left over go to the orders with the largest
remainders. Both sides therefore sum to exactly $Q_t$, the short side trades
its full order quantities, and no order deviates from its exact pro-rata share
by more than one step. Prices are rounded to four decimals in EUR/kWh on the
wire.

### Bilateral decomposition

The trade object of the ontology is bilateral, and settlement settles one match
per trade. After the preference step, the engine therefore cuts the remaining
allocations into buyer–seller matches at the clearing price with a sequential
fill:

1. Sort the sellers and the buyers with a remaining allocation by actor
   identifier, then by order identifier.
2. Line both sides up along the remaining traded quantity, which is the same
   on both sides.
3. Cut at every boundary between two orders: each cut gives one match.

Each match exhausts at least one order, so $n$ sellers and $m$ buyers give at
most $n + m - 1$ matches. Every participant trades exactly its allocation at
the clearing price; only the counterparty is a result of the fill. Sorting by
actor identifier lines up the same participants in the same order every slot,
so pairings repeat across slots.

If a match would pair an actor with itself (an actor with both an offer and a
bid in the slot), the fill moves the next bid of another actor forward. A
self-match remains only when every remaining bid belongs to that actor
([#125](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues/125)).

The pool remains the mechanism that sets the price and the allocation; it does
not appear in the trades. The decomposition itself is in
`src/decompose.py`, independent of the pricing function.

The pricing function limits its exponent to $[-500, 500]$ to prevent overflow
and clamps its result to the band.

## Clearing summary

`run_clearing()` returns a summary, which the HTTP endpoint passes back in its
`detail` field. A `cleared` result carries all fields below; `skipped`,
`no_trade` and `error` results carry only the status and the fields known at
that point:

| Field                                                     | Meaning                                                                                                                                             |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status`                                                  | `cleared`; `no_trade` if one side of the market is empty; `skipped` if the slot was already cleared; `error` if the audit-anchor transaction failed |
| `market_id`                                               | The cleared market                                                                                                                                  |
| `total_supply_kwh`, `total_demand_kwh`                    | $E_t$ and $D_t$                                                                                                                                     |
| `clearing_price_ct_per_kwh`, `clearing_price_eur_per_kwh` | $\pi_t$ in both units; the EUR/kWh value as on the wire, at four decimals                                                                           |
| `traded_quantity_kwh`                                     | $Q_t$, the sum of the trades                                                                                                                        |
| `num_trades`                                              | Number of trades generated                                                                                                                          |
| `tx_hash`                                                 | Transaction of the audit anchor, or `0x0` without one                                                                                               |
| `price_adjustments`                                       | Differential-pricing adjustments, reported only and not applied to trade prices, or `null`                                                          |

## Triggering a clearing

**On request.** `POST /trigger-clearing` clears one slot; see the
[interfaces](../reference/interfaces.md#clearing-engine-http-api).

**Autonomously.** With `SCHEDULER_ENABLED=true`, a background scheduler polls
the market list every `SCHEDULER_POLL_INTERVAL_SEC` seconds. It clears every
market whose order window has closed, whose matching algorithm is `amm`, and
whose community is configured, using the market's delivery start as the time
slot. A market whose clearing fails is retried at the next tick. When a tick
fails as a whole, for example because the market list cannot be read, the
interval doubles up to ten times the configured value, and it returns to the
configured value after the next successful tick. The idempotency check of step
0 remains the safeguard against clearing a market twice.

## Transports

`OFFCHAIN_TRANSPORT` selects how the engine reaches market data. Both clients
expose the same methods: read orders, trades and markets, write trades and the
clearing result, and check health.

| Transport        | Client               | Use                                                                                           |
| ---------------- | -------------------- | --------------------------------------------------------------------------------------------- |
| `rest` (default) | `src/offchain_db.py` | Direct REST access to an off-chain store or the bundled simulator                             |
| `ewds`           | `src/ewds_client.py` | Publish and poll through an EWDS Client Gateway; see [EWDS transport](../integration/ewds.md) |

Both transports make up to three attempts on network errors and HTTP 5xx
responses (two retries), with exponential back-off and jitter (base 0.25 s, at most 2 s). Client errors
are not retried. On the `ewds` transport, writing trades and clearing results
is a logged no-op: in the integrated platform, matches are settled on-chain and
the off-chain storage records trades from the settlement events; see the
[settlement engine](settlement-engine.md).

## Validation

Inbound orders are validated against the order schema of the ontology. With
`OFFCHAIN_STRICT_VALIDATION=true` (the default), invalid orders are dropped
with a log entry; with `false`, they are kept and only logged, which helps
during integration against environments whose data does not yet fully match the
ontology. Outbound trades and clearing results are always validated.
