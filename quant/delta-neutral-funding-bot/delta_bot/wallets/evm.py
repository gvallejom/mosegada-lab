"""EVM wallet helper.

Used to:
  - derive the public address from the private key (sanity check)
  - read native + USDC/USDT balances
  - sign messages (e.g. for Hyperliquid registration)

We deliberately do NOT expose any "send_funds" or "transfer" method. Moving
collateral cross-chain is something the operator should do explicitly from a
wallet UI; bots holding withdraw permission is a footgun we won't enable.
"""
from __future__ import annotations
import structlog

logger = structlog.get_logger(__name__)


class EvmWallet:
    def __init__(self, private_key: str, rpc_url: str, chain_id: int = 42161):
        if not private_key:
            raise ValueError("EVM private key is empty")
        self.private_key = private_key
        self.rpc_url = rpc_url
        self.chain_id = chain_id
        self._address: str | None = None
        self._w3 = None

    def address(self) -> str:
        if self._address is None:
            try:
                from eth_account import Account
            except ImportError as e:
                raise RuntimeError(
                    "EvmWallet requires `eth-account`. pip install eth-account"
                ) from e
            self._address = Account.from_key(self.private_key).address
        return self._address

    def _web3(self):
        if self._w3 is None:
            try:
                from web3 import Web3
            except ImportError as e:
                raise RuntimeError(
                    "EvmWallet RPC calls require `web3`. pip install web3"
                ) from e
            self._w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 10}))
        return self._w3

    def native_balance(self) -> float:
        w3 = self._web3()
        wei = w3.eth.get_balance(self.address())
        return wei / 1e18

    def erc20_balance(self, token_address: str, decimals: int = 6) -> float:
        w3 = self._web3()
        # Minimal ERC20 balanceOf ABI
        abi = [{
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function",
        }]
        contract = w3.eth.contract(
            address=w3.to_checksum_address(token_address),
            abi=abi,
        )
        raw = contract.functions.balanceOf(
            w3.to_checksum_address(self.address())
        ).call()
        return raw / (10 ** decimals)
