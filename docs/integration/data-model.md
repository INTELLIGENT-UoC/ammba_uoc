# Data model and identifiers

## The ontology as wire contract

AMMBA exchanges data in the INTELLIGENT ontology, defined by the project and
implemented by the GSY DEX off-chain storage. The JSON schemas of the relevant
objects are vendored in
[`amm-clearing-node/schemas/intelligent/`](https://github.com/INTELLIGENT-UoC/ammba_uoc/tree/main/amm-clearing-node/schemas/intelligent),
together with a note on their source. Inbound orders and all outbound objects
are validated against them; measurement records are passed to the calibration
tool as received.

| Object               | Direction | Use in AMMBA                                                            |
| -------------------- | --------- | ----------------------------------------------------------------------- |
| `int:Order`          | in        | Bids and offers of a market slot                                        |
| `int:Market`         | in        | Market discovery for the self-trigger scheduler                         |
| `int:Measurement`    | in        | Metering history for calibration, retrieved by `src.fetch_measurements` |
| `int:Trade`          | out       | Bilateral buyer–seller matches at the clearing price                    |
| `int:ClearingResult` | out       | Per-slot summary: price, volumes, status                                |

The wire objects are flat, use camelCase field names, lower-case enumeration
values (for example order types `bid`/`offer` and status `submitted`),
RFC 3339 timestamps and prices in EUR/kWh. Markets carry UUID identifiers; the
off-chain storage returns order and market identifiers of orders in its
`0x`-hex form of the same 16 bytes. Trades produced by clearing have the status
`matched`; settlement on the exchange later marks trades as settled. Translation between the wire objects
and the engine's internal representation happens in one module,
`amm-clearing-node/src/adapters.py`; the algorithm modules never see wire field
names.

## Units

| Quantity   | Inside the engine                        | On the wire         |
| ---------- | ---------------------------------------- | ------------------- |
| Prices     | ct/kWh, as the tariff band is configured | EUR/kWh, 4 decimals |
| Energy     | kWh, in steps of 0.0001 kWh              | kWh, 4 decimals     |
| Time slots | Unix seconds                             | ISO-8601            |

Four decimals are the resolution of the on-chain encoding, which scales energy
and prices by 10,000 to integers, so a wire value encodes to the same integer
the settlement contract stores. The engine allocates in steps of 0.0001 kWh
with the largest-remainder method, so the bids and the offers of a slot sum to
the same total, and the traded quantity of the clearing result is the sum of
the slot's trades.

## Trades

The trade object is bilateral: it references a bid, an offer, a buyer and a
seller. Every trade of AMMBA pairs a participant's bid with a participant's
offer at the uniform clearing price. The pool is the pricing and allocation
mechanism; it does not appear on the wire.

- **Direct trades.** Mutual preferred partners trade with each other first;
  see [preferences](../model/extensions.md#preferred-trading-partners).
- **Matches of the sequential fill.** The remaining allocations are cut into
  buyer–seller matches; see the
  [clearing engine](../implementation/clearing-engine.md#bilateral-decomposition).

Every participant trades exactly its allocation, at the clearing price, and the
trades of a slot sum to its traded quantity. Apart from mutual preferred
partners, no participant chooses its counterparty, so the pairing has no
economic meaning beyond settlement. Individual price components, such as
energy-type adjustments, preferred rates and deviation penalties, are not part
of the trade price; they belong to the execution step
([#121](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues/121)).

## Deterministic identifiers

Trade identifiers are version 5 UUIDs derived from the market, the kind of
trade (`pref` for a direct trade of mutual preferred partners, `pair` for a
match of the sequential fill) and the two orders involved. Re-running the
clearing of a slot therefore reproduces the same identifiers, and repeated runs
can be detected reliably.

## On-chain identifiers

For settlement, identifiers are encoded following the conventions of the GSY
DEX:

- **Orders, trades and markets** are encoded as the 16 bytes of their UUID;
  the storage's `0x`-hex form of an identifier encodes to the same bytes.
- **Actors** (buyers and sellers) are not encoded directly but _mapped_:
  the on-chain identifier is the BLAKE2b-128 hash of the off-chain identifier
  string. The off-chain storage keeps the mapping and returns it through
  `ids.query` or `POST /ids?offchain_id=…`, creating it on first use; the
  settlement engine registers every actor before settling, so that settlement
  events can be attributed to off-chain actors.
- **Energy and prices** are unsigned integers scaled by 10,000; on-chain
  prices are in EUR/kWh, like the wire's `priceLimit` and `tradePrice`.

The settlement engine implements these conventions in
`amm-execution-node/src/ids.py` and `structs.py`; see the
[settlement engine](../implementation/settlement-engine.md#identifiers-and-units).
