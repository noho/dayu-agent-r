# WU-CLI-ACTIVITY-01 follow-up Slice 3 review fix

## 元数据

- Work unit：`WU-CLI-ACTIVITY-01 follow-up`
- Slice：3，EventLog filter-aware read 与 ProjectionRunner catch-up semantics
- Gate：review fix
- 日期：2026-06-18
- 实施者：Codex
- Artifact：`docs/reviews/wu-cli-activity-01-followup-slice-3-fix-codex-20260618.md`

## Scope

本次只处理 Slice 3 review accepted findings。未修改 Host / Engine public API/contracts，未修改 durable schema，未实现 Slice 4 memory repair / open_host / dispatch / inline repair 改动，未移除 `MemoryProjectionCatchupBudget`。

## Finding Status

- Finding 1：`ProjectionRunner.run_once` 缺少证明 `limit` 是 step cap 的测试。
  - 状态：已修复。
  - 证据：新增 `test_run_once_limit_caps_steps_when_matching_events_remain`，构造 5 条 matching `TYPE_A`，`limit=3` 只 apply 前 3 条，checkpoint 停在第 3 条。

- Finding 2：`FilteredEventLogPage.__post_init__` 对 covered cursor / event id 不变量不足。
  - 状态：已修复。
  - 证据：`FilteredEventLogPage` 增加 init-only `cursor` 校验；rows 非空或 `covered_event_sequence > cursor` 时要求 `covered_event_id` 非空，同时保留 empty window / idle 时 `cursor,None` 的 producer 行为。新增 focused unit assertion。

- Finding 3：缺少 `read_events_after_matching(session_id=...)` mixed sessions 测试。
  - 状态：已修复。
  - 证据：新增 session-scoped filtered read 测试，验证 rows 与 covered cursor/id 都限定在目标 session。

- Finding 4：`max_event_sequence < cursor` 行为需要说明，不改行为。
  - 状态：已修复。
  - 证据：`read_events_after_matching(...)` docstring 明确该空窗口返回 `cursor` 与 `covered_event_id=None`。

- Finding 5：ProjectionRunner docstring 需要说明 read_limit 取舍。
  - 状态：已修复。
  - 证据：`run_once(...)` 与 `_process_next_event(...)` docstring 增加说明：每个 step 只 apply 第一条 matching row；较大 page 仅帮助无匹配时更快推进 covered cursor，dense matching rows 仍每条一个 transaction。

## Rejected / Deferred Findings

- Public API / contract change：rejected，不在 Slice 3 范围内，本次未做。
- Slice 4 memory repair / open_host / dispatch / inline repair：deferred to approved later slice，本次未做。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_projection_runner.py`
  - 32 passed
- `source .venv/bin/activate && pyright dayu/host/durable/event_log.py dayu/host/projection.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py`
  - 0 errors, 0 warnings
- `git diff --check`
  - passed

## Residual Risks

- fixed in current slice：review accepted findings 1 到 5 均已补齐测试、docstring 或 invariant。
- covered by later approved slice：`memory_repair`、`open_host`、`dispatch` 与 RunInputBuilder inline repair 仍按 Slice 4 处理。
- no unclassified residual risk。

## Completion Status

Slice 3 review fix complete。
