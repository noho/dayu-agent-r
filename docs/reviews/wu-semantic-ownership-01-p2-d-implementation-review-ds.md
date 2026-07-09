# WU-SEMANTIC-OWNERSHIP-01 P2-D Implementation Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-D`
- Gate: implementation review
- Review focus: owner boundary correctness, source-unavailable text ownership, downstream fallback scan, `selected_recent_window_turn_floor=0` legitimacy, test coverage, README triggers, memory docstring sync

## Input Artifacts

- Accepted plan: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-codex.md`
- Plan review adjudication: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-review-controller-adjudication.md`
- Plan re-review adjudication: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-rereview-controller-adjudication.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-d-implementation-controller-validation.md`

## Overall Verdict: **pass**

Implementation correctly addresses the root cause at the projection owner boundary, with no downstream fallback patches, no internal ref leakage, and adequate test coverage.

---

## Review Item 1: Owner Boundary Correctness

**Question**: Is `dayu/host/accepted_result_projection.py` the correct owner boundary for source-unavailable LLM-facing text?

**Evidence**:

1. `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` is defined at `dayu/host/accepted_result_projection.py:38-41` — the same module that already defines `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` for the query projection.

2. The constant is exported in `__all__` at line 787, available for tests to reference.

3. `_source_projection()` at lines 605-639 returns this text in both unavailable branches:
   - Envelope missing: `diagnostic_reason="accepted_evidence_envelope_missing"` (line 620)
   - Business source refs empty: `diagnostic_reason="business_source_unavailable"` (line 633)

4. All production consumers (`compact_material.py:2294`, `durable/memory.py:433,454`) consume `projection.source.text` directly — they never import or reference the constant. This means the constant is only a contract definition; consumers just use the projection value. Tests import the constant to assert semantic equivalence.

5. No downstream consumer defines its own source-unavailable text. `rg "ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT"` across the codebase shows only imports in:
   - `dayu/host/accepted_result_projection.py` (definition and internal use)
   - `tests/host/test_accepted_result_projection.py` (assertion)
   - `tests/host/test_compact_material.py` (assertion)
   - `tests/host/test_run_input_builder.py` (assertion)
   - `tests/host/test_memory_projection.py` (assertion)

**Verdict**: ✅ Correct owner boundary. Source-unavailable text is defined once in the projection owner and consumed by all downstream consumers through the same `projection.source.text` value.

---

## Review Item 2: `AcceptedToolResultSourceProjection.text: str` Tightening

**Question**: Is tightening `text` from `str | None` to `str` correct? Does `state`/`diagnostic_reason` still distinguish envelope missing from business source unavailable?

**Evidence**:

1. `AcceptedToolResultSourceProjection.text` at line 120 is now `str` (was `str | None`).

2. The docstring at line 115 states: "LLM-facing source 文本；无业务 source 时为业务中性不可用文案。" — clear contract.

3. `_source_projection()` now always returns a non-empty `text`:
   - Available source: formatted business refs (e.g., `"filing:MSFT-10K"`)
   - Envelope missing: `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` + `state=UNAVAILABLE` + `diagnostic_reason="accepted_evidence_envelope_missing"`
   - Business source unavailable: `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` + `state=UNAVAILABLE` + `diagnostic_reason="business_source_unavailable"`

4. `state` and `diagnostic_reason` remain intact — consumers that need structured differentiation can use `projection.source.state` and `projection.source.diagnostic_reason`.

5. This aligns with the existing query projection pattern: `AcceptedToolResultQueryProjection.text: str` with `state` and `diagnostic_reason` for structured differentiation.

6. The `RunInputMaterialBlock.readable_source_text` field remains `str | None` (line 247) — this is correct because non-evidence material blocks don't need source. The evidence path enforces non-None at `_pack_evidence_blocks` (line 2749-2750).

**Verdict**: ✅ Type tightening is correct and consistent with the query projection pattern. `state` and `diagnostic_reason` continue to provide structured differentiation. The `RunInputMaterialBlock` optional field is appropriate for non-evidence block paths.

---

## Review Item 3: Downstream Fallback Scan

**Question**: Do compact material, RunInputBuilder, Memory, Tool Trace, or Read API each independently construct source text or leak event id / payload ref / digest / cursor / policy / ToolRuntime / Host governance?

**Evidence** — full audit of each consumer:

### Compact Material (`dayu/host/compact_material.py`)

- Line 2294: `readable_source_text=projection.source.text` — direct consumption, no fallback.
- Line 2749-2750: `_pack_evidence_blocks` raises `ValueError` if `readable_source_text is None` for evidence blocks — evidence contract enforcement.
- No `or "..."` fallback, no internal ref concatenation, no payload/digest derivation.

### Memory (`dayu/host/durable/memory.py`)

- Lines 433, 454: `evidence_source_text=projection.source.text` — direct consumption in both `envelope_available` and `!envelope_available` paths.
- Lines 391, 404: `evidence_source_text=None` for non-accepted-tool-evidence paths (e.g., `USER_INPUT_ACCEPTED`, `RUN_SUCCEEDED`) — correct.

### Memory readable text (`dayu/host/memory.py`)

- `_accepted_evidence_readable_text` at line 1733: passes `source_text` through, conditional `if source_text is not None`. After P2-D, source_text is always non-None for accepted evidence. No fallback text injection.
- `_selected_evidence_text` at line 1703: passes `event.evidence_source_text` (which comes from `projection.source.text`). No internal ref reconstruction.

### RunInputBuilder (`dayu/host/run_input.py`)

- Lines 3018-3019: `if block.readable_source_text is not None: lines.append(f"source={block.readable_source_text}")` — conditional rendering for ALL block types (evidence and non-evidence). After P2-D, evidence blocks always pass. Correct.
- No payload ref, digest, or event ref leakage into rendered text.

### Compact Pipeline (`dayu/host/compact_pipeline.py`)

- Lines 1121-1122: `if block.readable_source_text is not None: lines.append(f"source={block.readable_source_text}")` — identical pattern to RunInputBuilder. Correct.

### Tool Trace (`dayu/host/tool_trace.py`)

- `_tool_result_summary_from_projection` at line 1434: only reads `status`, `result_text`, `result_details_text`, `diagnostic_reasons`, `payload_refs` from projection. Does NOT read `source.text`. Does NOT expose source text in trace_summary.
- Tool trace `signal_source` in `_trace_summary_signals` and similar uses are internal governance identifiers (e.g., `CONTEXT_COMPACTION_FAILED`) — not LLM-facing source text.
- No internal ref leakage into trace_summary visible text.

### Read API

- Not directly modified in this diff. Read API consumes the same `project_accepted_tool_result` projection. No Read API changes in diff. ✅

**Additional scan**: The `_readable_ref_text` filter in `accepted_result_projection.py:642-652` correctly filters internal ref kinds (`event`, `eventlog`, `payload`, `artifact`, `digest`, `tool_call_event`, `tool_result_event`). Only business refs (like `filing:MSFT-10K`) pass through.

**Verdict**: ✅ No downstream fallback found. All consumers derive source semantics from `projection.source.text` without independent source construction. No internal ref (event_id, payload_ref, digest, cursor, policy, ToolRuntime, Host governance) leaks into LLM-facing source text.

---

## Review Item 4: `selected_recent_window_turn_floor=0` in Public Compact Smoke

**Question**: Is `selected_recent_window_turn_floor=0` a valid test-goal setup or does it mask a production selection issue?

**Evidence**:

1. `selected_recent_window_turn_floor` is a production `MemoryProjectionPolicy` field (defined in `dayu/host/memory.py:764-786`). Its default is `DEFAULT_SELECTED_RECENT_WINDOW_TURN_FLOOR` (line 1036).

2. The production semantics: it protects the most recent N turns from being selected for compaction/eviction. A positive value means "don't compact the latest turn."

3. In the smoke test scenario, the test needs to:
   - First turn: produce accepted tool evidence
   - Second turn: trigger compaction — the just-produced evidence must be selectable for compaction
   - Third turn: reuse the compacted fact

4. With a positive floor (default), the first turn's evidence would be protected and NOT selectable for compaction in the second turn. The test sets `floor=0` to remove this protection, allowing the recently produced evidence to enter compaction immediately.

5. The production path at `compact_material.py:1663`: `if selected_recent_window_turn_floor == 0: return frozenset(explicit)` — zero floor means no automatic recent-turn protection, only explicit `protected_recent_raw_turn` blocks are protected. This is a valid and supported code path.

6. The change is STILL valid because:
   - It creates the test condition needed for the scenario (immediate post-evidence compaction)
   - It does NOT bypass any source projection logic — the source still comes from `projection.source.text`
   - The original test's defect (source.text=None causing crash in evidence block construction) is fixed at the projection owner, not masked by the floor change
   - The floor change is simply the mechanism to make the test scenario feasible

7. The implementation report correctly states: "使'刚产生的 evidence 进入 compactor'这个测试目标成立" — this is a test-goal setup, not a fixture mask.

**Verdict**: ✅ `selected_recent_window_turn_floor=0` is a valid test-goal setup that enables the immediate post-evidence compaction scenario. The original defect (source=None) is fixed at the projection owner, not masked by this change.

---

## Review Item 5: Test Coverage Adequacy

| Test File | New/Modified Tests | Coverage Target | Status |
|-----------|-------------------|-----------------|--------|
| `test_accepted_result_projection.py` | 3 new/modified tests | Source-unavailable text, envelope missing, cross-consumer equivalence with unavailable source | ✅ |
| `test_compact_material.py` | 1 new test (`test_pre_dispatch_evidence_uses_projection_unavailable_source`) | Evidence block source-unavailable, no-leak | ✅ |
| `test_run_input_builder.py` | 1 modified test | RunInputBuilder consumes projection source constant, no-leak | ✅ |
| `test_memory_projection.py` | 1 modified test | Memory uses projection source-unavailable text | ✅ |
| `test_tool_trace_projection.py` | 2 modified tests | Internal source refs present in input, no-leak in cold text | ✅ |
| `test_public_compact_smoke.py` | 1 modified test | Full integration smoke now passes | ✅ |

**Detailed assessment**:

### Projection tests (`test_accepted_result_projection.py`)
- `test_projection_unavailable_source_uses_shared_llm_text_and_filters_internal_refs` (new): Covers all-internal refs → UNAVAILABLE + shared text + no-leak. ✅
- `test_projection_missing_envelope_returns_shared_unavailable_source_text` (new): Covers envelope missing → UNAVAILABLE + shared text. ✅
- `test_projection_falls_back_to_arguments_when_semantic_query_is_absent` (modified): Updated to assert source.text == UNAVAILABLE_TEXT. ✅
- `test_same_accepted_result_has_equivalent_consumer_projection` (modified): Changed from available+unavailable mix to source-unavailable focus. Cross-consumer (Trace, Memory, RunInput, CompactMaterial) no-leak scan. ✅

### Compact material test
- `test_pre_dispatch_evidence_uses_projection_unavailable_source` (new): Verifies evidence block source text comes from projection constant, no internal refs in visible text. ✅

### RunInputBuilder test
- `test_accepted_tool_evidence_content_consumes_projection_source_text` (modified): Uses UNAVAILABLE_TEXT constant, verifies no `tool_call_event:` or `payload:` leakage, adds no-leak assertions for `event-request` and `event-result`. ✅

### Memory test
- `test_accepted_tool_evidence_includes_query_and_raw_outcome_without_refs` (modified): Uses UNAVAILABLE_TEXT constant for `evidence_source_text`, verifies it appears in rendered text, continues to verify no preview/display leakage. ✅

### Tool Trace tests
- `test_tool_call_chain_projects_hot_rows_and_cold_lines` and `test_wait_resolution_tool_trace_summarizes_request_and_result_details` (modified): Both now pass internal `payload` source refs as input, verify `payload-source-internal` does not appear in cold text. ✅

### Public compact smoke
- `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`: First/second/third terminals all `SUCCEEDED`. ✅

**Coverage gap assessment**:

The plan's cross-consumer equivalence test (`test_same_accepted_result_has_equivalent_consumer_projection`) now only covers the source-unavailable path. The source-available cross-consumer path is indirectly covered by:
- `test_projection_filters_internal_source_refs` — verifies business refs survive filtering
- Individual consumer tests with available source refs

This is acceptable because the scope of P2-D is source-unavailable semantics. The available path was already tested before P2-D and none of the P2-D changes affect it.

**Verdict**: ✅ Test coverage is sufficient. All plan-required test areas are covered. No missing coverage gaps for source-unavailable path.

---

## Review Item 6: README Trigger and Memory Docstring

### README triggers

**`dayu/host/README.md`**:
- The README already states at line 34: "accepted 工具结果投影给 Tool Trace、Read API、Conversation Memory、RunInputBuilder 与 compact material 时，LLM-facing 的查询语义、状态语义、结果摘要和业务 source 由 Host 统一投影；下游消费者只消费该投影。"
- This statement already covers the P2-D design: source is unified-projected by Host. The implementation only tightens the contract; it doesn't change the architecture.
- The README's update constraint says to document "当前代码已实现的...开发接口、公共契约、架构、稳定边界." The concept is already documented. Adding the specific constant name would be a detail below the README's abstraction level.
- **Decision**: 无需更新 — correct.

**`tests/README.md`**:
- No new test layers, running methods, or maintenance rules were added.
- The test changes are incremental additions to existing test files in already-documented test categories.
- **Decision**: 无需更新 — correct.

### Memory docstring sync

Plan requirement (P2D-PLAN-F02): "explicitly require implementation to check and, if needed, update memory projection docstrings."

**Evidence**:
- `dayu/host/durable/memory.py` line 113-114: docstring updated from `:param evidence_source_text: 可选业务可读 source 文本。` to `:param evidence_source_text: 可选业务可读 source 文本；accepted result 正常路径由统一 projection owner 提供非空 source 文本。`
- The field type remains `str | None` — correct for non-accepted-result paths.
- The docstring addition correctly scopes the non-None guarantee to the accepted-result normal path.

**Verdict**: ✅ Memory docstring sync is adequate. The docstring correctly notes that accepted-result normal path source text is non-None, while keeping the field optional for other event types.

---

## Propagation Audit — Independent Verification

The plan required a propagation audit covering 6 segments. Independent verification:

1. **Durable truth** → `TOOL_RESULT_ACCEPTED` payload, envelope, raw outcome unchanged. ✅ No schema migration.

2. **Projection** → `project_accepted_tool_result()` now produces `source.text` as always-`str`. Available path unchanged; unavailable path produces shared constant with structured diagnostics. ✅

3. **Compact material** → `_accepted_tool_evidence_delta_blocks` directly uses `projection.source.text`. Evidence block enforcement at `_pack_evidence_blocks` catches None. Canonical refs kept as internal provenance, not LLM-facing source. ✅

4. **Compactor input** → Fake compactor in smoke uses prompt-local labels, not canonical refs, as business facts. ✅

5. **Accepted compact fact** → Stable fact derived from raw accepted evidence material. Source-unavailable text is source status, not upgraded to financial fact. ✅

6. **Follow-up visible outputs** → RunInputBuilder, Conversation Memory, Tool Trace all derive from same projection. Tests verify no internal ref leakage (`payload-internal`, `event-internal`, `sha256:internal`). ✅

---

## Validation Commands — Controller Results Cross-Check

Controller reran all validation commands and confirmed:
- Public compact smoke: `1 passed` ✅
- Projection tests: `13 passed` ✅
- Compact material + RunInput + Memory: `206 passed` ✅
- Tool trace: `46 passed` ✅
- Pyright: `0 errors, 0 warnings, 0 informations` ✅
- `git diff --check`: passed ✅
- Source-leak scan: hits limited to internal implementation fields, no leakage in source-unavailable text ✅

---

## Non-blocking Notes

### N1: Source-available cross-consumer equivalence test scope narrowing

`test_same_accepted_result_has_equivalent_consumer_projection` was changed from testing available-source cross-consumer consistency to exclusively testing unavailable-source. The available-source cross-consumer path is still indirectly covered by individual tests (`test_projection_filters_internal_source_refs` + individual consumer tests). This is acceptable for P2-D scope since P2-D only modifies the unavailable path.

**Severity**: N/A (non-blocking observation).  
**Recommendation**: No action needed for P2-D. If future work touches source-available rendering, a dedicated cross-consumer available-source test would be a useful addition.

### N2: Tool Trace does not expose source text

Tool Trace `_tool_result_summary_from_projection` does not read or expose `projection.source.text`. This is consistent — Tool Trace is an operator-facing diagnostic view, not an LLM-facing context. The implementation correctly did NOT force source text into Tool Trace, as noted in the implementation's residual risks section.

**Severity**: N/A (by design).

---

## Residual Risks

Agreed with implementation report:

1. Tool Trace doesn't expose source text — by design, not a gap.
2. `selected_recent_window_turn_floor=0` only serves the test scenario; production recent tail selection is unchanged.
3. P2-D does not close other WU-SEMANTIC-OWNERSHIP-01 backlog items.

---

## Conclusion

**Verdict: pass**

Implementation:
- ✅ Fixes root cause at the projection owner boundary (`accepted_result_projection.py`)
- ✅ Defines single source-unavailable text constant, reused by all consumers via `projection.source.text`
- ✅ Tightens `AcceptedToolResultSourceProjection.text` from `str | None` to `str` while preserving `state`/`diagnostic_reason` differentiation
- ✅ No downstream fallback: compact material, RunInputBuilder, Memory, Tool Trace all consume the same projection value
- ✅ No internal ref leakage: verified via source-leak scan and no-leak test assertions across all consumers
- ✅ `selected_recent_window_turn_floor=0` is a valid test-goal setup, not a fixture mask
- ✅ Test coverage is adequate: projection, compact material, RunInput, Memory, Tool Trace, and public compact smoke
- ✅ README trigger decisions correct
- ✅ Memory docstring sync adequate
- ✅ Pyright clean, all tests pass
