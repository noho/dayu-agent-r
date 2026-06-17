# WU-CLI-ACTIVITY-01 follow-up Slice 4 review fix

## 元数据

- Work unit：`WU-CLI-ACTIVITY-01 follow-up`
- Slice：4 review fix
- 日期：2026-06-18
- 实施者：Codex
- Accepted plan：`docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- Implementation artifact：`docs/reviews/wu-cli-activity-01-followup-slice-4-implementation-codex-20260618.md`
- DS review artifact：`docs/reviews/ds-wu-cli-activity-01-followup-slice-4-code-review-20260618-074930.md`
- MiMo review artifact：`docs/reviews/mimo-wu-cli-activity-01-followup-slice-4-20260618-074855.md`
- Fix artifact：`docs/reviews/wu-cli-activity-01-followup-slice-4-fix-codex-20260618.md`

## Finding 裁决

- DS finding：`ConversationMemoryProjectionCatchupPort` 保留为可注入 unbounded conversation-memory catch-up adapter，违反 Slice 4 hot-path 约束与兼容性胶水禁令。
  - 裁决：accepted。
  - 状态：已修复。
- MiMo finding：`ConversationMemoryProjectionCatchupPort` 保留为内部 hook 可接受。
  - 裁决：被本轮用户裁决覆盖；不采纳保留方案。
  - 状态：证据失效。

## Fix Scope

本 fix 只删除 `ConversationMemoryProjectionCatchupPort` 及直接测试引用。不修改 Host / Engine public API/contracts，不修改 durable schema，不实现 Slice 5 RunInputBuilder inline repair / filter 共源化。

## Changed Files

- `dayu/host/memory_repair.py`
  - 删除 `ConversationMemoryProjectionCatchupPort` 类，避免留下可被手动注入 after-commit `ProjectionCatchupPort` 的 unbounded memory catch-up adapter。

- `tests/host/test_memory_repair.py`
  - 删除 `ConversationMemoryProjectionCatchupPort` delegation 测试。

- `tests/host/test_toolruntime_accept_barrier.py`
  - 删除 direct import / 构造。
  - 原 concrete memory catch-up 测试改为：工具事实先正常 commit，再由测试显式调用 `catch_up_conversation_memory_projection(...)` 验证 memory projection 行为。

- `tests/host/test_resolve_wait_command.py`
  - 删除 direct import / 构造。
  - 原 resolve_wait concrete memory catch-up 测试改为：resolve_wait 先提交工具结果，再由测试显式调用 `catch_up_conversation_memory_projection(...)` 验证 cursor 覆盖。

- `tests/host/test_admission_queue.py`
  - 删除 direct import / 构造。
  - 原 start_run concrete memory catch-up 测试改为：start_run 先提交用户输入，再由测试显式调用 `catch_up_conversation_memory_projection(...)` 验证用户输入被投影。

## Validation

- `rg -n "ConversationMemoryProjectionCatchupPort" dayu tests`
  - no matches
- `source .venv/bin/activate && pytest tests/host/test_memory_repair.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py -q`
  - 156 passed
- `source .venv/bin/activate && python -m pyright dayu/host/memory_repair.py tests/host/test_memory_repair.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py`
  - 0 errors, 0 warnings
- `git diff --check`
  - passed

## README Decision

本 fix 未新增 Host public 行为或测试分层，只删除已裁决为不应保留的 adapter。Slice 4 implementation 中已同步 `dayu/host/README.md` 的 opener / memory page size 语义；本 fix 不需要进一步修改 README。

## Residual Risks

- fixed in current fix：不再存在 `ConversationMemoryProjectionCatchupPort` 可供 after-commit hot path 注入。
- fixed in current fix：已知四个测试文件不再直接 import / 构造该 adapter。
- covered by later approved slice：RunInputBuilder inline repair 与 durable projection filter/read 共源化仍属于 Slice 5，本 fix 未实现。
- assigned to later work unit：历史 review artifacts 中仍可能提到旧类名；它们是历史记录，不参与代码 / 测试验证。

## Completion Status

Slice 4 review fix complete。DS finding 已修复；无 Host / Engine public API/contracts 变更；未实现 Slice 5。
