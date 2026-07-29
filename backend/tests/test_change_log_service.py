import datetime as dt

from app.models.account import AccountType
from app.models.change import AccountChange, ChangeOperation
from app.services import accounts as accounts_service
from app.services import app_settings as app_settings_service
from app.services import change_log


def test_record_change_generates_group_id_when_omitted(db_session):
    group_id = change_log.record_change(
        db_session,
        AccountChange,
        1,
        ChangeOperation.CREATE,
        before=None,
        after={"name": "x"},
        summary="Created account 'x'",
    )
    db_session.commit()
    assert group_id

    row = db_session.query(AccountChange).one()
    assert row.group_id == group_id
    assert row.is_primary is True
    assert row.undone_at is None


def test_record_change_shares_group_id_across_calls(db_session):
    group_id = change_log.record_change(
        db_session, AccountChange, 1, ChangeOperation.UPDATE, {}, {}, "a"
    )
    change_log.record_change(
        db_session, AccountChange, 2, ChangeOperation.UPDATE, {}, {}, "b", group_id=group_id, is_primary=False
    )
    db_session.commit()

    rows = db_session.query(AccountChange).order_by(AccountChange.id).all()
    assert [r.group_id for r in rows] == [group_id, group_id]
    assert rows[0].is_primary is True
    assert rows[1].is_primary is False


def test_summarize_account_create_update_delete():
    after = {"name": "Checking", "account_number": None, "type": "asset", "opening_balance": 0, "color": None}
    assert change_log.summarize_account(ChangeOperation.CREATE, None, after) == "Created account 'Checking'"
    assert change_log.summarize_account(ChangeOperation.DELETE, after, None) == "Deleted account 'Checking'"

    renamed = {**after, "name": "Checking 2"}
    assert (
        change_log.summarize_account(ChangeOperation.UPDATE, after, renamed)
        == "Renamed account 'Checking' to 'Checking 2'"
    )


def test_purge_expired_removes_rows_older_than_retention(db_session):
    accounts_service.create_account(db_session, "Checking", AccountType.ASSET)
    row = db_session.query(AccountChange).one()

    # Backdate the row past the default 100-day retention window and purge.
    row.created_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=101)
    db_session.commit()

    change_log.purge_expired(db_session)
    db_session.commit()

    assert db_session.query(AccountChange).count() == 0


def test_purge_expired_keeps_rows_within_retention(db_session):
    accounts_service.create_account(db_session, "Checking", AccountType.ASSET)
    change_log.purge_expired(db_session)
    db_session.commit()
    assert db_session.query(AccountChange).count() == 1


def test_lowering_retention_purges_immediately(db_session):
    accounts_service.create_account(db_session, "Checking", AccountType.ASSET)
    row = db_session.query(AccountChange).one()
    row.created_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)
    db_session.commit()

    app_settings_service.set_retention_days(db_session, 5)

    assert db_session.query(AccountChange).count() == 0
