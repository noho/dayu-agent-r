# WU-TOOL-01 Slice 3 Code Review (MiMo)

- Gate: code review
- Reviewer: MiMo
- Date: 2026-06-01
- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Implementation artifact: `docs/reviews/wu-tool-01-implementation-slice3-codex-20260601.md`
- Scope: Slice 3 — Governed Event / Diagnostic / Trace Scope

## Findings

### BLOCKING-01: `_diagnostic_refs_for_duplicate` uses `duplicate_decision.message` instead of `duplicate_decision.diagnostic_message`

- File: `dayu/host/tool_runtime.py:2547-2551`
- Severity: **BLOCKING**
- Plan reference: Section 7.11 — "diagnostic emitter message for duplicate must use `policy.messages.attempt_scope_diagnostic`"

Current code:

```python
ref = self._diagnostic_emitter.emit(
    ToolTraceDiagnosticRecord(
        reason_code=_duplicate_reason_code(duplicate_decision.kind),
        message=duplicate_decision.message,  # BUG: should be diagnostic_message
    )
)
```

`DuplicateDecision` carries two separate message fields:
- `message`: per-decision-type message (e.g., `hard_stop`, `hint`, `reuse` message from `DuplicateGovernanceMessages.message_for(kind)`)
- `diagnostic_message`: attempt-scope diagnostic message from `DuplicateGovernanceMessages.attempt_scope_diagnostic`

In `InMemoryAttemptDuplicateGovernance._decision_for_accepted_entry()` (`tool_duplicate_governance.py:496-497`):
```python
message=self._policy.messages.message_for(decision),
diagnostic_message=self._policy.messages.attempt_scope_diagnostic,
```

The diagnostic emitter is contractually required to emit the **attempt-scope diagnostic message**, not the per-decision-type model-facing message. The `diagnostic_message` field exists precisely for this purpose, but `_diagnostic_refs_for_duplicate` reads `message` instead.

**Impact**: diagnostic record message will be `hard_stop` / `hint` / `require_justification` / `reuse` / `prior_accept_missing` text instead of the configured `attempt_scope_diagnostic` text. This breaks the plan's separation of model-facing message vs diagnostic message.

**Fix**: Change line 2550 from `duplicate_decision.message` to `duplicate_decision.diagnostic_message`, and update the None-check guard (line 2545-2546) to check `diagnostic_message` instead of `message`.

---

### BLOCKING-02: `test_candidate_and_ack_carry_duplicate_diagnostic_refs` asserts diagnostic message equals hard_stop configured message

- File: `tests/host/test_toolruntime_diagnostics.py:219`
- Severity: **BLOCKING**
- Plan reference: Section 7.11 and Slice 3 test expectations

Current assertion:

```python
assert diagnostics.records[0].message == configured_message
```

where `configured_message = "配置化 hard stop duplicate message"` — this is the `hard_stop` message passed to `DuplicateGovernanceMessages(hard_stop=configured_message)`.

Per plan Section 7.11, the diagnostic record message must be `policy.messages.attempt_scope_diagnostic`. The test should assert:

```python
assert diagnostics.records[0].message == "duplicate tool call governed by attempt-local ToolRuntime index"
```

or, if a custom `attempt_scope_diagnostic` is configured in the test setup, assert against that custom value.

**Note**: This test currently passes because BLOCKING-01 causes the wrong message to flow through. Fixing BLOCKING-01 will cause this test to fail unless the assertion is updated simultaneously.

---

### OK-01: `tool_trace.py` duplicate_scope projection — CORRECT

- File: `dayu/host/tool_trace.py` — `_extract_canonical_trace`, `_trace_summary`, `_build_cold_line`, `_build_hot_row`
- `duplicate_scope` is extracted from payload via `_json_value_or_none(payload, _FIELD_DUPLICATE_SCOPE)` (line 482)
- Stored in `trace_summary` as `_FIELD_DUPLICATE_SCOPE` (line 774)
- Carried through to both hot row and cold line correctly
- Test assertions in `test_tool_trace_projection.py:352-355` and `:391-394` verify `trace_summary["duplicate_scope"]` equals `{"kind": "attempt", "attempt_id": "attempt-trace"}`
- **No issues found.**

### OK-02: `test_toolruntime_accept_barrier.py` TOOL_CALL_GOVERNED duplicate_scope and prior refs — CORRECT

- File: `tests/host/test_toolruntime_accept_barrier.py:504-514`
- `test_event_sequence_monotonic_and_reuse_has_canonical_governance_only` asserts:
  - `duplicate_scope["kind"] == "attempt"` (line 507)
  - `duplicate_scope["attempt_id"] == reuse.attempt_id` (line 508)
  - `reuse_prior_event_refs` matches prior accepted event refs (line 509-514)
- `test_duplicate_allow_does_not_append_governed_event` verifies allow policy does not write governance event
- **No issues found.**

### OK-03: No durable ledger / EventLog rebuild / schema change / Any / object / untyped signatures / README violations

- `DuplicateDecision` fields are fully typed (`tool_duplicate_governance.py:254-277`)
- `DuplicateGovernanceRequest` uses `DuplicateGovernanceScope` typed field, not bare string
- No `Any`, `object`, untyped parameters or returns found in changed code
- No compatibility re-exports in `tool_runtime.py`
- No `DuplicateGovernanceMessages` fields use untyped `dict` or extra payload
- README updates (if any) are limited to `dayu/host/README.md` and `tests/README.md`
- **No issues found.**

---

## Open Questions

None.

## Verification

| Command | Result |
|---|---|
| `pytest tests/host/test_toolruntime_diagnostics.py` | 5/5 passed |
| `pytest tests/host/test_toolruntime_accept_barrier.py` | 11/11 passed |
| `pytest tests/host/test_tool_trace_projection.py` | 5/5 passed |
| `pytest tests/host/test_toolruntime_duplicate_governance.py` | 31/31 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |

**Note**: Tests pass because BLOCKING-01 and BLOCKING-02 are consistent with each other (both use `message` instead of `diagnostic_message`). Fixing BLOCKING-01 without simultaneously fixing BLOCKING-02 will cause `test_candidate_and_ack_carry_duplicate_diagnostic_refs` to fail.

## Conclusion

**2 BLOCKING findings**, both related to the diagnostic message path:

1. `tool_runtime.py:2550` — `_diagnostic_refs_for_duplicate` emits `duplicate_decision.message` (per-decision model-facing message) instead of `duplicate_decision.diagnostic_message` (attempt-scope diagnostic message). Violates plan Section 7.11.
2. `test_toolruntime_diagnostics.py:219` — test asserts diagnostic record message equals `hard_stop` configured message instead of `attempt_scope_diagnostic`. Must be updated alongside BLOCKING-01.

Remaining blocking findings: **2**
