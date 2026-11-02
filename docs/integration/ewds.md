# EWDS transport

With `OFFCHAIN_TRANSPORT=ewds`, the clearing engine reads market data through
a Client Gateway of the Energy Web Digital Spine (EWDS) instead of accessing an
off-chain store directly. The calibration fetch step (`src.fetch_measurements`)
always uses this transport to retrieve the metering history; see the
[calibration tool](../implementation/calibration-tool.md#input-data). The client is `amm-clearing-node/src/ewds_client.py`;
it follows the request/response pattern of the GSY DEX off-chain storage's
EWDS request handler.

## Request and response

Every query is a request message published to a request topic, followed by
polling of the paired response topic until the matching response arrives or
the timeout elapses.

**Publish.** `POST {gateway}/api/v2/messages` with a transport message:

```json
{
  "fqcn": "gsy.intelligent.requests.pub",
  "topicName": "ordersQuery",
  "topicVersion": "1.0.0",
  "topicOwner": "integration.apps.intelligent.auth.ewc",
  "transactionId": "<requestId>",
  "payload": "<inner envelope as a JSON string>",
  "anonymousRecipient": []
}
```

The inner envelope is `{"requestId", "operation", "payload"}`, where
`payload` holds the query parameters. The request identifier has the form
`{operation}-{milliseconds}-{process id}`, for example
`orders-query-1787562858069-34902`.

**Poll.** `GET {gateway}/api/v2/messages` with `fqcn`, `topicName`,
`topicOwner`, `amount` and `clientId`. Each response message carries a
stringified envelope `{"requestId", "success", "data", "error"}`. The
client ignores responses to other requests and returns `data` of the
matching one; `success: false` raises an error with the handler's code and
message.

## Operations

| Operation            | Request topic       | Response topic              | Query parameters                                                   |
| -------------------- | ------------------- | --------------------------- | ------------------------------------------------------------------ |
| `orders.query`       | `ordersQuery`       | `ordersQueryResponse`       | `marketId`, `startTime`, `endTime`                                 |
| `trades.query`       | `tradesQuery`       | `tradesQueryResponse`       | `marketId`                                                         |
| `measurements.query` | `measurementsQuery` | `measurementsQueryResponse` | `startTime`, `endTime`, optional `facility_id`                     |
| `markets.query`      | `marketsQuery`      | `marketsQueryResponse`      | `communityId`, `startTime`, `endTime` (bounds of the opening time) |
| `ids.query`          | `idsQuery`          | `idsQueryResponse`          | `offchainId`                                                       |

Times go on the wire as RFC 3339 strings. The handler filters order time slots
on the right-open window `[startTime, endTime)`, like AMMBA's slot window. The
off-chain storage keeps order and market identifiers as `0x` followed by 32 hex
digits and matches `marketId` in `orders.query` and `trades.query` literally,
while `markets.query` returns markets with UUID identifiers; the client
converts a UUID market identifier to the stored form before querying.
`measurements.query` has no community filter: the calibration fetch step
drops records of other communities itself. The self-trigger scheduler asks for
the markets of each configured community that opened during the last 24 hours,
which keeps every response well below the broker's message size limit.

## Consumer identity

Message cursors on the gateway are kept per consumer identity, so every
consumer of a shared gateway needs its own client identifier. Sharing one would
let consumers read each other's messages. The client derives one identifier per
topic as the alphanumeric concatenation of a base and the topic name; with the
default base `ammclearingnode`, it polls `ordersQueryResponse` as
`ammclearingnodeordersQueryResponse`. Ad-hoc diagnostic scripts use the single
fixed identifier `ammclearingnodediag` and never generate random identifiers,
which would create new consumers on the gateway.

## Polling and load

Brokered responses typically take several seconds. To keep the load on a shared
gateway low, the client waits 1 s before the first poll and multiplies the
delay by 1.5 up to a ceiling of 5 s, until the timeout of 60 s elapses. Network
errors and HTTP 5xx responses are retried with bounded back-off. When the
self-trigger scheduler's market query fails, the scheduler doubles its tick
interval up to ten times the configured value. The initial delay, the ceiling,
the timeout and the scheduler interval are configurable; see the
[configuration reference](../reference/configuration.md#environment-variables).
The factor of 1.5 and the tenfold cap are fixed.

## Data normalisation

The handler's order objects follow the ontology. Older handler versions used
other field-naming dialects, which the client still accepts: it normalises every
order to the ontology's order shape before validation, for example mapping
snake_case to camelCase fields, legacy statuses such as `open` to the
ontology's `submitted`, and the `NONE` energy-type marker to an absent field. `OFFCHAIN_STRICT_VALIDATION=false` keeps orders that still fail
validation, logging them instead of dropping them. Measurement records are
passed to the calibration tool as received.

## Writing results

The `ewds` transport does not write trades or clearing results. In the
integrated platform, matching engines produce matches that are settled
on-chain, and the off-chain storage records trades from the settlement events.
See the [settlement engine](../implementation/settlement-engine.md).
