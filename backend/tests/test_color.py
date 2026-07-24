import hashlib

from app.services.color import DEFAULT_PALETTE, hash_color


def test_hash_color_is_deterministic():
    assert hash_color(42) == hash_color(42)


def test_hash_color_varies_by_id():
    colors = {hash_color(i) for i in range(20)}
    assert len(colors) > 1


def test_hash_color_matches_sha256_based_formula():
    # Pins down the actual algorithm (sha256 digest mod palette length) rather
    # than a naive `id % len(palette)`, which would make color assignment
    # visibly sequential.
    entity_id = 123
    digest = hashlib.sha256(str(entity_id).encode()).hexdigest()
    expected = DEFAULT_PALETTE[int(digest, 16) % len(DEFAULT_PALETTE)]
    assert hash_color(entity_id) == expected


def test_hash_color_from_palette():
    assert hash_color(7) in DEFAULT_PALETTE


def test_hash_color_accepts_custom_palette():
    palette = ["#111111", "#222222"]
    assert hash_color(5, palette=palette) in palette
