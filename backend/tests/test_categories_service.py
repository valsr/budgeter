import pytest

from app.errors import NotFoundError, ValidationError
from app.services import categories as svc


def test_create_top_level_category(db_session):
    cat = svc.create_category(db_session, "shared")
    assert cat.id is not None
    assert cat.parent_id is None
    assert cat.sort_order == 0


def test_create_child_category(db_session):
    parent = svc.create_category(db_session, "shared")
    child = svc.create_category(db_session, "groceries", parent_id=parent.id)
    assert child.parent_id == parent.id
    assert child.sort_order == 0


def test_cannot_nest_more_than_one_level(db_session):
    parent = svc.create_category(db_session, "shared")
    child = svc.create_category(db_session, "groceries", parent_id=parent.id)
    with pytest.raises(ValidationError):
        svc.create_category(db_session, "alcohol", parent_id=child.id)


def test_create_with_missing_parent_raises_not_found(db_session):
    with pytest.raises(NotFoundError):
        svc.create_category(db_session, "x", parent_id=999)


def test_sibling_sort_order_increments(db_session):
    parent = svc.create_category(db_session, "shared")
    c1 = svc.create_category(db_session, "groceries", parent_id=parent.id)
    c2 = svc.create_category(db_session, "utilities", parent_id=parent.id)
    assert c1.sort_order == 0
    assert c2.sort_order == 1


def test_hash_based_color_is_deterministic_per_id(db_session):
    from app.services.color import hash_color

    cat = svc.create_category(db_session, "shared")
    assert hash_color(cat.id) == hash_color(cat.id)


def test_update_name_and_color(db_session):
    cat = svc.create_category(db_session, "shared")
    updated = svc.update_category(db_session, cat.id, name="household", color="#ff0000")
    assert updated.name == "household"
    assert updated.color == "#ff0000"


def test_update_cannot_self_parent(db_session):
    cat = svc.create_category(db_session, "shared")
    with pytest.raises(ValidationError):
        svc.update_category(db_session, cat.id, parent_id=cat.id)


def test_update_cannot_become_child_of_own_child(db_session):
    parent = svc.create_category(db_session, "shared")
    child = svc.create_category(db_session, "groceries", parent_id=parent.id)
    with pytest.raises(ValidationError):
        svc.update_category(db_session, parent.id, parent_id=child.id)


def test_update_reparent_assigns_new_sort_order(db_session):
    p1 = svc.create_category(db_session, "shared")
    p2 = svc.create_category(db_session, "personal")
    svc.create_category(db_session, "dining", parent_id=p2.id)
    child = svc.create_category(db_session, "groceries", parent_id=p1.id)

    moved = svc.update_category(db_session, child.id, parent_id=p2.id)
    assert moved.parent_id == p2.id
    assert moved.sort_order == 1  # after "dining"


def test_update_missing_category_raises_not_found(db_session):
    with pytest.raises(NotFoundError):
        svc.update_category(db_session, 999, name="x")


def test_archive_soft_deletes_and_cascades_to_children(db_session):
    parent = svc.create_category(db_session, "shared")
    child = svc.create_category(db_session, "groceries", parent_id=parent.id)

    archived = svc.archive_category(db_session, parent.id)
    assert archived.archived_at is not None

    db_session.refresh(child)
    assert child.archived_at is not None


def test_archive_missing_category_raises_not_found(db_session):
    with pytest.raises(NotFoundError):
        svc.archive_category(db_session, 999)


def test_list_categories_excludes_archived_by_default(db_session):
    a = svc.create_category(db_session, "shared")
    svc.create_category(db_session, "personal")
    svc.archive_category(db_session, a.id)

    roots = svc.list_categories(db_session)
    assert [c.name for c in roots] == ["personal"]

    all_roots = svc.list_categories(db_session, include_archived=True)
    assert {c.name for c in all_roots} == {"shared", "personal"}


def test_reorder_categories(db_session):
    parent = svc.create_category(db_session, "shared")
    c1 = svc.create_category(db_session, "groceries", parent_id=parent.id)
    c2 = svc.create_category(db_session, "utilities", parent_id=parent.id)
    c3 = svc.create_category(db_session, "household", parent_id=parent.id)

    reordered = svc.reorder_categories(db_session, parent.id, [c3.id, c1.id, c2.id])
    assert [c.name for c in reordered] == ["household", "groceries", "utilities"]
    assert [c.sort_order for c in reordered] == [0, 1, 2]


def test_reorder_rejects_mismatched_id_set(db_session):
    parent = svc.create_category(db_session, "shared")
    c1 = svc.create_category(db_session, "groceries", parent_id=parent.id)
    svc.create_category(db_session, "utilities", parent_id=parent.id)

    with pytest.raises(ValidationError):
        svc.reorder_categories(db_session, parent.id, [c1.id])


def test_reorder_top_level_categories(db_session):
    a = svc.create_category(db_session, "shared")
    b = svc.create_category(db_session, "personal")

    reordered = svc.reorder_categories(db_session, None, [b.id, a.id])
    assert [c.name for c in reordered] == ["personal", "shared"]


def test_get_category_not_found(db_session):
    with pytest.raises(NotFoundError):
        svc.get_category(db_session, 999)
