# Host Phase 5 P5-S1 代码复审查报告

- **审查对象**: Host Phase 5 P5-S1 controller fix 后未提交 diff
- **审查分支**: `feat/host-phase5-local-dispatch`
- **审查日期**: 2026-05-15
- **审查角色**: 独立复审查员 (review only, no production changes)
- **复审查触发**: 首轮 DS M1 (PENDING → DISPATCHING 跳转语义缺陷) fix 验证
- **fix artifact**: `docs/reviews/gateflow-fix-host-p5-s1-dispatch-schema-transitions-20260514.md`

## 复审查重点

1. M1 修复正确性: `mark_dispatching_after_lane_row` 是否已限制为仅 `WAITING_FOR_LANE` 源状态
2. WHERE / source status / CAS result 是否正确
3. 是否引入新 blocker

## M1 修复验证

### 变更文件

- `dayu/host/durable/state.py` — 2 处修改
- `tests/host/test_run_attempt_transitions.py` — 1 个新回归测试

### 修复点 1: WHERE 子句限制源状态

**修复前** (原始实现):
```sql
WHERE attempt_id = ?
  AND status IN (?, ?)    -- 'pending', 'waiting_for_lane'
```
`PENDING` 可作为源状态直接跳转到 `DISPATCHING`。

**修复后**:
```sql
WHERE attempt_id = ?
  AND status = ?                          -- 仅 'waiting_for_lane'
  AND waiting_for_lane_at IS NOT NULL
  AND lane_name = ?
```

`PENDING` 被排除。新增 `waiting_for_lane_at IS NOT NULL` 和 `lane_name = ?` 双重防御，确保记录确实经过了 `waiting_for_lane` 阶段。

### 修复点 2: 移除 COALESCE 合成行为

**修复前**: SET 子句包含 `waiting_for_lane_at = COALESCE(waiting_for_lane_at, ?)`，可在 `waiting_for_lane_at` 为 NULL 时用 `dispatching_at` 合成伪值。

**修复后**: SET 子句不再触达 `waiting_for_lane_at`。因为源状态只能是 `WAITING_FOR_LANE`，该字段已有 CHECK 约束保证的 NOT NULL 值，无需合成。

### 修复点 3: 新增专用 mutation 结果分类器

新增 `_dispatch_record_mutation_result_for_lane_dispatching`:

```python
if rowcount == 1:
    return UPDATED
if latest is None:
    return NOT_FOUND
if latest.status == DispatchRecordStatus.WAITING_FOR_LANE:
    return CAS_LOST
return INVALID_STATE
```

与原 `_dispatch_record_mutation_result_for_dispatch_start` 的关键区别:
- `PENDING` 不再返回 `CAS_LOST`，改为 `INVALID_STATE`
- `WAITING_FOR_LANE` 仍返回 `CAS_LOST`（并发竞争保护）

调用方关系:
- `mark_dispatch_waiting_for_lane_row` → `_dispatch_record_mutation_result_for_dispatch_start` (PENDING 源，正确)
- `mark_dispatching_after_lane_row` → `_dispatch_record_mutation_result_for_lane_dispatching` (WAITING_FOR_LANE 源，新分类器)

### 修复点 4: 回归测试

新增 `test_dispatching_requires_waiting_for_lane_source`:
1. 创建 PENDING dispatch record
2. 直接调用 `mark_dispatching_after_lane_row` (跳过 `mark_dispatch_waiting_for_lane_row`)
3. 断言返回 `INVALID_STATE`，dispatch record 保持 `PENDING`

### M1 结论

**已修复。** PENDING 不能跳过 WAITING_FOR_LANE 直接进入 DISPATCHING。WHERE 子句、源状态限定、CAS 结果分类器和回归测试四层保障一致。

## 完整正确性交叉验证

### `mark_dispatching_after_lane_row` WHERE 条件审查

| 条件 | 作用 | 正确性 |
|---|---|---|
| `AND status = 'waiting_for_lane'` | 仅 WAITING_FOR_LANE 源 | ✓ |
| `AND waiting_for_lane_at IS NOT NULL` | 防御: 确保 wait 时间戳存在 | ✓ (CHECK 约束冗余) |
| `AND lane_name = ?` | 防御: 确保 lane 名称匹配 | ✓ |
| `AND lane_claim_id IS NULL` | 未重复派发 | ✓ |
| `AND lane_owner_id IS NULL` | 未重复派发 | ✓ |
| `AND lane_acquired_at IS NULL` | 未重复派发 | ✓ |
| `AND dispatching_at IS NULL` | 未重复派发 | ✓ |
| `AND worker_accept_event_id IS NULL` | 未 worker accept | ✓ |
| `AND cancelled_event_id IS NULL` | 未取消 | ✓ |

SET 参数绑定: 8 个 SET 参数 + 3 个 WHERE 参数 = 11 参数，与 SQL 占位符数量匹配。`lane_name` 在 SET 和 WHERE 中均使用同一值——正确。

### 并发竞争分析

| 场景 | 结果 | 正确性 |
|---|---|---|
| 两次并发 `mark_dispatch_waiting_for_lane_row` | 率先者 UPDATED，后者 CAS_LOST (WAITING_FOR_LANE) | ✓ |
| 两次并发 `mark_dispatching_after_lane_row` | 率先者 UPDATED，后者 CAS_LOST (WAITING_FOR_LANE) | ✓ |
| PENDING 直接调用 `mark_dispatching_after_lane_row` | INVALID_STATE，记录保持 PENDING | ✓ (回归测试覆盖) |
| DISPATCHING (pre-accept) 再次调用 `mark_dispatching_after_lane_row` | INVALID_STATE | ✓ |
| DISPATCHING (with worker accept) 再次调用 `mark_dispatching_after_lane_row` | INVALID_STATE | ✓ |
| CANCELLED 调用 `mark_dispatching_after_lane_row` | INVALID_STATE | ✓ |

### 已有 DS 建议项状态

| 原发现 | 状态 |
|---|---|
| M1: PENDING → DISPATCHING 语义缺陷 | **已修复** |
| M2: RUN_CANCELLING append 返回值未捕获 | 非阻塞，未变更 |
| M3: `_validate_common_cancel_input` 参数命名不匹配 | 非阻塞，未变更 |
| L1: 负面路径测试不完整 | 非阻塞，未变更 |
| L2: `_ensure_host_instance_tx` 测试间重复 | 非阻塞，未变更 |

### 架构约束重申检查

- [x] 分层边界: 改动仅限 `dayu/host/durable/state.py`，无跨界
- [x] 类型签名: 无 `object`/`Any`/无类型签名
- [x] 中文 docstring: 新函数 `_dispatch_record_mutation_result_for_lane_dispatching` 有完整 docstring
- [x] 无胶水 seam / lazy import / 兼容性代码
- [x] 无 lease/fencing/owner 语义
- [x] `test_weak_typing_guard.py` 未改动且继续通过

## 验证结果

```
34 passed in 0.23s
pyright: 0 errors, 0 warnings, 0 informations
git diff --check: no whitespace errors
```

测试从 33 增至 34（新增 `test_dispatching_requires_waiting_for_lane_source`）。

## 裁决

**M1 已修复，无新 blocker 引入。接受此 slice。**

fix 变更精准且最小化: 2 行 WHERE 限制 + 1 个分类器 + 1 个回归测试。状态机语义现在与 approved plan 一致: `pending → waiting_for_lane → dispatching → worker accepted refs`，且 SQL 层、CAS 结果层和测试层三层防御。
