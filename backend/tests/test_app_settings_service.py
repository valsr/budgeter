import pytest

from app.errors import ValidationError
from app.services import app_settings as svc


def test_default_retention_when_no_row_exists(db_session):
    assert svc.get_retention_days(db_session) == svc.DEFAULT_RETENTION_DAYS


def test_set_and_get_retention(db_session):
    assert svc.set_retention_days(db_session, 30) == 30
    assert svc.get_retention_days(db_session) == 30


def test_set_retention_upserts_a_single_row(db_session):
    svc.set_retention_days(db_session, 30)
    svc.set_retention_days(db_session, 60)
    assert svc.get_retention_days(db_session) == 60

    from app.models.change import AppSettings

    assert db_session.query(AppSettings).count() == 1


@pytest.mark.parametrize("days", [0, -1, 3651])
def test_set_retention_rejects_out_of_range(db_session, days):
    with pytest.raises(ValidationError):
        svc.set_retention_days(db_session, days)
