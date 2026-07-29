import pytest

from app.errors import NotFoundError, ValidationError
from app.models.account import AccountType
from app.models.import_batch import ReviewItemStatus
from app.services import accounts as accounts_svc
from app.services import imports as imports_svc


@pytest.fixture()
def account(db_session):
    return accounts_svc.create_account(
        db_session, name="Main checking", type=AccountType.ASSET, opening_balance=1000
    )


QIF_BASIC = """!Type:Bank
D07/19/2026
T-88.40
PCostco
^
D07/20/2026
T19.99
PSPOTIFY *19.99
^
"""


def test_import_new_transactions(db_session, account):
    batch, ids = imports_svc.import_qif(db_session, account.id, "test.qif", QIF_BASIC)
    assert batch.row_count == 2
    assert batch.imported_count == 2
    assert batch.skipped_duplicate_count == 0
    assert batch.needs_review_count == 0
    assert len(ids) == 2


def test_import_unknown_account_404(db_session):
    with pytest.raises(NotFoundError):
        imports_svc.import_qif(db_session, 999, "test.qif", QIF_BASIC)


def test_import_logs_one_grouped_entry_per_batch(db_session, account):
    from app.models.change import ChangeOperation, TransactionChange

    batch, ids = imports_svc.import_qif(db_session, account.id, "test.qif", QIF_BASIC)

    rows = db_session.query(TransactionChange).filter(TransactionChange.operation == ChangeOperation.CREATE).all()
    assert {r.entity_id for r in rows} == set(ids)
    assert len({r.group_id for r in rows}) == 1

    primary = next(r for r in rows if r.is_primary)
    assert "Imported 2 transactions from 'test.qif'" == primary.summary


def test_reimport_same_file_dedupes_exactly(db_session, account):
    imports_svc.import_qif(db_session, account.id, "test.qif", QIF_BASIC)
    batch2, ids2 = imports_svc.import_qif(db_session, account.id, "test.qif", QIF_BASIC)
    assert batch2.imported_count == 0
    assert batch2.skipped_duplicate_count == 2
    assert ids2 == []


def test_near_match_goes_to_review_queue(db_session, account):
    imports_svc.import_qif(db_session, account.id, "first.qif", QIF_BASIC)

    near_match_qif = """D07/19/2026
T-88.40
PCOSTCO WHOLESALE #443
^
"""
    batch2, ids2 = imports_svc.import_qif(db_session, account.id, "second.qif", near_match_qif)
    assert batch2.needs_review_count == 1
    assert batch2.imported_count == 0
    assert ids2 == []

    pending = imports_svc.list_review_items(db_session, batch_id=batch2.id)
    assert len(pending) == 1
    assert pending[0].name == "COSTCO WHOLESALE #443"
    assert pending[0].candidate_transaction_id is not None


def test_intra_batch_exact_duplicates_dedupe_against_each_other(db_session, account):
    content = """D07/19/2026
T-88.40
PCostco
^
D07/19/2026
T-88.40
PCostco
^
"""
    batch, ids = imports_svc.import_qif(db_session, account.id, "dupe.qif", content)
    assert batch.imported_count == 1
    assert batch.skipped_duplicate_count == 1
    assert len(ids) == 1


def test_get_import_batch(db_session, account):
    batch, _ = imports_svc.import_qif(db_session, account.id, "test.qif", QIF_BASIC)
    fetched = imports_svc.get_import_batch(db_session, batch.id)
    assert fetched.id == batch.id


def test_get_import_batch_missing_404(db_session):
    with pytest.raises(NotFoundError):
        imports_svc.get_import_batch(db_session, 999)


def test_list_import_batches(db_session, account):
    imports_svc.import_qif(db_session, account.id, "a.qif", QIF_BASIC)
    imports_svc.import_qif(db_session, account.id, "b.qif", "")
    batches = imports_svc.list_import_batches(db_session)
    assert len(batches) == 2


def test_list_review_items_defaults_to_pending_only(db_session, account):
    imports_svc.import_qif(db_session, account.id, "first.qif", QIF_BASIC)
    near_match_qif = "D07/19/2026\nT-88.40\nPCOSTCO WHOLESALE #443\n^\n"
    batch2, _ = imports_svc.import_qif(db_session, account.id, "second.qif", near_match_qif)
    item = imports_svc.list_review_items(db_session, batch_id=batch2.id)[0]

    imports_svc.resolve_review_item(db_session, item.id, "skip")

    assert imports_svc.list_review_items(db_session, batch_id=batch2.id) == []
    assert len(imports_svc.list_review_items(db_session, batch_id=batch2.id, pending_only=False)) == 1


class TestResolveReviewItem:
    @pytest.fixture()
    def pending_item(self, db_session, account):
        imports_svc.import_qif(db_session, account.id, "first.qif", QIF_BASIC)
        near_match_qif = "D07/19/2026\nT-88.40\nPCOSTCO WHOLESALE #443\n^\n"
        batch2, _ = imports_svc.import_qif(db_session, account.id, "second.qif", near_match_qif)
        return imports_svc.list_review_items(db_session, batch_id=batch2.id)[0]

    def test_resolve_as_new_creates_transaction(self, db_session, pending_item):
        from app.services import transactions as txn_svc

        resolved = imports_svc.resolve_review_item(db_session, pending_item.id, "new")
        assert resolved.status == ReviewItemStatus.RESOLVED_NEW

        items, total = txn_svc.list_transactions(db_session)
        assert total == 3  # original Costco + Spotify from QIF_BASIC, plus the newly-resolved one

    def test_resolve_as_merge_overwrites_name_keeps_category(self, db_session, pending_item):
        from app.services import categories as categories_svc
        from app.services import transactions as txn_svc

        category = categories_svc.create_category(db_session, "shared")
        txn_svc.update_transaction_splits(
            db_session, pending_item.candidate_transaction_id, [(category.id, -88.40)]
        )

        resolved = imports_svc.resolve_review_item(db_session, pending_item.id, "merge")
        assert resolved.status == ReviewItemStatus.RESOLVED_MERGED

        candidate = txn_svc.get_transaction(db_session, pending_item.candidate_transaction_id)
        assert candidate.name == "COSTCO WHOLESALE #443"
        assert candidate.splits[0].category_id == category.id  # category preserved

    def test_resolve_as_skip_creates_nothing(self, db_session, pending_item):
        from app.services import transactions as txn_svc

        imports_svc.resolve_review_item(db_session, pending_item.id, "skip")
        _, total = txn_svc.list_transactions(db_session)
        assert total == 2  # only the original Costco + Spotify transactions from QIF_BASIC

    def test_resolve_already_resolved_rejected(self, db_session, pending_item):
        imports_svc.resolve_review_item(db_session, pending_item.id, "skip")
        with pytest.raises(ValidationError):
            imports_svc.resolve_review_item(db_session, pending_item.id, "skip")

    def test_resolve_missing_item_404(self, db_session):
        with pytest.raises(NotFoundError):
            imports_svc.resolve_review_item(db_session, 999, "skip")

    def test_resolve_unknown_action_rejected(self, db_session, pending_item):
        with pytest.raises(ValidationError):
            imports_svc.resolve_review_item(db_session, pending_item.id, "bogus")

    def test_merge_without_candidate_rejected(self, db_session, account):
        import datetime as dt

        from app.models.import_batch import ImportBatch, ReviewQueueItem

        batch = ImportBatch(filename="x.qif", account_id=account.id, row_count=1)
        db_session.add(batch)
        db_session.flush()
        item = ReviewQueueItem(
            import_batch_id=batch.id,
            account_id=account.id,
            date=dt.date(2026, 7, 19),
            amount=-1.0,
            name="orphan",
            candidate_transaction_id=None,
        )
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)

        with pytest.raises(ValidationError):
            imports_svc.resolve_review_item(db_session, item.id, "merge")
