import json
import pathlib

import pytest

from dashtouch_helper import protocol

VECTORS = json.loads(
    (pathlib.Path(__file__).parents[2] / "docs" / "protocol-vectors.json").read_text()
)


def k(name):
    return bytes.fromhex(VECTORS[name])


def test_verify_ev_accepts_vector():
    r = protocol.verify_ev(k("pairing_key"), VECTORS["ev_line"], last_counter=0)
    assert r.nonce == k("nonce")
    assert (r.counter, r.slot, r.score) == (
        VECTORS["counter"], VECTORS["slot"], VECTORS["score"])


def test_verify_ev_rejects_tampered_hmac():
    line = VECTORS["ev_line"][:-1] + ("0" if VECTORS["ev_line"][-1] != "0" else "1")
    with pytest.raises(protocol.ProtocolError):
        protocol.verify_ev(k("pairing_key"), line, last_counter=0)


def test_verify_ev_rejects_replayed_counter():
    with pytest.raises(protocol.ProtocolError):
        protocol.verify_ev(k("pairing_key"), VECTORS["ev_line"],
                           last_counter=VECTORS["counter"])


def test_derive_response_key_matches_vector():
    assert protocol.derive_response_key(k("pairing_key"), k("nonce")) == k("response_key")


def test_pw_line_matches_vector_with_fixed_gcm_nonce():
    line = protocol.encrypt_password(
        k("pairing_key"), k("nonce"), VECTORS["password"],
        _gcm_nonce=k("gcm_nonce"))
    assert line == VECTORS["pw_line"]


def test_pw_roundtrip_decrypts():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    line = protocol.encrypt_password(k("pairing_key"), k("nonce"), "s3cret pw")
    _, gcm_hex, ct_hex = line.split(" ")
    key = protocol.derive_response_key(k("pairing_key"), k("nonce"))
    pt = AESGCM(key).decrypt(bytes.fromhex(gcm_hex), bytes.fromhex(ct_hex), None)
    assert pt.decode() == "s3cret pw"
