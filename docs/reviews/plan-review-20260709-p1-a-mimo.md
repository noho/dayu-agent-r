# WU-SEMANTIC-OWNERSHIP-01 P1-A Plan Review (AgentMiMo)

## Metadata

- Review date: 2026-07-09
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-a-plan.md`
- Codex review: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-codex.md`
- Umbrella plan: `docs/host/wu-semantic-ownership-01-umbrella-plan.md`
- Controller adjudications:
  - `docs/reviews/wu-semantic-ownership-01-plan-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-plan-rereview-controller-adjudication.md`
- Review style: adversarial plan review

## Conclusion

**`pass-with-risks`**

Plan is code-generation-ready with well-defined root cause, correct owner boundary, and sound contract approach. No blocking findings. Three medium-severity risks require implementation-stage attention; four low-severity residual observations are documented.

---

## Review Dimensions

### D1. Motivation and direct evidence

**Verdict: PASS**

Motivation is directly supported by current code evidence. The plan correctly identifies that `AcceptedEvidenceEnvelope` already exists (umbrella plan's "完全没有 accepted evidence envelope" is expired), and narrows the real remaining problem to: multiple consumers independently back-query, fallback, and filter the same durable facts for query/status/source projection.

Evidence scan commands in §2 are comprehensive and current. The four root-cause categories (query projection, status projection, source projection, raw outcome duplication) are each backed by specific file:line references.

No stale findings detected.

### D2. Owner boundary

**Verdict: PASS**

Owner boundary is correctly defined:

- **Producer**: `tool_runtime.py` (ordinary accepted) and `waiting.py` (wait-resolution accepted) — confirmed by code.
- **Validator**: `evidence.py` (envelope schema, digest, producer ref) — confirmed by code.
- **Durable**: EventLog canonical payload / payload descriptor — confirmed by code.
- **Projection**: new `accepted_result_projection.py` helper — correctly identified as the missing piece.

Boundary exclusions (§3 "修复不得落在") are correct: no single-consumer workaround, no UI/Service/CLI, no test fixture compatibility, no wait/poll/runtime downstream governance.

The projection helper reading from EventLog (not from a cached/durable projection store) is appropriate: projection is derived truth, re-derivable from durable truth, and should not introduce a new durable state.

### D3. Contract approach: sibling projection helper vs. extending envelope

**Verdict: PASS**

The decision to add a sibling Host projection helper rather than extending `AcceptedEvidenceEnvelope` is well-reasoned:

1. Envelope's docstring explicitly states it is provenance mapping, not content container — verified at `evidence.py:156`.
2. Host design §projection section confirms accepted evidence envelope is provenance mapping.
3. Writing derived text back to envelope would confuse durable truth with readable projection.
4. New helper can unify query/status/source/result semantics without changing EventLog schema.

This aligns with C04 (consumer migration pressure) from controller adjudication.

### D4. Implementation slices

**Verdict: PASS**

Slices are code-generation-ready:

- **S1** (Projection Contract): Focused on `accepted_result_projection.py` + narrow `evidence.py` additions + focused tests. Clear completion signal with 9 test scenarios.
- **S2** (Consumer Migration): Allows all 7 consumer files + tests. Completion signal uses `rg` to verify old helpers removed.
- **S3** (Tests/Docs/Audit): Lists all 7 test files + README/design updates. Completion signal includes cross-consumer equivalence tests.

Slice ordering is correct: S1 defines contract before S2 migrates consumers; S3 validates after S2.

### D5. Consumer migration completeness checklist

**Verdict: PASS**

§8 checklist covers all required consumers:

1. Tool Trace ✓
2. Read API ✓
3. Durable Memory ✓
4. Conversation Memory ✓
5. RunInputBuilder ✓
6. CompactMaterial ✓
7. Compact pipeline ✓
8. Tests ✓

All 8 items match the consumers identified in §2 evidence. This satisfies C04 from controller adjudication.

### D6. Validation commands

**Verdict: PASS**

§9 validation commands are sufficient:

- Focused tests for new projection helper.
- Focused tests for each migrated consumer group.
- `rg` to verify old private helpers removed from production code.
- `pyright` for type safety.
- `git diff --check` for whitespace.

### D7. Stop conditions

**Verdict: PASS**

All four stop conditions are real and correctly identified:

1. EventLog schema change needed but design truth not ready.
2. Source refs business classification impossible from current `OpaqueEvidenceRef`.
3. Budget truncation conflicts between consumers.
4. Consumer needs wait/poll/runtime state (wrong owner boundary).

### D8. Propagation audit plan

**Verdict: PASS**

§12 covers the full semantic propagation path: produce → validate → persist → trace → read API → memory → run input → compact → tests. 9-item checklist is comprehensive.

### D9. README / design update triggers

**Verdict: PASS**

§10 triggers are correct and aligned with CLAUDE.md trigger rules. The conditional update of `docs/host/design.md` (only when public projection contract or durable schema changes) is appropriate.

---

## Findings

### F01 [Medium] Compact pipeline migration details in S2

**Location**: §6 S2 "允许改动"

**Issue**: S2 "允许改动" section lists 6 consumer migration items but does not explicitly describe the compact_pipeline migration action. The section mentions "RunInputBuilder / compact pipeline 删除重复 `_llm_facing_evidence_source_text()` blacklist 逻辑" but this is in the bullet for RunInputBuilder, not a standalone compact_pipeline item.

The allowed files section does list `dayu/host/compact_pipeline.py`, and §8 checklist item 7 covers compact pipeline. The risk is that S2 implementation may treat compact_pipeline as a sub-item of RunInputBuilder rather than an independent consumer with its own `_is_internal_evidence_source_part()` duplication.

**Evidence**: `compact_pipeline.py:1158` defines `_is_internal_evidence_source_part()` independently from `run_input.py:3051`. Both are used by their respective `_llm_facing_evidence_source_text()` wrappers. The plan correctly notes this duplication in §2 evidence but S2 doesn't give compact_pipeline its own migration bullet.

**Violates**: Plan completeness — consumer migration should treat each independent consumer explicitly.

**Required fix**: Add a standalone S2 bullet for compact_pipeline migration: "compact pipeline 的 accepted evidence source note 消费 projection helper 的 `readable_source_text`，删除 `_llm_facing_evidence_source_text()` 和 `_is_internal_evidence_source_part()` 独立实现。"

**Severity rationale**: Not blocking because the allowed files already include `compact_pipeline.py` and the checklist covers it. Risk is implementation oversight, not design error.

### F02 [Medium] Projection helper interface design under-specified

**Location**: §4 "helper 输入建议为"

**Issue**: The plan suggests helper input as `HostTransaction`, `EventLogStore` or equivalent read protocol, and `TOOL_RESULT_ACCEPTED` row. But it does not specify:

1. Whether the helper takes a single `TOOL_RESULT_ACCEPTED` row and internally reads the `TOOL_CALL_REQUESTED` request atom, or whether the caller must provide both.
2. Whether the helper is a standalone function or a method on a projection service object.
3. Whether the helper raises on identity mismatch or returns a typed error in `diagnostic`.

S1 says "读取并校验 envelope 指向的 `TOOL_CALL_REQUESTED` request atom" which implies internal back-query. But this is the same back-query pattern the plan aims to eliminate from consumers — it's just moved into the helper. This is architecturally correct (single back-query in one place), but the plan should explicitly state this design decision.

**Violates**: Plan clarity for code generation.

**Required fix**: Add one sentence to §4: "projection helper 内部负责从 envelope 指向的 `TOOL_CALL_REQUESTED` request atom 读取 query 信息；消费者不直接读 request atom。identity mismatch 在 helper 内部处理，写入 `diagnostic` 字段，不抛异常。"

**Severity rationale**: Not blocking because S1 completion signal already lists "request atom 缺失、identity mismatch" as test scenarios. The design intent is implicit; making it explicit reduces implementation ambiguity.

### F03 [Medium] `AcceptedToolResultStatus` mapping rules for 'lost' and 'unknown'

**Location**: §4 `AcceptedToolResultStatus`

**Issue**: The plan proposes `AcceptedToolResultStatus` with values including `completed`, `failed`, `cancelled`, `governed_error`, `lost`, `unknown`. The current `_tool_result_status()` in `tool_trace.py:2008` only returns field values from `resolution_kind`, `tool_fact_kind`, or raw outcome `kind`/`result.ok`. It has no concept of `lost` or `unknown`.

The plan says "状态由 payload 中的 Host accepted status fields 归一，优先级和 wait-resolution / ordinary result 映射只在 helper 内定义" but does not define:
1. What payload condition maps to `lost`.
2. What payload condition maps to `unknown` vs. returning `None`.
3. Whether `governed_error` corresponds to an existing `tool_fact_kind` value or is new.

**Violates**: Contract completeness for code generation.

**Required fix**: Either add a brief mapping table in §4 (e.g., "`lost`: payload missing or envelope identity mismatch; `unknown`: status fields present but not mappable to known values; `governed_error`: `tool_fact_kind == 'governed_error'` or equivalent"), or explicitly defer this to S1 implementation with a note that mapping rules must be defined in S1 before writing tests.

**Severity rationale**: Not blocking because S1 completion signal requires tests for these states, forcing definition during implementation. Risk is implementation delay from ambiguity.

---

## Residual Risks

### R01 [Low] Source refs production paths mostly empty

The plan correctly notes in §11 that current `source_refs` / `locator_refs` production paths are mostly empty. S1 may only be able to define the source projection contract and no-leak behavior without meaningful business source content. This is a subsequent source producer WU concern, not a P1-A blocker.

### R02 [Low] Tool Trace result details bounded rendering

Tool Trace's result details extraction may still need bounded rendering for display. The plan correctly notes this is a Tool Trace display strategy and should not reverse-modify projection truth. The interaction between projection helper's `result_details_text` and Tool Trace's own truncation needs to be clarified during S1, but is not a design error.

### R03 [Low] Legacy EventLog rows missing new fields

If legacy `TOOL_RESULT_ACCEPTED` EventLog rows lack envelope or raw outcome, the projection helper must handle them via typed limited-signal or fail-closed. The plan's non-goal §5 "不为旧 schema / 旧 fixture 写兼容读取分支；历史缺字段只进入统一 limited-signal 或 fail closed" is correct. Implementation must not add compatibility branches for old rows.

### R04 [Low] Cross-consumer equivalence test design

S3 lists cross-consumer equivalence tests but doesn't specify the test structure. Implementation should create a shared fixture that constructs a `TOOL_RESULT_ACCEPTED` event with known query/status/source, then asserts that Tool Trace, Memory, RunInput, and CompactMaterial all derive the same projection semantics. This is an implementation detail, not a design gap.

---

## Open Questions

### OQ01: `docs/host/issues-implementation-control.md` update

Git status shows `docs/host/issues-implementation-control.md` is modified on the current branch. The plan does not mention updating this file. Should P1-A update the implementation control document to reflect its scope and status? This is a process question, not a design blocker.

### OQ02: Interaction with P1-C

P1-C (LLM-facing governance leakage cleanup) depends on P1-A's projection contract. The plan's non-goal §5 "不把 source refs 的业务分类扩展成通用 provenance 平台" is correct, but P1-C may need to reference the projection helper's `readable_source_text` for LLM-facing text. Should P1-A document the projection helper's public API surface for P1-C consumption?

---

## Summary

| Dimension | Verdict |
|---|---|
| D1. Motivation / evidence | PASS |
| D2. Owner boundary | PASS |
| D3. Contract approach | PASS |
| D4. Implementation slices | PASS |
| D5. Consumer migration checklist | PASS |
| D6. Validation commands | PASS |
| D7. Stop conditions | PASS |
| D8. Propagation audit | PASS |
| D9. README/design triggers | PASS |

| Category | Count |
|---|---|
| Blocking findings | 0 |
| Medium findings | 3 |
| Low residual risks | 4 |
| Open questions | 2 |

**Final verdict: `pass-with-risks`** — plan is approved for implementation. Medium findings F01-F03 should be addressed during S1/S2 implementation, not as plan blockers.
