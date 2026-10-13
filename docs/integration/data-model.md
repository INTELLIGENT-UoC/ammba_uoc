# Data model and identifiers

## The ontology as wire contract

AMMBA exchanges data in the INTELLIGENT ontology, defined by the project and
implemented by the GSY DEX off-chain storage. The JSON schemas of the relevant
objects are vendored in
[`amm-clearing-node/schemas/intelligent/`](https://github.com/INTELLIGENT-UoC/ammba_uoc/tree/main/amm-clearing-node/schemas/intelligent),
together with a note on their source. Inbound orders and all outbound objects
are validated against them.

| Object               | Direction | Use in AMMBA                                         |
| -------------------- | --------- | ---------------------------------------------------- |
| `int:Order`          | in        | Bids and offers of a market slot                     |
| `int:Market`         | in        | Market discovery for the self-trigger scheduler      |
| `int:Measurement`    | in        | Metering history for calibration                     |
| `int:Trade`          | out       | Buyer–pool, pool–seller and direct preference trades |
| `int:ClearingResult` | out       | Per-slot summary: price, volumes, status             |

The wire objects are flat, use camelCase field names, UUID identifiers,
ISO-8601 timestamps and prices in EUR/kWh. Translation between the wire objects
and the engine's internal representation happens in one module,
`amm-clearing-node/src/adapters.py`; the algorithm modules never see wire field
names.

## Units

| Quantity   | Inside the engine                        | On the wire |
| ---------- | ---------------------------------------- | ----------- |
| Prices     | ct/kWh, as the tariff band is configured | EUR/kWh     |
| Energy     | kWh                                      | kWh         |
| Time slots | Unix seconds                             | ISO-8601    |

## The pool on the wire

The trade object is bilateral: it references a bid, an offer, a buyer and a
seller. Pool-mediated exchanges are represented as two trades each, buyer–pool
and pool–seller, in which the pool appears as a configured actor
(`pool_actor_uuid` of the community). The pool is modelled as holding one
standing bid and one standing offer per market slot, with identifiers derived
deterministically from the market and the side, so every trade references valid
orders on both sides and validates against the schema. For on-chain settlement, the
settlement engine instead derives one pool order per trade, because a settled
order cannot be reused; see the
[settlement engine](../implementation/settlement-engine.md#representing-the-pool-on-chain).

## Deterministic identifiers

Trade identifiers are version 5 UUIDs derived from the market, the kind of
trade and the orders involved, and pool order identifiers are derived in the
same way. Re-running the clearing of a slot therefore reproduces the same identifiers, and repeated runs can be detected
reliably.

## On-chain identifiers

For settlement, identifiers are encoded following the conventions of the GSY
DEX:

- **Orders, trades and markets** are encoded as the 16 bytes of their UUID.
- **Actors** (buyers, sellers, the pool) are not encoded directly but _mapped_:
  the on-chain identifier is the BLAKE2b-128 hash of the off-chain identifier
  string. The off-chain storage keeps the mapping and returns it through
  `ids.query` or `POST /ids?offchain_id=…`, creating it on first use; the
  settlement engine registers every actor before settling, so that settlement
  events can be attributed to off-chain actors.
- **Energy and prices** are unsigned integers scaled by 10,000.

The settlement engine implements these conventions in
`amm-execution-node/src/ids.py` and `structs.py`; see the
[settlement engine](../implementation/settlement-engine.md#identifiers-and-units).
