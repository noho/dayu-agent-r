# Code Review: Host Phase 5 P5-S6 Integration, Docs And Validation Closeout

- **reviewer**: AgentMiMo
- **date**: 2026-05-15
- **scope**: P5-S6 allowed files + controller-approved controlled scope expansions (`dayu/host/dispatch.py`, `tests/host/test_admission_queue.py`, `tests/host/test_durable_schema.py`, `tests/host/test_run_attempt_transitions.py`)
- **design doc**: `docs/host/design.md`
- **control doc**: `docs/host/implementation-control.md`
- **plan**: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S6
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p5-s6-integration-docs-validation-20260515.md`

## Findings

### F1. dispatch.py worker event stream 四类收口 — PASS

**Evidence**: `dayu/host/dispatch.py:829-878`

四类收口路径已正确实现：

1. **terminal EngineEvent 已 accepted / duplicate**（L869-870）：`terminal_seen = True`，后续 `StopAsyncIteration` 时不调用 `close_clean_eof`。✓
2. **clean EOF 且未见 terminal**（L834-840）：`StopAsyncIteration` 时 `if not terminal_seen` 调用 `ingestor.close_clean_eof`。✓
3. **worker stream 异常**（L844-852）：`except Exception as exc`（排除 `CancelledError`）调用 `ingestor.close_worker_lost`。✓
4. **CancelledError 透传**（L842-843）：`except asyncio.CancelledError: raise`。✓

**late rejected event**：`_close_terminal` 内 `_late_rejection_reason`（`engine_ingest.py`）在 terminal 已关闭后返回 diagnostic，不会二次 closeout。✓

**duplicate terminal**：`_duplicate_terminal_result` 在 terminal 已提交后返回 `DUPLICATE` + `promotion_triggered`。✓

**finally 路径**（L872-878）：lane token release、active registry unregister、handle.close 均在 finally 中。✓

### F2. P5-S6 e2e tests 真实覆盖生产路径 — PASS

**Evidence**: `tests/host/test_phase5_local_execution_integration.py`

六个 e2e 测试均通过 public `start_run` + real `HostDispatchScheduler` + runtime lane + fake local worker 路径：

| 测试 | 路径 | 终态 | 验证 |
|------|------|------|------|
| `test_start_run_fake_worker_final_answer_succeeds` | public start_run → scheduler drain → fake worker final_answer | Run SUCCEEDED, Attempt SUCCEEDED | ✓ |
| `test_start_run_fake_worker_run_failed_fails` | public start_run → scheduler drain → fake worker run_failed | Run FAILED, Attempt FAILED | ✓ |
| `test_start_run_fake_worker_clean_eof_fails` | public start_run → scheduler drain → fake worker clean EOF | Run FAILED, Attempt FAILED, RUN_FAILED×1 | ✓ |
| `test_start_run_fake_worker_crash_loses` | public start_run → scheduler drain → fake worker crash | Run LOST, Attempt LOST, RUN_LOST×1 | ✓ |
| `test_cancel_active_fake_worker_closes_cancelled` | public start_run → scheduler drain → cancel_run → fake worker run_cancelled | Run CANCELLED, Attempt CANCELLED | ✓ |
| `test_queue_promotion_after_terminal_and_cancel_wakes_dispatch` | public start_run × 2 → terminal / cancel → promoted dispatch | 2× ATTEMPT_RUNNING | ✓ |

所有测试不绕过 scheduler、不直接改生产状态。fake worker 通过 `LocalEngineWorkerFactory` / `LocalWorkerHandle` 边界产出 `EngineEvent`。✓

低层 `EngineEventIngestor` lifecycle closeout 测试（`test_clean_eof_without_terminal_closes_failed`、`test_stream_error_or_worker_crash_closes_lost`、`test_run_cancelled_after_active_cancel_closes_cancelled`）同步保留。✓

### F3. import boundary tests — PASS

**Evidence**: `tests/host/test_import_boundary.py`

| 测试 | 约束 | 结果 |
|------|------|------|
| `test_host_does_not_import_upper_or_business_layers` | Host 不 import Fins/Service/UI | ✓ |
| `test_host_engine_imports_stay_on_allowed_boundary_modules` | Host 只有 api/dispatch/engine_ingest/local_proxy/run_input 可 import Engine | ✓ |
| `test_runtime_does_not_import_host_or_engine_layers` | Runtime 不 import Host/Engine/Service/UI/Fins | ✓ |
| `test_engine_does_not_import_host_layer` | Engine 不 import Host | ✓ |

边界宽度合理：`HOST_ENGINE_CONTRACT_ALLOWED_MODULES` 包含 5 个模块，覆盖本地执行边界需求，不过窄误杀合法 contract boundary。`dispatch.py` 通过 `engine_ingest.py` 间接使用 Engine types，不直接 import `dayu.engine`。✓

### F4. 旧 Phase 3 测试迁移 — PASS

**Evidence**:

- `test_durable_schema.py:103`：`user_version` 期望从 2 迁移为 3，`HOST_SCHEMA_VERSION == 3`。这是 schema version bump 的正确同步。
- `test_admission_queue.py:914-995`：
  - `test_cancel_terminal_run_returns_current_terminal_without_new_facts`：terminal Run cancel 返回当前终态、`active_cancel_target is None`、不追加事件。符合 Phase 5 "terminal 已提交时 cancel 返回当前 Run snapshot" 设计。
  - `test_cancel_attempt_running_enters_cancelling_with_cancel_facts`：Attempt RUNNING cancel 进入 `CANCELLING`、追加 `CANCEL_REQUESTED` + `RUN_CANCELLING`、返回 `active_cancel_target`。符合 Phase 5 active cancel 设计。
- `test_run_attempt_transitions.py:470-523`：`test_terminal_closeout_accepts_attempt_running_in_phase5`：Attempt RUNNING terminal closeout 收口为 SUCCEEDED。Phase 3 只允许 STARTING closeout，Phase 5 扩展支持 RUNNING。

所有迁移只更新过时断言，没有为迎合旧测试修改生产代码。✓

### F5. README — PASS

**Evidence**: `dayu/host/README.md`、`tests/README.md`

**dayu/host/README.md**：
- 当前能力描述已更新：RunInputBuilder no-tool boundary、LocalProxy / fake worker semantic baseline、dispatch record 四状态、active cancel 子集、scheduler worker stream EOF / crash closeout。✓
- deferred owner 已保留：ToolRuntime、WAITING / wait cancellation、RemoteProxy、Recovery、policy provider set、projection / audit / outbox。✓
- 无未来设计描述。✓
- 无旧术语残留（旧 "未实现" 表述已清理）。✓

**tests/README.md**：
- 已新增 Phase 5 本地执行集成测试 strata、运行命令和 fake local worker 约定。✓
- 只写当前事实。✓

**dayu/README.md**：implementation artifact 声称已检查、当前总览无需修改。✓

### F6. validation 可信度 — PASS

**Evidence**: 现场验证

```bash
pytest tests/host/test_phase5_local_execution_integration.py tests/host/test_import_boundary.py -q
# 14 passed ✓

pytest tests/host tests/runtime -q
# 334 passed ✓

python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations ✓
```

`git diff --check` 无 trailing whitespace。✓

完整 334 passed 覆盖 host + runtime 全量测试，pyright 无报错。validation 可信。✓

## Required Fixes

无 blocking fix。

## Residual Risks

1. **真实 provider runner smoke**：Phase 5 以 fake local worker 覆盖本地 no-tool 闭环，真实 LLM provider 的外部网络 / API smoke 不在范围内。这是计划内 residual risk。
2. **active cancel 超时 watchdog**：active worker cancel 后若 Engine 不产出 `run_cancelled`，当前无超时 LOST policy。计划由后续 lifecycle hardening 处理。
3. **`dispatch.py` 未出现在 `HOST_ENGINE_CONTRACT_ALLOWED_MODULES`**：当前 `dispatch.py` 不直接 import `dayu.engine`，通过 `engine_ingest.py` 间接使用。如果未来 `dispatch.py` 需要直接 import Engine types，需同步更新白名单。当前不构成问题。

## Review Gate Checklist (Plan §6)

| 检查项 | 结果 |
|--------|------|
| Phase 5 没有修改 Engine public `EngineEvent` contract | ✓ |
| Dispatch record enum 含 `pending/waiting_for_lane/dispatching/cancelled` | ✓ |
| `dispatching` 在 worker accept 后仍是 dispatch record 最终非取消状态 | ✓ |
| RunInputBuilder provider set 区分 real / noop | ✓ |
| 当前用户输入只来自 durable `USER_INPUT_ACCEPTED` | ✓ |
| `usage_reported` 是 projection_signal | ✓ |
| context compaction / unsupported recovery 只 diagnostic + FAILED | ✓ |
| clean EOF => FAILED；worker crash => LOST | ✓ |
| pre-worker cancel => `ATTEMPT_CANCELLED` / `RUN_CANCELLED` | ✓ |
| active worker cancel 只有 Attempt RUNNING 后才进入 `CANCELLING` | ✓ |
| `cancel_session_runs` replay 不取消新 Run | ✓ |
| lane token release 只在 scheduler / worker finally | ✓ |
| 未实现 ToolRuntime / fetch_more / wait / recovery / RemoteProxy | ✓ |

## Verdict

**PASS — 无 blocking finding。**

P5-S6 实现正确覆盖了 dispatch.py worker event stream 四类收口、六个 e2e 集成测试、import boundary、旧 Phase 3 断言迁移和 README 同步。验证 334 passed、pyright 0 errors 可信。可以进入 PR 创建。
