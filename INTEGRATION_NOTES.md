# INTEGRATION_NOTES.md — provisional decisions & where to change them

This file is the single source of truth for everything the AMMBA integration
assumes **provisionally** while waiting on GSY DEX / Energy Web answers or
ontology changes. Each row is a decision we made so work could proceed, the
current behaviour, exactly where it lives in code, and what to change when the
external answer arrives. Keep this updated — it is the hand-off map for the next
contributor (human or LLM).

Status legend: 🟢 done & stable · 🟡 provisional, works, will adjust · 🔴 blocked on GSY

## Wire / transport

| # | Decision | Current behaviour | Where to change | Trigger to revisit |
|---|----------|-------------------|-----------------|--------------------|
| 1 | 🟡 Transport | Plain REST to the off-chain DB (or local sim) | `amm-clearing-node/src/offchain_db.py` is the seam; add a CGW publish/poll client implementing the same methods, select by env | GSY confirms CGW request/response + topic names |
| 2 | 🔴 Channel naming | n/a (REST) | new CGW client | GSY locks topic names, `topicOwner`, `topicVersion`, FQCNs, AMM `clientId`, gateway URL |
| 3 | 🟡 Write path | REST `POST /trades-normalized` + `/clearing-results` | `offchain_db.py` `post_trades` / `post_clearing_result` | GSY defines a `*.upsert` envelope (or confirms REST) |

## Identifiers, units, semantics

| # | Decision | Current behaviour | Where to change | Trigger to revisit |
|---|----------|-------------------|-----------------|--------------------|
| 4 | 🟡 `marketId` encoding | UUID on the `int.*` wire; bytes32 only on the on-chain/query-payload path | `adapters.py` (wire), `contract.py` (on-chain bytes32 — currently assumes hex, breaks on UUID) | GSY says who owns UUID↔bytes32 and which crosses the wire |
| 5 | 🟡 Matchable order statuses | `Submitted`, `PartiallyFilled` → internal "Open" | `adapters.MATCHABLE_ORDER_STATUSES` | GSY confirms which `orderStatus` values are matchable |
| 6 | 🟢 Price units | internal ct/kWh, wire EUR/kWh | `adapters.CT_PER_EUR` (only conversion point) | only if the ontology unit changes |
| 7 | 🔴 Clearing trigger | own `POST /trigger-clearing` endpoint | `amm-clearing-node/src/main.py` | GSY says orchestrator-push vs self-trigger off a CGW tick |

## Pool model

| # | Decision | Current behaviour | Where to change | Trigger to revisit |
|---|----------|-------------------|-----------------|--------------------|
| 8 | 🟡 Pool as `int:Trade` counterparty | pool = configured actor UUID (`pool_actor_uuid`) + deterministic synthetic standing pool orders | `adapters.pool_actor_uuid` / `pool_order_uuid`; `config.CommunityConfig.pool_actor_uuid` | GSY decides how the pool registers as an actor / whether synthetic pool orders are OK |

## Calibration (amm-calibration)

| # | Decision | Current behaviour | Where to change | Trigger to revisit |
|---|----------|-------------------|-----------------|--------------------|
| 9 | 🟡 Measurement sign | net-load: positive `energyKwh` = consumption, negative = injection | `amm-calibration/src/measurements.py` (`positive_is_consumption`) | GSY confirms `int:Measurement` sign/units |
| 10 | 🟡 Price bounds for calibration | flat per-community `k_upper`/`k_lower` | `calibrate.py` args; later a per-slot tariff series from `int:Tariff` | a tariff feed exists |
| 11 | 🟡 Parameter publishing | emit a `communities:` YAML snippet to merge into `configuration.yaml` (and/or `AMMContract.setCommunityParams`) | `amm-calibration/src/calibrate.py` `to_config_snippet` | an `int:AmmParameters` object exists (then write it; clearing node fetches live) |

## Proposed ontology extensions (to raise with GSY)

These are **not** added to the vendored schemas (we don't edit GSY's contract).
They are proposals; until adopted, the data either lives off-wire or is dropped.

| Field / object | Why | Interim handling |
|----------------|-----|------------------|
| `int:AmmParameters` (theta, steepness, kUpper, kLower, calibratedAt) or extend `int:MarketMechanism` | publish calibration output; the contract already stores these on-chain | config + on-chain `setCommunityParams` |
| `theta` / `steepness` / `ratio` / `mechanismName` on `int:ClearingResult` | make a clearing result self-describing/auditable | dropped from the wire (kept in the node's return summary) |
| pool counterparty marker on `int:Trade` (or nullable `bidId`/`offerId`) | avoid synthetic pool orders | synthetic pool order UUIDs (#8) |
| `preferredTradingPartner` as an array | support multiple/ranked preferred partners | single partner only (ontology cap) |
| differential-pricing provenance on `int:Trade` (basePrice, adjustment) | revive green/grey multipliers on the flat schema | multipliers dormant |
| `int:Penalty` / settlement-adjustment object | revive the execution node | execution node deferred |

## On-chain strategy

| # | Decision | Current behaviour | Where to change | Trigger to revisit |
|---|----------|-------------------|-----------------|--------------------|
| 12 | 🟡 On-chain scope | clearing runs off-chain; contract is an optional audit anchor (skipped by default) | `clearing.py` step 4; `amm-smart-contract/contracts/AMMContract.sol` | GSY scope answer #10 (settlement conformance vs off-chain only) |
| 13 | 🟡 Price verifiability | contract bounds-checks the price only | `AMMContract.clearMarket` | if trustless price wanted: compute the sigmoid on-chain from aggregates (params already on-chain) + Merkle-commit the order set; ZK later |

See ARCHITECTURE.md §13 for the broader open-items list and the questions sent to
GSY.
