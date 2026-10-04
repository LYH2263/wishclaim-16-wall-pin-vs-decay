from datetime import datetime, timedelta, timezone

from app.db import connect
from app.modules.wish_pin import PIN_DEFAULTS
from app.modules.wish_pin import store as pin_store

DEFAULT_SETTINGS = {
    "ttl_seconds": "86400",
    "wall_title": "暖粉愿望墙",
    **PIN_DEFAULTS,
}


def _migrate(c):
    cols = {r["name"] for r in c.execute("PRAGMA table_info(wishes)")}
    if "created_at" not in cols:
        c.execute("ALTER TABLE wishes ADD COLUMN created_at TEXT")
    # 回填：老数据统一落当前时间，同分按 id 倒序，保持迁移前墙序不变
    now_iso = datetime.now(timezone.utc).isoformat()
    c.execute("UPDATE wishes SET created_at=? WHERE created_at IS NULL", (now_iso,))


def init_db():
    c = connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS wishes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, note TEXT, status TEXT,
      claimer TEXT, claimed_at TEXT, expires_at TEXT, data_quality TEXT,
      created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    pin_store.ensure_schema(c)
    _migrate(c)
    for k, v in DEFAULT_SETTINGS.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (k, v))
    if c.execute("SELECT COUNT(*) c FROM wishes").fetchone()["c"] == 0:
        now = datetime.now(timezone.utc)

        def ago(**kw):
            return (now - timedelta(**kw)).isoformat()

        c.executemany(
            "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [
                ("机械键盘", "红轴", "open", None, None, None, "clean", ago(days=1)),
                ("围巾", "羊毛", "open", None, None, None, "clean", ago(days=3)),
                ("脏愿望-空标题", "", "open", None, None, None, "dirty", ago(hours=12)),
                ("过期锁样例", "应被TTL释放", "claimed", "ghost", "2020-01-01T00:00:00+00:00",
                 "2020-01-01T01:00:00+00:00", "dirty", ago(days=9)),
            ],
        )
    c.commit()
    c.close()
