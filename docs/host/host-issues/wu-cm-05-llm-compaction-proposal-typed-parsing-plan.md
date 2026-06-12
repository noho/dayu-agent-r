# WU-CM-05 LLM Compaction Proposal Typed Parsing Plan

## Metadata

- Work unit: `WU-CM-05 LLM Compaction Proposal Typed Parsing`
- Type: issue-backed hardening work unit
- GitHub issue: #93, child of #81
- Current gate: plan gate only
- Branch observed during plan gate: `work/cm-05-06-08-09`
- Artifact path: `docs/host/host-issues/wu-cm-05-llm-compaction-proposal-typed-parsing-plan.md`
- Design sources: `docs/host/design.md`; `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Gate constraints: no implementation, no review gate, no commit, no push, no PR.

## Goal / Motivation / Success Signal

目标：把 post-#81 的 LLM compaction proposal parsing 收敛到单一显式 typed validation boundary：

```text
LLM raw final answer
  -> parse JSON
  -> local JsonValue/object helpers with field-path validation
  -> existing Host-owned candidate section types
  -> Host-owned ConversationCompactOutputVNext
```

动机成立，且严重性没有被高估。当前代码已经有 `ConversationCompactOutputVNext` accept target，但 LLM raw JSON 到该 target 之间仍以 `Mapping[str, JsonValue]` 传递，并在多个 helper 中分散读取字段。这个形态让类型边界、字段级错误定位和 proposal 字段覆盖都依赖调用者记住局部 helper 规则，不符合 issue #93 的 hardening 目标。

成功信号：

- `parse_conversation_compact_output_vnext(...)` 不再把 `_parse_vnext_proposal(...)` 返回的宽 `Mapping[str, JsonValue]` 直接传给各 section parser。
- `json.loads(...)` 之后只有一个外部输入收口点；raw JSON 只存在于局部 helper 边界，递归 helper 验证字段、类型、枚举和数量后直接构造现有 Host-owned candidate section types。
- 每个 post-#81 proposal 字段都有直接验证路径，错误信息包含业务可读 field path，例如 `evidence_backed_facts[0].evidence_kind`。
- malformed JSON、top-level 非 object、缺必填字段、字段类型错误、数组超限、非法 enum、未知 label、stale label、跨 section label、current input anchor label 都有测试。
- vNext output 没有 patch operation 字段；旧 patch candidate 只能作为 old schema fail-closed 覆盖，不得为测试项重新引入 patch operation schema。
- 不改变 compact output 业务语义，不放宽非法 proposal 的接受条件。
- 受影响 pytest 通过，`python -m pyright dayu/ tests/ utils/` 不新增或扩散类型错误。

## First-principles Judgment And Direct Code Evidence

第一性原理判断：

- LLM final answer 是不可信外部文本，必须先解析为 JSON，再在 Host-owned typed boundary fail closed。接受边界不能依赖宽 mapping 在多个 parser helper 间传递。
- `ConversationCompactOutputVNext` 是 Host accepted candidate contract，不应承担 raw LLM JSON 的全部诊断职责。parser 应作为 LLM raw JSON primary validator，递归验证 raw JSON 并直接构造现有 Host-owned candidate section types，最终构造 Host-owned output contract。
- 私有 typed proposal DTO / 平行类型层次的动机被 review 高估。当前目标可以通过局部 JsonValue helper、完整 field path 组合和现有 candidate type 构造满足；默认不引入 8 个与 Host candidate type 同构的私有 DTO。
- proposal parsing 只负责字段、类型、枚举、数量和 prompt-local source label contract；semantic repair / retry、artifact 写入、memory projection、budget gate 和 EventLog 写入仍属于 Context Governance / compaction operation。
- post-#81 vNext schema 已移除旧 patch candidate。为满足旧 issue 文案中的 patch operation 验收，只能测试旧 schema fail closed，不能把 patch operation 重新设计成 vNext 字段。

直接证据：

- `docs/host/issues-implementation-control.md:873`-`875` 要求将 LLM proposal parsing 收敛为显式 typed validation，并固定转换边界。
- `docs/host/issues-implementation-control.md:879`-`887` 明确非目标是不改变 compact output 业务含义、不放宽非法 proposal，验收要求字段级验证和 invalid proposal diagnostic。
- `dayu/host/llm_compaction.py:546`-`575` 的 public parser 当前先拿 `_parse_vnext_proposal(...)` 返回值，再调用多个 section parser 构造 `ConversationCompactOutputVNext`。
- `dayu/host/llm_compaction.py:578`-`608` 的 `_parse_vnext_proposal(...)` 当前返回 `Mapping[str, JsonValue]`，并使用 `cast(Mapping[str, JsonValue], parsed)`。
- `dayu/host/llm_compaction.py:611`-`762` 以宽 `Mapping[str, JsonValue]` 为输入分别解析 `session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items` 与 `diagnostics`。
- `dayu/host/llm_compaction.py:765`-`826` 已经有 source label validation，但它发生在 Host candidate 构造之后，仍应保留为 accept barrier 前的 label contract 校验。
- `tests/host/test_llm_compaction.py:172`-`187` 覆盖 happy path，`207`-`223` 覆盖 old schema fail closed，`226`-`242` 覆盖 current input anchor label；还缺系统性字段类型、数组上限、非法 enum、未知/stale/cross-section label 和 malformed JSON 覆盖。

## Design Document Alignment

Host design alignment:

- `docs/host/design.md:3107`-`3122` 明确 Context Governance 是 Host 责任，包含 `ConversationCompactInputVNext` 构造、`ConversationCompactOutputVNext` accept barrier 和 compact event / memory projection 输入。
- `docs/host/design.md:3145` 明确 LLM 只能提出 `ConversationCompactOutputVNext` 结构化候选，Host 负责校验、接受并写入 canonical compact event / artifact。
- `docs/host/design.md:3166` 明确 `LLMContextCompactor` 是 Host-owned 单次 proposal executor，返回 typed candidate 或 typed failure；不负责 retry、EventLog、artifact 或 memory projection。
- `docs/host/design.md:3167` 把空文本、非 JSON、top-level 非 object、缺必填 key、字段类型 / 值非法、未知 source label、source boundary violation 等归入 Host compaction operation 的 repair / retry 决策输入。本 WU 只让单次 proposal executor 更准确地产出 typed failure。
- `docs/host/design.md:3210` 明确 prompt-local label mapping 是内部 accept barrier / audit / rebuild 用途，不作为 LLM 主要语义输入；parser 只能验证 label contract，不得把 event id、payload ref、digest、cursor 等内部治理字段投影为业务事实。

Engine design alignment:

- `docs/engine/design.md:487`-`501` 明确 Engine 不做上下文压缩、不计算 Host budget、不做 compact / retry；是否压缩和如何重新构造消息属于 Engine 之外的调用方职责。
- 因此本 WU 不修改 Engine contract、Engine state machine、Runner overflow behavior 或 provider retry。

## Non-goals / Scope Boundary

非目标：

- 不改变 compact output 的业务语义。
- 不修改 Conversation Memory 语义模型。
- 不放宽非法 proposal 接受条件。
- 不引入 Service-provided candidate builder、repair callback、新 schema 或 per-run compactor override。
- 不处理 WU-CM-06、WU-CM-08、WU-CM-09。
- 不改变 `ConversationCompactInputVNext`、source label section 规则、compact material selection 或 memory projection。
- 不改变 EventLog schema、HostEvent public shape、durable artifact schema、Run / Attempt 状态机。
- 不把旧 patch operation 重新引入 vNext proposal。
- 不 commit / push / PR。

本 plan gate 只写本 artifact。后续 implementation gate 必须限制在 plan 明确允许的文件内；若发现必须改变 public contract、schema 或设计真源，应停止并回到设计裁决。

## Affected Files / Modules

本 gate 创建：

- `docs/host/host-issues/wu-cm-05-llm-compaction-proposal-typed-parsing-plan.md`

后续 implementation 允许修改：

- `dayu/host/llm_compaction.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_contract.py`，仅当需要补充 output contract 与 parser 边界协同测试时修改

后续 implementation 只读参考：

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/compaction_operation.py`
- `docs/host/design.md`
- `docs/engine/design.md`
- `docs/host/issues-implementation-control.md`
- `dayu/host/README.md`
- `tests/README.md`

禁止修改：

- `dayu.engine`
- `dayu.service`
- `dayu.fins`
- `dayu.config`
- durable schema / migration
- GitHub issue / PR metadata

## Contract / Schema / State-machine / Public-interface Changes

Public Host API: no change.

Engine public contract: no change.

Durable schema: no change.

EventLog / HostEvent schema: no change.

Run / Attempt state machine: no change.

LLM-facing schema: no change. The accepted output shape remains the existing vNext JSON shape with:

- `schema_version`
- `session_summary`
- `evidence_backed_facts`
- `answer_anchors`
- `forward_intents`
- `reference_continuity_items`
- `diagnostics`

Internal contract: no new public schema and no default private DTO hierarchy.

- Prefer replacing the wide cross-function proposal mapping with private module-level JSON helper functions that validate raw JSON fields and directly construct existing Host-owned candidate section types:
  - `SessionSummaryCandidateVNext`
  - `EvidenceBackedFactCandidateVNext`
  - `AnswerAnchorCandidateVNext`
  - `AnswerAnchorItemVNext`
  - `ForwardIntentCandidateVNext`
  - `ReferenceContinuityCandidateVNext`
  - `DiagnosticCandidateVNext`
  - `ConversationCompactOutputVNext`
- Raw JSON values may be typed as `JsonValue` or `Mapping[str, JsonValue]` only inside local parser/helper boundaries. They must not become the cross-function proposal contract after the top-level parse step.
- Only if implementation finds direct code evidence that helper-based direct candidate construction cannot satisfy typed parser boundaries may it introduce the smallest private typed structure needed for that specific gap. That exception must not default to eight section DTOs, must not mirror the entire Host candidate hierarchy, must be justified in implementation notes, and must remain private to `dayu/host/llm_compaction.py`.

## Implementation Decisions

1. Keep `parse_conversation_compact_output_vnext(request, final_answer)` as the only public parser entry point.
2. Replace `_parse_vnext_proposal(...) -> Mapping[str, JsonValue]` with a function that returns `ConversationCompactOutputVNext`, or with a function that returns an internal tuple/sequence of existing Host-owned candidate section types before final output construction. It must not return a broad mapping as the cross-function proposal contract.
3. Keep `json.loads(...)` at the raw external boundary, then immediately validate top-level object and recursively read fields into existing Host candidate constructors. Do not use `cast(...)` to bless parsed JSON.
4. Use this type narrowing pattern:
   - `parsed: JsonValue = json.loads(raw)` immediately after malformed JSON handling.
   - `_json_object(value: JsonValue, field_path: str) -> Mapping[str, JsonValue]` validates `isinstance(value, Mapping)` and every key is `str`; it returns only after the object boundary is proven.
   - Array helpers accept `JsonValue`, validate `Sequence` / list semantics without treating `str` as array, enforce max item count, and pass each item as `JsonValue` to item parsers.
   - Recursive helpers use `isinstance` to narrow each concrete JSON member before returning `str`, `int`, tuple values, enum values, candidate dataclasses, or `None`.
   - Do not use `Any`, `object`, `# type: ignore`, or broad `cast(...)` to skip validation. If pyright cannot narrow a value, add a smaller helper with a proven input/output type instead of weakening the type boundary.
5. Use module-level private helpers for field extraction and path composition. Helpers must receive a complete absolute `field_path` for the value being validated, or must receive a parent path plus key/index generated by the explicit join helpers below:
   - `_field_path(parent: str, key: str) -> str`: returns `key` when `parent == ""`, otherwise `f"{parent}.{key}"`.
   - `_item_path(parent: str, index: int) -> str`: returns `f"{parent}[{index}]"`; callers must pass a non-empty array field path.
   - Example helper signatures:
     - `_required_value(source: Mapping[str, JsonValue], key: str, *, parent_path: str) -> JsonValue`
     - `_required_string(source: Mapping[str, JsonValue], key: str, *, parent_path: str) -> str`
     - `_required_array(source: Mapping[str, JsonValue], key: str, *, parent_path: str, max_items: int) -> tuple[JsonValue, ...]`
     - `_optional_non_negative_int(source: Mapping[str, JsonValue], key: str, *, parent_path: str) -> int | None`
     - `_required_enum(source: Mapping[str, JsonValue], key: str, *, parent_path: str, allowed_values: frozenset[str]) -> str`
   - Helper error messages must use the complete path produced by `_field_path(...)` or `_item_path(...)`, never only the leaf key. Stable examples required by tests include `evidence_backed_facts[0].evidence_kind` and `answer_anchors[0].anchor_items[1].ordinal`.
6. Field helpers must return typed values:
   - required object / nullable object
   - required array with `max_items`
   - required string
   - optional string array with item path and max item count
   - required enum for `FactEvidenceKindVNext`, `ForwardIntentTypeVNext`, `ForwardIntentStatusVNext`, `ReferenceContinuityReasonVNext`
   - optional non-negative integer for `answer_anchors[i].anchor_items[j].ordinal`
7. Validate `schema_version` explicitly against `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT` before constructing `ConversationCompactOutputVNext`, so invalid schema version diagnostics point to `schema_version`.
8. Parser is the LLM raw JSON primary validator and owns field-path diagnostics. `ConversationCompactOutputVNext.__post_init__` is the Host contract safety net and must remain unchanged. Parser should not duplicate unnecessary structural invariants already enforced by candidate constructors beyond what is needed to read raw JSON safely; candidate construction failures from `KeyError`, `TypeError` or `ValueError` must be wrapped uniformly as `LLMCompactionProposalError`.
9. Keep `_validate_vnext_candidate_source_labels(...)` as the source label accept barrier, but make sure errors preserve field paths already used by the typed parser.
10. Remove parsing-time reliance on broad `Mapping[str, JsonValue]` beyond local JSON object helper boundaries. If a helper must temporarily accept a JSON object, it must be private, typed as `Mapping[str, JsonValue]`, and not become the cross-function proposal contract.
11. Do not add generic callback / factory / profile / query style extension points. This is a closed parser hardening task.
12. Do not modify prompt assets or LLM-facing schema text unless tests prove the existing prompt and parser schema are inconsistent; if that happens, stop and report because it would touch `dayu/config/` README trigger and LLM-facing semantics.

## Small Implementation Slices

### Slice 1: Introduce direct typed candidate parser

Objective: replace wide proposal mapping as the cross-function parser contract without adding a parallel DTO hierarchy.

Allowed files:

- `dayu/host/llm_compaction.py`
- `tests/host/test_llm_compaction.py`

Exact changes:

- Do not add the eight private LLM proposal dataclasses listed in the prior plan revision.
- Change `_parse_vnext_proposal(final_answer)` to return `ConversationCompactOutputVNext`, or split it into private helpers that return existing Host candidate section tuples consumed immediately by the final output constructor.
- Add private field helpers and path join helpers exactly as described in Implementation Decisions #4-#6.
- Replace section parser inputs from broad top-level `Mapping[str, JsonValue]` to local object helper boundaries plus explicit parent paths. Section parsers should directly return existing Host-owned candidate section types.
- Remove the unchecked `cast(Mapping[str, JsonValue], parsed)` import/use if no other code in the module needs `cast`.
- Preserve existing public exception type `LLMCompactionProposalError`.

Data flow:

```text
final_answer.strip()
  -> json.loads(raw)
  -> _json_object(parsed, "proposal")
  -> section helpers validate field paths and construct Host candidate section types
  -> ConversationCompactOutputVNext(...)
  -> _validate_vnext_candidate_source_labels(...)
```

Error handling:

- Empty string: `compactor vNext proposal is empty`.
- Malformed JSON: preserve JSON parser message category, but wrap as `LLMCompactionProposalError`.
- Top-level non-object: field path should identify `proposal`.
- Missing top-level key: `missing required key: <key>` or equivalent, with key name.
- Nested type/value errors: include exact path, for example `answer_anchors[0].anchor_items must be array`.
- Nested item errors: include exact item path, for example `answer_anchors[0].anchor_items[1].ordinal`.
- Invalid enum: include exact path and invalid value category.
- Candidate constructor failures that escape parser field helpers must be caught and re-raised as `LLMCompactionProposalError` so parser callers see one proposal failure type.

Invariants:

- No accepted invalid proposal condition may become valid.
- Current input anchor labels remain rejected.
- Unknown / stale / cross-section labels remain rejected.
- `ConversationCompactOutputVNext.to_json()` shape remains unchanged.
- `ConversationCompactOutputVNext.__post_init__` remains unchanged as Host contract safety net; parser is the primary validator for LLM raw JSON and field-path diagnostics.

Tests:

- Existing happy path still passes.
- Existing old schema fail-closed test still passes.
- Existing current anchor label rejection still passes.
- Add path-specific diagnostics tests that prove complete nested paths are stable, including `evidence_backed_facts[0].evidence_kind` and `answer_anchors[0].anchor_items[1].ordinal`.
- Add a candidate safety-net wrapping test only if a candidate constructor can still reject after parser field validation, for example an empty `source_labels` case; assert it raises `LLMCompactionProposalError`, without requiring parser to duplicate every candidate invariant.
- Add a focused assertion that parser code no longer exposes `_parse_vnext_proposal(...)` as a wide mapping contract if feasible through behavior; do not add brittle source-text tests unless this repo already uses them for weak typing.

Stop condition:

- If pyright requires introducing `Any`, `object`, untyped parameters, `# type: ignore`, or a broad `cast(...)` to make the parser type-check, stop and redesign the helper boundary instead of landing weak typing.
- If direct candidate construction cannot satisfy the typed boundary, stop and document the direct code evidence before introducing any minimal private typed structure. Do not silently reintroduce the eight-DTO plan.

### Slice 2: Complete invalid proposal diagnostics coverage

Objective: ensure each invalid proposal class required by WU-CM-05 has a direct test.

Allowed files:

- `tests/host/test_llm_compaction.py`
- `dayu/host/llm_compaction.py`, only to fix parser diagnostics exposed by tests

Exact tests to add or update:

- malformed JSON: `"{bad"` raises `LLMCompactionProposalError` with `not valid JSON`.
- top-level non-object: `[]` raises with top-level / proposal object diagnostic.
- missing required key: remove `diagnostics`, assert key path.
- field type error: set `session_summary.summary_text = 1`, assert `session_summary.summary_text`.
- nested array type error: set `answer_anchors[0].anchor_items = "bad"`, assert `answer_anchors[0].anchor_items`.
- array item type error: set `diagnostics[0].source_labels = [1]`, assert `diagnostics[0].source_labels[0]`.
- top-level array overlimit: create `evidence_backed_facts` with `MAX_VNEXT_FACT_ITEMS + 1`, assert `evidence_backed_facts`.
- nested array overlimit: create `answer_anchors[0].anchor_items` with `MAX_VNEXT_ANSWER_ANCHOR_ITEMS + 1`, assert nested path.
- invalid enum: set `evidence_backed_facts[0].evidence_kind = "bad"`, assert `evidence_backed_facts[0].evidence_kind`.
- invalid enum: set `forward_intents[0].status = "bad"`, assert `forward_intents[0].status`.
- invalid enum: set `reference_continuity_items[0].reason = "bad"`, assert `reference_continuity_items[0].reason`.
- unknown label: set a source label to a syntactically plausible but absent label, assert `unknown source label`.
- stale label: set a stale-looking old label, assert `stale source label`.
- cross-section label: cite an evidence label from an answer field or answer label from evidence field, assert `cross-section label`.
- old patch schema: keep the existing old schema fail-closed test with `pinned_state_patch_candidate`; assert fail closed as old schema, for example via missing required vNext key. Do not add patch operation field parsing, patch operation enum parsing, or any vNext patch operation validator.

Data flow:

- Tests should mutate `_proposal_json(compact_input)` or a local minimal valid proposal builder.
- Every invalid test should call `parse_conversation_compact_output_vnext(compact_input, json.dumps(...))`.
- `_proposal_json(compact_input)` is only a legal raw proposal JSON shape builder. Slice 2 tests must pass `json.dumps(...)` raw JSON into the public parser and must not depend on `_parse_vnext_proposal(...)` internals, private helper return types, or any DTO/candidate construction detail.

Error handling:

- Tests assert stable diagnostic substrings by field path and reason, not the whole sentence.
- Do not assert implementation class names in error messages.
- Tests for nested paths must assert complete absolute paths, not only leaf keys, including `evidence_backed_facts[0].evidence_kind` and `answer_anchors[0].anchor_items[1].ordinal`.

Invariants:

- All invalid proposal tests fail before any candidate can be accepted.
- Tests do not require Service-provided repair callback or candidate builder.
- Tests do not expose event id, payload ref, digest, cursor, tool_call_id or other internal governance identifiers as business facts.

Stop condition:

- If adding tests reveals the current prompt schema differs from the parser-supported schema, stop and report before modifying prompt assets.

### Slice 3: Contract and boundary cleanup

Objective: remove leftover broad parsing helpers that are no longer needed, without touching unrelated compact behavior.

Allowed files:

- `dayu/host/llm_compaction.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_contract.py`, only if contract tests need a small assertion update

Exact changes:

- Remove unused `_required_mapping(...)`, `_json_mapping(...)` or similar helpers only if they are no longer used in `llm_compaction.py`.
- Keep generic JSON helpers only where they are still directly part of raw JSON parsing.
- Update docstrings for changed private functions in Chinese, including params, returns and exceptions.
- Ensure no new public export is introduced.
- Ensure `from typing import cast` is removed if unused.

Data flow:

- Public call sites remain unchanged.
- `LLMContextCompactor.run_prepared_compactor_proposal(...)` still calls `parse_conversation_compact_output_vnext(prepared_input.compact_input, outcome.final_answer)`.

Error handling:

- `LLMCompactionProposalError` remains the only proposal parse / schema / label public failure type.
- `TypeError` for invalid `request` input remains unchanged.

Invariants:

- No changes to `CompactionRequest`, `ConversationCompactInputVNext`, `ConversationCompactOutputVNext`, compaction operation retry semantics, or memory projection.
- No lazy import.
- No compatibility wrapper or re-export.

Stop condition:

- If cleanup requires changing `dayu/host/compaction.py` dataclass invariants, stop and split a separate design decision; WU-CM-05 should not redefine Host output semantics.

## Tests / Validation Commands And Expected Assertions

Plan gate validation performed only static read/search commands, because this gate intentionally made no implementation code change.

Implementation validation commands:

```bash
source .venv/bin/activate
pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q
python -m pyright dayu/ tests/ utils/
```

Expected assertions:

- `tests/host/test_llm_compaction.py` covers happy path and every invalid proposal class listed in Slice 2.
- `tests/host/test_compaction_contract.py` remains green, proving `ConversationCompactOutputVNext` contract and LLM-facing output contract identifier did not change.
- pyright reports no new or expanded errors.

Optional focused commands during implementation:

```bash
source .venv/bin/activate
pytest tests/host/test_llm_compaction.py -q
rg -n "cast\\(|_parse_vnext_proposal|Mapping\\[str, JsonValue\\]" dayu/host/llm_compaction.py
```

Expected optional assertions:

- No `cast(...)` remains in the vNext proposal parsing path.
- `_parse_vnext_proposal` no longer returns a broad mapping; it returns `ConversationCompactOutputVNext` or existing Host-owned candidate section types consumed by the final output constructor.
- Remaining `Mapping[str, JsonValue]` usages, if any, are local JSON helper boundaries or unrelated existing code paths.

## README / Docs Decision

This plan gate only creates `docs/host/host-issues/wu-cm-05-llm-compaction-proposal-typed-parsing-plan.md`; it does not require README updates.

Implementation will touch `dayu/host/llm_compaction.py`, so `dayu/host/README.md` must be checked after implementation. This plan fix gate read `dayu/host/README.md` before making the README decision:

- `dayu/host/README.md` Agent update constraint says the file records already implemented Agent / Host design intent, public contracts, architecture boundaries, stable mechanisms and extension points; it explicitly forbids work unit process state, file-level changelog, future plans and unstable implementation details.
- Relevant Host README compaction sections describe stable context governance behavior: proactive / reactive compact, accepted compact payload consumption by Conversation Memory, and Host-owned LLM-facing input rewriting. They do not describe `_parse_vnext_proposal`, `cast`, wide mapping, private helper shape, or parser internals.
- Expected decision: no README update unless implementation changes stable developer-facing Host compact behavior, public contracts, context governance semantics, or LLM-facing schema beyond tighter internal diagnostics.

Implementation will touch `tests/host/...`, so `tests/README.md` must be checked after implementation. This plan fix gate read `tests/README.md` before making the README decision:

- `tests/README.md` records existing test layering, commands and maintenance rules, and its README update boundary says to update only when test layers, running modes or maintenance rules change.
- Current `tests/README.md` already lists Host compaction-related commands and existing `test_llm_compaction.py` / `test_compaction_contract.py` coverage under Host Context Governance / Conversation Memory / P12.6 memory semantic smoke.
- Expected decision: no README update if implementation only adds cases to existing Host compaction parser test files without a new test layer, new command category or changed maintenance convention.

No `dayu/config/` prompt asset change is planned. If implementation discovers prompt/schema mismatch requiring prompt edits, stop and re-evaluate `dayu/config/README.md` before editing.

## Risks / Open Questions

- Risk: duplicating validation already present in `ConversationCompactOutputVNext.__post_init__` could create two divergent rule sets. Mitigation: parser is the raw LLM JSON primary validator for field-path diagnostics; `ConversationCompactOutputVNext.__post_init__` remains the Host contract safety net unchanged. Parser validates what is necessary to safely read raw JSON and construct candidates, uses shared constants from `dayu.host.compaction`, and wraps candidate construction failures as `LLMCompactionProposalError`.
- Risk: improving diagnostic messages may break tests that assert old broad error text. Mitigation: update only affected tests to assert field path and reason substrings.
- Risk: `json.loads(...)` is typed broadly by Python tooling. Mitigation: treat it as the only raw external boundary, annotate to `JsonValue`, then use recursive helpers with `isinstance` narrowing into concrete typed values and existing Host candidate constructors without `Any`, `object`, `# type: ignore`, or unchecked `cast`.
- Risk: control doc currently has pre-existing uncommitted edits marking WU-CM-05 as planning. This plan gate treats it as read-only source evidence and does not modify it.
- Open question: none blocking. The scope is implementation-ready.

## Why This Is Not Over-designed

The plan explicitly avoids a default parallel private DTO hierarchy. It keeps raw JSON inside local helper boundaries, uses explicit path join helpers for diagnostics, and directly constructs existing Host-owned candidate section types before the final `ConversationCompactOutputVNext`. It does not add a public schema version, Service extension point, callback, factory, repair API, parser framework, or cross-module abstraction. The remaining changes are the minimum structure needed to remove the current wide mapping/cast boundary and make invalid LLM proposals fail closed with field-level diagnostics.

## Completion Report Format

When this plan gate is reported, use:

1. Artifact path
2. Fix status: `ready-for-re-review` or `blocked`
3. Accepted findings addressed
4. Validation performed
5. Remaining risks/open questions
