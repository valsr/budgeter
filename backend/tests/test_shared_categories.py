from decimal import Decimal

import pytest

from app import shared_books
from app.errors import NotFoundError, ValidationError
from app.services import shared_categories as sc


@pytest.fixture()
def sh(server_session):
    with shared_books.session_for(1) as s:
        yield s


def test_create_and_nest(sh):
    a = sc.create_category(sh, "Home", None, False)
    b = sc.create_category(sh, "Rent", a.id, False)
    assert b.parent_id == a.id
    assert [c.name for c in sc.list_categories(sh)] == ["Home", "Rent"]
    with pytest.raises(ValidationError):
        sc.create_category(sh, "X", 999, False)


def test_update_category_rejects_cycle(sh):
    a = sc.create_category(sh, "A", None, False)
    b = sc.create_category(sh, "B", a.id, False)
    c = sc.create_category(sh, "C", b.id, False)
    with pytest.raises(ValidationError, match="can't be moved under itself"):
        sc.update_category(sh, a.id, parent_id=c.id)
    with pytest.raises(ValidationError):
        sc.update_category(sh, a.id, parent_id=a.id)
    assert sc.update_category(sh, c.id, parent_id=None).parent_id is None
    with pytest.raises(NotFoundError):
        sc.update_category(sh, 999, name="x")


def test_delete_with_children_rejected(sh):
    a = sc.create_category(sh, "A", None, False)
    b = sc.create_category(sh, "B", a.id, False)
    with pytest.raises(ValidationError, match="Delete or move its subcategories first"):
        sc.delete_category(sh, a.id)
    sc.delete_category(sh, b.id)
    sc.delete_category(sh, a.id)
    assert sc.list_categories(sh) == []
    with pytest.raises(NotFoundError):
        sc.delete_category(sh, a.id)


def test_archive_and_unarchive(sh):
    a = sc.create_category(sh, "A", None, False)
    assert sc.update_category(sh, a.id, archived=True).archived_at is not None
    assert sc.update_category(sh, a.id, archived=False).archived_at is None


def test_set_amounts_upserts_and_null_deletes(sh):
    a = sc.create_category(sh, "A", None, False)
    sc.set_amounts(sh, 2026, [(a.id, 1, Decimal("10")), (a.id, 2, Decimal("20"))])
    sc.set_amounts(sh, 2026, [(a.id, 1, Decimal("15")), (a.id, 2, None)])
    rows = sc.get_amounts(sh, 2026)
    assert [(r.month, Decimal(str(r.amount))) for r in rows] == [(1, Decimal("15"))]
    assert sc.get_amounts(sh, 2025) == []


def test_set_amounts_rejects_bad_month(sh):
    a = sc.create_category(sh, "A", None, False)
    with pytest.raises(ValidationError):
        sc.set_amounts(sh, 2026, [(a.id, 13, Decimal("1"))])
    with pytest.raises(ValidationError):
        sc.set_amounts(sh, 2026, [(999, 1, Decimal("1"))])
