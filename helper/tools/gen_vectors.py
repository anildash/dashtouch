"""Regenerate docs/protocol-vectors.json. Deterministic by construction."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from dashtouch_helper import protocol  # noqa: E402

KEY = bytes(range(32))                     # 000102...1f
NONCE = bytes(range(0xA0, 0xB0))           # a0a1...af
GCM_NONCE = bytes(range(0xC0, 0xCC))       # c0c1...cb
COUNTER, SLOT, SCORE = 7, 3, 142
PASSWORD = "hunter2"

canonical = f"EV {NONCE.hex()} {COUNTER} {SLOT} {SCORE}"
mac = protocol._hmac256(KEY, canonical.encode())
ev_line = f"{canonical} {mac.hex()}"
pw_line = protocol.encrypt_password(KEY, NONCE, PASSWORD, _gcm_nonce=GCM_NONCE)

out = {
    "pairing_key": KEY.hex(), "nonce": NONCE.hex(),
    "counter": COUNTER, "slot": SLOT, "score": SCORE,
    "ev_line": ev_line, "hmac": mac.hex(),
    "response_key": protocol.derive_response_key(KEY, NONCE).hex(),
    "gcm_nonce": GCM_NONCE.hex(), "password": PASSWORD, "pw_line": pw_line,
}
path = pathlib.Path(__file__).parents[2] / "docs" / "protocol-vectors.json"
path.write_text(json.dumps(out, indent=2) + "\n")
print(f"wrote {path}")
