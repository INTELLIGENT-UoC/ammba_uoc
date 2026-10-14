# Audit anchor contract

`amm-smart-contract` contains `AMMContract`, an optional on-chain audit anchor
for clearing results on the Energy Web Chain. The pricing function is evaluated
off-chain; the contract receives the result of each clearing, checks that the
price lies inside the community's band when the band is registered, stores the
result immutably, and emits an event. It does not move energy or money.

> **Optional.** In the integrated platform, trades are settled through the
> GSY DEX settlement layer (see the [settlement engine](settlement-engine.md)).
> The audit anchor is an additional transparency record and is not needed for
> settlement. The clearing engine's contract client currently expects
> hexadecimal market identifiers, while the exchange uses UUIDs; see
> [issue #36](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues/36).

## Interface

| Function                                                                                  | Access        | Description                                                                                                                                |
| ----------------------------------------------------------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `clearMarket(marketId, communityUuid, timeSlot, totalSupply, totalDemand, clearingPrice)` | Clearing node | Records a clearing result. Rejects a market that has already been recorded and, if the community's band is registered, a price outside it. |
| `setCommunityParams(communityUuid, kUpper, kLower, theta, steepness)`                     | Owner         | Registers a community's band and pricing parameters.                                                                                       |
| `setClearingNode(address)`                                                                | Owner         | Sets the address allowed to record results.                                                                                                |
| `getClearingResult(marketId)`                                                             | View          | Returns time slot, supply, demand and price of a recorded result.                                                                          |
| `getCommunityParams(communityUuid)`                                                       | View          | Returns a community's registered parameters.                                                                                               |

Events: `MarketCleared`, `CommunityParamsUpdated`, `ClearingNodeUpdated`.

All numeric values are unsigned integers scaled by `SCALING_FACTOR = 10000`, the
convention of the GSY DEX; 28.5 ct/kWh is stored as 285000.

## Build, test and deploy

```bash
cd amm-smart-contract
npm ci
npx hardhat compile
npx hardhat test
DEPLOYER_PRIVATE_KEY=0x... CLEARING_NODE_ADDRESS=0x... \
  npx hardhat run scripts/deploy.js --network volta
```

The Hardhat configuration defines the Volta test network and the Energy Web
Chain main network. Deploy to the main network only deliberately and with
dedicated keys.
