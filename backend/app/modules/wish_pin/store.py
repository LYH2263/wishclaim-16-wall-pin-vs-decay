"""置顶存储：pins 表的唯一读写口。

钉选只写本表；本模块绝不触碰 wishes 表，也不触发 claim/release。
"""

DDL = """
CREATE TABLE IF NOT EXISTS pins(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wish_id INTEGER NOT NULL UNIQUE,
  pinned_by TEXT NOT NULL DEFAULT '',
  pinned_at TEXT NOT NULL
);
"""


def ensure_schema(c):
    c.executescript(DDL)


def list_pins(c) -> list[dict]:
    return [dict(r) for r in c.execute(
        "SELECT * FROM pins ORDER BY pinned_at ASC, wish_id ASC")]


def get_pin(c, wish_id: int) -> dict | None:
    r = c.execute("SELECT * FROM pins WHERE wish_id=?", (wish_id,)).fetchone()
    return dict(r) if r else None


def pin_count(c) -> int:
    return c.execute("SELECT COUNT(*) n FROM pins").fetchone()["n"]


def add_pin(c, wish_id: int, pinned_by: str, pinned_at: str) -> None:
    c.execute("INSERT INTO pins(wish_id, pinned_by, pinned_at) VALUES (?,?,?)",
              (wish_id, pinned_by, pinned_at))


def remove_pin(c, wish_id: int) -> None:
    c.execute("DELETE FROM pins WHERE wish_id=?", (wish_id,))
