# Host-owned Compactor Final Review Fix

## Scope

- 处理 MiMo final review artifact：`docs/reviews/host-owned-compactor-final-review-mimo-20260519-115936.md`
- 只处理 final review fix gate 指定的 Finding 001 与 Finding 002。
- 未提交、未 push。

## Finding 001

### Why Thread Timeout Was Dropped

上一版 `thread.join(timeout)` 只能给同步线程桥加等待上限，但没有消除根因：Host compactor 仍把 async Engine runner 包进同步 `compact()`，provider 挂起后仍会留下无法治理的后台线程，且同步调用链仍无法自然表达 cancellation / await / retry 边界。

因此该方向属于表面修复，本轮已移除。

### Root Cause

`ContextCompactor.compact()` 是同步 port，但真实 `LLMContextCompactor` 的下游是 async `run_agent_and_wait()`。为跨过这个类型错位，原实现引入 `_run_agent_request_sync()`、线程桥、`asyncio.run()` 与 `thread.join()`。Host governance 因此在 compaction proposal 阶段失去 async backpressure，runner 永久挂起时会阻塞或遗留后台执行。

### Fix

- `ContextCompactor.compact()` 改为 async typed port。
- `LLMContextCompactor.compact()` 直接 `await run_agent_and_wait(request)`，不再使用线程、`thread.join()`、`asyncio.run()` 或 sync wrapper。
- `run_compaction_operation()` 改为 async，并在 attempt loop 内 `await compactor.compact(request)`；proposal failure / retry / final failure 行为保持不变。
- proactive compaction 在 `HostDispatchScheduler.run_queue_promotion()` / `_run_pre_start_governance()` / `_execute_proactive_compaction()` async 链路中 await operation。
- `HostDispatchScheduler.wake_queue_promotion()` 仍保持同步 wakeup port，但只负责把 Session id 放入 scheduler-owned promotion queue，并启动受管理的 promotion drain task。
- promotion drain task 纳入 scheduler lifecycle：异常在 loop 内记录，close 时取消并等待该 task，避免裸 `asyncio.create_task(...)`、silent task exception 或 close 后遗留 promotion task。
- reactive compaction 通过 `EngineEventIngestor.ingest_async()` await operation；同步 `ingest()` 保留给不触发 reactive compaction 的既有路径，触发 reactive compaction 时要求调用 async 入口。
- `FakeContextCompactor` 与相关测试 compactor 全部迁移为 async compact。
- Service-facing public contract 保持不变：`OpenHostOptions` 仍只暴露 `CompactorRunnerBaseline`，Host 内部构造 `LLMContextCompactor`，没有恢复 Service 注入 `ContextCompactor`。

### Tests

- `tests/host/test_llm_compaction.py`
  - 覆盖 direct await fake async runner 成功、非 final / empty output、runner exception 失败路径。
  - 覆盖源码层不再包含 `threading`、`thread.join()` 或 `asyncio.run()`。
- `tests/host/test_compaction_operation.py`
  - 覆盖 async operation 在 proposal 第一次失败后 retry 并成功。
  - 覆盖 async operation 在 attempt budget 耗尽后失败。
- `tests/host/test_dispatch_scheduler.py`
  - 覆盖 proactive compaction async 链路仍保持原有调度行为。
  - 覆盖 sync `wake_queue_promotion()` 创建的 scheduler-owned promotion task 可完成 compact / promotion。
  - 覆盖 promotion task 内异常会记录 warning，且 task 不以 unhandled exception 结束。
  - 覆盖 scheduler close 会取消并等待 wakeup 创建的 promotion task。
- `tests/host/test_engine_ingest_mapping.py`
  - 覆盖 reactive compaction async 链路仍保持 recovery / failure 行为。

## Finding 002

### Root Cause

Host budget 决策语义是 `estimated_input_tokens >= hard_threshold_tokens` 时 hard block；`_budget_after_compact()` 用 `hard_threshold_tokens - 1` 保证 compact 后预算低于 hard block 边界。

因此 `hard_threshold_tokens == 1` 没有任何正整数预算可同时满足“低于 hard threshold”。根因是 policy / estimate 边界允许了不可调度阈值，而不是 compactor mapper 的局部算式错误。

### Fix

- 新增 `MIN_CONTEXT_HARD_THRESHOLD_TOKENS = 2`。
- `ContextBudgetPolicy` 拒绝显式 `hard_threshold_tokens < 2`。
- `ContextBudgetPolicy` 在未显式 hard threshold 时也校验 `input_budget_tokens - minimum_protection_tokens >= 2`。
- `BudgetEstimate` 同步拒绝 `hard_threshold_tokens < 2`，防止绕过 policy 构造不可调度 estimate。
- `dayu/host/README.md` 同步当前 async compactor 行为与 hard threshold 语义。

### Tests

- `tests/host/test_context_policy.py::test_context_budget_policy_rejects_non_dispatchable_hard_threshold`
- `tests/host/test_context_budget.py::test_budget_estimate_rejects_non_dispatchable_hard_threshold`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_context_policy.py tests/host/test_context_budget.py -q`
  - 32 passed
- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py -q`
  - 34 passed
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -q`
  - 38 passed
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q`
  - 72 passed
- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q`
  - 106 passed
- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py tests/host/test_active_cancel_dispatch.py tests/host/test_phase5_local_execution_integration.py tests/host/test_phase7_waiting_integration.py -q`
  - 35 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - passed

## Findings Not Handled

- Finding 003-007：未展开处理。它们是更大范围的 orchestration / reactive / event consistency 测试矩阵缺口，用户明确要求不要展开；本轮只补了 async operation retry/failure 的最小覆盖，避免回退既有 attempt loop 行为。
- Finding 008-013：未处理。当前 gate 明确只要求修复 Finding 001 与 Finding 002；其余低风险 README / lifecycle / 入口校验问题不属于本次 final review fix gate 的必须项。
