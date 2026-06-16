# WU-CLI-FINS-OBS-01 S1 Code Review Adjudication

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S1-fins-job-event-contract`
- Gate: code review adjudication
- Implementation artifact: `docs/reviews/wu-cli-fins-obs-01-s1-implementation-codex.md`
- Code reviews:
  - `docs/reviews/code-review-20260615-183010.md` (AgentMiMo)
  - `docs/reviews/code-review-20260615-183203.md` (AgentDS)

## Decision Summary

S1 implementation direction is accepted, but this slice must enter fix before re-review.

Accepted fixes are limited to tests, public surface cleanup, and README sync. The performance finding is real but belongs to S2, where high-frequency `PROGRESS` events are introduced and the actual append volume can be validated.

## Finding Adjudication

| Finding | Decision | Reason | Required Action |
|---|---|---|---|
| MiMo-001: non-terminal event append failure WARN path not tested | accepted | The plan required warning-and-continue behavior for non-terminal event append failures; current test only forces terminal `JOB_SUCCEEDED` append failure. | Add a test forcing `JOB_QUEUED` or `JOB_RUNNING` append failure and assert job still reaches terminal state plus bounded WARN is emitted. |
| MiMo-002 / DS-F001: `_last_event_sequence_locked` reads full JSONL on every append | deferred-with-owner | The O(n) behavior is directly evidenced, but S1 emits only a small fixed number of status events. Optimizing tail reads now would add complexity before high-frequency progress behavior exists. | Owner: WU-CLI-FINS-OBS-01 S2. S2 must re-evaluate before introducing frequent `PROGRESS` events and either optimize sequence lookup or prove expected event volume is bounded. |
| MiMo-003: empty payload WARN logs `payload_keys=` | rejected-with-reason | This is log formatting polish with no correctness, stability, maintainability, or reviewability impact. Current bounded log is explicit and acceptable. | No action. |
| DS-F002: event types re-exported from `ingestion_runtime.__all__` | accepted | New re-export is not required for compatibility and creates two public import paths. Project constraints prefer avoiding re-export-only public surfaces. | Remove event types from `ingestion_runtime.__all__`; keep canonical imports from `dayu.fins.ingestion_events`. Verify tests/imports use the canonical module. |
| DS-F003: README sync not handled | accepted | `dayu/fins/` and `tests/` changed. The implemented S1 public event/read contract and tests should be reflected in the relevant README scope. | Update `dayu/fins/README.md` and `tests/README.md` according to each README's update constraints, writing only current landed facts. |

## Open Questions

None blocking after accepted fixes.

## Residual Risks / Owners

- Event sidecar sequence lookup scalability: deferred to WU-CLI-FINS-OBS-01 S2 before high-frequency progress events.
- S2 payload construction bugs being warned instead of failing fast: defer to S2 implementation review, because S1 only emits empty status payloads.
- Terminal event duplicate idempotency: no current duplicate path; defer as non-blocking defensive hardening unless S3 Service consumption requires stronger terminal de-duplication.

## Conclusion

Proceed to `fix` gate. AgentCodex should address only accepted findings above, update validation, and write a S1 fix artifact. No S2/S3/S4/S5 behavior should be implemented in this fix.
