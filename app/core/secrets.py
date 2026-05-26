import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


def _get_secret_key() -> bytes:
    path = get_settings().secret_key_file
    if path.exists():
        return base64.b64decode(path.read_bytes().strip())
    key = os.urandom(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64encode(key))
    path.chmod(0o600)
    return key


def ensure_secret_key_configured() -> None:
    _get_secret_key()


def encrypt_secret(value: str) -> str:
    key = _get_secret_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), None)
    return base64.b64encode(nonce).decode("ascii") + ":" + base64.b64encode(ciphertext).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        nonce_b64, ciphertext_b64 = value.split(":", 1)
        key = _get_secret_key()
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(base64.b64decode(nonce_b64), base64.b64decode(ciphertext_b64), None)
        return plaintext.decode("utf-8")
    except (ValueError, binascii.Error, InvalidTag, UnicodeDecodeError):
        return ""
