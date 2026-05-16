# P1-P7 Design Conformance Review

- 日期：2026-05-16
- 基线：main，HEAD=c39de2e（PR #56 merge commit）
- 设计真源：`docs/host/design.md`（全部 §1–§28）
- 总控参考：`docs/host/implementation-control.md`
- 审查性质：已合并 main 上 P1-P7 全量实现与设计真源的专项一致性审查，非 PR diff review
- 修改范围：仅创建本 artifact，未修改生产代码
- 并行审查：2 个独立子代理（Codex, Mimo）并行审查全部 28 个设计章节 + 架构边界 + 耦合分析；主 reviewer 对子代理发现做独立验证、去重、severity 裁决并合成最终 artifact

## Scope

- Included: `dayu/host/` 全部 31 个 .py 文件（~32,800 LOC）、`dayu/runtime/`、`dayu/contracts/`、`dayu/engine/contracts/` import 方向、`tests/host/` 测试覆盖
- Excluded: `dayu/engine/` 执行路径、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、recovery/outbox/audit/tool trace read-model（均为后续 phase）
- Review slices:
  - Slice 1 (Codex): 公共契约、真实入口、start/dispatch/engine、tool awaiting/resolve_wait、cancel/late result、engine awaiting confirmation、架构边界
  - Slice 2 (Mimo): Repository map、全部状态机、关键 transition、resolve_wait condition chain、WaitPoller、EngineEvent ingest、Schema DDL、设计 §20 退出条件、non-goals 验证

## Findings

### D01-Medium — Dispatch Scheduler 未接入 P7 Awaiting Accept Port 与 Wait Adapter Registry

**Severity：Medium. Not blocking — capability is fully implemented; gap is in production wiring.**

**入口/函数**: `HostDispatchScheduler._run_input_builder_for_dispatch`

**文件(行号)**: `dayu/host/dispatch.py:707-734`

**输入场景**: 业务工具经 `HostDispatchScheduler` 的本地执行路径返回 `ToolAwaitingOutcome`。

**实际分支**: `ToolRuntimeBuildRequest` 构造时未传入 `awaiting_accept_port` 和 `wait_adapter_registry`，两者保持默认值 `None`。ToolRuntime 的 `_accept_awaiting` (`tool_runtime.py:2449-2455`) 检测到两者为 `None` 后返回 `_awaiting_configuration_failure()`，将 `ToolAwaitingOutcome` 降级为受治理工具失败，Run 不进入 `WAITING`。

**预期行为**: 经 dispatch scheduler 的生产路径应能正确将 `ToolAwaitingOutcome` 持久化为 `WAITING` Run + `SUSPENDED` Attempt + active wait record。

**实际行为**: 只通过直接构造 ToolRuntime 的集成测试（`test_phase7_waiting_integration.py`）可到达 WAITING 路径；生产入口 `HostDispatchScheduler` 无法到达。

**直接证据**:

- `dispatch.py:707-735` 构造 `ToolRuntimeBuildRequest` 时只传入 `accept_port`（普通 tool fact accept port）和 `duplicate_governance_registry`，不传 `awaiting_accept_port` 和 `wait_adapter_registry`
- `dispatch.py:293-334` `HostDispatchScheduler.__init__` 没有 `awaiting_accept_port` 或 `wait_adapter_registry` 参数
- `api.py:668-703` `HostLocalExecutionOptions` 没有 `awaiting_accept_port` 或 `wait_adapter_registry` 字段
- `tool_runtime.py:2449-2455`：`self._awaiting_accept_port is None or self._wait_adapter_registry is None` → 返回 `_awaiting_configuration_failure()`
- `tool_runtime.py:2093-2098` docstring 明确说明 "无则 awaiting outcome 返回受治理错误"
- `tests/host/test_phase7_waiting_integration.py:143-178` 绕过 scheduler，直接构造 ToolRuntime 并手工传入 `DefaultHostToolAwaitingAcceptPort(...)` 和 wait adapter registry

**影响**: P7 核心能力（awaiting tool → WAITING Run）在生产 dispatch 入口不可用。`ToolRuntime` gracefully degrades（返回 governed error，不崩溃），但用户无法通过正常执行路径触发等待流程。

**建议改法和验证点**:

1. 在 `HostDispatchScheduler.__init__` 或 `HostLocalExecutionOptions` 中增加 `wait_adapter_registry` 和可选的 `awaiting_accept_port` 输入
2. `_run_input_builder_for_dispatch` 构造 `ToolRuntimeBuildRequest` 时传入这些依赖
3. 补一条真实 scheduler 级 integration test 证明 waiting path 从生产入口可达

**修复风险（低）**: `DefaultHostToolAwaitingAcceptPort` 可从 `self._transaction_runner` 和 `self._event_log_store` 就地构造；`wait_adapter_registry` 需从 composition root 注入。不改变现有 public API shape。

**严重程度（中）**: 不影响代码正确性（ToolRuntime 正确实现了 awaiting accept），但生产 wiring 断点使 P7 能力在真实路径不可达。不是设计偏离——design.md §20 规定 ToolRuntime 是 awaiting canonical owner，ToolRuntime 实现正确；gap 在于 Host composition root 未把 awaiting dependencies 注入 scheduler。

### D02-Low — RunStartReason 枚举缺少 STEER 和 RECOVERY

**入口/函数**: `RunStartReason` enum

**文件(行号)**: `dayu/host/durable/state.py:114-119`

**输入场景**: steer 或 recovery 启动新 Attempt 时需要 `start_reason=steer` 或 `start_reason=recovery`。

**实际分支**: `RunStartReason` 仅定义 `INITIAL = "initial"`、`QUEUE_PROMOTION = "queue_promotion"`、`RESUME = "resume"`。

**预期行为**: 设计 §7 第 579 行规定 `start_reason` "第一版枚举为 `initial`、`queue_promotion`、`resume`、`steer`、`recovery`"。

**实际行为**: `STEER` 和 `RECOVERY` 缺失。

**直接证据**: `state.py:114-119` vs `design.md:579`。

**影响**: 低。steer 和 recovery 功能尚未实现（分别属于 Phase 8+ 和 Phase 11），当前没有消费者需要这两个枚举值。但设计规定这是"第一版"枚举，提前补上可避免后续实现时遗漏。

**建议改法和验证点**: 添加 `STEER = "steer"` 和 `RECOVERY = "recovery"` 到 `RunStartReason` enum，更新测试中对该 enum 的封闭断言。

**修复风险（低）**: 纯新增枚举值，无消费者。

**严重程度（低）**: 为尚未实现的功能提前准备枚举值；不影响当前正确性。

### D03-Info — dispatch.py 生成 ATTEMPT_RUNNING 治理事实

**入口/函数**: `HostDispatchScheduler._handle_worker_accept` / `_build_attempt_running_event`

**文件(行号)**: `dayu/host/dispatch.py:801-841`, `1108-1141`

**输入场景**: worker accept 后推进 Attempt 状态。

**实际分支**: dispatch.py 生成 `ATTEMPT_RUNNING` canonical 事实（第 832 行）并调用 `terminal_closeout_in_transaction`（第 873 行）。

**预期行为**: 设计 §2 第 48 行规定 "Attempt Dispatch：只消费已提交的 dispatch record / attempt snapshot，负责 LocalProxy / RemoteProxy 派发与 cancel 传播；不得生成治理事实。"

**实际行为**: dispatch 同时承担了 Attempt 状态推进（属于 admission/transition 的职责）和 worker lifecycle closeout。

**直接证据**: `dispatch.py:832` — `event_log_store.append_event(transaction, ...)` with `event_type=_EVENT_TYPE_ATTEMPT_RUNNING`；`dispatch.py:873` — `terminal_closeout_in_transaction(...)`。

**影响**: 无。这是 Phase 5 实现时已确认的范围扩展——为保持 worker accept 与 Attempt 状态推进的原子性而由 dispatch 执行。行为正确，事务内原子性有保证。

**建议改法和验证点**: 可在 `implementation-control.md` 中记录此已知偏差，无需修改代码。

**修复风险（低）**: 不需要修复。

**严重程度（信息性）**: 已知的 Phase 5 实现决策，行为正确，不影响后续 phase。

## Architecture Boundary Verification

### 层依赖方向（UI → Service → Host → Engine）

全部合规。逐项验证：

| 检查项 | 结果 | 证据 |
|--------|------|------|
| Host → Engine contracts | 合规 | `engine_ingest.py`、`local_proxy.py`、`run_input.py` 导入 `dayu.engine.contracts.*`（共享类型：AgentRunRequest, EngineEvent, RunnerSpec 等） |
| Host → Engine execution | 合规 | `local_proxy.py:13` 导入 `dayu.engine.run_agent_messages`（Host 通过 Engine 执行） |
| Engine → Host | 合规 | `dayu/engine/` 无任何 `dayu.host` import |
| Host → service/ui/fins | 合规 | `dayu/host/` 无任何 `dayu.service`/`dayu.ui`/`dayu.fins` import |
| Host → runtime | 合规 | `dispatch.py:83` 导入 `dayu.runtime.lane`（层中立基础设施） |
| runtime → 业务层 | 合规 | `dayu/runtime/` 只导入 `dayu.contracts` 和标准库 |

自动守卫：`tests/host/test_import_boundary.py` 有 7 条自动化 import guard；`tests/runtime/test_import_boundary.py` 守卫 runtime 中立性。

### 公共契约封装

| 检查项 | 结果 |
|--------|------|
| 内部对象未暴露 | 合规 — `DefaultHostToolAwaitingAcceptPort`、`WaitPoller`、`DefaultHostResolveWaitService`、`HostAdmissionService` 等均不在 `__init__.py` 导出 |
| Public API 完整 | 合规 — `__init__.py` 导出全部 13 个 public command + 所有 Phase 7 类型（WaitAdapterKey, HostPayloadRef, 四个 outcome 类型, WaitProviderStatusRef, WaitResolutionSource） |
| `dayu.runtime` 中立 | 合规 — 6 个模块全部只依赖 `dayu.contracts` 和标准库，不承载任何业务/Host/Engine 语义 |

### 禁止文件

未经修改：`dayu/engine/`（implementation）、`dayu/contracts/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、recovery/outbox/audit/tool trace 模块。

## State Machine Conformance

### RunStatus（设计 §12-§13）

全部 9 个状态均已实现且与设计一致：QUEUED, RUNNING, WAITING, CANCELLING, RECOVERING, SUCCEEDED, FAILED, CANCELLED, LOST。无额外未文档化状态。

### AttemptStatus（设计 §13）

全部 8 个状态均已实现：STARTING, RUNNING, SUCCEEDED, FAILED, CANCELLED, SUSPENDED, STEERED, LOST。SUSPENDED 为 Phase 7 新增。

### WaitRecordStatus（设计 §20）

全部 5 个状态：WAITING, RESOLVED, FAILED, CANCELLED, LOST。DDL CHECK 约束一致（`schema.py:506-508`）。

### WaitResumePolicy（设计 §20）

全部 3 个值：POLL, CALLBACK, MANUAL。DDL CHECK 约束一致（`schema.py:478-480`）。

### EventClass（设计 §16）

全部 4 个 class：CANONICAL_FACT, PREVIEW, DIAGNOSTIC, PROJECTION_SIGNAL。

## Key Transition Verification

### cancel_waiting_run_in_transaction（设计 §22）

`run_transition.py:1315-1399` 顺序完全正确：
1. 输入校验 ✓
2. read_run → 检查 WAITING + current_attempt_id ✓
3. read_attempt → 检查 SUSPENDED ✓
4. read_active_wait_records → 确认有 active waits ✓
5. append CANCEL_REQUESTED ✓
6. cancel_active_wait_records_for_run（CAS WAITING→CANCELLED）✓
7. 若 CAS 失败 → 回滚事务 ✓
8. append RUN_CANCELLED ✓
9. cancel_waiting_run_row（CAS WAITING→CANCELLED）✓

不创建 ATTEMPT_CANCELLED（Attempt 已在 SUSPENDED 终态）。cancel_run 和 cancel_session_runs 均委托到同一 `cancel_waiting_run_in_transaction`。

### resume_run_from_waiting_in_transaction（设计 §20-§21）

`run_transition.py:832-912` 顺序完全正确：
1. 输入校验 ✓
2. read_run / read_attempt / read_wait_record ✓
3. append RESUME_REQUESTED ✓
4. append TOOL_RESULT_ACCEPTED ✓
5. mark_wait_record_resolved_row（CAS WAITING→RESOLVED）✓
6. append RUN_STARTED(start_reason=resume) ✓
7. append ATTEMPT_STARTED ✓
8. insert_attempt + resume_waiting_run_row（CAS WAITING→RUNNING）✓

### resolve_wait condition chain（设计 §20）

`waiting.py:600-731` 完全符合设计：
- Terminal wait (RESOLVED/FAILED/LOST): 先尝试 replay；同 key 同 digest → 重放；不同 key + RESOLVED/FAILED → INVALID_STATE（不写 diagnostic）；不同 key + LOST → late diagnostic ✓
- CANCELLED → late diagnostic ✓
- 非 WAITING → late diagnostic ✓
- WAITING + owner Run terminal → late diagnostic ✓
- WAITING + Run active → idempotency check → dispatch to resume/failed/lost ✓

### WaitPoller（设计 §20）

`wait_adapter.py:324-377`：
- 读快照在 read transaction 内 ✓
- adapter 调用在 transaction 外 ✓
- CANCELLED → adapter.abandon_wait()，不调用 resolve_wait ✓
- NotReady → 不调用 resolve_wait ✓
- Ready → 构造 ResolveWaitRequest 调 resolve_wait ✓
- Lost → 同上 ✓
- Adapter 异常 → adapter_errors += 1，不崩溃 ✓

### EngineEvent TOOL_AWAITING/RUN_SUSPENDED（设计 §20）

`engine_ingest.py:721-773`：
- 只写 ENGINE_EVENT_DIAGNOSTIC（DIAGNOSTIC class）✓
- terminal_closeout=False ✓
- 不创建 wait record ✓
- 不调用 terminal_closeout_in_transaction ✓
- 重复 ingest → DUPLICATE ✓
- `_late_rejection_reason` (`engine_ingest.py:1172-1191`) 对 WAITING+SUSPENDED 返回 None（允许通过）✓

### Schema DDL（设计 §20）

`schema.py:459-577` `host_wait_records` DDL：
- status CHECK (5 values) ✓
- resume_policy CHECK (3 values) ✓
- terminal_at ↔ terminal status 配对 ✓
- snapshot triplet 约束 ✓
- one_active_per_run unique index ✓
- active_poll observation index ✓
- external_job index ✓
- 外键（session/run/attempt/execution/event refs）✓
- Schema version 4（全新起库，无迁移）✓

## Design §20 Exit Condition Verification

| 设计要求 | 实现位置 | 状态 |
|----------|----------|------|
| ToolRuntime Host accept path 是 awaiting canonical owner | `waiting.py` DefaultHostToolAwaitingAcceptPort | 合规 |
| Engine tool_awaiting/run_suspended 不能创建 wait state | `engine_ingest.py` `_confirm_waiting_engine_event` — 只 diagnostic | 合规 |
| wait record 是 Host durable state index | `durable/schema.py` + `durable/state.py` | 合规 |
| resolve_wait 是短事务 command | `waiting.py` DefaultHostResolveWaitService — single write transaction | 合规 |
| 幂等范围 (wait_id, idempotency_key) | `waiting.py` `_wait_resolution_scope` | 合规 |
| 同 key 同 outcome 重放，不同 outcome 冲突 | `waiting.py` + `_replay_terminal_resolution_or_none` | 合规 |
| cancelled/lost late result → diagnostic | `waiting.py` `_reject_late_result` | 合规 |
| resolved/failed 不同 key → INVALID_STATE（不写 diagnostic） | `waiting.py:641-649` | 合规 |
| WAITING cancel → cancelled wait records + CANCELLED Run | `run_transition.py` `cancel_waiting_run_in_transaction` | 合规 |
| resume 是同一 Run 内新 Attempt | `run_transition.py` `resume_run_from_waiting_in_transaction` | 合规 |
| RunInputBuilder 从 EventLog canonical facts 重建 messages | `run_input.py` resume message reconstruction | 合规 |
| poll/callback/manual 都走同一 resolve_wait pipeline | `wait_adapter.py` WaitPoller → resolve_wait | 合规 |
| typed outcome envelope | `api.py` 四个 ResolveWaitOutcome 子类型 | 合规 |
| adapter_key 来源明确 | `api.py` WaitAdapterKey typed ref | 合规 |
| snapshot_ref / external_job_id typed ref | `api.py` HostPayloadRef / wait_adapter.py | 合规 |

## Non-goals 验证（设计 §28 + implementation-control.md）

全部 non-goal 均保持未实现：

| Non-goal | 状态 |
|----------|------|
| 不保证外部 job physical cancel | 未实现 — adapter abandon best-effort only |
| 不实现 callback 认证入口完整产品化 | 未实现 — 仅预留 CALLBACK source |
| 不实现远端 worker 自治 resume | 未实现 |
| 不实现 HTTP callback endpoint | 未实现 |
| 不修改 Engine contract | 未修改 |
| 不把 adapter object/callable 放进 durable wait record | 只存 typed refs |
| 不做旧库兼容 | 全新 schema v4 |
| 不实现 recovery scan | Phase 11 |
| 不实现 durable tool trace projection | 后续 phase |
| 不实现 long-term memory | 后续 phase |

## Verification Results

| 命令 | 结果 |
|------|------|
| `pytest tests/host -q` | 391 passed |
| `pyright dayu/host/` | 0 errors, 0 warnings |
| `pyright dayu/ tests/ utils/` | 0 errors, 0 warnings（仅 `reportMissingImports` 为 pytest 搜索路径问题） |
| `git diff --check` | clean |

## Open Questions

无。

## Residual Risk

以下为 P1-P7 已知非目标或后续 phase owner 事项：

1. **D01 (Medium) — Dispatch scheduler 未接入 P7 awaiting wiring**: 当前生产入口无法到达 WAITING 路径。Owner: 需在后续 slice 中完成 wiring。修复方式：在 `HostDispatchScheduler` composition 中注入 `awaiting_accept_port` 和 `wait_adapter_registry`。

2. **D02 (Low) — RunStartReason 缺少 STEER/RECOVERY**: steer 和 recovery 功能尚未实现，当前无消费者。Owner: Phase 8+ steer / Phase 11 recovery。

3. **Callback endpoint / auth / replay**: Phase 7 只预留 `callback` source 和 `resolve_wait` pipeline contract。Owner: 后续 phase。

4. **外部 job physical cancel / revoke**: adapter 只能 best-effort。Owner: 后续 adapter hardening。

5. **Engine contract 不携带 Host accepted wait refs**: P7 只能做 diagnostic confirmation。Owner: 后续 Engine contract 演进。

6. **Poller 后台调度循环 / 退避 / in-flight fencing**: 当前只有 `poll_once()` 单轮。Owner: 后续 runtime hardening。

7. **Recovery scan 对 WAITING Run 处理**: design §27 明确归 Phase 11。

8. **Tool trace projection / late diagnostic 可观测性**: WAIT_LATE_RESULT_REJECTED diagnostic 已写入 EventLog，无 read model 投影。Owner: 后续 projection。

9. **Durable duplicate ledger**: 当前 duplicate governance 为 run-local in-memory。Owner: 后续 duplicate hardening。

10. **`tool_runtime.py` 文件规模（4997 行 / 66 class）**: 后续可拆分子模块。Owner: 后续 refactor。

11. **SHA256 digest 正则重复定义**（`api.py` 和 `codec.py` 各一个，语义完全一致）: 后续可统一复用。Owner: 后续 cleanup。

12. **`retry_run` / `replay_run`**: 当前返回 `UNSUPPORTED_OPERATION`。Owner: 后续 phase。

以上 residual risk 均有明确 owner 或属于已确认 non-goal，无无主风险。

## Verdict

**PASS — 0 DESIGN_VIOLATION, 1 MEDIUM wiring gap (D01), 1 LOW missing future enum value (D02), 1 INFO acknowledged deviation (D03).**

P1-P7 全部实现对 `docs/host/design.md` 设计真源保持高度一致：

- **层依赖方向** UI→Service→Host→Engine 严格正确，无反向依赖。`dayu.runtime` 完全中立。
- **公共契约** 封装良好，内部实现对象不外泄。Phase 7 新增类型（typed outcome envelope、WaitAdapterKey、HostPayloadRef 等）均在 `__all__` 中正确导出。
- **状态机** RunStatus/AttemptStatus/WaitRecordStatus/WaitResumePolicy/EventClass 全部状态均与设计一致，DDL CHECK 约束同步。
- **关键 transition** cancel_waiting_run_in_transaction、resume_run_from_waiting_in_transaction、resolve_wait condition chain、WaitPoller、EngineEvent confirmation 均逐条与设计对齐，EventLog 顺序正确，CAS 失败触发事务回滚。
- **Non-goals** 全部保持未实现，无 scope creep。
- **测试覆盖** 391 passed，0 pyright errors。

3 个 findings 中：D01（dispatch scheduler 未接入 P7 awaiting wiring）是 Medium 级生产 wiring gap，需在后续 slice 中完成 Host composition root 的 awaiting dependency injection。D02/D03 为低/信息性，不阻塞。

设计真源 `docs/host/design.md` 和总控 `docs/host/implementation-control.md` 未被修改，设计合同完整。
