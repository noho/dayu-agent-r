# AgentDS P5-S6 Integration, Docs And Validation Closeout — Code Review

- **reviewer**: AgentDS
- **artifact path**: `docs/reviews/gateflow-code-review-host-p5-s6-integration-docs-validation-ds-20260515.md`
- **design source**: `docs/host/design.md`
- **control doc**: `docs/host/implementation-control.md`
- **plan**: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S6
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p5-s6-integration-docs-validation-20260515.md`
- **scope**: P5-S6 allowed files + controller-approved controlled scope expansions (`dayu/host/dispatch.py`, `tests/host/test_admission_queue.py`, `tests/host/test_durable_schema.py`, `tests/host/test_run_attempt_transitions.py`)

---

## Findings

### F1 — dispatch.py worker event stream closeout 逻辑正确 (PASS)

**Evidence**: `dayu/host/dispatch.py:_consume_worker_events` (lines 794–878)

| 路径 | 实现 | 结论 |
|---|---|---|
| clean EOF (StopAsyncIteration) | `terminal_seen` 为 True 时直接 break；否则调用 `ingestor.close_clean_eof()` 收口 FAILED | PASS |
| stream exception | `except Exception` 调用 `ingestor.close_worker_lost()` 收口 LOST，`stream_error_code=exc.__class__.__name__` | PASS |
| `asyncio.CancelledError` | `except asyncio.CancelledError: raise`，透传给 scheduler close / task cancel 语义 | PASS |
| terminal_seen 设置 | `result.terminal_closeout == True` 且 `result.status in (ACCEPTED, DUPLICATE)` 时设为 True | PASS |
| duplicate terminal | `_with_terminal_promotion_retry` 对 DUPLICATE 也触发 promotion wakeup；不会导致二次 closeout | PASS |
| late rejected event (terminal 后迟到) | `_late_rejection_reason` 在 `run.terminal_event_id is not None or attempt.terminal_event_id is not None` 时返回 REJECTED diagnostic；不触发二次 closeout | PASS |
| lane release / unregister / handle.close | 均在 `finally` 块中执行（lines 871–878） | PASS |

`_late_rejection_reason` (engine_ingest.py:1132-1144) 的守卫逻辑正确：一旦 `run.terminal_event_id` 或 `attempt.terminal_event_id` 已设置，迟到事件返回 `REJECTED` diagnostic，不会进入 `_ingest_validated` 产生新的 terminal closeout。`_duplicate_terminal_event_ids` (engine_ingest.py:1236) 稳定派生出可能已写入的 event id 集合用于去重。

**结论**: 六类收口路径全部正确实现，无 error double closeout、无 missing closeout、lane release owner 仍在 finally。

### F2 — P5-S6 public start_run + scheduler + fake worker 测试真实覆盖生产路径 (PASS)

**Evidence**: `tests/host/test_phase5_local_execution_integration.py`

| 测试用例 | 覆盖场景 | 生产路径 |
|---|---|---|
| `test_start_run_fake_worker_final_answer_succeeds` | final_answer -> SUCCEEDED | `start_run()` public facade → `HostDispatchScheduler.open()` → `wake_dispatch()` → `drain_once()` → worker accept → event stream → `close_clean_eof`/ingest → terminal closeout |
| `test_start_run_fake_worker_run_failed_fails` | run_failed -> FAILED | 同上，fake worker 产出 `EngineEventType.RUN_FAILED` |
| `test_start_run_fake_worker_clean_eof_fails` | clean EOF no terminal -> FAILED | 同上，fake worker 产出空 stream → `close_clean_eof` |
| `test_start_run_fake_worker_crash_loses` | worker stream crash -> LOST | 同上，fake worker 在 `events()` 中 raise `RuntimeError` |
| `test_cancel_active_fake_worker_closes_cancelled` | active cancel -> CANCELLED | `cancel_run()` public facade → active registry cancel → fake worker 收到 cancel → 产出 `RUN_CANCELLED` → ingest → terminal closeout |
| `test_queue_promotion_after_terminal_and_cancel_wakes_dispatch` | queue promotion after terminal/cancel | 两个子场景：terminal (final_answer) promotion 与 cancel promotion，均验证 promoted RUNNING → SUCCEEDED |

所有集成测试均通过 `HostDispatchScheduler.open()` 打开真实 scheduler、通过 runtime lane DB 做 capacity control、通过 `_SequencedLocalWorkerFactory` 注入 fake worker、通过 `drain_once()` 同步消费。fake worker (`_ScriptedLocalWorkerHandle`) 实现 `LocalWorkerHandle` 协议，只通过 `events()` / `cancel()` / `close()` / `local_worker_id` 与生产代码交互，不绕过 scheduler 直接改 durable 状态。

`_ScriptedLocalWorker.accept()` (line 336) 还额外断言 `request.disable_tools is True` 和 `request.tool_schemas == ()`，确保 RunInputBuilder 的 no-tool 边界在生产路径中被遵守。

**结论**: 六条端到端路径真实覆盖，fake worker 不绕过生产边界。

### F3 — import boundary tests 分层正确，不会过窄误杀，也不会漏掉反向依赖 (PASS)

**Evidence**: `tests/host/test_import_boundary.py`

| 测试 | 断言 | 结论 |
|---|---|---|
| `test_host_does_not_import_upper_or_business_layers` | Host 不 import `dayu.fins` / `dayu.service` / `dayu.ui` | PASS，AST 扫描所有 `dayu/host/*.py` |
| `test_host_engine_imports_stay_on_allowed_boundary_modules` | 只有 `api.py`, `dispatch.py`, `engine_ingest.py`, `local_proxy.py`, `run_input.py` 可 import `dayu.engine` | PASS，allowlist 对应 plan 中 P5-S3/S4 允许的边界模块 |
| `test_runtime_does_not_import_host_or_engine_layers` | `dayu.runtime` 不 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` | PASS |
| `test_engine_does_not_import_host_layer` | `dayu.engine` 不 import `dayu.host` | PASS |
| `test_host_request_dataclasses_do_not_carry_tool_bundle` | per-run request dataclass 无 `business_tool_bundle` 字段 | PASS |

分析 allowlist 的合理性：
- `api.py`：定义 `HostLocalExecutionOptions`、`LocalWorkerHandle`、`LocalEngineWorker`、`LocalEngineWorkerFactory` 等 Phase 5 本地执行配置契约，需要引用 Engine contract 类型
- `dispatch.py`：scheduler 在 `_start_worker` 中调用 `create_no_tool_run_input_builder` 构造 `AgentRunRequest`
- `engine_ingest.py`：ingest 需要映射 `EngineEvent` / `EngineEventType` 到 Host event
- `local_proxy.py`：LocalProxy 默认 worker 调用 `dayu.engine.run_agent_messages`
- `run_input.py`：RunInputBuilder 构造 `AgentRunRequest` 等 Engine public contract 对象

不在 allowlist 中的 Host 模块（如 `command.py`、`admission.py`、`durable/` 等）通过 `dayu.host.api` 的类型重导出使用 Engine 类型，不直接 import `dayu.engine`。这符合分层：Host 内部模块通过 Host 自有 API 层间接消费 Engine 类型。

**结论**: import boundary tests 正确区分了合法 Host→Engine 边界依赖与非法反向依赖，allowlist 覆盖了 plan 明确允许的模块，同时不会误杀。

### F4 — 旧 Phase 3 测试迁移只更新过时真源断言，没有掩盖真实回归 (PASS)

**Evidence**: 三个受控范围扩展文件

**`tests/host/test_durable_schema.py`**:
- `test_fresh_db_creates_foundation_and_phase5_tables`：`user_version` 断言从 `2` 迁移到 `3`，同步 `HOST_SCHEMA_VERSION == 3`。仅此一处变更。PASS。

**`tests/host/test_admission_queue.py`**:
- `test_cancel_terminal_run_returns_current_terminal_without_new_facts`：旧断言 `invalid_state` 改为验证返回当前 terminal result、没有 `promotion`/`active_cancel_target`、不追加新 canonical facts。这与 Phase 5 的 `cancel_run` idempotent replay 语义一致：terminal Run 的后续 cancel 返回当前 snapshot，不修改 durable state。
- `test_cancel_attempt_running_enters_cancelling_with_cancel_facts`：旧断言 `invalid_state` 改为验证 Run 进入 `CANCELLING`、追加 `CANCEL_REQUESTED` + `RUN_CANCELLING`、返回 `active_cancel_target`。这与 Phase 5 的 active worker cancel 语义一致：Attempt RUNNING（worker 已 accept）时 cancel 应推进 CANCELLING 并传播取消。测试使用 `_force_attempt_status` 构造 Attempt RUNNING 前置条件（模拟 Phase 5 生产路径中 worker accept 后的状态），`_force_attempt_status` 的 docstring 明确标注 "Phase 3 unsupported state"，表明这是为测试构造前置条件而非修改生产代码。PASS。

**`tests/host/test_run_attempt_transitions.py`**:
- `test_terminal_closeout_accepts_attempt_running_in_phase5`：旧断言 `INVALID_STATE` 改为验证 `UPDATED` + `AttemptStatus.SUCCEEDED`。这与 Phase 5 的 `terminal_closeout_in_transaction` 支持 `RUNNING` Attempt 关闭的语义一致。测试同样使用 `_force_attempt_status` 强制设置 Attempt RUNNING。PASS。

所有三处变更都只是更新 test expectation 以匹配 Phase 5 新增支持的状态机路径；没有修改生产代码来迎合测试，也没有保留旧兼容逻辑。

**结论**: 旧测试迁移是纯粹的断言真源更新，不存在掩盖回归的风险。

### F5 — README 只写当前能力和 deferred owner，不写未来设计 (PASS)

**Evidence**: `dayu/host/README.md`, `tests/README.md`

**`dayu/host/README.md`**:
- Durable Foundation 段 (line 93-96) 以现在时描述 Phase 5 dispatch scheduler / LocalProxy baseline、RunInputBuilder no-tool boundary、EngineEvent ingest mapping，均为已实现能力。
- "当前未实现" 段 (line 147-148) 与 "Internal Admission" 未实现段 (line 116-117) 以 deferred owner 格式列出：policy provider set、RemoteProxy、wait cancellation、recovery classifier、lease/fencing/takeover、artifact cleanup scheduler、ToolRuntime 等。没有描述这些能力的未来行为。
- 没有 "未来会实现"、"计划支持"、"即将"等未来时态表述。

**`tests/README.md`**:
- Phase 5 本地执行集成测试 strata (line 87) 描述当前已存在的测试事实：public `start_run` + 真实 scheduler + runtime lane + fake local worker 覆盖 no-tool 闭环。
- fake worker 约定 (line 87): "fake worker 必须只通过 LocalEngineWorkerFactory / LocalWorkerHandle 边界产出 Engine public EngineEvent 或模拟 clean EOF / stream crash；测试断言 Host durable Run / Attempt 终态...不绕过 scheduler 直接改生产状态。" 这是当前约定，不是未来设计。
- 没有未来测试计划或未落地测试体系描述。

**`dayu/README.md`**: implementation artifact 报告已检查，未修改（当前总览没有把 RunInputBuilder/LocalProxy 描述成未来能力）。

**根 `README.md`**: 未修改（无新增 CLI/配置入口/用户运行方式）。

**结论**: README 同步符合触发规则和只写当前能力的约束。

### F6 — 完整 validation 334 passed、pyright 0 errors、diff check 可信 (PASS)

**Evidence**: implementation artifact 报告的 validation results

```
source .venv/bin/activate && pytest tests/host tests/runtime -q
# 334 passed

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# 0 errors, 0 warnings, 0 informations

git diff --check
# passed
```

Validation 覆盖范围与 plan 一致：
- `tests/host` + `tests/runtime` — 覆盖 Host 全部测试层与 Runtime lane 测试
- `pyright dayu/host tests/host` — 覆盖 Host 生产代码与测试的类型检查
- `pyright dayu/ tests/ utils/` — 全量类型检查
- `git diff --check` — 无空白冲突

实施过程中的旧测试迁移已验证通过（4 passed for controlled scope expansion tests）。所有数字来自 gate artifact 记录。

**结论**: validation 范围完整、结果一致、可信。

---

## Additional Observations (Non-blocking)

### O1 — `_HostCancellationToken` 使用 `threading.RLock` 在 async context 中 (LOW)

`dayu/host/dispatch.py:_HostCancellationToken` (lines 208–258) 使用 `threading.RLock()` 做同步。在 async context 中，若 lock 被竞争，理论上会阻塞 event loop。实际风险极低：
- lock 临界区极短（设置/读取几个字段）
- 只有一个 writer（cancel path）和一个 reader（worker check path）
- 竞争窗口极小

建议在未来 lifecycle hardening (Phase 11) 中评估是否需要替换为 `asyncio.Lock`，但不构成 Phase 5 blocking issue。

### O2 — Fake worker crash 通过同步 `RuntimeError` 模拟 (OBSERVATION)

`_ScriptedLocalWorkerHandle.events()` 在 `_WORKER_MODE_CRASH` 模式下直接 `raise RuntimeError("fake worker crash")`（line 256）。这个 raise 发生在 async generator 的第一次 `yield` 之前，被 `_consume_worker_events` 的 `except Exception` 捕获。这正确模拟了 "worker stream 在产生事件前崩溃" 的场景。但如果要测试 "worker 在产生若干事件后崩溃"，当前的 fake worker 设计不支持。这不影响 Phase 5 覆盖目标——stream error 的 ingress 路径已被 `close_worker_lost` 低层测试覆盖。

### O3 — `_active_handles` 与 `_active_tasks` 的双轨维护 (OBSERVATION)

`dispatch.py:_start_worker` (lines 649–651) 同时维护 `self._active_handles` 和 `self._active_tasks`。handle 的 discard 发生在 `_consume_worker_events` 的 finally 中，task 的 discard 通过 `task.add_done_callback(self._active_tasks.discard)` 自动完成。`close()` 方法在关闭时遍历 `_active_handles` 的 tuple 副本，cancel 每个 handle。由于 `_suppress_task_cancel(task)` 会等待 drain task 完成（从而等待其内部的 finally 清理），如果 drain task 仍在处理某个 handle，close 后的 `for handle in tuple(self._active_handles)` 可能重复 cancel 已释放的 handle。但 `LocalWorkerHandle.cancel()` 和 `.close()` 预期是幂等的，所以这不会造成问题。

---

## Required Fixes

无。所有六项重点审查均通过，未发现 blocking issue。

---

## Residual Risks

1. **真实 provider runner 的 provider API smoke** — 不在 Phase 5 必测范围。当前以 fake local worker 和 Engine public event contract 覆盖 Host state machine。如果真实 `dayu.engine.run_agent_messages` 的事件流行为与 fake worker 假设不一致，可能需要 Phase 6 补齐 smoke 测试。

2. **`_HostCancellationToken` async safety** — 当前 `threading.RLock` 在 async context 中的理论风险极低，但建议在 Phase 11 lifecycle hardening 中评估。

3. **`cancel_session_runs` active cancel 的 worker 幂等再传播** — `DEFAULT_ACTIVE_WORKER_REGISTRY.cancel()` 对已 unregister 的 worker 返回 False，对 `handle.cancel()` 抛出的 `RuntimeError` 做 swallow。当 worker 在 cancel 传播途中完成 terminal closeout 并 unregister 时，这个行为是正确的。但如果未来引入 handle.cancel() 的更多异常类型，需要考虑是否也需要 swallow。

4. **多进程 orphan proof 与 restart recovery** — 由 Phase 11 负责，Phase 5 不做防呆。进程崩溃后 `dispatching + Attempt STARTING` 的 recovery classification 尚未实现。

5. **ToolRuntime / fetch_more** — Phase 6；**WAITING / resolve_wait** — Phase 7；**Memory** — Phase 9；**Context Governance** — Phase 10；**Recovery** — Phase 11；**Observer / Sink** — Phase 13；**RemoteProxy** — Phase 14。

---

## Verdict

**PASS** — P5-S6 Integration, Docs And Validation Closeout 通过 DS code review。

六项重点审查全部通过：
1. dispatch.py 六类 worker event stream closeout 路径正确，lane release owner 仍在 finally。
2. P5-S6 集成测试真实覆盖 public start_run + scheduler + fake worker 的六条端到端路径。
3. import boundary tests 分层正确，allowlist 覆盖合法 Host→Engine 边界且不误杀。
4. 旧 Phase 3 测试迁移只更新过时真源断言，无回归掩盖。
5. README 只写当前能力和 deferred owner。
6. 334 passed + pyright 0 errors + git diff --check 完整可信。

无 blocking fix。Residual risks 均为已明确 deferred owner 的后续 phase 范围。
