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
