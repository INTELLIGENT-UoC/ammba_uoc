"""Off-chain ↔ on-chain identifier conventions (GSY id-mapping, 2026-09).

Mirrors ``primitives/src/utils/mod.rs`` in gsy-decentralized-exchange
(commit 648b346):

- **Order / trade / market ids** are random UUIDs converted with
  ``parse_uuid_or_hex_bytes16``: dashes stripped (or a ``0x`` prefix
  removed), 32 hex chars → 16 bytes. For a UUID this is exactly its RFC 4122
  byte form.
- **Actor ids** (buyer, seller, facility, pool) are NOT converted — they are
  *mapped*: ``onchain_id = blake2b-128(offchain_id_string)`` (their
  ``create_encrypted_bytes16_from_string``; a keyless hash despite the name).
  The storage keeps the mapping in its DB (``POST /ids?offchain_id=`` /
  EWDS ``ids.query``) so on-chain events can be attributed back to off-chain
  actors. Computing the hash locally is exact; registering the mapping with
  the storage is still required for that reverse lookup (see engine.py).
"""

import hashlib
import uuid

ZERO_BYTES16 = b"\x00" * 16


def parse_uuid_or_hex_bytes16(value: str) -> bytes:
    """UUID (dashed) or ``0x``-prefixed 32-hex string → 16 bytes.

    Parity with GSY's ``parse_uuid_or_hex_bytes16``; raises ValueError where
    theirs returns None.
    """
    text = value.strip()
    hex_value = text[2:] if text.startswith("0x") else text.replace("-", "")
    if len(hex_value) != 32:
        raise ValueError(f"not a UUID or 32-hex bytes16: {value!r}")
    try:
        return bytes.fromhex(hex_value)
    except ValueError as exc:
        raise ValueError(f"not a UUID or 32-hex bytes16: {value!r}") from exc


def uuid_to_bytes16(value: str) -> bytes:
    """Encode an order/trade/market UUID as its on-chain bytes16."""
    return parse_uuid_or_hex_bytes16(value)


def bytes16_to_uuid(value: bytes) -> str:
    """Decode an on-chain bytes16 order/trade/market id back to a UUID string."""
    if len(value) != 16:
        raise ValueError(f"expected 16 bytes, got {len(value)}")
    return str(uuid.UUID(bytes=value))


def bytes16_to_hex(value: bytes) -> str:
    """``0x``-prefixed hex, the storage's wire form for on-chain ids."""
    return "0x" + value.hex()


def actor_onchain_id(offchain_id: str) -> bytes:
    """On-chain bytes16 for an actor: blake2b-128 of the off-chain id string.

    Hashes the string exactly as given (a UUID keeps its dashes) — this is
    what the storage stores as ``onchain_id`` for that ``offchain_id``.
    """
    return hashlib.blake2b(offchain_id.encode("utf-8"), digest_size=16).digest()
