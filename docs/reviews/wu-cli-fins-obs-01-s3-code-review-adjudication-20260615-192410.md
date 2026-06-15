# WU-CLI-FINS-OBS-01 S3 Code Review Adjudication

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S3-service-fins-direct-subscription`
- Gate: code review adjudication
- Implementation artifact: `docs/reviews/wu-cli-fins-obs-01-s3-implementation-codex.md`
- Review artifacts:
  - AgentMiMo: `docs/reviews/code-review-20260615-192103.md`
  - AgentDS: `docs/reviews/code-review-20260615-191952.md`

## Review Conclusions

- AgentMiMo: `PASS`
- AgentDS: `PASS-WITH-FINDINGS`

No blocking issue was found. The controller accepts all three AgentDS low-severity findings because they are small, directly evidenced, and improve the Service boundary's diagnosability and regression coverage without expanding S3 scope.

## Accepted Findings

### S3-FIX-01 terminal event / job record inconsistency should not raise usage error

- Source finding: AgentDS `DS-001`.
- Decision: accepted.
- Required fix:
  - When `stream_job_events_until_terminal(...)` sees a terminal event but `read_job(...)` returns a non-terminal record, raise an exception whose semantics clearly indicate runtime data inconsistency rather than user/service usage error.
  - Do not change normal terminal mapping behavior.
  - Add focused test coverage for this inconsistency path.

### S3-FIX-02 negative after_sequence validation coverage

- Source finding: AgentDS `DS-002`.
- Decision: accepted.
- Required fix:
  - Add a focused test proving `stream_job_events_until_terminal(handle, after_sequence=-1)` fails fast with `FinsDirectUsageError`.

### S3-FIX-03 terminal event read_job failure propagation coverage

- Source finding: AgentDS `DS-003`.
- Decision: accepted.
- Required fix:
  - Add a focused test proving that when `read_job_events(...)` returns a terminal event and the subsequent `read_job(...)` fails, the failure propagates to the caller.

## Non-actions

- Do not alter the accepted terminal fallback design: fallback event is yielded only to the consumer and is not written back to sidecar.
- Do not add locking or mutual exclusion between `wait_for_terminal(...)` and `stream_job_events_until_terminal(...)`.
- Do not expand S3 into CLI, Host, Engine, Fins runtime, adapter/runner protocol, or pipeline stream changes.

## Required Validation

- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py -q`
- `source .venv/bin/activate && python -m pyright dayu/service/fins_direct.py tests/service/test_fins_direct.py`
- `git diff --check`

## Controller Decision

S3 enters fix gate for `S3-FIX-01`, `S3-FIX-02`, and `S3-FIX-03`. After AgentCodex applies the focused fix and validation passes, run scoped re-review against these three accepted findings.
