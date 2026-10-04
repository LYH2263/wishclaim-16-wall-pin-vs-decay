from datetime import datetime, timedelta, timezone
import sqlite3
from app.engines.claim_lock import claim_allowed, lock_payload, release_if_expired, sweep_expired

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

def test_mutex_blocks_second_claimer():
    r = claim_allowed("claimed", "alice", NOW, (NOW + timedelta(hours=1)).isoformat())
    assert r["ok"] is False and r["reason"] == "locked"

def test_ttl_allows_reclaim():
    r = claim_allowed("claimed", "alice", NOW, (NOW - timedelta(minutes=1)).isoformat())
    assert r["ok"] is True

def test_lock_payload_sets_expiry():
    p = lock_payload("bob", NOW, 3600)
    assert p["status"] == "claimed" and p["claimer"] == "bob"
    assert release_if_expired("claimed", p["expires_at"], NOW) is None
    assert release_if_expired("claimed", (NOW - timedelta(seconds=1)).isoformat(), NOW)["status"] == "open"

def test_sweep_expired_releases_only_expired_locks():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE wishes(id INTEGER PRIMARY KEY, title TEXT, note TEXT, status TEXT,"
              " claimer TEXT, claimed_at TEXT, expires_at TEXT, data_quality TEXT)")
    past = (NOW - timedelta(hours=1)).isoformat()
    future = (NOW + timedelta(hours=1)).isoformat()
    c.execute("INSERT INTO wishes VALUES (1,'a','','claimed','x',?,?,'clean')", (past, past))
    c.execute("INSERT INTO wishes VALUES (2,'b','','claimed','y',?,?,'clean')", (future, future))
    assert sweep_expired(c, NOW) == 1
    rows = {r["id"]: (r["status"], r["claimer"]) for r in c.execute("SELECT * FROM wishes")}
    assert rows == {1: ("open", None), 2: ("claimed", "y")}
    assert sweep_expired(c, NOW) == 0
