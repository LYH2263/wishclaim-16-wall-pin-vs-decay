"""Pin storage: one row per pinned wish. Knows nothing about wish status."""

DDL = "CREATE TABLE IF NOT EXISTS pins(wish_id INTEGER PRIMARY KEY)"


def init_table(c):
    c.execute(DDL)


def pin(c, wish_id):
    # PK makes duplicate pins raise sqlite3.IntegrityError even under concurrency.
    c.execute("INSERT INTO pins(wish_id) VALUES (?)", (wish_id,))


def unpin(c, wish_id):
    cur = c.execute("DELETE FROM pins WHERE wish_id=?", (wish_id,))
    return cur.rowcount


def is_pinned(c, wish_id):
    return c.execute("SELECT 1 FROM pins WHERE wish_id=?", (wish_id,)).fetchone() is not None


def pin_count(c):
    # Counts grey pins too — no JOIN, no status filter.
    return c.execute("SELECT COUNT(*) c FROM pins").fetchone()["c"]


def pinned_ids(c):
    return [r["wish_id"] for r in c.execute("SELECT wish_id FROM pins ORDER BY wish_id DESC")]
