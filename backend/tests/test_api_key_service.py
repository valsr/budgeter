from app.services import api_key as api_key_svc


def test_get_current_key_falls_back_to_env_default_when_no_row(db_session):
    assert api_key_svc.get_current_key(db_session) == "test-api-key"


def test_regenerate_creates_row_and_returns_new_key(db_session):
    new_key = api_key_svc.regenerate_key(db_session)
    assert new_key != "test-api-key"
    assert api_key_svc.get_current_key(db_session) == new_key


def test_regenerate_twice_replaces_previous_key(db_session):
    first = api_key_svc.regenerate_key(db_session)
    second = api_key_svc.regenerate_key(db_session)
    assert first != second
    assert api_key_svc.get_current_key(db_session) == second
