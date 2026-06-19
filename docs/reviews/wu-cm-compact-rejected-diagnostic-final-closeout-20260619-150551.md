# Final Closeout: Compact Rejected Attempt Diagnostics

- **Gate**: final closeout
- **Work unit**: Conversation Memory compact rejected attempt diagnostics
- **Design doc**: `docs/host/conversation-memory-smoke-compact-followup.md`
- **PR**: https://github.com/noho/dayu-agent-r/pull/150
- **Timestamp**: 20260619-150551

## What Changed

- Added Host-only `CompactionRejectedAttemptDiagnostic` data and durable artifact writer for compact rejected attempts.
- Persisted diagnostic JSON through `LocalArtifactStore` and `PayloadStore` artifact descriptors.
- Added structured EventLog payload fields for rejected attempts: diagnostic artifact ref/digest, failure stage, parser/validator, exception class/message, offending block locator, text digest/length, material pack digest, and diagnostic suffix.
- Wired proactive dispatch and reactive Engine ingest rejected-attempt EventLog paths to write diagnostic artifacts in the caller transaction.
- Kept raw offending `REFERENCE_CONTINUITY` text only inside confidential Host diagnostic artifact JSON, not EventLog canonical payload or LLM-facing material.
- Updated public compact smoke test assertion drift: long current input now verifies full `current_input_anchor` delivery to compactor.
- Updated `dayu/host/README.md` and `tests/README.md`.

## Verification

- `source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py` -> `87 passed`.
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py::test_proactive_compact_long_current_input_reaches_compactor_without_lossy_anchor` -> `1 passed`.
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py` -> `11 passed, 1 skipped`.
- `source .venv/bin/activate && pyright` -> `0 errors, 0 warnings, 0 informations`.
- `gh pr checks 150` -> no checks reported on the branch.

## Review Status

- Plan review: completed with `/planreview`; accepted plan committed.
- Code review: completed with `/deepreview`; accepted finding fixed and re-reviewed.
- Aggregate deepreview: completed with `/deepreview --base main`; old smoke assertion drift fixed and re-reviewed.
- PR review: completed with `/deepreview --pr 150`; no blocking findings.

## Remaining Risks / Owners

- Production compact root cause for `previous reference continuity text is invalid`: assigned to later production memory compact failure work unit.
- Recovery-tier rejected attempt EventLog coverage, attempt count, stale-result protection, operation attribution, and tests: assigned to later recovery-tier compact audit diagnostics work unit.
- Diagnostic artifact file-only orphan after SQL rollback: existing artifact storage maintenance ownership.

## Long25 Diagnostic Signals

If `--long-rounds 25` fails again, the durable trail should expose:

- `operation_id`, `attempt_number`, `host_run_id`, `session_id`, `input_snapshot_cursor`;
- `failure_stage` such as `previous_compacted_view_parse`;
- `parser_or_validator`, exception class/message, diagnostic suffix;
- offending block section/kind/label/ordinal, text digest and length;
- material pack digest and diagnostic artifact payload ref/digest;
- artifact JSON with `previous_compacted_view` and offending `raw_text`.

## Gate Status

`draft-PR-pass` complete for PR 150.
