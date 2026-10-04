"""置顶钉 + 衰减序：置顶存储 / 排序投影 / 真态详情 分模块。

- store:       pins 表的唯一读写口（钉选只写 pins 表）
- projection:  墙排序投影（先全置顶再按衰减），纯函数
- truth:       真态判定（TTL 到期视为 open），纯函数
- service:     钉/卸编排与帽数校验，只经 store 写 pins
- rules_text:  规则页文案，与实现同源（同钉）
"""
from app.modules.wish_pin import store, projection, truth, service, rules_text

PIN_DEFAULTS = {
    "pin_max": "3",
    "decay_half_life_seconds": "604800",
}

__all__ = ["store", "projection", "truth", "service", "rules_text", "PIN_DEFAULTS"]
