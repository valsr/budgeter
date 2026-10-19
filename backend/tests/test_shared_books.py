import shutil

from app import shared_books
from app.shared_models import MemberTally, SharedBudgetAmount, SharedCategory
from tests.helpers import tables


def test_upgrade_creates_shared_schema(tmp_path):
    path = tmp_path / "shared" / "1.db"
    shared_books.upgrade(path)
    assert tables(path) >= {"shared_categories", "shared_budget_amounts", "member_tallies"}
    assert not {"accounts", "users"} & tables(path)


def test_session_for_creates_missing_file(files):
    shared_books.session_for(5).close()
    assert (files / "shared" / "5.db").exists()


def test_deleting_a_shared_category_cascades(files):
    with shared_books.session_for(1) as db:
        cat = SharedCategory(name="Rent")
        db.add(cat)
        db.flush()
        db.add(SharedBudgetAmount(shared_category_id=cat.id, year=2026, month=1, amount=10))
        db.add(MemberTally(user_id=1, shared_category_id=cat.id, year=2026, month=1, amount=5))
        db.commit()
        db.delete(cat)
        db.commit()
        assert db.query(SharedBudgetAmount).count() == 0
        assert db.query(MemberTally).count() == 0


def test_replace_all_keeps_exactly_the_staged_files(files, tmp_path):
    shared_books.create(1)
    shared_books.create(2)
    staged_dir = tmp_path / "staged"
    staged_dir.mkdir()
    shutil.copy(files / "shared" / "2.db", staged_dir / "2.db")
    shutil.copy(files / "shared" / "2.db", staged_dir / "3.db")
    shared_books.replace_all({2: staged_dir / "2.db", 3: staged_dir / "3.db"})
    assert sorted(p.name for p in (files / "shared").glob("*.db")) == ["2.db", "3.db"]


def test_in_memory_mode_uses_create_all():
    try:
        with shared_books.session_for(1) as db:
            db.add(SharedCategory(name="Rent"))
            db.commit()
            assert db.query(SharedCategory).count() == 1
    finally:
        shared_books.dispose_all()


def test_autoincrement_migration_keeps_rows_and_stops_id_reuse(tmp_path):
    import sqlite3

    path = tmp_path / "shared" / "1.db"
    shared_books.upgrade(path, revision="dbf1bbe8aec4")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        INSERT INTO shared_categories (id, name, parent_id, sort_order, is_income) VALUES
            (1, 'Home', NULL, 0, 0), (2, 'Rent', 1, 0, 0), (3, 'Gone', NULL, 1, 0);
        INSERT INTO shared_budget_amounts (shared_category_id, year, month, amount) VALUES (2, 2026, 1, 900);
        INSERT INTO member_tallies (user_id, shared_category_id, year, month, amount) VALUES (7, 2, 2026, 1, -850);
        DELETE FROM shared_categories WHERE id = 3;
        """
    )
    conn.commit()
    conn.close()

    shared_books.upgrade(path)

    conn = sqlite3.connect(path)
    try:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'shared_categories'").fetchone()[0]
        assert "AUTOINCREMENT" in sql
        assert conn.execute("SELECT id, name, parent_id FROM shared_categories ORDER BY id").fetchall() == [
            (1, "Home", None),
            (2, "Rent", 1),
        ]
        assert conn.execute("SELECT shared_category_id, amount FROM shared_budget_amounts").fetchall() == [(2, 900)]
        assert conn.execute("SELECT user_id, shared_category_id, amount FROM member_tallies").fetchall() == [
            (7, 2, -850)
        ]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        # Children still cascade from the recreated table.
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM shared_categories WHERE id = 2")
        assert conn.execute("SELECT count(*) FROM shared_budget_amounts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM member_tallies").fetchone()[0] == 0
        # And from now on a deleted id is never handed out again.
        new_id = conn.execute(
            "INSERT INTO shared_categories (name, sort_order, is_income) VALUES ('New', 0, 0)"
        ).lastrowid
        conn.execute("DELETE FROM shared_categories WHERE id = ?", (new_id,))
        newer_id = conn.execute(
            "INSERT INTO shared_categories (name, sort_order, is_income) VALUES ('Newer', 0, 0)"
        ).lastrowid
        assert newer_id > new_id
        conn.commit()
    finally:
        conn.close()
