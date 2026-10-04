# Wishclaim · 礼物愿望认领

发布 → 认领锁定（互斥+TTL）→ 核销/释放。置顶钉 + 衰减序上墙。

| 服务 | 端口 |
| --- | --- |
| 前端 | 5200 |
| API | 10200 |

```bash
docker compose up --build
pytest backend/app/tests
```

0-1：`wish_comment` / `secret_santa` / `price_cap`。

## 置顶钉 + 衰减序（拍板记录）

| 决策点 | 拍板 |
| --- | --- |
| 合并策略 | **先全置顶再按衰减**：置顶区整体在墙顶，区内按钉时升序（先钉先顶，同刻 id 小者先）；其余按创建时间衰减分降序（`0.5^(age/半衰期)`，半衰期取 `settings.decay_half_life_seconds`，默认 7 天） |
| claimed 进置顶区 | **保留灰钉**：不自动卸钉，灰钉仍占名额；真态回到可认领（open/released）时自动点亮 |
| 钉帽 | 全墙共享 `N = settings.pin_max`（默认 3），仅真态 open 可钉，超帽 `409 pin_cap_reached` |
| 副作用边界 | 钉/卸**只写 pins 表**：不改 `wishes.status`，不触发 claim/release（钉选路径连 sweep 都不跑，open 判定用纯函数真态） |
| 卸钉 | 幂等删行，墙序即刻回到衰减口径 |
| 详情 | 恒为真态 status（claimed 锁过期视为 open）；钉态只作 `pinned/pin_active` 附加字段，绝不覆盖 status |

灰钉决策**三路可核**：① 规则页 `/api/rules` 的 `pin_gray` 文案；② 墙投影 `/api/wishes` 的 `zone=pinned + pin_active=false`（前端渲染灰钉）；③ 详情 `/api/wishes/{id}` 的真 `status` + `pinned`。

### 模块边界（置顶存储 / 排序投影 / 真态详情分模块）

```
app/modules/wish_pin/
  store.py        pins 表唯一读写口（DDL + CRUD）
  projection.py   墙排序投影（纯函数）：先全置顶再按衰减
  truth.py        真态判定（纯函数）：effective_status / pin_active
  service.py      钉/卸编排 + 帽数校验（写路径只经 store）
  rules_text.py   规则页文案，与实现同源（同钉）
```

### 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/wishes` | 投影序列表，含 `pinned/pin_active/pinned_at/decay_score/zone` |
| GET | `/api/wishes/{id}` | 真态详情 + 钉态附加字段 |
| POST | `/api/wishes/{id}/pin` | 钉（幂等；`not_open` / `pin_cap_reached` → 409） |
| POST | `/api/wishes/{id}/unpin` | 卸钉（幂等） |
| GET | `/api/rules` | 规则文案（含 pin_* 条目，数值取自 settings） |

设置项：`pin_max`（默认 3）、`decay_half_life_seconds`（默认 604800），经 `/api/settings` 可读。
