"""Password hashing and opaque-token helpers, standard library only."""

import hashlib
import hmac
import secrets

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=_KEY_BYTES)


def hash_password(password: str) -> str:
    """`scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>` -- the cost parameters
    travel with the hash so they can be raised later without invalidating
    the passwords already stored."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _scrypt(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = _scrypt(password, bytes.fromhex(salt_hex), int(n), int(r), int(p))
    except ValueError:
        # Wrong field count, non-numeric cost, bad hex, or parameters scrypt rejects.
        return False
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    """A session token or API key: 32 random bytes, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """What gets stored for a token. A plain SHA-256 is enough here, unlike
    for passwords: the input is already 256 bits of randomness."""
    return hashlib.sha256(token.encode()).hexdigest()
