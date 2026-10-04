"""规则页文案：与投影/存储同源生成，规则页说明与墙实际顺序同钉。"""


def pin_rules(pin_max: int, half_life_seconds: int) -> dict:
    days = half_life_seconds / 86400
    return {
        "pin_merge": "置顶区整体置于墙顶（先钉先顶，同刻 id 小者先），"
                     f"其余愿望按创建时间衰减排序（半衰期 {days:g} 天，越新越靠前）",
        "pin_cap": f"全墙最多同时钉 {pin_max} 条，仅 open 状态可钉，超帽拒钉",
        "pin_gray": "钉上的愿望被认领/核销后保留为灰钉且仍占名额，不自动卸钉；"
                    "恢复可认领（open/released）时自动点亮",
        "pin_side_effect": "钉/卸只写 pins 表：不改 wishes.status，不触发认领/释放",
        "pin_unpin": "卸钉后该愿望回到衰减序位置",
    }
