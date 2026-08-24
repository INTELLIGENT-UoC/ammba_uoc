"""UUID ↔ bytes16 conversion for the on-chain identifiers.

PROVISIONAL: GSY is publishing canonical conversion utilities (upstream PR,
currently deprioritized). Until they land, we use the natural mapping — a UUID
*is* 16 bytes — which is the obvious candidate for their implementation too.
If their convention differs (byte order, hashing), only this module changes.
"""

import uuid

ZERO_BYTES16 = b"\x00" * 16


def uuid_to_bytes16(value: str) -> bytes:
    """Encode a UUID string as the on-chain bytes16 identifier."""
    return uuid.UUID(value).bytes


def bytes16_to_uuid(value: bytes) -> str:
    """Decode an on-chain bytes16 identifier back to a UUID string."""
    if len(value) != 16:
        raise ValueError(f"expected 16 bytes, got {len(value)}")
    return str(uuid.UUID(bytes=value))
