"""
Encryption for stored Google refresh tokens.

A refresh token grants durable read/write access to a real person's calendar and
does not expire on its own. Storage-level encryption (RDS `storage_encrypted`)
protects the disk, but any path that can read the table — a SQL injection, a
leaked read-only credential, a snapshot restored elsewhere — yields usable
tokens. Encrypting the column means the database alone is not enough.

Fernet is AES-128-CBC with an HMAC, from `cryptography`, which is already a
transitive dependency, so this adds no new package.

The key lives in Secrets Manager and is injected as TOKEN_ENCRYPTION_KEY. It is
deliberately a different secret from JWT_SECRET: rotating session signing should
not invalidate every stored calendar authorization.
"""

import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class TokenDecryptionError(RuntimeError):
    """Stored ciphertext could not be decrypted, usually a rotated key."""


@lru_cache(maxsize=1)
def _cipher() -> Fernet:
    # Read lazily rather than at import, so tests and tooling can import this
    # module without the variable set.
    key = os.environ["TOKEN_ENCRYPTION_KEY"]
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt a stored token.

    Deliberately strict: there is no fallback to treating unreadable values as
    plaintext. No database with plaintext tokens exists, so a decrypt failure
    means a rotated or wrong key, and silently accepting the raw column value
    would turn a key problem into an undetected downgrade.
    """
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        # No ciphertext or key material in the log.
        logger.error("auth.token_decrypt_failed")
        raise TokenDecryptionError(
            "Stored Google credentials could not be decrypted"
        ) from e


def generate_key() -> str:
    """A new Fernet key, for local development and key rotation."""
    return Fernet.generate_key().decode()
