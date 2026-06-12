# WU-OBS-SIGNALS-01 / OBS-SIG-03 Code Review Controller Adjudication

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-03` / P03 Structured Failure Metadata
- Implementation artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-03-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-03-code-review-mimo.md`
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-03-code-review-ds.md`

## Verdict

OBS-SIG-03 code review passed. No fix gate is required before accepting the slice.

## Review Results

### AgentMiMo

- Verdict: PASS.
- Findings: none blocking.
- Validation: 149 focused tests passed; pyright 0 errors.

### AgentDS

- Verdict: PASS with findings.
- Findings:
  - F1 LOW: bounded text max constant is duplicated in producer and projection.
  - F2 LOW: `_text_sha256` test helper is duplicated across focused test files.
  - F3 INFO: `budget_after_attempted_compact` is optional in projection.
  - F4 INFO: bounded text validators verify digest format, not digest equality.

## Controller Adjudication

- DS-F1 is not accepted as current fix. Producer and projection intentionally have independent error contracts; introducing a shared module for one stable constant would add more coupling than it removes. Reconsider only if OBS-SIG-04 / integration adds more shared signal validation constants.
- DS-F2 is not accepted as current fix. The duplicated test helper is tiny, local to independent test fixtures, and extraction would broaden test coupling without improving behavior coverage.
- DS-F3 is not a defect. The P03 contract explicitly allows `null` to mean unavailable; optional budget-after-compact preserves non-failing projection semantics for limited historical or malformed-adjacent signals.
- DS-F4 is not a defect. Projection cannot recompute a digest over truncated original text because it does not have the original text. Producer computes bounded value and digest from the original in one helper; tests cover full original digest behavior.

No accepted findings remain.

## Controller Verification

- `source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_engine_ingest_mapping.py tests/host/test_context_compact_events.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py`
  - Result: 185 passed.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## README Decision

The README updates are accepted:

- `dayu/host/README.md` now states that Tool Trace projects read-only structured signals including context pressure, tool timing, and failure metadata. This is current implemented Host behavior and fits the Host README update constraints.
- `tests/README.md` now lists context pressure / tool timing / failure metadata signal coverage in the existing Host testing layer. This reflects current tests and does not add a new testing convention.

## Residual Risk

- Historical trace rows without `failure_metadata` remain limited signal for WU-OBS-00 analyzer.
- Context compaction payload schema changes would require updating projection derivation; current implementation fails closed for required field type errors.
- P04 partial tool-call signal remains unimplemented and is owned by OBS-SIG-04.
