# Phase 12.5 Implementation-Ready Plan: Conversation Memory Optimization

## 0. Gate 与角色

- 当前 gate：Phase 12.5 implementation-ready plan。
- 角色：planning agent only。
- 权威 assignment：`docs/reviews/phase12-5-plan-handoff-controller-20260522.md`。
- 设计真源：`docs/host/design.md`。
- 控制文档：`docs/host/implementation-control.md`。
- 讨论上下文：`docs/host/conversation-memory-first-principles-discussion.md`，只用于理解动机，不作为实现真源。
- 本计划只生成 handoff-ready / code-generation-ready implementation plan，不实施、不修改生产代码或测试、不提交、不推送、不开 PR。

## 1. 动机判断与目标

### 1.1 动机是否成立

动机成立，且不是表面改名问题。

直接证据：

- `docs/host/design.md` §24 明确要求 `evidence_backed_facts` 只来自 accepted tool evidence，至少包含 `claim_text`、`evidence_kind`、`evidence_refs`、producer / extraction operation ref、event ref 与可选 opaque attributes；缺 candidate 时只能记录 diagnostic / repair outcome，不得合成 neutral fallback fact。
- `docs/host/design.md` §25 明确要求 compactor 同一次 structured JSON proposal 输出 episode summary、pinned state patch、`evidence-backed fact candidates` 与 `minimum preserve item candidates`。
- 当前 `dayu/host/memory.py` 存在 `VerifiedFactView`、`ConversationMemorySnapshot.verified_facts`、`MemoryProjectionPolicy.max_verified_facts`，且 `_verified_fact_from_projection_event()` 会从 `TOOL_RESULT_ACCEPTED` 直接生成 verified fact；缺 `fact_summary` 时还会合成 neutral fallback fact diagnostic。
- 当前 `dayu/host/run_input.py` 的 `_memory_verified_fact_message()` 渲染 `fact.fact_summary` 与 `digest_ref`，不是 `claim_text + evidence_refs`。
- 当前 `dayu/host/compaction.py` 的 `CompactionCandidate` 只包含 episode summary、pinned patch 和 preservation evidence，没有 `evidence_backed_fact_candidates` / `minimum_preserve_item_candidates`。

根因是契约与数据流仍以旧 `verified_facts` / tool result summary 为中心，尚未切到“accepted evidence envelope -> compaction-gated fact candidate -> Host accept barrier -> memory projection -> RunInputBuilder claim rendering”的事实链路。

### 1.2 本 phase 目标

把 Conversation Memory 的稳定事实层迁移为 `evidence_backed_facts`：

- `TOOL_RESULT_ACCEPTED` 只形成可审计 accepted evidence envelope，不直接生成最终 memory fact。
- compaction 同一次 structured JSON proposal 生成 `evidence_backed_fact_candidates` 与 `minimum_preserve_item_candidates`。
- Host accept barrier 只校验 Host-neutral shape 和 refs，不理解财报业务 source / locator。
- `CONTEXT_COMPACTED` canonical payload 承载 accepted candidates、diagnostics 与 compact refs。
- memory projection 从 accepted compact output materialize `EvidenceBackedFactView` 与 minimum preserve continuity items。
- RunInputBuilder 渲染 facts 时必须包含 `claim_text` 与 `evidence_refs`。

## 2. Non-Goals / Scope Boundaries

本 phase 不做：

- 不修改 Engine Agent loop 或 Runner provider contract。
- 不修改真实 Fins 工具实现或 `dayu.fins.storage`。
- 不修改 Service / UI workflow public methods，不新增 Host command / handle public methods，不改 `open_host(options)` 字段名，不改 `SubmitFollowupRequest` public 字段。
- 不实现 long-term retrieval、cross-session research memory、vector index、public memory edit / reset / forget API。
- 不引入兼容 wrapper、兼容 re-export、旧 schema 兼容读取或旧 config key 兼容读取。
- 不做 eager per-tool-result extraction。
- 不让 tool provider 生成最终 memory facts。
- 不生成 neutral fallback fact。
- 不把 `recent_raw_turns_floor` 或 `minimum_preserve_items` 当事实真源。

## 3. 直接证据

- `docs/host/design.md` §18 ToolRuntime：工具事实必须走 Host-mediated accept barrier；ToolRuntime 只有 accepted ack 后才能把结果返回 Engine。
- `docs/host/design.md` §23 RunInputBuilder：RunInputBuilder 是 memory / EventLog / Service 场景输入进入 Engine 的唯一运行态入口；messages 顺序中 stable memory 优先。
- `docs/host/design.md` §24 Conversation Memory：定义 `evidence_backed_facts`、accepted evidence envelope、no fallback facts、recent raw turns 与 minimum preserve 的边界。
- `docs/host/design.md` §25 Context Governance：compactor 输出必须包含 episode summary candidate、pinned state patch candidate、evidence-backed fact candidates、minimum preserve item candidates；Context Governance 不直接写 memory。
- `docs/host/implementation-control.md` Phase 12.5：固定 P12.5 的目标、禁止范围、验证要求和退出条件。
- `docs/reviews/phase12-5-plan-handoff-controller-20260522.md`：固定本计划必须覆盖的契约、切片、测试、stop condition 与 completion report。

注：handoff 中写到 `docs/host/design.md` §20 RunInputBuilder，但当前设计真源中 RunInputBuilder 实际为 §23；计划按当前文档的 §23 执行，不改变 scope。

## 3.5 Handoff Coverage Checklist

- Required Plan Contents：见 §1-§6、§8-§11、§13-§14，覆盖目标 / non-goals、直接证据、contract/schema/state、affected files、data flow、JSON schema、accept barrier、slice、tests、docs、risks、completion report。
- Required Slice Coverage：见 §7，七个 slices 覆盖 contract migration、accepted evidence envelope、compaction candidate extension、accept barrier and diagnostics、LLM compactor structured JSON rewrite、memory projection、RunInputBuilder rendering、tests / smoke。
- Required Tests：见 §8，每条 handoff-required test 都映射到具体测试文件。
- Scope Boundaries：见 §2 与 §10。
- Stop Conditions：见 §10，并在每个 slice 内重复局部 stop condition。
- Completion Report：见 §13 和 §14。

## 3.6 Plan Review Fix Coverage

- A1：见 §5.3 与 §7 Slice 4，LLM compactor structured JSON rewrite 独立成 slice，plain-text success path 必须移除或拒绝，并有 bounded repair stop condition。
- A2：见 §4.2、§5.2 与 §7 Slice 6，`CompactionRequest.accepted_evidence_envelopes` / `accepted_evidence_refs` 来自 compact input range 内 `TOOL_RESULT_ACCEPTED.accepted_evidence_envelope` 的 bounded EventLog read。
- A3：见 §4.6 与 §7 Slice 5，`EvidenceBackedFactView` provenance 来自 accepted `CONTEXT_COMPACTED` event；candidate id 只做 local diagnostic / dedupe。
- A4：见 §4.8、§7 Slice 3 / Slice 4 与 §8，冻结第一版 bounded validation constants 并要求边界拒绝测试。
- A5：见 §4.1、§6.4、§7 Slice 7 与 §9，扩展 old-name cleanup list 和 stale-term search criteria。
- A6：见 §4.9、§7 Slice 5、§8 与 §11，old durable snapshot / item kind fail closed，不兼容读取、不静默跳过。
- A7：见 §4.10、§6.4 与 §7 Slice 7，要求对 `preserved_fact_refs` 相关消费者做 pre-implementation search 和逐项分类。

## 4. Contract / Schema / State Decisions

### 4.1 命名迁移

必须全量迁移旧命名，不保留兼容层：

- `VerifiedFactView` -> `EvidenceBackedFactView`。
- `ConversationMemorySnapshot.verified_facts` -> `ConversationMemorySnapshot.evidence_backed_facts`。
- `MemoryProjectionPolicy.max_verified_facts` -> `MemoryProjectionPolicy.max_evidence_backed_facts`。
- `MemoryProjectionConfig.max_verified_facts` -> `MemoryProjectionConfig.max_evidence_backed_facts`。
- `dayu/config/execution_profiles.json` 中所有 `max_verified_facts` -> `max_evidence_backed_facts`。
- `CompactionRequest.verified_fact_refs` -> `CompactionRequest.evidence_backed_fact_refs`。
- `CompactionCandidate.preserved_verified_fact_refs` -> `preserved_evidence_backed_fact_refs`。
- `EpisodeSummaryCandidate.proposed_verified_fact_refs` -> `proposed_evidence_backed_fact_refs`，且 accepted compact payload 中必须为空。
- RunInputBuilder block id `stable:verified_facts` -> `stable:evidence_backed_facts`。
- durable memory item kind `verified_fact` -> `evidence_backed_fact`。
- `MemoryClaimStatus.TOOL_VERIFIED` -> `EVIDENCE_BACKED`。
- `MemoryIncludedReason.TOOL_VERIFIED_FACT` -> `EVIDENCE_BACKED_FACT`。
- `CompactQualityIssue.SUMMARY_PRETENDS_VERIFIED_FACT` -> `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` 或等价新名。
- `_FIELD_PROPOSED_VERIFIED_FACT_REFS` -> `_FIELD_PROPOSED_EVIDENCE_BACKED_FACT_REFS`。
- old verified JSON codec helpers such as `_verified_fact_to_json_value()` / `_verified_fact_from_json_value()` -> evidence-backed equivalents。
- durable constants such as `_ITEM_KIND_VERIFIED_FACT` -> `_ITEM_KIND_EVIDENCE_BACKED_FACT`。

禁止新增旧名 alias、旧名 property、旧 key fallback、旧 JSON key 兼容读取。旧库按全新 schema 起库处理。

### 4.2 Accepted Evidence Envelope

新增 Host-neutral typed contract，建议放在新模块 `dayu/host/evidence.py`，因为它会被 `tool_runtime.py`、`compaction.py`、`context_events.py` 和 `memory.py` 共同使用；这是事实 contract，不是兼容 facade。

类型决策：

```text
AcceptedEvidenceEnvelope
  evidence_id: str
  producer_event_ref: str
  tool_name: str
  tool_call_id: str
  tool_query: AcceptedEvidenceToolQuery
  result_ref: AcceptedEvidenceResultRef
  source_refs: tuple[OpaqueEvidenceRef, ...]
  locator_refs: tuple[OpaqueEvidenceRef, ...]

AcceptedEvidenceToolQuery
  tool_call_requested_event_ref: str | None
  normalized_arguments_digest: str
  semantic_input_digest: str

AcceptedEvidenceResultRef
  payload_ref: str | None
  payload_digest: str | None
  outcome_digest: str | None
  truncation_applied: bool

OpaqueEvidenceRef
  ref_kind: str
  ref_id: str
  digest: str | None
```

Event payload key:

- `TOOL_RESULT_ACCEPTED.accepted_evidence_envelope`

`evidence_id` 必须稳定、不可空，第一版按 accepted tool result event 派生：

```text
evidence_id = "evidence:" + TOOL_RESULT_ACCEPTED.event_id
```

Host 只校验 envelope shape、非空文本、digest 格式和 ref 对应已 accepted event。Host 不解析 URL、章节、chunk、span、row、cell、metric、period、subject 等业务语义。

Compaction input source is frozen：

- Context Governance builds compact input by reading `TOOL_RESULT_ACCEPTED.accepted_evidence_envelope` from committed EventLog rows covered by the compaction request input range.
- `CompactionRequest` must add:

```text
accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]
accepted_evidence_refs: tuple[str, ...]
```

- `accepted_evidence_refs` is derived from `accepted_evidence_envelopes[*].evidence_id` during request construction, not supplied by LLM output.
- Existing stable fact refs are separate and must be named `evidence_backed_fact_refs: tuple[str, ...]`。
- `dispatch.py` proactive request construction and `engine_ingest.py` reactive request construction must replace current hardcoded empty refs with bounded EventLog reads over the compact input range. They may pass explicit empty tuples only when that bounded range contains no `TOOL_RESULT_ACCEPTED` with accepted evidence.
- The bounded read must not scan unrelated sessions or unbounded history; it only reads rows in the same session and compact input cursor/range.

### 4.3 Evidence-Backed Fact Candidate

新增 typed contract，建议位于 `dayu/host/compaction.py`：

```text
EvidenceBackedFactKind
  observed_value
  quoted_statement
  table_value
  derived_from_evidence

EvidenceBackedFactCandidate
  candidate_id: str
  claim_text: str
  evidence_kind: EvidenceBackedFactKind
  evidence_refs: tuple[str, ...]
  attributes: Mapping[str, JsonValue]
```

JSON key：

- `evidence_backed_fact_candidates`

最小 contract 是 `claim_text + evidence_refs`，但 `candidate_id` 和 `evidence_kind` 必须保留以支持 diagnostic、review 和预算治理。`attributes` 是 opaque JSON object，Host 不解释业务含义。

`candidate_id` 只用于 candidate-local diagnostics / dedupe，不是 authoritative provenance，也不得替代 EventLog provenance。

### 4.4 Minimum Preserve Candidate

新增 typed contract，建议位于 `dayu/host/compaction.py`：

```text
MinimumPreserveReason
  needed_for_recent_reference
  needed_for_ordered_item_reference
  needed_for_local_followup

MinimumPreserveItemCandidate
  item_id: str
  label: str
  text: str
  source_refs: tuple[str, ...]
  preserve_reason: MinimumPreserveReason
```

JSON key：

- `minimum_preserve_item_candidates`

它只能 materialize 为 continuity item，不能生成 `EvidenceBackedFactView`。

### 4.5 Context Compacted Payload

`CONTEXT_COMPACTED` payload 必须新增并验证：

```text
evidence_backed_fact_candidates: list[EvidenceBackedFactCandidate JSON]
minimum_preserve_item_candidates: list[MinimumPreserveItemCandidate JSON]
preserved_fact_refs:
  accepted_evidence_refs: list[str]
  evidence_backed_fact_refs: list[str]
quality_check_result:
  accepted_evidence_refs_retained: bool
  evidence_backed_fact_candidates_accepted: bool
  minimum_preserve_items_accepted: bool
  retained_accepted_evidence_refs: list[str]
```

旧 `preserved_fact_refs.tool_fact_refs`、`preserved_fact_refs.verified_fact_refs` 不保留兼容读取。实现若发现当前 event helper 仍需要 `tool_fact_refs` 作为内部 compaction preservation ref，可保留为 `accepted_tool_result_event_refs` 这样的新语义字段，但不得继续把它命名为 verified facts。

### 4.6 Memory Snapshot

`EvidenceBackedFactView` 字段：

```text
item_id: str
claim_text: str
evidence_kind: EvidenceBackedFactKind
evidence_refs: tuple[str, ...]
attributes: Mapping[str, JsonValue]
provenance: MemoryProvenanceRef
extraction_operation_ref: str
compact_artifact_ref: str | None
candidate_id: str
included_reason: MemoryIncludedReason | None
excluded_reason: MemoryExcludedReason | None
size_units: MemorySizeUnits
```

Provenance source is frozen：

- `EvidenceBackedFactView.provenance.event_id` and `event_sequence` must come from the accepted `CONTEXT_COMPACTED` event that materialized the fact.
- `extraction_operation_ref` and `compact_artifact_ref` must come from trusted compacted payload / artifact metadata, not from LLM candidate text as authoritative provenance.
- `candidate_id` is item-local diagnostic / dedupe metadata only.
- Evidence origin remains in `evidence_refs`, which point to accepted evidence envelopes from earlier `TOOL_RESULT_ACCEPTED` events.

`MemoryClaimStatus.TOOL_VERIFIED` 改为 `EVIDENCE_BACKED`；`MemoryIncludedReason.TOOL_VERIFIED_FACT` 改为 `EVIDENCE_BACKED_FACT`。

`ConversationContinuityKind` 新增：

```text
MINIMUM_PRESERVE_ITEM = "minimum_preserve_item"
```

`ConversationContinuityItem` 可复用，但要能承载 minimum preserve 的 `label` 和 `source_refs`。若现有字段不足，允许新增 Host-neutral typed continuity item 字段：

```text
label: str | None
source_refs: tuple[str, ...]
preserve_reason: MinimumPreserveReason | None
```

不得用 untyped extra payload 承载这些显式参数。

### 4.7 Diagnostics

`MemoryDiagnosticReason` / compact rejection category 需要新增：

- `FACT_CANDIDATE_MISSING_FOR_ACCEPTED_EVIDENCE`
- `FACT_CANDIDATE_INVALID_EVIDENCE_REF`
- `FACT_CANDIDATE_EMPTY_CLAIM_TEXT`
- `FACT_CANDIDATE_FORBIDDEN_SOURCE`
- `MINIMUM_PRESERVE_ITEM_INVALID`
- `ACCEPTED_EVIDENCE_RETAINED_WITHOUT_FACT`

当 accepted evidence 存在但无可接受 fact candidate 时：

- 记录 diagnostic / repair outcome。
- 保留 accepted evidence envelope refs。
- 不生成 neutral fallback fact。
- episode summary 和 minimum preserve 仍可作为 continuity / navigation materialize。

### 4.8 Bounded Validation Constants

第一版 validation constants 必须定义在 Host compaction / memory contract code 中，建议放在 `dayu/host/compaction.py`；若 accepted evidence envelope codec 也需要共享，则允许放入 `dayu/host/evidence.py`。这些常量不得放入 runtime config，也不得由 Service / UI 配置覆盖。

冻结常量：

```text
MAX_EVIDENCE_BACKED_FACT_CANDIDATES = 64
MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES = 32
MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS = 2000
MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS = 1200
MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS = 120
MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS = 4096
MAX_EVIDENCE_REFS_PER_FACT = 16
MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM = 16
```

Validation requirements：

- `claim_text` must be non-empty after strip and length `<= MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS`。
- minimum preserve `text` must be non-empty after strip and length `<= MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS`。
- candidate counts must not exceed the constants above。
- `attributes` canonical JSON length must not exceed `MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS`。
- tests must reject empty and overlong `claim_text`, and overlong minimum preserve text at minimum。

### 4.9 Old Durable Snapshot Fail-Closed

Project policy is new schema start. Current readers must fail closed on old durable memory snapshot JSON or old item kinds:

- `conversation_memory_snapshot_from_json_value()` must reject old `verified_facts` key and require `evidence_backed_facts`。
- durable item row readers / validators must reject old item kind `verified_fact` with a clear validation error。
- implementation must not silently skip old verified items。
- implementation must not add compatibility reads, aliases or migration fallback。
- tests must cover old snapshot key rejection and old durable item kind rejection where current codec exposes those paths。

### 4.10 `preserved_fact_refs` Consumer Audit

Before implementation edits, the implementation agent must run:

```bash
rg -n "preserved_fact_refs|tool_fact_refs|verified_fact_refs|preserved_verified|proposed_verified" dayu tests
```

Every hit must be classified before coding:

- included in an explicit slice and renamed / semantically updated; or
- documented in the implementation report as not consuming the changed semantics, with direct reason.

Any hit outside the affected-file list in §6.1 / §6.2 that consumes compact request, compact candidate, compact event payload, memory snapshot JSON, durable item rows, RunInputBuilder rendering, or tests must be added to an explicit slice before implementation continues.

## 5. State / Data Flow

### 5.1 Accepted Tool Result

```text
Engine tool call
  -> ToolRuntime executes / truncates / governs
  -> Host accept barrier appends TOOL_RESULT_ACCEPTED
  -> TOOL_RESULT_ACCEPTED payload includes accepted_evidence_envelope
  -> ToolRuntime receives accepted ack and only then returns result to Engine
```

`TOOL_RESULT_ACCEPTED` 不再直接进入 stable fact projection。它只提供 accepted evidence envelope、payload refs、digest、query refs 和 diagnostics。

### 5.2 Compaction Request

```text
Context Governance builds CompactionRequest
  -> includes input_event_refs
  -> bounded EventLog read over the compact input range
  -> includes accepted_evidence_envelopes from TOOL_RESULT_ACCEPTED.accepted_evidence_envelope
  -> derives accepted_evidence_refs from accepted_evidence_envelopes
  -> includes existing evidence_backed_fact_refs separately
  -> includes recent_raw_turn_refs for continuity only
```

`recent_raw_turns_floor` 只影响 raw turn continuity inclusion，不参与 stable fact validation。

### 5.3 Structured JSON Proposal

```text
LLMContextCompactor
  -> same structured JSON proposal
      episode_summary_candidate
      pinned_state_patch_candidate
      evidence_backed_fact_candidates
      minimum_preserve_item_candidates
      preservation / quality / diagnostic data
```

正常路径不得额外增加第二次 LLM call；repair 只在 JSON parse / schema / quality / ref validation 失败时进入 bounded semantic repair。Plain-text summary success path must be removed or rejected; it cannot be silently accepted as a compact success.

### 5.4 Accept Barrier

```text
Context Governance check_compaction_candidate
  -> validates candidate shape
  -> validates evidence_refs point to accepted evidence envelopes
  -> rejects assistant/user/summary/working-assumption refs as fact evidence
  -> validates minimum preserve item source refs point to compact input
  -> records diagnostics for missing/invalid candidates
  -> appends CONTEXT_COMPACTED only for accepted candidate
```

Host 不证明 claim 与证据逐字一致，不解析业务 locator。

### 5.5 Memory Projection

```text
ConversationMemoryProjectionConsumer consumes committed EventLog:
  USER_INPUT_ACCEPTED -> pinned state / raw user continuity
  RUN_SUCCEEDED -> assistant conclusion continuity
  TOOL_RESULT_ACCEPTED -> accepted evidence availability only; no fact
  CONTEXT_COMPACTED -> EvidenceBackedFactView + minimum preserve continuity + episode summary + pinned patch
```

Projection 是 read model，不直接写 EventLog；Context Governance 不直接写 memory tables。

### 5.6 RunInputBuilder

RunInputBuilder stable layer order：

1. pinned goal / constraints。
2. confirmed subjects。
3. `evidence_backed_facts` rendered as `claim_text` + `evidence_refs` + extraction event refs。
4. open questions / working assumptions。
5. recent raw turns。
6. minimum preserve continuity items。
7. episode summaries。

Fact block 禁止 digest-only rendering。

## 6. Affected Files / Modules

### 6.1 Production files allowed

- `dayu/host/evidence.py`：新增 accepted evidence envelope typed contract 与 JSON codec。
- `dayu/host/memory.py`：memory typed contract、projection、JSON codec、policy digest、diagnostics、no-fallback behavior。
- `dayu/host/durable/memory.py`：durable item kind、snapshot JSON read/write、projection consumer event filter / item rows。
- `dayu/host/tool_runtime.py`：`TOOL_RESULT_ACCEPTED` payload 增加 `accepted_evidence_envelope`；ack 可继续保持 public shape 不变。
- `dayu/host/compaction.py`：CompactionRequest / Candidate schema 扩展与旧 verified 命名迁移。
- `dayu/host/context_events.py`：`CONTEXT_COMPACTED` payload builder / validator 扩展与旧 key 移除。
- `dayu/host/context_governance.py`：candidate accept barrier、diagnostic issue、no-fallback-facts validation。
- `dayu/host/llm_compaction.py`：改为要求并解析 structured JSON proposal；禁用 plain summary-only success。
- `dayu/host/compact_artifact.py`：如 artifact schema 展示 compact candidate，则同步新 fields。
- `dayu/host/compaction_operation.py`：repair/rejection category 与 diagnostic refs。
- `dayu/host/dispatch.py`：proactive compaction request 构造新 accepted evidence input。
- `dayu/host/engine_ingest.py`：reactive compaction request 构造新 accepted evidence input。
- `dayu/host/run_input.py`：memory stable block rendering 改为 evidence-backed facts 与 minimum preserve continuity。
- `dayu/runtime/config_loader.py`：`max_evidence_backed_facts` config schema，拒绝旧 key。
- `dayu/service/host_assembly.py`：runtime config -> Host `MemoryProjectionPolicy` 映射新 key。
- `dayu/config/execution_profiles.json`：默认 profiles 使用 `max_evidence_backed_facts`。

### 6.2 Test files allowed

- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/fake_compaction.py`
- `tests/service/test_host_assembly.py`
- `tests/runtime/test_config_loader.py`
- existing public lifecycle / multiturn smoke tests only if they fail due to renamed policy or memory rendering.

### 6.3 Docs allowed

- `dayu/host/README.md`
- `dayu/config/README.md`
- `tests/README.md`
- `README.md` only if root user-facing config examples mention old `max_verified_facts` or old memory fact terminology.
- `dayu/README.md` only if project terminology still exposes `verified_facts`.

### 6.4 Pre-Implementation Search Requirements

Before any code edits, implementation must run both searches and record the classification in the slice report:

```bash
rg -n "preserved_fact_refs|tool_fact_refs|verified_fact_refs|preserved_verified|proposed_verified" dayu tests
rg -n "verified_facts|max_verified_facts|VerifiedFact|verified fact|verified_fact|TOOL_VERIFIED|PRETENDS_VERIFIED|proposed_verified|preserved_verified|stable:verified|max_verified" dayu tests docs README.md
```

Search results are not optional cleanup hints. Every semantic consumer of the renamed contract must be included in an explicit slice or documented as unrelated to the changed semantics.

## 7. Implementation Slices

### Slice 1: Contract Rename And Config Schema

Objective：

- Remove old verified naming from typed memory/config contracts.
- Establish `EvidenceBackedFactView`, `evidence_backed_facts`, `max_evidence_backed_facts`.

Allowed files：

- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/runtime/config_loader.py`
- `dayu/service/host_assembly.py`
- `dayu/config/execution_profiles.json`
- `tests/runtime/test_config_loader.py`
- `tests/service/test_host_assembly.py`
- focused compile/type fallout in `tests/host/*` only where imports/constructors require rename.

Exact changes：

- Rename dataclasses, fields, constants and JSON keys from verified to evidence-backed.
- Update memory policy digest JSON to use `max_evidence_backed_facts`.
- Update config parser exact field set to require `max_evidence_backed_facts`.
- Add tests that old `max_verified_facts` is rejected.
- Do not add old-name aliases, wrappers or fallback keys.

Tests：

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py`
- `source .venv/bin/activate && pyright dayu/host/memory.py dayu/host/durable/memory.py dayu/runtime/config_loader.py dayu/service/host_assembly.py`

Stop condition：

- If old config / snapshot compatibility is required to pass existing tests, stop and report to controller; do not add compatibility.

### Slice 2: Accepted Evidence Envelope In Tool Accept Path

Objective：

- Make every new `TOOL_RESULT_ACCEPTED` carry a stable accepted evidence envelope.
- Ensure tool providers do not create final memory facts.

Allowed files：

- `dayu/host/evidence.py`
- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_memory_projection.py` for projection assertion that tool result alone creates no fact.

Exact changes：

- Add typed envelope JSON codec with strict validation.
- In `_append_tool_result_if_needed()`, add `accepted_evidence_envelope`.
- Envelope `evidence_id` derives from the accepted result event id.
- Envelope includes tool call/query refs from existing candidate fields, result refs from payload/digest/truncation, and opaque source/locator refs if present in accepted payload; absence is represented as empty tuples, not fallback business parsing.
- Reuse `TOOL_RESULT_ACCEPTED` for accepted waiting terminal results if applicable, but only accepted terminal tool results get evidence envelopes; `ToolFactKind.REUSE` must not fabricate a new evidence envelope.

Tests：

- accepted completed result payload includes `accepted_evidence_envelope.evidence_id == "evidence:<tool_result_event_id>"`.
- envelope refs include tool query/digest/result refs and Host does not parse source / locator shape.
- `TOOL_RESULT_ACCEPTED` alone no longer materializes `EvidenceBackedFactView`.

Validation：

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_memory_projection.py`
- `source .venv/bin/activate && pyright dayu/host/evidence.py dayu/host/tool_runtime.py`

Stop condition：

- If accepted evidence envelope cannot be added without changing public Host command APIs, stop and write `Blocking Questions For Controller`.

### Slice 3: Compaction Structured Candidate Contract And Accept Barrier

Objective：

- Extend compact proposal contract to carry evidence-backed fact candidates and minimum preserve item candidates.
- Reject invalid fact candidates without neutral fallback fact.

Allowed files：

- `dayu/host/compaction.py`
- `dayu/host/context_events.py`
- `dayu/host/context_governance.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/compact_artifact.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/fake_compaction.py`

Exact changes：

- Add `EvidenceBackedFactCandidate`, `EvidenceBackedFactKind`, `MinimumPreserveItemCandidate`, `MinimumPreserveReason`.
- Extend `CompactionRequest` with accepted evidence envelope inputs; rename existing verified fact refs.
- Extend `CompactionCandidate` with `evidence_backed_fact_candidates` and `minimum_preserve_item_candidates`.
- Extend JSON parser / builder / validator for `CONTEXT_COMPACTED`.
- `check_compaction_candidate()` validates:
  - `claim_text` non-empty and bounded.
  - `evidence_refs` non-empty and subset of accepted evidence ids.
  - evidence refs do not point to user input, assistant final answer, episode summary or working assumption.
  - `minimum_preserve_item_candidates` have non-empty `text`, bounded count, valid `source_refs` within compact input and valid reason enum.
  - accepted evidence with no valid fact candidate records diagnostic and does not create fallback fact.
- Use constants from §4.8 for claim text, minimum preserve text, candidate counts, evidence refs per fact and attributes JSON size.

Tests：

- valid candidate referencing accepted evidence passes.
- candidate referencing assistant/user/summary refs is rejected.
- empty `claim_text`, missing evidence refs, unknown evidence refs are rejected.
- overlong `claim_text` and overlong minimum preserve `text` are rejected.
- accepted evidence with missing fact candidates yields diagnostic / repair outcome, not neutral fallback fact.
- minimum preserve item candidate validates source refs and cannot appear in fact candidates.

Validation：

- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py`
- `source .venv/bin/activate && pyright dayu/host/compaction.py dayu/host/context_events.py dayu/host/context_governance.py dayu/host/compaction_operation.py`

Stop condition：

- If implementation requires a second normal-path LLM extraction call or eager extraction after each tool result, stop and report scope violation.

### Slice 4: LLM Compactor Structured JSON Rewrite

Objective：

- Rewrite `LLMContextCompactor` from plain-text summary acceptance to strict structured JSON proposal parsing.
- Keep extraction compaction-gated and in the same normal-path LLM call as episode summary and pinned patch.

Allowed files：

- `dayu/host/llm_compaction.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/fake_compaction.py` only if helper schema must match the new structured contract.

Exact changes：

- Update compactor system/user prompt to request strict JSON only with these top-level keys:
  - `episode_summary_candidate`
  - `pinned_state_patch_candidate`
  - `evidence_backed_fact_candidates`
  - `minimum_preserve_item_candidates`
  - preservation / quality / diagnostic data required by `CompactionCandidate`
- Parse the final answer as JSON, map it through typed constructors in `dayu/host/compaction.py`, and let schema / value errors become proposal failure or bounded repair input.
- Remove or reject the existing plain-text summary success path. A final answer containing only plain text must not produce accepted `CompactionCandidate`.
- Do not add a second normal-path LLM call for fact extraction.
- Do not trust candidate-provided provenance for materialized facts; provenance remains governed by `CONTEXT_COMPACTED` event metadata as frozen in §4.6.

Tests：

- valid structured JSON final answer maps to `CompactionCandidate` including fact and minimum preserve candidates.
- plain text final answer is rejected and not accepted as compact success.
- malformed JSON and schema-invalid JSON are rejected.
- structured JSON with overlong `claim_text` or minimum preserve `text` is rejected via the shared constants.
- structured JSON cannot create fact candidates from non-evidence refs.

Validation：

- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py`
- `source .venv/bin/activate && pyright dayu/host/llm_compaction.py`

Stop condition：

- If structured JSON parsing / schema validation cannot work within bounded repair attempts, stop and report `Blocking Questions For Controller`。

### Slice 5: Memory Projection Materialization

Objective：

- Materialize facts only from accepted compact output.
- Materialize minimum preserve only as continuity.
- Preserve recent raw turn semantics as continuity only.

Allowed files：

- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `tests/host/test_memory_projection.py`

Exact changes：

- Remove direct `TOOL_RESULT_ACCEPTED -> EvidenceBackedFactView` projection.
- On `TOOL_RESULT_ACCEPTED`, update only diagnostics / evidence availability behavior needed for later compaction; do not add stable fact.
- On `CONTEXT_COMPACTED`, validate payload and materialize:
  - `EvidenceBackedFactView` from accepted `evidence_backed_fact_candidates`.
  - `ConversationContinuityItem(item_kind=MINIMUM_PRESERVE_ITEM)` from `minimum_preserve_item_candidates`.
  - episode summary as continuity navigation.
  - pinned state patch as before, with renamed fact refs.
- Enforce `max_evidence_backed_facts` budget and diagnostics.
- Snapshot JSON key is `evidence_backed_facts`; old `verified_facts` JSON is invalid.

Tests：

- assistant final answer, user input, episode summary and working assumption cannot become evidence-backed facts.
- `TOOL_RESULT_ACCEPTED` alone creates accepted evidence availability but zero facts.
- valid `CONTEXT_COMPACTED.evidence_backed_fact_candidates` creates facts with `claim_text` and `evidence_refs`.
- created facts use the accepted `CONTEXT_COMPACTED` event id / sequence as provenance; candidate id is not authoritative provenance.
- invalid / missing candidates produce diagnostics only.
- `minimum_preserve_item_candidates` create continuity items and never facts.
- recent raw turns still support no-compaction follow-up but are not stable post-compaction fact truth.
- durable snapshot read/write roundtrip uses new keys and item kind.
- old snapshot key `verified_facts` and old durable item kind `verified_fact` fail closed with clear validation errors.

Validation：

- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py`
- `source .venv/bin/activate && pyright dayu/host/memory.py dayu/host/durable/memory.py`

Stop condition：

- If projection needs to parse financial source / locator semantics to decide fact validity, stop; Host must remain business-neutral.

### Slice 6: RunInputBuilder Rendering And Compaction Request Wiring

Objective：

- Render evidence-backed facts with `claim_text + evidence_refs`.
- Inject minimum preserve continuity items.
- Build compaction requests with accepted evidence envelopes on proactive and reactive paths.

Allowed files：

- `dayu/host/run_input.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_compaction_operation.py` only if request construction helpers need update.

Exact changes：

- Rename stable block id to `stable:evidence_backed_facts`.
- `_memory_evidence_backed_fact_message()` renders:
  - `claim_text=...`
  - `evidence_refs=[...]`
  - `evidence_kind=...`
  - extraction event id / sequence.
- Do not render digest-only facts.
- Render minimum preserve continuity items after recent raw turns and before episode summaries, with label/text/source refs/reason.
- Update proactive `CompactionRequest` construction in `dispatch.py` and reactive construction in `engine_ingest.py` to include accepted evidence envelopes / refs and renamed existing fact refs.
- Replace hardcoded empty `tool_fact_refs` / `verified_fact_refs` construction with bounded EventLog reads over the compact input range; explicit empty tuples are allowed only when the compact input range has no accepted tool evidence.
- Keep `accepted_evidence_refs` separate from `evidence_backed_fact_refs`.

Tests：

- RunInputBuilder memory block contains `claim_text` and `evidence_refs`.
- No digest-only rendering regression.
- minimum preserve continuity item is injected as continuity, not stable fact.
- no-compaction short-link follow-up can use recent raw turns.
- post-compaction follow-up can use evidence-backed facts even when old raw turns are compacted away.

Validation：

- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py`
- `source .venv/bin/activate && pyright dayu/host/run_input.py dayu/host/dispatch.py dayu/host/engine_ingest.py`

Stop condition：

- If wiring requires modifying Engine, Runner provider, Host public command API, `open_host(options)`, or `SubmitFollowupRequest`, stop.

### Slice 7: Integration Smoke, README Sync, Aggregate Validation

Objective：

- Prove the full P12.5 semantic path and synchronize docs that are now stale.

Allowed files：

- tests listed in §6.2.
- `dayu/host/README.md`
- `dayu/config/README.md`
- `tests/README.md`
- `README.md` and `dayu/README.md` only if searches find stale public terms.

Exact changes：

- Add or update integration/smoke tests for:
  - accepted evidence envelope can be referenced by fact candidates.
  - no-compaction short-link raw-turn reuse.
  - post-compaction revenue / gross-profit facts reused to answer gross-margin follow-up without relying on compacted-away raw turns.
  - long input minimum preserve item resolves “第二个因素” without preserving whole raw input.
  - compaction confirmed facts do not drift; episode summary references facts/evidence but does not create facts.
- README sync:
  - `dayu/host/README.md` must describe `evidence_backed_facts`, accepted evidence envelope, compaction-gated extraction, no fallback facts, minimum preserve as continuity.
  - `dayu/config/README.md` must show `max_evidence_backed_facts`.
  - `tests/README.md` must mention the P12.5 memory projection / compaction / run input test responsibilities if not already covered.
  - `README.md` only if user-facing config snippets contain old key.
  - `dayu/README.md` only if terminology still names `verified_facts`.

Validation commands：

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/service/test_host_assembly.py tests/runtime/test_config_loader.py`
- `source .venv/bin/activate && pyright`
- `rg -n "verified_facts|max_verified_facts|VerifiedFact|verified fact|verified_fact|TOOL_VERIFIED|PRETENDS_VERIFIED|proposed_verified|preserved_verified|stable:verified|max_verified" dayu tests docs README.md`
- `rg -n "preserved_fact_refs|tool_fact_refs|verified_fact_refs|preserved_verified|proposed_verified" dayu tests`

Stop condition：

- If focused tests require changing Engine, Fins storage, real tool providers or Service/UI workflow public methods, stop and report the exact failing test and required boundary change.

## 8. Required Tests Matrix

| Requirement | Primary tests |
| --- | --- |
| Accepted evidence envelope can be referenced by candidates; Host does not parse source / locator | `tests/host/test_toolruntime_accept_barrier.py`, `tests/host/test_compaction_contract.py` |
| Assistant final answer, user input, episode summary, working assumption cannot become facts | `tests/host/test_memory_projection.py`, `tests/host/test_compaction_contract.py` |
| Missing / invalid fact candidates produce diagnostic / repair outcome, not fallback fact | `tests/host/test_compaction_operation.py`, `tests/host/test_memory_projection.py` |
| Bounded validation rejects empty / overlong claim text and overlong minimum preserve text | `tests/host/test_compaction_contract.py`, `tests/host/test_llm_compaction.py` |
| Plain-text LLM compactor final answer is rejected, not silently accepted | `tests/host/test_llm_compaction.py` |
| Minimum preserve materializes only continuity | `tests/host/test_memory_projection.py`, `tests/host/test_run_input_builder.py` |
| RunInputBuilder renders `claim_text` and `evidence_refs` | `tests/host/test_run_input_builder.py` |
| Recent raw turns support no-compaction follow-up but are not stable post-compaction facts | `tests/host/test_run_input_builder.py`, memory integration test in `tests/host/test_memory_projection.py` |
| Post-compaction revenue / gross-profit facts reused for gross-margin follow-up | integration/smoke test in `tests/host/test_run_input_builder.py` or existing public lifecycle smoke if already wired |
| Config loader / service assembly accepts new key and rejects old key | `tests/runtime/test_config_loader.py`, `tests/service/test_host_assembly.py` |
| Old durable snapshot key / old item kind fail closed | `tests/host/test_memory_projection.py` |

## 9. README Sync Decision

README updates are required after implementation because this phase changes Host memory contract, config key names and test responsibilities.

- Required: `dayu/host/README.md`
- Required: `dayu/config/README.md`
- Required: `tests/README.md`
- Conditional: `README.md` if root user manual contains stale config examples or memory terms.
- Conditional: `dayu/README.md` if development overview / terminology still says `verified_facts`.

Implementation agent must run:

```bash
rg -n "verified_facts|max_verified_facts|VerifiedFact|verified fact|verified_fact|TOOL_VERIFIED|PRETENDS_VERIFIED|proposed_verified|preserved_verified|stable:verified|max_verified" README.md dayu/README.md dayu/host/README.md dayu/config/README.md tests/README.md
```

Only update docs whose responsibilities match the stale content.

## 10. Stop Conditions

Planning found no blocking question at plan time. Implementation must stop and report `Blocking Questions For Controller` if any of these occur:

- Accepted evidence envelope cannot be defined without changing public Host command APIs.
- Schema migration requires preserving old config/database compatibility.
- Implementation needs to modify Engine, Fins storage, real Fins tool implementations or Service-facing command APIs.
- Implementation cannot keep extraction compaction-gated and single-call on the normal path.
- Structured JSON parsing / schema validation cannot work within bounded repair attempts.
- Bounded EventLog reads cannot provide `accepted_evidence_envelopes` for compact input without changing public Host command APIs.
- Implementation cannot produce small slice-local tests without broad, unrelated refactors.
- Evidence-backed fact validation requires Host to understand source / locator / financial business semantics.
- Current dirty worktree or unrelated file ownership makes safe staging / review impossible.

## 11. Residual Risks And Owners

- LLM fact extraction quality remains model-dependent. Owner: Context Governance / compactor tests in this phase; long-term factual quality and better extraction prompting belong to later compactor-quality work, not tool providers.
- Fine-grained item-level evidence ids are deferred. Owner: later evidence granularity work. P12.5 uses one stable evidence id per accepted tool result.
- Existing old durable snapshots are not compatible. Owner: controller decision already says new schema start; do not add compatibility.
- Old durable snapshots / item rows fail closed by design. Owner: implementation Slice 5 tests; operational migration remains explicitly out of scope unless controller opens a separate migration work unit.
- Real Fins tool source / locator descriptors may be sparse. Owner: later Fins/tool provider work unit. P12.5 envelope must tolerate empty opaque source/locator refs while still retaining payload/digest refs.
- Cross-session retrieval and public memory edit/forget are out of scope. Owner: later phases.

## 12. Blocking Questions For Controller

无。

## 13. Completion Report Format For Implementation Agents

Each implementation slice must report:

- Gate / work unit / slice id。
- Approved plan path：`docs/reviews/phase12-5-implementation-ready-plan-20260522.md`。
- Changed files。
- Implemented plan items。
- Tests and pyright commands run, with pass/fail result。
- README sync decision for that slice。
- Residual risks, classified as fixed now / covered by later approved slice / later phase / requires controller decision。
- Stop status：complete or `Blocking Questions For Controller`。

## 14. Planning Completion Report

- Plan artifact path：`docs/reviews/phase12-5-implementation-ready-plan-20260522.md`。
- Handoff-ready：是。
- Code-generation-ready：是。
- Blocking questions：无。
- Proposed slices：
  1. Contract Rename And Config Schema。
  2. Accepted Evidence Envelope In Tool Accept Path。
  3. Compaction Structured Candidate Contract And Accept Barrier。
  4. LLM Compactor Structured JSON Rewrite。
  5. Memory Projection Materialization。
  6. RunInputBuilder Rendering And Compaction Request Wiring。
  7. Integration Smoke, README Sync, Aggregate Validation。
- Validation matrix：见 §8 与各 slice 的 commands。
- README sync matrix：见 §9。
- Residual risks：见 §11，均有 owner / destination。
