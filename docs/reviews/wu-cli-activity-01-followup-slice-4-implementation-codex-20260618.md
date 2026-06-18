# WU-CLI-ACTIVITY-01 follow-up Slice 4 implementation

## 元数据

- Work unit：`WU-CLI-ACTIVITY-01 follow-up`
- Slice：4，Conversation Memory repair 去预算化并迁移调用方
- 日期：2026-06-18
- 实施者：Codex
- Accepted plan：`docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- Artifact：`docs/reviews/wu-cli-activity-01-followup-slice-4-implementation-codex-20260618.md`

## Scope

本 slice 只移除 Conversation Memory projection correctness 语义预算，并确保 open_host after-commit 与 dispatch compact accepted 热路径不执行无界 required catch-up。

未修改 Host / Engine public API/contracts，未修改 durable schema，未实现 Slice 5 的 RunInputBuilder inline repair / filter 共源化。

## Changed Files

- `dayu/host/memory_repair.py`
  - 删除 `MemoryProjectionCatchupBudget`、`MemoryProjectionRepairPurpose` 与 `MemoryProjectionRepairStopReason.BUDGET_EXHAUSTED`。
  - `ConversationMemoryProjectionRepairResult` 删除 `budget_exhausted`、`max_batches`、`max_scanned_events`，保留 cursor、计数、failure、target 与 page loop 汇总字段。
  - `catch_up_conversation_memory_projection(...)` 与 `rebuild_conversation_memory_projection(...)` 删除 `budget` 参数。
  - `_run_memory_projection_until_stop(...)` 使用 `batch_size` 作为 page size，循环直到 target reached、idle 或 failure。
  - memory repair 日志删除 budget purpose / exhausted / max batch / max scanned fields。

- `dayu/host/open_host.py`
  - 删除 opener 内部 `_MemoryProjectionCatchupPort` 与 after-commit memory budget helper。
  - scheduler 与 admission service 的 after-commit projection port 不再注入 conversation-memory catch-up。
  - opener close cleanup 仍保留 audit、tool trace、outbox projection catch-up。

- `dayu/host/dispatch.py`
  - 删除 compact accepted 后的 opportunistic memory catch-up budget helper 与同步 catch-up 调用。
  - compact accepted 后只记录 diagnostic 并启动 governed attempt；worker accept 前 required catch-up 仍负责 correctness。
  - dispatch required repair / rebuild 调用不再传 `budget=None`。
  - repair-not-reached warning 删除 `budget_exhausted`、`max_batches`、`max_scanned_events` 字段。

- `tests/host/test_memory_repair.py`
  - 删除预算耗尽断言，改为覆盖 page size=1 多页追到 idle / target。
  - 覆盖 rebuild 多页追到 target、failure 立即停止、真实 durable store page size=1 追到 idle。
  - 更新 `ConversationMemoryProjectionCatchupPort` 测试为无 budget 参数。

- `tests/host/test_open_host_runtime.py`
  - 删除旧 `_MemoryProjectionCatchupPort` / budget 断言。
  - 新增 open_host after-commit 不向 scheduler 注入 conversation-memory catch-up port 的断言。
  - dispatch 前 required memory catch-up 集成测试保留。

- `tests/host/test_dispatch_scheduler.py`
  - 删除旧 `budget` 参数测试替身。
  - 新增 compact accepted queue promotion 不调用 `catch_up_conversation_memory_projection(...)` 的断言。
  - dispatch required repair 仍断言 target reached 后才能继续 worker accept。

- `tests/host/test_logging.py`
  - 删除旧 memory catch-up budget log 字段断言。

- `dayu/host/README.md`
  - 同步 opener 当前装配事实：after-commit 热路径不执行 conversation-memory catch-up。
  - 明确 memory catch-up batch size 是 page size，不是 correctness stop budget。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_logging.py -q`
  - 96 passed
- `source .venv/bin/activate && python -m pyright dayu/host/memory_repair.py dayu/host/open_host.py dayu/host/dispatch.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_logging.py`
  - 0 errors, 0 warnings
- `git diff --check`
  - passed
- `rg -n "MemoryProjectionCatchupBudget|MemoryProjectionRepairPurpose|MemoryProjectionRepairStopReason\.BUDGET_EXHAUSTED|\bbudget_exhausted\b" dayu/host/memory_repair.py dayu/host/open_host.py dayu/host/dispatch.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_logging.py`
  - no matches
- `rg -n "MemoryProjectionCatchupBudget|MemoryProjectionRepairPurpose|MemoryProjectionRepairStopReason\.BUDGET_EXHAUSTED" dayu tests`
  - no matches
- `rg -n "catch_up_conversation_memory_projection\([^\n]*budget=|rebuild_conversation_memory_projection\([^\n]*budget=" dayu tests`
  - no matches

## README Decision

已按 AGENTS.md 阅读 `dayu/host/README.md` 与 `tests/README.md` 更新约束。

- `dayu/host/README.md` 需要更新，因为 open_host 当前已不再装配 conversation-memory after-commit catch-up port，且 `memory_projection_catchup_batch_size` 的 page size 语义属于 Host 开发者稳定边界。
- `tests/README.md` 不需要更新；新增 / 修改测试仍落在既有 Host memory repair、dispatch scheduler 与 logging 测试分层中，没有新增测试层级或运行方式。

## Residual Risks

- fixed in current slice：Conversation Memory required catch-up / rebuild 不再因 max batch / max scanned semantic budget 提前停止。
- fixed in current slice：open_host command/admission after-commit 热路径不再执行 conversation-memory catch-up。
- fixed in current slice：dispatch compact accepted hot path 不再执行同步 memory catch-up；required correctness 仍在 worker accept 前校验 target reached。
- fixed in current slice：memory repair logs/tests 不再暴露 semantic budget fields。
- covered by later approved slice：RunInputBuilder inline repair 与 durable projection filter/read 共源化仍属于 Slice 5，本 slice 未实现。
- assigned to later work unit：`retry_repair_budget_exhausted` 是 Context Governance / compaction payload 字段，不是 memory projection repair budget，本 slice 未重命名或删除。

## Completion Status

Slice 4 implementation complete。未修改 Host / Engine public API/contracts；未实现 Slice 5；awaiting code review gate。
