# Phase 15 P15-S4 Code Review Controller Adjudication

- **Gate**: Phase 15 S4 code review adjudication
- **Date**: 2026-05-29
- **Approved plan**: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- **Implementation artifact**: `docs/reviews/phase15-s4-implementation-codex-20260529.md`
- **Review artifacts**:
  - `docs/reviews/phase15-s4-code-review-mimo-20260529.md`
  - `docs/reviews/phase15-s4-code-review-ds-20260529.md`

## Scope Decision

Both reviewers confirm the S4 implementation satisfies the core fail-before-success invariant: public `purge_session` cannot return a successful `PurgeSessionResult` unless purge tombstone audit JSONL append has succeeded and tombstone row carries `audit_record_ref` and `audit_record_digest`.

However, DS identified several quality findings that are directly caused by S4 changes. Controller accepts the current-slice fixes below because they improve the same invariant and reduce newly introduced duplication without changing public API shape.

## Findings Adjudication

| ID | Source | Decision | Reason |
| --- | --- | --- | --- |
| S4-ADJ-001 | DS H1: `PurgeTombstoneRow.audit_record_ref` / `audit_record_digest` remain `str | None` while S4 requires non-null | Accepted for fix | In this branch schema v14 is fresh-start, not a compatibility boundary. S4 should encode the new invariant in schema/type/codec, not leave it as a runtime-only check. |
| S4-ADJ-002 | DS M1: audit default path constants duplicated between `audit.py` and `open_host.py` | Accepted for fix | S4 introduced `default_log_audit_sink_options`; `open_host.py` should reuse it so command and opener share one path derivation source. This touches `open_host.py` only to remove duplication, not to change public API. |
| S4-ADJ-003 | DS M2: redundant mkdir in `LogAuditSink._append_line` | Accepted for fix | `_append_audit_json_line` owns directory creation. Keeping both calls is unnecessary duplication in the same module. |
| S4-ADJ-004 | DS L1: `_RecordingAuditRecorder.requests` cast unnecessary | Rejected as already satisfied | Direct code inspection shows `requests` is already annotated as `tuple[PurgeTombstoneAuditRecordRequest, ...]` and no cast is used there. No action required. |
| S4-ADJ-005 | DS L2: audit append succeeds but SQLite commit later fails can leave orphan JSONL line | Deferred residual | This is a cross-medium atomicity limitation between append-only JSONL and SQLite. It does not violate S4 fail-before-success because public success still requires tombstone commit. Track for S6 / follow-up audit tooling and docs. |
| MiMo INFO findings | Accepted as non-blocking | They are either addressed by S4-ADJ-001/S4-ADJ-003 or documented as residual performance/test-fixture observations. |

## Fix Requirements

Implementation specialist must:

1. Change fresh schema / row type / row codec so valid purge tombstone rows require non-empty audit ref and digest at the storage contract boundary.
2. Reuse `dayu.host.audit.default_log_audit_sink_options` from `open_host.py` and remove duplicated audit path constants/helpers.
3. Remove redundant directory creation in `LogAuditSink._append_line`.
4. Update focused tests and validation commands.

No public API shape, public error code, Engine / Service / UI / Fins, or RemoteProxy changes are allowed.
