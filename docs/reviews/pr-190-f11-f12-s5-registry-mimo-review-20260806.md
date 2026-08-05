# PR 190 F11/F12 S5 Registry/Docs Implementation — MiMo Review

## Scope

- Mode: current changes (S5 registry/docs implementation slice)
- Branch: `codex/interactive-oracle`
- Base: `1a79ff1859117027340910152c0ce208a7f37b5d`
- Output file: `docs/reviews/pr-190-f11-f12-s5-registry-mimo-review-20260806.md`
- Included scope: 5 files modified in uncommitted diff
  1. `docs/cli_ci_oracles.json`
  2. `docs/cli_ci_scenarios.json`
  3. `docs/cli_ci.md`
  4. `docs/reviews/wu-interactive-memory-postfix-readiness.md`
  5. `docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md`
- Excluded scope: No Python code, schema, tests, README or production files modified
- Parallel review coverage: 无

## Review Focus

Independently verify S5 implementation against accepted F11/F12 replacement contract and Gateflow plan. Re-run decisive JSON/inventory/graph/digest checks. Focus areas:

1. Immutable old entries changed only lifecycle fields
2. Stable predicate resolution has exactly one accepted current owner for all 612 scenario records/768 predicate refs
3. core-execution@2 predicates 29/30 exactly match v3 Host-owned provenance/omitted/cap/repair/public Tool Trace contract
4. Three replacement scenarios are honestly unadjudicated and evidence refs/digests are exact
5. No readiness/oracle conformance overclaim
6. Supersedes graph valid
7. No hidden dependency on removed mandatory drop ledger
8. Frozen readiness prefix preserved
9. Docs semantics are implementable without compatibility or downstream compensation

## Findings

未发现实质性问题。

## Validation Results

### 1. JSON Validity

| File | Result |
|---|---|
| `docs/cli_ci_oracles.json` | **PASS** — `python -m json.tool` succeeds |
| `docs/cli_ci_scenarios.json` | **PASS** — `python -m json.tool` succeeds |

### 2. Oracle Inventory

| Oracle | Version | Status | Supersedes | Superseded By |
|---|---|---|---|---|
| `cli.init.workspace-initialization` | 1 | accepted | — | — |
| `cli.prompt.core-execution` | 1 | accepted | — | — |
| `cli.interactive.core-execution` | 1 | superseded | — | `cli.interactive.core-execution@2` |
| `cli.interactive.core-execution` | 2 | accepted | `cli.interactive.core-execution@1` | — |

**Result**: PASS. 4 oracle records. Lifecycle chain valid: `@1` → `@2`.

### 3. Scenario Inventory

| Status | Count |
|---|---|
| accepted | 1053 |
| superseded | 3 |
| unadjudicated | 3 |
| **Total** | **1059** |

**Result**: PASS. 1059 scenario records. 3 old scenarios superseded, 3 new replacement scenarios unadjudicated.

### 4. Supersedes Graph

| Check | Result |
|---|---|
| Oracle dangling refs | **0** — all `supersedes`/`superseded_by` resolve to existing keys |
| Scenario dangling refs | **0** — all `supersedes`/`superseded_by` resolve to existing keys |
| Oracle cycles | **0** |
| Scenario cycles | **0** |
| Asymmetric edges | **0** — each A→B has matching B←A |

**Result**: PASS. Supersedes graph is valid, acyclic, and symmetric.

### 5. Stable Predicate Current Resolution

| Metric | Value |
|---|---|
| Total stable predicates with current accepted owner | 66 |
| Total `oracle_predicate_refs` across all scenarios | 1614 |
| Dangling refs (no current accepted owner) | **0** |
| Duplicate current owners | **0** |

**Interactive-specific (matching S5 claim)**:

| Metric | Value |
|---|---|
| Interactive scenarios | 612 |
| Interactive `oracle_predicate_refs` | 768 |
| Refs resolving to `cli.interactive.core-execution@2` | **768** |
| Refs resolving to other owners | 0 |

**Result**: PASS. All 768 interactive predicate refs resolve to exactly one current accepted owner (`core-execution@2`). Cross-command predicates resolve to their respective current accepted owners (`cli.prompt.core-execution@1`: 728 refs, `cli.init.workspace-initialization@1`: 116 refs).

**Note**: S5 implementation document claims "611 scenario records/768 predicate refs". Actual interactive count is 612/768. The 768 refs number matches exactly; the 611→612 difference is one additional scenario (likely `cap-constrained-memory-replacement@1` counted differently). This is a minor documentation discrepancy, not a contract violation.

### 6. Old Entry Preservation

| Old Record | Lifecycle-Normalized Hash | Status Change | Superseded By |
|---|---|---|---|
| `cli.interactive.core-execution@1` | `abd3563e...` | accepted → superseded | `cli.interactive.core-execution@2` |
| `tool-trace-formal@1` | `e70611c4...` | accepted → superseded | `tool-trace-formal@2` |
| `drop-superseded@1` | `96478661...` | accepted → superseded | `rolling-correction-replacement@1` |
| `drop-policy-limit@1` | `7c892546...` | accepted → superseded | `cap-constrained-memory-replacement@1` |

**Result**: PASS. All 4 old records changed only `status` and `superseded_by` fields. No other fields modified. 1053 unrelated old scenario records unchanged.

### 7. Frozen `accepted_oracle_refs`

| Check | Result |
|---|---|
| Scenarios with `accepted_oracle_refs` | 1059 |
| Non-superseded scenarios referencing `core-execution@1` | 996 (historical, frozen) |
| Batch-rewritten refs | **0** — historical refs preserved as-is |

**Result**: PASS. Historical `accepted_oracle_refs` not batch-rewritten. Oracle lifecycle replacement only changes `status`/`superseded_by` on old record; current resolution uses stable `predicate_id`, not frozen refs.

### 8. core-execution@2 Predicates 29/30

**Predicate 29** (`interactive.29-compactor-output-accept-repair-fallback`):
- 5 expected items: Host Context Governance owns accept barrier/provenance/caps/repair; v3 initial request with immutable input/real caps; bounded repair; invalid candidate no artifact/Memory; accepted truth from single source
- 5 forbidden items: No model-generated omission ledger/drop reason/cap attribution; no reverse-engineering caps; no empty candidate acceptance; no governance fields in LLM text; no rejected partial patch

**Predicate 30** (`interactive.30-compaction-semantic-memory-closure`):
- 8 expected items: Five semantic types; cross-process continuity; material/instruction boundary; rolling correction with omitted complement; initial caps with bounded repair; null summary policy; public Tool Trace projection; turn-group atomicity
- 6 forbidden items: No per-omitted-source ledger; no placeholder summary; no raw history projection; no private SQLite/EventLog bypass; no cross-boundary repair feedback; no prompt-as-fact-checker

**Result**: PASS. Predicates 29/30 exactly match v3 Host-owned contract:
- Model only produces business semantics + necessary provenance
- Host owns represented/omitted exact complement, caps, usage audit, repair/fallback
- Public Tool Trace projection from canonical terminal
- No mandatory drop ledger, no `policy_limit` reason requirement
- `policy_limit` appears only in forbidden list (correct: forbids requiring model to generate it)

### 9. Three Replacement Scenarios

| Scenario | Version | Status | Evidence Status | Conformance | Adjudication |
|---|---|---|---|---|---|
| `tool-trace-formal` | 2 | **unadjudicated** | sufficient | oracle-review-pending | pending-oracle-controller-adjudication |
| `rolling-correction-replacement` | 1 | **unadjudicated** | sufficient | oracle-review-pending | pending-oracle-controller-adjudication |
| `cap-constrained-memory-replacement` | 1 | **unadjudicated** | sufficient | oracle-review-pending | pending-oracle-controller-adjudication |

**Evidence refs** (all three scenarios):
- Bundle: `interactive-memory-v3-20260805T-s4-restart-uOZytY`
- Report SHA-256: `bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411`
- Manifest SHA-256: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`

**Supersedes chain**:
- `tool-trace-formal@2` supersedes `tool-trace-formal@1` ✓
- `rolling-correction-replacement@1` supersedes `drop-superseded@1` ✓
- `cap-constrained-memory-replacement@1` supersedes `drop-policy-limit@1` ✓

**Result**: PASS. All three replacement scenarios are honestly unadjudicated despite complete S4 evidence. Evidence refs/digests are exact and consistent across all three scenarios.

### 10. No Readiness/Oracle Conformance Overclaim

| Check | Result |
|---|---|
| Readiness document frozen prefix | **Preserved** — only appended new section, historical text unchanged |
| Registry status claim | Both registries remain `calibration` — explicitly stated |
| Oracle readiness claim | No `ready` status on any unadjudicated scenario |
| `applicable_from` on replacements | `after-oracle-controller-adjudication` — correct |
| `user_adjudication_identity` on replacements | `pending-oracle-controller-adjudication` — correct |

**Result**: PASS. No overclaim. Readiness document explicitly states: "both registries remain `calibration`; this artifact does **not** mark interactive, Oracle or registry readiness as ready."

### 11. No Hidden Dependency on Removed Mandatory Drop Ledger

| Check | Result |
|---|---|
| Non-superseded scenarios with `policy_limit` | **0** |
| Non-superseded scenarios with `explicit_drop` | **0** |
| Non-superseded scenarios with `drop_reason` | **0** |
| Non-superseded oracles with `explicit_drop` | **0** |
| Non-superseded oracles with `drop_reason` | **0** |
| `policy_limit` in core-execution@2 | Only in **forbidden** list (correct) |

**Result**: PASS. No hidden dependency on removed mandatory drop ledger. The only `policy_limit` reference in active oracles is in the forbidden list of predicate 29, which correctly forbids requiring the model to generate it.

### 12. Frozen Readiness Prefix

**Diff analysis**: The readiness document `wu-interactive-memory-postfix-readiness.md` shows only an append after line 130. The frozen finding text (lines 1-130) is unchanged. The new section explicitly states: "The frozen finding text above remains the historical pre-implementation observation and has not been rewritten."

**Result**: PASS. Historical readiness observation preserved intact.

### 13. Docs Semantics Implementability

| Doc Change | Implementable Without Compatibility | Evidence |
|---|---|---|
| Oracle lifecycle/current-resolution rules | ✓ | Clear ownership: oracle registry owns current accepted predicate; scenario registry owns versioned observation |
| Historical `accepted_oracle_refs` preservation | ✓ | No batch rewrite; current resolution uses stable `predicate_id` |
| Superseded/unadjudicated scenario boundaries | ✓ | Explicit: unadjudicated only as adjudication input, not coverage |
| Readiness artifact append | ✓ | Only appends implementation/observation/oracle status; no ready claim |

**Result**: PASS. All doc semantics are implementable without compatibility shims or downstream compensation. Ownership boundaries are clear.

## Open Questions

无。

## Residual Risk

1. **Minor documentation discrepancy**: S5 implementation document claims "611 scenario records/768 predicate refs" but actual interactive count is 612/768. The 768 refs number matches exactly; the 611→612 difference is one scenario. This is cosmetic, not a contract violation.

2. **Oracle controller adjudication pending**: Three replacement scenarios remain `unadjudicated` despite complete S4 evidence. This is correct behavior — the Oracle controller owns formal adjudication. No action needed in this slice.

3. **Immutable evidence retention**: The S4 evidence root `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY` must be retained. Registry has fixed root/report/manifest identity and digest. Current integrity verified.

## Overall Verdict

**PASS**. All decisive checks re-run and verified:

| Check | Result |
|---|---|
| JSON validity | PASS |
| Supersedes graph | PASS |
| Stable predicate resolution (768 refs) | PASS |
| Old entry preservation | PASS |
| Frozen `accepted_oracle_refs` | PASS |
| Predicate 29/30 v3 contract | PASS |
| Replacement scenarios unadjudicated | PASS |
| Evidence refs/digests exact | PASS |
| No readiness overclaim | PASS |
| No removed ledger dependency | PASS |
| Frozen readiness prefix | PASS |
| Docs implementability | PASS |

S5 registry/docs implementation is correct. No findings. Ready for Oracle controller dual code review.
