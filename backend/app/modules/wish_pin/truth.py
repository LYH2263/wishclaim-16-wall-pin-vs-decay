"""真态详情：愿望的真实状态判定，纯函数，不写库。

详情页与投影共用同一份真态口径：claimed 且锁已过期即视为 open。
"""
from datetime import datetime

from app.engines.claim_lock import parse_ts

# 钉子为“亮”的真态集合：当前可认领。claimed/fulfilled 为灰钉。
PIN_ACTIVE_STATUSES = ("open", "released")


def effective_status(status: str, expires_at: str | None, now: datetime) -> str:
    """claimed 锁已过期 → 真态 open；其余原样返回。"""
    if status == "claimed" and expires_at and parse_ts(expires_at) <= now:
        return "open"
    return status


def pin_active(status: str, expires_at: str | None, now: datetime) -> bool:
    return effective_status(status, expires_at, now) in PIN_ACTIVE_STATUSES
