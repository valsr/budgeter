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


def test_supports_arbitrary_depth(db_session):
    shared = svc.create_category(db_session, "shared")
    groceries = svc.create_category(db_session, "groceries", parent_id=shared.id)
    alcohol = svc.create_category(db_session, "alcohol", parent_id=groceries.id)
    craft_beer = svc.create_category(db_session, "craft beer", parent_id=alcohol.id)
    assert alcohol.parent_id == groceries.id
    assert craft_beer.parent_id == alcohol.id


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


def test_create_defaults_to_not_income(db_session):
    cat = svc.create_category(db_session, "shared")
    assert cat.is_income is False


def test_create_can_be_marked_income(db_session):
    cat = svc.create_category(db_session, "salary", is_income=True)
    assert cat.is_income is True


def test_update_income_flag(db_session):
    cat = svc.create_category(db_session, "salary")
    updated = svc.update_category(db_session, cat.id, is_income=True)
    assert updated.is_income is True


def test_update_omitting_income_flag_leaves_it_unchanged(db_session):
    cat = svc.create_category(db_session, "salary", is_income=True)
    updated = svc.update_category(db_session, cat.id, name="bonus")
    assert updated.is_income is True


def test_update_cannot_self_parent(db_session):
    cat = svc.create_category(db_session, "shared")
    with pytest.raises(ValidationError):
        svc.update_category(db_session, cat.id, parent_id=cat.id)


def test_update_cannot_become_child_of_own_child(db_session):
    parent = svc.create_category(db_session, "shared")
    child = svc.create_category(db_session, "groceries", parent_id=parent.id)
    with pytest.raises(ValidationError):
        svc.update_category(db_session, parent.id, parent_id=child.id)


def test_update_cannot_become_child_of_deeper_descendant(db_session):
    shared = svc.create_category(db_session, "shared")
    groceries = svc.create_category(db_session, "groceries", parent_id=shared.id)
    alcohol = svc.create_category(db_session, "alcohol", parent_id=groceries.id)
    with pytest.raises(ValidationError):
        svc.update_category(db_session, shared.id, parent_id=alcohol.id)


def test_update_can_reparent_to_unrelated_deep_category(db_session):
    shared = svc.create_category(db_session, "shared")
    groceries = svc.create_category(db_session, "groceries", parent_id=shared.id)
    personal = svc.create_category(db_session, "personal")
    moved = svc.update_category(db_session, groceries.id, parent_id=personal.id)
    assert moved.parent_id == personal.id


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


def test_archive_cascades_through_the_whole_subtree(db_session):
    shared = svc.create_category(db_session, "shared")
    groceries = svc.create_category(db_session, "groceries", parent_id=shared.id)
    alcohol = svc.create_category(db_session, "alcohol", parent_id=groceries.id)
    craft_beer = svc.create_category(db_session, "craft beer", parent_id=alcohol.id)

    svc.archive_category(db_session, shared.id)

    for cat in (groceries, alcohol, craft_beer):
        db_session.refresh(cat)
        assert cat.archived_at is not None


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


def test_resolve_path_creates_the_full_chain_when_nothing_exists(db_session):
    leaf = svc.resolve_category_path(db_session, "shared:groceries:alcohol")
    assert leaf.name == "alcohol"

    groceries = svc.get_category(db_session, leaf.parent_id)
    assert groceries.name == "groceries"
    shared = svc.get_category(db_session, groceries.parent_id)
    assert shared.name == "shared"
    assert shared.parent_id is None


def test_resolve_path_reuses_existing_categories_case_insensitively(db_session):
    shared = svc.create_category(db_session, "Shared")
    groceries = svc.create_category(db_session, "Groceries", parent_id=shared.id)

    leaf = svc.resolve_category_path(db_session, "shared:groceries:alcohol")

    assert leaf.parent_id == groceries.id
    # no duplicate "shared"/"groceries" categories were created
    assert len(svc.list_categories(db_session)) == 1
    assert len(svc.get_category(db_session, shared.id).children) == 1


def test_resolve_path_trims_whitespace_around_segments(db_session):
    leaf = svc.resolve_category_path(db_session, "  shared : groceries  ")
    assert leaf.name == "groceries"
    assert svc.get_category(db_session, leaf.parent_id).name == "shared"


def test_resolve_path_rejects_empty_segments(db_session):
    for bad in ("", "shared::groceries", ":shared", "shared:"):
        with pytest.raises(ValidationError):
            svc.resolve_category_path(db_session, bad)


def test_resolve_path_ignores_archived_siblings_and_creates_a_fresh_one(db_session):
    shared = svc.create_category(db_session, "shared")
    svc.archive_category(db_session, shared.id)

    leaf = svc.resolve_category_path(db_session, "shared")

    assert leaf.id != shared.id
    assert leaf.archived_at is None


def test_resolve_path_partial_match_creates_only_the_missing_tail(db_session):
    shared = svc.create_category(db_session, "shared")

    leaf = svc.resolve_category_path(db_session, "shared:groceries:alcohol")

    assert leaf.parent_id is not None
    groceries = svc.get_category(db_session, leaf.parent_id)
    assert groceries.parent_id == shared.id
