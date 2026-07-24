from app.services.categorization import run_categorization


def test_run_categorization_is_a_noop_placeholder(db_session):
    assert run_categorization(db_session, [1, 2, 3]) is None
