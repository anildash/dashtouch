"""Wire protocol v1 — implements docs/protocol.md, nothing else."""
from __future__ import annotations

import hashlib
import hmac as hmac_mod
import os
import re
from collections import namedtuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROTO_VERSION = 1
EvResult = namedtuple("EvResult", "nonce counter slot score")

_EV_RE = re.compile(
    r"^EV ([0-9a-f]{32}) (\d{1,10}) (\d{1,3}) (\d{1,5}) ([0-9a-f]{64})$")


class ProtocolError(Exception):
    pass


def _hmac256(key: bytes, msg: bytes) -> bytes:
    return hmac_mod.new(key, msg, hashlib.sha256).digest()


def verify_ev(key: bytes, line: str, last_counter: int) -> EvResult:
    m = _EV_RE.match(line.strip())
    if not m:
        raise ProtocolError(f"malformed EV line: {line!r}")
    nonce_hex, counter_s, slot_s, score_s, mac_hex = m.groups()
    canonical = f"EV {nonce_hex} {counter_s} {slot_s} {score_s}".encode()
    expect = _hmac256(key, canonical)
    if not hmac_mod.compare_digest(expect.hex(), mac_hex):
        raise ProtocolError("bad HMAC")
    counter = int(counter_s)
    if counter <= last_counter:
        raise ProtocolError(f"replayed counter {counter} <= {last_counter}")
    return EvResult(bytes.fromhex(nonce_hex), counter, int(slot_s), int(score_s))


def derive_response_key(key: bytes, nonce: bytes) -> bytes:
    return _hmac256(key, b"DTPW1" + nonce)


def encrypt_password(key: bytes, nonce: bytes, password: str,
                     _gcm_nonce: bytes | None = None) -> str:
    gcm_nonce = _gcm_nonce if _gcm_nonce is not None else os.urandom(12)
    ct = AESGCM(derive_response_key(key, nonce)).encrypt(
        gcm_nonce, password.encode(), None)
    return f"PW {gcm_nonce.hex()} {ct.hex()}"
