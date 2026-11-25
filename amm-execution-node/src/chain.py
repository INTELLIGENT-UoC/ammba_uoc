"""On-chain access for settlement (TradeSettlement.settleBatch).

Thin async web3 wrapper. Everything environment-specific (RPC URL, contract
address, the operator signer key, gas funding, chain id) comes from the
settlement environment, which is not available yet: the engine tests
substitute a FakeChain for this client, and ``main.py`` refuses --execute with
a message listing what is missing.

The engine places no orders: every match pairs two participant orders the
community client registered during the open market. The ABI fragment is
hand-declared for the one call the engine needs (tests check it against the
encoding signatures in structs.py); it is replaced by the compiled contract
artifacts once the contracts freeze.
"""

import logging

from web3 import AsyncHTTPProvider, AsyncWeb3

logger = logging.getLogger(__name__)

# Struct fields in contract order (OrderRegistry.OrderParams / TradeSettlement,
# GSYDEXv2 f0ea6c8).
_ORDER_PARAMS = [
    {"name": n, "type": t}
    for n, t in [
        ("orderId", "bytes16"),
        ("createdBy", "bytes16"),
        ("marketId", "bytes16"),
        ("timeSlot", "uint64"),
        ("creationTime", "uint64"),
        ("energy", "uint64"),
        ("energyRate", "uint64"),
        ("energySourcePreference", "uint8"),
        ("energyType", "uint8"),
        ("isBid", "bool"),
        ("preferredTradingPartner", "bytes16"),
        ("preferredEnergyRate", "uint64"),
    ]
]
_MATCH = [
    {"name": "tradeId", "type": "bytes16"},
    {"name": "bid", "type": "tuple", "components": _ORDER_PARAMS},
    {"name": "offer", "type": "tuple", "components": _ORDER_PARAMS},
    {"name": "residualBidId", "type": "bytes16"},
    {"name": "residualOfferId", "type": "bytes16"},
    {"name": "selectedEnergy", "type": "uint256"},
    {"name": "clearingPrice", "type": "uint256"},
    {"name": "matchType", "type": "uint8"},
]
_CLEARING_RESULT = [
    {"name": n, "type": t}
    for n, t in [
        ("marketId", "bytes16"),
        ("clearingStatus", "uint8"),
        ("clearingPrice", "uint256"),
        ("totalSupply", "uint256"),
        ("totalDemand", "uint256"),
        ("tradedQuantity", "uint256"),
        ("numTrades", "uint32"),
    ]
]
_MARKET_SETTLEMENT = [
    {"name": "matches", "type": "tuple[]", "components": _MATCH},
    {"name": "clearingResult", "type": "tuple", "components": _CLEARING_RESULT},
]


TRADE_SETTLEMENT_ABI = [
    {
        "name": "settleBatch",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "settlements", "type": "tuple[]", "components": _MARKET_SETTLEMENT}],
        "outputs": [],
    }
]


class SettlementChainClient:
    """Signs and submits settleBatch transactions."""

    def __init__(
        self,
        rpc_url: str,
        trade_settlement_address: str,
        private_key: str,
        gas_limit: int = 3_000_000,
    ):
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self.account = self.w3.eth.account.from_key(private_key)
        self.settlement = self.w3.eth.contract(
            address=self.w3.to_checksum_address(trade_settlement_address),
            abi=TRADE_SETTLEMENT_ABI,
        )
        self.gas_limit = gas_limit

    async def _send(self, fn) -> str:
        nonce = await self.w3.eth.get_transaction_count(self.account.address)
        tx = await fn.build_transaction(
            {"from": self.account.address, "nonce": nonce, "gas": self.gas_limit}
        )
        signed = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt["status"] != 1:
            raise RuntimeError(f"transaction reverted: {receipt['transactionHash'].hex()}")
        return "0x" + receipt["transactionHash"].hex()

    async def settle_batch(self, settlement_tuples: list[tuple]) -> str:
        return await self._send(self.settlement.functions.settleBatch(settlement_tuples))
