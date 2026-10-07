import io
import sqlite3
import zipfile

import pytest

from app import books
from app.errors import ValidationError
from app.services import server_backup
from tests.helpers import account_names, make_account


def snapshot(files) -> dict[str, bytes]:
    return {str(p.relative_to(files)): p.read_bytes() for p in sorted(files.rglob("*")) if p.is_file()}


def rezip(archive: bytes, *, drop=(), add=None) -> bytes:
    """Rebuild an archive, dropping and/or adding members."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive)) as src, zipfile.ZipFile(out, "w") as dst:
        for name in src.namelist():
            if name not in drop:
                dst.writestr(name, src.read(name))
        for name, data in (add or {}).items():
            dst.writestr(name, data)
    return out.getvalue()


@pytest.fixture()
def two_users(make_client):
    alice, bob = make_client("alice"), make_client("bob")
    make_account(alice, "Alice checking")
    make_account(bob, "Bob savings")
    return alice, bob


def test_archive_holds_server_db_and_every_users_books(two_users):
    alice, bob = two_users
    archive = server_backup.create_archive()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert set(z.namelist()) == {"server.db", f"books/{alice.user_id}.db", f"books/{bob.user_id}.db"}
        assert z.read("server.db").startswith(b"SQLite format 3\x00")
        assert z.testzip() is None


def test_restore_round_trips_users_and_books_and_drops_extra_books(two_users, make_client, files):
    alice, bob = two_users
    archive = server_backup.create_archive()

    carol = make_client("carol")
    make_account(carol, "Carol cash")
    make_account(alice, "Added later")
    carol_books = books.books_path(carol.user_id)
    assert carol_books.exists()

    server_backup.restore_archive(archive)

    assert not carol_books.exists()
    assert carol.get("/api/auth/me").status_code == 401
    assert make_client().post("/api/auth/login", json={"username": "carol", "password": "password1"}).status_code == 401
    # Sessions travel with the archive: alice and bob were logged in when it was taken.
    assert account_names(alice) == ["Alice checking"]
    assert account_names(bob) == ["Bob savings"]
    assert sorted(p.name for p in files.iterdir()) == ["books", "server.db"]  # no staging leftovers


@pytest.mark.parametrize(
    "name", ["../server.db", "books/../../x.db", "books/abc.db", "notes.txt", "/etc/x.db", "books/1.db/", "books/01.db-wal"]
)
def test_restore_rejects_hostile_or_unexpected_members(two_users, files, name):
    alice, _ = two_users
    good_books = books.books_path(alice.user_id).read_bytes()
    archive = rezip(server_backup.create_archive(), add={name: good_books})
    before = snapshot(files)

    with pytest.raises(ValidationError):
        server_backup.restore_archive(archive)

    assert snapshot(files) == before
    assert not (files.parent / "x.db").exists()


def test_restore_with_one_corrupt_books_member_changes_nothing(two_users, files):
    alice, bob = two_users
    archive = server_backup.create_archive()
    bad = rezip(archive, drop=[f"books/{bob.user_id}.db"], add={f"books/{bob.user_id}.db": b"not a database"})
    make_account(alice, "Added later")
    before = snapshot(files)

    with pytest.raises(ValidationError):
        server_backup.restore_archive(bad)

    assert snapshot(files) == before
    assert account_names(alice) == ["Alice checking", "Added later"]


def test_restore_without_server_db_is_rejected(two_users, files):
    archive = rezip(server_backup.create_archive(), drop=["server.db"])
    before = snapshot(files)
    with pytest.raises(ValidationError, match="server.db"):
        server_backup.restore_archive(archive)
    assert snapshot(files) == before


def test_restore_rejects_a_books_file_posing_as_server_db_and_vice_versa(two_users, files):
    alice, _ = two_users
    archive = server_backup.create_archive()
    books_bytes = books.books_path(alice.user_id).read_bytes()
    server_bytes = (files / "server.db").read_bytes()
    before = snapshot(files)
    for bad in (
        rezip(archive, drop=["server.db"], add={"server.db": books_bytes}),
        rezip(archive, drop=[f"books/{alice.user_id}.db"], add={f"books/{alice.user_id}.db": server_bytes}),
    ):
        with pytest.raises(ValidationError):
            server_backup.restore_archive(bad)
    assert snapshot(files) == before


def test_restore_rejects_books_that_belong_to_no_user_in_the_archive(two_users, files):
    alice, _ = two_users
    orphan = rezip(server_backup.create_archive(), add={"books/999.db": books.books_path(alice.user_id).read_bytes()})
    before = snapshot(files)
    with pytest.raises(ValidationError, match="999"):
        server_backup.restore_archive(orphan)
    assert snapshot(files) == before


def test_restore_rejects_something_that_is_not_a_zip(two_users, files):
    before = snapshot(files)
    with pytest.raises(ValidationError):
        server_backup.restore_archive(b"plainly not a zip archive")
    assert snapshot(files) == before


def test_a_user_in_the_archive_without_a_books_file_gets_empty_books(two_users, files):
    alice, bob = two_users
    archive = rezip(server_backup.create_archive(), drop=[f"books/{bob.user_id}.db"])
    server_backup.restore_archive(archive)
    assert account_names(bob) == []
    assert account_names(alice) == ["Alice checking"]


def test_whole_server_backup_endpoints_are_admin_only(two_users, make_client):
    alice, bob = two_users
    assert alice.patch(f"/api/admin/users/{bob.user_id}", json={"is_admin": False}).status_code == 200

    resp = alice.get("/api/admin/backup")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith('attachment; filename="budgeter-server-backup-')
    assert resp.headers["content-disposition"].endswith('.zip"')
    archive = resp.content

    upload = {"file": ("backup.zip", archive, "application/zip")}
    assert bob.get("/api/admin/backup").status_code == 403
    assert bob.post("/api/admin/backup/restore", files=upload).status_code == 403
    assert make_client().get("/api/admin/backup").status_code == 401

    make_account(alice, "Added later")
    assert alice.post("/api/admin/backup/restore", files=upload).status_code == 204
    assert account_names(alice) == ["Alice checking"]

    resp = alice.post("/api/admin/backup/restore", files={"file": ("backup.zip", b"junk", "application/zip")})
    assert resp.status_code == 422


def _edit_server_db(archive: bytes, tmp_path, sql: str) -> bytes:
    """The archive with `sql` applied to its server.db."""
    path = tmp_path / "edited-server.db"
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        path.write_bytes(z.read("server.db"))
    conn = sqlite3.connect(path)
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return rezip(archive, drop=["server.db"], add={"server.db": path.read_bytes()})


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE users SET is_admin = 0;",
        "UPDATE users SET is_disabled = 1;",
        # One admin, but disabled; the only active user isn't an admin.
        "UPDATE users SET is_disabled = 1 WHERE username = 'alice'; UPDATE users SET is_admin = 0 WHERE username = 'bob';",
    ],
)
def test_restore_rejects_an_archive_with_no_active_admin(two_users, files, tmp_path, sql):
    archive = _edit_server_db(server_backup.create_archive(), tmp_path, sql)
    before = snapshot(files)

    with pytest.raises(ValidationError, match="no active admin"):
        server_backup.restore_archive(archive)

    assert snapshot(files) == before


def test_restore_accepts_an_archive_with_one_active_admin_among_others(two_users, files, tmp_path):
    alice, bob = two_users
    archive = _edit_server_db(
        server_backup.create_archive(), tmp_path, "UPDATE users SET is_admin = 0 WHERE username = 'bob';"
    )
    server_backup.restore_archive(archive)
    assert alice.get("/api/admin/users").status_code == 200
    assert bob.get("/api/admin/users").status_code == 403


def test_restore_accepts_an_archive_from_a_server_nobody_registered_on(two_users, files, tmp_path):
    # No users at all isn't a lock-out: registration is always open then.
    archive = _edit_server_db(
        server_backup.create_archive(), tmp_path, "DELETE FROM sessions; DELETE FROM users;"
    )
    archive = rezip(archive, drop=[n for n in zipfile.ZipFile(io.BytesIO(archive)).namelist() if n != "server.db"])
    server_backup.restore_archive(archive)
    assert sorted(p.name for p in (files / "books").iterdir()) == []
