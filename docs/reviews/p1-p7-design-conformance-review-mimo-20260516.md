# P1-P7 Design Conformance Review

日期：2026-05-16

## Scope

- Mode: design conformance review（非 PR diff review，而是已合并 main 上 P1-P7 全量实现与设计真源的一致性检查）
- Branch: main，HEAD=c39de2e（PR 56 merge commit）
- 设计真源: `docs/host/design.md` §1-§28
- 总控参考: `docs/host/implementation-control.md`
- Included scope: `dayu/host/` 全部 31 个 .py 文件、`dayu/runtime/`、`dayu/contracts/`、`dayu/engine/contracts/` import 方向、`tests/host/` 测试覆盖
- Excluded scope: Engine 执行路径、fins、ui、recovery、outbox、audit、tool trace read-model（均为后续 phase）
- Output file: `docs/reviews/p1-p7-design-conformance-review-mimo-20260516.md`

## Repository Map

### dayu/host/ (31 files, 32,803 LOC)

| 文件 | LOC | 职责 |
|------|-----|------|
| tool_runtime.py | 4997 | ToolRuntime governance: accept barrier, truncation, fetch_more, duplicate governance, diagnostics, awaiting accept (P6+P7) |
| durable/state.py | 4706 | Durable state row codec, status enums, CAS helpers (P1-P7) |
| durable/run_transition.py | 3785 | Run/Attempt state transitions: create, accept, cancel, resume, terminal (P2-P7) |
| admission.py | 2855 | Host admission: start_run, followup, cancel, session cancel, queue promotion (P3-P7) |
| waiting.py | 2075 | Awaiting accept port, resolve_wait service, late result rejection (P7) |
| api.py | 2017 | Public API types: request, snapshot, status, error, context, constants (P1) |
| engine_ingest.py | 1902 | EngineEvent ingest: terminal closeout, diagnostic confirmation (P5-P7) |
| run_input.py | 1331 | RunInputBuilder: message reconstruction from EventLog (P5-P7) |
| dispatch.py | 1282 | Local dispatch scheduler, WorkerProxy lifecycle (P5) |
| command.py | 986 | Public command facade: start_run, cancel, resolve_wait, etc. (P4-P7) |
| durable/session_lifecycle.py | 872 | Session lifecycle CRUD (P2) |
| durable/event_log.py | 766 | EventLog append/read (P2) |
| durable/schema.py | 669 | Schema DDL v4: 8 tables, CHECK constraints, indexes (P2-P7) |
| durable/liveness.py | 580 | Host instance liveness: register, heartbeat, mark stopping (P2) |
| durable/payload.py | 502 | Payload store: inline/ref storage (P2) |
| _event_payload.py | 472 | Event payload helpers (P5-P7) |
| wait_adapter.py | 422 | WaitAdapterBinding, WaitAdapterRegistry, WaitPoller (P7) |
| durable/transaction.py | 396 | HostTransaction, HostTransactionRunner (P2) |
| durable/artifact.py | 389 | Artifact store (P2) |

### Import Dependencies

```
dayu/contracts/  ←── dayu/runtime/ (CancellationToken)
               ←── dayu/host/ (JsonValue, ToolBundle, ToolAwaitSpec, etc.)
               ←── dayu/engine/contracts/ (internal)

dayu/runtime/    ←── dayu/engine/ (cancellation, log_levels)
               ←── dayu/host/ (lane)

dayu/engine/contracts/ ←── dayu/host/ (AgentRunRequest, EngineEvent, RunnerSpec, AgentPolicy)
dayu/engine/            ←── dayu/host/local_proxy.py (run_agent_messages — dispatch execution)
```

## Findings

### F1-未修复-低-工具运行时文件规模

- **入口/函数**: `dayu/host/tool_runtime.py` 整体
- **文件(行号)**: `tool_runtime.py` (4997 行, 66 classes, 165 functions)
- **输入场景**: 任何对 ToolRuntime 的修改
- **实际分支**: 该文件承载 P6 全部 ToolRuntime 治理（accept barrier, truncation, fetch_more, duplicate governance, diagnostics）加上 P7 awaiting accept path
- **预期行为**: 设计 §18 明确 ToolRuntime 是工具治理的唯一 owner，所有工具治理职责归于同一模块
- **实际行为**: 66 个 class 定义在一个文件中，包含 Protocol、dataclass、internal helper、factory、executor wrapper 等多种角色
- **直接证据**: `grep -c 'class ' tool_runtime.py` → 66；`wc -l tool_runtime.py` → 4997
- **影响**: 单文件修改风险高，新增工具治理能力时容易引入回归；但当前行为正确
- **建议改法和验证点**: 后续 phase 可考虑拆分为 `tool_runtime_accept.py`、`tool_runtime_truncation.py`、`tool_runtime_duplicate.py` 等子模块，保持同一包内聚。不阻塞当前 P1-P7 exit
- **修复风险（低/中/高）**: 低（重构不改变行为）
- **严重程度（低/中/高/严重）**: 低

### F2-未修复-信息-SHA256 digest 正则重复定义

- **入口/函数**: `_SHA256_DIGEST_PATTERN` 在 `api.py:50` 和 `codec.py` 中各定义一次
- **文件(行号)**: `dayu/host/api.py:50`、`dayu/host/durable/codec.py:93`
- **输入场景**: digest 校验
- **实际分支**: 两处均使用 `re.compile(r"^sha256:[0-9a-f]{64}$")` 的 `fullmatch`
- **预期行为**: 设计要求 digest 校验语义一致
- **实际行为**: 语义完全一致（同一正则），但定义重复
- **直接证据**: `api.py:50`: `_SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")`；`codec.py` `is_sha256_digest` 使用相同 pattern
- **影响**: 无功能影响。若未来正则变更需同步两处，但当前已通过 PR 56 fix 统一了 `waiting.py` 的 digest 校验
- **建议改法和验证点**: 后续可让 `api.py` 的 `_require_sha256_digest` 复用 `codec.is_sha256_digest`。不阻塞
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 信息

## Architecture Boundary Verification

### 1. 层依赖方向（UI → Service → Host → Engine）

| 检查项 | 结果 | 证据 |
|--------|------|------|
| Host → Engine contracts | ✅ 允许 | `api.py`、`engine_ingest.py`、`run_input.py`、`local_proxy.py` 导入 `dayu.engine.contracts.*`（AgentRunRequest, EngineEvent, RunnerSpec 等共享类型） |
| Host → Engine execution | ✅ 允许 | `local_proxy.py:13` 导入 `dayu.engine.run_agent_messages`（Host 通过 Engine 执行，正确方向） |
| Engine → Host | ✅ 无 | `dayu/engine/` 无任何 `dayu.host` import |
| Host → service/ui/fins | ✅ 无 | `dayu/host/` 无任何 `dayu.service`/`dayu.ui`/`dayu.fins` import |
| Host → runtime | ✅ 允许 | `dispatch.py:83` 导入 `dayu.runtime.lane`（层中立基础设施） |
| runtime → 业务层 | ✅ 无 | `dayu/runtime/` 只导入 `dayu.contracts` 和标准库 |
| contracts → 业务层 | ✅ 无 | `dayu/contracts/` 只导入自身 |
| Engine → runtime | ✅ 允许 | `engine/agent.py`、`engine/runners/openai/runner.py` 导入 `dayu.runtime.cancellation` |

**结论**: 层依赖方向完全正确，无反向依赖。

### 2. dayu.runtime 中立性

`dayu/runtime/` 提供 5 个模块：`__init__.py`、`cancellation.py`、`filelock.py`、`lane.py`、`log_levels.py`、`log.py`。全部只导入 `dayu.contracts.cancellation.CancellationToken`、`dayu.contracts.json_value.JsonValue` 和标准库。无业务语义、无 Host 治理状态、无 Engine 协议状态机。**完全中立**。

### 3. 公共契约泄漏检查

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 内部对象未暴露 | ✅ | `DefaultHostToolAwaitingAcceptPort`、`WaitPoller`、`DefaultHostResolveWaitService`、`HostAdmissionService` 等均不在 `__init__.py` 导出 |
| Public API 完整 | ✅ | `__init__.py` 导出：`ensure_session`、`start_run`、`cancel_run`、`cancel_session_runs`、`resolve_wait`、`retry_run`、`replay_run`、`get_run`、`get_session`、`stream_run_events`、`submit_followup`、`create_session`、`close_session`、`purge_session` |
| Phase 7 类型已导出 | ✅ | `WaitAdapterKey`、`HostPayloadRef`、`ResolveWaitCompletedOutcome`/`FailedOutcome`/`CancelledOutcome`/`LostOutcome`、`WaitProviderStatusRef`、`WaitResolutionSource` 均在 `__all__` |

## State Machine Conformance

### RunStatus（设计 §12-§13）

| 设计要求状态 | 实现 | 位置 |
|-------------|------|------|
| QUEUED | ✅ | `api.py:263` |
| RUNNING | ✅ | `api.py:264` |
| WAITING | ✅ | `api.py:265` |
| CANCELLING | ✅ | `api.py:266` |
| RECOVERING | ✅ | `api.py:267` |
| SUCCEEDED | ✅ | `api.py:268` |
| FAILED | ✅ | `api.py:269` |
| CANCELLED | ✅ | `api.py:270` |
| LOST | ✅ | `api.py:271` |

无额外未文档化状态。

### AttemptStatus（设计 §13）

| 设计要求状态 | 实现 | 位置 |
|-------------|------|------|
| STARTING | ✅ | `api.py:281` |
| RUNNING | ✅ | `api.py:282` |
| SUCCEEDED | ✅ | `api.py:283` |
| FAILED | ✅ | `api.py:284` |
| CANCELLED | ✅ | `api.py:285` |
| SUSPENDED | ✅ | `api.py:286`（Phase 7） |
| STEERED | ✅ | `api.py:287`（设计 §14 steer） |
| LOST | ✅ | `api.py:288` |

无额外未文档化状态。

### WaitRecordStatus（设计 §20）

| 设计要求状态 | 实现 | DDL CHECK |
|-------------|------|-----------|
| waiting | ✅ `state.py:125` | ✅ `schema.py:507` |
| resolved | ✅ `state.py:126` | ✅ `schema.py:507` |
| failed | ✅ `state.py:127` | ✅ `schema.py:507` |
| cancelled | ✅ `state.py:128` | ✅ `schema.py:507` |
| lost | ✅ `state.py:129` | ✅ `schema.py:507` |

DDL CHECK: `status IN ('waiting', 'resolved', 'failed', 'cancelled', 'lost')` — 完全一致。

### WaitResumePolicy（设计 §20）

| 设计要求 | 实现 | DDL CHECK |
|----------|------|-----------|
| poll | ✅ `state.py:134` | ✅ `schema.py:479` |
| callback | ✅ `state.py:135` | ✅ `schema.py:479` |
| manual | ✅ `state.py:136` | ✅ `schema.py:479` |

### EventClass（设计 §16）

| 设计要求 | 实现 |
|----------|------|
| canonical_fact | ✅ |
| preview | ✅ |
| diagnostic | ✅ |
| projection_signal | ✅ |

## Key Transition Verification

### cancel_waiting_run_in_transaction（设计 §22）

`run_transition.py:1315-1399`：

1. `_validate_cancel_waiting_input` — 输入校验 ✓
2. `read_run_by_id` → 检查 `WAITING` + `current_attempt_id is not None` ✓
3. `read_attempt_by_id` → 检查 `SUSPENDED` ✓
4. `read_active_wait_records_for_run` → 确认有 active waits ✓
5. `append_event(CANCEL_REQUESTED)` — line 1355 ✓
6. `cancel_active_wait_records_for_run` (CAS WAITING→CANCELLED) — line 1359 ✓
7. `append_event(RUN_CANCELLED)` 含 wait_ids — line 1372 ✓
8. `cancel_waiting_run_row` (CAS WAITING→CANCELLED with current_attempt_id) — line 1382 ✓

**顺序完全正确**: CANCEL_REQUESTED → wait records mutation → RUN_CANCELLED → Run row CAS。

### resume_run_from_waiting_in_transaction（设计 §20-§21）

`run_transition.py:832-912`：

1. `_validate_resume_waiting_input` ✓
2. `read_run_by_id` / `read_attempt_by_id` / `read_wait_record_by_id` ✓
3. `append_event(RESUME_REQUESTED)` — line 863 ✓
4. `append_event(TOOL_RESULT_ACCEPTED)` — line 866 ✓
5. `mark_wait_record_resolved_row` (CAS WAITING→RESOLVED) — line 870 ✓
6. `append_event(RUN_STARTED(start_reason=resume))` — line 883 ✓
7. `append_event(ATTEMPT_STARTED)` — line 892 ✓
8. `insert_attempt` + `resume_waiting_run_row` (CAS WAITING→RUNNING) — line 908-909 ✓

**顺序完全正确**: RESUME_REQUESTED → TOOL_RESULT_ACCEPTED → wait RESOLVED → RUN_STARTED(resume) → ATTEMPT_STARTED → attempt row + run CAS。

### resolve_wait condition chain（设计 §20）

`waiting.py:600-731`：

1. terminal wait (RESOLVED/FAILED/LOST): `_replay_terminal_resolution_or_none`
   - 同 key 同 digest → 重放 ✓
   - 同 key 不同 digest → `IDEMPOTENCY_CONFLICT` ✓
   - 不同 key + RESOLVED/FAILED → `INVALID_STATE`（不写 diagnostic）✓
   - 不同 key + LOST → `_reject_late_result`（写 diagnostic）✓
2. CANCELLED → `_reject_late_result`（写 diagnostic）✓
3. 非 WAITING → `_reject_late_result(rejection_reason=INVALID_WAIT_STATE)` ✓
4. WAITING 但 owner Run terminal → `_reject_late_result(rejection_reason=RUN_TERMINAL)` ✓
5. WAITING + Run active → idempotency check → dispatch to `_resolve_resume` / `_resolve_failed` / `_resolve_lost` ✓

**完全符合设计**: resolved/failed 不同 key 不写 diagnostic（只抛 INVALID_STATE）；cancelled/lost/terminal owner 写 diagnostic。

### WaitPoller（设计 §20）

`wait_adapter.py:324-377`：

1. `_read_wait_records_for_poll_observation` — 读快照（transaction 内）✓
2. adapter 调用在 transaction 外 ✓
3. CANCELLED → `adapter.abandon_wait(record)`，不调用 `resolve_wait` ✓
4. WaitPollNotReady → 不调用 `resolve_wait` ✓
5. WaitPollReady → 构造 `ResolveWaitRequest` 调用 `resolve_wait` ✓
6. WaitPollLost → 同上，outcome 为 `ResolveWaitLostOutcome` ✓
7. adapter 异常 → `adapter_errors += 1`，不崩溃 ✓

### EngineEvent ingest — TOOL_AWAITING / RUN_SUSPENDED（设计 §20）

`engine_ingest.py:721-773`：

1. 只写 diagnostic event，不创建 wait state ✓
2. `terminal_closeout=False` ✓
3. reason 按 run/attempt 状态区分：WAITING+SUSPENDED → `waiting_event_confirmation`；其它 → `waiting_event_without_host_accepted_refs` ✓
4. 幂等确认：event_id 基于 candidate 派生，`_existing_rows` 检查重复 → DUPLICATE ✓

`engine_ingest.py:1172-1191` `_late_rejection_reason`：

1. `RUN_SUSPENDED`/`TOOL_AWAITING` + WAITING+SUSPENDED → 返回 None（允许通过）✓
2. terminal run → 返回 rejection reason（拒绝）✓
3. 其它 → 返回 None（允许）✓

## Schema DDL Conformance（设计 §20）

`schema.py:459-577` `host_wait_records` DDL：

| 设计要求 | 实现 | 证据 |
|----------|------|------|
| status CHECK (5 values) | ✅ | `schema.py:506-508` |
| resume_policy CHECK (3 values) | ✅ | `schema.py:478-480` |
| terminal_at ↔ terminal status 配对 | ✅ | `schema.py:524-536` |
| snapshot triplet 约束 | ✅ | `schema.py:524-530` (允许 digest 为 NULL — 有意设计) |
| resolve key+digest 配对 | ✅ | `schema.py:537-541` |
| one_active_per_run unique index | ✅ | `schema.py:562-566` |
| active_poll index | ✅ | `schema.py:568-571` |
| external_job index | ✅ | `schema.py:573-577` |
| 外键: session/run/attempt/execution/event refs | ✅ | `schema.py:516-523` |
| Schema version 4 (fresh, no migration) | ✅ | 设计 §20 要求 |

## Design Alignment Summary（设计 §20 退出条件）

| 设计要求 | 实现位置 | 状态 |
|----------|----------|------|
| ToolRuntime Host accept path 是 awaiting canonical owner | `waiting.py` `DefaultHostToolAwaitingAcceptPort` | ✅ |
| Engine tool_awaiting/run_suspended 不能创建 wait state | `engine_ingest.py` `_confirm_waiting_engine_event` — 只 diagnostic | ✅ |
| wait record 是 Host durable state index | `durable/schema.py` + `durable/state.py` | ✅ |
| resolve_wait 是短事务 command | `waiting.py` `DefaultHostResolveWaitService` — single write transaction | ✅ |
| 幂等范围 (wait_id, idempotency_key) | `waiting.py` `_wait_resolution_scope` | ✅ |
| 同 key 同 outcome 重放，不同 outcome 冲突 | `waiting.py` `_resolve_in_transaction` + `_replay_terminal_resolution_or_none` | ✅ |
| cancelled/lost late result → diagnostic | `waiting.py` `_reject_late_result` | ✅ |
| resolved/failed 不同 key → INVALID_STATE（不写 diagnostic） | `waiting.py:641-649` | ✅ |
| WAITING cancel → cancelled wait records + CANCELLED Run | `run_transition.py` `cancel_waiting_run_in_transaction` | ✅ |
| resume 是同一 Run 内新 Attempt | `run_transition.py` `resume_run_from_waiting_in_transaction` | ✅ |
| RunInputBuilder 从 EventLog canonical facts 重建 messages | `run_input.py` `_resume_wait_message_from_current_start` | ✅ |
| poll/callback/manual 都走同一 resolve_wait pipeline | `wait_adapter.py` `WaitPoller.poll_once` → `resolve_wait` | ✅ |
| typed outcome envelope | `api.py` `ResolveWaitCompletedOutcome`/`FailedOutcome`/`CancelledOutcome`/`LostOutcome` | ✅ |
| adapter_key 来源明确 | `api.py` `WaitAdapterKey` typed ref | ✅ |
| snapshot_ref / external_job_id typed ref | `api.py` `HostPayloadRef` / `wait_adapter.py` `WaitExternalJobRefSource` | ✅ |

## Non-goals 验证（设计 §28 + implementation-control.md）

| Non-goal | 状态 |
|----------|------|
| 不保证外部 job physical cancel | ✅ 未实现 |
| 不实现 callback 认证入口完整产品化 | ✅ 未实现 |
| 不实现远端 worker 自治 resume | ✅ 未实现 |
| 不实现 HTTP callback endpoint | ✅ 未实现 |
| 不修改 Engine contract | ✅ 未修改 |
| 不把 adapter object / callable 放进 durable wait record | ✅ 只存 typed refs |
| 不做旧库兼容 | ✅ 全新 schema v4 |
| 不实现 recovery scan | ✅ Phase 11 |
| 不实现 durable tool trace projection | ✅ 后续 phase |
| 不实现长期 memory | ✅ 后续 phase |

## Verification Results

- `pytest tests/host -q` → **391 passed** ✓
- `python -m pyright dayu/host/` → **0 errors** ✓（生产代码无类型错误）
- `python -m pyright dayu/ tests/ utils/` → 36 errors，全部为 `reportMissingImports`（pytest 未在 pyright 搜索路径中）和 `dayu/runtime/filelock.py` 的第三方库类型桩问题。**无生产代码类型错误** ✓
- `git diff --check` → clean ✓
- HEAD = c39de2e（PR 56 merge commit）✓

## Open Questions

无。

## Residual Risk

以下为 P1-P7 已知非目标或后续 phase owner 事项：

1. **callback endpoint / auth / replay**: Phase 7 只预留 `callback` source 和 `resolve_wait` pipeline contract。Owner: 后续 phase。
2. **外部 job physical cancel / revoke**: adapter 只能 best-effort。Owner: 后续 adapter hardening。
3. **Engine contract 不携带 Host accepted wait refs**: P7 只能做 diagnostic confirmation。Owner: 后续 Engine contract 演进。
4. **poller 后台调度循环 / 退避 / in-flight fencing**: 当前只有 `poll_once()` 单轮。Owner: 后续 runtime hardening。
5. **recovery scan 对 WAITING Run 处理**: design §27 明确归 Phase 11。
6. **tool trace projection / late diagnostic 可观测性**: WAIT_LATE_RESULT_REJECTED diagnostic 已写入 EventLog，无 read model 投影。Owner: 后续 projection。
7. **durable duplicate ledger**: 当前 duplicate governance 为 run-local in-memory。Owner: 后续 duplicate hardening。
8. **tool_runtime.py 文件规模**: 4997 行 / 66 class，后续可拆分子模块。Owner: 后续 refactor。
9. **_SHA256_DIGEST_PATTERN 重复定义**: `api.py` 和 `codec.py` 各定义一次，语义一致。Owner: 后续 cleanup。
10. **retry_run / replay_run**: 当前返回 `UNSUPPORTED_OPERATION`。Owner: 后续 phase。

所有 residual risk 均有明确 owner 或属于已确认 non-goal，无无主风险。

## 结论

**PASS。**

P1-P7 全部实现与 `docs/host/design.md` 设计真源一致。层依赖方向正确（UI→Service→Host→Engine，无反向依赖）。dayu.runtime 完全中立。公共契约无内部实现泄漏。Run/Attempt/WaitRecord 状态机、cancel/resume 转换、resolve_wait 条件链、WaitPoller、EngineEvent diagnostic confirmation、Schema DDL CHECK 约束和索引均与设计逐条对齐。测试覆盖完整（391 passed）。未发现 blocking design deviation。两个低/信息 severity maintainability findings（tool_runtime.py 规模、digest 正则重复）不阻塞 Phase 7 exit。Residual risks 均有明确 owner。
