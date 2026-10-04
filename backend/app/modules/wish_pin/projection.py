"""排序投影：墙顺序 = 先全置顶，再按创建时间衰减。纯函数。

拍板：置顶区整体在墙顶（区内按 pinned_at 升序，先钉先顶，同刻 id 小者先）；
其余愿望按衰减分降序（同分 id 大者先）。投影只读输入行，输出附带
pinned / pin_active / pinned_at / decay_score / zone 字段，不改真态 status。
"""
from datetime import datetime

from app.engines.claim_lock import parse_ts
from app.modules.wish_pin.truth import pin_active


def decay_score(created_at: str | None, now: datetime, half_life_seconds: int) -> float:
    """score = 0.5 ** (age / half_life)。无创建时间 → 0.0（沉底）。"""
    if not created_at:
        return 0.0
    hl = max(1, int(half_life_seconds))
    age = max(0.0, (now - parse_ts(created_at)).total_seconds())
    return 0.5 ** (age / hl)


def project_wall(wishes: list[dict], pins: list[dict], now: datetime,
                 half_life_seconds: int) -> list[dict]:
    pin_map = {p["wish_id"]: p for p in pins}
    pinned, decay = [], []
    for w in wishes:
        row = dict(w)
        row["decay_score"] = decay_score(w.get("created_at"), now, half_life_seconds)
        p = pin_map.get(w["id"])
        if p:
            row["pinned"] = True
            row["pinned_at"] = p["pinned_at"]
            row["pin_active"] = pin_active(w["status"], w.get("expires_at"), now)
            row["zone"] = "pinned"
            pinned.append(row)
        else:
            row["pinned"] = False
            row["pinned_at"] = None
            row["pin_active"] = False
            row["zone"] = "decay"
            decay.append(row)
    pinned.sort(key=lambda r: (r["pinned_at"], r["id"]))
    decay.sort(key=lambda r: (-r["decay_score"], -r["id"]))
    return pinned + decay
