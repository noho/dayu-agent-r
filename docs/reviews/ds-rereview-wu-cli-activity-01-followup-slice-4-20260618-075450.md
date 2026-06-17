# Re-review: WU-CLI-ACTIVITY-01 follow-up Slice 4 fix

## 元数据

- Work unit：`WU-CLI-ACTIVITY-01 follow-up`
- Slice：4 review fix
- 日期：2026-06-18
- 触发 review artifact：`docs/reviews/ds-wu-cli-activity-01-followup-slice-4-code-review-20260618-074930.md`
- Fix report：`docs/reviews/wu-cli-activity-01-followup-slice-4-fix-codex-20260618.md`
- MiMo review artifact：`docs/reviews/mimo-wu-cli-activity-01-followup-slice-4-20260618-074855.md`

## Re-review Scope

只验证 DS review（`20260618-074930`）中 Finding 1 的修复证据，以及 MiMo review 的对应 finding 状态变化。不重新 review 整个 Slice 4。

## Finding Status

### DS Finding 1：ConversationMemoryProjectionCatchupPort 违反设计计划命名约束和兼容性胶水禁令

**状态：已修复。**

逐项验证：

| 修复要求 | 证据 | 状态 |
|---------|------|------|
| 类从 `dayu/host/memory_repair.py` 删除 | `rg -n "class ConversationMemoryProjectionCatchupPort" dayu/host/memory_repair.py` → exit 1 | ✅ |
| 无 import/引用残留 | `rg -n "ConversationMemoryProjectionCatchupPort" dayu/ tests/` → exit 1 | ✅ |
| 无 catchup_port 命名残留 | `rg -n "catch.up_port\|CatchupPort\|_MemoryProjectionCatchupPort" dayu/host/memory_repair.py dayu/host/open_host.py dayu/host/dispatch.py` → exit 1 | ✅ |
| test_memory_repair.py 删除 delegation 测试 | `rg -n "test_catchup_port_delegates" tests/host/test_memory_repair.py` → exit 1 | ✅ |
| test_admission_queue.py 改为显式调用 | `tests/host/test_admission_queue.py:1025` — `start_run` 提交后显式调用 `catch_up_conversation_memory_projection(..., max_event_sequence=result.run.input_event_sequence)` | ✅ |
| test_toolruntime_accept_barrier.py 改为显式调用 | `tests/host/test_toolruntime_accept_barrier.py:663` — `accept_tool_fact` 提交后显式调用 `catch_up_conversation_memory_projection(..., max_event_sequence=result.tool_result_event_ref.event_sequence)` | ✅ |
| test_resolve_wait_command.py 改为显式调用 | `tests/host/test_resolve_wait_command.py:216` — resolve_wait 提交后显式调用 `catch_up_conversation_memory_projection(..., max_event_sequence=tool_events[-1].event_sequence)` | ✅ |
| 替换测试不注入 unbounded catch-up 到 after-commit port | 三个测试均先 commit，再显式调用带 `max_event_sequence` 的 catch-up；不再通过 `ProjectionCatchupPort` 注入无界 catch-up | ✅ |
| 无 Slice 5 改动 | `rg -n "Slice.5\|RunInputBuilder\|_MEMORY_EVENT_TYPES\|_is_memory_projection_row"` 在所有变更文件 → exit 1 | ✅ |
| 无 public Host/Engine contract 变更 | 仅删除内部 adapter 类；`dayu/host/__init__.py` 与 `dayu/host/api.py` 未修改 | ✅ |
| 剩余 `ProjectionCatchupPort` import（test_admission_queue、test_toolruntime_accept_barrier、test_resolve_wait_command）只用于 `_FailingProjectionCatchup` 测试替身，不涉及 conversation-memory catch-up | 已核查三个文件的 import 用途 | ✅ |
| 156 tests pass | `pytest ... -q` → 156 passed | ✅ |
| pyright clean | 0 errors, 0 warnings | ✅ |

### MiMo Finding 5：ConversationMemoryProjectionCatchupPort 保留为内部 hook ✓（可接受）

**状态：证据失效。**

MiMo review（`mimo-wu-cli-activity-01-followup-slice-4-20260618-074855.md`）Finding 验证第 5 条判定 `ConversationMemoryProjectionCatchupPort` 保留为内部 hook 可接受。该判定的直接证据——"该类仍在 `memory_repair.py:75` 定义"——在当前 workspace 中已不再成立：类已被删除，`rg -n "ConversationMemoryProjectionCatchupPort" dayu/ tests/` 返回 exit 1。

MiMo review 的其余 8 条验证（去预算化、after-commit 热路径、compact accepted 热路径、required repair target_reached、日志、README、测试覆盖、retry_repair_budget_exhausted）不受此 fix 影响，仍然有效。

## Residual Risk

- 与原 DS review 一致：Slice 3 依赖（`events_scanned` 语义）与 Slice 5 未实现仍属于后续 slice
- 三个测试文件中的 `ProjectionCatchupPort` import 仅用于 `_FailingProjectionCatchup` 测试替身，不构成 conversation-memory catch-up 注入风险
- 无新增风险

## Final Statuses

| 来源 | Finding | 裁决 | 状态 |
|------|---------|------|------|
| DS review | `ConversationMemoryProjectionCatchupPort` 违反设计计划命名约束和兼容性胶水禁令 | accepted | **已修复** |
| MiMo review | `ConversationMemoryProjectionCatchupPort` 保留为内部 hook 可接受 | 被 DS 裁决覆盖 | **证据失效** |
