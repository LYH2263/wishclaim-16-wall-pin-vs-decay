"""置顶钉 + 衰减序：存储 / 投影 / 真态 三路可核测试。

纯 stdlib（pytest 兼容，无 fixture），每个用例独立 DATA_DIR。
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

from app.db import connect
from app import seed
from app.modules.wish_pin import rules_text, service
from app.modules.wish_pin.projection import decay_score
from app.modules.wish_pin.truth import effective_status

NOW = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
HL = 604800  # 7 天半衰期


def fresh(pin_max="3"):
    os.environ["DATA_DIR"] = tempfile.mkdtemp()
    seed.init_db()
    c = connect()
    c.execute("DELETE FROM wishes")
    c.execute("DELETE FROM pins")
    c.execute("UPDATE settings SET value=? WHERE key='pin_max'", (pin_max,))
    c.commit()
    return c


def add_wish(c, title, status="open", created_at=None, claimer=None, expires_at=None):
    cur = c.execute(
        "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality,created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (title, "", status, claimer, None, expires_at, "clean",
         (created_at or NOW).isoformat()))
    c.commit()
    return cur.lastrowid


def wishes_snapshot(c):
    return [dict(r) for r in c.execute("SELECT * FROM wishes ORDER BY id")]


def iso(dt):
    return dt.isoformat()


# ---------- 存储：钉选只写 pins 表 ----------

def test_pin_writes_only_pins_table():
    c = fresh()
    wid = add_wish(c, "键盘")
    before = wishes_snapshot(c)
    r = service.pin_wish(c, wid, NOW, "alice")
    assert r["ok"] and wishes_snapshot(c) == before
    pins = [dict(x) for x in c.execute("SELECT * FROM pins")]
    assert len(pins) == 1 and pins[0]["wish_id"] == wid and pins[0]["pinned_by"] == "alice"
    assert wishes_snapshot(c)[0]["status"] == "open"  # 不触发 claim/release


def test_unpin_writes_only_pins_table_and_idempotent():
    c = fresh()
    wid = add_wish(c, "键盘")
    service.pin_wish(c, wid, NOW)
    before = wishes_snapshot(c)
    assert service.unpin_wish(c, wid)["ok"]
    assert wishes_snapshot(c) == before
    assert [dict(x) for x in c.execute("SELECT * FROM pins")] == []
    assert service.unpin_wish(c, wid)["ok"]  # 幂等


def test_repin_is_idempotent_and_keeps_first_pin_time():
    c = fresh()
    wid = add_wish(c, "键盘")
    service.pin_wish(c, wid, NOW)
    r = service.pin_wish(c, wid, NOW + timedelta(seconds=5))
    assert r["already"] is True
    pins = [dict(x) for x in c.execute("SELECT * FROM pins")]
    assert len(pins) == 1 and pins[0]["pinned_at"] == iso(NOW)


# ---------- 帽数与门槛 ----------

def test_pin_cap_rejects_beyond_n():
    c = fresh(pin_max="2")
    w1 = add_wish(c, "a")
    w2 = add_wish(c, "b")
    w3 = add_wish(c, "c")
    service.pin_wish(c, w1, NOW)
    service.pin_wish(c, w2, NOW)
    try:
        service.pin_wish(c, w3, NOW)
        assert False, "应当拒钉"
    except service.PinError as e:
        assert e.reason == "pin_cap_reached"
    assert c.execute("SELECT COUNT(*) n FROM pins").fetchone()["n"] == 2


def test_pin_requires_true_open_status():
    c = fresh()
    future = iso(NOW + timedelta(hours=1))
    past = iso(NOW - timedelta(hours=1))
    w_claimed = add_wish(c, "claimed", status="claimed", claimer="x", expires_at=future)
    w_fulfilled = add_wish(c, "fulfilled", status="fulfilled")
    w_released = add_wish(c, "released", status="released")
    w_expired = add_wish(c, "expired", status="claimed", claimer="x", expires_at=past)
    for wid in (w_claimed, w_fulfilled, w_released):
        try:
            service.pin_wish(c, wid, NOW)
            assert False, f"{wid} 应当拒钉"
        except service.PinError as e:
            assert e.reason == "not_open"
    # 锁已过期的 claimed 真态为 open，可钉；且 wishes 行不被钉选改写
    service.pin_wish(c, w_expired, NOW)
    row = c.execute("SELECT * FROM wishes WHERE id=?", (w_expired,)).fetchone()
    assert row["status"] == "claimed" and row["claimer"] == "x"


def test_pin_missing_wish_404():
    c = fresh()
    try:
        service.pin_wish(c, 999, NOW)
        assert False
    except service.PinError as e:
        assert e.reason == "not_found"


# ---------- 投影：先全置顶再按衰减 ----------

def test_merge_order_all_pins_first_then_decay():
    c = fresh()
    w_old = add_wish(c, "old", created_at=NOW - timedelta(days=3))
    w_new = add_wish(c, "new", created_at=NOW - timedelta(days=1))
    w_mid = add_wish(c, "mid", created_at=NOW - timedelta(days=2))
    # 纯衰减序：new > mid > old
    assert [r["id"] for r in service.wall(c, NOW)] == [w_new, w_mid, w_old]
    service.pin_wish(c, w_old, NOW)
    service.pin_wish(c, w_mid, NOW + timedelta(seconds=1))
    rows = service.wall(c, NOW)
    # 置顶区先钉先顶：old, mid；衰减区：new
    assert [r["id"] for r in rows] == [w_old, w_mid, w_new]
    assert [r["zone"] for r in rows] == ["pinned", "pinned", "decay"]
    assert rows[0]["pinned"] and rows[2]["pinned"] is False
    before = wishes_snapshot(c)
    service.wall(c, NOW)
    assert wishes_snapshot(c) == before  # 投影纯读，不写库


def test_unpin_returns_to_decay_order():
    c = fresh()
    w_old = add_wish(c, "old", created_at=NOW - timedelta(days=3))
    w_new = add_wish(c, "new", created_at=NOW - timedelta(days=1))
    w_mid = add_wish(c, "mid", created_at=NOW - timedelta(days=2))
    service.pin_wish(c, w_old, NOW)
    assert service.wall(c, NOW)[0]["id"] == w_old
    service.unpin_wish(c, w_old)
    assert [r["id"] for r in service.wall(c, NOW)] == [w_new, w_mid, w_old]


def test_decay_score_math():
    assert decay_score(iso(NOW), NOW, HL) == 1.0
    assert abs(decay_score(iso(NOW - timedelta(seconds=HL)), NOW, HL) - 0.5) < 1e-9
    assert decay_score(None, NOW, HL) == 0.0
    assert decay_score(iso(NOW + timedelta(days=1)), NOW, HL) == 1.0  # 未来创建不越界


# ---------- 灰钉：三路可核 ----------

def test_gray_pin_kept_and_three_way_verifiable():
    c = fresh()
    wid = add_wish(c, "将被认领", created_at=NOW - timedelta(days=5))
    w_new = add_wish(c, "新愿望", created_at=NOW - timedelta(days=1))
    service.pin_wish(c, wid, NOW)
    future = iso(NOW + timedelta(hours=1))
    c.execute("UPDATE wishes SET status='claimed', claimer='bob', expires_at=? WHERE id=?",
              (future, wid))
    c.commit()
    # 路一：规则页文案承诺“保留灰钉”
    rules = rules_text.pin_rules(service.pin_max(c), service.half_life(c))
    assert "灰钉" in rules["pin_gray"] and "不自动卸钉" in rules["pin_gray"]
    # 路二：墙投影仍在置顶区但置灰，且钉子仍在（占名额）
    rows = service.wall(c, NOW)
    assert rows[0]["id"] == wid and rows[0]["zone"] == "pinned"
    assert rows[0]["pin_active"] is False and rows[0]["status"] == "claimed"
    assert rows[1]["id"] == w_new
    assert c.execute("SELECT COUNT(*) n FROM pins WHERE wish_id=?", (wid,)).fetchone()["n"] == 1
    # 路三：详情恒为真态 claimed，钉态只是附加字段
    d = service.wish_detail(c, wid, NOW)
    assert d["status"] == "claimed" and d["pinned"] is True and d["pin_active"] is False


def test_gray_pin_reactivates_after_ttl_without_unpin():
    c = fresh()
    wid = add_wish(c, "过期锁")
    service.pin_wish(c, wid, NOW)
    past = iso(NOW - timedelta(minutes=1))
    c.execute("UPDATE wishes SET status='claimed', claimer='ghost', expires_at=? WHERE id=?",
              (past, wid))
    c.commit()
    # 锁已过期：真态 open，钉子自动点亮，无需任何写操作
    rows = service.wall(c, NOW)
    assert rows[0]["id"] == wid and rows[0]["pin_active"] is True
    d = service.wish_detail(c, wid, NOW)
    assert d["status"] == "open" and d["pinned"] is True


# ---------- 真态 ----------

def test_truth_effective_status():
    future = iso(NOW + timedelta(hours=1))
    past = iso(NOW - timedelta(hours=1))
    assert effective_status("claimed", past, NOW) == "open"
    assert effective_status("claimed", future, NOW) == "claimed"
    assert effective_status("open", None, NOW) == "open"
    assert effective_status("fulfilled", None, NOW) == "fulfilled"


# ---------- 规则页与实现同钉 ----------

def test_rules_text_matches_live_settings_and_behavior():
    c = fresh(pin_max="2")
    rules = rules_text.pin_rules(service.pin_max(c), service.half_life(c))
    assert "最多同时钉 2 条" in rules["pin_cap"]
    assert "半衰期 7 天" in rules["pin_merge"]
    w1 = add_wish(c, "a")
    w2 = add_wish(c, "b")
    w3 = add_wish(c, "c")
    service.pin_wish(c, w1, NOW)
    service.pin_wish(c, w2, NOW)
    try:
        service.pin_wish(c, w3, NOW)
        assert False
    except service.PinError as e:
        assert e.reason == "pin_cap_reached"  # 文案帽数与行为一致
