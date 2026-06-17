# Code Review — Re-review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/mimo-rereview-wu-cli-activity-01-followup-slice-4-20260618-075452.md`
- Included scope:
  - `dayu/host/memory_repair.py`
  - `dayu/host/open_host.py`
  - `dayu/host/dispatch.py`
  - `dayu/host/README.md`
  - `tests/host/test_memory_repair.py`
  - `tests/host/test_open_host_runtime.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `tests/host/test_logging.py`
  - `tests/host/test_toolruntime_accept_barrier.py`
  - `tests/host/test_resolve_wait_command.py`
  - `tests/host/test_admission_queue.py`
  - `docs/reviews/wu-cli-activity-01-followup-slice-4-fix-codex-20260618.md`
  - `docs/reviews/ds-wu-cli-activity-01-followup-slice-4-code-review-20260618-074930.md`
  - `docs/reviews/mimo-wu-cli-activity-01-followup-slice-4-20260618-074855.md`
- Excluded scope: Slice 1-3 / Slice 5 改动；Engine / Service / UI / Fins；durable schema
- Parallel review coverage: 无
- Design truth: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md` Slice 4

## DS Finding 验证

### 1-已修复-中-ConversationMemoryProjectionCatchupPort 违反设计计划命名约束和兼容性胶水禁令

- **DS review artifact**: `docs/reviews/ds-wu-cli-activity-01-followup-slice-4-code-review-20260618-074930.md`
- **Fix artifact**: `docs/reviews/wu-cli-activity-01-followup-slice-4-fix-codex-20260618.md`
- **Fix 裁决**: accepted
- **验证结果**: **已修复**

逐项验证：

1. **ConversationMemoryProjectionCatchupPort 类已删除** ✓
   - `grep -rn "ConversationMemoryProjectionCatchupPort" dayu/ tests/` 返回无匹配。
   - `dayu/host/memory_repair.py` 不再包含该类定义（原 75-120 行）。

2. **测试不再注入 unbounded catch-up 到 after-commit projection_catchup_port** ✓
   - `tests/host/test_toolruntime_accept_barrier.py`：`DefaultHostToolFactAcceptPort` 不再接收 `projection_catchup_port` 参数。
   - `tests/host/test_resolve_wait_command.py`：`create_host_admission_service` 不再传 `projection_catchup_port`。
   - `tests/host/test_admission_queue.py`：`_service()` 不再传 `projection_catchup` 参数。

3. **替换测试显式调用 catch_up_conversation_memory_projection** ✓
   - `test_tool_fact_accept_then_direct_memory_catchup_does_not_project_fact`：先 `accept_tool_fact`，再 `catch_up_conversation_memory_projection(..., max_event_sequence=result.tool_result_event_ref.event_sequence)`。
   - `test_resolve_wait_committed_tool_result_direct_catchup_without_fact`：先 `resolve_wait`，再 `catch_up_conversation_memory_projection(..., max_event_sequence=tool_events[-1].event_sequence)`。
   - `test_start_run_then_direct_memory_catchup_projects_user_input`：先 `start_run`，再 `catch_up_conversation_memory_projection(..., max_event_sequence=result.run.input_event_sequence)`。
   - 所有替换测试都传入 `max_event_sequence`，行为有界。

4. **无 Slice 5 变更** ✓
   - `dayu/host/run_input.py` 无变更。
   - `dayu/host/durable/memory.py` 无变更。
   - `memory_repair.py` 中无 `_MEMORY_EVENT_TYPES`、`_is_memory_projection_row`、`conversation_memory_projection_event_filter` 相关代码。

5. **无 public Host/Engine contract 变更** ✓
   - `ConversationMemoryProjectionCatchupPort` 从未出现在 `dayu/host/__init__.py` 导出中。
   - `memory_repair.py` 保留的 public 函数 `rebuild_conversation_memory_projection` 和 `catch_up_conversation_memory_projection` 签名不变（budget 参数在之前实现中已删除）。

6. **测试通过、pyright 无错误** ✓
   - 160 passed（包含新增的 4 个受影响测试文件）。
   - pyright 0 errors, 0 warnings。

## MiMo Review 状态更新

### 原 MiMo review finding: ConversationMemoryProjectionCatchupPort 保留为内部 hook 可接受

- **原 artifact**: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-4-20260618-074855.md`
- **原判定**: 保留可接受，不违反热路径约束
- **更新状态**: **证据失效**

原因：MiMo 原 finding 基于"热路径已断开、类保留为内部 hook 风险低"的证据链。DS review 指出该类违反 Slice 4 设计计划的显式约束（line 336-337: "若保留，只能暴露 maintenance 语义，不得命名为 catch-up port；否则删除该 port"）和 CLAUDE.md 兼容性胶水禁令。用户裁决采纳 DS finding，Codex 已删除该类。原 MiMo finding 的证据基础（类存在但不在热路径中）已不成立——类已不存在。

### MiMo 原 finding 2-9 状态

原 MiMo review 的 finding 2-9（memory repair 去预算化、open_host after-commit、dispatch compact accepted、dispatch required repair、日志、README、测试覆盖、retry_repair_budget_exhausted）验证结果不受本 fix 影响，状态仍为 **未发现实质性问题**。

## 最终状态汇总

| 来源 | Finding | 状态 |
|------|---------|------|
| DS | ConversationMemoryProjectionCatchupPort 违反命名约束和兼容性禁令 | **已修复** |
| MiMo | ConversationMemoryProjectionCatchupPort 保留为内部 hook 可接受 | **证据失效** |
| MiMo | memory repair 去预算化 | **未发现实质性问题** |
| MiMo | open_host after-commit 不注入 memory catch-up | **未发现实质性问题** |
| MiMo | dispatch compact accepted 不执行 memory catch-up | **未发现实质性问题** |
| MiMo | dispatch required repair 仍要求 target_reached | **未发现实质性问题** |
| MiMo | 日志无 budget_exhausted 噪音 | **未发现实质性问题** |
| MiMo | README 匹配当前代码 | **未发现实质性问题** |
| MiMo | 测试覆盖充分 | **未发现实质性问题** |
| MiMo | retry_repair_budget_exhausted 不属于本 slice | **未发现实质性问题** |

## Residual Risk

- Slice 5（RunInputBuilder inline repair filter 共源化）未实现，属于后续 slice。
- `retry_repair_budget_exhausted` 命名不在本 slice 重命名范围内。
- 替换测试中 `catch_up_conversation_memory_projection` 的 `max_event_sequence` 参数来自 commit 后的 event sequence，确保 catch-up 有界；这比原 port 注入方式更明确、更安全。
