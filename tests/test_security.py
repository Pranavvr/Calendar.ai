import os

import pytest

from api.rate_limit import SlidingWindowRateLimiter

# Fernet needs a valid key before auth.crypto is exercised. Set it before import
# so the module-level lru_cache picks it up.
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "aXTMOJlYlmCXG5nCCfJ5xkyLxvBihBIisd5vsHUsm-M=")

from auth.crypto import (  # noqa: E402
    TokenDecryptionError,
    decrypt_token,
    encrypt_token,
    generate_key,
)


# --- token encryption -------------------------------------------------------


def test_round_trip():
    token = "1//0gLONG-google-refresh-token-value"
    assert decrypt_token(encrypt_token(token)) == token


def test_ciphertext_does_not_contain_the_plaintext():
    """The whole point: a database read must not yield a usable token."""
    token = "1//0gSECRET"
    assert token not in encrypt_token(token)


def test_encryption_is_non_deterministic():
    """
    Fernet includes a random IV, so the same token encrypts differently each
    time. Without this, equal ciphertexts would reveal that two users share a
    token, and the column would be vulnerable to a dictionary attack.
    """
    token = "1//0gSAME"
    assert encrypt_token(token) != encrypt_token(token)


def test_tampered_ciphertext_is_rejected():
    """Fernet authenticates, so a modified value must not decrypt."""
    ciphertext = encrypt_token("1//0gORIGINAL")
    tampered = ciphertext[:-4] + ("AAAA" if not ciphertext.endswith("AAAA") else "BBBB")
    with pytest.raises(TokenDecryptionError):
        decrypt_token(tampered)


def test_plaintext_is_not_silently_accepted():
    """
    Decryption is deliberately strict. Falling back to treating an unreadable
    value as plaintext would turn a key problem into an undetected downgrade.
    """
    with pytest.raises(TokenDecryptionError):
        decrypt_token("1//0gNOT-ENCRYPTED")


def test_generated_keys_are_usable_and_unique():
    assert generate_key() != generate_key()
    assert len(generate_key()) == 44  # 32 bytes, url-safe base64 with padding


# --- rate limiting ----------------------------------------------------------


def test_allows_up_to_the_limit():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        allowed, _ = limiter.check("user-1")
        assert allowed


def test_blocks_past_the_limit():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        limiter.check("user-1")
    allowed, retry_after = limiter.check("user-1")
    assert not allowed
    assert retry_after > 0


def test_limits_are_per_user():
    """One user exhausting their budget must not affect anyone else."""
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    limiter.check("user-1")
    limiter.check("user-1")
    assert not limiter.check("user-1")[0]
    assert limiter.check("user-2")[0]


def test_window_slides():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.2)
    assert limiter.check("u")[0]
    assert limiter.check("u")[0]
    assert not limiter.check("u")[0]

    import time
    time.sleep(0.25)
    assert limiter.check("u")[0], "window should have slid past the old hits"


def test_retry_after_never_exceeds_the_window():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    limiter.check("u")
    _, retry_after = limiter.check("u")
    assert 0 < retry_after <= 60


def test_reset_clears_state():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    limiter.check("u")
    assert not limiter.check("u")[0]
    limiter.reset("u")
    assert limiter.check("u")[0]


def test_evict_idle_reclaims_memory():
    """Without eviction the key dict grows once per user and never shrinks."""
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=0.1)
    for i in range(50):
        limiter.check(f"user-{i}")
    assert len(limiter._hits) == 50

    import time
    time.sleep(0.15)
    evicted = limiter.evict_idle()
    assert evicted == 50
    assert len(limiter._hits) == 0


def test_active_keys_are_not_evicted():
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
    limiter.check("busy")
    assert limiter.evict_idle() == 0
    assert "busy" in limiter._hits
