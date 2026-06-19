# Plan review adjudication

## Gate

- Gate: plan review / fix adjudication
- Work unit: Conversation Memory smoke/log diagnostics and smoke coverage boundary
- Plan artifact: `docs/reviews/wu-cm-conversation-memory-smoke-log-diagnostics-plan-20260619-115520.md`
- Reviews:
  - AgentMiMo: `docs/reviews/plan-review-20260619-115816.md`
  - AgentDS: `docs/reviews/plan-review-20260619-115858.md`

## Decision Summary

Both reviews concluded `pass-with-risks`. No blocker requires stopping the work unit. The plan artifact was updated to remove ambiguity before implementation.

## Findings

### Mimo-01: `_durable_options_from_open_host_options()` implementation path unclear

- Status: rejected-with-reason
- Reason: the function already exists in `utils/smoke_host_public_conversation_memory_scenarios.py`; it constructs `HostDurableStoreOptions` from `OpenHostOptions` using existing imports. No new Host internal API exploration is required.
- Follow-up: no plan change needed for existence, but report data flow remains constrained to existing durable EventLog read helpers.

### Mimo-02 / DS-03: `_compact_audit_report_from_rows()` reuse path unclear and durable read logic may duplicate summary logic

- Status: accepted
- Plan fix: Slice 1 now requires `_compact_audit_report()` to only read rows and return `_compact_audit_report_from_rows(rows)`. The pure from-rows function must reuse `_compact_audit_summary_from_rows(rows)` and `_compact_request_trigger_sources(rows)`.
- Validation: tests target `_compact_audit_report_from_rows()` for report behavior; DB read logic remains thin.

### Mimo-03: `proposal_manifest_ref` missing stage mapping depends on current Host implementation

- Status: accepted
- Plan fix: plan now states the mapping depends on current Host manifest write timing and must be recalibrated if production payload semantics change.
- Tracking: current work unit still only outputs diagnostic smoke labels; production failure remains later work.

### Mimo-04: stdout newline / flush implementation underspecified

- Status: accepted
- Plan fix: plan now names the exact existing summary / failure print sites that need `flush=True` and requires line-level output assertions.

### Mimo-05: README should not mention internal issue 80

- Status: accepted
- Plan fix: README slice now says to avoid internal issue numbers and future eval claims; use "当前 smoke 不覆盖 memory correctness 全量验证" instead.

### DS-01: tests need boundary / error paths

- Status: accepted
- Plan fix: Slice 1 tests now include empty rows, payload non-object, empty diagnostic refs, helper type mismatch, missing operation id, and line-output assertions.

### DS-02: `_compact_audit_report` signature consistency

- Status: accepted as clarification
- Plan fix: signature remains keyword-only `*, session_id: str`, matching the current call site.

### DS-04: diagnostic suffix algorithm under-specified

- Status: accepted
- Plan fix: plan now includes explicit split / offset / fallback algorithm and two examples.

### DS-05: typed payload helper mismatch behavior undefined

- Status: accepted
- Plan fix: plan now states field missing and type mismatch return `None` or empty tuple; only non-object payload JSON remains fail-fast.

## Residual Risks

- Production memory compact failure remains assigned to later work unit.
- Long25 real-LLM validation may be skipped for cost/flakiness; unit / assembly tests cover no-real-LLM diagnostics.
- If Host changes compact EventLog payload semantics later, diagnostic smoke labels may need recalibration.

## Conclusion

Plan review gate status: pass-with-risks after plan fix.
