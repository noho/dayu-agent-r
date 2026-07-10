# WU-SEMANTIC-OWNERSHIP-01 P3-E Plan Re-Review (AgentDS)

## Review Metadata

- **Review target**: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md`
- **Fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-e-plan-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-e-plan-review-controller-adjudication.md`
- **Prior review**: `docs/reviews/wu-semantic-ownership-01-p3-e-plan-review-ds.md`
- **Reviewer**: AgentDS (adversarial plan re-review)
- **Date**: 2026-07-11
- **Gate**: `plan-re-review`
- **Conclusion**: **pass**

## Scope

Re-review the plan after Codex plan-fix gate to verify:

1. P3-E-PF-01 through P3-E-PF-06 are fully closed in the plan text.
2. The plan-fix did not introduce new material plan defects.
3. Focus areas: `last_error_code` preservation, hint dead-code cleanup, LOST vs UNKNOWN semantics, UNKNOWN consumer coverage, Fins producer sentinel/no-hang audit, and CLI `FinsDirectStreamContractViolation` disposition.

## Context Re-Verified

| Source | What was checked |
|---|---|
| `dayu/host/tool_runtime.py:775,793,3657-3907,7533,7559` | `last_error_code` used in WaitTimeout / WaitAccepted / accept failure paths; currently injected into `hint` at lines 7533, 7559 |
| `dayu/host/tool_runtime.py:266-276` | Accept reason constants (`_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON`, `_TOOL_RUNTIME_ACCEPT_REJECTED_REASON`) and hint format constants (`_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`, `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`, `_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`) |
| `dayu/host/tool_runtime.py:7496-7511` | `_hint_with_diagnostic_refs` helper concatenating diagnostic refs into hint |
| `dayu/host/accepted_result_projection.py:305-341` | `_result_payload` — all `None` exits confirmed: `HostDurableError` → `(None, ("result_payload_unavailable",))` |
| `dayu/host/accepted_result_projection.py:180-241` | `project_accepted_tool_result` — consumes `_result_payload` and `_accepted_status` |
| `dayu/host/accepted_result_projection.py:280` | `_result_event_payload` — `HostDurableError` → `({}, ("event_payload_unavailable",))` |
| `dayu/host/accepted_result_projection.py:394-416` | `_accepted_status` — current LOST paths: (1) payload unavailable diagnostics, (2) raw_outcome is None; `_status_from_raw_outcome` fallback; UNKNOWN as final fallback |
| `dayu/host/read_api.py:1285-1298` | `_accepted_result_activity_state` — COMPLETED→COMPLETED, CANCELLED→CANCELLED, else→FAILED (UNKNOWN maps fail-closed) |
| `dayu/host/run_input.py:3138-3142` | Calls `project_accepted_tool_result()` — consumes projection.status |
| `dayu/host/compact_material.py:50,2557` | Calls `project_accepted_tool_result()` — consumes projection fields |
| `dayu/host/evidence.py` | Defines `AcceptedToolEvidenceLLMMaterial`; no direct `AcceptedToolResultStatus` consumption |
| `dayu/host/memory.py` | Uses `AcceptedToolEvidenceLLMMaterial`; no direct `AcceptedToolResultStatus` consumption |
| `dayu/fins/ingestion_runtime.py:1295-1299` | `_DirectStreamProducerDone` sentinel class |
| `dayu/fins/ingestion_runtime.py:2751,4532` | Sentinel put on producer path; `_direct_missing_result_event` at line 2717 |
| `dayu/cli/commands/fins.py:96,720,736` | `FinsDirectStreamContractViolation(RuntimeError)` — CLI-local exception for missing terminal result |
| `dayu/service/fins_direct.py:497-510` | `_ensure_result_event` — duplicate raises `FinsDirectUsageError`, missing yields `_missing_result_event` |

All code facts align with the plan's source finding disposition and fix text.

## Prior Finding Closure Audit

### P3-E-PF-01 — last_error_code preservation → **CLOSED**

**Controller requirement**: S1 must audit every `last_error_code` path and preserve it in non-LLM-facing diagnostics or self-contained `message` text.

**Plan fix evidence** (plan lines 110-114):
- Explicit "audit every `last_error_code` reference" instruction.
- Three-way classification: already preserved / needs message update / out of S1 scope.
- Hard constraint: `last_error_code` must not be in hint AND must not be dropped.
- Concrete action: preserve in `message` as explanatory text and/or in ToolRuntime-owned diagnostics/failure_metadata.

**Test evidence** (plan lines 127):
- "accept timeout / ack-lost tests using a non-empty `last_error_code`, proving the code is preserved in `message`, owner diagnostics, `failure_metadata`, or Tool Trace while `hint is None`."
- "The test must fail if `last_error_code` is only removed from hint with no replacement diagnostic path."

**Assessment**: The fix is concrete, actionable, and covers the controller's concern. The three-way classification gives the implementation agent clear decision criteria. The test requirement provides a falsifiable gate. **Closed.**

---

### P3-E-PF-02 — hint dead-code cleanup → **CLOSED**

**Controller requirement**: Replace "remove if unused" with deterministic deletion; list all four hint-format constants plus unreferenced accept-reason constants.

**Plan fix evidence** (plan line 120):
- "deterministically delete `_hint_with_diagnostic_refs`" — no conditional.
- Explicit list: `_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`, `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`, `_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`.
- Accept reason constants: delete `_TOOL_RUNTIME_ACCEPT_REJECTED_REASON` or `_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON` if unreferenced after migration.
- S1 validation `rg` scan includes all five symbols.

**Assessment**: The fix is deterministic for the four hint-format symbols. The accept-reason constants have a conditional gated on reference scan, which is objectively verifiable and therefore deterministic in outcome. **Closed.**

---

### P3-E-PF-03 — LOST vs UNKNOWN semantics → **CLOSED**

**Controller requirement**: Inspect `_result_payload(...)` exits; add tests for unavailable payload paths; specify exact result when typed status absent but payload unavailable vs payload available with missing typed status.

**Plan fix evidence** (plan lines 181-186):
- Pre-implementation audit: "enumerate every exit that returns `result_payload=None` and prove it appends `result_payload_unavailable` or `event_payload_unavailable`."
- Explicit semantic split: payload unavailable + diagnostic → `LOST`; payload available + missing typed status → `UNKNOWN`.
- Safeguard: if audit finds a `None` exit without diagnostic, "fix `_result_payload(...)` at the projection owner to emit one; do not infer `LOST` from `raw_outcome is None`."
- Delete `_status_from_raw_outcome`.
- Add unavailable payload tests for `_result_payload(...)` paths.

**Code fact cross-check**: `_result_payload` currently has one `None` exit (line 341, `HostDurableError` → `(None, ("result_payload_unavailable",))`). The plan's audit requirement will confirm this is the only None exit. If any other path produces `None` without diagnostic, the fix instruction is to add the diagnostic at `_result_payload` — the semantic owner — not to add another inference rule in `_accepted_status`. This is architecturally correct.

**Assessment**: The fix provides a clear two-step process (audit then act), explicit semantic distinction, and a fallback safeguard. The validation `rg` scan covers `_result_payload`, `AcceptedToolResultStatus.UNKNOWN`, `_status_from_raw_outcome`, and payload-unavailable diagnostics. **Closed.**

---

### P3-E-PF-04 — UNKNOWN consumer coverage → **CLOSED**

**Controller requirement**: S2 validation must include explicit consumer coverage for `read_api`, `run_input`/evidence material, `memory`, and `compact` material paths.

**Plan fix evidence** (plan lines 188-203):
- Consumer impact check at projection boundaries with four named consumers.
- `read_api`: "activity state remains fail-closed and does not crash or reclassify from raw outcome." Verified: `_accepted_result_activity_state` maps non-COMPLETED/non-CANCELLED → FAILED/ERROR (fail-closed).
- `run_input` / evidence material: "LLM-facing material includes a self-explanatory unknown status or explicitly omits only where existing rules already omit non-actionable tool results; no raw fallback."
- `memory` projection: "handles `UNKNOWN` without converting it to completed / failed from raw outcome."
- `compact` material: "handles `UNKNOWN` consistently with projection status and does not reconstruct raw status."
- No-op escape hatch: "If a named consumer has no direct code path from accepted result projection, record that no-op evidence with an `rg` result."

**Code fact cross-check**: `evidence.py` and `memory.py` do not directly consume `AcceptedToolResultStatus` — they will qualify for no-op evidence. `run_input.py` and `compact_material.py` call `project_accepted_tool_result()` and consume the projection — they need explicit verification.

**Assessment**: The fix covers all four consumers with specific verification criteria and a documented no-op path. The validation `rg` scan includes S2-specific terms (`_result_payload`, `AcceptedToolResultStatus.UNKNOWN`) across both production and test directories. **Closed.**

---

### P3-E-PF-05 — Fins producer sentinel/no-hang audit → **CLOSED**

**Controller requirement**: Add producer lifecycle audit step, verification of sentinel emission on all exit paths, and concrete no-hang validation strategy.

**Plan fix evidence** (plan lines 251-256, 285):
- Pre-implementation lifecycle audit with four explicit checks:
  1. Normal producer completion puts exactly one sentinel.
  2. Producer exception paths put sentinel after surfacing exception.
  3. Every producer path emitting terminal RESULT reaches sentinel promptly.
  4. No producer relies on current early `break` after first RESULT for cleanup.
- "Record the audit evidence in the implementation artifact with source line references."
- No-hang validation: "focused async test should consume a normal direct stream through the new drain-until-sentinel path and complete without relying on arbitrary downstream timeouts."
- Stop condition: if producer hangs, "fix producer termination at `FinsIngestionRuntime` / direct producer owner; do not add CLI / Service timeout wrappers that hide the protocol lifecycle bug."

**Code fact cross-check**: `_DirectStreamProducerDone` is put at line 2751 and 4532. The current early-break path (line 2707) checks `isinstance(item, _DirectStreamProducerDone)` and `break`s. The plan changes this to drain-until-sentinel with buffered RESULT — the lifecycle audit requirement ensures this behavioral change is safe before implementation.

**Assessment**: The fix adds a concrete lifecycle audit with four falsifiable checks, requires recording source-line evidence, and provides a focused no-hang validation test. The stop condition correctly pins repair at Fins runtime owner. **Closed.**

---

### P3-E-PF-06 — CLI FinsDirectStreamContractViolation disposition → **CLOSED**

**Controller requirement**: Make Fins-owned typed protocol error the source of truth; delete or replace CLI-local exception; include CLI files in allowed scope.

**Plan fix evidence** (plan lines 272-275):
- "make the Fins-owned typed protocol error the only source of truth for direct stream protocol violations."
- "delete `FinsDirectStreamContractViolation` if it only represents missing terminal result."
- "replace CLI-local raises with `FinsDirectStreamProtocolError(MISSING_RESULT, operation_kind, ...)` or let the Service / runtime error propagate when already typed."
- CLI command-exit formatting: "catch / render `FinsDirectStreamProtocolError` directly without introducing a second exception type for the same protocol fact."
- `dayu/cli/commands/fins.py` and `tests/cli/test_fins_commands.py` explicitly listed in S3 allowed files.
- S3 validation `rg` scan includes `FinsDirectStreamContractViolation` as a disallowed term.

**Assessment**: The fix unambiguously elevates `FinsDirectStreamProtocolError` as the sole source of truth and provides clear disposition for the CLI-local exception (delete or replace). CLI files and tests are in scope. **Closed.**

---

## New Material Defect Check

I examined the plan for defects introduced by the plan-fix text, focusing on the six focus areas plus general architecture, overengineering, overcoupling, and implementation-readiness lenses.

### No new material defects found.

Detailed checks:

1. **S1 classification burden**: The three-way `last_error_code` classification (already preserved / needs message update / out of scope) could be burdensome if there are many paths. However, there are only two hint-injection call sites (lines 7533, 7559) plus the accept/awaiting-accept paths — the classification is scoped and manageable. Not a defect.

2. **S1 validation rg expected matches**: The plan correctly notes that `last_error_code` is expected in owner diagnostics and durable wait state — the `rg` output must be reviewed, not blindly expected empty. The plan provides classification rules. Not a defect.

3. **S2 `_result_payload` audit completeness**: The plan requires auditing all exits of `_result_payload`. The function is 37 lines with 4 return statements — the audit is straightforward for an implementation agent. Not a defect.

4. **S2 consumer `evidence.py` and `memory.py` no-op evidence**: Both files lack direct `AcceptedToolResultStatus` consumption. The plan's no-op evidence recording is appropriate. Not a defect.

5. **S3 "promptly" language in lifecycle audit**: The plan says "reaches the sentinel promptly" — this is somewhat subjective. However, the companion no-hang validation test provides the concrete gate: complete without arbitrary timeouts. The "promptly" is implementation guidance, not a pass/fail criterion. Not a material defect.

6. **S3 RESULT buffering event ordering**: The plan changes from "yield RESULT then break" to "buffer RESULT, drain, yield after sentinel." This is correctly scoped as a protocol fix, and the residual risk section (original plan) notes the ordering change as low risk. The plan-fix did not alter this. Not a new defect.

7. **S1 hint=None effect on Engine**: The plan conditionally includes an Engine-facing regression test. The Engine directly projects `result.hint` into LLM-facing JSON — `None` serializes as `null`, which LLMs handle. The risk is already identified in the original plan. Not a new defect.

8. **Cross-slice coupling**: S1 (hint + envelope), S2 (callback + projection), and S3 (Fins RESULT) remain independent. The plan-fix added cross-slice awareness (S2 references S1's hint cleanup, S3 references S2's typed-error approach) but no cross-slice implementation dependencies. Not overcoupled.

9. **No scope creep**: The plan-fix added detail within existing slice boundaries. Allowed files lists grew slightly (CLI files in S3, consumer files in S2) but remain within the plan's original semantic scope. Not a defect.

10. **Validation command completeness**: Aggregate validation `rg` covers all key terms. The plan correctly notes expected matches (e.g., `_DirectStreamProducerDone`, `AcceptedToolResultStatus.UNKNOWN`, `last_error_code` in owner diagnostics) vs. disallowed matches (`_status_from_raw_outcome`, `FinsDirectStreamContractViolation`, synthetic helpers). The classification instruction is concrete. Not a defect.

## Open Questions

None.

## Residual Risks (unchanged from prior review)

| Risk | Severity | Status |
|---|---|---|
| S1: `message` may not be actionable enough after hint removal | 低 | S1 stop condition covers; implementation artifact must report message readability |
| S2: External callback callers with string provider refs get `malformed_payload` | 低 | Intentional contract hardening |
| S3: RESULT buffering changes event yield order | 低 | CLI/Service expect RESULT as terminal; implementation artifact confirms |
| UNKNOWN status consumer impact | 中 | S2 now has explicit consumer coverage (PF-04) |

## Conclusion

**pass**

All six controller-adjudicated plan-fix items (P3-E-PF-01 through P3-E-PF-06) are fully and concretely addressed in the plan. The plan-fix added specific audit steps, deterministic cleanup instructions, explicit semantic distinctions, consumer coverage requirements, and lifecycle validation without introducing new material defects. The plan is code-generation-ready for the implementation gate.

---

## Completion Report

| Field | Value |
|---|---|
| **Status** | `complete` |
| **Artifact path** | `docs/reviews/wu-semantic-ownership-01-p3-e-plan-rereview-ds.md` |
| **Conclusion** | `pass` |
| **Prior fixes closed** | P3-E-PF-01 ✓, P3-E-PF-02 ✓, P3-E-PF-03 ✓, P3-E-PF-04 ✓, P3-E-PF-05 ✓, P3-E-PF-06 ✓ |
| **Prior fixes still open** | 0 |
| **New material finding count** | 0 |
| **Blocking questions** | none |
