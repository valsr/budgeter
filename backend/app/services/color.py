import hashlib

# Ported from docs/wireframes.html's c1-c6 palette so backend defaults match the
# frontend's existing visual language.
DEFAULT_PALETTE = [
    "#6f8f6a",  # c1
    "#b3823f",  # c2
    "#8a6aa0",  # c3
    "#4f8a9c",  # c4
    "#b5555a",  # c5
    "#7a7550",  # c6
]


def hash_color(entity_id: int, palette: list[str] = DEFAULT_PALETTE) -> str:
    """Deterministic, non-sequential color pick for a given entity id."""
    digest = hashlib.sha256(str(entity_id).encode()).hexdigest()
    index = int(digest, 16) % len(palette)
    return palette[index]
