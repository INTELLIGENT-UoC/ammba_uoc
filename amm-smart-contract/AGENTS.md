# AGENTS.md — amm-smart-contract

> Component-specific onboarding. See the [repo-root AGENTS.md](../AGENTS.md)
> for the big picture first.

## What this contract does

`AMMContract.sol` is the **on-chain audit anchor** for AMMBA clearing.

It does **not** compute prices. The clearing node runs the sigmoid off-chain
(gas reasons), then calls `clearMarket(...)` with the result. The contract
validates bounds, stores the result keyed by `marketId`, and emits a
`MarketCleared` event.

Per-community parameters (`K_upper`, `K_lower`, `theta`, steepness) are set
on-chain by the owner so anyone can independently re-run the sigmoid and
verify the submitted price.

## File map

```
contracts/AMMContract.sol     # the contract (~205 lines, fully commented)
test/AMMContract.test.js      # 17 hardhat tests
scripts/deploy.js             # Volta/EWC deploy script
hardhat.config.js             # network config (volta, ewc)
ignition/                     # Hardhat Ignition module (alternative deploy)
```

## Roles

- **owner** — can set community params, swap the clearing node.
- **clearingNode** — single whitelisted EOA that may call `clearMarket(...)`.

## Key functions

| Function | Modifier | Purpose |
|---|---|---|
| `clearMarket(marketId, communityUuid, timeSlot, totalSupply, totalDemand, clearingPrice)` | `onlyClearingNode` | Records a clearing result. Idempotent on `marketId`. |
| `setCommunityParams(communityUuid, kUpper, kLower, theta, steepness)` | `onlyOwner` | Configures price bounds + sigmoid params for verification. |
| `setClearingNode(address)` | `onlyOwner` | Rotates the clearing node EOA. |
| `getClearingResult(marketId)` | `view` | `(timeSlot, supply, demand, price)` |
| `getCommunityParams(communityUuid)` | `view` | `(kUpper, kLower, theta, steepness)` |

## Scaling convention

**All `uint256` numeric inputs and outputs are scaled by `SCALING_FACTOR =
10000`**. This matches `NODE_FLOAT_SCALING_FACTOR` in the Python services.
Example: 28.5 ct/kWh → `285000`. Don't change this without coordinating with
both Python services.

## Dev loop

```bash
npm ci                              # install
npx hardhat compile                 # compile + regenerate ABI/artifacts
npx hardhat test                    # all 17 tests
npx hardhat test --grep "clearMarket"  # subset
```

Tests use `chai` matchers via Hardhat-Toolbox. They mint clearing results,
check storage, check events, and exercise access control.

## Deployment

**Volta testnet (default for dev):**
```bash
export DEPLOYER_PRIVATE_KEY=0x...   # account with VT tokens
npx hardhat run scripts/deploy.js --network volta
```

**EWC mainnet: do not deploy without explicit instruction in a PR.** The
network is defined but should never be triggered by CI or by an LLM.

After deployment:
1. Set `CONTRACT_ADDRESS` in the clearing node's env.
2. Call `setClearingNode(<clearing node EOA>)` from the owner account.
3. Call `setCommunityParams(...)` for each community before clearing.

## Conventions to preserve

1. **`SCALING_FACTOR = 10000`** — load-bearing, matches Python side.
2. **`onlyClearingNode` on `clearMarket`** — the audit guarantee depends on
   this. Anyone can read; only the whitelisted EOA can write.
3. **Idempotency on `marketId`** — re-submitting the same `marketId` reverts.
   The clearing node relies on this to make retries safe.
4. **Price bounds check** — `clearingPrice ∈ [kLower, kUpper]` when community
   params exist. Don't relax this.
5. **`MarketCleared` event shape is API.** Off-chain indexers and the Python
   clearing node parse it; adding fields is fine, reordering/removing is breaking.

## After ABI changes

The clearing node loads the ABI at runtime from
`../amm-smart-contract/artifacts/contracts/AMMContract.sol/AMMContract.json`.
After any contract change:

1. `npx hardhat compile` — regenerates artifacts.
2. Run the clearing-node tests — they exercise the web3.py wrapper end-to-end
   with a local mock.

## Toolchain pinning

This contract project is intentionally on **Hardhat 2.x** + **hardhat-toolbox
5.x**. Hardhat 3 is a major rewrite (new config format, ESM-first, EDR
runtime). Migration is tracked as a separate effort — see the open
[Hardhat 3 migration tracking issue](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues).
Dependabot is configured to **ignore major-version bumps** of `hardhat` and
`@nomicfoundation/hardhat-toolbox`.

## Don'ts

- Don't add owner-only functions that can mutate stored `ClearingResult` —
  the contract's value is its immutability.
- Don't put community-specific business logic on-chain — it goes in the
  clearing node. The contract should stay a thin audit anchor.
- Don't bundle Hardhat globally — always use `npx hardhat`.
- Don't change the `SPDX-License-Identifier` from `GPL-3.0-or-later`.
