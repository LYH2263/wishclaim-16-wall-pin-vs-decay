"""钉/卸编排：帽数校验 + 真态门槛。写路径只经 store 落 pins 表。

钉/卸不 sweep、不改 wishes.status、不触发 claim/release；
open 判定用真态函数（claimed 锁过期视为 open），无需写库。
"""
from datetime import datetime

from app.modules.wish_pin import store
from app.modules.wish_pin.projection import project_wall
from app.modules.wish_pin.truth import effective_status, pin_active

DEFAULT_PIN_MAX = 3
DEFAULT_HALF_LIFE = 604800


class PinError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _setting(c, key: str, default: int) -> int:
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    try:
        return int(r["value"]) if r else default
    except (TypeError, ValueError):
        return default


def pin_max(c) -> int:
    return _setting(c, "pin_max", DEFAULT_PIN_MAX)


def half_life(c) -> int:
    return _setting(c, "decay_half_life_seconds", DEFAULT_HALF_LIFE)


def pin_wish(c, wish_id: int, now: datetime, pinned_by: str = "") -> dict:
    """钉：仅真态 open 可钉，超帽拒钉。只写 pins 表。幂等。"""
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wish_id,)).fetchone()
    if not r:
        raise PinError("not_found")
    if effective_status(r["status"], r["expires_at"], now) != "open":
        raise PinError("not_open")
    if store.get_pin(c, wish_id):
        return {"ok": True, "already": True, "wish_id": wish_id}
    if store.pin_count(c) >= pin_max(c):
        raise PinError("pin_cap_reached")
    store.add_pin(c, wish_id, pinned_by, now.isoformat())
    return {"ok": True, "wish_id": wish_id}


def unpin_wish(c, wish_id: int) -> dict:
    """卸钉：幂等，只写 pins 表。卸后墙序回到衰减口径。"""
    store.remove_pin(c, wish_id)
    return {"ok": True, "wish_id": wish_id}


def wall(c, now: datetime) -> list[dict]:
    wishes = [dict(r) for r in c.execute("SELECT * FROM wishes")]
    return project_wall(wishes, store.list_pins(c), now, half_life(c))


def wish_detail(c, wish_id: int, now: datetime) -> dict | None:
    """真态详情：status 恒为真态，钉态只作附加字段，绝不覆盖 status。"""
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wish_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["status"] = effective_status(d["status"], d.get("expires_at"), now)
    p = store.get_pin(c, wish_id)
    d["pinned"] = p is not None
    d["pinned_at"] = p["pinned_at"] if p else None
    d["pin_active"] = pin_active(r["status"], r["expires_at"], now) if p else False
    return d
