# AGENTS.md — amm-smart-contract

> Component-specific onboarding. See the [repo-root AGENTS.md](../AGENTS.md)
> for the big picture first.
>
> Public documentation: `docs/implementation/smart-contract.md`. Update these pages
> together with behaviour changes.

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
```

## Roles

- **owner** — can set community params, swap the clearing node.
- **clearingNode** — single whitelisted EOA that may call `clearMarket(...)`.

## Key functions

| Function                                                                                  | Modifier           | Purpose                                                    |
| ----------------------------------------------------------------------------------------- | ------------------ | ---------------------------------------------------------- |
| `clearMarket(marketId, communityUuid, timeSlot, totalSupply, totalDemand, clearingPrice)` | `onlyClearingNode` | Records a clearing result. Idempotent on `marketId`.       |
| `setCommunityParams(communityUuid, kUpper, kLower, theta, steepness)`                     | `onlyOwner`        | Configures price bounds + sigmoid params for verification. |
| `setClearingNode(address)`                                                                | `onlyOwner`        | Rotates the clearing node EOA.                             |
| `getClearingResult(marketId)`                                                             | `view`             | `(timeSlot, supply, demand, price)`                        |
| `getCommunityParams(communityUuid)`                                                       | `view`             | `(kUpper, kLower, theta, steepness)`                       |

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
export CLEARING_NODE_ADDRESS=0x...  # the clearing node's account (may call clearMarket)
npx hardhat run scripts/deploy.js --network volta
```

The constructor takes the clearing node address. Optional `COMMUNITY_UUID`,
`K_UPPER`, `K_LOWER`, `THETA`, `STEEPNESS` register one community's parameters
right after deployment; the identifier is packed with
`encodeBytes32String`, so it must fit into 32 bytes — a 36-character UUID
does not (see #36).

**EWC mainnet: do not deploy without explicit instruction in a PR.** The
network is defined but should never be triggered by CI or by an LLM.

After deployment:

1. Set `CONTRACT_ADDRESS` and `CLEARING_NODE_PRIVATE_KEY` in the clearing
   node's env.
2. Call `setCommunityParams(...)` for each community before clearing (unless
   the deploy script did it). `setClearingNode` rotates the clearing node's
   account later.

## Conventions to preserve

1. **`SCALING_FACTOR = 10000`** — load-bearing, matches Python side.
2. **`onlyClearingNode` on `clearMarket`** — the audit guarantee depends on
   this. Anyone can read; only the whitelisted EOA can write.
3. **Idempotency on `marketId`** — re-submitting the same `marketId` reverts.
   The clearing node relies on this to make retries safe.
4. **Price bounds check** — `clearingPrice ∈ [kLower, kUpper]` when community
   params exist. Don't relax this.
5. **`MarketCleared` event shape is API.** Off-chain indexers parse it (the
   clearing node only waits for the transaction receipt); adding fields is
   fine, reordering/removing is breaking.

## After ABI changes

The clearing node loads the ABI at runtime from
`../amm-smart-contract/artifacts/contracts/AMMContract.sol/AMMContract.json`.
After any contract change:

1. `npx hardhat compile` — regenerates artifacts.
2. Check `amm-clearing-node/src/contract.py` against the new ABI by hand: no
   automated test exercises the web3.py wrapper yet (its role is open in #36).

## Toolchain pinning

This contract project is intentionally on **Hardhat 2.x** + **hardhat-toolbox
5.x**. Hardhat 3 is a major rewrite (new config format, ESM-first, EDR
runtime). Migration is tracked in
[#67](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues/67).
Dependabot is configured to **ignore major-version bumps** of `hardhat` and
`@nomicfoundation/hardhat-toolbox`.

## Don'ts

- Don't add owner-only functions that can mutate stored `ClearingResult` —
  the contract's value is its immutability.
- Don't put community-specific business logic on-chain — it goes in the
  clearing node. The contract should stay a thin audit anchor.
- Don't bundle Hardhat globally — always use `npx hardhat`.
- Don't change the `SPDX-License-Identifier` from `GPL-3.0-or-later`.
