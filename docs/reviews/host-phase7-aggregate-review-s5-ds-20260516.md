# Host Phase 7 P7-S5 + Aggregate Exit Review

## Scope

- Mode: current changes
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-aggregate-review-s5-ds-20260516.md
- Included scope: P7-S5 changes (test_phase7_waiting_integration.py, dayu/host/README.md) + Phase 7 aggregate consistency across S1–S5
- Excluded scope: Engine/contracts/fins/service/ui/recovery/outbox/audit/tool trace — not modified in any Phase 7 slice
- Parallel review coverage: 无

## P7-S5 Changes

仅 2 个文件变更：

- `tests/host/test_phase7_waiting_integration.py`：+385/-0 行，新增 `test_local_awaiting_tool_manual_resolve_resumes_run` 集成测试。
- `dayu/host/README.md`：+14/-9 行，同步 WAITING cancel、ResolveWaitRequest 字段、Engine diagnostic 边界与未实现项。

## Findings

### 1. Plan Satisfaction

P7-S5 plan 要求：

1. **集成测试**：本地 awaiting tool → WAITING → manual/poll resolve → resumed run。已实现 `test_local_awaiting_tool_manual_resolve_resumes_run`，覆盖完整路径：
   - 通过 `_seed_active_integration_run` 创建 active Run（`dayu/host/README.md:143-218`）。
   - 通过 `DefaultToolRuntimeFactory` + `EffectiveToolBundleBuilder` + `DefaultHostToolFactAcceptPort` + `DefaultHostToolAwaitingAcceptPort` 构造真实 ToolRuntime（`dayu/host/README.md:148-179`）。
   - `_AwaitingBusinessTool` 返回 `ToolAwaitingOutcome(await_kind=EXTERNAL_JOB)`（`dayu/host/README.md:102-134`）。
   - `asyncio.run(tool_runtime.tool_executor.execute(batch))` 执行后断言 outcome 为 `ToolAwaitingOutcome`、Run `WAITING`、Attempt `SUSPENDED`、wait `WAITING`（`dayu/host/README.md:200-204`）。
   - `resolve_wait(host, wait_id, completed_request(source=manual))` 后断言 Run `RUNNING`、新 attempt_id 不同于原 attempt_id、resume messages 包含 `"Accepted wait result fact:"` 和 wait_id（`dayu/host/README.md:205-213`）。

2. **README 同步**：已按当前事实更新：
   - `cancel_run` 描述包含 WAITING cancel（`dayu/host/README.md:50`）。
   - `cancel_session_runs` 描述包含 WAITING target（`dayu/host/README.md:51`）。
   - `ResolveWaitRequest` 字段已文档化：`observed_at`（UTC-aware）、`source`、`idempotency_key`、typed `outcome` envelope（`dayu/host/README.md:69`）。
   - 新增 Engine diagnostic 行为段与明确未实现项列表（`dayu/host/README.md:79`）。
   - 内部 admission 段列出 WAITING cancel（`dayu/host/README.md:142`）。

3. **不修改设计真源**：`docs/host/design.md` 与 `docs/host/implementation-control.md` 未修改。✅

4. **不修改 tests/README.md**：未引入新测试层级或命令约定。✅

**结论**：P7-S5 完全满足 plan 规定的目标。

### 2. Integration Test Value

`test_local_awaiting_tool_manual_resolve_resumes_run` 提供了此前单元测试无法覆盖的端到端价值：

- **真实组件链路**：测试使用了 `DefaultToolRuntimeFactory`、`EffectiveToolBundleBuilder`、`DefaultHostToolFactAcceptPort`、`DefaultHostToolAwaitingAcceptPort` — 全部为生产实现，非 mock。
- **完整状态变迁**：验证了 `RUNNING → WAITING → RUNNING` 的 Run 生命周期、`STARTING → SUSPENDED → (new) STARTING` 的 Attempt 生命周期、以及 wait record `WAITING → RESOLVED` 的转换。
- **resume 消息连续性**：验证了 `RunInputBuilder` 在 resume 路径中重建了 accepted wait fact system message，这是 S3 的关键契约。
- **跨 Attempt 验证**：验证了 resume 后的 `current_attempt_id` 不同于原 `attempt_id`，确认新 Attempt 被正确创建。

测试辅助依赖评估：

- 从 `tests.host.test_resolve_wait_command` 导入 `_SeededWaitingRun`、`_build_resume_request`、`_completed_request`、`_options`、`_read_wait`、`_seed_active_run`。这些是测试内部共享 helper，不涉及生产代码依赖。
- `_NeverCancelledToken`、`_AwaitingBusinessTool` 是本文件内定义的测试替身，类型完整，docstring 齐全。
- 所有辅助函数有中文 docstring，类型签名无 `Any`/`object`。

### 3. Phase 7 Aggregate Consistency

#### 3.1 公共契约一致性（S1）

- `ResolveWaitRequest` 使用 typed `outcome: ResolveWaitOutcome` 替代 `outcome_ref: str`；`observed_at: datetime` 强制 UTC-aware。
- `ResolveWaitCompletedOutcome`、`ResolveWaitFailedOutcome`、`ResolveWaitCancelledOutcome`、`ResolveWaitLostOutcome` 互斥校验（completed/failed/cancelled 不携带 `provider_status_ref`，lost 不携带 `payload_ref`）。
- `HostPayloadRef` 从 `dayu.host.tool_runtime` 迁移至 `dayu.host.api`，消除重复定义。
- `ToolFactKind.LOST` 枚举值已添加，供 lost resolve 路径使用。
- 字符串长度常量（`HOST_WAIT_ID_MAX_LENGTH` 等）统一用于 dataclass validation 与 DDL CHECK。

#### 3.2 Wait Record / Awaiting Accept 一致性（S1-S2）

- `host_wait_records` 表 schema 与 plan §3.7 一致：typed fields、CHECK 约束、partial unique index on `(run_id) WHERE status='waiting'`、poll observation index。
- `DefaultHostToolAwaitingAcceptPort` 在单个 write transaction 内写入 `TOOL_AWAITING` + `RUN_WAITING` + `ATTEMPT_SUSPENDED` + insert wait record + CAS Run→WAITING + close Attempt→SUSPENDED。
- Awaiting accept 幂等 scope 为 `(wait_accept, wait_id, accept_idempotency_key)`，同 key 同 digest 返回既有 ack，同 key 异 digest 返回 rejected ack。
- Adapter binding 由 Host 根据 tool_name + await_kind + Host policy 解析，不由 Engine 选择。

#### 3.3 resolve_wait / Resume Attempt 一致性（S3）

- `resolve_wait` 幂等 scope 为 `(wait_id, request.idempotency_key)`；同 key 同 semantic digest 返回既有 RunSnapshot；同 key 异 digest 返回 `IDEMPOTENCY_CONFLICT`。
- completed/cancelled tool outcome：在同一 transaction 内 close wait→RESOLVED → RESUME_REQUESTED → TOOL_RESULT_ACCEPTED → RUN_STARTED(start_reason=resume) → ATTEMPT_STARTED → pending dispatch record → commit 后 wake dispatch。
- failed outcome：close wait→FAILED → TOOL_RESULT_ACCEPTED → RUN_FAILED，不创建 resume Attempt。
- lost outcome：close wait→LOST → TOOL_RESULT_ACCEPTED(tool_fact_kind=lost) → RUN_LOST，不创建 resume Attempt。
- S3-F1（LOST terminal replay gap）已修复：`WaitRecordStatus.LOST` 已加入 terminal replay 分支，同 key 重放返回既有 snapshot。
- `resume_run_from_waiting_in_transaction` CAS 前提：Run=WAITING + current_attempt_id 匹配 + Attempt=SUSPENDED + wait=waiting + NOT EXISTS idle-session 互斥。
- `RunInputBuilder` resume 路径从 EventLog `TOOL_RESULT_ACCEPTED` 通过 payload ref 重建 accepted wait/tool fact system message。
- `RunStartReason.RESUME` 已添加且参与 codec。

#### 3.4 WAITING Cancel 一致性（S4）

- `cancel_run` 和 `cancel_session_runs` 复用同一 `cancel_waiting_run_in_transaction`。
- Cancel 事务顺序：CANCEL_REQUESTED → cancel_active_wait_records_for_run（bulk CAS WAITING→CANCELLED，rowcount 校验）→ RUN_CANCELLED → cancel_waiting_run_row（CAS WAITING→CANCELLED）。
- 不创建 resume Attempt，不追加 ATTEMPT_CANCELLED（Attempt 已在 SUSPENDED 终态）。
- `cancel_session_runs` 的 `_SupportedSessionCancelTarget` 包含 `waiting: bool` 字段，WAITING Run 被正确分类。

#### 3.5 Late Diagnostic 一致性（S4）

- Late rejection 使用独立 `wait_late_rejection` 幂等 scope，不复用 `wait_resolution`。
- CANCELLED/LOST wait record 或 owner Run terminal → `WAIT_LATE_RESULT_REJECTED` diagnostic。
- RESOLVED/FAILED wait record + 不同 key → `INVALID_STATE`，不写 diagnostic（与 plan §3.9 步骤 6 一致）。
- 同 key 同 digest 不重复写 diagnostic；同 key 异 digest 返回 `IDEMPOTENCY_CONFLICT` 且不追加事件。
- `WaitLateRejectionReason` 枚举覆盖 7 种 rejection reason，`_wait_late_rejection_scope` 独立于 `_wait_resolution_scope`。

#### 3.6 Poller 一致性（S4）

- `WaitPoller.poll_once()` 在 read transaction 内读取 active poll wait 快照，释放 transaction 后调用 adapter，adapter 调用在 Host transaction 外。
- ready/lost → 调用 `resolve_wait`（通过 `WaitResolvePort` protocol）。
- cancelled → 调用 adapter `abandon_wait()`，不调用 `resolve_wait`。
- `_poll_idempotency_key()` 使用 sha256(source=poll, wait_id=wait_id) 生成确定性 key。
- Poller 不持有 EventLog appender 或 wait-state writer 端口；唯一的状态变更路径是 `resolve_wait`。

#### 3.7 EngineEvent Confirmation 一致性（S4）

- `TOOL_AWAITING` / `RUN_SUSPENDED` 路由到 `_confirm_waiting_engine_event`，不再走 `_diagnostic_then_failed_waiting`。
- 只写入 `ENGINE_EVENT_DIAGNOSTIC`（DIAGNOSTIC class），不创建 wait record，不调用 `terminal_closeout_in_transaction`。
- Run WAITING + Attempt SUSPENDED + 匹配 refs → "waiting_event_confirmation" diagnostic。
- 缺 refs → "waiting_event_without_host_accepted_refs" diagnostic。
- Duplicate ingest 幂等，不追加重复事件。

#### 3.8 边界一致性

- **无越界修改**：Phase 7 未修改 `dayu/engine/`、`dayu/contracts/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`。
- **无反向依赖**：Engine 不从 Host 导入；Host 不从上层导入。
- **dayu.runtime 未承载 Phase 7 语义**：所有 wait record、adapter registry、resolution pipeline 均在 `dayu.host` 内。
- **设计真源未修改**：`docs/host/design.md` 和 `docs/host/implementation-control.md` 保持原样。

#### 3.9 状态机闭包

Phase 7 wait record 状态机闭包检查：

| 源状态 | 触发 | 目标状态 | 正确性 |
| --- | --- | --- | --- |
| — | ToolRuntime awaiting accept | WAITING | ✅ |
| WAITING | resolve_wait(completed/cancelled) | RESOLVED | ✅ |
| WAITING | resolve_wait(failed) | FAILED | ✅ |
| WAITING | resolve_wait(lost) | LOST | ✅ |
| WAITING | cancel_run/cancel_session_runs | CANCELLED | ✅ |
| RESOLVED | 同 key replay | RESOLVED（幂等） | ✅ |
| RESOLVED | 不同 key | INVALID_STATE（不写 diagnostic） | ✅ |
| FAILED | 同 key replay | FAILED（幂等） | ✅ |
| FAILED | 不同 key | INVALID_STATE（不写 diagnostic） | ✅ |
| LOST | 同 key replay | LOST（幂等） | ✅ |
| LOST | 任何新请求 | WAIT_LATE_RESULT_REJECTED | ✅ |
| CANCELLED | 任何新请求 | WAIT_LATE_RESULT_REJECTED | ✅ |

所有 terminal state（RESOLVED/FAILED/LOST/CANCELLED）均为吸收态，不可回退。

#### 3.10 README 事实一致性

逐项对比 README 声明与代码实现：

- "cancel_run 支持 WAITING Run cancel" → `admission.py:_CancelRunOperation._cancel_waiting()` ✅
- "cancel_session_runs 支持 WAITING Run" → `admission.py:_CancelSessionRunsOperation._cancel_waiting_target()` ✅
- "ResolveWaitRequest 必须携带 UTC-aware observed_at、source、idempotency_key 与强类型 outcome envelope" → `api.py:ResolveWaitRequest` dataclass ✅
- "WAITING cancel 复用同一 Host admission transition" → `run_transition.py:cancel_waiting_run_in_transaction` ✅
- "late result 只写入 WAIT_LATE_RESULT_REJECTED diagnostic" → `waiting.py:_reject_late_result` ✅
- "Poller 只读取 durable poll wait 快照，外部 adapter 调用在 Host transaction 外" → `wait_adapter.py:WaitPoller.poll_once()` ✅
- "Engine TOOL_AWAITING/RUN_SUSPENDED 只作为 diagnostic confirmation" → `engine_ingest.py:_confirm_waiting_engine_event()` ✅
- 未实现项列表（callback endpoint、poll loop、recovery scan、remote wait、physical cancel、duplicate ledger、tool trace projection）→ 均与代码事实一致 ✅

### 4. Verification Command Sufficiency

P7-S5 验证命令：

```bash
source .venv/bin/activate && pytest tests/host -q  # 389 passed
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/  # 0 errors
git diff --check  # 通过
```

- 389 passed 覆盖了 Phase 7 全部测试（S1-S5），包含 P7-S5 新增的集成测试。
- pyright 覆盖 `dayu/`、`tests/`、`utils/` 全量，0 errors 确认无类型问题扩散。
- `git diff --check` 通过确认无空白问题。

### 5. Residual Risk

Phase 7 aggregate 未覆盖风险（与 plan §11 一致，均已有明确 owner）：

- **Callback endpoint**：未实现 HTTP callback 入口、callback 认证/重放防护。Owner: 后续 callback adapter 工作单元。
- **Poller 后台循环**：当前仅 `poll_once()` 单轮入口，无调度循环、退避、并发 in-flight fencing 或 adapter 错误重试。Owner: 后续 poller hardening 工作单元。
- **Recovery scan**：Host 重启后不会自动恢复 active poll wait observation。Owner: Phase 11 Recovery。
- **Remote wait 恢复**：RemoteProxy/remote worker 自治 resume 未实现。Owner: 后续 remote proxy 工作单元。
- **External job physical cancel**：adapter abandon 仅为 best-effort，不保证外部 job 被取消。Owner: 后续 adapter hardening 工作单元。
- **Engine matching-ref 校验**：Engine 公共事件不携带 Host accepted wait refs，当前只能做 diagnostic/idempotent confirmation，不能做强 matching-ref 校验。Owner: Engine contract 演进（需跨层协调）。
- **Durable duplicate ledger / tool trace projection**：未实现。Owner: 后续 projection/tool trace 工作单元。

以上风险均有明确 deferred owner，不构成 Phase 7 blocking finding。

## Open Questions

无。

## Verdict

**PASS**。P7-S5 满足 plan 目标，集成测试提供了真实端到端覆盖，README 与代码事实一致。Phase 7 aggregate 五片实现（S1–S5）整体一致：公共契约、wait record、ToolRuntime awaiting accept、resolve_wait resume/terminal、WAITING cancel、late diagnostic、poller、EngineEvent confirmation 各模块边界清晰，状态机闭包完整，无边界越位或反向依赖。
