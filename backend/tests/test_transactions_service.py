import datetime as dt

import pytest

from app.errors import NotFoundError, ValidationError
from app.models.account import AccountType
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
