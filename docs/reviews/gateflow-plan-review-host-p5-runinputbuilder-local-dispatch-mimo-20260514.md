# Phase 5 Plan Review: RunInputBuilder 与本地执行 Dispatch

## Review Role

Independent plan reviewer. Review only the Phase 5 handoff implementation-ready plan. Do not modify production code, do not fix findings, do not commit, do not push, do not enter implementation. Write only the review artifact.

## Artifacts Inspected

- `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` — Phase 5 plan
- `docs/host/design.md` — 设计真源（§13.4, §17, §22, §23）
- `docs/host/implementation-control.md` — 实施总控
- `docs/reviews/gateflow-phase-design-re-review-host-p5-controller-adjudication-20260514.md` — controller 裁决
- `docs/reviews/gateflow-phase-design-fix-re-review-host-p5-ds-20260514.md` — DS F1/F2 fix 验证
- `docs/reviews/gateflow-phase-design-fix-re-review-host-p5-mimo-20260514.md` — MiMo F1/F2 fix 验证
- `dayu/host/durable/schema.py` — 当前 dispatch record DDL
- `dayu/host/durable/state.py` — 当前 `DispatchRecordStatus` 枚举
- `dayu/host/durable/run_transition.py` — 当前 cancel / terminal transition helpers
- `dayu/host/admission.py` — 当前 `cancel_run` / `cancel_session_runs`
- `dayu/host/command.py` — 当前 public facade
- `dayu/engine/contracts/engine_events.py` — Engine `EngineEvent` 契约

## Review Lens

1. Plan 是否 code-generation-ready，还是 implementation agent 仍需发明 schema、state transitions、EngineEvent payloads、RunInputBuilder provider set、dispatch race behavior、cancel semantics、terminal closeout、validation 或 docs decisions？
2. 是否满足 Phase 5 目标且不越界进入 ToolRuntime、WAITING、RECOVERING、RemoteProxy、Memory、Context Governance、Observer/Sink 或 Engine contract 变更？
3. 是否正确 carry forward DS F3-F6 与 MiMo observations 作为 plan 决策与 plan review checks？
4. 挑战 slice size、ownership、sequencing、test coverage、pyright/readme 义务、import boundaries 和 overcoupling。

---

## 整体评估

**Plan 整体质量高，code-generation-ready 程度充分。** 6 个 implementation slices 切分合理，每个 slice 有明确的 allowed files、exact changes、tests、validation、stop conditions 和 residual risks。§3 公共契约与 schema 决策覆盖了 DS F3-F6 和 MiMo observations 的所有 plan-gate 检查项。

**无 blocking finding。** 以下 findings 均为 non-blocking，implementation agent 可在实施过程中澄清或修正。

---

## Findings

### F001: `observed_at` 时区约定未明确

**Severity**: observation (non-blocking)

**Direct Evidence**: §3.1 定义 `EngineEventCandidate.observed_at: datetime`，但未指定时区约定。

**Impact**: `datetime` 可以是 naive 或 timezone-aware。如果不同 provider 使用不同时区约定，canonical event identity 派生和去重可能出现不一致。Phase 2 durable schema convention 已固定 UTC ISO-8601 TEXT 微秒精度 + `Z` 后缀，但 `observed_at` 是 Python `datetime` 对象，序列化约定不明确。

**Recommendation**: 在 §3.1 或 §3.5 补充：`observed_at` 必须为 `datetime` 且使用 UTC（`timezone.utc`），与 Phase 2 durable timestamp convention 一致。implementation agent 应在 `EngineEventCandidate` construction 时强制 UTC。

**Blocks plan acceptance**: 否。

---

### F002: Canonical event ID 派生公式未显式定义

**Severity**: observation (non-blocking)

**Direct Evidence**: §3.1 声明 "canonical event id 必须由 `execution_id`、`worker_event_index`、canonical event type、sub-index 派生；preview / diagnostic event id 也必须稳定可去重"，但未给出具体派生公式或 hash 算法。

**Impact**: Implementation agent 需要自行选择派生算法。如果不同 slice 的实现者选择不同算法（例如 string concatenation vs hash），会导致 event id 不稳定或去重失败。虽然 plan 明确了输入要素，但缺少公式可能导致实现分歧。

**Recommendation**: 补充最小派生规则，例如：`event_id = f"{execution_id}:{worker_event_index}:{canonical_type}:{sub_index}"`，或指定 hash digest。如果 plan 认为实现可自行选择，应显式声明 "implementation agent 自行选择稳定派生算法，但必须保证同一 `(execution_id, worker_event_index, canonical_type, sub_index)` 输入产出相同 `event_id`"。

**Blocks plan acceptance**: 否。

---

### F003: `PROVIDER_PROTOCOL_ERROR` payload 中 `raw_payload` 与 `partial_tool_call_count` 映射

**Severity**: observation (non-blocking)

**Direct Evidence**: §3.5 定义 `PROVIDER_PROTOCOL_ERROR` payload 包含 `raw_payload_ref?`、`raw_payload_digest?`、`partial_tool_call_count`。但 Engine `ProviderProtocolErrorData` 的对应字段为 `raw_payload: JsonValue | None` 和 `partial_tool_calls: tuple[PartialToolCallSummary, ...]`。

**Impact**: Plan 正确识别了 Host payload 只存 ref/digest 而非内联 raw payload，但 `partial_tool_call_count` 与 Engine 的 `partial_tool_calls` tuple 之间需要一个 `len()` 映射。这是简单实现细节，但 plan 未显式说明映射关系。

**Recommendation**: 在 §3.5 补充一句：`partial_tool_call_count` 由 `len(engine_event.data.partial_tool_calls)` 派生。`raw_payload_ref` / `raw_payload_digest` 通过 Phase 2 payload descriptor 机制存储 `engine_event.data.raw_payload`。

**Blocks plan acceptance**: 否。

---

### F004: `EngineEvent` 字段枚举遗漏 `occurred_at`

**Severity**: info (non-blocking)

**Direct Evidence**: §1.2 evidence 声明 "`EngineEvent` 只包含 `session_id`、`run_id`、`type`、`data`、`metadata`"。但实际 `EngineEvent` 还有 `occurred_at: datetime` 字段（`engine_events.py:443`）。

**Impact**: 不影响 plan 正确性，因为 plan 不修改 `EngineEvent`，且 `EngineEventCandidate` 的 `observed_at` 是 Host-owned 独立时间戳。但 evidence 陈述与代码事实不完全一致。

**Recommendation**: 修正 §1.2 evidence 为 "`EngineEvent` 包含 `occurred_at`、`session_id`、`run_id`、`type`、`data`、`metadata`，没有 Host Attempt identity"。这是文档准确性修正，不影响实施。

**Blocks plan acceptance**: 否。

---

### F005: `AttemptDispatchSnapshot` 字段完整性

**Severity**: observation (non-blocking)

**Direct Evidence**: §5 P5-S2 定义 `AttemptDispatchSnapshot` 至少包含 `session_id`、`run_id`、`attempt_id`、`execution_id`、`dispatch_record_id`、`execution_target`、policy snapshot、cancellation token。但 `RunInputBuilder.build(attempt_snapshot)` 输出的 `AgentRunRequest` 还需要 `runner_spec`、`runner_options`、`agent_policy`、`tool_schemas`、`tool_executor`。

**Impact**: `runner_spec`、`runner_options`、`agent_policy` 由 `PolicySnapshotProvider` 提供，`tool_schemas` 和 `tool_executor` 由 `ToolSchemaSnapshotProvider` 和 `ToolExecutorProvider` 提供。这些不在 `AttemptDispatchSnapshot` 中而是由 providers 注入。Plan 的设计是正确的——snapshot 只携带最小 durable refs，providers 负责构造具体字段。但 plan 未显式说明 snapshot 与 provider 之间的字段分工。

**Recommendation**: 在 §3.4 补充一句：`AttemptDispatchSnapshot` 携带 durable identity refs 与 policy snapshot refs；`runner_spec`、`runner_options`、`agent_policy`、`tool_schemas`、`tool_executor` 由对应 providers 在 `build()` 时注入，不在 snapshot 中重复。

**Blocks plan acceptance**: 否。

---

### F006: `cancel_session_runs` 幂等 replay 的 "best-effort 再次传播" 语义边界

**Severity**: observation (non-blocking)

**Direct Evidence**: §3.7 声明 "幂等 scope 仍是 `(operation=cancel_session_runs, scope_id=session_id, idempotency_key=request.client_request_id)`" 和 "replay 不追加 facts，但可以 best-effort 再次调用 active registry 取消仍处于 `CANCELLING` 且 execution_id 匹配的 worker"。

**Impact**: 语义清晰，但 "可以 best-effort" 意味着 implementation agent 需要决定是否实际执行该 side effect。如果不执行，处于 `CANCELLING` 的 worker 可能因为首次 cancel propagation 失败而永远挂着（直到 watchdog / Phase 11 LOST policy）。Plan 正确识别了这是 best-effort，但未说明测试是否覆盖该路径。

**Recommendation**: 在 P5-S5 tests 中补充一条：`cancel_session_runs` replay 返回当前 snapshot，不追加 facts；若有仍 active 的 `CANCELLING` worker，best-effort re-propagation 不影响返回值正确性。

**Blocks plan acceptance**: 否。

---

## DS F3-F6 / MiMo Observations 覆盖确认

逐项确认 plan 是否将 design re-review 的 deferred items 转化为 plan 决策和 plan review checks：

| Finding | Plan Coverage | Evidence |
|---|---|---|
| **DS F3** EngineEvent canonical payload 最小字段 | **已覆盖** | §3.5 定义了 `ATTEMPT_RUNNING`、`ATTEMPT_SUCCEEDED`、`RUN_SUCCEEDED`、`ATTEMPT_FAILED`/`RUN_FAILED`、`ATTEMPT_CANCELLED`/`RUN_CANCELLED`、`ATTEMPT_LOST`/`RUN_LOST`、`PROVIDER_PROTOCOL_ERROR` 的完整 payload 字段清单 |
| **DS F4** dispatch diagnostic 列 | **已覆盖** | §3.2 定义了 9 个新增 diagnostic columns（`waiting_for_lane_at`、`lane_name`、`lane_claim_id`、`lane_owner_id`、`lane_acquired_at`、`dispatching_at`、`worker_accepted_at`、`worker_accept_event_id`、`worker_accept_event_sequence`），并为每个 dispatch 状态定义了 nullability/check 规则 |
| **DS F5** RunInputBuilder real vs noop provider | **已覆盖** | §3.4 明确枚举 4 个 real providers（`CurrentRunFactProvider`、`SessionContinuityProvider`、`SceneParameterProvider`、`PolicySnapshotProvider`）和 4 个 noop providers（`MemorySnapshotProvider`、`CompactArtifactProvider`、`ToolSchemaSnapshotProvider`、`ToolExecutorProvider`），并定义了每个 noop 的返回语义 |
| **DS F6** `cancel_session_runs` partial completion idempotency | **已覆盖** | §3.7 定义了 supported subset、幂等 scope、replay 行为、partial completion 语义、post-commit propagation |
| **MiMo F-O1** `dispatching` 最终 record 状态 | **已覆盖** | §3.2 明确 "`dispatching` 在 WorkerProxy accept 后仍保留为 dispatch record 的最终非取消状态"；§3.3 明确 "record worker accept refs on dispatch record, status remains dispatching"；不新增第五个状态 |
| **MiMo F-O4** context compaction 处理 | **已覆盖** | §3.5 明确 "`context_compaction_requested`：允许 `budget_state=None`，不得视为协议错误；append diagnostic，随后以 `ATTEMPT_FAILED` / `RUN_FAILED` 收口，reason=`unsupported_recovery_policy`，`unsupported_later_owner="phase10"`" |
| **MiMo F-O5** `usage_reported` 处理 | **已覆盖** | §3.5 明确 "`usage_reported` Phase 5 决策：不映射为 canonical fact；append `EventClass.PROJECTION_SIGNAL` event_type `USAGE_REPORTED`"，并定义了 payload 字段 |

**结论**：所有 7 个 deferred items 均已在 plan 中转化为具体决策和检查项。

---

## Non-Goals 边界确认

逐项确认 plan 是否正确保持在 Phase 5 边界内：

| 禁止项 | Plan Compliance | Evidence |
|---|---|---|
| 不修改 Engine `EngineEvent` contract | **合规** | §1.3 明确列出；§3.1 定义 Host-owned `EngineEventCandidate` 包装 `EngineEvent` |
| 不实现 RemoteProxy / RemoteStub | **合规** | §1.3 明确列出；§2.3 禁止修改 Engine contracts |
| 不实现 ToolRuntime governance | **合规** | §3.4 `ToolSchemaSnapshotProvider` 返回空 tuple，`ToolExecutorProvider` 返回 `NoToolExecutor` |
| 不实现 wait record / `resolve_wait` | **合规** | §3.5 `tool_awaiting` / `run_suspended` 只做 diagnostic + FAILED closeout |
| 不实现 Memory projection | **合规** | §3.4 `MemorySnapshotProvider` 返回空 stable layer |
| 不实现 Context Governance | **合规** | §3.5 `context_compaction_requested` 只做 diagnostic + FAILED |
| 不实现 Observer / Sink | **合规** | §3.5 `usage_reported` 只做 projection_signal |
| 不进入 `RECOVERING` | **合规** | §3.6 terminal closeout 表明确所有异常路径终态为 `FAILED` 或 `LOST`，无 `RECOVERING` |
| 不把 dispatch record 当 lease / fencing | **合规** | §3.2 明确 "dispatch record 只表达 dispatch 诊断与重复派发抑制" |

---

## Slice Sequencing 与依赖分析

```text
P5-S1 (schema + transition primitives)
  -> P5-S2 (RunInputBuilder providers)  [independent of S1]
  -> P5-S3 (dispatch scheduler + LocalProxy)  [depends on S1 schema, S2 RunInputBuilder]
  -> P5-S4 (EngineEvent ingest + terminal closeout)  [depends on S1 transitions, S3 LocalProxy]
  -> P5-S5 (active cancel + session-scope cancel)  [depends on S1, S3, S4]
  -> P5-S6 (integration + docs)  [depends on all above]
```

S1 和 S2 可以并行。S3 依赖 S1 + S2。S4 依赖 S1 + S3。S5 依赖 S1 + S3 + S4。S6 是收口。

Plan 的 slice 顺序（S1 → S2 → S3 → S4 → S5 → S6）是合理的串行路径。S2 与 S1 之间没有代码依赖（S2 的 `run_input.py` 是新文件，只读取 EventLog 和 durable state），理论上可并行，但 plan 按串行组织不影响正确性。

---

## Test Coverage 评估

每个 slice 的 test 覆盖与 plan 声明的 test matrix 一致：

- **P5-S1**: schema nullability、state transition chain、cancel boundaries、CAS guards — 覆盖充分。
- **P5-S2**: message determinism、continuity provider ordering、noop providers、no-tool request — 覆盖充分。
- **P5-S3**: scheduler lifecycle、lane acquire timeout、durable recheck loser、pre-call cancel race、handle close — 覆盖充分。
- **P5-S4**: terminal event mapping、recoverable FAILED、cancel CANCELLED、compaction diagnostic、usage signal、EOF/LOST、duplicate rejection、stale rejection — 覆盖充分。
- **P5-S5**: pre-worker direct cancel、active worker cancel propagation、final_answer vs cancel race、session-scope partial completion、replay、WAITING/RECOVERING guard — 覆盖充分。
- **P5-S6**: end-to-end fake worker scenarios（success/failure/EOF/crash/cancel）、queue promotion、import boundary — 覆盖充分。

**唯一 gap**: P5-S5 缺少 `cancel_session_runs` replay 后 best-effort re-propagation 的测试（见 F006）。不阻塞。

---

## Import Boundary 评估

Plan 的 import 边界设计正确：

- `dayu.host.run_input` / `dispatch` / `local_proxy` / `engine_ingest` 可以依赖 `dayu.engine.contracts`（`EngineEvent`、`AgentRunRequest` 等） — 正确，Host → Engine 方向允许。
- `dayu.engine` 不 import `dayu.host` — plan 未修改 Engine 代码，保持。
- `dayu.runtime` 不 import `dayu.host` / `dayu.engine` — plan 不修改 `dayu.runtime`，保持。
- 新增模块之间的依赖：`dispatch.py` → `local_proxy.py`（worker factory protocol）、`engine_ingest.py` → `local_proxy.py`（`EngineEventCandidate`）、`command.py` → `dispatch.py` + `local_proxy.py` + `run_input.py` + `engine_ingest.py` — 依赖方向合理，从 composition root 向下。

---

## Overcoupling 检查

- `LocalEngineEnvelope` 是 Host-owned 内部类型，不进入 Engine contracts — 正确。
- `EngineEventCandidate` 是 Host ingest boundary 类型，不暴露给 Engine — 正确。
- `AttemptDispatchSnapshot` 是 RunInputBuilder 内部类型，不暴露为 public API — 正确。
- Dispatch scheduler 只通过 `wake_dispatch(PendingDispatchRecord)` 接收通知，不直接读取 admission service — 正确。
- Cancel path 不直接操作 lane token，只提交 facts 并 wake scheduler — 正确，避免了 cancel 与 scheduler 的 ownership 竞争。

未发现 overcoupling。

---

## Final Verdict

| Category | Result |
|---|---|
| Blocking findings | **0** |
| Non-blocking findings | 4 (F001-F004) |
| Observations | 2 (F005-F006) |
| DS F3-F6 coverage | **全部覆盖** |
| MiMo observations coverage | **全部覆盖** |
| Non-goals compliance | **全部合规** |
| Code-generation-ready | **是** — implementation agent 可直接按 plan 生成代码，无需自行发明 schema、state transitions、payloads、provider set、dispatch race behavior、cancel semantics 或 terminal closeout policy |
| Slice sequencing | **合理** |
| Test coverage | **充分**（1 个 minor gap） |
| Import boundary | **正确** |
| Overcoupling | **未发现** |

**Gate recommendation: Plan 通过，可以进入 implementation gate。** 4 个 non-blocking findings 和 2 个 observations 可在 implementation 过程中澄清或修正，不阻塞 plan acceptance。
