# WU-DUR / WU-OBS / WU-CM Closeout Plan

## Gate Scope

本 artifact 只服务 plan gate。当前不进入 implementation / fix / review / commit / push / PR，不修改生产代码、测试、README 或 control doc。

计划状态：code-generation-ready after plan-fix。

blocking open question：无。

核心判断：四个 WU 可以按依赖顺序组合推进，但 implementation 前必须先完成 WU-DUR-P01 的设计真源回写。`docs/host/design.md` 已给出 EventLog 真源、payload/ref/digest、RunInputBuilder 与 LLM-facing compact 边界；但 runner-call reconstruction atoms / manifest 的稳定字段、状态副作用、payload / artifact 边界和 projector metadata 还没有写成 design.md stable contract。该设计回写必须作为 Slice 0，不得跳过。

## Goal

按依赖顺序关闭以下 correctness chain：

1. WU-DUR-P01：补齐 EventLog / payload / artifact 中 runner-call reconstruction atoms，使历史 LLM-facing runner call input 可由 durable truth 与版本化 projector 重建或明确 limited-signal。
2. WU-OBS-P00：定义 Runner call input reconstruction signals，让 Tool Trace / analyzer 消费 DUR-P01 refs、digests、projection artifact refs 与 projector metadata，而不是依赖日志、当前代码或 prompt 猜测。
3. WU-CM-01-F02：改善 compact evidence material 的 `query_text`。`EvidenceReadableItem.tool_name` 在设计中已存在；真实缺口是 `query_text` 缺少 durable arguments / semantic query 的业务可读表达，不能把问题表述成完全缺失 tool identity。
4. WU-CM-01-F01：修正 Host public Conversation Memory smoke correctness，用四个 public smoke / focused tests 验证前三个 WU 的 durable truth、observability 和 LLM-facing prompt 质量。

## Motivation

目标成立。当前缺口不是单个 smoke 断言过窄，而是 Host durable truth、runner-call observability、compact evidence readability 与 public smoke 验收之间的同源缺口。

直接影响：

- recovery / resume / replay 的架构要求是从 EventLog canonical facts 重建 messages，不能依赖旧 provider request 或 Engine 内存。
- analyzer 若只能看日志 `message_count` 或当前代码重跑 projector，会输出看似完整但无法校验的 historical dump。
- compactor evidence material 的 `tool_name` 已有设计位置，但 `query_text` 当前退化为 `tool_call_id=...`，LLM 缺少“工具为什么被调用、参数是什么”的业务语义锚点。
- public smoke 若只看终态成功，无法证明 compact 后实际 LLM-facing input 与 durable projection 对齐。

## Success Signals

- DUR-P01：tool-call roundtrip、compact 后 follow-up、Host-owned compactor internal runner call 三类路径都有 durable input assembly manifest 或明确 limited-signal 诊断；EventLog 不内联完整 messages / provider request / memory snapshot / compact material。
- OBS-P00：Tool Trace / analyzer fixture 可通过 refs / digests / projector metadata 定位 runner-call input，校验 message_count、role sequence digest、projection artifact digest；字段不足时输出 structured limited-signal。
- F02：`evidence_material[*].tool_name` 继续承担工具身份；`query_text` 不再退化为裸 `tool_call_id=...`，而是来自 durable arguments 或 optional semantic query；query text 不包含 event id、payload ref、digest、cursor 或 policy ref。
- F01：control doc 列出的四个 utility smoke scripts 完成逐一审计；相关 focused public smoke tests 覆盖 runner call 最多一个 system message、compactor prompt 不暴露内部实现术语、compact 后 message_count / manifest / dump item 数量可解释。
- `source .venv/bin/activate` 后受影响 pytest 通过，pyright 0 errors；README 按触发规则同步。

## Non-goals / Scope Boundary

- 不实现完整 Tool Trace analyzer / WU-OBS-00。
- 不把完整 provider request/messages、完整 memory snapshot、完整 compact material 或 analyzer bundle 内联进 EventLog canonical payload。
- 不让 Tool Trace / Audit / memory snapshot 反向成为 EventLog、recovery、resume、memory 或 Run 状态迁移真源。
- 不用 smoke、prompt、日志或当前代码猜测补 durable truth。
- 不改变 Engine/Runner 执行语义来掩盖 Host durable atom 缺口。
- 不保留旧 schema 兼容逻辑；本轮按 fresh schema 起库与测试。
- 不把业务工具 schema 特例硬编码进 compact material projection。

## Design.md Alignment

已对齐的设计真源：

- [docs/host/design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:43)：projection、timeline、audit、usage、tool trace、outbox、memory snapshot 都不能反向成为 EventLog 真源。
- [docs/host/design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:49)：EventLog / State Transition 是 EventLog append、sequence 与 canonical_fact 索引原子更新 owner。
- [docs/host/design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:52)：RunInputBuilder 负责聚合 EventLog、memory snapshot、compact artifact、tool schema snapshot 与场景约束，构造 `AgentRunRequest.messages`。
- [docs/host/design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:1437)：canonical event 必须记录 payload ref / descriptor 与 digest，或其它可校验 ref；大 payload 应外移。
- [docs/host/design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:1516)：当前 `TOOL_CALL_REQUESTED` 设计矩阵只要求 tool_call_id / tool name / normalized args digest。
- [docs/host/design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:2495)：RunInputBuilder 输出必须能由 input fact refs、memory snapshot cursor、compact artifact refs 与 policy snapshot 解释。
- [docs/host/design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:2582)：LLM-readable compact input 只能包含用户 / 业务可理解材料。
- [docs/host/design.md](/Users/leo/workspace/dayu-agent-r/docs/host/design.md:2591)：compact input/output 不得暴露 EventLog id、payload ref、digest、cursor、policy 等内部治理细节。

implementation 前必须先回写 design.md：

- 新增 runner-call input assembly manifest 的稳定 contract：字段、event class、状态副作用、消费方、payload / artifact ref 边界；字段 shape 必须至少等价于本 plan 的 consolidated contract appendix。
- 扩展 `TOOL_CALL_REQUESTED` contract：accepted arguments 明文的 durable ref/digest、normalized arguments digest 校验、可选 semantic query / readable input。
- 定义 typed refs/digests/projector metadata：`runner_call_index`、`iteration_id`、message_count、role sequence digest、per-message source refs / digest、RunInput projector id/schema version/digest、tool-result projector id、memory / compact material projector id、tool schema snapshot refs。
- 定义 Host-owned compactor internal runner call 的 parent run / compaction operation / projection artifact refs，明确它不是 Host admitted user Run。
- 明确这些 manifest / projection artifact 只服务 recovery explanation、trace、audit、debug 和 smoke validation；不得成为 Run 状态迁移、memory projection 或 recovery 的反向真源。

## First-principles Judgment And Direct Evidence

第一性原理判断：

- 模型调用是无状态的。若 Host 声称能恢复、审计和解释历史 runner call，就必须持有可校验 durable atoms，而不能依赖日志、当前代码、smoke fixture 或 provider request 内存。
- EventLog 不应变成 messages dump store。正确边界是：canonical facts 保存最小恢复事实、refs、digests 与 projector metadata；大体积 LLM-facing projection 进入 payload/artifact，并可由 source refs/digests 校验。
- Compact input 是给无状态 LLM 读的材料，必须业务可读。裸 `tool_call_id`、event id、payload ref、digest 只能作为 Host 内部 provenance，不是 query 语义。
- Smoke 是验收手段，不是真源。Smoke 可以证明 production path 输出对齐，但不能补造 durable truth。

直接代码证据：

- [dayu/engine/contracts/engine_events.py](/Users/leo/workspace/dayu-agent-r/dayu/engine/contracts/engine_events.py:56)：`IterationStartedData` 只有 `iteration_id`、`iteration_index`、`message_count`。
- [dayu/engine/agent.py](/Users/leo/workspace/dayu-agent-r/dayu/engine/agent.py:1104)：Engine 在 runner call start 只 emit `IterationStartedData(... message_count=len(messages))`。
- [dayu/engine/contracts/engine_events.py](/Users/leo/workspace/dayu-agent-r/dayu/engine/contracts/engine_events.py:110)：`ToolCallRequestedData` 内部有 `arguments` 明文字段。
- [dayu/host/engine_ingest.py](/Users/leo/workspace/dayu-agent-r/dayu/host/engine_ingest.py:4241)：Host preview payload 对 `ToolCallRequestedData` 只保存 `tool_call_id`、`tool_name`、`index_in_iteration`、`argument_key_count`、`provider_state_present`。
- [dayu/host/tool_runtime.py](/Users/leo/workspace/dayu-agent-r/dayu/host/tool_runtime.py:3268)：canonical `TOOL_CALL_REQUESTED` payload 当前只有 session/run/attempt/execution、tool ids、schema/identity digest、`normalized_arguments_digest`、`semantic_input_digest` 等字段，没有 arguments payload ref。
- [dayu/host/compaction_evidence.py](/Users/leo/workspace/dayu-agent-r/dayu/host/compaction_evidence.py:257)：`_readable_query_text()` 当前固定返回 `tool_call_id={envelope.tool_call_id}`。
- [dayu/config/prompts/scenes/conversation_compaction.md](/Users/leo/workspace/dayu-agent-r/dayu/config/prompts/scenes/conversation_compaction.md:3)：compactor system prompt 暴露 `Host-owned context compaction`。
- [dayu/config/prompts/scenes/conversation_compaction.md](/Users/leo/workspace/dayu-agent-r/dayu/config/prompts/scenes/conversation_compaction.md:14)：prompt 要求输出符合 `ConversationCompactOutputVNext` schema。
- [dayu/config/prompts/scenes/conversation_compaction_user.md](/Users/leo/workspace/dayu-agent-r/dayu/config/prompts/scenes/conversation_compaction_user.md:52)：user prompt 仍出现 `vNext 字段` 等迁移术语。
- [tests/host/public_smoke_support.py](/Users/leo/workspace/dayu-agent-r/tests/host/public_smoke_support.py:357)：public smoke support 已能记录 `AgentRunRequest` 和 runner `messages_seen`，说明测试可直接断言 runner-call messages，不需要新增测试私有入口。
- [docs/host/issues-implementation-control.md](/Users/leo/workspace/dayu-agent-r/docs/host/issues-implementation-control.md:698)：WU-DUR-P01 已定义为 WU-OBS-P00 / WU-OBS-00 durable truth 前置。
- [docs/host/issues-implementation-control.md](/Users/leo/workspace/dayu-agent-r/docs/host/issues-implementation-control.md:760)：WU-OBS-P00 只定义 runner-call input reconstruction signal contract，不实现完整 analyzer。
- [docs/host/issues-implementation-control.md](/Users/leo/workspace/dayu-agent-r/docs/host/issues-implementation-control.md:487)：WU-CM-01-F02 明确依赖 DUR-P01，不允许用 prompt 猜测或 hardcode 伪造 query text。
- [docs/host/issues-implementation-control.md](/Users/leo/workspace/dayu-agent-r/docs/host/issues-implementation-control.md:445)：WU-CM-01-F01 是 public smoke correctness closeout，审计 control doc 列出的四个 utility smoke scripts。

## Affected Files / Modules

设计与文档：

- `docs/host/design.md`
- `dayu/host/README.md`
- `dayu/engine/README.md`
- `dayu/config/README.md`
- `tests/README.md`

Engine contracts / agent:

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/tool_records.py`
- `dayu/engine/agent.py`
- `dayu/engine/__init__.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/test_agent_phase2.py`

Host durable / payload / ingest / projection:

- `dayu/host/durable/schema.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/_event_payload.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/run_input.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/compaction_evidence.py`
- `dayu/host/tool_trace.py`
- `dayu/host/compact_artifact.py`
- `dayu/host/compact_payload.py`

Config / prompts / smoke:

- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/public_smoke_support.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_public_open_host_multiturn_smoke.py`
- `tests/host/test_public_tool_wiring_smoke.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_run_input_builder.py`
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_diagnostics.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`

## Contract / Schema / State-machine / Public-interface Changes

Contract changes:

- Add a typed `RunnerCallInputAssemblyManifest` contract exactly defined in the consolidated contract appendix. It describes a logical runner call input using refs/digests/projector metadata, not full message text.
- Engine owns only execution-local observations it can see without Host durable store access: `iteration_id`, `iteration_index`, `message_count`, and optional actual runner-call role sequence digest if implemented in the Engine event contract. Host owns `runner_call_index`, manifest refs/digests, source refs, projector metadata, compact/memory/tool schema refs, and all EventLog / payload descriptor writes.
- Replace the overlapping `runner_call_kind` list with the closed classification in the appendix: `runner_call_kind` is non-overlapping, and retry / replay / resume / length / forced-answer details are carried by `runner_call_trigger_reason`.
- Extend `TOOL_CALL_REQUESTED` canonical payload with accepted arguments durable atom using a mixed storage strategy: bounded inline canonical JSON when `arguments_json_size_bytes <= payload_inline_threshold_bytes`; otherwise payload descriptor kind `tool_call_arguments_json`. Keep `normalized_arguments_digest` and verify both are同源.
- Add optional durable semantic query / readable input atom when tool/runtime can provide it through typed contract. It is an independent optional readable atom, not a replacement for existing `semantic_input_digest` and not assumed to be its preimage.
- Add per-message manifest entries with `role`, `content_digest`, `source_refs`, optional `projection_artifact_ref`, and projector metadata id/digest as defined in the appendix.

Schema changes:

- Fresh schema only. Add columns and payload descriptor kinds for `runner_call_input_manifest`, `runner_call_projection_artifact`, `tool_call_arguments_json`, `tool_call_semantic_query_text`, and `compactor_input_projection` as needed.
- Tool Trace hot projection may add nullable manifest ref / digest / runner call identity fields. These are projection fields, not truth.
- No compatibility read path for old DB. Tests create fresh schema.

State-machine changes:

- No Run / Attempt status transition semantics change.
- Add `RUNNER_CALL_INPUT_ASSEMBLED` as a canonical audit/reconstruction event with no Run / Attempt status side effect. Its hot payload only records scope, runner-call identity, manifest descriptor ref/digest and validation status. The manifest body is stored as payload descriptor / artifact according to `payload_inline_threshold_bytes`; it is not Run state truth and must not drive recovery, memory projection or lifecycle transitions.
- Engine internal tool-loop execution order remains unchanged.

Public interface changes:

- Engine public event contract may change only for Engine-owned execution observations. Host-owned `runner_call_index` and manifest refs must not be added to `IterationStartedData`.
- Host public `SubmitFollowupRequest`, `open_host(options)` and Service-facing `HostEvent` should not change.
- Tool Trace query contract may expose additional diagnostic fields / manifest refs; it remains read-only projection.

## Implementation Decisions

Durable atom vs derived artifact:

- Durable atoms are: accepted user input refs/digests, accepted tool call arguments refs/digests, accepted tool result refs/digests, compact artifact refs/digests, memory snapshot cursor used by RunInputBuilder, tool schema snapshot refs/digests, runner-call manifest refs/digests, projector metadata.
- Derived artifacts are: fully rendered LLM-facing messages, compactor rendered user prompt, expanded tool message text, analyzer dump bundle. They may be written under artifact storage with digest and producer metadata, but cannot become EventLog truth or recovery source by themselves.

Typed refs / digests / projector metadata:

- Every manifest ref must identify producer kind, schema version, parent run/attempt/execution/iteration, and content digest.
- Digests use canonical JSON serialization and stable message projection rules.
- Projector metadata includes stable id, schema version, source code/config digest where applicable, and semantic purpose. It must not be a raw Python module path in LLM-facing material.

Runner-call input assembly manifest:

- Manifest captures message count, role sequence, per-message source refs, source cursor, tool schema refs, compact/memory refs, context fallback decision refs, and projector metadata.
- It does not inline full messages. For small human-readable projections, payload may inline bounded text only when the design.md contract explicitly allows it and tests prove no large prompt/material enters EventLog.
- It must cover initial RunInputBuilder call and Engine-internal continuation calls after tool results, fallback calls, and length continuation calls.

Compactor internal runner call:

- Treat compactor proposal call as `runner_call_kind=compactor_proposal`, with explicit parent/self identity from `CompactorRunnerCallIdentity`, not as a Host admitted user Run.
- Store compactor system prompt asset digest, user template digest, `ConversationCompactInput` projection artifact ref/digest, compaction request digest, and accepted/rejected attempt association.
- Analyzer can dump or report limited-signal by resolving these refs; it must not rerun compaction material selection to rediscover historical input.

Compact query readable projection:

- `_readable_query_text()` must read durable tool-call request atoms by `tool_call_requested_event_ref`.
- Prefer semantic query / readable input if present; otherwise render stable bounded `tool_name(arguments_json)` from durable normalized arguments.
- If atoms are missing, return structured limited-signal diagnostic for trace/smoke; do not silently fall back to only `tool_call_id`.
- Query text must not expose event ids, payload refs, digests, cursor, artifact descriptors, policy refs, or Host internal state.

Tool Trace signal contract:

- Tool Trace stores refs/digests/manifest summaries sufficient to locate runner-call input artifacts.
- Analyzer output can say `complete`, `limited_signal`, or `mismatch`.
- `mismatch` must name which check failed: message_count, role sequence digest, missing projection artifact, missing tool-call arguments atom, missing compactor manifest, unsupported projector version.

Smoke verification boundary:

- Smoke verifies public path behavior and prints/validates manifest/dump signals.
- Smoke must fail fast on multiple system role messages where the scenario asserts one-system-message convergence.
- Smoke must not inspect private DB tables except through accepted focused test helpers. Human-run utils may print public diagnostics and artifact refs but must not become the only validation for durable truth.

## Consolidated Contract Appendix

本 appendix 是 Slice 0 写回 `design.md` 的最低 contract shape。implementation 不得在代码中发明弱于本 appendix 的字段、枚举、ref / digest 边界或校验规则；若 Slice 0 design review 要求调整字段名，必须保持同等语义与同等可验证性。

Scalar aliases used below：

- `Digest`：lowercase hex SHA-256 digest over the contract's stated canonical bytes.
- `HostInternalRef`：typed Host ref string or descriptor object used only by Host / trace / smoke consumers; never LLM-facing.
- `JsonObject`：JSON-compatible mapping with string keys and JSON scalar/list/object values; no Python `Any`, provider objects, binary blobs or callable values.

### Runner-call storage form

Runner-call manifest 使用组合形态：

- canonical event：新增 `RUNNER_CALL_INPUT_ASSEMBLED`，只表达“某次 logical runner call input 已完成 durable assembly manifest 写入”。它没有 Run / Attempt 状态副作用，不参与 terminal decision、recovery scan、memory projection 或 dispatch decision。
- payload descriptor / artifact：manifest body 使用 descriptor kind `runner_call_input_manifest` 存储。若 canonical JSON 字节数小于等于 design.md 第 13.1 节的 `payload_inline_threshold_bytes`，可写 SQLite payload；超过阈值必须写 artifact root 并通过 payload descriptor 引用。
- projection artifact：完整 LLM-facing rendered messages 若为 debug / analyzer 需要生成，只能作为 derived artifact kind `runner_call_projection_artifact`，并由 manifest ref/digest 指向；不得作为 canonical event hot payload。

`RUNNER_CALL_INPUT_ASSEMBLED` hot payload required fields：`session_id: str`、`host_run_id: str`、`attempt_id: str | null`、`execution_id: str | null`、`runner_call_index: int`、`runner_call_kind: RunnerCallKind`、`runner_call_trigger_reason: RunnerCallTriggerReason`、`manifest_payload_ref: HostInternalRef`、`manifest_digest: Digest`、`manifest_schema_version: str`、`validation_status: "complete" | "limited_signal" | "mismatch"`。validation rule：`manifest_digest` 必须等于 manifest body canonical JSON digest；scope fields 必须与 manifest body identity fields 一致。

### RunnerCallInputAssemblyManifest

| field | type | required | business / Host semantics | digest / ref boundary | validation rule |
|---|---|---:|---|---|---|
| `schema_version` | `str` | yes | manifest contract version | in manifest body | must equal design-approved current version |
| `manifest_id` | `str` | yes | stable logical id for this manifest body | not LLM-facing | unique within payload/artifact namespace |
| `session_id` | `str` | yes | parent Session scope | canonical scope, not business fact | equals canonical event `session_id` |
| `host_run_id` | `str` | yes | Host admitted user Run for ordinary calls; parent user Run for compactor calls | internal Host id | equals canonical event `host_run_id` |
| `attempt_id` | `str | null` | conditional | Host Attempt that owns this runner call when one exists | internal Host id | required for ordinary dispatch after Attempt creation; null allowed for pre-dispatch proactive compact |
| `execution_id` | `str | null` | conditional | Engine execution envelope id when call belongs to an Engine execution | internal Engine/Host correlation id | required for Engine-emitted ordinary/tool continuation calls |
| `runner_call_index` | `int` | yes | Host-owned monotonic zero-based index per `host_run_id`; compactor operations use a separate zero-based index scoped by `compaction_operation_id` | stored in event hot payload and manifest | first call is 0; each later call in the same scope increments by 1 |
| `runner_call_kind` | `RunnerCallKind` | yes | non-overlapping business kind of the logical call | hot payload mirror | value must be in closed enum below |
| `runner_call_trigger_reason` | `RunnerCallTriggerReason` | yes | why this call was assembled now | hot payload mirror | value must be compatible with `runner_call_kind` |
| `iteration_id` | `str | null` | conditional | Engine iteration id for calls observed by Engine | Engine-owned observation | required when Engine emitted an iteration-started event |
| `iteration_index` | `int | null` | conditional | Engine iteration index | Engine-owned observation | non-negative when present |
| `message_count` | `int` | yes | number of messages actually sent to the runner/provider boundary | digest input summary only | must equal count of `message_entries` and Engine `message_count` when present |
| `role_sequence_digest` | `Digest` | yes | digest of message roles in order | no message text | computed from canonical UTF-8 string `role0\nrole1\n...` over allowed roles |
| `input_projection_digest` | `Digest` | yes | digest of canonical manifest source summary, not full rendered messages | no full messages | recompute from `message_entries[*].content_digest`, source refs and projector metadata |
| `message_entries` | `list[RunnerCallMessageEntry]` | yes | per-message lightweight provenance and digest | no raw content | length must equal `message_count`; indexes contiguous |
| `source_cursor_refs` | `list[HostInternalRef]` | yes | EventLog cursor, memory cursor, compact boundary or equivalent source boundary used to assemble input | refs only | every ref must resolve or produce limited-signal diagnostic |
| `tool_schema_snapshot_refs` | `list[HostInternalRef]` | no | tool schema snapshots visible to the call | refs only | required when tools are available to the runner call |
| `memory_snapshot_cursor_ref` | `HostInternalRef | null` | no | memory read model cursor used by RunInputBuilder | cursor/ref only | if historical snapshot body is unavailable, manifest remains valid and trace emits limited-signal for body reconstruction |
| `compact_artifact_refs` | `list[HostInternalRef]` | no | accepted compact artifacts or fallback diagnostic artifacts used in input selection | refs only | refs must point to accepted compact or explicit fallback diagnostic |
| `context_fallback_decision_ref` | `HostInternalRef | null` | no | recent-window fallback decision when compaction failed but dispatch continued | ref only | present only when fallback affected this input |
| `projector_metadata` | `list[ProjectorMetadata]` | yes | stable producer metadata for each message/source projection | no Python module path in LLM-facing material | every `message_entries[*].projector_metadata_id` must resolve here |
| `compactor_identity` | `CompactorRunnerCallIdentity | null` | conditional | parent/self identity for Host-owned compactor calls | refs/ids only | required when `runner_call_kind == "compactor_proposal"` |
| `diagnostic` | `RunnerCallReconstructionDiagnostic | null` | no | typed incomplete/mismatch signal | internal consumer only | required when validation status is not `complete` |

Closed `RunnerCallKind` enum：`initial_user_dispatch`、`followup_user_dispatch`、`tool_result_continuation`、`post_compaction_dispatch`、`compactor_proposal`。

Closed `RunnerCallTriggerReason` enum：`initial_user_input`、`followup_user_input`、`tool_results_available`、`force_answer_after_tool_limit`、`finish_reason_length_continuation`、`host_retry`、`host_replay`、`host_resume`、`context_compaction_completed`、`context_compaction_repair_attempt`、`context_compaction_retry_attempt`。validation rule：forced answer、length continuation、retry/replay/resume 是 trigger reason，不再挤入 `runner_call_kind`；这样可覆盖 ordinary initial/follow-up、tool loop continuation、forced answer、length continuation、retry/replay/resume 与 context compaction without overlap。

### RunnerCallMessageEntry

| field | type | required | business / Host semantics | digest / ref boundary | validation rule |
|---|---|---:|---|---|---|
| `index` | `int` | yes | message order in actual runner call input | no content | contiguous from 0 |
| `role` | `"system" | "user" | "assistant" | "tool"` | yes | LLM role sent to runner | role only | must match Engine/provider role vocabulary accepted by AgentRunRequest |
| `content_digest` | `Digest` | yes | digest of rendered content for this message | digest only; no content inline | computed from canonical text/parts serializer chosen by projector metadata |
| `content_size_bytes` | `int` | yes | bounded observability for payload size | size only | non-negative; used to test manifest stays bounded |
| `source_refs` | `list[HostInternalRef]` | yes | canonical facts, payload descriptors, compact artifacts, memory cursors or tool result refs that explain the message | refs only | empty only for static system prompt with prompt asset digest in projector metadata |
| `projection_artifact_ref` | `HostInternalRef | null` | no | optional derived rendered-message artifact for analyzer/debug | artifact ref only | may be null; if present digest must match `projection_artifact_digest` |
| `projection_artifact_digest` | `Digest | null` | no | digest of optional derived rendered-message artifact | digest only | required when artifact ref is present |
| `projector_metadata_id` | `str` | yes | lookup id into manifest `projector_metadata` | not LLM-facing | must resolve to one projector metadata entry |
| `provider_tool_calls_digest` | `Digest | null` | no | digest for assistant tool_calls/provider structured parts when present | no provider dict bag | provider-specific raw shape is deferred unless Slice 0 design review scopes typed provider atoms into Slice 2 |
| `reasoning_content_digest` | `Digest | null` | no | digest for provider reasoning content if typed Engine contract already exposes it | no raw reasoning content | absent unless provider contract has typed field; otherwise follow-up owner is WU-ENG provider contract work |

Provider-specific assistant `tool_calls` / `reasoning_content` handling：Slice 0 design review must choose one of two outcomes. If current Engine provider contract already exposes typed fields, Slice 2 stores digests through `provider_tool_calls_digest` / `reasoning_content_digest`. If provider data is only raw provider state, this chain defers raw content storage to a later provider-contract WU; implementation must not add `dict` / `Any` bags to Host manifests.

### ProjectorMetadata

| field | type | required | business / Host semantics | digest / ref boundary | validation rule |
|---|---|---:|---|---|---|
| `projector_metadata_id` | `str` | yes | stable id referenced by message entries | internal label only | unique within manifest |
| `projector_id` | closed string enum | yes | semantic projector identity, such as `run_input_system_context`, `user_input_message`, `tool_result_message`, `compact_memory_material`, `compactor_user_prompt` | not Python module path | must be one of design-approved projector ids |
| `projector_schema_version` | `str` | yes | output contract version for the projector | contract metadata | must be supported by consumer or diagnostic reason `unsupported_projector_version` |
| `projector_digest` | `Digest` | yes | digest of prompt asset / config / projector contract that affects output shape | digest only | recompute from declared source refs where possible |
| `purpose` | closed string enum | yes | why the projector contributes to LLM input | business-readable internal enum | allowed values defined in design writeback |
| `source_contract_refs` | `list[HostInternalRef]` | yes | design/prompt/tool schema/config refs that define projector input contract | refs only | every ref must be resolvable or diagnostic |

### ToolCallArgumentsAtom

| field | type | required | business / Host semantics | digest / ref boundary | validation rule |
|---|---|---:|---|---|---|
| `tool_call_requested_event_ref` | `HostInternalRef` | yes | canonical `TOOL_CALL_REQUESTED` event that accepted the intent | canonical event ref | must resolve to same `tool_call_id` and `tool_name` |
| `tool_call_id` | `str` | yes | provider/Engine tool call identity | can appear in internal trace, not compact query text | equals canonical payload id |
| `tool_name` | `str` | yes | business-readable tool identity | allowed in compact evidence | equals canonical payload tool name |
| `normalized_arguments_digest` | `Digest` | yes | existing digest used for idempotency/tool intent validation | digest only | must equal digest of normalized canonical arguments |
| `arguments_json_size_bytes` | `int` | yes | canonical JSON byte size | size only | non-negative |
| `arguments_storage_kind` | `"inline_json" | "payload_descriptor"` | yes | storage form for accepted arguments | boundary decision | inline iff size `<= payload_inline_threshold_bytes`; descriptor otherwise |
| `arguments_inline_json` | `JsonObject | null` | conditional | bounded accepted arguments when small | canonical payload field | required for `inline_json`; forbidden for descriptor path |
| `arguments_payload_ref` | `HostInternalRef | null` | conditional | descriptor ref for accepted arguments JSON | payload descriptor kind `tool_call_arguments_json` | required for descriptor path; forbidden for inline path |
| `arguments_payload_digest` | `Digest` | yes | digest of canonical accepted arguments JSON | digest only | persisted arguments use the same canonical normalization preimage as `normalized_arguments_digest`; recomputing from durable args must equal both digests |
| `semantic_input_digest` | `Digest | null` | no | existing idempotency semantic digest | digest only | retained; not assumed to be readable query preimage |
| `semantic_query_storage_kind` | `"absent" | "inline_text" | "payload_descriptor"` | yes | optional business-readable query supplied by typed tool/runtime contract | boundary decision | absent is valid and diagnosable |
| `semantic_query_text` | `str | null` | conditional | bounded readable query text | allowed for compact query after Host semantic rewrite | required only for inline text |
| `semantic_query_payload_ref` | `HostInternalRef | null` | conditional | descriptor ref for long readable semantic query | payload descriptor kind `tool_call_semantic_query_text` | required only for descriptor path |
| `semantic_query_digest` | `Digest | null` | conditional | digest of semantic query text | digest only | required when semantic query exists |

### Tool Trace signal and diagnostic contract

Tool Trace is a read model. It may cache the following typed signal but cannot become recovery, memory, dispatch or Run status truth.

| field | type | required | business / Host semantics | digest / ref boundary | validation rule |
|---|---|---:|---|---|---|
| `runner_call_index` | `int` | yes | Host call index for locating the manifest | projection copy | must match manifest |
| `runner_call_kind` | `RunnerCallKind` | yes | non-overlapping call kind | projection copy | must match manifest |
| `runner_call_trigger_reason` | `RunnerCallTriggerReason` | yes | call trigger/reason | projection copy | must match manifest |
| `iteration_id` | `str | null` | no | Engine iteration id when available | observation copy | if present must match Engine event |
| `manifest_ref` | `HostInternalRef | null` | no | ref to runner-call manifest descriptor/artifact | ref only | null only with diagnostic reason `missing_runner_call_manifest` |
| `manifest_digest` | `Digest | null` | no | manifest digest | digest only | required when `manifest_ref` present |
| `message_count` | `int | null` | no | manifest/Engine message count summary | count only | mismatch emits diagnostic |
| `role_sequence_digest` | `Digest | null` | no | role sequence digest summary | digest only | mismatch emits diagnostic |
| `input_projection_digest` | `Digest | null` | no | manifest source summary digest | digest only | mismatch emits diagnostic |
| `projector_metadata_summary` | `list[ProjectorMetadataSummary]` | no | projector ids/schema versions/digests needed by analyzer | no raw code path | unsupported version emits diagnostic |
| `diagnostic` | `RunnerCallReconstructionDiagnostic | null` | no | typed limited/mismatch signal | internal consumers only | required unless status is `complete` |

`ProjectorMetadataSummary` fields：`projector_metadata_id: str`、`projector_id: str`、`projector_schema_version: str`、`projector_digest: Digest`、`purpose: str`。It is a read-model summary copied from manifest projector metadata; it must not include Python module paths or source code text.

`RunnerCallReconstructionDiagnostic` fields：

| field | type | required | semantics | validation rule |
|---|---|---:|---|---|
| `status` | `"complete" | "limited_signal" | "mismatch"` | yes | complete means all required refs/digests validated; limited means missing durable atom/ref prevents full reconstruction; mismatch means observed data conflicts with expected data | closed enum |
| `reason` | `DiagnosticReason` | conditional | machine-readable reason | required when status is not `complete` |
| `missing_atom_kind` | closed string enum \| `null` | no | missing atom such as `tool_call_arguments`, `semantic_query`, `runner_call_manifest`, `compactor_manifest`, `projection_artifact`, `memory_snapshot_body` | required for missing atom reasons |
| `missing_ref_kind` | closed string enum \| `null` | no | missing ref category such as `payload_ref`, `artifact_ref`, `event_ref`, `cursor_ref` | required for missing ref reasons |
| `missing_ref` | `HostInternalRef | null` | no | specific unresolved ref if one existed | internal only; never LLM-facing |
| `observed_count` | `int | null` | no | observed count for mismatch | required for count mismatch |
| `expected_count` | `int | null` | no | expected count for mismatch | required for count mismatch |
| `observed_digest` | `Digest | null` | no | observed digest for mismatch | required for digest mismatch |
| `expected_digest` | `Digest | null` | no | expected digest for mismatch | required for digest mismatch |
| `consumer_boundary` | `"tool_trace_query" | "analyzer_fixture" | "compact_evidence_projection" | "public_smoke"` | yes | who may consume the diagnostic | compact LLM-facing text may only receive business-neutral unavailable wording, never refs/digests |

Closed `DiagnosticReason` enum：`missing_runner_call_manifest`、`missing_projection_artifact`、`missing_tool_call_arguments_atom`、`missing_semantic_query_atom`、`missing_compactor_manifest`、`missing_memory_snapshot_body`、`unsupported_projector_version`、`message_count_mismatch`、`role_sequence_digest_mismatch`、`input_projection_digest_mismatch`、`payload_digest_mismatch`、`unresolvable_ref`、`provider_specific_atom_deferred`。

### CompactorRunnerCallIdentity

| field | type | required | semantics | validation rule |
|---|---|---:|---|---|
| `parent_host_run_id` | `str` | yes | Host admitted user Run that triggered or is governed by compaction | must equal manifest `host_run_id` |
| `parent_session_id` | `str` | yes | parent Session | must equal manifest `session_id` |
| `compaction_operation_id` | `str` | yes | Host context governance operation id shared across proposal/repair attempts | required for every compactor call |
| `compactor_engine_run_id` | `str` | yes | self Engine/runner id for the compactor proposal call, e.g. `context-compactor:*` | must not be treated as Host admitted user Run id |
| `compaction_attempt_number` | `int` | yes | proposal/repair attempt number within operation | positive and <= Host compaction policy max attempts |
| `compaction_request_digest` | `Digest` | yes | digest of immutable compaction request | must match compactor input projection |
| `compactor_input_projection_ref` | `HostInternalRef` | yes | artifact/descriptor for rendered compactor input data block | descriptor kind `compactor_input_projection` |
| `accepted_context_compacted_event_ref` | `HostInternalRef | null` | no | accepted `CONTEXT_COMPACTED` event for successful attempt | present only for accepted attempt |
| `rejected_attempt_diagnostic_ref` | `HostInternalRef | null` | no | diagnostic/progress ref for rejected/failed proposal attempt | present for rejected or failed attempts |

Relationship to compact events：`CONTEXT_COMPACTED` continues to own accepted compact artifact refs, accepted attempt number, candidate digest, label mapping refs, source boundary refs, quality check and budget after compact. The compactor runner-call manifest complements it by recording the LLM proposal call input identity. Accepted compact events reference the accepted proposal manifest; rejected attempts reference their manifest through typed diagnostics. Neither path turns rejected proposal content into memory or compact truth.

## Implementation Slices

### Slice 0: Design Contract Writeback

Objective：把 runner-call reconstruction stable contract 写回 `docs/host/design.md`，使后续代码实现有真源。

Allowed files：`docs/host/design.md`，必要时本 plan artifact 的 review/fix 更新。

Exact changes：

- 在 EventLog / canonical event matrix 中增加 `RUNNER_CALL_INPUT_ASSEMBLED` contract，明确 hot payload、descriptor kind、状态副作用为 none、消费者边界和不成为 Run state truth。
- 扩展 `TOOL_CALL_REQUESTED` payload contract，写明 `ToolCallArgumentsAtom`、`payload_inline_threshold_bytes` 判定、`tool_call_arguments_json` / `tool_call_semantic_query_text` descriptor kind、`semantic_input_digest` 与 optional semantic query 的关系。
- 在 RunInputBuilder 章节加入 `RunnerCallInputAssemblyManifest`、`RunnerCallMessageEntry`、role sequence digest canonicalization、source refs、projector metadata、manifest size-boundary 和 no-full-message invariant。
- 在 Context Governance / compact 章节加入 `CompactorRunnerCallIdentity`，明确 `parent_host_run_id`、`compaction_operation_id`、`compactor_engine_run_id`、accepted `CONTEXT_COMPACTED` refs 与 rejected attempt diagnostics 的关系。
- 在 Tool Trace 章节加入 signal contract 和 `RunnerCallReconstructionDiagnostic` typed shape，不让 trace 成为 truth。
- 在 design.md 中写明 provider-specific assistant `tool_calls` / `reasoning_content` 的当前 owner：若已有 typed Engine provider contract 则纳入 Slice 2 digest fields；若只有 raw provider state，则 deferred to later WU-ENG provider contract，当前 implementation 禁止 `dict` / `Any` bag。

Data flow：design.md -> implementation slices 只按该 contract 落地。

Invariants：

- 不把完整 provider request/messages 写成 canonical fact。
- 不改变 Run / Attempt 状态机。
- LLM-facing compact input 不暴露内部 refs/digests。

Tests：无代码测试；design review sub-gate 必须裁决 design contract 足够具体。

Stop condition：若 design.md 不能容纳该 contract 或出现架构争议，停止进入 implementation。

### Slice 0.5: Design Review Sub-gate

Objective：在任何代码 slice 派发前审查 Slice 0 的 `design.md` 写回是否达到可实施 contract 真源标准。

Artifact path：`docs/reviews/wu-dur-obs-cm-closeout-design-review.md`。

Review owner：phaseflow 总控派发的 design reviewer；优先使用未实施 Slice 0 的 reviewer，例如 AgentDS 或等价 plan/design reviewer。

Acceptance criteria：

- `design.md` 已包含本 plan appendix 等价或更严格的 `RunnerCallInputAssemblyManifest`、message entry、projector metadata、tool-call arguments atom、Tool Trace signal 与 diagnostic contract。
- inline-vs-ref、payload descriptor kind、manifest storage form、`payload_inline_threshold_bytes` 复用关系、Run state non-truth boundary 已明确。
- `RunnerCallKind` / trigger reason classification 覆盖 ordinary initial/follow-up、tool loop continuation、forced answer、length continuation、retry/replay/resume、context compaction，且无语义重叠。
- compactor parent/self identity 与 `CONTEXT_COMPACTED` / rejected diagnostics 的引用关系可实现。
- Engine vs Host ownership 写清：Engine 只产出 execution-local observations；Host 产出 runner_call_index、manifest refs/digests、source refs 和 EventLog / payload descriptor。
- 没有 LLM-facing 文本暴露裸 refs/digests/cursors/internal module path。

Stop condition：该 artifact 未给出 pass / accepted verdict 前，Slice 1-7 不得派发；若 review 判定需要超出 `design.md` 当前原则的新架构决策，本 work unit group 标记 blocked，并由总控提出 blocking question。

### Slice 1: Durable Tool-call Request Atoms

Objective：让 accepted tool call arguments 与可选 semantic query 成为可校验 durable atom。

Allowed files：`dayu/host/durable/schema.py`、`dayu/host/_event_payload.py`、`dayu/host/tool_runtime.py`、`dayu/host/engine_ingest.py`、`dayu/host/payload_resolution.py`、相关 host tests。

Exact changes：

- 为 `TOOL_CALL_REQUESTED` 写入 `ToolCallArgumentsAtom`：`arguments_inline_json` 或 `arguments_payload_ref` 二选一，判定阈值复用 design.md 第 13.1 节 `payload_inline_threshold_bytes`。
- 校验 durable arguments 与 `normalized_arguments_digest` 同源。
- 保留 `tool_name`、`tool_call_id`、`tool_schema_digest`、`tool_identity_digest`、`semantic_input_digest`。
- 若引入 semantic query，使用 `semantic_query_*` typed 字段或 descriptor kind `tool_call_semantic_query_text`，不使用 extra payload；`semantic_input_digest` 保留为 idempotency digest，不假定 semantic query 是它的 preimage。

Data flow：Engine `ToolCallRequestedData.arguments` -> ToolRuntime accept candidate -> payload descriptor / canonical payload -> EventLog row -> projection consumers。

Invariants：

- arguments 是 JSON-compatible mapping。
- 大 arguments 走 payload descriptor；小 arguments inline 仍必须经过 canonical JSON digest 校验。
- 不能从 tool behavior 或 prompt 猜测 arguments。
- fresh schema only：focused tests 和 smoke workspace 必须使用 fresh DB/workspace path，禁止旧库兼容读取。

Tests：

- existing `tests/host/test_toolruntime_accept_barrier.py`
- existing `tests/host/test_engine_ingest_mapping.py`
- existing `tests/host/test_tool_trace_projection.py`
- existing `tests/host/test_durable_schema.py`

Stop condition：accepted tool call arguments 不能从 durable store 读取并校验 digest 时停止。

### Slice 2: Runner-call Manifest Contract And Engine Signals

Objective：为每次 logical runner call 记录轻量、可校验的 input assembly manifest signal。

Allowed files：`dayu/engine/contracts/engine_events.py`、`dayu/engine/agent.py`、`dayu/engine/__init__.py`、`dayu/host/run_input.py`、`dayu/host/engine_ingest.py`、`dayu/host/durable/schema.py`、相关 tests。

Exact changes：

- Engine contract 只增加 Engine-owned observation fields：可选 actual role sequence digest / provider serializer schema version；不得加入 Host-owned `runner_call_index`、manifest ref 或 Host source refs。
- Host 初始 RunInputBuilder 生成 ordinary call manifest refs。
- Engine tool-loop continuation / fallback / continuation call 通过 Engine event 暴露 iteration/message_count/role digest；Host ingest 根据 accepted lifecycle context 生成 `RUNNER_CALL_INPUT_ASSEMBLED` 与 manifest refs/digests。
- Host ingest 将 manifest refs/digests 写入 durable canonical event，并让 Tool Trace 只复制 read-model signal。
- 增加 manifest bounded-size 断言：manifest 不包含完整 message text，且大 input 下 manifest body 只增长 refs/digests/entries summary，不随 message content 成比例膨胀。

Data flow：RunInputBuilder/Engine messages -> Engine-owned observations -> Host manifest/digests -> `RUNNER_CALL_INPUT_ASSEMBLED` -> EventLog/payload/artifact refs -> Tool Trace projection。

Invariants：

- Manifest 不内联完整 messages。
- `message_count` 与 role sequence digest 必须来自实际 runner call input。
- Engine 不理解 Host recovery truth；Host 不要求 Engine 管理 Session lifecycle。
- `runner_call_index`、manifest refs/digests、source refs、compact/memory/tool schema refs 只能由 Host 产生和持久化。

Tests：

- existing `tests/engine/test_engine_event_contract.py`
- existing `tests/engine/test_agent_phase3_tool_call.py`
- existing `tests/host/test_engine_ingest_mapping.py`
- existing `tests/host/test_run_input_builder.py`
- new focused test in `tests/host/test_run_input_builder.py` or `tests/host/test_engine_ingest_mapping.py` asserting manifest does not inline full messages and remains size-bounded.

Stop condition：真实 runner call message_count 与 manifest message_count 不能一致时停止。

### Slice 3: Compactor Internal Runner-call Manifest

Objective：覆盖 Host-owned compactor proposal call，使 analyzer 可轻量定位 compactor system/user messages 或报告 limited-signal。

Allowed files：`dayu/host/llm_compaction.py`、`dayu/host/compact_payload.py`、`dayu/host/compact_artifact.py`、`dayu/host/context_events.py`、`dayu/host/engine_ingest.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_public_compact_smoke.py`。

Exact changes：

- 在 compactor request/proposal call 前生成 `runner_call_kind=compactor_proposal` manifest artifact/ref。
- 记录 `CompactorRunnerCallIdentity`：`parent_host_run_id`、`parent_session_id`、`compaction_operation_id`、`compactor_engine_run_id`、`compaction_attempt_number`、`compaction_request_digest`、`compactor_input_projection_ref`。
- 记录 system prompt asset digest、user template digest、compaction request projection artifact/digest、proposal attempt number。
- accepted `CONTEXT_COMPACTED` 引用 accepted proposal manifest；rejected/failed attempt 通过 typed diagnostic/progress ref 引用相应 manifest。

Data flow：Context Governance compaction request -> LLMContextCompactor -> manifest artifact -> compactor AgentRunRequest -> accepted/rejected compact event -> trace/smoke。

Invariants：

- Compactor internal runner call 不是 Host admitted Run。
- Analyzer 不重跑 compact material selection。
- Compact output schema 不改变。

Tests：

- existing `tests/host/test_llm_compaction.py`
- existing `tests/host/test_compaction_operation.py`
- existing `tests/host/test_public_compact_smoke.py`

Stop condition：不能从 refs 校验 `compaction_request_digest` 与 message_count 时停止。

### Slice 4: Tool Trace Reconstruction Signal Projection

Objective：让 Tool Trace / analyzer 前置 fixture 消费 manifest refs/digests，并能输出 complete / limited_signal / mismatch。

Allowed files：`dayu/host/tool_trace.py`、`dayu/host/durable/tool_trace.py`、`tests/host/test_tool_trace_projection.py`、`tests/host/test_tool_trace_queries.py`。

Exact changes：

- 在 hot/cold trace projection 中加入 runner_call_index、iteration_id、manifest_ref、manifest_digest、message_count、role_sequence_digest、projector metadata summary。
- 对 missing tool-call arguments、missing compactor manifest、missing projection artifact、unsupported projector version、message_count mismatch、role_sequence_digest mismatch、payload digest mismatch 输出 `RunnerCallReconstructionDiagnostic`。
- 不实现完整 analyzer report，只提供 WU-OBS-00 可消费的 fixture/query contract。

Data flow：EventLog canonical facts + payload descriptors + manifest artifacts -> Tool Trace projection -> query helper / fixture。

Invariants：

- Tool Trace 是 read model。
- Trace 字段不能被 recovery / memory / Run 状态机消费。
- Hot trace 不内联长 prompt或完整 messages。

Tests：

- existing `tests/host/test_tool_trace_projection.py`
- existing `tests/host/test_tool_trace_queries.py`
- new focused diagnostic cases in existing trace tests for `limited_signal` and `mismatch` enum values.

Stop condition：trace query 无法定位 manifest 或无法表达 limited-signal reason 时停止。

### Slice 5: Compact Evidence Query Readability

Objective：用 DUR-P01 durable atoms 改善 compact evidence `query_text`。

Allowed files：`dayu/host/compaction_evidence.py`、`dayu/host/compact_material.py`、`dayu/host/compaction.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_public_compact_smoke.py`。

Exact changes：

- `_readable_query_text()` 通过 `tool_call_requested_event_ref` 读取 `TOOL_CALL_REQUESTED` durable arguments。
- 渲染 bounded business-readable query：优先 `semantic_query_text`，否则 `tool_name` + normalized arguments JSON。`tool_name` 已由 `EvidenceReadableItem.tool_name` 承担身份，query_text 的职责是补足 arguments / semantic query。
- 缺失 durable atom 时输出 structured limited-signal，而不是无声退化为裸 id。
- operational chunking behavior：同一个 `tool_call_requested_event_ref` 被切成 `E1.1` / `E1.2` 等 evidence chunks 时，各 chunk 使用同一个 base `query_text`；chunk 序号由 prompt-local label 表达，不在 query_text 内重复；query_text 不重复注入完整长 arguments，长 arguments 只按 compact material 现有 field budget 做 bounded rendering。
- 增加 chunking 同源测试，确保各 chunk query_text 同源、稳定、简洁。

Data flow：accepted evidence envelope -> tool_call_requested_event_ref -> EventLog/payload arguments -> readable query text -> compact material JSON。

Invariants：

- Query text 不包含 Host internal refs/digests。
- 不修改 compact candidate output schema。
- 不把 result content 混入 query text。

Tests：

- existing `tests/host/test_compaction_operation.py`
- existing `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`

Stop condition：query text 仍只能输出 `tool_call_id=...` 且无 limited-signal 诊断时停止。

### Slice 6: Compactor Prompt Semantic Rewrite

Objective：清理 compactor LLM-facing prompt 内部术语，降低无状态 LLM 认知负担。

Allowed files：`dayu/config/prompts/scenes/conversation_compaction.md`、`dayu/config/prompts/scenes/conversation_compaction_user.md`、`tests/host/test_public_compact_smoke.py`、必要 config prompt tests。

Exact changes：

- 删除或改写 `Host-owned context compaction`、`ConversationCompactOutputVNext`、`vNext 字段` 等内部实现/迁移术语。
- 同步清理 `conversation_compaction_user.md` 中旧 candidate 字段名 / migration wording，例如 `candidate_id`、`episode_summary_candidate` 等只面向实现迁移的旧名。
- 当前 prompt 自足说明输入 JSON、输出字段、字段含义、类型、必填性、允许值和最小示例。
- 保留 prompt-local label 规则，但解释为“本次请求内的引用标签”，不是业务事实。

Data flow：scene prompt asset -> Service-like assembly -> CompactorRunnerBaseline -> LLMContextCompactor AgentRunRequest。

Invariants：

- 不改变 compact output schema 字段名。
- 不暴露 EventLog/payload/digest/cursor/policy。
- 不把 Host 内部治理伪装成财报事实。

Tests：

- existing focused prompt text assertions in `tests/host/test_public_compact_smoke.py` or new config prompt tests。
- `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` optional real smoke remains env-gated。

Stop condition：prompt dump 仍出现内部实现身份、Python 类型名或 vNext 迁移术语时停止。

### Slice 7: Public Smoke Correctness Closeout

Objective：用 public smoke / focused tests 验证前三个 WU 的最终闭环。

Allowed files：`tests/host/public_smoke_support.py`、`tests/host/test_public_compact_smoke.py`、`tests/host/test_public_open_host_multiturn_smoke.py`、`tests/host/test_public_tool_wiring_smoke.py`、四个 `utils/smoke_host_public_*.py`。

Exact changes：

- 对触发 runner call 的 public smoke 增加 one-system-message 断言。
- 对 compact 后 follow-up 增加 manifest message_count / dump item count / role sequence digest 对齐断言。
- 对 compactor prompt 装配路径增加内部术语检查。
- 对无法触发 runner call / compact 的入口输出不适用原因。
- 四个 utility smoke scripts 必须逐一审计并列出验证结果：`utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_diagnostics.py`、`utils/smoke_host_public_conversation_memory_scenarios.py`、`utils/smoke_host_public_multiturn.py`。
- fresh schema only：每个 smoke 使用 fresh temporary workspace / DB path，或在执行前显式创建隔离 workspace；不得依赖旧 schema DB 兼容读取。

Data flow：public `open_host` / `submit_followup` / `watch_session_events` -> worker/runner recorded messages -> manifest/trace diagnostics -> assertions。

Invariants：

- Smoke 仍走 public Host path。
- 不读取或伪造 private durable atom 作为通过条件。
- Smoke 不替代 focused durable tests。

Tests：

- existing `tests/host/test_public_tool_wiring_smoke.py`
- existing `tests/host/test_public_open_host_multiturn_smoke.py`
- existing `tests/host/test_public_compact_smoke.py`
- optional scripts:
  - `python utils/smoke_host_public_conversation_memory.py --help`
  - `python utils/smoke_host_public_diagnostics.py --help`
  - `python utils/smoke_host_public_conversation_memory_scenarios.py --help`
  - `python utils/smoke_host_public_multiturn.py --help`

Stop condition：四个 smoke 入口任一仍无法解释 runner-call message_count mismatch，或需要依赖日志计数作为唯一证据。

## Tests / Validation Commands

每个 implementation slice 后运行受影响测试；最终 closeout 运行：

```bash
source .venv/bin/activate
pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
pytest tests/host/test_compaction_operation.py tests/host/test_run_input_builder.py
pytest tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py
pyright
```

Expected assertions：

- `TOOL_CALL_REQUESTED` durable payload/ref 可读取 arguments，并与 `normalized_arguments_digest` 校验一致。
- Engine execution observation / Host manifest 的 `message_count` 与实际 runner call messages 数量一致；Host-owned `runner_call_index` 和 manifest refs 不进入 `IterationStartedData`。
- tool-loop continuation、compact 后 follow-up、compactor internal call 都有 manifest 或 limited-signal。
- Tool Trace projection 能定位 manifest refs/digests，并表达 typed `limited_signal` / `mismatch` diagnostic。
- Compact `query_text` 包含 normalized arguments 或 semantic query；`tool_name` 仍由 `EvidenceReadableItem.tool_name` 承担；query text 不包含 internal refs。
- Compactor prompt 不包含 `Host-owned context compaction`、`ConversationCompactOutputVNext`、`vNext 字段`。
- Public smoke focused tests 能断言 one-system-message convergence 和 compact 后 message shape。

Optional env-gated validation：

```bash
source .venv/bin/activate
DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity
```

Final public smoke validation scope：

- focused pytest files：`tests/host/test_public_tool_wiring_smoke.py`、`tests/host/test_public_open_host_multiturn_smoke.py`、`tests/host/test_public_compact_smoke.py`。
- control-doc utility smoke scripts：`utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_diagnostics.py`、`utils/smoke_host_public_conversation_memory_scenarios.py`、`utils/smoke_host_public_multiturn.py` 的 help / assembly / optional provider smoke。

## Docs / README Decision

按 AGENTS.md 触发规则：

- 修改 `dayu/engine/`：更新 `dayu/engine/README.md`，说明 Engine event / runner call identity signal。
- 修改 `dayu/host/`：更新 `dayu/host/README.md`，说明 EventLog atoms、runner-call manifest、Tool Trace signal、compact evidence query boundary。
- 修改 `dayu/config/` prompt：更新 `dayu/config/README.md`，只说明 compactor prompt asset 的稳定职责和 LLM-facing 文本边界。
- 修改 `tests/`：更新 `tests/README.md`，说明新增 focused tests / public smoke 验收边界。
- 修改 `utils/` smoke 或 public workflow：若用户运行方式、输出诊断或 trace/render 入口变化，更新根目录 `README.md`；若只是内部断言增强且 CLI 使用不变，可不更新根 README，并在 implementation report 说明理由。
- 涉及 Host/Engine/Tool Trace 边界与装配方式：检查 `dayu/README.md` 是否职责范围内需要同步；只在术语或稳定边界变化时更新。

## Risks / Open Questions

无 blocking open question。

Residual risks：

- Runner-call manifest schema 需要在 Slice 0 design review 中严格压缩字段，避免变成隐形 messages dump。
- Compactor internal call 的失败 attempt manifest 与 accepted manifest 归档方式已在 plan 中指定为 accepted `CONTEXT_COMPACTED` ref 或 rejected diagnostic ref；Slice 0 design review 仍需检查 design.md 写回是否保持该边界。
- Provider-specific assistant tool_calls projection 可能涉及 `reasoning_content` / provider state；本 plan 已指定 Slice 0 design review 必须纳入 typed Engine contract digest fields 或显式 deferred to later WU-ENG provider contract，implementation 禁止 raw dict bag。
- Public smoke 脚本可能受真实 provider 稳定性影响；CI 只依赖 deterministic focused tests，真实 provider smoke 保持 env-gated。
- Prompt rewrite 保持 Slice 6 而不前移：它是 LLM-facing semantic cleanup，可独立实现，但 public smoke 的最终验收需要 durable manifest / trace / compact query signals 先落地；提前移动不会降低 contract 风险，反而会让 prompt tests 缺少最终 material shape 证据。

## Why This Is Not Over-design

该计划没有建设完整 analyzer、通用 tracing 平台或 provider request archive。它只补当前 correctness chain 必需的最小生产能力：

- DUR-P01 只补 durable atoms / refs / digests / projector metadata，不保存完整 messages。
- OBS-P00 只定义 analyzer 前置信号，不实现完整分析器。
- F02 只修 compact evidence query 可读性，不改 compact output schema。
- F01 只修 public smoke 的验收能力，不用 smoke 替代 durable truth。

拆分方式沿真实依赖边界推进：设计真源 -> durable atoms -> manifest signal -> trace projection -> compact readability -> prompt rewrite -> public smoke closeout。每个 slice 都有独立输入、输出、测试和 stop condition，可按 Gateflow 多 slice 重复 implementation -> code review -> fix -> re-review -> accepted slice commit 推进。

## Completion Report Format

implementation agent 每个 slice 完成后按以下格式报告：

```text
slice:
status: completed | blocked
changed files:
contract/design updates:
implementation summary:
tests run:
pyright:
README/docs sync:
remaining risks:
next slice readiness:
```

本 plan gate 完成报告：

- artifact path：`docs/host/wu-dur-obs-cm-closeout-plan.md`
- status：code-generation-ready after plan-fix
- core slices：Slice 0 design writeback；Slice 0.5 design review sub-gate；Slice 1 durable tool-call atoms；Slice 2 runner-call manifest；Slice 3 compactor internal call manifest；Slice 4 Tool Trace signals；Slice 5 compact query readability；Slice 6 prompt rewrite；Slice 7 public smoke closeout
- 需要总控裁决的问题：无 blocking；总控需在进入 implementation 前确认 Slice 0 design contract 先行，并在 design review 后再派发代码实现。
