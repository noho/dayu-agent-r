# WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation Plan

## Gate

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- gate: plan
- artifact path: `docs/host/wu-eng-02-provider-request-identity-plan.md`
- scope: code-generation-ready plan only; no implementation, fix, review, commit, push or PR gate

## Goal / Motivation / Success Signal

### Goal

为 Engine Runner 公共契约引入强类型 per-call request identity / correlation context。Agent 每次调用 Runner 时构造本次逻辑 Runner call 的 request identity，OpenAI-compatible adapter 仅在显式 policy 允许时把其中的 client correlation id 映射为合法 `X-Client-Request-Id`，并继续采集 provider response `x-request-id`。

Host / Tool Trace 侧需要能把 provider-native request id、client correlation id、本地 `run_id`、Attempt、execution、iteration 与 engine event ref 放在同一条诊断链路中，供后续 issue-70 analyzer 消费。

### Motivation

动机成立，且不是用户治理字段问题。当前系统已经采集 provider response request id，但缺少发往 provider 的本地 client correlation signal；当 provider/model 行为疑似 bug 时，只靠 response `x-request-id` 不一定足以把厂商排障、本地 run / attempt / iteration / tool trace 串起来。

### Success Signal

- `AsyncRunner.call` 有强类型 `request_identity` 输入，Agent 每次 Runner 调用都传入。
- 普通 Host dispatch 能把 `AttemptDispatchSnapshot.attempt_id/execution_id` 投影到 Engine request。
- OpenAI-compatible adapter 在 policy 开启时发送 `X-Client-Request-Id`；policy 关闭或 request identity 缺失时不发送。
- response `x-request-id` 采集行为不回退。
- Host ingest / Tool Trace 诊断 payload 能同时呈现 `provider_request_id` 与 `client_correlation_id`，且不新增 SQLite 表/列。
- 不伪造 `user_id`、`safety_identifier` 或 Anthropic `metadata.user_id`。

## Non-Goals / Scope Boundary

- 不实现 native Anthropic runner。
- 不实现 Tool Trace analyzer；issue-70 只消费本 WU 产生的信号。
- 不把动态 per-run / per-attempt ID 放进 `RunnerSpec.headers`。
- 不在 Host / Agent 增加 provider 字符串治理分支。
- 不改变 `RunnerEvent` 不携带 Host ownership 的边界；RunnerEvent 仍只表达 provider 协议事实。
- 不把 `session_id`、`run_id`、`attempt_id` 或 UI / Service 用户概念伪装成 provider end-user governance field。
- 不新增 durable SQLite schema column；如需诊断持久化，只进入既有 EventLog payload / Tool Trace summary JSON。

## Design Document Alignment

- `docs/engine/design.md` 定义 Engine 是一次性 Agent run，Runner 是 provider 协议归一边界，Runner 不做 Agent 多轮迭代、Host 终态或工具执行治理。新增 request identity 应从 Agent 调 Runner 的边界进入 Runner，不进入 Host 反向依赖。
- `docs/engine/design.md` 明确 `RunnerEvent` 不含 `session_id` / `run_id`，这些字段在 EngineEvent 提升阶段补齐。本 WU 不改变 RunnerEvent ownership，只让 Agent 把本地 request identity 用于 outbound header，并在 EngineEvent / Host ingest 中记录本地关联。
- `docs/host/design.md` 定义 Host 对 Agent / Runner lifecycle、Attempt、execution、EventLog、Tool Trace 负责；普通 Run 的 Attempt / execution identity 已是 Host durable truth。新增 client correlation signal 应由 Host execution context 与 Engine ingest 关联，不让 Runner 拥有 Host 状态机。
- `docs/host/issues-implementation-control.md` 中 WU-ENG-02 已明确：当前目标是 provider debugging correlation，不是用户治理字段；OpenAI-compatible 只在显式 capability / policy 允许时映射 `X-Client-Request-Id`；Anthropic native / Claude Code gateway 只做 policy 区分规划。

当前 design_doc 足以支撑 plan：需要的是 Engine public contract 变更与 Host request projection 补齐，不需要新增 Host 状态机裁决。

## First-Principles Judgment And Direct Code Evidence

### Judgment

问题真实存在，严重性评估成立。当前代码已经具备 provider response request id 的下游消费链路，但缺少 outbound client correlation id；这会在多 iteration、retry、provider 报障与 Tool Trace 分析中造成关联信号不完整。最佳修复点是 Runner 公共契约，而不是把动态 header 塞进静态 `RunnerSpec.headers`，也不是在 Host / Agent 写 provider 字符串分支。

### Direct Evidence

- `dayu/engine/contracts/runner.py`：`AsyncRunner.call(messages, options, tools)` 当前只有 `messages/options/tools`，没有 per-call request context。
- `dayu/engine/agent.py`：`_AsyncAgent._run_iteration()` 在调用 `self._runner.call(...)` 时只传 `messages`、`self._request.runner_options`、`tools`。
- `dayu/engine/runners/openai/runner.py`：`AsyncOpenAIRunner.call()` / `_call_impl()` 也只接收 `messages/options/tools`；`_do_attempt()` 构造 headers 时只包含 `"Content-Type": "application/json"` 与 `dict(self._spec.headers)`。
- `dayu/engine/runners/openai/runner.py`：`_extract_provider_request_id()` 已从 response headers 提取 `x-request-id`，并在 HTTP error、SSE parser、non-stream parser、`RunnerDoneData` 等路径上传递 `provider_request_id`。
- `dayu/engine/contracts/agent_run.py`：`AgentRunRequest` 只有 `run_id/session_id`，没有 `attempt_id/execution_id`；这解释了 Agent 当前无法构造 Attempt-aware provider-call identity。
- `dayu/host/api.py`：`AttemptDispatchSnapshot` 已有 `session_id/run_id/attempt_id/execution_id/dispatch_record_id/execution_target/policy_snapshot_ref/cancellation_token`，说明 attempt identity 可以从当前 Host 输入获得。
- `dayu/host/dispatch.py`：`_snapshot_from_dispatch()` 从 `PendingDispatchRecord` 构造 `AttemptDispatchSnapshot` 时已填充 `attempt_id` 与 `execution_id`。
- `dayu/host/run_input.py`：`RunInputBuilder.build()` 使用 `AttemptDispatchSnapshot` 构造 `AgentRunRequest`，当前只投影 `run_id/session_id`，没有投影 `attempt_id/execution_id`。
- `dayu/host/engine_ingest.py`：`provider_request_id` 已进入 context compaction、provider protocol diagnostic、terminal plan 与 preview payload 等链路，但没有 client correlation 字段。
- `dayu/host/durable/tool_trace.py` 与 `dayu/host/tool_trace.py`：Tool Trace hot row 有 `provider_request_id` column 和 provider request 查询；projection summary 当前可承载 JSON 诊断字段，但没有 client correlation signal。
- `tests/engine/runners/openai/_fakes.py`：FakeSession 已记录 `headers`，适合新增 OpenAI-compatible outbound header 测试。

## Affected Files / Modules

后续 implementation 允许触碰的主要模块：

- Engine contracts: `dayu/engine/contracts/runner_identity.py`（新增）、`dayu/engine/contracts/runner.py`、`dayu/engine/contracts/agent_run.py`、`dayu/engine/contracts/engine_events.py`、`dayu/engine/contracts/runner_spec.py`、`dayu/engine/contracts/__init__.py`
- Engine Agent / runner: `dayu/engine/agent.py`、`dayu/engine/runners/openai/runner.py`
- Host projection / dispatch: `dayu/host/run_input.py`、`dayu/host/llm_compaction.py`、`dayu/host/_execution_config_projection.py`
- Host ingest / trace: `dayu/host/engine_ingest.py`、`dayu/host/tool_trace.py`
- Tests: affected `tests/engine/**` and `tests/host/**` listed per slice below
- README sync: `dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md` if implementation changes land

## Contract / Schema / State-Machine / Public-Interface Changes

### Public Contract

1. Add Engine contract module `dayu.engine.contracts.runner_identity`.
2. Add `RunnerRequestIdentity` dataclass:
   - `run_id: str`
   - `attempt_id: str | None`
   - `execution_id: str | None`
   - `iteration_id: str`
   - `iteration_index: int`
   - `runner_call_index: int`
   - `client_correlation_id: str`
3. Add module-level builder `build_runner_request_identity(...) -> RunnerRequestIdentity`.
4. Change `AsyncRunner.call(messages, options, tools, *, request_identity: RunnerRequestIdentity | None)` by adding only the keyword-only `request_identity`; keep existing `messages/options/tools` positional parameters unchanged to minimize public-contract churn.
5. Add `attempt_id: str | None` and `execution_id: str | None` to `AgentRunRequest`; both must be set together or both be `None`.
6. Add `client_correlation_id: str | None` to EngineEvent data classes that already carry provider request identity:
   - `ContextCompactionRequestedData`
   - `ProviderProtocolErrorData`
   - `IterationCompletedData`
   - `RunFailedData`
7. Add `client_correlation_id: str | None` to `EngineRunOutcomeFailed` as an `AgentRunResult` outcome class in `dayu.engine.contracts.agent_run`, not as an EngineEvent data class.

### Adapter Policy

Add explicit RunnerSpec policy for outbound client correlation:

- `ClientCorrelationPolicy.DISABLED`
- `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID`

`RunnerSpec.client_correlation_policy` must be frozen with the rest of RunnerSpec and projected through Host effective execution config. OpenAI-compatible runner only maps `request_identity.client_correlation_id` to `X-Client-Request-Id` when the policy is `OPENAI_X_CLIENT_REQUEST_ID`.

`ClientCorrelationPolicy` docstring must state that enum values are provider-protocol-specific outbound mapping policies. They are not provider-name branches, and Host / Agent must not dispatch behavior by provider string.

Anthropic native and Claude Code gateway are not implemented in code in this WU because the repository has no native Anthropic runner. The adapter policy decision is:

- Anthropic native: collect response `request-id` when native runner exists; do not send `metadata.user_id`.
- Claude Code gateway: `X-Claude-Code-Session-Id` is session/gateway continuity policy, not provider-call client request id; only a future Claude Code gateway adapter may send it under explicit gateway policy.

### Durable Schema

- No SQLite table, column, index, or migration change.
- Durable EventLog payload semantics change: Host ingest should include optional `client_correlation_id` in provider-related diagnostic / terminal / preview payloads.
- Tool Trace hot row schema does not add a column; projection stores `client_correlation_id` in `trace_summary_json` and cold JSONL line summary.
- Because this project treats schema changes as fresh-schema only unless compatibility is explicitly requested, implementation tests should validate new payload shape directly and should not add old-payload compatibility tests.

### State Machine

No Host Run / Attempt / dispatch / recovery state transition changes. Attempt identity is already present; the implementation only projects it into Engine request and diagnostics.

## Client Correlation ID Source Choice

Chosen source: provider-call-level derived value.

Do not use bare `run_id`: one run can contain multiple Agent iterations and thus multiple provider calls.

Do not use bare `attempt_id`: one Attempt can contain multiple iterations, fallback/continuation calls, and tool-calling loops.

Use deterministic provider-call-level identity derived from:

- `run_id`
- `attempt_id` when available
- `execution_id` when available
- `iteration_id`
- `iteration_index`
- `runner_call_index`

Keep both `run_id` and `iteration_id` in the canonical tuple even though the current `iteration_id` format embeds `run_id`. `run_id` remains the local root correlation input and avoids making digest semantics depend on the textual shape of `iteration_id`.

The emitted `client_correlation_id` must be ASCII and short. Implementation must use a stable `dayu-` prefix plus the full SHA-256 hex digest over a canonical tuple of the above fields: exactly `dayu-` plus 64 lowercase hex characters. This avoids illegal header characters, excessive length, and leaking internal IDs into provider logs while preserving local reversibility through EventLog / Tool Trace payloads.

Retry semantics: transport retry inside `AsyncOpenAIRunner._call_impl()` should reuse the same `client_correlation_id` for all HTTP attempts of one logical Runner call. This prevents vendor ambiguity: the provider sees retries as repeated transport attempts for the same logical client call, while local diagnostics still retain provider-native `x-request-id` per final/observed response and Runner HTTP error attempt count.

Multi-call semantics: every logical Runner call increments `runner_call_index` and gets a distinct `client_correlation_id`. This includes normal Agent iterations, tool-loop re-entries, length continuations, force-answer fallback, and any future fallback path that performs a Runner call. Transport retries inside one logical Runner call do not increment the index.

## Provider Adapter Policy Design

### OpenAI-Compatible

- Policy field: `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID`.
- Header name constant: `X-Client-Request-Id`.
- Mapping: `headers["X-Client-Request-Id"] = request_identity.client_correlation_id`.
- Only send when policy is enabled and `request_identity is not None`.
- Reject or fail fast when policy is enabled and `RunnerSpec.headers` already contains a case-insensitive `x-client-request-id`, because static headers are not valid per-call identity and would make precedence ambiguous.
- Continue response `x-request-id` extraction unchanged.

### Anthropic Native

- Current WU does not implement native runner.
- Future native adapter should collect response `request-id` as provider-native request id.
- It must not map Dayu internal ids to Anthropic `metadata.user_id`.

### Claude Code Gateway

- Current WU does not implement gateway adapter.
- `X-Claude-Code-Session-Id` is not equivalent to per-call provider client request id.
- Future gateway adapter may send it only under explicit Claude Code gateway policy; it must be separate from OpenAI-compatible `X-Client-Request-Id`.

## Implementation Decisions

- Add one small Engine identity contract instead of a generic tracing framework.
- Keep correlation id generation in Engine contracts / Agent boundary, not in Host / OpenAI runner, so all Runner implementations receive the same typed identity.
- Add `attempt_id/execution_id` to `AgentRunRequest` because ordinary Host already has them in `AttemptDispatchSnapshot`; compactor requests can pass their request attempt/execution when reactive, otherwise `None`.
- Keep RunnerEvent unchanged; EngineEvent and Host EventLog payload carry local correlation.
- Store client correlation in EventLog payload and Tool Trace summary JSON, not a new hot-table column.
- Use explicit `ClientCorrelationPolicy` in `RunnerSpec` rather than provider-name branching.
- Do not add `Any`, `object`, untyped payload bags, lazy imports, nested helper functions, or compatibility wrappers.

## Small Implementation Slices

### Slice 1: Engine Contract And Agent Identity

Objective: introduce typed request identity and make Agent pass it to Runner on every logical Runner call.

Allowed files:

- `dayu/engine/contracts/runner_identity.py`
- `dayu/engine/contracts/runner.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/agent.py`
- `tests/engine/contracts/test_runner_identity.py`
- `tests/engine/contracts/test_agent_run.py`
- affected fake Runner tests in `tests/engine/test_agent_phase2.py`, `tests/engine/test_agent_phase3_tool_call.py`, `tests/engine/test_metadata_boundary.py`

Exact changes:

- Create `RunnerRequestIdentity` and `build_runner_request_identity`.
- Validate non-empty text fields; validate `iteration_index >= 0`; validate `runner_call_index >= 1`; validate `attempt_id/execution_id` pair consistency.
- Compute `client_correlation_id` as `dayu-` + full 64-character SHA-256 hex digest.
- Add `attempt_id/execution_id` to `AgentRunRequest` and validation.
- Change `AsyncRunner.call` protocol to `call(messages, options, tools, *, request_identity=...)`; only `request_identity` is keyword-only, and existing positional `messages/options/tools` stay positional.
- Add `_runner_call_index` counter to `_AsyncAgent`.
- Increment `_runner_call_index` immediately before every logical `_run_runner_iteration` / Runner invocation, including normal iterations, tool-loop re-entries, length-continuation calls, force-answer fallback, and fallback paths that call the Runner.
- In each logical Runner call, build identity from `self._request.run_id`, `self._request.attempt_id`, `self._request.execution_id`, `iteration_id`, `iteration_index`, and incremented call index.
- Pass `request_identity=identity` to `self._runner.call(...)`.
- Store current identity in iteration state or derive `client_correlation_id` through a module-level helper. Avoid scattering repeated optional-correlation extraction logic across `_AsyncAgent` emit sites.

Call path:

`Host RunInputBuilder -> AgentRunRequest -> run_agent_messages -> _AsyncAgent._run_iteration -> AsyncRunner.call(request_identity=...)`.

Data flow:

Host durable attempt identity enters `AgentRunRequest`; Agent derives per-call correlation id; Runner consumes it; Agent emits correlation id in EngineEvents for Host ingest.

Error handling:

- Invalid request identity inputs raise `ValueError` at construction.
- Missing attempt/execution is allowed only as both `None` for non-Attempt Engine usage such as proactive compactor or direct Engine tests.
- Ordinary Agent -> Runner paths must pass a non-`None` `RunnerRequestIdentity`. Direct Runner tests, direct Engine call sites, and compactor paths outside an ordinary Agent attempt may explicitly pass `None`.
- Runner exceptions preserve existing failure behavior and include current `client_correlation_id` in `RunFailedData` when tied to a provider call.

Tests:

- Contract test validates digest is ASCII, stable, exactly 69 characters (`dayu-` plus 64 lowercase SHA-256 hex characters), accepts `iteration_index=0` with `runner_call_index=1`, and changes across iteration/call index.
- Agent test fake Runner captures non-`None` `request_identity` for one-call and multi-iteration flows.
- Agent tests verify `runner_call_index` increments for force-answer fallback, length continuation, and fallback/continuation paths that perform logical Runner calls.
- Existing fake Runner signatures updated without changing behavior.

Completion signal:

- Engine contract and Agent tests pass.
- Every ordinary Agent -> Runner call path passes a non-`None` `request_identity`; direct Runner / direct Engine / allowed compactor paths pass `request_identity=None` explicitly when no ordinary Agent attempt identity exists.

Stop condition:

- Stop if a direct Engine call site cannot provide `attempt_id/execution_id` and cannot safely pass both as `None`.

### Slice 2: RunnerSpec Policy And OpenAI-Compatible Header Mapping

Objective: add explicit adapter policy and map client correlation to `X-Client-Request-Id` only when enabled.

Allowed files:

- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/host/_execution_config_projection.py`
- `tests/engine/contracts/test_runner_spec.py`
- `tests/engine/runners/openai/test_request_identity.py`
- `tests/engine/runners/openai/_factories.py`
- `tests/host/test_effective_execution_config.py`

Exact changes:

- Add `ClientCorrelationPolicy` enum with `DISABLED` and `OPENAI_X_CLIENT_REQUEST_ID`.
- Add required `client_correlation_policy: ClientCorrelationPolicy` to `RunnerSpec`.
- Update RunnerSpec validation and field-set tests.
- Update Host execution config JSON projection to persist `client_correlation_policy`.
- Update all RunnerSpec factories and direct constructors.
- Update `AsyncOpenAIRunner.call/_call_impl/_do_attempt` signatures to accept `request_identity`.
- Build request headers via private helper that:
  - starts from `Content-Type`;
  - merges `RunnerSpec.headers`;
  - adds `X-Client-Request-Id` only when policy is enabled and identity exists;
  - rejects conflicting static `x-client-request-id` under enabled policy.

Call path:

`AsyncOpenAIRunner.call(..., request_identity=identity) -> _call_impl -> _do_attempt -> session.post(..., headers=headers)`.

Data flow:

`RunnerRequestIdentity.client_correlation_id` becomes `X-Client-Request-Id` in outbound HTTP headers only under explicit policy.

Error handling:

- Policy disabled: no outbound header, no error.
- `request_identity is None`: no outbound header, even if policy enabled; direct Runner tests can cover no dynamic id behavior.
- Static header conflict under enabled policy raises `ValueError` before HTTP post.
- Transport retry reuses the same identity object and same header value.

Tests:

- OpenAI runner sends `X-Client-Request-Id` under enabled policy.
- Policy disabled omits the header.
- `request_identity=None` omits the header.
- Retry uses the same header for all attempts.
- Static `RunnerSpec.headers` conflict is rejected.
- Response `x-request-id` tests continue passing.
- Effective execution config round-trips `client_correlation_policy`.

Completion signal:

- OpenAI request header behavior is fully covered by deterministic fake session tests.
- No Host / Agent provider string branch is introduced.

Stop condition:

- Stop if a provider header legality constraint requires external policy not present in design/control docs; do not guess new provider behavior.

### Slice 3: Host Projection, Ingest, And Tool Trace Signal

Objective: project Attempt identity into AgentRunRequest and persist client correlation alongside provider request id in Host diagnostics.

Allowed files:

- `dayu/host/run_input.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- affected Host worker / proxy tests that construct `AgentRunRequest`

Exact changes:

- `RunInputBuilder.build()` passes `attempt_snapshot.attempt_id` and `attempt_snapshot.execution_id` into `AgentRunRequest`.
- `LLMContextCompactor._agent_request()` passes `request.attempt_id/execution_id` when present; proactive compaction passes both `None`.
- Host ingest writes `client_correlation_id` into:
  - provider protocol diagnostic payload;
  - context compaction requested payload;
  - run failed terminal summary when provider-related;
  - Engine event diagnostic preview for `IterationCompletedData`;
  - any existing payload that already writes `provider_request_id` from the affected EngineEvent.
- Tool Trace projection extracts optional `client_correlation_id` from payload and writes it into `trace_summary_json` / cold JSONL `trace_summary`; no hot row column or index.

Call path:

`AttemptDispatchSnapshot -> RunInputBuilder.build -> AgentRunRequest -> EngineEvent(client_correlation_id) -> EngineIngest -> EventLog payload -> ToolTraceProjectionConsumer -> trace_summary_json`.

Data flow:

Attempt/execution identity supplies Agent; Agent supplies EngineEvent client correlation; Host stores it with event payload; Tool Trace summary exposes it for analyzer.

Error handling:

- Missing `client_correlation_id` remains valid and is represented as `None`.
- Payload extraction treats absent field as `None`; newly created databases/tests use the new field where provider-related events include it.
- Invalid non-text `client_correlation_id` in payload raises `HostDurableError`, matching existing Tool Trace payload validation style.

Tests:

- RunInputBuilder test asserts `AgentRunRequest.attempt_id/execution_id` equal snapshot values.
- Compactor request test covers reactive values and proactive `None`.
- Engine ingest mapping tests assert provider diagnostic / terminal / context compaction payload includes `client_correlation_id`.
- Tool Trace projection test asserts summary/cold JSONL contains `client_correlation_id`.

Completion signal:

- Tool Trace rows can show both `provider_request_id` and `client_correlation_id` through existing projection data.
- No durable table schema migration is needed.

Stop condition:

- Stop if adding `client_correlation_id` to EventLog payload is judged a durable semantic schema change requiring design_doc update before code.

### Slice 4: Documentation Sync And Final Validation

Objective: sync stable docs and run validation.

Allowed files:

- `dayu/engine/README.md`
- `dayu/host/README.md`
- `tests/README.md`

Exact changes:

- `dayu/engine/README.md`: document `RunnerRequestIdentity`, `client_correlation_id`, Runner call boundary, and OpenAI-compatible policy.
- `dayu/host/README.md`: document that Host projects Attempt identity into Engine request and Tool Trace diagnostics may include provider/native request id plus client correlation id.
- `tests/README.md`: update test coverage description for provider request identity / OpenAI header / Tool Trace correlation.

Completion signal:

- README content describes current implemented behavior only.
- No root `README.md` update unless implementation changes CLI/config/user workflow, which this WU should not.

Stop condition:

- Stop if implementation changes project-level user commands or configuration entry points unexpectedly; that would require root README scope review.

## Tests / Validation Commands And Expected Assertions

Plan gate does not run tests. Implementation must run:

```bash
source .venv/bin/activate
pytest tests/engine/contracts/test_runner_identity.py \
  tests/engine/contracts/test_agent_run.py \
  tests/engine/contracts/test_runner_spec.py \
  tests/engine/test_agent_phase2.py \
  tests/engine/test_agent_phase3_tool_call.py \
  tests/engine/runners/openai/test_request_identity.py \
  tests/engine/runners/openai/test_streaming_capability_and_content_type.py \
  tests/engine/runners/openai/test_http_error_event.py
```

Expected assertions:

- request identity is stable, ASCII and unique per logical Runner call.
- Agent passes identity to every fake Runner call.
- Agent tests cover incrementing `runner_call_index` for normal calls, force-answer fallback, length continuation, and fallback/continuation paths that perform logical Runner calls.
- OpenAI-compatible header appears only under enabled policy.
- response `x-request-id` propagation still reaches `IterationCompletedData` and failures.

```bash
source .venv/bin/activate
pytest tests/host/test_effective_execution_config.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_local_proxy_engine_ingest.py
```

Expected assertions:

- Host freezes and restores `client_correlation_policy`.
- Host projects `attempt_id/execution_id` into `AgentRunRequest`.
- EventLog payloads include `client_correlation_id` where provider-related EngineEvents include it.
- Tool Trace summary / cold JSONL exposes `client_correlation_id` with `provider_request_id`.

```bash
source .venv/bin/activate
pyright
```

Expected assertions:

- no new or expanded type errors.
- no `Any` / `object` signatures introduced by this WU.

Coverage:

- Single-file coverage target applies to changed modules where pytest coverage is configured. `dayu/render/` and `utils/` are not touched.

## Docs Decision

Current plan artifact only: no README update in this gate.

Future implementation:

- `dayu/engine/` changes trigger `dayu/engine/README.md`; update required because Runner public contract changes.
- `dayu/host/` changes trigger `dayu/host/README.md`; update required because Host request projection / Tool Trace diagnostic behavior changes.
- `tests/` changes trigger `tests/README.md`; update required if new test class/category is added.
- Root `README.md` is not expected to change because CLI, config entry points, trace/render commands and user workflow do not change.

## Risks / Open Questions

Blocking open questions: none found in plan research.

Residual risks:

- current slice fixed: collision / illegal header risk is addressed by digest-based ASCII `client_correlation_id` and tests.
- current slice fixed: multi-iteration ambiguity is addressed by including iteration and runner call index in the digest input.
- current slice fixed: transport retry ambiguity is addressed by reusing the same identity for one logical Runner call and leaving provider-native `x-request-id` response capture intact.
- current slice fixed: static `RunnerSpec.headers` conflict is addressed by rejecting `x-client-request-id` conflict under enabled policy.
- later approved slice: README sync is deferred to Slice 4 after implementation behavior is real.
- later work unit: Tool Trace analyzer display/report logic belongs to issue-70.
- later work unit: native Anthropic response `request-id` collection and Claude Code gateway `X-Claude-Code-Session-Id` mapping require their own adapter implementation work because this repository has no native Anthropic runner.
- existing issue: issue-63 and issue-64 remain the owner/destination for this work unit until implementation closes the accepted scope.
- new issue/user decision: none currently required.

## Why This Is Not Over-Designed

- It adds one typed identity contract at the existing Agent -> Runner boundary instead of a general tracing framework.
- It uses the existing Host AttemptDispatchSnapshot and EngineEvent / EventLog / Tool Trace projection path instead of inventing a new durable correlation store.
- It does not add SQLite columns, migrations, callbacks, factories, profiles or provider lookup registries.
- It implements only the current OpenAI-compatible adapter behavior; Anthropic native / Claude Code gateway remain explicit policy notes until actual adapters exist.
- It avoids fake user identity and keeps provider governance fields separate from debugging correlation.

## Completion Report Format

Final report for the current plan / plan-fix gate must include only:

- modified files
- each accepted finding status
- whether blocking open questions exist
