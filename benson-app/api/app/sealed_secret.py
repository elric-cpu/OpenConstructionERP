import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def seal_secret(value: str, key: bytes, *, context: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode(), context.encode())
    return json.dumps(
        {
            "nonce": base64.urlsafe_b64encode(nonce).decode(),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode(),
        },
        sort_keys=True,
    )


def open_secret(value: str, key: bytes, *, context: str) -> str:
    payload = json.loads(value)
    nonce = base64.urlsafe_b64decode(payload["nonce"])
    ciphertext = base64.urlsafe_b64decode(payload["ciphertext"])
    return AESGCM(key).decrypt(nonce, ciphertext, context.encode()).decode()
