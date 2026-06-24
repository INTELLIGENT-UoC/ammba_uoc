# ARCHITECTURE.md — AMMBA Comprehensive Documentation

> **Last updated**: 2026-06-24
> **Status**: v1 MVP — the clearing node is integrated with the GSY DEX `int.*`
> ontology and tested end-to-end against a local off-chain DB simulator. The
> execution node (penalties) is deferred.

> ### v1 integration note (read before the older sections below)
>
> Parts of this document predate the GSY DEX data-contract alignment and are kept
> for algorithmic reference. The integration-facing reality as of v1:
>
> - **Wire contract = the `int.*` ontology** (`amm-clearing-node/schemas/intelligent/`).
>   The clearing node consumes `int:Order` and produces `int:Trade` +
>   `int:ClearingResult`. These are **flat** (UUID foreign keys, camelCase,
>   EUR/kWh, ISO-8601), unlike the older nested `bid_component`/`offer_component`
>   trade shape described in §7, which is retired. All translation happens in
>   `src/adapters.py`; the internal algorithm dicts are unchanged.
> - **The pool is a counterparty on the wire too.** Because `int:Trade` is
>   bilateral (one bid + one offer + a real buyer + seller), pool half-trades are
>   serialized by giving the pool a configured actor UUID (`pool_actor_uuid`) and
>   deterministic standing pool orders. This is provisional pending GSY's
>   pool-registration decision (§13).
> - **Units**: the sigmoid runs in ct/kWh (community bounds); the wire is EUR/kWh.
>   Conversion is isolated in `adapters.py` (`CT_PER_EUR`).
> - **Transport**: plain REST today (to the real off-chain DB or the bundled
>   simulator). The EW Client Gateway request/response channels replace it later,
>   behind the same adapter boundary.
> - **Scope**: the execution node, on-chain settlement conformance, energy-type
>   differential pricing, and the CGW transport are out of v1.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Component Documentation](#3-component-documentation)
   - 3.1 [AMM Smart Contract](#31-amm-smart-contract)
   - 3.2 [AMM Clearing Node](#32-amm-clearing-node)
   - 3.3 [AMM Execution Node](#33-amm-execution-node)
4. [Data Flow](#4-data-flow)
5. [Core Algorithms](#5-core-algorithms)
   - 5.1 [Sigmoid Price Function](#51-sigmoid-price-function)
   - 5.2 [Pro-Rata Allocation](#52-pro-rata-allocation)
   - 5.3 [Preference Matching](#53-preference-matching)
   - 5.4 [Penalty Calculation (VCG)](#54-penalty-calculation-vcg)
6. [API Reference](#6-api-reference)
7. [Data Schemas](#7-data-schemas)
8. [Configuration Reference](#8-configuration-reference)
9. [Test Coverage](#9-test-coverage)
10. [Development Guide](#10-development-guide)
11. [Deployment Guide](#11-deployment-guide)
12. [Decision Log](#12-decision-log)
13. [Open Items / TODOs](#13-open-items--todos)
14. [Glossary](#14-glossary)

---

## 1. System Overview

AMMBA (Automated Market Maker for Batch Auctions) is a peer-to-peer energy market mechanism. It runs periodic batch auctions where prosumers (buyers and sellers) submit energy orders into a community market. When a market slot closes, a sigmoid-based uniform clearing price is computed and all participants trade with a central AMM pool at that price, with quantities allocated pro-rata.

**Key properties**:
- **Uniform clearing price**: All participants in a slot pay/receive the same price (before preference adjustments)
- **Sigmoid pricing**: Price is a function of supply/demand ratio, bounded by community retail price (K_upper) and feed-in tariff (K_lower)
- **Pro-rata allocation**: When supply != demand, the short side is fully served and the long side is rationed proportionally
- **Pool-mediated trades**: Every participant trades with the AMM pool (not directly with each other), except preference-matched mutual pairs
- **On-chain audit**: Clearing results are anchored on the Energy Web Chain for transparency
- **VCG penalties**: Post-delivery, participants who deviated from commitments face penalties based on counterfactual pricing

**Three components**:
1. **AMM Smart Contract** — Solidity contract on Energy Web Chain, stores clearing results
2. **AMM Clearing Node** — Python/FastAPI service, runs the 8-step clearing algorithm
3. **AMM Execution Node** — Python/FastAPI service, computes post-delivery penalties

---

## 2. Architecture Diagram

```
                    Market Orchestrator
                    (external trigger)
                           |
                    POST /trigger-clearing
                           |
                           v
+------------------+    +--------------------+    +--------------------+
|  Off-chain DB    |<-->|  AMM Clearing Node |    |  AMM Smart Contract|
|  (GSY DEX)       |    |  :8081             |--->|  (Energy Web Chain)|
|  :8080           |    +--------------------+    +--------------------+
|                  |           |                         ^
|  - orders        |    POST /trades-normalized          |
|  - trades        |<----------+                   clearMarket()
|  - measurements  |                                     |
|                  |    +--------------------+            |
|                  |<-->|  AMM Execution Node|            |
|                  |    |  :8082             |            |
+------------------+    +--------------------+            |
                           |                              |
                    POST /trigger-execution               |
                           or                             |
                    --poll (autonomous)                    |
                                                          |
                    +--------------------+                |
                    |  EW Digital Spine  |<-- (Phase 3) --+
                    |  (metering data)   |
                    +--------------------+
```

**Data flow summary**:
1. External orchestrator triggers clearing when a 15-min market slot closes
2. Clearing Node fetches open orders from off-chain DB
3. Clearing Node computes sigmoid price, allocates quantities, generates trades
4. Clearing Node writes clearing result to smart contract and trades to off-chain DB
5. After delivery period (T + offset), Execution Node fetches trades and measurements
6. Execution Node computes penalties for any delivery deviations

---

## 3. Component Documentation

### 3.1 AMM Smart Contract

**Location**: `amm-smart-contract/`
**Technology**: Solidity ^0.8.24, Hardhat 2, Node.js
**Chain**: Energy Web Chain (Volta testnet for dev, EWC mainnet for prod)

#### Purpose
On-chain audit anchor. The sigmoid computation runs off-chain for efficiency; this contract receives the result, validates price bounds, stores it immutably, and emits events.

#### Key Functions

| Function | Access | Description |
|----------|--------|-------------|
| `clearMarket(marketId, communityUuid, timeSlot, totalSupply, totalDemand, clearingPrice)` | `onlyClearingNode` | Records clearing result. Validates price within [kLower, kUpper] if community params are set. Rejects duplicate marketId (idempotent). |
| `setCommunityParams(communityUuid, kUpper, kLower, theta, steepness)` | `onlyOwner` | Configures community price bounds and sigmoid parameters. |
| `setClearingNode(address)` | `onlyOwner` | Whitelists the off-chain clearing node address. |
| `getClearingResult(marketId)` | `view` | Returns (timeSlot, supply, demand, price) for auditing. |
| `getCommunityParams(communityUuid)` | `view` | Returns (kUpper, kLower, theta, steepness). |

#### Scaling Convention
All `uint256` values are scaled by `SCALING_FACTOR = 10000` (matching `NODE_FLOAT_SCALING_FACTOR` in Python). Example: 28.5 ct/kWh becomes 285000.

#### Structs
- **CommunityParams**: `{kUpper, kLower, theta, steepness, exists}`
- **ClearingResult**: `{communityUuid, timeSlot, totalSupply, totalDemand, clearingPrice, caller, blockTimestamp, exists}`

#### Events
- `MarketCleared(marketId, communityUuid, timeSlot, totalSupply, totalDemand, clearingPrice, blockTimestamp)`
- `CommunityParamsUpdated(communityUuid, kUpper, kLower, theta, steepness)`
- `ClearingNodeUpdated(newClearingNode)`

#### Files
| File | Description |
|------|-------------|
| `contracts/AMMContract.sol` | Main contract (205 lines) |
| `test/AMMContract.test.js` | 17 tests (deployment, params, clearing, access control, views) |
| `scripts/deploy.js` | Deployment script reading CLEARING_NODE_ADDRESS from env |
| `hardhat.config.js` | Hardhat 2 config with volta/ewc network definitions |

---

### 3.2 AMM Clearing Node

**Location**: `amm-clearing-node/`
**Technology**: Python 3.13, FastAPI, uv, httpx, web3.py, pydantic
**Port**: 8081

#### Purpose
Runs the core 8-step clearing algorithm when a market slot closes.

#### Module-by-Module Documentation

##### `src/clearing.py` — Core Algorithm
The main orchestration module. `run_clearing()` executes:

| Step | Description | Key Logic |
|------|-------------|-----------|
| 0 | Idempotency check | Fetches existing trades; skips if already cleared |
| 1 | Fetch open orders | Filters by `status == "Open"` and time_slot range |
| 2 | Aggregate supply/demand | Sums `energy` field from offers/bids |
| 3 | Compute clearing price | `sigmoid_price(supply/demand, K_upper, K_lower, theta, B)` |
| 4 | Record on-chain | Calls `clearMarket()` on smart contract (optional if no credentials) |
| 5 | Pro-rata allocation | Each participant gets `(their_energy / total) * traded_quantity` |
| 6 | Preference allocation | Mutual pairs get priority; remaining goes to pool trades |
| 7a | Generate preference trades | Direct buyer-seller trades for mutual pairs |
| 7b | Generate buyer-pool trades | Buyer -> Pool for remaining allocated_energy |
| 7c | Generate pool-seller trades | Pool -> Seller for remaining allocated_energy |
| 7d | Apply energy type multipliers | Green subsidy / grey levy adjustments |
| 8 | POST trades | Writes all trade objects to off-chain DB |

**Returns**: Summary dict with `{status, market_id, total_supply_kwh, total_demand_kwh, clearing_price_ct_per_kwh, traded_quantity_kwh, num_trades, tx_hash}`.

##### `src/sigmoid.py` — Sigmoid Price Function
```
price = K_upper - (K_upper - K_lower) / (1 + exp(-B * (ratio - theta)))
```
- `ratio = total_supply / total_demand`
- Overflow guards at exponent > 500 / < -500
- Clamped to [K_lower, K_upper]
- `to_node_int()` / `from_node_int()` scaling utilities (factor: 10000)

##### `src/adapters.py` — Wire translation + trade construction
> Supersedes the former `src/trade_builder.py` (which built the retired nested
> trade shape with blake2b `_id`s). Trades are now built directly as flat
> `int:Trade` objects.

Three `int:Trade` builders, all validated against `int.trade.schema.v1.json`:

| Function | Trade Type | buyerId | sellerId |
|----------|-----------|---------|----------|
| `build_buyer_pool_int_trade()` | Buyer -> Pool | participant | `pool_actor_uuid` |
| `build_pool_seller_int_trade()` | Pool -> Seller | `pool_actor_uuid` | participant |
| `build_direct_int_trade()` | Buyer -> Seller (preference) | buyer | seller |

Each `int:Trade` is flat: `tradeId` (deterministic `uuid5`), `marketId`, `bidId`,
`buyerId`, `offerId`, `sellerId`, `tradeStatus`, `tradeQuantity`, `tradePrice`
(EUR/kWh), `tradedAt` (ISO-8601). Pool half-trades reference deterministic pool
standing-order UUIDs for the missing side. `adapters.py` also builds the
`int:ClearingResult` and maps inbound `int:Order` → the internal dict.

##### `src/preferences.py` — Preference Matching
Two mechanisms implemented:

**1. Preferred Trading Partners (Priority Allocation)**
- `find_mutual_preferred_pairs()`: Scans bids/offers for mutual `requirements.trading_partner_id` matches
- `apply_priority_allocation()`: Allocates min(bid_allocated, offer_allocated) to mutual pairs, deducts from their pool allocation
- Results stored as `_preference_matches` on bid/offer dicts for trade builder

**2. Energy Type Multipliers (Differential Pricing)**
- `apply_energy_type_multipliers()`: Post-price adjustment
- Green types: `{GREEN, PV, HYDRO, BIOMASS, BATTERY}` -> price + subsidy
- Grey types: `{GREY}` -> price - levy
- **Levy Cap**: Grey levy capped at `levy_cap_ct_per_kwh`
- **Dynamic Subsidy Scaling**: If grey revenue < target subsidy, scale down subsidy proportionally (zero-sum guarantee)
- `EnergyTypeMultipliers` dataclass: `{green_subsidy_rate, grey_levy_rate, levy_cap_ct_per_kwh}`

##### `src/offchain_db.py` — HTTP Client
Async httpx client wrapping the GSY DEX off-chain DB REST API:
- `get_orders(market_id, start_time, end_time)` -> `GET /orders`
- `get_trades(market_id)` -> `GET /trades`
- `post_trades(trades)` -> `POST /trades-normalized`
- `health_check()` -> `GET /health_check`

##### `src/contract.py` — Web3.py Wrapper
- Loads ABI from Hardhat artifacts (`../amm-smart-contract/artifacts/...`)
- `AMMContractClient.clear_market()`: Converts hex market_id to bytes32, scales values via `to_node_int()`, builds + signs + sends transaction, waits for receipt
- Uses `ExtraDataToPOAMiddleware` for Energy Web Chain (PoA)

##### `src/config.py` — Configuration
- `CommunityConfig`: `{k_upper_ct_per_kwh, k_lower_ct_per_kwh, theta, steepness, pool_id}`
- `Settings`: All service config including communities dict
- `load_settings()`: Loads from `configuration.yaml`, env vars always override

##### `src/main.py` — FastAPI Application
- `POST /trigger-clearing` (202): Accepts `{market_id, community_uuid, time_slot}`, runs clearing
- `GET /health`: Returns `{status: "ok"}`
- `create_app()`: Factory pattern, initializes DB client and optional contract client

---

### 3.3 AMM Execution Node

**Location**: `amm-execution-node/`
**Technology**: Python 3.13, FastAPI, uv, httpx, pydantic
**Port**: 8082

#### Purpose
Post-delivery penalty computation. Compares what was traded vs. what was actually delivered/consumed, and applies VCG-based penalties to incentivize truthful reporting.

#### Module-by-Module Documentation

##### `src/penalties.py` — Penalty Formulas
Three penalty types from the IMPLEMENTATION_GUIDE.md:

| Penalty | When Applied | Formula |
|---------|-------------|---------|
| **Seller Shortfall** | Seller delivered less than traded | `K_sho * max(0, energy_traded - actual_delivered - eta)` where `K_sho = gamma * K_upper` |
| **Seller Externality** | Seller withheld supply (supply-limited rounds) | `max(0, (clearing_price - p_counterfactual) * traded_quantity)` where counterfactual adds withheld supply |
| **Buyer Externality** | Buyer underreported demand (demand-limited rounds) | `max(0, (p_counterfactual - clearing_price) * traded_quantity)` where counterfactual adds unreported demand |

VCG penalties use counterfactual sigmoid pricing: "what would the price have been if this participant reported truthfully?"

`compute_penalties_for_trades()`: Aggregate function that:
1. Extracts clearing parameters from trade objects
2. Determines if round was supply-limited or demand-limited
3. Classifies each trade as seller or buyer based on pool position
4. Fetches actual measurements per area_uuid
5. Returns per-trade penalty breakdown

##### `src/execution.py` — Execution Cycle
`run_execution_cycle()`:
1. Fetches settled trades for the market
2. Collects actual measurements from off-chain DB per area_uuid
3. Calls `compute_penalties_for_trades()`
4. Returns penalty results (persistence strategy TBD)

`compute_previous_timeslot()`: Calculates the most recently completed delivery slot that's older than `execution_offset_min`.

##### `src/offchain_db.py` — HTTP Client (Execution)
Similar to clearing node but adds:
- `get_community_markets(community_uuid)` -> `GET /community-market`
- `get_asset_measurements(community_uuid, area_uuid)` -> `GET /asset_measurements`

##### `src/config.py` — Configuration (Execution)
Extends clearing config with:
- `PenaltyConfig`: `{gamma: 1.1, eta: 0.0}`
- `execution_offset_min`: How long after delivery before checking (default: -120 min)
- `polling_interval_sec`: Polling loop interval (default: 300 sec)

##### `src/main.py` — FastAPI Application + Polling
Two modes:
- **HTTP mode** (default): `POST /trigger-execution` endpoint
- **Polling mode** (`--poll` flag): Autonomous loop checking for completed slots

---

## 4. Data Flow

### 4.1 Clearing Flow (per market slot)

```
Time: T-15min         T (slot close)          T+1sec
  |                     |                       |
  |  Buyers/Sellers     |  Market Orchestrator  |
  |  submit orders      |  triggers clearing    |
  |  POST /orders       |  POST /trigger-clearing|
  v                     v                       v

          +---------------------------------------+
          |         Clearing Node Pipeline         |
          |                                        |
          |  1. GET /orders (filter Open)           |
          |  2. Sum supply, sum demand              |
          |  3. sigmoid_price(S/D ratio)            |
          |  4. clearMarket() on smart contract     |
          |  5. Pro-rata allocation                 |
          |  6. Preference matching (mutual pairs)  |
          |  7. Build trade objects                 |
          |  8. POST /trades-normalized             |
          +---------------------------------------+
```

### 4.2 Execution Flow (per delivered slot)

```
Time: T+delivery        T+delivery+offset
  |                       |
  |  Smart meters         |  Execution Node
  |  report actuals       |  runs penalties
  v                       v

          +---------------------------------------+
          |        Execution Node Pipeline         |
          |                                        |
          |  1. GET /trades (filter Settled)        |
          |  2. GET /asset_measurements per area    |
          |  3. Compare traded vs actual            |
          |  4. Compute shortfall + VCG penalties   |
          |  5. Return penalty results              |
          +---------------------------------------+
```

### 4.3 Trade Model

Every participant trades with the AMM pool, not directly with each other. This creates two trades per participant:

```
Buyer A  --[2.5 kWh @ 18.3 ct]--> AMM Pool
AMM Pool --[3.0 kWh @ 18.3 ct]--> Seller B
AMM Pool --[1.5 kWh @ 18.3 ct]--> Seller C
Buyer D  --[2.0 kWh @ 18.3 ct]--> AMM Pool
```

**Exception**: Preference-matched mutual pairs trade directly:
```
Buyer A  --[1.0 kWh @ 18.3 ct]--> Seller B   (direct, preference_matched=True)
Buyer A  --[1.5 kWh @ 18.3 ct]--> AMM Pool   (remaining allocation)
```

---

## 5. Core Algorithms

### 5.1 Sigmoid Price Function

```
price = K_upper - (K_upper - K_lower) / (1 + exp(-B * (ratio - theta)))
```

| Parameter | Description | Typical Value |
|-----------|-------------|---------------|
| `K_upper` | Community retail buy price (ct/kWh) | 30.0 |
| `K_lower` | Community feed-in tariff (ct/kWh) | 8.0 |
| `theta` | Sigmoid midpoint (supply/demand ratio) | 1.0 |
| `B` (steepness) | Sigmoid steepness | 2.5 |
| `ratio` | `total_supply / total_demand` | varies |

**Behavior**:
- `ratio << theta` (scarce supply): price approaches K_upper
- `ratio == theta` (balanced): price at midpoint
- `ratio >> theta` (excess supply): price approaches K_lower

**Implementation guards**: Exponent clamped at [-500, 500] to prevent `math.exp()` overflow. Output clamped to [K_lower, K_upper].

### 5.2 Pro-Rata Allocation

```python
traded_quantity = min(total_supply, total_demand)

for each offer:
    allocated = (offer.energy / total_supply) * traded_quantity

for each bid:
    allocated = (bid.energy / total_demand) * traded_quantity
```

If supply > demand, sellers are rationed. If demand > supply, buyers are rationed. Each gets a proportional share of the tradeable quantity.

### 5.3 Preference Matching

**Phase 1: Priority Allocation (Mutual Trading Partners)**
1. Scan all bid/offer pairs for mutual `requirements.trading_partner_id`
2. For mutual pairs, allocate `min(bid_allocated, offer_allocated)` as a direct trade
3. Deduct from their pool allocation (so remaining goes through AMM pool)
4. Direct trades use `preference_matched: True` in parameters

**Phase 2: Energy Type Multipliers**
Applied post-price to all trades:
1. Classify trades as green/grey based on offer `attributes.energy_type`
2. Green: `final_price = clearing_price + (clearing_price * green_subsidy_rate)`
3. Grey: `final_price = clearing_price - min(clearing_price * grey_levy_rate, levy_cap)`
4. **Zero-sum constraint**: If grey revenue < green subsidy target, scale down subsidy

### 5.4 Penalty Calculation (VCG)

**Seller Shortfall**: Direct penalty for under-delivery.
```
penalty = gamma * K_upper * max(0, energy_traded - actual_delivered - eta)
```

**Seller Externality (VCG)**: "What if this seller had offered their full capacity?"
```
counterfactual_supply = total_supply + withheld_supply
p_cf = sigmoid(counterfactual_supply / total_demand)
penalty = max(0, (clearing_price - p_cf) * total_traded)
```

**Buyer Externality (VCG)**: "What if this buyer had reported their true demand?"
```
counterfactual_demand = total_demand + unreported_demand
p_cf = sigmoid(total_supply / counterfactual_demand)
penalty = max(0, (p_cf - clearing_price) * total_traded)
```

---

## 6. API Reference

### 6.1 Clearing Node (port 8081)

| Method | Endpoint | Request Body | Response | Description |
|--------|----------|-------------|----------|-------------|
| `POST` | `/trigger-clearing` | `{market_id, community_uuid, time_slot}` | 202 `{status, detail}` | Trigger clearing for a market slot |
| `GET` | `/health` | — | 200 `{status: "ok"}` | Health check |

### 6.2 Execution Node (port 8082)

| Method | Endpoint | Request Body | Response | Description |
|--------|----------|-------------|----------|-------------|
| `POST` | `/trigger-execution` | `{market_id, community_uuid, time_slot}` | 202 `{status, detail}` | Trigger penalty computation |
| `GET` | `/health` | — | 200 `{status: "ok"}` | Health check |

### 6.3 Off-chain DB (port 8080, external)

| Method | Endpoint | Parameters | Description |
|--------|----------|------------|-------------|
| `GET` | `/orders` | `market_id, start_time, end_time` | Fetch orders for a market slot |
| `POST` | `/orders` | JSON body | Create an order |
| `GET` | `/trades` | `market_id` | Fetch trades for a market |
| `POST` | `/trades-normalized` | JSON array | Write trade objects |
| `GET` | `/asset_measurements` | `community_uuid, area_uuid` | Fetch metering data |
| `GET` | `/community-market` | `community_uuid` | Fetch markets for a community |
| `GET` | `/health_check` | — | Health check |

---

## 7. Data Schemas

> **v1 wire format:** The authoritative on-the-wire schemas are the vendored
> `int.*` JSON Schemas in `amm-clearing-node/schemas/intelligent/`
> (`int.order`, `int.trade`, `int.clearing-result`). The shapes shown in 7.1–7.3
> below are the **internal** representation (and, for 7.2, the retired nested
> trade shape). `src/adapters.py` maps between the two; see the v1 integration
> note at the top of this document.

### 7.1 Order Object (internal representation, mapped from `int:Order`)
```json
{
  "order_id": "0xabc...",
  "status": "Open",
  "order_type": "Bid",
  "market_id": "market-uuid",
  "area_uuid": "prosumer-area-uuid",
  "created_by": "prosumer-id",
  "energy": 2.5,
  "energy_rate": 30.0,
  "time_slot": 1700000000,
  "creation_time": 1699999900,
  "nonce": 1,
  "requirements": {
    "trading_partner_id": ["seller-id-1"],
    "energy_source": ["GREEN", "PV"]
  },
  "attributes": {
    "trading_partner_id": ["buyer-id-1"],
    "energy_type": ["PV"]
  }
}
```

### 7.2 Trade Object (written to off-chain DB)
```json
{
  "_id": "0x<blake2b-256-hash>",
  "trade_uuid": "uuid-v4",
  "status": "Settled",
  "buyer": "buyer-id",
  "seller": "AMM_POOL_community-uuid",
  "market_id": "market-uuid",
  "time_slot": 1700000000,
  "creation_time": 1700000010,
  "offer": {
    "seller": "AMM_POOL_community-uuid",
    "offer_component": {
      "area_uuid": "AMM_POOL_community-uuid",
      "market_id": "market-uuid",
      "time_slot": 1700000000,
      "creation_time": 1700000010,
      "energy": 2.5,
      "energy_rate": 18.3
    }
  },
  "offer_hash": "0x...",
  "bid": {
    "buyer": "buyer-id",
    "nonce": 1,
    "bid_component": {
      "area_uuid": "buyer-area-uuid",
      "market_id": "market-uuid",
      "time_slot": 1700000000,
      "creation_time": 1699999900,
      "energy": 2.5,
      "energy_rate": 18.3
    }
  },
  "bid_hash": "0x...",
  "residual_offer": null,
  "residual_bid": null,
  "parameters": {
    "selected_energy": 2.5,
    "energy_rate": 18.3,
    "trade_uuid": "uuid-v4",
    "amm_tx_hash": "0x...",
    "theta": 1.0,
    "steepness": 2.5,
    "total_supply_kwh": 10.0,
    "total_demand_kwh": 8.0,
    "preference_matched": false
  }
}
```

### 7.3 Penalty Result Object
```json
{
  "trade_uuid": "uuid-v4",
  "seller_shortfall_penalty": 0.0,
  "seller_externality_penalty": 1.25,
  "buyer_externality_penalty": 0.0,
  "total_penalty": 1.25
}
```

---

## 8. Configuration Reference

### 8.1 Clearing Node (`amm-clearing-node/configuration.yaml`)
```yaml
application:
  host: "0.0.0.0"
  port: 8081

offchain_db:
  base_url: "http://localhost:8080"

blockchain:
  rpc_url: "https://volta-rpc.energyweb.org"
  contract_address: "0x..."

market:
  time_slot_sec: 900   # 15 minutes

communities:
  community-uuid-1:
    k_upper_ct_per_kwh: 30.0
    k_lower_ct_per_kwh: 8.0
    theta: 1.0
    steepness: 2.5
    pool_id: "AMM_POOL_community-uuid-1"
```

### 8.2 Execution Node (`amm-execution-node/configuration.yaml`)
```yaml
application:
  host: "0.0.0.0"
  port: 8082

offchain_db:
  base_url: "http://localhost:8080"

market:
  time_slot_sec: 900
  execution_offset_min: -120   # Run 2 hours after delivery
  polling_interval_sec: 300    # Check every 5 minutes

penalties:
  gamma: 1.1     # Shortfall multiplier
  eta: 0.0       # Tolerance threshold (kWh)

communities:
  community-uuid-1:
    k_upper_ct_per_kwh: 30.0
    k_lower_ct_per_kwh: 8.0
    theta: 1.0
    steepness: 2.5
```

### 8.3 Environment Variable Overrides
Environment variables always take precedence over YAML:

| Variable | Node | Description |
|----------|------|-------------|
| `OFFCHAIN_DB_URL` | Both | Off-chain DB base URL |
| `RPC_URL` | Clearing | Blockchain RPC endpoint |
| `CONTRACT_ADDRESS` | Clearing | Deployed contract address |
| `CLEARING_NODE_PRIVATE_KEY` | Clearing | Wallet key for signing tx |
| `TIME_SLOT_SEC` | Both | Market slot duration |
| `EXECUTION_OFFSET_MIN` | Execution | Post-delivery wait time |
| `POLLING_INTERVAL_SEC` | Execution | Polling loop interval |
| `HOST` | Clearing | Server bind host |
| `PORT` | Clearing | Server bind port |

---

## 9. Test Coverage

### 9.1 Smart Contract Tests (17 tests)
```
cd amm-smart-contract && npx hardhat test
```
| Category | Tests | Description |
|----------|-------|-------------|
| Deployment | 2 | Owner, clearingNode set correctly |
| setCommunityParams | 3 | Set params, kUpper >= kLower validation, onlyOwner |
| clearMarket | 6 | Basic clearing, price bounds validation, idempotency, events, supply-limited, access control |
| setClearingNode | 2 | Update address, onlyOwner |
| View functions | 4 | getClearingResult, getCommunityParams, edge cases |

### 9.2 Clearing Node Tests (55 tests)
```
cd amm-clearing-node && uv sync --extra dev && uv run pytest -v
```
| File | Tests | Description |
|------|-------|-------------|
| `test_sigmoid.py` | 10 | Scaling roundtrip, balanced/imbalanced markets, clamping, edge cases, cross-validation, monotonicity |
| `test_ontology.py` | — | Validator: valid order/trade pass; missing-required, bad-enum, additionalProperties, bad-uuid, non-positive quantity fail |
| `test_adapters.py` | — | Time/price conversion, deterministic pool/trade UUIDs, `int:Order`→internal mapping, built `int:Trade`/`int:ClearingResult` validate |
| `test_clearing.py` | — | Clearing against the int.* contract: imbalance, no bids/offers (NO_BID result), idempotency, status filtering, price bounds, pro-rata, direct preference pair |
| `test_e2e.py` | — | End-to-end via the real client against the off-chain DB simulator (ASGI), schema-validated both ways |
| `test_preferences.py` | 13 | Mutual pair finding, priority allocation, energy-type multipliers (function retained; dormant on the int.* path), integration |

### 9.3 Execution Node Tests (19 tests)
```
cd amm-execution-node && uv run pytest -v
```
| File | Tests | Description |
|------|-------|-------------|
| `test_penalties.py` | 14 | Shortfall (5: basic, exact delivery, over-delivery, eta tolerance, zero traded), seller externality (3: basic, no withholding, high withholding), buyer externality (3: basic, no underreport, demand-limited), aggregate (3) |
| `test_execution.py` | 5 | Timeslot computation (2), no trades skip, shortfall detection, no deviations |

**Total: 91 tests across all components** (clearing 55, execution 19 — deferred, contract 17).

---

## 10. Development Guide

### 10.1 Prerequisites
- **Node.js 20+** (for Hardhat 2)
- **Python 3.13** (for clearing and execution nodes)
- **uv** (Python package manager): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Docker** (optional, for containerized deployment)

### 10.2 Initial Setup
```bash
# Clone and enter project
cd /path/to/AMMBA

# Smart contract
cd amm-smart-contract
npm install
npx hardhat compile
npx hardhat test          # Verify 17 tests pass

# Clearing node
cd ../amm-clearing-node
uv sync --extra dev       # Install dependencies (incl. pytest)
uv run pytest -v          # Verify 55 tests pass

# Execution node
cd ../amm-execution-node
uv sync
uv run pytest -v          # Verify 19 tests pass
```

### 10.3 Running Services Locally
```bash
# Terminal 1: Clearing Node
cd amm-clearing-node
uv run uvicorn src.main:app --port 8081 --reload

# Terminal 2: Execution Node
cd amm-execution-node
uv run uvicorn src.main:app --port 8082 --reload

# Terminal 3: Execution Node (polling mode)
cd amm-execution-node
uv run python -m src.main --poll
```

### 10.4 Docker
```bash
docker compose up --build
```
Services: clearing node (8081), execution node (8082). Expects an external off-chain DB at `offchain-db:8080`.

### 10.5 Adding a New Community
1. Add entry to `configuration.yaml` under `communities:`
2. Optionally call `setCommunityParams()` on the smart contract to enable on-chain price validation
3. The pool_id follows the convention `AMM_POOL_{community_uuid}`

---

## 11. Deployment Guide

### 11.1 Volta Testnet (Development)
```bash
cd amm-smart-contract

# Set deployer private key (with Volta test tokens)
export DEPLOYER_PRIVATE_KEY=0x...
export CLEARING_NODE_ADDRESS=0x...

npx hardhat run scripts/deploy.js --network volta
```

### 11.2 EWC Mainnet
**Do not deploy to mainnet without explicit instruction.** Same process as Volta but use `--network ewc` and real credentials.

### 11.3 Docker Production
Set all environment variables in `.env` file or CI secrets:
```
CONTRACT_ADDRESS=0x...
CLEARING_NODE_PRIVATE_KEY=0x...
OFFCHAIN_DB_URL=http://offchain-db:8080
RPC_URL=https://rpc.energyweb.org
```

---

## 12. Decision Log

Architectural and implementation decisions made during development:

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | **Hardhat 2 over Hardhat 3** | System has Node 20.12; Hardhat 3 requires Node 22+. Also Hardhat 3 ESM-only conflicts with hardhat-toolbox CJS. | 2026-02-24 |
| 2 | **uv over pip/poetry** | Faster, integrated venv management, simpler pyproject.toml. User selected. | 2026-02-24 |
| 3 | **Mock-first for off-chain DB** | No GSY DEX instance running locally. All tests use in-memory mock clients. Real integration deferred. | 2026-02-24 |
| 4 | **Contract client optional in clearing.py** | Allows clearing to run without blockchain access (returns `tx_hash="0x0"`). Essential for local dev and testing. | 2026-02-24 |
| 5 | **Preference matches stored on order dicts** | Uses `_preference_matches` key (underscore = internal) on bid/offer dicts passed between clearing steps. Avoids extra data structures. | 2026-02-24 |
| 6 | **Energy type multipliers applied post-trade-generation** | Multipliers modify existing trade parameters rather than influencing allocation. This preserves the clearing price purity. | 2026-02-24 |
| 7 | **Separate sigmoid.py in both nodes** | Execution node needs sigmoid for counterfactual pricing. Duplicated rather than sharing a package to keep nodes independently deployable. | 2026-02-24 |
| 8 | **CJS (not ESM) for smart contract project** | Hardhat 2 + hardhat-toolbox uses `require()`. Consistent with ecosystem. | 2026-02-24 |
| 9 | ~~**blake2b-256 for trade IDs**~~ **Superseded (v1)** | `int:Trade` uses a UUID `tradeId`. We now derive a deterministic `uuid5` in `adapters.py` (reproducible re-runs) instead of a blake2b `_id`. | 2026-06-24 |
| 11 | **int:Trade serialized with the pool as an actor** | `int:Trade` is bilateral; pool half-trades reference a configured `pool_actor_uuid` and deterministic standing pool orders so they validate. Provisional pending GSY pool registration (§13.1). | 2026-06-24 |
| 12 | **Dependency-free ontology validator** | Validate at the I/O boundary against the vendored `int.*` schemas without adding `jsonschema` (lockfile hygiene). See `src/ontology.py`. | 2026-06-24 |
| 10 | **Execution node polling loop vs. cron** | Built-in polling loop (`--poll` flag) matches GSY DEX execution engine pattern. Can also be triggered via HTTP for testing. | 2026-02-24 |

---

## 13. Open Items / TODOs

### 13.1 Blocked on External Input

| # | Item | Blocker | Priority | Notes |
|---|------|---------|----------|-------|
| 1 | **Pool representation in `int:Trade`** | Confirm with GSY how the AMM pool registers as an actor and whether synthetic pool standing orders are acceptable | HIGH | v1 serializes pool half-trades with `pool_actor_uuid` + deterministic pool order UUIDs (`adapters.py`). Provisional convention. |
| 2 | **Transport: REST vs EW CGW** | Confirm AMM targets the CGW publish/poll request/response pattern; lock topic names, FQCNs, a distinct AMM client id, gateway URL | HIGH | v1 uses REST (real DB or the local simulator). CGW client slots in behind the adapter once conventions are fixed. |
| 3 | **`marketId` UUID ↔ bytes32** | Who owns the mapping; which encoding crosses the wire | HIGH | `int:*` uses UUID `marketId`; the orders.query payload and on-chain path use bytes32. Affects `contract.py`. |
| 4 | **Matchable order statuses** | Which `int:Order.orderStatus` values count as open/matchable | MEDIUM | v1 treats `Submitted`/`PartiallyFilled` as open (`MATCHABLE_ORDER_STATUSES`). |
| 5 | **Trade / clearing-result write path** | No `*.upsert` envelope exists; confirm how AMM writes back over EWDS | MEDIUM | v1 posts REST `/trades-normalized` + `/clearing-results`. |
| 6 | **Order status update after clearing** | GSY DEX may not support PATCH; how are cleared orders marked executed | MEDIUM | Relying on the idempotency check (existing trades) for now. |
| 7 | **Per-slot pricing params home** | `int:Trade`/`int:ClearingResult` have no field for `theta`/`steepness` | LOW | Needed only if the (deferred) execution node is revived. |
| 8 | **Measurement feed for penalties** | `int:Measurement` shape, units/sign convention; no `/asset_measurements` route exists | LOW | Blocks reviving the execution node. |

### 13.2 Implementation TODOs

| # | Item | Component | Priority | Notes |
|---|------|-----------|----------|-------|
| 9 | **Integration test with real off-chain DB** | Clearing | HIGH | Local end-to-end now runs against the schema-validating simulator (`tests/test_e2e.py`, `sim/`). Still need a run against a real GSY DEX instance. |
| 10 | **Volta testnet deployment** | Smart Contract | HIGH | Deploy to Volta, run end-to-end with real transactions. |
| 11 | **Retry logic for off-chain DB calls** | Clearing | MEDIUM | Currently no retries on HTTP failures. Add exponential backoff via `tenacity` or `httpx` retry. |
| 12 | ~~**CI/CD pipeline**~~ DONE | All | — | GitHub Actions runs the test suites on push/PR. See `.github/workflows/ci.yml`. |
| 13 | **Logging to structured JSON** | Clearing + Execution | LOW | Current logging is plaintext. Structured logs would help with observability. |
| 14 | **Metrics / monitoring** | Clearing + Execution | LOW | Add Prometheus metrics: clearing duration, trade count, penalty totals, etc. |
| 15 | **Energy type multiplier configuration UI/API** | Clearing | LOW | Community managers need a way to set multipliers. Currently code-level config only. |
| 16 | **Rate limiting on trigger endpoints** | Clearing + Execution | LOW | Prevent accidental double-triggering beyond the idempotency check. |

### 13.3 Known Limitations

| # | Limitation | Impact | Mitigation |
|---|-----------|--------|------------|
| 1 | **Sigmoid computed off-chain** | Clearing node could submit fraudulent prices | Smart contract validates price within [K_lower, K_upper] bounds |
| 2 | **No order status update** | Orders remain "Open" after clearing | Idempotency check prevents re-clearing, but stale orders accumulate |
| 3 | **Single clearing node** | No HA / failover | Docker restart policy; future: multi-node with consensus |
| 4 | **Penalties not persisted** | Execution results returned but not stored | Caller (or future settlement service) must handle persistence |
| 5 | **No authentication on endpoints** | Anyone can trigger clearing/execution | Acceptable for dev; add API keys or mTLS for production |
| 6 | **Duplicate sigmoid.py** | Code duplication between clearing and execution nodes | Acceptable trade-off for independent deployability |

---

## 14. Glossary

| Term | Definition |
|------|-----------|
| **AMMBA** | Automated Market Maker for Batch Auctions |
| **AMM Pool** | Virtual counterparty that intermediates all trades |
| **Batch Auction** | All orders in a time slot are cleared simultaneously at a uniform price |
| **Clearing** | The process of matching orders and determining the market price |
| **Clearing Price** | The uniform price at which all trades in a slot execute |
| **Community** | A group of prosumers participating in a local energy market |
| **EWC** | Energy Web Chain (mainnet) |
| **Execution** | Post-delivery verification and penalty computation |
| **Feed-in Tariff (K_lower)** | Minimum price floor (what grid pays for surplus energy) |
| **GSY DEX** | Decentralized energy exchange platform by GSY |
| **NODE_FLOAT_SCALING_FACTOR** | 10000 — multiplier for converting floats to on-chain integers |
| **Off-chain DB** | GSY DEX's REST API for storing orders, trades, and measurements |
| **Preference Matching** | Priority allocation for mutually preferred trading partners |
| **Pro-rata** | Proportional allocation of tradeable quantity |
| **Prosumer** | Producer-consumer of energy |
| **Retail Buy Price (K_upper)** | Maximum price ceiling (grid retail rate) |
| **Sigmoid** | S-shaped function mapping supply/demand ratio to clearing price |
| **Time Slot** | 15-minute market window (900 seconds) |
| **VCG** | Vickrey-Clarke-Groves mechanism — incentive-compatible penalty scheme |
| **Volta** | Energy Web Chain testnet |
