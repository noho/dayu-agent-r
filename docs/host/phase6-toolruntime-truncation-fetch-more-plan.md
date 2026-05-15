# Host Phase 6 ToolRuntime / Truncation / fetch_more Plan

- **current gate**: Phase 6 handoff implementation-ready plan
- **work unit**: ToolRuntime / Truncation / fetch_more / Duplicate Governance
- **plan status**: implementation-ready
- **blocking question count**: 0
- **artifact path**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`

本文档是 Gateflow-governed handoff plan。implementation agent 只能按本文档指定的 contract、文件边界、slice、测试和 stop condition 实施；不得重新设计 Host / Engine 分层、等待状态机、Remote wire protocol、业务工具发现、工具 trace projection、recovery 或 durable cursor 机制。

## 1. Goal / Motivation / Non-goals

### 1.1 Goal

Phase 6 落地 Host-owned ToolRuntime，使 Engine 只能通过 Host-governed `ToolExecutor` 执行工具；工具结果必须先通过 Host accept barrier durable accepted，收到 accepted ack 后才允许返回给 Engine 继续推理。同期落地 attempt-local effective `ToolBundle`、run-scoped `TruncationManager`、普通工具路径的 `fetch_more`、run-local duplicate governance、side-effect / paid tool idempotency policy、最小 `ToolTraceDiagnosticEmitter` interface。

### 1.2 Motivation Judgment

动机成立，严重性评估没有被高估。

Phase 5 已完成本地 Engine 执行闭环，但仍是 no-tool / fake tool 边界。若 Phase 6 不固定 ToolRuntime ports、effective `ToolBundle` 同源、Host accept candidate / ack / reject / timeout、run-scoped truncation / `fetch_more` 与 duplicate governance，implementation agent 会被迫自行选择 LLM 是否可消费未确认工具结果、是否进入 `WAITING`、是否新增 durable cursor、是否让 Engine 理解 Host 工具治理。这些都是 Host 状态治理和分层边界问题，必须在计划中收敛。

### 1.3 Non-goals

Phase 6 不做以下事项：

- 不让 Engine 理解 Host tool governance；Engine 仍只消费 `ToolExecutor`、`ToolSchema`、`BatchToolExecutionRequest`、`BatchToolExecutionOutcome`。
- 不实现 wait record、`WAITING`、`resolve_wait`、wait adapter、外部 job cancel handle 或长耗时 awaiting 资源收口。
- 不实现 durable cursor descriptor、专用 cursor table、跨 restart / recovery / replay / memory retrieval 的 `fetch_more` 续读。
- 不修改 Remote wire protocol，不实现 RemoteProxy / RemoteStub 等价 ack 传输。
- 不扫描业务工具，不导入 `dayu.fins`，不实现 ToolsDiscovery / ScenePrepare provider registry。
- 不把显式参数塞进 `extra payload` 或无结构 metadata bag。
- 不使用 `Any`、`object`、无类型参数、无类型返回值作为新增 contract 目标。
- 不写兼容旧 schema / 旧接口的 re-export、wrapper、facade 或兼容读取。
- 不实现完整 Tool Trace / Audit / Outbox projection；Phase 6 只定义 diagnostic emitter interface 与 diagnostic refs。
- 不实现跨 Run / 跨 Session duplicate ledger；第一版只做 run-local in-memory duplicate index。

## 2. Direct Evidence

- `docs/host/implementation-control.md` Phase 6 目标明确为落地 Host-owned ToolRuntime、effective `ToolBundle`、Host accept barrier、`TruncationManager`、`fetch_more` 与同 Run 语义级重复工具调用治理。
- `docs/host/implementation-control.md` Phase 6 前置条件要求 Phase 5 本地执行闭环和 Phase 2 payload descriptor / EventLog append primitive 已完成。
- `docs/host/implementation-control.md` Phase 6 进入条件要求确认 ToolRuntime ports、accept idempotency key、effective `ToolBundle` 与 run-scoped truncation / `fetch_more` 的最小 typed contract。
- `docs/host/design.md` “Tool fact accept ack 语义”明确 `scope_kind=tool_fact_accept`，`scope_id` 至少绑定 `attempt_id` 与 `tool_call_id`，`semantic_input_digest` 至少覆盖 tool identity、normalized arguments digest、tool fact kind、result / payload digest、policy decision digest 与 truncation metadata digest。
- `docs/host/design.md` 同一段明确 ack timeout 不能把 tool result 返回给 Engine；Phase 6 第一版采用有限 accept retry，仍未确认时返回 governed tool error，不创建 wait record，不进入 `WAITING`，不触发 recovery。
- `docs/host/design.md` §18.1 明确 attempt-local effective tool view 是 RunInputBuilder 暴露 schemas 与 ToolRuntime callable dispatch 的单一真源；Phase 6 不为该 invariant 引入额外 durable snapshot 机制。
- `docs/host/design.md` §18.2 明确 ToolRuntime 必须拆成 ToolBundle/schema projection、dispatcher、policy decision、truncation / fetch_more、awaiting placeholder、duplicate governance、Host accept、`ToolTraceDiagnosticEmitter` 等稳定 ports。
- `docs/host/design.md` §18.2 明确工具事实必须先交给 Host durable accepted，收到 accepted ack 后 ToolRuntime 才能把结果返回给 Engine；EngineEvent ingest 不能替代 ToolRuntime accept path 写工具 canonical facts。
- `docs/host/design.md` §18.3 明确 duplicate governance 属于 Host / ToolRuntime，第一版只做同 Run、run-local deterministic duplicate key；`reuse` 引用 prior accepted result，不伪造新的工具事实。
- `docs/host/design.md` §19 明确 `fetch_more` 是 Host / ToolRuntime 内置 framework tool，但必须作为普通 tool 暴露和执行，不能有 Host / Engine 特化分支。
- `docs/host/design.md` §19 明确 Phase 6 cursor / `scope_token` 是 Run-scoped、short-lived、ToolRuntime-local capability，不承诺跨 Run、跨 Session、Host restart、Attempt `LOST` / recovery、replay 或长期 memory retrieval 后继续可用。
- `docs/reviews/host-phase6-design-discussion-controller-adjudication-20260515.md` 裁决 BQ1 / BQ2 为 accepted design blocker，已写回 ack timeout 默认治理动作与 accept idempotency mapping。
- `docs/reviews/host-phase6-design-discussion-controller-adjudication-20260515.md` 裁决 BQ3 / BQ4 降级为 implementation invariant / algorithm test requirement，明确不要重型 durable effective bundle snapshot 或 durable cursor descriptor。
- `docs/reviews/host-phase6-design-discussion-controller-adjudication-20260515.md` 裁决 BQ5 为 Phase 6 只保留 awaiting placeholder / unsupported；BQ6 拆分为 side-effect / paid policy 属于 P6，long-running / external job awaiting 属于 P7。

## 3. Public / Internal Contract Decisions

### 3.1 Layer Boundary

Host 是 tool governance owner。Engine contract 不改；Engine 不导入 Host，不读取 Host durable store，不理解 duplicate policy、accept barrier、truncation cursor 或 `fetch_more` implementation。Host 不导入业务工具包，只接收 construction-time `HostToolingOptions.business_tool_bundle`。

新增 Host 模块必须位于 `dayu/host/`。公共跨层协作只能复用 `dayu.contracts` 中已有 `ToolBundle`、`ToolDefinition`、`ToolCallable`、`ToolSchema`、`ToolTruncateSpec`、`ToolExecutor`、`BatchToolExecutionRequest`、`ToolExecutionOutcome` 等类型；不得把 Host-only governance 类型下放到 `dayu.contracts`，除非 implementation 证明 Engine 与 ToolRuntime 共同需要且不会泄漏 Host 状态。

### 3.2 ToolRuntime Ports

Phase 6 新增 `dayu/host/tool_runtime.py`，内部定义下列 typed ports / dataclasses。所有类、模块、函数必须有中文 docstring，签名禁止 `Any`、`object`、无类型参数、无类型返回值。

- `ToolRuntimeFactory`
  - 输入：`ToolRuntimeBuildRequest`。
  - 输出：`ToolRuntimeHandle`，同时暴露 `tool_schemas` 与 `tool_executor`，且二者来自同一个 `EffectiveToolBundle` 对象。
- `EffectiveToolBundleBuilder`
  - 输入：business `ToolBundle`、`HostToolingOptions.source_refs`、`FrameworkToolPolicyView`、`TruncationManager | None`、policy snapshot。
  - 输出：`EffectiveToolBundle`。
  - 负责 reserved name conflict、防御性 digest、framework tool injection、schema projection。
- `ToolDispatcher`
  - 输入：单个 `ToolCallRequest`、`BatchToolExecutionContext`。
  - 输出：`ToolExecutionOutcome`。
  - 只做 callable lookup / invocation / exception normalization；不写 EventLog。
- `ToolRuntimePolicyPort`
  - 输入：attempt snapshot、tool definition、call、duplicate state。
  - 输出：`ToolPolicyDecision`。
  - 覆盖 read-only、side-effect、paid、required tool idempotency key、replay no-tool defense、awaiting unsupported。
- `TruncationPort`
  - 输入：tool name、`ToolExecutionOutcome`、`ToolTruncateSpec | None`、call scope。
  - 输出：`TruncationAppliedOutcome`，包含 possibly truncated outcome 与 cursor hint。
- `DuplicateGovernancePort`
  - 输入：tool identity、normalized arguments digest、optional semantic key、prior accepted refs。
  - 输出：`DuplicateDecision`。
- `HostToolFactAcceptPort`
  - 输入：`ToolFactAcceptCandidate`。
  - 输出：`ToolFactAcceptResult = ToolFactAcceptedAck | ToolFactRejectedAck | ToolFactAcceptTimedOut`。
  - 这是唯一可追加工具 canonical facts 的入口。
- `ToolTraceDiagnosticEmitter`
  - 输入：`ToolTraceDiagnosticRecord`。
  - 输出：`ToolTraceDiagnosticRef`。
  - 不 append EventLog，不写 trace 文件，不更新 Run / Attempt。

### 3.3 Effective ToolBundle

`EffectiveToolBundle` 是 attempt-local runtime object，不是 durable snapshot 表。它至少包含：

- `business_bundle: ToolBundle`
- `definitions_by_name: Mapping[str, ToolDefinition]`
- `tool_schemas: tuple[ToolSchema, ...]`
- `truncate_specs_by_name: Mapping[str, ToolTruncateSpec]`
- `source_refs: tuple[ToolBundleSourceRef, ...]`
- `enabled_framework_tools: frozenset[FrameworkToolName]`
- `injected_framework_tool_names: frozenset[FrameworkToolName]`
- `business_bundle_digest: str`
- `effective_schema_digest: str`
- `policy_snapshot_digest: str | None`

Digest 只用于诊断、trace、EventLog payload 解释和测试，不是防止普通装配 bug 的重型 durable snapshot。RunInputBuilder 的 tool schema provider 与 ToolExecutor provider 必须持有同一个 `ToolRuntimeHandle` 或同一个 `EffectiveToolBundle` 派生对象；测试必须证明 `fetch_more` 注入后 schema projection 与 callable dispatch 同源。

### 3.3.1 Tool Execution Mode / RunInputBuilder Boundary

Phase 6 第一版必须在 Host dispatch / RunInputBuilder construction 边界显式传入 typed enum `ToolExecutionMode` 或等价类型，禁止 RunInputBuilder 通过 provider 是否为空、schema 数量或 replay 副作用反推工具模式。

Required modes:

- `TOOL_ENABLED`: 普通 initial / queue promotion / resume 等允许工具的 Attempt。RunInputBuilder 暴露 effective tool schemas，并提供来自同一 `ToolRuntimeHandle` 的 executor。
- `NO_TOOL_REPLAY`: replay Attempt。RunInputBuilder 不暴露 tool schemas，executor 使用 no-tool guard；ToolRuntime 仍保留 defense-in-depth 拒绝意外工具调用。
- `NO_TOOL_DISABLED`: Phase 5 fake / no-tool 禁用路径或明确禁用工具的 Attempt。RunInputBuilder 不暴露 tool schemas，executor 使用 `NoToolExecutor`。

If implementation chooses to add this mode to `AttemptDispatchSnapshot`, that is an approved Host public/internal typed contract change for P6-S1 and must be covered by tests. If implementation can keep it as a dispatch-local construction argument without weakening replay/no-tool evidence, no `AttemptDispatchSnapshot` change is required.

`PolicySnapshot.__post_init__` must only validate policy reference consistency and typed field coherence; it must not unconditionally reject `allow_tool_calls=True`. The no-tool hard check currently represented by `_validate_no_tool_snapshot` must be split or made conditional:

- no-tool validation runs only for `NO_TOOL_REPLAY` / `NO_TOOL_DISABLED` and requires `disable_tools=True`, empty tool schemas and `allow_tool_calls=False`;
- tool-enabled validation runs only for `TOOL_ENABLED` and requires `disable_tools=False`, `allow_tool_calls=True`, and schema/executor providers derived from the same `ToolRuntimeHandle`.

`DefaultSceneParameterProvider` must derive system-message tool status from `ToolExecutionMode` plus policy / tool snapshot. It must not output `tools=disabled` for `TOOL_ENABLED`; replay/no-tool scopes must still express that tools are disabled.

### 3.4 ToolExecutor Wrapper

ToolRuntime implements `ToolExecutor.execute(request: BatchToolExecutionRequest) -> BatchToolExecutionOutcome`。执行顺序固定：

1. 校验 request context 与 attempt snapshot 的 `session_id` / `run_id` / execution scope 一致。
2. 对每个 call 按输入顺序计算 normalized arguments digest 与 duplicate key。
3. 先执行 policy / duplicate governance；若决策为 governed rejection、reuse、hint、require_justification 或 hard_stop，按决策构造 candidate 或 governed outcome，不调用业务 callable。
4. 对 `allow` 的普通工具调用，调用 `ToolDispatcher`。
5. 如果返回 `ToolAwaitingOutcome`，Phase 6 必须转为 `ToolFailedOutcome`，policy decision 使用 `governed_error` 并携带 `unsupported_awaiting` reason，不创建 wait record、不进入 `WAITING`。
6. 对 completed / failed / cancelled outcome 应用 truncation policy。
7. 构造 `ToolFactAcceptCandidate`，通过 `HostToolFactAcceptPort` 有限 retry。
8. 只有收到 `ToolFactAcceptedAck` 后，才把对应 `ToolExecutionOutcome` 放入返回给 Engine 的 `BatchToolExecutionOutcome`。
9. `ToolFactRejectedAck` 或 retry 后 `ToolFactAcceptTimedOut` 必须返回 governed tool error，不得返回原始业务结果。

批内一个 call 的 accept failure 不得让其它已 accepted call 的事实回滚。Engine 侧后续是否继续由既有 Engine tool outcome handling 决定；Host truth 是每条 accepted tool fact 的 EventLog。

### 3.5 Host Accept Candidate / Ack / Reject / Timeout

`ToolFactAcceptCandidate` 最小字段：

- `session_id: str`
- `run_id: str`
- `attempt_id: str`
- `execution_id: str`
- `iteration_id: str`
- `tool_call_id: str`
- `tool_name: str`
- `tool_schema_digest: str`
- `tool_identity_digest: str`
- `normalized_arguments_digest: str`
- `tool_fact_kind: ToolFactKind`
- `outcome_digest: str`
- `payload_digest: str`
- `payload_ref: HostPayloadRef | None`
- `truncation: ToolTruncationFact | None`
- `duplicate_key: str | None`
- `duplicate_decision: DuplicateDecisionKind | None`
- `reuse_prior_event_refs: tuple[HostEventRef, ...]`
- `policy_decision: ToolPolicyDecision`
- `tool_idempotency_key: str | None`
- `diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]`
- `accept_idempotency_key: str`
- `semantic_input_digest: str`

`ToolFactKind` 至少覆盖 `completed`、`failed`、`cancelled`、`reuse`、`governed_error`。`awaiting` 在 Phase 6 只能映射为 canonical `governed_error`；`unsupported_awaiting` 只允许作为 policy reason / diagnostic reason，不作为 canonical wait fact 或 `ToolFactKind`。

`ToolFactAcceptCandidate.__post_init__` 必须按 `ToolFactKind` 校验必填字段，禁止语义不完整的 candidate 进入 accept path：

| `ToolFactKind` | 必填字段 | 必须为空或受限字段 |
|---|---|---|
| `completed` | `payload_digest`、`outcome_digest`、`policy_decision`、`semantic_input_digest`；如结果外置则必须有 `payload_ref` | `reuse_prior_event_refs` 可为空；`duplicate_decision` 仅在 duplicate port 已产生决策时填写 |
| `failed` | `outcome_digest`、`policy_decision`、`semantic_input_digest` | `payload_ref` 仅在失败详情外置时允许；不得携带 prior reuse refs |
| `cancelled` | `outcome_digest`、`policy_decision`、`semantic_input_digest` | `payload_ref` 仅在取消详情外置时允许；不得携带 prior reuse refs |
| `reuse` | `duplicate_key`、`duplicate_decision=reuse`、非空 `reuse_prior_event_refs`、`policy_decision`、`semantic_input_digest` | 不得携带新的 result `payload_ref`；不得生成新的 `TOOL_RESULT_ACCEPTED` |
| `governed_error` | `outcome_digest`、`policy_decision`、`semantic_input_digest` | `payload_ref` 仅在 governed error 详情外置时允许；`unsupported_awaiting` 只能作为 policy reason |

`__post_init__` 还必须校验 `accept_idempotency_key` 与 `semantic_input_digest` 非空且格式稳定；`tool_call_id`、`attempt_id`、`execution_id`、`iteration_id`、`tool_name`、`tool_schema_digest`、`tool_identity_digest`、`normalized_arguments_digest` 对所有 kind 均为必填。`duplicate_decision` 为 `reuse` / `hint` / `require_justification` / `hard_stop` 时必须有对应 `duplicate_key`；普通 allow 可为空或记录 allow 决策，但不能缺失 policy decision。

`ToolFactAcceptedAck` 最小字段：

- `accepted_event_refs: tuple[HostEventRef, ...]`
- `tool_fact_id: str`
- `tool_call_requested_event_ref: HostEventRef`
- `tool_call_governed_event_ref: HostEventRef | None`
- `tool_result_event_ref: HostEventRef | None`
- `result_payload_ref: HostPayloadRef | None`
- `result_digest: str`
- `reuse_prior_event_refs: tuple[HostEventRef, ...]`
- `diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]`
- `idempotency_record_ref: str`

`ToolFactRejectedAck` 最小字段：

- `reason_code: ToolAcceptRejectReason`
- `message: str`
- `diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]`
- `retryable: bool`

`ToolFactAcceptTimedOut` 最小字段：

- `attempt_count: int`
- `last_error_code: str | None`
- `diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]`

有限 retry 的具体次数与 backoff 必须是 named policy fields，例如 `ToolAcceptRetryPolicy(max_attempts: int, backoff_seconds: float)`；禁止魔法数字散落。retry 只针对 accept ack 丢失 / transient timeout，不针对 idempotency conflict、CAS conflict、schema mismatch、explicit reject。

### 3.6 TruncationManager / fetch_more

`TruncationManager` 是 run-scoped、short-lived、ToolRuntime-local capability manager。它不写 durable cursor table，不承诺跨 restart。最小类型：

- `ToolTruncationCursor`
  - `cursor_id: str`
  - `scope_token_digest: str`
  - `session_id: str`
  - `run_id: str`
  - `attempt_id: str`
  - `tool_call_id: str`
  - `tool_name: str`
  - `strategy: ToolTruncationStrategy`
  - `created_at: datetime`
  - `expires_at: datetime`
  - `remaining_ref: TruncatedRemainderRef`
  - `single_use: bool`
  - `used_at: datetime | None`
- `TruncatedRemainderRef`
  - strict union/dataclass set for text chars, text lines, list items, binary bytes.
  - No `Any` / `object`; payload values use `JsonValue` or typed `str` / `tuple[str, ...]` / `tuple[JsonValue, ...]`.
- `FetchMoreRequest`
  - `cursor: str`
  - `scope_token: str`
  - `limit: int | None`
- `FetchMoreResult`
  - returns ordinary `ToolCompletedOutcome` or `ToolFailedOutcome`.

`TruncationManager` construction must receive `truncate_specs_by_name: Mapping[str, ToolTruncateSpec]` from the same `EffectiveToolBundle.truncate_specs_by_name` used by schema projection and dispatcher. `TruncationPort` may still receive the selected `ToolTruncateSpec | None` per call, but that spec must be looked up by tool name from the effective bundle / manager, not recomputed from business definitions elsewhere.

Cursor validation must cover run scope, token digest, TTL, single-use, missing cursor, scope mismatch, artifact / remainder digest mismatch. Every failure returns ordinary tool error result through normal ToolRuntime / accept path; it must not trigger recovery or wait record.

`fetch_more` injection rules:

- Business `ToolBundle` cannot define `fetch_more`; existing `HostToolingOptions` conflict validation remains source of truth.
- If `FrameworkToolPolicyView.enabled_framework_tools` includes `FETCH_MORE` and `TruncationManager` is enabled, `EffectiveToolBundleBuilder` injects a framework `ToolDefinition` named `fetch_more`.
- The injected callable captures a typed `TruncationPort` or `TruncationManager` dependency; this is ordinary callable dependency injection.
- RunInputBuilder schemas and ToolRuntime dispatcher both use the resulting same `EffectiveToolBundle`.

### 3.7 Duplicate Governance

Duplicate governance is run-local only. It maintains in-memory accepted / governed index keyed by:

- tool name / version / schema digest;
- normalized arguments digest;
- optional tool-provided semantic key;
- accepted result digest / evidence anchor.

`index_in_iteration` is explicitly excluded from the duplicate key. Two calls in the same iteration with the same tool identity and same normalized arguments must still enter duplicate governance; policy decides `allow` / `reuse` / `hint` / `require_justification` / `hard_stop`. The LLM output order is diagnostic context, not semantic uniqueness.

Decision matrix:

- `allow`: execute tool and accept result.
- `reuse`: do not execute callable; accept governance event referencing prior accepted event refs; return a tool result message derived from prior accepted result without creating a new `TOOL_RESULT_ACCEPTED`.
- `hint`: append / accept `TOOL_CALL_GOVERNED` with hint; return governed tool error or guidance-shaped result according to policy; do not execute callable unless policy explicitly says continue.
- `require_justification`: accept governance event and allow execution only if the model supplied a structured justification in arguments or configured policy says the next round can carry justification. If no justification channel exists in current tool schema, default to `hint` rather than inventing extra payload.
- `hard_stop`: governed stop; no callable execution; return governed tool error to Engine and record diagnostic. Attempt terminal policy beyond tool outcome remains existing Engine / Host ingest behavior; P6 must not invent retry / replay.

`reuse` must not fabricate a fresh tool result fact. It records governance with prior refs and returns an Engine-consumable outcome only after Host accepts that governance decision. Tests must assert EventLog has no second `TOOL_RESULT_ACCEPTED` for reuse.

### 3.8 Side-effect / Paid Policy

Phase 6 first version supports:

- read-only tools without tool idempotency key;
- side-effect or paid tools only when policy declares an idempotency key requirement and the call provides a valid `tool_idempotency_key` via a typed policy/call binding.

If implementation cannot derive `tool_idempotency_key` from existing `ToolDefinition` / `ToolCallRequest` without an untyped bag, it must add a Host-internal `ToolRuntimePolicyView` keyed by tool name, not mutate Engine request or stuff explicit parameters into metadata. Missing required key returns governed rejection before callable execution. Long-running external job id、cancel handle、await adapter metadata are P7 owner and must not appear in P6 accepted facts except as diagnostic refs when already produced by a fake test tool.

### 3.9 Awaiting / Replay Guards

Awaiting:

- ToolRuntime may observe `ToolAwaitingOutcome` because Engine contract supports it.
- Phase 6 maps it to `ToolFailedOutcome` with governed error message.
- Canonical fact kind is `governed_error`; `unsupported_awaiting` is only a policy reason / diagnostic reason and must not become a canonical `ToolFactKind`.
- No `TOOL_AWAITING`, no `RUN_WAITING`, no `ATTEMPT_SUSPENDED`, no wait record, no `WAITING`, no `resolve_wait`.

Replay:

- Primary defense remains RunInputBuilder: replay Attempts do not expose tool schemas.
- RunInputBuilder selects this path through explicit `ToolExecutionMode.NO_TOOL_REPLAY`, not implicit provider absence.
- Defense in depth: ToolRuntime must reject any tool call marked as replay/no-tool execution scope with hard stop or governed tool error and diagnostic.
- P6 does not implement replay orchestration; it only supplies the guard path and tests.

## 4. Durable / EventLog / Idempotency Decisions

### 4.1 Durable Foundation

Phase 6 must use Phase 2 foundation only:

- existing Host SQLite durable DB;
- existing transaction runner;
- existing EventLog append / read primitives;
- existing payload descriptor / artifact storage;
- existing idempotency primitive.

### 4.2 Schema Decision

No new durable table is allowed for Phase 6.

Current EventLog `append_event` does not perform global closed-set validation for `event_type`; P6 normally does not need a schema version bump just to append new `TOOL_*` event types. Allowed schema/code changes are limited to adding tool canonical event payload types / codecs / payload validators if the current implementation has a payload shape registry that requires explicit registration. If such a validator requires schema code updates, it is P6 owner because tool facts are the core canonical output of ToolRuntime accept barrier. The implementation must still follow fresh schema rules; no old DB migration compatibility is required.

Explicitly forbidden:

- durable cursor descriptor table;
- session-scope duplicate ledger table;
- wait record table;
- remote ack table;
- tool trace projection table;
- business tool registry table.

### 4.3 EventLog Facts

P6-owned EventLog payloads:

- `TOOL_CALL_REQUESTED`: records model/tool call intent after Host validates attempt identity.
- `TOOL_CALL_GOVERNED`: records policy / duplicate decision, reason, scope, prior refs.
- `TOOL_RESULT_ACCEPTED`: records accepted completed / failed / cancelled / governed error result.
- `TOOL_TERMINAL_RESULT`: only if current EventLog model already separates terminal tool outcome from result accepted; otherwise implementation must document that `TOOL_RESULT_ACCEPTED` covers the Phase 6 terminal result. Do not invent duplicate facts for the same meaning.

`TOOL_AWAITING` is not P6-owned. It remains P7.

Event payloads must use explicit structured fields for tool identity, arguments digest, result digest, payload ref, truncation metadata, duplicate decision, policy decision, diagnostic refs and accepted ack refs. They must not hide explicit fields in `extra payload`.

### 4.3.1 EngineEvent Tool Events Are Preview / Diagnostic

EngineEvent ingest must not become a canonical tool fact writer in Phase 6. Engine-emitted `TOOL_CALL_REQUESTED`, `TOOL_RESULT_ACCEPTED`, `TOOL_CALLS_BATCH_READY`, `TOOL_CALLS_BATCH_DONE`, `TOOL_CALL_DELTA` and equivalent tool preview events must remain `PREVIEW` / `DIAGNOSTIC` mappings only. If current mapping treats any of these as canonical facts, P6-S2 must downgrade that mapping.

The only canonical owner for `TOOL_CALL_REQUESTED`, `TOOL_CALL_GOVERNED` and `TOOL_RESULT_ACCEPTED` is `ToolRuntime -> HostToolFactAcceptPort`. Tests must prove EngineEvent ingest cannot append canonical tool facts and cannot bypass accept idempotency.

### 4.4 Idempotency

Tool fact accept idempotency fixed mapping:

- `scope_kind = "tool_fact_accept"`
- `scope_id = f"{attempt_id}:{tool_call_id}"`
- `idempotency_key` derived from attempt identity, tool call identity, tool fact kind, result / awaiting digest, and policy decision digest.
- `semantic_input_digest` covers tool identity, normalized arguments digest, tool fact kind, result / payload digest, policy decision digest, truncation metadata digest.

Same scope + key + digest returns existing `ToolFactAcceptedAck`. Same scope + key + different digest returns structured `idempotency_conflict`; ToolRuntime must return governed tool error and must not expose raw result to Engine.

## 5. Affected Files / Modules

Implementation may modify only files listed in the assigned slice. If a slice needs an unlisted file, stop and return to controller.

### 5.1 Production Files By Slice

- P6-S1:
  - `dayu/host/tool_runtime.py` new.
  - `dayu/host/tooling.py`.
  - `dayu/host/run_input.py`.
  - `dayu/host/command.py`.
  - `dayu/host/api.py` only if construction options need typed policy fields or `AttemptDispatchSnapshot` must carry `ToolExecutionMode`.
  - `dayu/host/__init__.py` only for public Host options, not internal ports.
- P6-S2:
  - `dayu/host/tool_runtime.py`.
  - `dayu/host/durable/event_log.py`.
  - `dayu/host/durable/schema.py` only if event type validation requires schema update.
  - `dayu/host/durable/run_transition.py`.
  - `dayu/host/_event_payload.py`.
  - `dayu/host/engine_ingest.py` only to ensure EngineEvent ingest does not duplicate tool canonical facts.
- P6-S3:
  - `dayu/host/tool_runtime.py`.
  - `dayu/host/run_input.py`.
  - `dayu/host/dispatch.py` only for wiring ToolRuntime into local dispatch request construction.
  - `dayu/host/local_proxy.py` only for passing the ToolExecutor supplied by RunInputBuilder, not for protocol changes.
- P6-S4:
  - `dayu/host/tool_runtime.py`.
  - `dayu/host/tooling.py` only if `FrameworkToolName.FETCH_MORE` policy wiring needs expansion.
  - `dayu/host/run_input.py`.
- P6-S5:
  - `dayu/host/tool_runtime.py`.
  - `dayu/host/_event_payload.py`.
  - `dayu/host/durable/event_log.py` only for governance event payload support.
- P6-S6:
  - `dayu/host/api.py` only to add composition-root local execution tooling options.
  - `dayu/host/dispatch.py` to wire real `HostDispatchScheduler` to tool-enabled RunInputBuilder when construction tooling and policy allow tools.
  - `dayu/host/README.md`.
  - `dayu/README.md`.
  - `tests/README.md` only if new test categories or commands are added.

### 5.2 Test Files By Slice

- P6-S1:
  - `tests/host/test_toolruntime_effective_bundle.py` new.
  - `tests/host/test_run_input_builder.py`.
  - `tests/host/test_tooling_options.py`.
  - `tests/host/test_package_exports.py`.
- P6-S2:
  - `tests/host/test_toolruntime_accept_barrier.py` new.
  - `tests/host/test_event_log_store.py`.
  - `tests/host/test_durable_schema.py` only if schema event validation changes.
  - `tests/host/test_engine_ingest_mapping.py`.
- P6-S3:
  - `tests/host/test_toolruntime_executor.py` new.
  - `tests/host/test_phase6_toolruntime_integration.py` new.
  - Prefer no change to `tests/host/test_phase5_local_execution_integration.py`; only touch it if an assertion explicitly names Phase 5 no-tool internals that P6 removes. Add new Phase 6 integration tests instead of migrating broad Phase 5 coverage.
- P6-S4:
  - `tests/host/test_toolruntime_truncation_fetch_more.py` new.
  - `tests/host/test_toolruntime_effective_bundle.py`.
  - `tests/host/test_phase6_toolruntime_integration.py`.
- P6-S5:
  - `tests/host/test_toolruntime_duplicate_governance.py` new.
  - `tests/host/test_toolruntime_diagnostics.py` new.
  - `tests/host/test_toolruntime_accept_barrier.py`.
- P6-S6:
  - update tests only for docs examples if needed; no new production behavior.

### 5.3 Forbidden Files / Modules

- `dayu/fins/`, `dayu/service/`, `dayu/ui/`.
- Engine public contracts unless a pre-existing bug prevents using `ToolExecutor` as designed; such a discovery is a stop condition.
- Remote transport / wire protocol modules.
- New durable cursor / wait / trace projection / business tool registry tables.
- Review artifacts other than implementation artifacts required by later gates.

## 6. Implementation Slices

The implementation control document suggested four Phase 6 slices. This plan intentionally refines them into six independently verifiable slices so RunInputBuilder/tool mode wiring, accept barrier, executor governance, truncation/fetch_more, duplicate governance and final docs/integration can each close with focused tests.

### P6-S1 - Effective ToolBundle And RunInputBuilder Wiring

- **objective**: Introduce ToolRuntime typed ports, `EffectiveToolBundle`, and RunInputBuilder providers that expose schemas and executor from the same effective bundle.
- **allowed files**: P6-S1 files only.
- **prerequisites**: Phase 5 RunInputBuilder exists and currently no-tools; `HostToolingOptions` exists.
- **exact changes**:
  - Add `dayu/host/tool_runtime.py` with module docstring and typed dataclasses/protocols listed in §3.2 / §3.3.
  - Implement `EffectiveToolBundleBuilder` reserved name validation, digest derivation, schema projection and optional framework injection hook.
  - Add `ToolRuntimeHandle(tool_schemas, tool_executor, effective_bundle_digest)` shape.
  - Add `ToolExecutionMode` or equivalent typed enum with `TOOL_ENABLED`, `NO_TOOL_REPLAY`, `NO_TOOL_DISABLED`; pass it explicitly from Host dispatch / builder construction.
  - If `AttemptDispatchSnapshot` carries the mode, treat it as an approved Host typed contract change and update construction tests. If not, the dispatch path must still pass the mode explicitly to RunInputBuilder.
  - Split `PolicySnapshot.__post_init__` from no-tool enforcement: it must allow `allow_tool_calls=True` and only validate typed policy consistency.
  - Split or conditionalize `_validate_no_tool_snapshot`; run it only for `NO_TOOL_REPLAY` / `NO_TOOL_DISABLED`, and add a tool-enabled validation path for `TOOL_ENABLED`.
  - Update `DefaultSceneParameterProvider` so system messages reflect mode/policy: `TOOL_ENABLED` must not emit `tools=disabled`; replay/no-tool modes still must express tools disabled.
  - Replace / extend no-op `ToolSchemaSnapshotProvider` and `ToolExecutorProvider` wiring so tool-enabled Attempts can receive a `ToolRuntimeHandle`.
  - Keep replay/no-tool scope returning empty schemas and `NoToolExecutor`.
  - Do not implement accept barrier, dispatcher execution, truncation or duplicate governance in this slice; use explicit unsupported executor if needed.
- **non-goals**: no EventLog changes, no tool callable execution, no `fetch_more`, no duplicate policy.
- **tests**:
  - Business `ToolBundle` with normal tool projects schema and callable binding from same `EffectiveToolBundle`.
  - Business `ToolBundle` defining `fetch_more` remains rejected.
  - Disabled framework tools do not inject `fetch_more`.
  - `PolicySnapshot(allow_tool_calls=True)` constructs successfully for `TOOL_ENABLED` and passes RunInputBuilder validation with a `ToolRuntimeHandle`.
  - Tool-enabled RunInputBuilder exposes schemas and executor from the same handle and does not use no-tool validation.
  - Tool-enabled scene/system messages do not contain `tools=disabled`.
  - Replay/no-tool scope exposes no schemas and keeps `AgentPolicy.allow_tool_calls=False`.
  - Replay/no-tool scene/system messages still express tools disabled.
  - Pyright catches no `Any` / `object` in new public/internal signatures.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host/test_toolruntime_effective_bundle.py tests/host/test_run_input_builder.py tests/host/test_tooling_options.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- **completion signal**: RunInputBuilder can produce a tool-enabled request whose schemas and executor originate from one `ToolRuntimeHandle`.
- **stop condition**: If Engine contract must change to pass tool schemas or executor, stop; the design forbids it.

### P6-S2 - Host Accept Barrier And Tool Canonical Facts

- **objective**: Implement Host accept path, accepted / rejected / timeout result types, idempotency mapping and EventLog canonical facts for tool results.
- **allowed files**: P6-S2 files only.
- **prerequisites**: P6-S1 contracts available.
- **exact changes**:
  - Add `HostToolFactAcceptPort` production implementation using Phase 2 transaction runner and idempotency primitive.
  - Validate Run / Attempt / execution identity and current state before accepting tool fact.
  - Append `TOOL_CALL_REQUESTED`, `TOOL_CALL_GOVERNED` where applicable, and `TOOL_RESULT_ACCEPTED` in one transaction with idempotency record.
  - Return `ToolFactAcceptedAck` with stable event refs.
  - Return `ToolFactRejectedAck` for invalid state, stale execution, schema mismatch, CAS conflict or explicit policy reject.
  - Map same scope + key + digest to existing ack; same scope + key + different digest to `idempotency_conflict`.
  - Keep EngineEvent tool mappings diagnostic / preview only. `TOOL_CALL_REQUESTED`, `TOOL_RESULT_ACCEPTED`, `TOOL_CALLS_BATCH_READY`, `TOOL_CALLS_BATCH_DONE`, `TOOL_CALL_DELTA` and equivalent EngineEvent tool events must not append canonical tool facts; if current mapping is canonical, downgrade it.
  - Ensure ToolRuntime accept path is the only canonical writer for `TOOL_CALL_REQUESTED`, `TOOL_CALL_GOVERNED` and `TOOL_RESULT_ACCEPTED`.
- **non-goals**: no executor callable execution, no waiting accept, no cursor table, no remote ack.
- **tests**:
  - same accept key + same digest returns existing ack with no duplicate EventLog facts.
  - same accept key + different digest returns idempotency conflict.
  - invalid Attempt / stale execution rejects.
  - EventLog event_sequence remains monotonic and tool facts are canonical.
  - EngineEvent ingest cannot bypass accept path to write tool result facts.
  - EngineEvent `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` / batch-ready / batch-done mappings stay preview or diagnostic and do not produce canonical tool facts.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_event_log_store.py tests/host/test_engine_ingest_mapping.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- **completion signal**: Direct accept port tests prove accepted ack / rejected ack / idempotency conflict behavior without ToolExecutor.
- **stop condition**: If implementing tool facts requires a new durable table beyond EventLog/idempotency/payload foundations, stop for controller decision.

### P6-S3 - ToolExecutor Wrapper, Ack Retry, Side-effect Policy, Awaiting Guard

- **objective**: Implement batch `ToolExecutor` wrapper that executes business callables only through ToolRuntime governance and never returns unaccepted raw results.
- **allowed files**: P6-S3 files only.
- **prerequisites**: P6-S1 and P6-S2 complete.
- **exact changes**:
  - Implement `ToolRuntimeExecutor.execute`.
  - Implement `ToolDispatcher` callable lookup, async invocation and exception-to-`ToolFailedOutcome` normalization.
  - Inject `PassThroughDuplicateGovernance` always-allow stub for P6-S3; P6-S5 replaces it with the full duplicate matrix.
  - Implement named `ToolAcceptRetryPolicy`; retry only timeout / ack-lost classes.
  - On `ToolFactRejectedAck`, return governed `ToolFailedOutcome` or `ToolCancelledOutcome` without raw result.
  - On retry exhaustion / timeout, return governed tool error and emit diagnostic; do not create wait record, do not mark Attempt recoverable.
  - Implement side-effect / paid policy: missing required tool idempotency key rejects before callable execution.
  - Implement awaiting unsupported guard: `ToolAwaitingOutcome` becomes `ToolFailedOutcome` with `governed_error` policy decision and `unsupported_awaiting` reason through accept path where appropriate, never `WAITING`.
  - Wire local dispatch / RunInputBuilder to use ToolRuntime executor for tool-enabled Attempts.
- **non-goals**: no `fetch_more`, no duplicate governance beyond pass-through `allow`, no remote transport.
- **tests**:
  - fake tool result is returned to Engine only after accepted ack.
  - accept rejected does not expose raw fake result.
  - accept timeout bounded retry returns governed error; no wait record, no `WAITING`, no recovery.
  - side-effect / paid tool without required idempotency key never calls callable.
  - awaiting outcome returns `ToolFailedOutcome` with canonical kind `governed_error`, records `unsupported_awaiting` only as policy reason, and leaves Run / Attempt out of `WAITING`.
  - replay/no-tool scope rejects model tool call.
  - batch with mixed accept outcomes keeps already accepted call outcomes visible to Engine and returns governed error only for rejected/timed-out calls.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_phase5_local_execution_integration.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- **completion signal**: End-to-end local fake business tool path runs Engine -> ToolExecutor -> ToolRuntime -> Host accept -> Engine continuation.
- **stop condition**: If a test requires adding Host governance fields to Engine events or Engine requests, stop; this violates P6 boundary.

### P6-S4 - TruncationManager And fetch_more Normal Tool Path

- **objective**: Implement run-scoped truncation and `fetch_more` as an ordinary framework tool injected into effective bundle.
- **allowed files**: P6-S4 files only.
- **prerequisites**: P6-S1 to P6-S3 complete.
- **exact changes**:
  - Implement `TruncationManager` with cursor creation, token digest, TTL, single-use and scope validation.
  - Initialize `TruncationManager` from `EffectiveToolBundle.truncate_specs_by_name`; business `ToolTruncateSpec` must not be recomputed from another source.
  - Apply `ToolTruncateSpec` to completed outcomes for text chars, text lines, list items and binary bytes where current contracts support them.
  - Add `fetch_more` framework `ToolDefinition` injection when enabled and truncation manager exists.
  - Ensure `fetch_more` callable uses normal `ToolDispatcher`, policy, accept barrier and EventLog path.
  - Represent truncation metadata in `ToolFactAcceptCandidate` and accepted EventLog payload.
  - Return ordinary tool error for cursor missing, token mismatch, scope mismatch, expired, used, digest mismatch.
- **non-goals**: no durable cursor table, no cross restart continuation, no Host / Engine special case, no business registry public API.
- **tests**:
  - truncated normal tool result includes opaque cursor + scope token and hides internal storage.
  - `fetch_more` appears in tool schemas and callable dispatch from the same effective bundle.
  - normal `fetch_more` call passes through ToolExecutor / accept barrier.
  - cursor single-use, TTL expiry, scope mismatch, token mismatch, missing cursor and digest mismatch return ordinary tool errors.
  - disabled truncation does not inject `fetch_more`.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- **completion signal**: `fetch_more` is indistinguishable from a normal tool call at Engine / WorkerProxy boundary and still has run-scoped cursor enforcement.
- **stop condition**: If implementation needs to persist raw remainder for restart-safe fetch, stop; P6 explicitly forbids durable cursor descriptor.

### P6-S5 - Duplicate Governance And Diagnostic Emitter

- **objective**: Add run-local duplicate governance matrix and minimal diagnostic emitter interface.
- **allowed files**: P6-S5 files only.
- **prerequisites**: P6-S1 to P6-S4 complete.
- **exact changes**:
  - Implement `DuplicateGovernancePort` and in-memory per-run duplicate index scoped to the ToolRuntime instance.
  - Compute duplicate key without `index_in_iteration`; same iteration same tool identity and same normalized args still go through duplicate governance.
  - Record prior accepted refs after accepted ack.
  - Implement decision matrix `allow` / `reuse` / `hint` / `require_justification` / `hard_stop`.
  - Ensure `reuse` references prior accepted refs and does not append a second `TOOL_RESULT_ACCEPTED`.
  - Add `ToolTraceDiagnosticEmitter` protocol plus no-op / in-memory implementation for tests.
  - Include diagnostic refs in candidates, ack, reject and timeout governed errors.
- **non-goals**: no session durable duplicate ledger, no Memory retrieval, no audit/trace projection writes.
- **tests**:
  - duplicate key normalizes arguments deterministically.
  - duplicate key excludes `index_in_iteration`; two same-iteration calls with different indexes and same normalized args still enter governance.
  - `allow` executes and accepts.
  - `reuse` does not call callable and does not append new result fact.
  - `hint` / `require_justification` / `hard_stop` produce governed facts and diagnostic refs.
  - accepted prior refs survive within same run-local ToolRuntime but are not assumed after new runtime construction.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- **completion signal**: Duplicate action matrix is covered without Engine changes or durable duplicate table.
- **stop condition**: If implementation needs cross-run semantic recall to satisfy tests, stop; that is P9 Memory / retrieval, not P6.

### P6-S6 - Integration, Documentation, And Gate Validation

- **objective**: Finish integration coverage, real scheduler ToolRuntime wiring, README sync and phase validation.
- **allowed files**: P6-S6 files only plus test files already introduced in earlier slices if assertions need final alignment.
- **prerequisites**: P6-S1 to P6-S5 complete.
- **exact changes**:
  - Wire `HostDispatchScheduler` to construct a ToolRuntime handle and use tool-enabled RunInputBuilder when Host construction tooling exists and policy allows tools.
  - Preserve no-tool behavior when construction tooling is absent or policy disables tools.
  - Add / update integration tests covering the full fake tool path and `fetch_more` path.
  - Add replay no-tool defense integration test.
  - Update README files listed in §8.
  - Ensure all modified/new functions/classes/modules have Chinese docstrings with params / returns / raises where applicable.
  - Ensure no new weak typing exceptions or import boundary violations.
- **non-goals**: no durable tool snapshot table, no Remote transport, no P7 wait record, no P13 trace projection, no business tool discovery.
- **tests**:
  - full testing matrix in §7.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host -q`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
- **completion signal**: P6 implementation artifact can report Engine only consumes accepted tool facts, `fetch_more` is normal tool path, no `WAITING` / recovery / remote / durable cursor slipped in.
- **stop condition**: Any README update would need to claim future P7/P11/P13/P14 behavior as implemented.

## 7. Testing Matrix

Unit:

- `PolicySnapshot(allow_tool_calls=True)` is valid for `ToolExecutionMode.TOOL_ENABLED`; no-tool validation still rejects tool-enabled snapshots in `NO_TOOL_REPLAY` / `NO_TOOL_DISABLED`.
- RunInputBuilder receives explicit `ToolExecutionMode`; tool-enabled mode exposes tool schemas/executor, replay/no-tool modes expose none.
- tool-enabled scene/system messages do not contain `tools=disabled`; replay/no-tool scene/system messages still express no-tool.
- effective bundle rejects business `fetch_more` conflict.
- effective bundle injects `fetch_more` only when enabled and truncation manager is present.
- schema projection and callable dispatch derive from same effective bundle.
- `ToolFactAcceptCandidate.__post_init__` enforces required fields for `completed` / `failed` / `cancelled` / `reuse` / `governed_error`.
- accept idempotency same key + same digest returns existing ack.
- accept idempotency same key + different digest returns conflict.
- EngineEvent tool mappings remain preview / diagnostic and cannot append canonical tool facts.
- accepted ack retry handles lost ack without duplicate EventLog facts.
- rejected ack and timeout do not return raw tool result.
- batch execution with one accept failure does not roll back other already accepted calls in the same batch.
- side-effect / paid tool missing required idempotency key rejects before callable execution.
- `TruncationManager` uses `EffectiveToolBundle.truncate_specs_by_name` for business `ToolTruncateSpec`.
- truncation normal path creates opaque cursor / scope token.
- cursor single-use, TTL, scope mismatch, token mismatch, missing cursor and digest mismatch return ordinary tool errors.
- duplicate matrix covers `allow` / `reuse` / `hint` / `require_justification` / `hard_stop`.
- duplicate key excludes `index_in_iteration`; same iteration same tool and same normalized args still enter duplicate governance.
- `reuse` references prior accepted event refs and appends no second result fact.
- replay no-tool ToolRuntime guard rejects unexpected tool calls.
- P6 awaiting unsupported guard: `ToolAwaitingOutcome` maps to `ToolFailedOutcome` + canonical `governed_error`; `unsupported_awaiting` stays policy reason, no wait record, no `WAITING`, no `resolve_wait`.

Integration:

- fake business tool goes Engine -> ToolExecutor -> ToolRuntime -> Host accept barrier -> Engine continuation.
- tool-enabled RunInputBuilder uses `ToolExecutionMode.TOOL_ENABLED` and keeps schema projection / executor from the same `ToolRuntimeHandle`.
- replay Attempt uses `ToolExecutionMode.NO_TOOL_REPLAY`, exposes no schemas and keeps no-tool system message.
- bounded accept retry with ack loss returns existing ack.
- bounded accept timeout returns governed error and leaves Run out of `WAITING` / recovery.
- mixed batch accept outcomes return accepted call results and governed errors for failed accepts without EventLog rollback.
- `fetch_more` executes through normal tool path and accept barrier.
- duplicate tool call reuse path returns accepted prior fact to Engine without re-executing callable.
- replay Attempt exposes no tool schemas; if model still emits tool call, ToolRuntime rejects as defense-in-depth.

Pyright:

- `source .venv/bin/activate && python -m pyright dayu/host tests/host` after each implementation slice.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` before accepted slice / aggregate gate.

Docs:

- `dayu/host/README.md` updated for current ToolRuntime, accept barrier, `fetch_more`, duplicate governance and non-goals.
- `dayu/README.md` updated only if overall Host / Engine tool boundary or user-visible workflow changes.
- `tests/README.md` updated only if new Phase 6 test categories or commands become stable maintenance facts.

## 8. Docs Decision

README trigger rules for Phase 6 implementation:

- `dayu/host/` changes require `dayu/host/README.md` update. It must describe current facts: Host-owned ToolRuntime, effective `ToolBundle`, accept barrier, governed ack timeout behavior, run-scoped `fetch_more`, duplicate governance, awaiting unsupported boundary. It must not document P7 wait record or P14 remote as implemented.
- Boundary changes between Host and Engine require checking `dayu/README.md`. Update only the architecture/tool boundary section if the current README still says Host has no ToolRuntime or tools are disabled. Keep it as developer overview, not user manual.
- New `tests/host/test_toolruntime_*` categories require checking `tests/README.md`. Update only if test grouping / commands / maintenance rules change.
- Root `README.md` is not required unless CLI usage, config entry, trace/render entry or user workflow changes. P6 is internal Host implementation, so default decision is no root README change.
- `dayu/engine/README.md` should not need changes because Engine public contract is unchanged. If wording claims tools are no-op only, implementation agent may update that file only after controller approval because it is outside the README trigger list in this handoff.

## 9. Residual Risks / Later Phase Owners

- P7 Tool Awaiting / Wait Record owns `TOOL_AWAITING`, wait record table, `WAITING`, `resolve_wait`, wait adapter result acceptance, external job cancel handle and awaiting resume/cancel.
- P11 Host lifecycle / Recovery owns orphan proof, startup recovery, stuck cancelling, durable unavailable recovery and any future ack-timeout recovery branch.
- P12 ToolsDiscovery / ScenePrepare owns provider registry, manifest schema, business tool scanning, scene input assembly and multi profile selection.
- P13 Audit / Tool Trace / Outbox owns durable trace projection, hot JSON / cold JSONL, audit query and outbox delivery. P6 only emits typed diagnostic refs.
- P14 RemoteProxy / RemoteStub owns remote wire protocol, remote ToolRuntime transport, remote ack semantics, late remote tool fact handling and remote `fetch_more` equivalence.
- P9 / P10 Memory / Context Governance own cross-run retrieval, compact artifacts and long-term evidence reuse. P6 duplicate governance remains run-local.

## 10. Blocking Questions For Controller

Blocking question count: 0.

Working assumptions:

- Existing `ToolDefinition.tags` is not sufficient by itself to carry side-effect / paid idempotency policy. P6 may add Host-internal typed `ToolRuntimePolicyView` keyed by tool name. This is not blocking because it stays inside Host construction/runtime governance and does not change Engine contract.
- EventLog `append_event` currently permits arbitrary event type strings with structured payloads; P6 does not need schema version bump for `TOOL_*` event type names. If implementation encounters a payload validator / codec registry that requires registration, only that validator/codec registration should change.
- `fetch_more` default enablement should follow `FrameworkToolPolicyView.enabled_framework_tools`; tests may enable it explicitly. Default construction can remain disabled unless Host command policy turns on truncation for a run.
- `ToolTraceDiagnosticEmitter` may be no-op in production for P6 as long as it returns typed refs or empty refs consistently; P13 will own projection persistence.

## 11. Completion Report Format For Implementation Agent

Each implementation artifact must report:

- slice id and approved plan path;
- changed files;
- implemented contract items;
- tests run and exact results;
- pyright result;
- docs decision and files updated;
- residual risks classified by later slice or later phase owner;
- explicit confirmation that no wait record / `WAITING` / `resolve_wait`, durable cursor descriptor, Remote wire protocol, business tool scanning, `dayu.fins` import, or Engine governance change was introduced.
