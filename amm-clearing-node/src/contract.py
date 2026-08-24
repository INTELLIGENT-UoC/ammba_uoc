"""Web3.py wrapper for the AMM Smart Contract."""

import json
import logging
from pathlib import Path

from web3 import AsyncHTTPProvider, AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware

from src.sigmoid import to_node_int

logger = logging.getLogger(__name__)

# ABI path — compiled by Hardhat, referenced from the smart contract project
ABI_PATH = Path(__file__).parent.parent.parent / "amm-smart-contract" / "artifacts" / "contracts" / "AMMContract.sol" / "AMMContract.json"


def _load_abi() -> list:
    """Load the contract ABI from the Hardhat artifacts."""
    if not ABI_PATH.exists():
        raise FileNotFoundError(
            f"Contract ABI not found at {ABI_PATH}. "
            "Run 'npx hardhat compile' in amm-smart-contract/ first."
        )
    with open(ABI_PATH) as f:
        artifact = json.load(f)
    return artifact["abi"]


class AMMContractClient:
    """Async wrapper around the AMMContract on Energy Web Chain."""

    def __init__(
        self,
        rpc_url: str,
        contract_address: str,
        private_key: str,
    ):
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        self.account = self.w3.eth.account.from_key(private_key)
        abi = _load_abi()
        self.contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(contract_address),
            abi=abi,
        )

    async def clear_market(
        self,
        market_id: str,
        community_uuid: str,
        time_slot: int,
        total_supply_kwh: float,
        total_demand_kwh: float,
        clearing_price: float,
    ) -> str:
        """Call clearMarket on the smart contract.

        Returns the transaction hash.
        """
        # Convert market_id hex string to bytes32
        market_id_bytes = bytes.fromhex(market_id.lstrip("0x")).ljust(32, b"\x00")
        community_bytes = community_uuid.encode("utf-8").ljust(32, b"\x00")[:32]

        supply_scaled = to_node_int(total_supply_kwh)
        demand_scaled = to_node_int(total_demand_kwh)
        price_scaled = to_node_int(clearing_price)

        tx = await self.contract.functions.clearMarket(
            market_id_bytes,
            community_bytes,
            time_slot,
            supply_scaled,
            demand_scaled,
            price_scaled,
        ).build_transaction(
            {
                "from": self.account.address,
                "nonce": await self.w3.eth.get_transaction_count(
                    self.account.address
                ),
                "gas": 200000,
            }
        )

        signed = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)

        logger.info(
            "clearMarket tx confirmed: hash=%s block=%s",
            receipt["transactionHash"].hex(),
            receipt["blockNumber"],
        )

        return "0x" + receipt["transactionHash"].hex()
