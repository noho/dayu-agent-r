# P9.5 Pre-P10 Cross-Repository Hardening Implementation Plan

## Gate And Role

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR.
- Current gate: implementation-ready handoff plan.
- Role: planning agent only. This artifact is the handoff plan; it does not implement code, tests, commits, pushes, PR work, or review gates.
- Baseline branch at planning time: `p9.5-pre-p10-hardening`.
- Working tree at planning time: clean.

## Goal And Motivation

P9.5 的问题真实存在，但严重性来自“跨仓非阻塞债已经足够多，会污染 P10 Context Governance 的入口”，不是来自单个 blocker。目标是在 P10 前收口当前追踪区中不依赖 P10+ owner 的 Engine / Host / runtime / contracts hardening、cleanup 与 public contract repair，并把每一项变成可验证闭环：修复、明确不修，或发现真实 P10+ 依赖后重新归属到具体后续 phase owner。

第一性原理判断：

- 当前架构是 Host 强约束下的 `LLM in the loop`。P9.5 必须降低 Engine / Host 基础设施噪音，而不是把 Host governance 下放给 Engine、runtime、projection 或日志。
- P9.5 scope 极大，不能作为 God cleanup 口袋。计划按 semantic ownership 切片：Engine runner/parser、Host public/durable/read、LocalProxy/dispatch、ToolRuntime、runtime lane、memory/projection、schema/log/contract audit。
- 每个 slice 只处理已归属到 P9.5 的具体事项；遇到 public API、schema、状态机、用户可见行为、P10+ owner 能力或跨模块大重构需要重新裁决时必须停下。

## Direct Evidence

- `docs/host/implementation-control.md:935-938`：P9.5 design discussion accepted；必须先生成 implementation-ready handoff plan，并经双路 plan review / controller adjudication 后才可进入 implementation。
- `docs/host/implementation-control.md:940-947`：P9.5 目标是收口不依赖 P10+ phase owner 的 hardening / cleanup / public contract repair，并按日志级别语义与 Contract Ownership 做检查。
- `docs/host/implementation-control.md:963-984`：明确允许修改范围与禁止修改范围，禁止 Context Governance、RECOVERING、ToolsDiscovery、Audit / Tool Trace / Outbox sinks、RemoteProxy、purge / retention 等 P10+ 能力。
- `docs/host/implementation-control.md:986-1089`：逐项列出 P9.5 收口清单与每项边界。
- `docs/host/implementation-control.md:1091-1099`：验证要求为 `pytest -q`、`python -m pyright dayu tests`、`git diff --check`，且每个 P9.5 收口项必须有 targeted tests。
- `docs/host/implementation-control.md:1476-1527`：追踪区确认 P9.5 ownership；God module / broader hardening 只能接收已归属具体条目的 cleanup，P9.5 结束不得保留无 owner 的 broader hardening 表述。
- `docs/host/implementation-control.md:2036-2052`：design discussion 已确认关键裁决：runner 不做 factory / registry；minimal read model 维持 single-consumer reset contract；Command handle internal service 不暴露；工具定义与执行边界进入 Contract Ownership audit。
- `dayu/README.md:17-38`：整体依赖方向固定为 `UI -> Service -> Host -> Engine`，`dayu.host` public namespace 不导出 durable store、dispatch scheduler、ToolRuntime 与 policy provider。
- `dayu/README.md:99-124`：command path、WorkerProxy、ToolRuntime、wait record、RunInputBuilder、Conversation Memory、lane 的真源边界。
- `dayu/README.md:158-197`：日志 level、字段命名、脱敏与日志非真源约束。
- `dayu/README.md:199-226` 与 `docs/design.md:60-92`：Contract Ownership 与工具定义 / 执行边界；Engine 只接收 `tool_schemas` 与 `tool_executor`，不持有 `ToolDefinition` / `ToolCallable` / ToolRuntime。
- `dayu/engine/README.md:21-62`：Engine 稳定入口是 `run_agent_messages` / `run_agent_and_wait`，调用方不直接实例化 Agent 或 Runner 实现类。
- `dayu/engine/README.md:117-146`：`AsyncRunner` 是 Runner 协议；Engine 只依赖 `ToolExecutor` 协议与 tool schema 快照，不理解工具治理。
- `dayu/engine/README.md:148-160`：OpenAI Runner 具体实现类、上层 session / run 生命周期治理、工具治理、memory 与财报语义均非 Engine 稳定接口。

## Non-Goals

- 不实现 P10 Context Governance、compact provider、provider-specific tokenizer、proactive compaction 或 memory snapshot history。
- 不实现 P11 recovery、RECOVERING、positive orphan proof、active cancel watchdog、startup recovery scan 或 recovery dispatch。
- 不实现 P12 ToolsDiscovery / ScenePrepare / manifest provider / tool profile policy provider。
- 不实现 P13 Audit / Tool Trace / Outbox concrete sinks、durable duplicate ledger 或 heavy sink runner。
- 不实现 P14 RemoteProxy / RemoteStub 或 remote wire protocol。
- 不实现 P15 purge / retention / production scale policy、poller production backoff、archive 或 per-session repair filter。
- 不处理已裁决排除项：Conversation Memory snapshot history、`cancel_active_wait_records_for_run` TOCTOU、session cancel replay 多 active worker 幂等、Gemini provider state 合约、Runner usage-only / partial tool-call-delta retry 粒度、`RECOVERING` Run。
- 不引入 runner factory / registry、compat re-export / wrapper、lazy import seam、extra payload bag、`Any` / `object` 签名、无类型签名、无 owner 的 God cleanup。

## Affected Files And Modules

Implementation agents must treat this list as ownership boundaries, not a license to edit all files in one pass.

- Engine runner / agent: `dayu/engine/agent.py`, `dayu/engine/contracts/runner.py`, `dayu/engine/contracts/*`, `dayu/engine/runners/openai/*`, `dayu/engine/__init__.py`, `dayu/engine/README.md`, `tests/engine/*`, `tests/engine/runners/openai/*`.
- Host public API / command / read: `dayu/host/api.py`, `dayu/host/command.py`, `dayu/host/read_api.py`, `dayu/host/__init__.py`, `tests/host/test_public_*`, `tests/host/test_command_handle.py`, `tests/host/test_package_exports.py`.
- Host durable / schema / transitions: `dayu/host/durable/schema.py`, `dayu/host/durable/errors.py`, `dayu/host/durable/state.py`, `dayu/host/durable/run_transition.py`, `dayu/host/durable/read_model.py`, `tests/host/test_durable_schema.py`, `tests/host/test_state_schema.py`, `tests/host/test_run_attempt_transitions.py`.
- Host dispatch / LocalProxy / ingest / run input: `dayu/host/dispatch.py`, `dayu/host/local_proxy.py`, `dayu/host/engine_ingest.py`, `dayu/host/run_input.py`, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_local_proxy_engine_ingest.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_run_input_builder.py`.
- ToolRuntime / tooling: `dayu/host/tool_runtime.py`, `dayu/host/tooling.py`, `tests/host/test_toolruntime_*`, `tests/host/test_phase6_toolruntime_integration.py`, `tests/host/test_tooling_options.py`.
- Runtime lane: `dayu/runtime/lane.py`, `tests/runtime/test_lane.py`, `tests/runtime/test_lane_multiprocess.py`, `tests/runtime/test_import_boundary.py`.
- Projection / memory: `dayu/host/projection.py`, `dayu/host/memory.py`, `dayu/host/memory_repair.py`, `dayu/host/durable/memory.py`, `dayu/host/admission.py`, `tests/host/test_memory_projection.py`, `tests/host/test_projection_*`, `tests/host/test_import_boundary.py`.
- Cross-repo docs / checks: `dayu/README.md`, `dayu/host/README.md`, `dayu/engine/README.md`, `tests/README.md`, `docs/design.md`, `docs/host/design.md`, `docs/host/implementation-control.md`.

## Contract, Schema, State-Machine, And Public Interface Changes

Allowed intentional changes:

- Engine internal runner construction may be refactored so `_AsyncAgent` consumes only `AsyncRunner`; public `run_agent_messages(request)` and `run_agent_and_wait(request)` signatures must remain unchanged.
- Durable / public error translation may be centralized and made consistent. Do not add a new `HostApiErrorCode` unless controller explicitly approves; prefer existing `NOT_FOUND`, `INVALID_STATE`, `CONFLICT`, `IDEMPOTENCY_CONFLICT`, `UNSUPPORTED_OPERATION`, `INTERNAL_ERROR` and existing typed detail union.
- SQLite DDL may add CHECK / FK / index hardening for fresh schemas. If DDL changes, increment `HOST_SCHEMA_VERSION` and update fresh-schema tests only; do not implement legacy migration or compatibility reads.
- Read API enum mapping may add private single-source helpers that fail closed for unknown durable values. Do not add states or reinterpret EventLog facts.
- Package public exports may be tightened to remove accidental exposure only if tests prove the symbol is not part of documented stable public API. Do not add compatibility re-export.
- Logging may add necessary structured messages and level corrections. Logs remain non-API and non-truth.

Forbidden changes:

- No new Host / Engine state-machine states or transitions except fail-closed validation around existing states.
- No `RECOVERING` production branch, no recovery scan, no orphan proof.
- No public runner factory / registry / provider selection contract.
- No durable cursor table, duplicate ledger, tool trace sink, outbox sink, audit sink, remote wire protocol, purge / retention schema, memory history retention schema, or P10 compact schema.
- No extra payload bag or untyped metadata as a way to pass explicit parameters.

## Implementation Decisions

1. Slice order is ownership-first and dependency-aware. Engine protocol decoupling and parser hardening happen before Host ingestion checks that rely on Engine event shape. Durable schema / helper tightening happens before read / command behavior tests depend on fail-closed invariants.
2. Every slice must add or update targeted tests in the same pass. Full `pytest -q` is required at aggregate readiness, but no slice may rely only on full-suite incidental coverage.
3. Broader module cleanup is allowed only inside a slice whose owner is explicit. Mechanical split is acceptable when it reduces file size and import coupling without semantic change; semantic ambiguity stops the slice.
4. Documentation is updated after tests pass and only where README responsibility is triggered. This plan artifact itself is the only current doc change.
5. Controller must run plan review before implementation. Implementation agents must not redesign material contracts; if a slice instruction is insufficient, they stop and report the gap.
6. Dispatch order is sequential by default: S0, S1, S2, S3, S4, S5, S6, S7, S8, S9, S10, S11, S12, S13, S14, S15, S16, S17, S18. Controller may parallelize only disjoint read-only review work or explicitly independent implementation slices with non-overlapping write sets. S14 depends on S10 for shared `resolve_wait` / dispatch catch-up test ownership; S16 should run after ownership-sensitive refactors S1/S3/S11/S14 unless controller dispatches it as audit-only.
7. Shared test files must be treated as accumulated assertions. Later slices may refactor shared fixtures, but must not delete, weaken, skip, or bypass prior-slice assertions; any fixture refactor affecting a shared file must be reported in the slice artifact with the prior assertions it preserves.
8. Accepted slice commit strategy is controller-owned. High-risk slices with public API, schema, state-machine, ToolRuntime, dispatch, runner, or memory semantics stay as separate accepted commits. Adjacent low-risk slices may be combined only by explicit controller decision before staging.

## Implementation Slices

### S0 Controller Preflight And Scope Lock

- Objective: prepare implementation without changing behavior.
- Allowed files/modules: no production code. May read all files. May update `docs/host/implementation-control.md` only after controller adjudication if plan review requires scope text fixes.
- Exact changes:
  - Confirm branch remains non-protected and worktree clean.
  - Record accepted plan artifact path and plan review artifact paths.
  - Run and record `source .venv/bin/activate && python -m pyright dayu tests` as the type-check baseline before S1. If baseline has errors, classify them as pre-existing; later slices must not introduce new errors, expand existing errors, or leave touched-file errors unfixed.
  - Confirm no unrelated dirty files before dispatching S1.
- Tests/validation: `git branch --show-current`, `git status --short`, `source .venv/bin/activate && python -m pyright dayu tests`.
- Completion signal: controller state records plan artifact and enters plan review.
- Stop condition: dirty worktree ownership unclear, branch protected, or plan review opens blocking architecture / public contract / schema question.

### S1 Engine Runner Protocol Decoupling

- Objective: ensure Engine Agent main path consumes `AsyncRunner` protocol, while public entry still uses current default OpenAI-compatible runner through a private helper.
- Current evidence: `dayu/engine/agent.py` imports `AsyncOpenAIRunner`, `_build_runner(request) -> AsyncRunner` constructs it, and `_AsyncAgent` already accepts `AsyncRunner`. The remaining hardening is to remove the concrete OpenAI runner dependency from the Agent coordination module itself.
- Allowed files/modules: `dayu/engine/agent.py`, new private `dayu/engine/_default_runner.py`, `dayu/engine/contracts/runner.py` if docstring/type cleanup is needed, `tests/engine/test_agent_phase2.py`, `tests/engine/test_agent_phase3_tool_call.py`, `tests/engine/test_protocols_surface.py`, `tests/engine/test_package_exports.py`, `dayu/engine/README.md` if stable interface docs become stale.
- Exact changes:
  - Keep `_AsyncAgent.__init__(request: AgentRunRequest, runner: AsyncRunner)`.
  - Create private `dayu/engine/_default_runner.py` with a typed Chinese-docstring helper such as `build_default_runner(request: AgentRunRequest) -> AsyncRunner`. That module may import `AsyncOpenAIRunner` at module top because it is the concrete current default runner assembly point.
  - In `dayu/engine/agent.py`, remove the direct `AsyncOpenAIRunner` import and make `_build_runner(request) -> AsyncRunner` delegate to the private default runner helper. `_build_runner` remains private and current-default-only; it is not a factory or extension point.
  - Do not use lazy import to hide the dependency. The dependency is allowed only in the private default runner assembly module.
  - Do not add factory, registry, provider selection map, plugin mechanism, lazy import seam, compatibility wrapper, or metadata dispatch.
  - Add a fake `AsyncRunner` implementation test proving `_AsyncAgent` path runs without importing / instantiating `AsyncOpenAIRunner`.
  - Add public entry regression proving `run_agent_messages` still constructs current default OpenAI-compatible runner and closes it on stream close.
- Data flow/call path: `run_agent_messages(request) -> private default runner helper -> _AsyncAgent(request, runner) -> AsyncRunner.call(...)`.
- Error handling: Runner construction failure still propagates; `AsyncRunner.close()` failure remains diagnostic-only per Engine README.
- Non-goals: no new Runner public API, no Host runner selection, no provider abstraction design beyond protocol consumption.
- Targeted tests:
  - `pytest tests/engine/test_protocols_surface.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py`
  - `python -m pyright dayu/engine tests/engine`
- Stop condition: implementation requires changing public `run_agent_messages` signature, adding runner registry, or teaching Engine about Host state / tool governance.

### S2 Engine / OpenAI Runner / Parser Hardening

- Objective: close non-P10 OpenAI-compatible runner/parser correctness and observability gaps without changing Engine public state contracts.
- Allowed files/modules: `dayu/engine/runners/openai/*`, `dayu/engine/contracts/*` only for existing typed event validation, `dayu/engine/agent.py` only for Engine event stream log/metadata boundary, `tests/engine/runners/openai/*`, `tests/engine/test_metadata_boundary.py`, `tests/engine/test_engine_event_contract.py`.
- Exact changes:
  - Add / tighten tests for SSE / non-stream terminal parity, finish reason parity, tool call aggregation, context overflow classification, provider protocol errors, malformed usage handling, metadata non-contract boundary, and no log record leakage into `EngineEvent`.
  - Fix only directly evidenced parser defects. Direct evidence means at least one of: existing failing test, directly inspected current code path contradicting current contract, provider protocol behavior reproduced by a focused fake/fixture, or official provider/protocol documentation that applies to the current OpenAI-compatible parser. Theory-only edge cases and speculative hardening are out of scope.
  - Do not re-open usage-only / partial tool-call-delta retry granularity.
  - Ensure RunnerEvent / EngineEvent metadata contains observer/debug hints only; no Host state, memory, tool governance, wait record truth, or durable cursor.
  - Add missing `VERBOSE` / `DEBUG` / `WARN` logs according to Engine ownership where directly tied to parser/runner paths; log typed ids and provider request ids only.
- Error handling: protocol errors become existing typed Runner / Engine error events; context overflow classification remains reactive fallback, not Host budget truth.
- Non-goals: no proactive context governance, no provider-specific public state, no new provider contract, no retry model redesign.
- Targeted tests:
  - `pytest tests/engine/runners/openai tests/engine/test_metadata_boundary.py tests/engine/test_engine_event_contract.py`
  - `python -m pyright dayu/engine tests/engine`
- Stop condition: any fix requires new public provider state, changing retry granularity previously excluded, or making Engine understand Host governance.

### S3 Host Public Error Taxonomy And Command Handle Encapsulation

- Objective: make public Host facades consistently translate durable/internal errors and enforce `HostCommandHandle` as the only public command boundary.
- Allowed files/modules: `dayu/host/api.py`, `dayu/host/command.py`, `dayu/host/read_api.py`, `dayu/host/__init__.py`, `dayu/host/durable/errors.py` only if new internal classification is required, `tests/host/test_public_contracts.py`, `tests/host/test_public_session_api.py`, `tests/host/test_public_run_api.py`, `tests/host/test_command_handle.py`, `tests/host/test_package_exports.py`.
- Exact changes:
  - Introduce private translation helpers if needed, e.g. `_host_api_error_from_durable_error(...) -> HostApiError`, with explicit mapping for not found, invalid state, conflict, idempotency conflict, unsupported operation, internal error, retryable transaction busy / exhausted.
  - Ensure closed `HostCommandHandle` causes all public facades to return `HostApiErrorCode.INVALID_STATE` before reaching durable store.
  - Add tests that Service/UI-level imports from `dayu.host` cannot access durable store, admission service, active registry, ToolRuntime, or scheduler internals.
  - Prefer behavior tests through public facades. Reduce tests that directly inspect `_durable_store`, `_admission_service`, `_active_registry` unless they are specifically testing private command assembly.
  - Do not expose internal service through properties; do not add compatibility re-export.
- Public-interface decision: no new public facade and no new error code unless controller approves.
- Targeted tests:
  - `pytest tests/host/test_command_handle.py tests/host/test_package_exports.py tests/host/test_public_contracts.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py`
  - `python -m pyright dayu/host tests/host`
- Stop condition: consistent behavior requires changing documented public error codes, exposing internal services, or preserving old internal test access through wrappers.

### S4 Host Durable Helper API Tightening

- Objective: make low-level durable helpers no broader than production scheduler paths.
- Allowed files/modules: `dayu/host/durable/state.py`, `dayu/host/durable/run_transition.py`, `dayu/host/dispatch.py` only where production caller needs adjusted arguments, `tests/host/test_run_attempt_transitions.py`, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_resolve_wait_command.py`, `tests/host/test_public_cancel_session_runs.py`, `tests/host/test_phase6_toolruntime_integration.py`, `tests/host/test_toolruntime_accept_barrier.py`.
- Exact changes:
  - For `accept_worker_running_in_transaction`, require diagnostic payload parity with scheduler production path and fail closed when attempt / dispatch / run / execution preconditions are not all satisfied.
  - For `mark_dispatching_after_lane_row`, reject attempts to bypass lane wait, durable recheck, dispatch record status, execution id, cancel race, or dispatcher ownership diagnostics.
  - Update white-box tests to construct realistic production-path states or use public/dispatch service helpers.
  - Keep helper internal; do not export or wrap for compatibility.
- State-machine decision: no new statuses; only stricter precondition checks for existing transitions.
- Targeted tests:
  - `pytest tests/host/test_run_attempt_transitions.py tests/host/test_dispatch_scheduler.py tests/host/test_resolve_wait_command.py tests/host/test_public_cancel_session_runs.py`
  - `python -m pyright dayu/host tests/host`
- Stop condition: a test only passes by preserving helper behavior that production code must not have, or tightening requires RECOVERING / Phase 11 semantics.

### S5 Schema CHECK Hardening

- Objective: make SQLite schema a final structural defense for existing P1-P9 truth.
- Allowed files/modules: `dayu/host/durable/schema.py`, `dayu/host/durable/_validation.py`, `dayu/host/durable/*` only for Python validation parity, `tests/host/test_durable_schema.py`, `tests/host/test_state_schema.py`, `tests/host/test_wait_record_state.py`, `tests/host/test_projection_checkpoint.py`, `tests/host/test_memory_projection.py`.
- Exact changes:
  - Audit existing DDL for enum/status, ref/digest pair invariants, dispatch record states, projection checkpoint/failure rows, minimal read model rows, memory rows, wait records, payload descriptors.
  - Add CHECK / FK / index constraints only for current schema facts. If DDL changes, bump `HOST_SCHEMA_VERSION`.
  - Add direct SQLite insertion tests that bypass dataclasses and prove invalid rows are rejected.
  - Ensure Python validation rejects the same invalid shapes before DB writes when practical.
- Schema decision: fresh schema only; no old DB compatibility migration or compatibility tests.
- Targeted tests:
  - `pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py`
  - `python -m pyright dayu/host tests/host`
- Stop condition: required CHECK would encode P10/P11/P13/P15 future states/tables or break current fresh bootstrap without clear current invariant.

### S6 Read API Enum Mapping And Minimal Read Model Reset Contract

- Objective: make public read views and minimal read model status/event mapping consistent and fail closed.
- Allowed files/modules: `dayu/host/read_api.py`, `dayu/host/read_model.py`, `dayu/host/durable/read_model.py`, `dayu/host/durable/state.py` mapping helpers only, `dayu/host/projection.py` if reset helper naming/docs need tightening, `tests/host/test_public_event_stream.py`, `tests/host/test_projection_read_model.py`, `tests/host/test_public_run_api.py`, `tests/host/test_public_session_api.py`.
- Exact changes:
  - Create or tighten private mapping helpers for durable row enum -> public enum / event view. Unknown value must raise internal/durable error that public facade translates fail-closed.
  - Ensure `get_run()`, `get_session()`, `stream_run_events()` and minimal read model represent the same current Run / Attempt / Session statuses and event classes.
  - Document in code/tests that `host_run_results` and `host_session_timeline_items` are owned exclusively by `host.minimal-read-model`; reset + EventLog replay is legal repair.
  - Do not add consumer isolation, consumer_id columns, or multi-consumer schema.
- Tests:
  - Add exhaustive mapping tests for current enum values.
  - Keep DB CHECK and Python mapping tests separate. S5 owns direct SQL invalid-row tests that should fail at SQLite CHECK / FK level. S6 owns mapping fail-closed tests; for unknown enum values that DB CHECK would reject, construct the durable row dataclass or mapping helper input directly so the Python mapping layer is exercised.
  - Add minimal read model reset/replay test proving tables can be cleared and rebuilt by the fixed consumer.
- Targeted commands:
  - `pytest tests/host/test_public_event_stream.py tests/host/test_projection_read_model.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py`
  - `python -m pyright dayu/host tests/host`
- Stop condition: consistency requires changing status names, adding read-model truth, or implementing multi-consumer isolation.

### S7 LocalProxy Close / Events Race

- Objective: close local worker event stream lifecycle races without RemoteProxy or recovery semantics.
- Allowed files/modules: `dayu/host/local_proxy.py`, `dayu/host/dispatch.py`, `dayu/host/engine_ingest.py` only for local envelope handling, `tests/host/test_local_proxy_engine_ingest.py`, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_engine_ingest_mapping.py`.
- Exact changes:
  - Ensure `_DefaultLocalWorkerHandle.events()` cannot be re-read after close and cannot create multiple Engine generators for one handle.
  - Ensure `close()` is idempotent and concurrently safe enough for close while event consumption is active; no unclosed generator.
  - Scheduler must close worker handle, release lane token, and unregister active registry on clean EOF without terminal, event stream exception, worker crash, terminal accepted then late event, close during active task, and scheduler shutdown.
  - Add race tests using controlled async generators/events instead of sleeps where possible.
- Error handling: clean EOF without terminal maps to current fail/lost diagnostic path; stream exception maps to current worker failure path. Do not write RemoteProxy or recovery facts.
- Targeted tests:
  - `pytest tests/host/test_local_proxy_engine_ingest.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py`
  - `python -m pyright dayu/host tests/host`
- Stop condition: fix requires exactly-once remote event semantics, RemoteProxy wire protocol, or Phase 11 orphan recovery.

### S8 Engine Wait Confirmation Matching-Ref Hardening

- Objective: ensure Engine awaiting/suspended confirmations can only confirm Host-accepted awaiting refs.
- Allowed files/modules: `dayu/host/engine_ingest.py`, `dayu/host/waiting.py`, `dayu/host/tool_runtime.py` only for accepted ack/ref shape validation, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_wait_awaiting_accept.py`, `tests/host/test_phase7_waiting_integration.py`, `tests/host/test_wait_cancel_late_result.py`.
- Exact changes:
  - Validate accepted refs on `tool_awaiting` / `run_suspended` Engine events against current run_id, attempt_id, execution_id, wait_id, and accepted ack refs available to ingest.
  - Missing or mismatched refs produce diagnostic/rejection only; they must not create wait record, close Attempt, advance Run to `WAITING`, or append canonical tool fact.
  - Add tests for missing refs, wrong run, wrong attempt, wrong execution_id, old Attempt late confirmation, and accepted refs replay.
  - Keep LocalProxy semantics compatible with future RemoteProxy by validating envelope identity, not in-process object identity.
- Non-goals: callback endpoint, poller loop, physical external cancel, RemoteProxy wire protocol, durable duplicate ledger.
- Targeted tests:
  - `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_wait_awaiting_accept.py tests/host/test_phase7_waiting_integration.py tests/host/test_wait_cancel_late_result.py`
  - `python -m pyright dayu/host tests/host`
- Stop condition: accepted-ref validation requires new wait state transitions or changing `resolve_wait` first-committer-wins semantics.

### S9 Runtime Lane Hardening

- Objective: make `dayu.runtime.lane` robust as a layer-neutral capacity primitive.
- Allowed files/modules: `dayu/runtime/lane.py`, `tests/runtime/test_lane.py`, `tests/runtime/test_lane_multiprocess.py`, `tests/runtime/test_import_boundary.py`, `dayu/README.md` runtime section if behavior docs change.
- Exact changes:
  - Tighten acquire cancellation precision: `Task.cancel()` propagates `asyncio.CancelledError`; `CancellationToken` returns `LaneAcquireCancelled`; cancellation wins over timeout.
  - Handle heartbeat/token lost and release failure with explicit runtime lane errors or warnings; repeated release remains idempotent and cannot release another owner claim.
  - `LaneController.close(reason=...)` must wake pending acquire and best-effort release held tokens without inventing Host truth.
  - Add tests for repeated outer cancellation, untracked release failure, idle scheduler sleeping task interaction where the scheduler part can be covered by S10.
- Import boundary: `dayu.runtime.lane` may depend only on stdlib, `dayu.contracts.cancellation`, and same/lower runtime helpers.
- Targeted tests:
  - `pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py tests/runtime/test_import_boundary.py`
  - `python -m pyright dayu/runtime tests/runtime`
- Stop condition: fix requires lease/fencing/takeover semantics, Host state, EventLog, Attempt owner, or recovery proof.

### S10 Host Dispatch Lifecycle / RunInputBuilder Non-Recovery Cleanup

- Objective: close dispatch and run-input hardening that does not require Phase 11 recovery.
- Allowed files/modules: `dayu/host/dispatch.py`, `dayu/host/run_input.py`, `dayu/host/admission.py` only for catch-up port wiring with existing APIs, `dayu/host/waiting.py` / `dayu/host/command.py` only for late resolve_wait catch-up suppression, `tests/host/test_dispatch_scheduler.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_resolve_wait_command.py`, `tests/host/test_wait_cancel_late_result.py`.
- Exact changes:
  - Add durable recheck / lane release / dispatch requeue tests around scheduler lane competition.
  - Improve `_drain_loop` observability for empty queue, sleep, exception exit, and close; logs only.
  - Make worker event consumption exception paths close worker handle, release lane token, unregister active registry.
  - Make RunInputBuilder stale snapshot / optimistic TOCTOU fail closed using existing error semantics.
  - Inspect late `resolve_wait` rejection after-commit catch-up: if suppression is simple and local, suppress; if not, add focused tests and code comments proving rejection writes no canonical fact, creates no Attempt, and only produces low-risk redundant projection catch-up.
  - When editing `tests/host/test_resolve_wait_command.py`, add S10-specific assertions without weakening existing resolve_wait behavior tests, and leave fixture names/shape stable for S14 unless a fixture refactor is reported explicitly.
- Non-goals: RECOVERING dispatch, orphan proof, active cancel watchdog, RemoteProxy, status changes.
- Targeted tests:
  - `pytest tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py`
  - `python -m pyright dayu/host tests/host`
- Stop condition: fix requires startup recovery scan, recovery dispatch, or changing `WAITING` cancel / resolve race semantics.

### S11 ToolRuntime Boundary Cleanup

- Objective: split ToolRuntime ownership boundaries only where it removes real coupling, without changing semantics.
- Allowed files/modules: `dayu/host/tool_runtime.py` and new private modules under `dayu/host/tool_runtime_*.py` if needed; `dayu/host/tooling.py`; `tests/host/test_toolruntime_*`; import-boundary tests.
- Exact changes:
  - Extract only if it removes real coupling or is needed to make S12/S16 changes localized. The listed owners are candidate groupings, not required new modules; small cohesive code may stay in `tool_runtime.py`.
  - If `tool_runtime.py` remains too large for targeted changes, mechanically extract private helpers by owner: effective bundle/schema projection, accept barrier, duplicate governance, truncation/fetch_more, diagnostics.
  - Preserve all public imports unless they are undocumented accidental exports; no compatibility re-export. If moving types used by tests, prefer behavior tests through public documented entries. Tests may import a true private owner only when the test is explicitly an import-boundary or private-invariant test and no public behavior can prove the invariant.
  - Do not create test-only private re-export, facade, or compatibility wrapper to preserve old test imports.
  - Keep `ToolRuntimeHandle`, factory behavior, accept barrier, EventLog facts, duplicate semantics, truncation cursor scope and diagnostics unchanged.
- Tests:
  - Existing ToolRuntime tests must remain behavior-identical.
  - Add import-boundary tests proving Engine does not import ToolRuntime / ToolBundle / ToolDefinition.
- Targeted commands:
  - `pytest tests/host/test_toolruntime_effective_bundle.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py tests/host/test_import_boundary.py tests/engine/test_import_boundary.py`
  - `python -m pyright dayu/host tests/host dayu/engine tests/engine`
- Stop condition: extraction requires public compatibility wrappers, test-only private re-export, semantic changes, or moving ToolRuntime into contracts/runtime.

### S12 ToolRuntime Truncation / Duplicate Defensive Hardening

- Objective: harden truncation and duplicate governance behavior with focused tests.
- Allowed files/modules: `dayu/host/tool_runtime.py` or owner modules from S11, `tests/host/test_toolruntime_truncation_fetch_more.py`, `tests/host/test_toolruntime_duplicate_governance.py`, `tests/host/test_toolruntime_executor.py`, `tests/host/test_toolruntime_accept_barrier.py`, `tests/host/test_toolruntime_diagnostics.py`.
- Exact changes:
  - Add truncation tests for `text_lines`, `list_items`, `binary_bytes`, cursor missing, scope token mismatch, digest mismatch, expired cursor, used cursor, invalid limit.
  - Tighten `ToolFactAcceptCandidate` validation for `GOVERNED_ERROR` / duplicate governed outcome: policy kind, prior refs, current call id, message / reason fields must match the decision kind.
  - Add duplicate tests for `allow`, `reuse`, `hint`, `require_justification`, `hard_stop`; assert `reuse` does not call business callable and does not append second `TOOL_RESULT_ACCEPTED`.
  - Review `TruncationManager` initialization cost in the real scheduler/tool runtime build path. If object is lightweight and run-scoped by design, write a test or comment-backed decision as no fix. If genuine production scale issue appears, stop and ask controller to reassign to Phase 15.
- Non-goals: durable cursor table, durable duplicate ledger, Tool Trace projection, policy default change, Host/Engine special fetch_more branch.
- Targeted tests:
  - `pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py`
  - `python -m pyright dayu/host tests/host`
- Stop condition: hardening requires cross-run cursor recovery, durable duplicate storage, or changing duplicate policy defaults.

### S13 Message / Tool Result Size Governance

- Objective: ensure large messages, tool results and payloads are governed by existing ref/digest/payload boundaries instead of unbounded inline facts/messages.
- Allowed files/modules: `dayu/host/api.py`, `dayu/host/_event_payload.py`, `dayu/host/durable/payload.py`, `dayu/host/durable/event_log.py`, `dayu/host/tool_runtime.py`, `dayu/host/run_input.py`, `dayu/engine/agent.py` only for Engine message-size defensive checks if existing constants live there, tests under `tests/host/test_payload_store.py`, `tests/host/test_event_log_store.py`, `tests/host/test_toolruntime_executor.py`, `tests/host/test_run_input_builder.py`, `tests/engine/test_agent_message_union.py`.
- Exact changes:
  - Inventory existing size constants/defaults/maxima. Prefer extending existing constants over introducing scattered magic numbers.
  - Enforce current design: oversized canonical content must use payload/artifact/ref/digest; inline EventLog facts and Engine messages must not silently accept unbounded content.
  - When over limit, produce existing structured HostApiError or diagnostic outcome. Do not silently drop content.
  - Ensure truncation/fetch_more cannot bypass size governance by returning oversized inline continuation content.
- Public-interface decision: do not add new public error code without controller approval. If no existing typed error/detail can express size limit, stop for controller.
- Targeted tests:
  - `pytest tests/host/test_payload_store.py tests/host/test_event_log_store.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/engine/test_agent_message_union.py`
  - `python -m pyright dayu tests`
- Stop condition: needs provider tokenizer, proactive compaction, memory history, business-specific payload rules, or new user-visible public error taxonomy.

### S14 P9 Memory Cleanup And Production Catch-Up Wiring

- Objective: finish P9 memory cleanup/test hardening and production concrete catch-up port wiring without snapshot history changes.
- Allowed files/modules: `dayu/host/memory.py`, `dayu/host/memory_repair.py`, `dayu/host/durable/memory.py`, `dayu/host/durable/event_log.py` only for unused legacy continuity reader cleanup, `dayu/host/run_input.py`, `dayu/host/projection.py`, `dayu/host/command.py`, `dayu/host/admission.py`, `dayu/host/dispatch.py`, `tests/host/test_memory_projection.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_projection_runner.py`, `tests/host/test_import_boundary.py`, `tests/host/test_toolruntime_accept_barrier.py`, `tests/host/test_resolve_wait_command.py`, `tests/host/test_admission_queue.py`.
- Current direct repository evidence:
  - `current_goal` is the `PinnedStateView.current_goal: str | None` field in `dayu/host/memory.py`; the dataclass validates non-empty optional text.
  - The production write path is memory projection, not RunInputBuilder: `build_conversation_memory_snapshot_from_events(...)` iterates EventLog rows in sequence, `project_conversation_memory_event(...)` handles `USER_INPUT_ACCEPTED`, and `_pinned_state_with_user_input(...)` derives text from the user-visible payload.
  - The current enforcement direction is first-write-wins in `_pinned_state_with_user_input(...)`: read `pinned_state.current_goal`, set it to the current user input text only when it is `None`, and then preserve it while appending later user constraints.
  - `SessionContinuityProvider` is the protocol in `dayu/host/run_input.py`; `DurableSessionContinuityProvider` is the production implementation. It currently owns only resume-specific continuity and returns at most the accepted wait result system message from `_resume_wait_message_from_current_start(...)`.
  - The bypass mechanism to guard against is not durable memory itself; it is the RunInputBuilder composition point, which appends `*continuity.messages` after memory messages and before the current user prompt. Any provider that reintroduces historical raw turns there can bypass `MemoryProjectionPolicy.history_pool_size_units`.
- Exact changes:
  - For `current_goal`, keep ownership in `dayu/host/memory.py`. Do not move it into RunInputBuilder, durable schema, Context Governance, or Service. If current first-write-wins code remains as evidenced above, do not rewrite it; add targeted tests that build a snapshot from two or more `USER_INPUT_ACCEPTED` events and assert the first accepted user input remains `pinned_state.current_goal` while later user inputs are appended as `user_constraints`. Also test inline delta repair preserves an existing prior `current_goal` when the current prompt is newer.
  - If implementation discovers current code no longer enforces first-write-wins, fix only `_pinned_state_with_user_input(...)` or its immediate pure helper in `dayu/host/memory.py` using the same transaction-free pure projection direction: set `current_goal` only when previous `current_goal is None`. Do not add DB uniqueness, CAS, state-machine transition, or schema history retention for this item.
  - For `SessionContinuityProvider`, keep ownership in `dayu/host/run_input.py`. The preferred decision is remove legacy historical raw-turn behavior from production continuity entirely; production `DurableSessionContinuityProvider` should remain resume-specific and must not call `read_run_input_continuity_events(...)` or emit prior user/assistant raw turns.
  - Tighten rather than remove only if a non-history use is directly evidenced, such as resume wait accepted fact reconstruction. The tightened provider may emit only bounded, non-history, current-run resume/system facts that cannot be represented by memory projection yet; it must not accept parameters that control history count, raw turn inclusion, before-event replay, or budget bypass.
  - Remove unused legacy reader paths or parameters when no production code uses them. If `EventLogStore.read_run_input_continuity_events(...)` / `read_run_input_continuity_events(...)` are unused after confirming imports, remove them or keep them only if another non-S14 owner directly uses them; do not preserve them through compatibility wrappers.
  - Add preview/reasoning/display-only exclusion tests; final answer remains assistant conclusion, not verified fact.
  - Add memory import-boundary automation: Host memory must not import Service/UI/Fins/Engine implementation modules.
  - Add catch-up end-to-end tests for user input, accepted tool fact, and `resolve_wait` committed facts.
  - When editing `tests/host/test_resolve_wait_command.py`, preserve S10 late-rejection/catch-up assertions. If S14 needs shared fixture changes for memory catch-up, report the fixture refactor and list the S10 assertions that still pass.
  - Wire production command/admission/scheduler composition to concrete memory catch-up port where already designed; keep test/dev no-op boundary explicit.
  - Catch-up failure logs/projection-local failure only; never rollback command, mutate Run/Attempt/EventLog, or become recovery.
- Non-goals: snapshot history retention, long-term retrieval index, public memory edit/reset/forget, final answer as verified fact, Host import of `dayu.fins`, P10 Context Governance.
- Targeted tests:
  - `pytest tests/host/test_memory_projection.py -k "current_goal or history_pool or final_answer or preview or import or catch_up"`
  - `pytest tests/host/test_run_input_builder.py -k "session_continuity or memory or current_goal or resume"`
  - `pytest tests/host/test_projection_runner.py tests/host/test_import_boundary.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py`
  - `python -m pyright dayu/host tests/host`
- Stop condition: concrete catch-up needs snapshot history retention, compaction provider, changing memory truth semantics, or any `SessionContinuityProvider` historical raw-turn path appears necessary for current behavior. Historical continuity must be reassigned to memory/P10 design rather than restored in RunInputBuilder.

### S15 Engine / Host Necessary Logs By Level

- Objective: add only necessary logs for P1-P9 implemented paths according to documented level semantics.
- Allowed files/modules: `dayu/engine/agent.py`, `dayu/engine/runners/openai/*`, `dayu/host/command.py`, `dayu/host/admission.py`, `dayu/host/dispatch.py`, `dayu/host/local_proxy.py`, `dayu/host/engine_ingest.py`, `dayu/host/tool_runtime.py`, `dayu/host/waiting.py`, `dayu/host/projection.py`, `dayu/host/memory_repair.py`, `tests/engine/*logging*`, `tests/host/*logging*` or focused existing tests with `caplog`.
- Exact changes:
  - Audit existing Engine/Host log calls before adding new ones. Classify each relevant path as already correct, missing, mis-leveled, missing required typed ids/refs, or unsafe because it logs oversized/sensitive data.
  - Follow each module's existing logger acquisition pattern. Where local code already uses module-level `logging.getLogger(__name__)`, keep that pattern and do not introduce constructor-injected loggers. If a module has no logger and needs one, default to module-level `_LOGGER = logging.getLogger(__name__)`.
  - Add `VERBOSE` skeleton logs for Engine run/iteration/runner call/tool loop/terminal, Host command accepted/committed, dispatch state advance, WorkerProxy accept, ingest, terminal closeout, projection catch-up, wait resolve.
  - Add `DEBUG` logs for bounded decisions, counts, cursor/digest refs, CAS outcomes, policy/diagnostic refs.
  - Add `WARN` for recoverable failures that do not break truth, `ERROR` for operation failures, `CRITICAL` for invariant/contract breaks.
  - Ensure logs never include full prompts, tool args/results, delta bodies, raw cursor/scope token, provider secrets, Fins source text, authorization claims, or large payloads.
  - Add caplog tests for level and redaction. Prefer exact field presence assertions over full log-line string matches.
- Non-goals: observability platform, UI output, audit/tool trace/projection checkpoint, P10+ path logs.
- Targeted tests:
  - `pytest tests/engine tests/host -k "log or logging or diagnostics or dispatch or ingest or projection or toolruntime"`
  - `python -m pyright dayu tests`
- Stop condition: logging change would require storing new durable facts, adding audit/tool trace sink, or exposing logs as public API.

### S16 Contract Ownership Audit And Import/Public Surface Fixes

- Objective: verify implemented contracts live at the correct layer and fix concrete violations.
- Allowed files/modules: `dayu/contracts/*`, `dayu/engine/*`, `dayu/host/*`, `dayu/runtime/*`, package `__init__.py` files, `tests/*/test_import_boundary.py`, `tests/*/test_package_exports.py`, `tests/host/test_public_contracts.py`, `tests/engine/contracts/*`.
- Exact changes:
  - Add automated import-boundary tests:
    - `dayu.runtime` does not import `dayu.engine`, `dayu.host`, `dayu.service`, `dayu.ui`, `dayu.fins`.
    - Engine does not import `ToolDefinition`, `ToolBundle`, `ToolCallable`, ToolRuntime, concrete tools, Host modules, memory modules, or Fins modules.
    - Host does not import Service/UI/Fins and does not scan business tool modules.
    - `dayu.contracts` does not import concrete Engine/Host/runtime implementation modules.
  - Audit public exports: documented `dayu.engine` and `dayu.host` exports remain stable; accidental private exports are removed only if not documented.
  - Move misplaced types to true owner only when direct evidence shows ownership violation. Do not create compatibility re-export.
  - Validate `fetch_more` is injected only by ToolRuntime factory into attempt-local effective ToolBundle.
- Non-goals: future P10+ contracts, public API rewrite, compatibility shims.
- Targeted tests:
  - `pytest tests/runtime/test_import_boundary.py tests/engine/test_import_boundary.py tests/engine/contracts/test_import_boundary.py tests/host/test_import_boundary.py tests/engine/test_package_exports.py tests/host/test_package_exports.py tests/host/test_public_contracts.py`
  - `python -m pyright dayu tests`
- Stop condition: fixing ownership requires moving a documented public contract or breaking current external imports; controller must adjudicate.

### S17 Documentation And Control Tracking

- Objective: update stable documentation and tracking after implementation evidence exists.
- Allowed files/modules: `dayu/README.md`, `dayu/engine/README.md`, `dayu/host/README.md`, `tests/README.md`, `docs/design.md`, `docs/host/design.md`, `docs/host/implementation-control.md`.
- Exact changes:
  - Update only README sections whose responsibilities are triggered by real code changes.
  - `dayu/engine/README.md`: update runner interface/private default runner wording if S1/S2 changes stable current interface docs.
  - `dayu/host/README.md`: update Host public/durable/dispatch/ToolRuntime/memory current behavior if S3-S15 changes stable boundaries.
  - `dayu/README.md` / `docs/design.md`: update only if log level semantics, Contract Ownership, or tool boundary stable descriptions changed.
  - `tests/README.md`: update only if test layering/commands/conventions changed.
  - `docs/host/implementation-control.md`: record P9.5 slice status, residual risk disposition, validation evidence, and clear P9.5 tracking items.
- Non-goals: process diary, future design promises, implementation details, version log.
- Validation: `git diff --check`; README examples must match current code.
- Stop condition: documentation would need to claim future P10+ behavior as implemented.

### S18 Aggregate Validation And Readiness Evidence

- Objective: prove all slices close P9.5 scope and prepare for aggregate deepreview.
- Allowed files/modules: review/validation artifacts only if controller requires them; no feature code unless fixing accepted findings.
- Required validation commands:
  - `source .venv/bin/activate`
  - `pytest -q`
  - `python -m pyright dayu tests`
  - `git diff --check`
  - Optional focused re-runs from failed slice tests after fixes.
- Completion signal:
  - Every P9.5收口项 is marked fixed, explicitly not fixed with reason, or reassigned to a concrete P10+ phase owner with dependency evidence.
  - No remaining “后续 hardening” / “broader cleanup” without owner.
  - Implementation artifacts for each slice list changed files, validations, docs decision, residual risks and stop status.
- Stop condition: full validation failure, unclassified residual risk, missing targeted tests for any P9.5 item, or controller cannot map a tracking item to fixed / not fixed / reassigned.

## Tests And Validation Matrix

Per-slice commands are required before code review for that slice. Aggregate commands are required before ready-to-open-draft-PR:

```bash
source .venv/bin/activate
pytest -q
python -m pyright dayu tests
git diff --check
```

Additional review checks:

- Import-boundary tests must prove no reverse dependency and no misplaced contract ownership.
- Logging tests must prove level semantics and redaction, not exact prose.
- Schema tests must include direct invalid-row SQLite insertion cases.
- LocalProxy/dispatch/lane race tests should use deterministic async synchronization instead of arbitrary sleep where possible.
- Each P9.5 tracking item must have at least one targeted test or an explicit controller adjudication explaining why code change is not needed.

## Documentation Decision

This plan artifact is the only documentation change in the current planning task.

During implementation:

- Update README files only after tests pass and only if changed code makes current README text stale.
- Do not update root `README.md` unless CLI/config/project-level user workflow changes.
- Update `dayu/README.md` only for stable architecture/log/Contract Ownership/tool-boundary changes.
- Update `dayu/engine/README.md` for Engine runner/interface behavior changes.
- Update `dayu/host/README.md` for Host public/durable/dispatch/ToolRuntime/memory stable behavior changes.
- Update `tests/README.md` only if testing conventions or commands change.
- Update `docs/host/implementation-control.md` after each accepted slice / aggregate gate to remove or reassign P9.5 tracking items.

## Review Gates

- Plan review: AgentMiMo and AgentDS double review before implementation. Controller adjudicates every finding.
- Slice review: each implementation slice must have implementation artifact, code review, accepted finding fix, re-review, and accepted local slice commit before the next slice unless controller explicitly allows combining adjacent low-risk slices.
- Aggregate deepreview: after all slices, run `$deepreview --base main` or controller-approved base. Accepted findings must be fixed and re-reviewed.
- Draft PR gate: only after accepted deepreview commit and user authorization. This plan does not authorize push, PR creation, merge, approve, mark ready, request reviewers, or external comments.

## Stop Conditions

Implementation must stop and return to controller if:

- A slice needs P10 / P11 / P12 / P13 / P14 / P15 owner semantics.
- A fix requires public API, schema, state-machine, or user-visible behavior not already decided here.
- A helper cannot be tightened without preserving old tests through compatibility wrapper.
- A module cleanup becomes cross-owner semantic rewrite.
- A logging change would make logs public truth, audit, projection checkpoint, tool trace, or UI output.
- A schema hardening requires legacy migration / compatibility handling.
- Tests reveal a currently undocumented external dependency on internal Host service or Engine runner implementation.
- Full validation fails and failure is not clearly local to the current slice.

## Risks And Open Questions

Blocking Questions For Controller:

- 当前无已知 blocking question。P9.5 design discussion 已裁决 runner 不做 factory/registry、minimal read model single-consumer、Command handle internal service 不暴露、工具边界进入 Contract Ownership audit。

Plan risks requiring controller attention during implementation:

- Message / tool result size governance may discover no existing typed public detail fits an over-limit error. If so, controller must decide whether to add a typed detail variant or keep a diagnostic-only internal error.
- Contract Ownership audit may uncover documented public exports that are actually misplaced. Removing them is a public-interface decision and must stop for controller.
- Schema CHECK hardening may require schema version bump. Fresh-schema-only is allowed, but any pressure to read old DBs must be rejected or separately authorized.
- ToolRuntime module split may become too broad. If extraction touches semantics, stop and re-slice rather than continuing as cleanup.
- Production memory catch-up wiring may reveal snapshot history coupling. That sub-item must be reassigned to the separate snapshot history PR, not solved in P9.5.

Non-blocking working assumptions:

- Current `.venv` exists and supports Python 3.11 project validation.
- Existing test suite remains the source of truth for current public behavior; failing tests that encode internal bypasses should be updated only when the production boundary is stricter and documented by this plan.
- Full `pytest -q` may be expensive; slice agents still run targeted tests first and aggregate gate runs full validation.

## Completion Report Format

Each implementation or fix agent must report:

```markdown
## Gate

- Work unit:
- Slice:
- Approved plan:
- Role:

## Scope

- Allowed files/modules:
- Non-goals honored:

## Changed Files

- path: summary

## Implemented Plan Items

- item:
- evidence:

## Tests And Validation

- command:
- result:
- important assertions:

## Docs Decision

- updated:
- not updated and why:

## Residual Risks

- fixed in current slice:
- covered by later approved slice:
- assigned to later phase/work unit:
- requires controller/user decision:

## Stop Status

- complete / stopped
- stop reason if any:
```

Controller aggregate closeout must report:

- All P9.5 tracking items and status: fixed / not fixed with reason / reassigned with owner.
- Slice commits and review artifacts.
- Validation commands and results.
- README/docs updates.
- Remaining risks with owner/destination.
- Whether the branch is ready for draft PR authorization.
