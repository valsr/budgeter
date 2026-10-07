from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import server_db
from app.config import settings
from app.errors import AuthError, ConflictError, NotFoundError, ValidationError
from app.security import hash_token, verify_password
from app.server_models import UserSession, utcnow
from app.services import users


@pytest.fixture()
def sdb(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    monkeypatch.setattr(settings, "data_dir", None)
    server_db.reset()
    with Session(server_db.get_engine()) as db:
        yield db
    server_db.reset()


def test_create_user_normalizes_and_hashes(sdb):
    u = users.create_user(sdb, "  Alice ", "password1")
    assert u.username == "alice"
    assert u.is_admin and not u.is_disabled
    assert verify_password("password1", u.password_hash)


@pytest.mark.parametrize("name", ["ab", "a" * 33, "has space", "ünï", "", "semi;colon"])
def test_rejects_bad_usernames(sdb, name):
    with pytest.raises(ValidationError, match="Username"):
        users.create_user(sdb, name, "password1")


@pytest.mark.parametrize("pw", ["short", "x" * 257])
def test_rejects_bad_passwords(sdb, pw):
    with pytest.raises(ValidationError, match="Password"):
        users.create_user(sdb, "alice", pw)


def test_accepts_boundary_lengths(sdb):
    users.create_user(sdb, "a.b", "x" * 8)
    users.create_user(sdb, "a" * 32, "x" * 256)


def test_duplicate_username_is_a_conflict_whatever_the_case(sdb):
    users.create_user(sdb, "alice", "password1")
    with pytest.raises(ConflictError, match="already taken"):
        users.create_user(sdb, "ALICE", "password2")


def test_unique_constraint_race_is_a_conflict_not_a_crash(sdb, monkeypatch):
    users.create_user(sdb, "alice", "password1")
    # Simulate a second registration that passed the existence check before
    # the first one committed: only the unique constraint can catch it.
    monkeypatch.setattr(users, "_find_by_username", lambda db, name: None)
    with pytest.raises(ConflictError, match="already taken"):
        users.create_user(sdb, "alice", "password2")
    monkeypatch.undo()
    assert len(users.list_users(sdb)) == 1


def test_authenticate_accepts_case_and_whitespace_variants(sdb):
    users.create_user(sdb, "alice", "password1")
    assert users.authenticate(sdb, "  Alice ", "password1").username == "alice"


def test_authenticate_failures_share_one_message(sdb):
    alice = users.create_user(sdb, "alice", "password1")
    bob = users.create_user(sdb, "bob", "password1")
    users.update_user(sdb, bob.id, is_disabled=True)
    for name, pw in [("nobody", "password1"), ("alice", "wrong-password"), ("bob", "password1"), ("", "")]:
        with pytest.raises(AuthError) as e:
            users.authenticate(sdb, name, pw)
        assert str(e.value) == "Invalid username or password"
    assert alice.id != bob.id


def test_registration_open_until_closed_and_always_open_with_no_users(sdb):
    assert users.get_settings(sdb).registration_open is True
    users.set_registration_open(sdb, False)
    assert users.has_users(sdb) is False
    users.register(sdb, "first", "password1")  # no users yet: always allowed
    with pytest.raises(AuthError, match="Registration is closed"):
        users.register(sdb, "second", "password1")
    users.set_registration_open(sdb, True)
    users.register(sdb, "second", "password1")


def test_session_resolves_slides_and_expires(sdb):
    u = users.create_user(sdb, "alice", "password1")
    t0 = utcnow()
    token = users.create_session(sdb, u)
    row = sdb.execute(select(UserSession)).scalar_one()
    assert row.token_hash == hash_token(token) and token not in row.token_hash
    assert abs(row.expires_at - (t0 + timedelta(days=30))) < timedelta(seconds=5)

    # Within the first day nothing is rewritten...
    assert users.resolve_session(sdb, token, now=t0 + timedelta(hours=1)).id == u.id
    assert abs(row.expires_at - (t0 + timedelta(days=30))) < timedelta(seconds=5)
    # ...after that the expiry slides forward from the time of use.
    assert users.resolve_session(sdb, token, now=t0 + timedelta(days=2)).id == u.id
    assert row.expires_at >= t0 + timedelta(days=32) - timedelta(seconds=5)

    assert users.resolve_session(sdb, token, now=t0 + timedelta(days=33)) is None
    assert users.resolve_session(sdb, "no-such-token") is None
    assert users.resolve_session(sdb, "") is None


def test_logout_deletes_only_that_session(sdb):
    u = users.create_user(sdb, "alice", "password1")
    a, b = users.create_session(sdb, u), users.create_session(sdb, u)
    users.delete_session(sdb, a)
    assert users.resolve_session(sdb, a) is None
    assert users.resolve_session(sdb, b).id == u.id


def test_purge_expired_sessions(sdb):
    u = users.create_user(sdb, "alice", "password1")
    live, dead = users.create_session(sdb, u), users.create_session(sdb, u)
    row = sdb.execute(select(UserSession).where(UserSession.token_hash == hash_token(dead))).scalar_one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    sdb.commit()
    users.purge_expired_sessions(sdb)
    assert [s.token_hash for s in sdb.execute(select(UserSession)).scalars()] == [hash_token(live)]


def test_disabling_ends_sessions_and_blocks_the_api_key(sdb):
    users.create_user(sdb, "admin", "password1")
    bob = users.create_user(sdb, "bob", "password1")
    token = users.create_session(sdb, bob)
    key = users.regenerate_api_key(sdb, bob)
    assert users.resolve_api_key(sdb, key).id == bob.id

    users.update_user(sdb, bob.id, is_disabled=True)
    assert users.resolve_session(sdb, token) is None
    assert users.resolve_api_key(sdb, key) is None

    users.update_user(sdb, bob.id, is_disabled=False)
    assert users.resolve_api_key(sdb, key).id == bob.id
    assert users.resolve_session(sdb, token) is None  # sessions were deleted, not suspended


def test_regenerated_api_key_replaces_the_old_one(sdb):
    u = users.create_user(sdb, "alice", "password1")
    assert users.resolve_api_key(sdb, "") is None
    first = users.regenerate_api_key(sdb, u)
    assert u.api_key_hash == hash_token(first)
    second = users.regenerate_api_key(sdb, u)
    assert first != second
    assert users.resolve_api_key(sdb, first) is None
    assert users.resolve_api_key(sdb, second).id == u.id


def test_change_password_needs_current_and_ends_other_sessions(sdb):
    u = users.create_user(sdb, "alice", "password1")
    mine, other = users.create_session(sdb, u), users.create_session(sdb, u)
    with pytest.raises(AuthError):
        users.change_password(sdb, u, "wrong-password", "password2", keep_token=mine)
    with pytest.raises(ValidationError):
        users.change_password(sdb, u, "password1", "short", keep_token=mine)
    users.change_password(sdb, u, "password1", "password2", keep_token=mine)
    assert users.authenticate(sdb, "alice", "password2").id == u.id
    assert users.resolve_session(sdb, mine).id == u.id
    assert users.resolve_session(sdb, other) is None


def test_admin_password_reset_ends_that_users_sessions(sdb):
    users.create_user(sdb, "admin", "password1")
    bob = users.create_user(sdb, "bob", "password1")
    token = users.create_session(sdb, bob)
    users.update_user(sdb, bob.id, password="new-password")
    assert users.resolve_session(sdb, token) is None
    assert users.authenticate(sdb, "bob", "new-password").id == bob.id


def test_last_active_admin_is_protected(sdb):
    a = users.create_user(sdb, "a-admin", "password1")
    b = users.create_user(sdb, "b-user", "password1")
    users.update_user(sdb, b.id, is_admin=False)
    for change in (dict(is_admin=False), dict(is_disabled=True)):
        with pytest.raises(ConflictError, match="last active admin"):
            users.update_user(sdb, a.id, **change)
    with pytest.raises(ConflictError, match="last active admin"):
        users.delete_user(sdb, a.id)
    assert users.get_user(sdb, a.id).is_admin and not users.get_user(sdb, a.id).is_disabled

    users.update_user(sdb, b.id, is_admin=True)
    users.delete_user(sdb, a.id)
    assert [u.username for u in users.list_users(sdb)] == ["b-user"]


def test_a_disabled_admin_does_not_count_as_active(sdb):
    a = users.create_user(sdb, "a-admin", "password1")
    b = users.create_user(sdb, "b-admin", "password1")
    users.update_user(sdb, b.id, is_disabled=True)
    with pytest.raises(ConflictError):
        users.update_user(sdb, a.id, is_admin=False)
    # Removing the disabled one is fine: an active admin remains.
    users.delete_user(sdb, b.id)


def test_delete_user_removes_their_sessions(sdb):
    users.create_user(sdb, "admin", "password1")
    bob = users.create_user(sdb, "bob", "password1")
    users.create_session(sdb, bob)
    users.delete_user(sdb, bob.id)
    assert sdb.execute(select(UserSession)).scalars().all() == []


def test_unknown_user_is_not_found(sdb):
    for call in (lambda: users.get_user(sdb, 99), lambda: users.update_user(sdb, 99, is_admin=True), lambda: users.delete_user(sdb, 99)):
        with pytest.raises(NotFoundError):
            call()
