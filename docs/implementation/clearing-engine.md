# Clearing engine

The clearing engine (`amm-clearing-node`) implements the order-based form of
the [market mechanism](../model/index.md) for operation. It clears one market slot at a
time, either on request or autonomously.

## Clearing procedure

`run_clearing()` in `src/clearing.py` executes the following steps for one
market slot.

| Step | Function                                                                                                                                                                |
| ---: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|    0 | Idempotency check: skip the slot if trades already exist for the market.                                                                                                |
|    1 | Read the open orders of the market and validate them against the ontology schemas. Orders in status `Submitted` are matchable.                                          |
|    2 | Aggregate the supply $E_t$ and the demand $D_t$.                                                                                                                        |
|    3 | Compute the clearing price with [Eq. (1)](../model/pricing.md#the-pricing-function) on the ratio $E_t / D_t$. If one side of the market is empty, finish without trade. |
|    4 | Optionally record the result with the [audit anchor](smart-contract.md). Skipped when no contract is configured.                                                        |
|    5 | Allocate the quantities pro rata with [Eq. (4)](../model/allocation.md#order-based-allocation).                                                                         |
|    6 | Serve mutual preferred partners first, then apply the optional [differential pricing](../model/extensions.md).                                                          |
|    7 | Generate the trades: buyer–pool and pool–seller trades for pool allocations, direct trades for preference pairs.                                                        |
|    8 | Publish the trades and the clearing result to the off-chain store.                                                                                                      |

Each pool allocation becomes two trades so that the bilateral trade object of
the ontology can describe pool-mediated exchanges; the pool appears as a
configured actor of the community. Trade identifiers are deterministic UUIDs
derived from the trade's inputs, so re-running a clearing reproduces them. The
[data model](../integration/data-model.md) describes the wire objects.

The pricing function limits its exponent to $[-500, 500]$ to prevent overflow
and clamps its result to the band.

## Clearing summary

`run_clearing()` returns a summary, which the HTTP endpoint passes back in its
`detail` field:

| Field                                                     | Meaning                                                                                                                                             |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status`                                                  | `cleared`; `no_trade` if one side of the market is empty; `skipped` if the slot was already cleared; `error` if the audit-anchor transaction failed |
| `market_id`                                               | The cleared market                                                                                                                                  |
| `total_supply_kwh`, `total_demand_kwh`                    | $E_t$ and $D_t$                                                                                                                                     |
| `clearing_price_ct_per_kwh`, `clearing_price_eur_per_kwh` | $\pi_t$ in both units                                                                                                                               |
| `traded_quantity_kwh`                                     | $Q_t$                                                                                                                                               |
| `num_trades`                                              | Number of trades generated                                                                                                                          |
| `tx_hash`                                                 | Transaction of the audit anchor, or `0x0` without one                                                                                               |
| `price_adjustments`                                       | Provenance of differential pricing, or `null`                                                                                                       |

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

Both transports retry network errors and HTTP 5xx responses up to three times
with exponential back-off and jitter (base 0.25 s, at most 2 s). Client errors
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
