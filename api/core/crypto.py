"""Symmetric encryption for at-rest secrets (user-supplied third-party API keys).

Secrets are Fernet-encrypted with a key derived from Django ``SECRET_KEY``, so the
stored ciphertext is useless without the server secret. Rules:

- Never persist plaintext secrets — store only ``encrypt_secret(...)`` output.
- Never return a decrypted secret to a client — expose masked forms only.
- The server decrypts on demand right before calling the third-party endpoint.

Caveat: if ``SECRET_KEY`` is rotated, existing ciphertext can no longer be decrypted
and users must re-enter their keys. That is an acceptable trade-off for at-rest safety.
"""
import base64
import hashlib
from functools import lru_cache

from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """A process-cached Fernet built from a SECRET_KEY-derived 32-byte key."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string into a urlsafe token. Empty input → ''."""
    if not plaintext:
        return ''
    return _fernet().encrypt(plaintext.encode('utf-8')).decode('ascii')


def decrypt_secret(token: str) -> str:
    """Decrypt a token from :func:`encrypt_secret`. Empty/invalid input → ''."""
    if not token:
        return ''
    try:
        return _fernet().decrypt(token.encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError, TypeError):
        return ''


def mask_secret(plaintext: str) -> str:
    """Return a display-safe mask like ``sk-****9f2a`` (last 4 chars), never the full key."""
    if not plaintext:
        return ''
    tail = plaintext[-4:] if len(plaintext) >= 4 else plaintext
    return f'sk-****{tail}'
