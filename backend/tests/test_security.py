import hashlib

from app.security import hash_password, hash_token, new_token, verify_password


def test_hash_round_trips():
    h = hash_password("correct horse")
    assert h.startswith("scrypt$16384$8$1$")
    assert len(h.split("$")) == 6
    assert verify_password("correct horse", h)
    assert not verify_password("wrong horse", h)


def test_same_password_hashes_differently():
    assert hash_password("correct horse") != hash_password("correct horse")


def test_verify_rejects_malformed_hashes():
    for bad in ["", "plain", "scrypt$1$2", "bcrypt$16384$8$1$00$00", "scrypt$x$8$1$00$00", "scrypt$16384$8$1$zz$zz"]:
        assert verify_password("x", bad) is False


def test_tokens_are_unique_and_hash_is_sha256_hex():
    a, b = new_token(), new_token()
    assert a != b
    assert len(a) >= 43
    assert hash_token(a) == hashlib.sha256(a.encode()).hexdigest()
