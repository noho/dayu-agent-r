# Re-Review: WU-CLI-ACTIVITY-01 follow-up Slice 3 fix

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/mimo-rereview-wu-cli-activity-01-followup-slice-3-20260618-073105.md`
- Reviewed artifacts:
  - `docs/reviews/mimo-wu-cli-activity-01-followup-slice-3-20260618-072504.md` (4 findings)
  - `docs/reviews/ds-wu-cli-activity-01-followup-slice-3-20260618-072339.md` (3 findings)
  - `docs/reviews/wu-cli-activity-01-followup-slice-3-fix-codex-20260618.md` (fix report)
- Included scope: `dayu/host/durable/event_log.py`, `dayu/host/projection.py`, `tests/host/test_event_log_store.py`, `tests/host/test_projection_runner.py`, `tests/host/test_projection_read_model.py`
- Verification focus: step cap test, FilteredEventLogPage cursor/id invariant with InitVar cursor, session_id test, max_event_sequence < cursor doc, read_limit tradeoff doc, no new public API, no Slice 4 changes

## Finding Status

### mimo Finding 001 — limit 作为 step cap 边界未被测试覆盖：已修复

- **修复证据**: 新增 `test_run_once_limit_caps_steps_when_matching_events_remain`（`test_projection_runner.py:1154`）
- **验证**: 构造 5 条 matching `TYPE_A` 事件，`limit=3`，断言：
  - `consumer.applied_events == ["event-1", "event-2", "event-3"]` — 只 apply 前 3 条
  - `result.events_scanned == 3, events_matched == 3, events_applied == 3`
  - `checkpoint.checkpoint_event_sequence == events[2].event_sequence` — checkpoint 停在第 3 条
  - `checkpoint.checkpoint_event_id == events[2].event_id`
- **结论**: 测试精确覆盖了"事件数 > limit 时循环在 limit 步后终止"的行为。`range(limit)` 截断语义有直接测试证明。

### mimo Finding 002 — FilteredEventLogPage 校验允许非空 rows 时 covered_event_id 为 None：已修复

- **修复证据**: `FilteredEventLogPage` 增加 `cursor: InitVar[int] = _MIN_EVENT_CURSOR`，`__post_init__` 接收 `cursor` 参数并增加不变量校验
- **验证**:
  - 新增 `has_covered_row = len(self.rows) > 0 or self.covered_event_sequence > cursor`（`event_log.py` line 253）
  - `if has_covered_row and self.covered_event_id is None: raise HostDurableError(...)`（line 254-255）
  - 新增 `test_filtered_event_log_page_requires_covered_event_id_for_real_cursor` 验证两个 case：
    - `rows=(row,), covered_event_id=None` → raises `HostDurableError`
    - `rows=(), covered_event_sequence > cursor, covered_event_id=None` → raises `HostDurableError`
  - Idle case 保留：`read_events_after_matching` 返回空 page 时传 `cursor=cursor`，`__post_init__` 中 `has_covered_row=False`，不触发校验
- **结论**: `InitVar cursor` 方案正确区分了"真实推进需要 event_id"与"idle 时允许 None"两种语义。不变量校验完整。

### mimo Finding 003 — max_event_sequence < cursor 时返回 cursor 而非报错：已修复

- **修复证据**: `read_events_after_matching` docstring 增加说明
- **验证**: docstring 现在明确写道："当 ``max_event_sequence`` 小于 ``cursor`` 时，读取窗口为空，同样返回 ``cursor`` 与 ``covered_event_id=None``。"
- **结论**: 行为未改变（保持返回 cursor 而非报错），但文档已明确说明此边界行为。符合 finding 建议的"保持现状并在 docstring 中说明"方案。

### mimo Finding 004 — store 层缺少 session_id 参数的直接测试：已修复

- **修复证据**: 新增 `test_read_events_after_matching_session_scope_limits_rows_and_covered_cursor`（`test_event_log_store.py:773`）
- **验证**:
  - 构造 session-a（event-1 TYPE_A, event-3 TYPE_B）和 session-b（event-2 TYPE_A, event-4 TYPE_A）
  - 用 `session_id="session-a"` 读取，filter 为 `TYPE_A`
  - 断言只返回 `("event-1",)` — session-a 的唯一 TYPE_A 事件
  - 断言 `covered_event_sequence == 3`（event-3 的 sequence，session-a 的 latest row）
  - 断言 `covered_event_id == "event-3"`（session-a 的 latest row id）
- **结论**: 测试精确覆盖了 session_id 过滤对 rows 和 covered cursor 的双重约束。SQL 参数绑定顺序（`*session_params` 位置）通过实际执行验证。

### ds Finding 01 — read_limit 导致 filtered query 重复执行：已修复

- **修复证据**: `run_once` 和 `_process_next_event` docstring 增加 tradeoff 说明
- **验证**:
  - `run_once` docstring（`projection.py` line 437-438）："每个 step 只 apply 第一条 matching row；较大的 page 可以在无匹配时更快推进 covered cursor，但密集 matching rows 仍按每条一个 transaction 处理。"
  - `_process_next_event` docstring（line 565-567）："``read_limit`` 只控制 filtered read page 大小。page 中有 matching row 时，本 step 只消费第一条 matching row；没有 matching row 时才使用 covered cursor 批量跳过不相关 rows。"
- **结论**: tradeoff 已在两处 docstring 中明确说明。finding 建议的"在 docstring 中明确注释此 tradeoff"已满足。

### ds Finding 02 — FilteredEventLogPage covered cursor 语义确认：证据失效

- **原始状态**: "无需修改。提为 finding 仅为显式确认"
- **结论**: 此 finding 本身是形式化确认，不要求修复。当前实现与设计 doc 一致。证据失效（finding 性质为确认而非缺陷）。

### ds Finding 03 — session_id filtered read 缺少测试：已修复

- **修复证据**: 同 mimo Finding 004，新增 `test_read_events_after_matching_session_scope_limits_rows_and_covered_cursor`
- **结论**: 已修复。

## 额外验证

### 无新增 public API / contract

- 新增类型 `EventLogReadClassFilter`、`EventLogReadFilter`、`FilteredEventLogPage`、`read_events_after_matching` 均在 `dayu/host/durable/event_log.py`（durable 层），不属于 Host public API
- `ProjectionRunner` 改动为内部实现细节，`run_once` 签名未变
- 无新增 Host public module export

### 无 Slice 4 memory 变更

- diff 未触及 `memory_repair.py`、`open_host.py`、`dispatch.py`、`run_input.py`
- `MemoryProjectionCatchupBudget` 未被移除（属 Slice 4 scope）
- 无新增 `conversation_memory_projection_event_filter()` 调用

### FilteredEventLogPage idle case 保留验证

- 空 page 返回 `FilteredEventLogPage(rows=(), covered_event_sequence=cursor, covered_event_id=None, cursor=cursor)`
- `__post_init__` 中 `has_covered_row = False`（rows 空且 sequence == cursor），不触发 `covered_event_id` 校验
- 测试 `test_read_events_after_matching_empty_log_and_cursor_at_latest_are_idle` 断言 `(7, None)` 和 `(1, None)` 均通过

## Residual Risk

- 无新增 residual risk。所有 accepted findings 均已修复或确认为证据失效。Slice 4 相关 deferred items 不在本次 scope 内。
