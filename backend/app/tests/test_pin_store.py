import sqlite3
import pytest
from fastapi import HTTPException
from app import seed, main
from app.db import connect
from app.modules import pin as pinstore
from app.engines.pin import pin_allowed


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    return tmp_path


def test_fresh_seed_schema(fresh_db):
    c = connect()
    assert c.execute("SELECT COUNT(*) FROM pins").fetchone()[0] == 0
    assert c.execute("SELECT value FROM settings WHERE key='max_pins'").fetchone()["value"] == "3"
    c.close()


def test_pin_writes_only_pin_table(fresh_db):
    c = connect()
    before = dict(c.execute("SELECT * FROM wishes WHERE id=2").fetchone())
    pinstore.pin(c, 2); c.commit()
    after = dict(c.execute("SELECT * FROM wishes WHERE id=2").fetchone())
    assert before == after
    assert before["status"] == "open"
    assert pinstore.is_pinned(c, 2)
    c.close()


def test_duplicate_pin_raises(fresh_db):
    c = connect()
    pinstore.pin(c, 2); c.commit()
    with pytest.raises(sqlite3.IntegrityError):
        pinstore.pin(c, 2)
    c.close()


def test_grey_pins_count_toward_cap(fresh_db):
    c = connect()
    for wid in (1, 2, 3):
        pinstore.pin(c, wid)
    c.commit()
    assert pinstore.pin_count(c) == 3
    c.execute("UPDATE wishes SET status='claimed' WHERE id=3"); c.commit()
    assert pinstore.pin_count(c) == 3
    assert pin_allowed(False, "open", 3, 3)["reason"] == "pin_cap_exceeded"
    c.close()


def test_claim_release_keep_pin_unpin_deletes(fresh_db):
    main.pin_wish(2)
    main.claim(2, main.ClaimIn(claimer="zoe"))
    d = main.get_wish(2)
    assert d["status"] == "claimed" and d["claimer"] == "zoe" and d["pinned"] is True

    wall = main.list_wishes()
    assert wall[0]["id"] == 2 and wall[0]["status"] == "claimed" and wall[0]["pinned"] is True

    main.release(2)
    d = main.get_wish(2)
    assert d["status"] == "released" and d["pinned"] is True

    r = main.unpin_wish(2)
    assert r["pinned"] is False
    assert main.get_wish(2)["pinned"] is False
    with pytest.raises(HTTPException) as ei:
        main.unpin_wish(2)
    assert ei.value.status_code == 400 and ei.value.detail == "not_pinned"


def test_pin_error_mapping(fresh_db):
    with pytest.raises(HTTPException) as ei:
        main.pin_wish(999)
    assert ei.value.status_code == 404

    # A live (unexpired) claimed wish cannot be pinned.
    c = connect()
    c.execute("UPDATE wishes SET status='claimed', expires_at='2099-01-01T00:00:00+00:00' WHERE id=1")
    c.commit(); c.close()
    with pytest.raises(HTTPException) as ei:
        main.pin_wish(1)
    assert ei.value.status_code == 400 and ei.value.detail == "pin_only_open"

    # Seed rows 1/2/3 open plus id 4 swept back to open: fill all 3 slots first.
    c = connect()
    for wid in (1, 2, 3):
        pinstore.pin(c, wid)
    c.commit(); c.close()
    with pytest.raises(HTTPException) as ei:
        main.pin_wish(4)
    assert ei.value.status_code == 409 and ei.value.detail == "pin_cap_exceeded"

    with pytest.raises(HTTPException) as ei:
        main.unpin_wish(999)
    assert ei.value.status_code == 404


def test_unpin_restores_decay_order(fresh_db):
    for wid in (2, 4):
        main.pin_wish(wid)
    assert [r["id"] for r in main.list_wishes()][:2] == [4, 2]
    main.unpin_wish(4)
    wall = main.list_wishes()
    assert wall[0]["id"] == 2 and wall[0]["pinned"] is True
    assert [r["id"] for r in wall if not r["pinned"]] == [4, 3, 1]


def test_old_db_migration_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    c = connect()
    c.executescript("""
    CREATE TABLE wishes(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT);
    CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    c.execute("INSERT INTO wishes(title) VALUES ('old')")
    c.commit(); c.close()

    seed.init_db()
    seed.init_db()
    c = connect()
    assert c.execute("SELECT COUNT(*) FROM pins").fetchone()[0] == 0
    rows = c.execute("SELECT value FROM settings WHERE key='max_pins'").fetchall()
    assert len(rows) == 1 and rows[0]["value"] == "3"
    c.close()
