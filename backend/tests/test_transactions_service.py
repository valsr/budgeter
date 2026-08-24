import datetime as dt

import pytest

from app.errors import NotFoundError, ValidationError
from app.models.account import AccountType
from app.models.transaction import TransactionType
from app.services import accounts as accounts_svc
from app.services import categories as categories_svc
from app.services import transactions as txn_svc


@pytest.fixture()
def account(db_session):
    return accounts_svc.create_account(
        db_session, name="Main checking", type=AccountType.ASSET, opening_balance=1000
    )


@pytest.fixture()
def other_account(db_session):
    return accounts_svc.create_account(
        db_session, name="Shared credit card", type=AccountType.LIABILITY, opening_balance=-200
    )


@pytest.fixture()
def category(db_session):
    return categories_svc.create_category(db_session, "shared")


def test_create_transaction_single_split(db_session, account, category):
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 5), "Costco", [(category.id, -88.40)]
    )
    assert txn.id is not None
    assert len(txn.splits) == 1
    assert txn.splits[0].category_id == category.id


def test_create_transaction_multi_split(db_session, account, category):
    c2 = categories_svc.create_category(db_session, "household")
    txn = txn_svc.create_transaction(
        db_session,
        account.id,
        dt.date(2026, 1, 5),
        "Costco",
        [(category.id, -60.0), (c2.id, -20.0)],
    )
    assert len(txn.splits) == 2


def test_create_transaction_unknown_account_404(db_session, category):
    with pytest.raises(NotFoundError):
        txn_svc.create_transaction(db_session, 999, dt.date(2026, 1, 1), "x", [(None, -1.0)])


def test_create_transaction_bad_splits_rejected(db_session, account, category):
    with pytest.raises(ValidationError):
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 1), "x", [(category.id, -1.0), (category.id, -2.0)]
        )


def test_update_transaction_details(db_session, account):
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 5), "Costco", [(None, -10.0)]
    )
    updated = txn_svc.update_transaction_details(db_session, txn.id, name="Costco Wholesale")
    assert updated.name == "Costco Wholesale"


def test_update_transaction_details_missing_404(db_session):
    with pytest.raises(NotFoundError):
        txn_svc.update_transaction_details(db_session, 999, name="x")


def test_update_splits_preserves_total(db_session, account, category):
    c2 = categories_svc.create_category(db_session, "household")
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 5), "Costco", [(category.id, -88.40)]
    )
    updated = txn_svc.update_transaction_splits(
        db_session, txn.id, [(category.id, -60.0), (c2.id, -28.40)]
    )
    assert len(updated.splits) == 2
    assert sum(float(s.amount) for s in updated.splits) == pytest.approx(-88.40)


def test_update_splits_rejects_total_mismatch(db_session, account, category):
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 5), "Costco", [(category.id, -88.40)]
    )
    with pytest.raises(ValidationError):
        txn_svc.update_transaction_splits(db_session, txn.id, [(category.id, -50.0)])


def test_update_splits_on_transfer_rejected(db_session, account, other_account):
    from_txn, _ = txn_svc.create_transfer(
        db_session, account.id, other_account.id, dt.date(2026, 1, 1), "Payment", 300.0
    )
    with pytest.raises(ValidationError):
        txn_svc.update_transaction_splits(db_session, from_txn.id, [(None, -300.0)])


def test_update_splits_missing_transaction_404(db_session):
    with pytest.raises(NotFoundError):
        txn_svc.update_transaction_splits(db_session, 999, [(None, -1.0)])


def test_delete_transaction(db_session, account):
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 5), "Costco", [(None, -10.0)]
    )
    txn_svc.delete_transaction(db_session, txn.id)
    with pytest.raises(NotFoundError):
        txn_svc.get_transaction(db_session, txn.id)


def test_delete_transaction_missing_404(db_session):
    with pytest.raises(NotFoundError):
        txn_svc.delete_transaction(db_session, 999)


def test_delete_transfer_deletes_both_legs(db_session, account, other_account):
    from_txn, to_txn = txn_svc.create_transfer(
        db_session, account.id, other_account.id, dt.date(2026, 1, 1), "Payment", 300.0
    )
    txn_svc.delete_transaction(db_session, from_txn.id)
    with pytest.raises(NotFoundError):
        txn_svc.get_transaction(db_session, to_txn.id)


def test_create_transfer_legs_have_opposite_signed_single_split(db_session, account, other_account):
    from_txn, to_txn = txn_svc.create_transfer(
        db_session, account.id, other_account.id, dt.date(2026, 1, 1), "Payment", 300.0
    )
    assert float(from_txn.splits[0].amount) == -300.0
    assert float(to_txn.splits[0].amount) == 300.0
    assert from_txn.transfer_pair_id == to_txn.id
    assert to_txn.transfer_pair_id == from_txn.id
    assert from_txn.splits[0].category_id is None
    assert to_txn.splits[0].category_id is None


def test_create_transfer_same_account_rejected(db_session, account):
    with pytest.raises(ValidationError):
        txn_svc.create_transfer(db_session, account.id, account.id, dt.date(2026, 1, 1), "x", 10.0)


def test_create_transfer_non_positive_amount_rejected(db_session, account, other_account):
    with pytest.raises(ValidationError):
        txn_svc.create_transfer(
            db_session, account.id, other_account.id, dt.date(2026, 1, 1), "x", 0
        )
    with pytest.raises(ValidationError):
        txn_svc.create_transfer(
            db_session, account.id, other_account.id, dt.date(2026, 1, 1), "x", -5
        )


def test_create_transfer_unknown_account_404(db_session, account):
    with pytest.raises(NotFoundError):
        txn_svc.create_transfer(db_session, account.id, 999, dt.date(2026, 1, 1), "x", 10.0)


def test_get_transaction_missing_404(db_session):
    with pytest.raises(NotFoundError):
        txn_svc.get_transaction(db_session, 999)


def test_count_uncategorized(db_session, account, category):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "a", [(None, -1.0)])
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 2), "b", [(category.id, -2.0)]
    )
    assert txn_svc.count_uncategorized(db_session) == 1


def test_count_uncategorized_excludes_transfers(db_session, account, other_account):
    txn_svc.create_transfer(
        db_session, account.id, other_account.id, dt.date(2026, 1, 1), "Payment", 300.0
    )
    assert txn_svc.count_uncategorized(db_session) == 0


def test_list_transactions_filters_by_account(db_session, account, other_account):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "a", [(None, -1.0)])
    txn_svc.create_transaction(
        db_session, other_account.id, dt.date(2026, 1, 1), "b", [(None, -2.0)]
    )
    items, total = txn_svc.list_transactions(db_session, account_id=account.id)
    assert total == 1
    assert items[0].name == "a"


def test_list_transactions_filters_by_date_range(db_session, account):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "jan", [(None, -1.0)])
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 2, 1), "feb", [(None, -1.0)])
    items, total = txn_svc.list_transactions(
        db_session, date_from=dt.date(2026, 2, 1), date_to=dt.date(2026, 2, 28)
    )
    assert total == 1
    assert items[0].name == "feb"


def test_list_transactions_filters_by_amount_range(db_session, account):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "small", [(None, -5.0)])
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "big", [(None, -50.0)])
    items, total = txn_svc.list_transactions(db_session, amount_min=-10, amount_max=0)
    assert total == 1
    assert items[0].name == "small"


def test_list_transactions_filters_by_name(db_session, account):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "Costco", [(None, -5.0)])
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "Amazon", [(None, -5.0)])
    items, total = txn_svc.list_transactions(db_session, name_contains="cost")
    assert total == 1
    assert items[0].name == "Costco"


def test_list_transactions_category_rollup_includes_children(db_session, account):
    parent = categories_svc.create_category(db_session, "shared")
    child = categories_svc.create_category(db_session, "groceries", parent_id=parent.id)
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "Costco", [(child.id, -5.0)]
    )
    items, total = txn_svc.list_transactions(db_session, category_id=parent.id)
    assert total == 1
    assert items[0].name == "Costco"


def test_list_transactions_category_rollup_includes_deep_descendants(db_session, account):
    shared = categories_svc.create_category(db_session, "shared")
    groceries = categories_svc.create_category(db_session, "groceries", parent_id=shared.id)
    alcohol = categories_svc.create_category(db_session, "alcohol", parent_id=groceries.id)
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "Beer run", [(alcohol.id, -20.0)])

    for filter_category in (shared, groceries, alcohol):
        items, total = txn_svc.list_transactions(db_session, category_id=filter_category.id)
        assert total == 1, f"expected a match filtering by {filter_category.name!r}"
        assert items[0].name == "Beer run"


def test_list_transactions_uncategorized_only(db_session, account, category):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "uncat", [(None, -1.0)])
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 2), "cat", [(category.id, -2.0)])

    items, total = txn_svc.list_transactions(db_session, show_categorized=False)
    assert total == 1
    assert items[0].name == "uncat"


def test_list_transactions_categorized_only_includes_transfers(db_session, account, other_account, category):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "uncat", [(None, -1.0)])
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 2), "cat", [(category.id, -2.0)])
    txn_svc.create_transfer(db_session, account.id, other_account.id, dt.date(2026, 1, 3), "Payment", 10.0)

    items, total = txn_svc.list_transactions(db_session, show_uncategorized=False)
    # transfers count as categorized (wireframe: isCat includes status==='transfer')
    assert total == 3  # "cat" + the transfer's two legs
    assert all(t.name != "uncat" for t in items)


def test_list_transactions_partially_categorized_split_counts_as_uncategorized(db_session, account, category):
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "partial", [(category.id, -5.0), (None, -5.0)]
    )
    items, total = txn_svc.list_transactions(db_session, show_categorized=False)
    assert total == 1
    assert items[0].name == "partial"


def test_list_transactions_neither_toggle_returns_empty(db_session, account):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "x", [(None, -1.0)])
    items, total = txn_svc.list_transactions(
        db_session, show_categorized=False, show_uncategorized=False
    )
    assert total == 0
    assert items == []


def test_list_transactions_pagination(db_session, account):
    for i in range(5):
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, i + 1), f"t{i}", [(None, -1.0)]
        )
    items, total = txn_svc.list_transactions(db_session, page=1, page_size=2)
    assert total == 5
    assert len(items) == 2
    # newest date first
    assert items[0].name == "t4"

    items_p2, _ = txn_svc.list_transactions(db_session, page=2, page_size=2)
    assert len(items_p2) == 2
    assert items_p2[0].name == "t2"


def test_delete_transfer_logs_both_legs_under_one_group(db_session, account, other_account):
    from app.models.change import ChangeOperation, TransactionChange

    from_txn, to_txn = txn_svc.create_transfer(
        db_session, account.id, other_account.id, dt.date(2026, 1, 1), "Payment", 300.0
    )
    txn_svc.delete_transaction(db_session, from_txn.id)

    rows = (
        db_session.query(TransactionChange)
        .filter(TransactionChange.operation == ChangeOperation.DELETE)
        .all()
    )
    assert {r.entity_id for r in rows} == {from_txn.id, to_txn.id}
    assert len({r.group_id for r in rows}) == 1


def test_update_splits_logs_full_before_after_snapshot(db_session, account, category):
    from app.models.change import ChangeOperation, TransactionChange

    txn = txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "Store", [(None, -50.0)])
    other_category = categories_svc.create_category(db_session, "other")
    txn_svc.update_transaction_splits(db_session, txn.id, [(other_category.id, -50.0)])

    row = (
        db_session.query(TransactionChange)
        .filter(TransactionChange.entity_id == txn.id, TransactionChange.operation == ChangeOperation.UPDATE)
        .one()
    )
    assert row.before["splits"][0]["category_id"] is None
    assert row.after["splits"][0]["category_id"] == other_category.id


# --- linking existing transactions as a transfer -----------------------


@pytest.fixture()
def leg_pair(db_session, account, other_account):
    """The shape the import flow produces: each account's own statement
    carried one side of the same movement, a day apart."""
    out = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 19), "UU500 TFR-TO 6000884", [(None, -6594.96)]
    )
    into = txn_svc.create_transaction(
        db_session, other_account.id, dt.date(2026, 1, 20), "UU500 TFR-FR 6263382", [(None, 6594.96)]
    )
    return out, into


def test_find_transfer_candidates_matches_opposite_leg(db_session, leg_pair):
    out, into = leg_pair
    candidates = txn_svc.find_transfer_candidates(db_session, out.id)
    assert [c.id for c in candidates] == [into.id]


def test_find_transfer_candidates_orders_by_date_proximity(db_session, account, other_account, leg_pair):
    out, into = leg_pair
    same_day = txn_svc.create_transaction(
        db_session, other_account.id, dt.date(2026, 1, 19), "Other refund", [(None, 6594.96)]
    )
    candidates = txn_svc.find_transfer_candidates(db_session, out.id)
    assert [c.id for c in candidates] == [same_day.id, into.id]


def test_find_transfer_candidates_excludes_same_account(db_session, account, leg_pair):
    out, _ = leg_pair
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 19), "Same account", [(None, 6594.96)]
    )
    candidates = txn_svc.find_transfer_candidates(db_session, out.id)
    assert all(c.account_id != out.account_id for c in candidates)


def test_find_transfer_candidates_excludes_out_of_window(db_session, other_account, leg_pair):
    out, into = leg_pair
    far = txn_svc.create_transaction(
        db_session, other_account.id, dt.date(2026, 2, 19), "Much later", [(None, 6594.96)]
    )
    assert far.id not in {c.id for c in txn_svc.find_transfer_candidates(db_session, out.id)}


def test_find_transfer_candidates_excludes_split_transactions(db_session, other_account, category, leg_pair):
    out, into = leg_pair
    c2 = categories_svc.create_category(db_session, "gifts")
    split_txn = txn_svc.create_transaction(
        db_session,
        other_account.id,
        dt.date(2026, 1, 19),
        "Split deposit",
        [(category.id, 6000.0), (c2.id, 594.96)],
    )
    assert split_txn.id not in {c.id for c in txn_svc.find_transfer_candidates(db_session, out.id)}


def test_find_transfer_candidates_rejects_transfer_source(db_session, leg_pair):
    out, into = leg_pair
    txn_svc.link_as_transfer(db_session, out.id, into.id)
    with pytest.raises(ValidationError):
        txn_svc.find_transfer_candidates(db_session, out.id)


def test_link_as_transfer_pairs_both_legs(db_session, leg_pair):
    out, into = leg_pair
    a, b = txn_svc.link_as_transfer(db_session, out.id, into.id)
    assert a.type == TransactionType.TRANSFER
    assert b.type == TransactionType.TRANSFER
    assert a.transfer_pair_id == b.id
    assert b.transfer_pair_id == a.id


def test_link_as_transfer_clears_category_and_suggestion(db_session, account, other_account, category):
    out = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 19), "TFR out", [(category.id, -50.0)]
    )
    into = txn_svc.create_transaction(
        db_session, other_account.id, dt.date(2026, 1, 19), "TFR in", [(None, 50.0)]
    )
    into.splits[0].suggested_category_id = category.id
    db_session.commit()

    a, b = txn_svc.link_as_transfer(db_session, out.id, into.id)
    assert a.splits[0].category_id is None
    assert b.splits[0].suggested_category_id is None


def test_link_as_transfer_rejects_mismatched_amounts(db_session, account, other_account):
    out = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 19), "out", [(None, -50.0)]
    )
    into = txn_svc.create_transaction(
        db_session, other_account.id, dt.date(2026, 1, 19), "in", [(None, 49.0)]
    )
    with pytest.raises(ValidationError):
        txn_svc.link_as_transfer(db_session, out.id, into.id)


def test_link_as_transfer_rejects_same_account(db_session, account):
    out = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 19), "out", [(None, -50.0)]
    )
    into = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 19), "in", [(None, 50.0)]
    )
    with pytest.raises(ValidationError):
        txn_svc.link_as_transfer(db_session, out.id, into.id)


def test_link_as_transfer_rejects_self(db_session, leg_pair):
    out, _ = leg_pair
    with pytest.raises(ValidationError):
        txn_svc.link_as_transfer(db_session, out.id, out.id)


def test_link_as_transfer_rejects_already_linked(db_session, other_account, leg_pair):
    out, into = leg_pair
    txn_svc.link_as_transfer(db_session, out.id, into.id)
    third = txn_svc.create_transaction(
        db_session, other_account.id, dt.date(2026, 1, 19), "third", [(None, 6594.96)]
    )
    with pytest.raises(ValidationError):
        txn_svc.link_as_transfer(db_session, out.id, third.id)


def test_link_as_transfer_rejects_split_leg(db_session, account, other_account, category):
    c2 = categories_svc.create_category(db_session, "gifts")
    out = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 19), "out", [(category.id, -30.0), (c2.id, -20.0)]
    )
    into = txn_svc.create_transaction(
        db_session, other_account.id, dt.date(2026, 1, 19), "in", [(None, 50.0)]
    )
    with pytest.raises(ValidationError):
        txn_svc.link_as_transfer(db_session, out.id, into.id)


def test_linked_transfer_leaves_uncategorized_count(db_session, leg_pair):
    out, into = leg_pair
    assert txn_svc.count_uncategorized(db_session) == 2
    txn_svc.link_as_transfer(db_session, out.id, into.id)
    assert txn_svc.count_uncategorized(db_session) == 0


def test_unlink_transfer_restores_both_legs(db_session, leg_pair):
    out, into = leg_pair
    txn_svc.link_as_transfer(db_session, out.id, into.id)
    legs = txn_svc.unlink_transfer(db_session, out.id)
    assert {leg.id for leg in legs} == {out.id, into.id}
    assert all(leg.type == TransactionType.NORMAL for leg in legs)
    assert all(leg.transfer_pair_id is None for leg in legs)


def test_unlink_transfer_rejects_normal_transaction(db_session, leg_pair):
    out, _ = leg_pair
    with pytest.raises(ValidationError):
        txn_svc.unlink_transfer(db_session, out.id)


def test_unlink_transfer_handles_orphan_leg(db_session, account, leg_pair):
    """A leg marked as a transfer with no pair — the shape an import leaves
    when only one account's statement was loaded."""
    out, _ = leg_pair
    out.type = TransactionType.TRANSFER
    db_session.commit()
    legs = txn_svc.unlink_transfer(db_session, out.id)
    assert [leg.id for leg in legs] == [out.id]
    assert legs[0].type == TransactionType.NORMAL
