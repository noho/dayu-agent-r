# Code Review — Slice 3 Fix Re-review

## Scope

- Mode: re-review of fix
- Branch: `wu-cli-activity-01`
- Base: `HEAD` (uncommitted Slice 3 fix workspace changes)
- Output file: `docs/reviews/ds-rereview-wu-cli-activity-01-followup-slice-3-20260618-073110.md`
- Source reviews:
  - `docs/reviews/mimo-wu-cli-activity-01-followup-slice-3-20260618-072504.md` — MiMo review (4 findings)
  - `docs/reviews/ds-wu-cli-activity-01-followup-slice-3-20260618-072339.md` — DS review (3 findings, overlapping with MiMo)
- Fix report: `docs/reviews/wu-cli-activity-01-followup-slice-3-fix-codex-20260618.md`
- Included scope:
  - `dayu/host/durable/event_log.py` — `FilteredEventLogPage` InitVar cursor invariant, `read_events_after_matching` docstring
  - `dayu/host/projection.py` — `run_once` / `_process_next_event` docstring read_limit tradeoff
  - `tests/host/test_event_log_store.py` — new session_id filtered read test
  - `tests/host/test_projection_runner.py` — new step cap test
- Excluded scope: Slice 4/5 files; `MemoryProjectionCatchupBudget` removal

## Finding Status

### Finding 001 (MiMo) / — (DS): limit 作为 step cap 边界未被测试覆盖

- **状态**: 已修复
- **证据**:
  - 新增测试 `test_run_once_limit_caps_steps_when_matching_events_remain` (`tests/host/test_projection_runner.py:751-786`)
  - 构造 5 条匹配 TYPE_A 事件 (`event-1` 到 `event-5`)，`run_once(limit=3)`
  - 断言 `consumer.applied_events == ["event-1", "event-2", "event-3"]` (line 775-779)
  - 断言 `result.events_scanned == 3`、`result.events_matched == 3`、`result.events_applied == 3` (line 780-782)
  - 断言 `result.finished_cursor == events[2].event_sequence` (line 783)
  - 断言 `checkpoint.checkpoint_event_sequence == events[2].event_sequence` (line 785)
  - 剩余 `event-4`、`event-5` 未被 apply，checkpoint 停在第 3 条
- **验证**: `pytest tests/host/test_projection_runner.py -q` — 32 passed

### Finding 002 (MiMo) / Finding 02 (DS): FilteredEventLogPage 校验允许非空 rows 时 covered_event_id 为 None

- **状态**: 已修复
- **证据**:
  - `FilteredEventLogPage` 新增 `cursor: InitVar[int]` 字段 (`dayu/host/durable/event_log.py:225`)
  - `__post_init__(self, cursor)` 新增三项校验 (line 227-259):
    1. `covered_event_sequence < cursor` → 报错 "covered cursor moved backwards" (line 239-240)
    2. `has_covered_row = len(self.rows) > 0 or self.covered_event_sequence > cursor` (line 244)
    3. `has_covered_row and self.covered_event_id is None` → 报错 "covered event_id is required" (line 245-246)
  - idle 场景 (`cursor == covered_event_sequence`, `rows=()`) 仍允许 `covered_event_id=None` (line 244: `has_covered_row` 为 False)
  - 所有 `read_events_after_matching` 构造点均传入 `cursor=cursor` (line 683-688 idle, line 735-740 non-idle)
  - `from dataclasses import InitVar, dataclass` (line 15)
- **边界验证**:
  - 空 EventLog (idle): `rows=(), covered=cursor, id=None, cursor=cursor` → `has_covered_row=False` ✅
  - 有 matching rows: `rows=(...), covered=row.seq, id=row.id, cursor=cursor` → `has_covered_row=True, id≠None` ✅
  - 无 matching but covered advance: `rows=(), covered=boundary.seq, id=boundary.id, cursor=cursor` → `has_covered_row=True, id≠None` ✅
- **验证**: `pyright dayu/host/durable/event_log.py` — 0 errors

### Finding 003 (MiMo) / Finding 03 (DS): max_event_sequence < cursor 时返回 cursor 而非报错 / session_id 缺测试

MiMo Finding 003 与 DS Finding 03 合并处理（DS Finding 03 对应 MiMo Finding 004）。

#### MiMo 003: max_event_sequence < cursor doc behavior

- **状态**: 已修复
- **证据**: `read_events_after_matching` docstring 新增 (`dayu/host/durable/event_log.py:656-657`):
  > 当 ``max_event_sequence`` 小于 ``cursor`` 时，读取窗口为空，同样返回 ``cursor`` 与 ``covered_event_id=None``。
- **验证**: 行为未改（空窗口返回 idle 语义正确），仅补充文档

#### MiMo 004 / DS 03: session_id 参数缺测试

- **状态**: 已修复
- **证据**:
  - 新增测试 `test_read_events_after_matching_session_scope_limits_rows_and_covered_cursor` (`tests/host/test_event_log_store.py:515-568`)
  - 构造 4 条事件：`event-1` (session-a, TYPE_A)、`event-2` (session-b, TYPE_A)、`event-3` (session-a, TYPE_B)、`event-4` (session-b, TYPE_A)
  - Filter: `CANONICAL_FACT TYPE_A`，`session_id="session-a"`
  - 断言 `rows == ("event-1",)` — 只返回 session-a 的匹配 TYPE_A (line 564-565)
  - 断言 `covered_event_sequence == 3` — covered cursor 是 session-a 内最新真实 row event-3 (TYPE_B, 不匹配但存在) (line 566)
  - 断言 `covered_event_id == "event-3"` — 不跨 session (line 567)
- **验证**: `pytest tests/host/test_event_log_store.py -q` — passed

### Finding 01 (DS): ProjectionRunner run_once 每步传递冗余 read_limit 导致 filtered query 重复执行

对应 fix report Finding 5。

- **状态**: 已修复
- **证据**:
  - `run_once` docstring 新增 (`dayu/host/projection.py:437-439`):
    > 每个 step 只 apply 第一条 matching row；较大的 page 可以在无匹配时更快推进 covered cursor，但密集 matching rows 仍按每条一个 transaction 处理。
  - `_process_next_event` docstring 新增 (line 566-570):
    > ``read_limit`` 只控制 filtered read page 大小。page 中有 matching row 时，本 step 只消费第一条 matching row；没有 matching row 时才使用 covered cursor 批量跳过不相关 rows。
  - 行为未改（tradeoff 是设计决策，不是 bug），仅补充文档说明
- **验证**: docstring 已自解释 read_limit 的双重作用与 tradeoff

## 附加验证

### 无新增 public API / contract 变更

- `EventLogStore` 的 public 方法签名未变（`read_events_after_matching` 签名未变）
- `ProjectionRunner` public 方法签名未变
- `ProjectionConsumer` Protocol 未变
- 无新增 `__all__`、re-export 或 public module 暴露

### 无 Slice 4 memory 变更泄漏

- `dayu/host/durable/event_log.py`、`dayu/host/projection.py`、`tests/host/test_event_log_store.py`、`tests/host/test_projection_runner.py` 均不含 `memory`、`MemoryProjectionCatchupBudget`、`_MEMORY_EVENT_TYPES`、`_is_memory_projection_row`、`conversation_memory` 引用
- `grep -rn` 确认零命中

### 测试与类型检查

- `pytest tests/host/test_event_log_store.py tests/host/test_projection_runner.py -q` — 32 passed
- `pyright dayu/host/durable/event_log.py dayu/host/projection.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py` — 0 errors, 0 warnings
- `git diff --stat HEAD` — 仅触及 Slice 3 文件，无 Slice 4 文件

## Open Questions

- 无。

## Residual Risk

- **无新增 residual risk**。本次 fix 仅补齐测试覆盖、defensive invariant 与 docstring，未修改任何生产行为路径。
- 原 DS review residual risks（`events_scanned` 语义变更窗口、`max_event_sequence <= started_cursor` 早退缺失）仍存在，属 Slice 4 处理范围。

## Finding Status Summary

| Finding ID | 来源 | 简述 | 状态 |
|---|---|---|---|
| MiMo 001 | mimo review | limit step cap 缺测试 | 已修复 |
| MiMo 002 | mimo review | FilteredEventLogPage covered_event_id 不变量不足 | 已修复 |
| MiMo 003 | mimo review | max_event_sequence < cursor doc | 已修复 |
| MiMo 004 | mimo review | session_id filtered read 缺测试 | 已修复 |
| DS 01 | ds review | read_limit tradeoff doc | 已修复 |
| DS 02 | ds review | covered cursor 语义形式化确认 | 已修复（同 MiMo 002） |
| DS 03 | ds review | session_id 测试盲区 | 已修复（同 MiMo 004） |

**7/7 accepted findings 均已修复。** 无部分修复或证据失效。
