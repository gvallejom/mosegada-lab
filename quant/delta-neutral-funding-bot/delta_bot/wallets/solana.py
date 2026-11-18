"""Solana wallet helper (read-only).

Same philosophy as EvmWallet: derive address, read balance, do NOT expose
transfer/spend methods. Movements should be triggered manually.
"""
from __future__ import annotations
import base58
import structlog

logger = structlog.get_logger(__name__)


class SolanaWallet:
    def __init__(self, private_key: str, rpc_url: str = "https://api.mainnet-beta.solana.com"):
        if not private_key:
            raise ValueError("Solana private key is empty")
        self.private_key = private_key
        self.rpc_url = rpc_url
        self._pubkey: str | None = None

    def address(self) -> str:
        if self._pubkey is None:
            try:
                from solders.keypair import Keypair  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "SolanaWallet requires `solders`. pip install solders"
                ) from e
            # Accept both base58 64-byte secret and JSON array forms
            if self.private_key.startswith("["):
                import json
                arr = json.loads(self.private_key)
                kp = Keypair.from_bytes(bytes(arr))
            else:
                raw = base58.b58decode(self.private_key)
                kp = Keypair.from_bytes(raw)
            self._pubkey = str(kp.pubkey())
        return self._pubkey

    def sol_balance(self) -> float:
        try:
            from solana.rpc.api import Client  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "SolanaWallet RPC calls require `solana`. pip install solana"
            ) from e
        client = Client(self.rpc_url)
        resp = client.get_balance(self.address())
        lamports = getattr(resp, "value", 0)
        return lamports / 1e9
