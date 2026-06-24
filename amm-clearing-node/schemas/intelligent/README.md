# Intelligent ontology schemas (vendored)

These JSON Schemas define the GSY DEX off-chain data contract — the shape of the
objects the clearing node exchanges with the off-chain storage over EWDS. They
are the single source of truth for the wire format and are vendored here so the
build does not depend on an external checkout and so any upstream change lands
as a reviewable diff.

The clearing node uses three of them directly:

| Schema | Role in the clearing node |
|---|---|
| `int.order.schema.v1.json` | Inbound orders (bids/offers) read for a market slot |
| `int.trade.schema.v1.json` | Outbound trades produced by clearing |
| `int.clearing-result.schema.v1.json` | Per-slot clearing summary |

The query/upsert envelope schemas (`int.orders.query.*`, `int.trades.query.*`,
`*.upsert.*`) describe the request/response messages for the EW Client Gateway
(CGW) transport, which the node will adopt in place of direct REST once the
channel conventions are finalised upstream.

Validation is performed by `src/ontology.py` with a small dependency-free
checker (no `jsonschema` dependency). `SOURCE_README.md` is the upstream README
kept for provenance. Keep these files in sync with the upstream `int.*` v1
schemas; bump to a new version folder if the upstream version changes.
