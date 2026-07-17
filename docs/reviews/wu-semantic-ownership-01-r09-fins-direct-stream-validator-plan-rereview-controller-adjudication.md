# WU-SEMANTIC-OWNERSHIP-01 R09 Fixed-Plan Re-Review Controller Adjudication

## 0. Identity and decision

- Umbrella: `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation.
- Internal sub-WU: `R09 — Fins direct-stream terminal validator`.
- Immutable fixed plan SHA-256: `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`, 773 lines.
- AgentMiMo re-review: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-mimo.md`, SHA-256 `4ac97bdca9fdb1e54f9e59c374c3667159ed72eafa4e08898583742949fb45fc`, 426 lines.
- AgentDS re-review: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-ds.md`, SHA-256 `ad7f5e4168ff02e80c765c1e2c00f33b0010206fb6e79dddb2545a9f6388a9fa`, 420 lines.
- Controller decision: `ACCEPTED_PLAN / EXACT_SCOPE_LOCAL_COMMIT_AUTHORIZED`.
- Implementation state before that local commit: `NOT_AUTHORIZED`.

Controller 已完整读取两份 re-review。两路都重新核对整份 plan、current code signatures、source locks、状态机、producer/queue 边界、Service/CLI provenance、README、安全、coverage/type/lint/scans/smoke与 deferred scope，而非只读 plan-fix diff。

## 1. Prior accepted finding closure

| Finding | MiMo | DS | Controller final disposition |
|---|---|---|---|
| `R09-PR-F01` exact signature/call-site cutover | closed | closed | `closed` |
| `R09-PR-F02` primary semantic error / cleanup close / idempotence | closed | closed | `closed` |
| `R09-PR-F03` remove speculative producer protocol-error channel | closed | closed | `closed` |
| `R09-PR-F04` terminal-result availability contract | closed | closed | `closed` |
| `R09-PR-F05` retain existing CLI presentation and README decision | closed | closed | `closed` |
| `R09-PR-F06` Fins operation-kind/error provenance propagation | closed | closed | `closed` |

No prior accepted finding remains open or deferred.

## 2. New finding adjudication

- AgentMiMo new finding ledger: zero.
- AgentDS new finding ledger: zero.
- Controller accepted new finding: zero.
- Controller rejected-with-reason new finding: zero.
- Needs-more-evidence finding: zero.
- Blocker: zero.

Reviewer observations about the large ingestion runtime coverage baseline, real SEC/Docling environment, control transition hash and remaining R10-R12 are already assigned gate/external facts, not R09 plan defects and not waivers.

## 3. Final architecture and scope decision

- The plan has one semantic owner: `dayu.fins.direct_stream.ValidatedFinsEventStream` decides exactly-one-and-last RESULT and terminal availability.
- Ingestion runtime owns raw producer/queue composition; Service returns the same typed stream; CLI consumes it and keeps the existing human-readable error projection.
- Runtime public stream methods become plain `def`; raw bridge remains an async generator; Service/CLI do not acquire coroutine or validation ownership.
- Producer queue union and generic execution-exception-to-bounded-business-failure RESULT remain unchanged; no source-less defensive protocol-error channel exists.
- Error/cancellation identity remains primary, cleanup close failure is chained, raw close is attempted at most once, and terminal-result early access is a Fins-owned ordinary RuntimeError contract.
- No compatibility wrapper, fallback, loose parsing, second validator, public error framework, unified tool authorization framework, Topic 8 change, R10-R12 implementation or deferred Issue work is accepted.

## 4. Validation and risk decision

- Plan target and both reviewer artifact hashes/line counts match.
- `git diff --check` passes and staged tree was empty at review completion.
- Full implementation validation remains mandatory: affected tests, R06/R08/full Fins regression, per-changed-file coverage `>=80.00%`, full pyright zero, scoped Ruff, source/propagation scans, README synchronization and real download/process/upload smoke.
- `DS-N03` does not authorize partial coverage or unrelated code changes. A real failure stops at Controller.
- SEC/Docling environment failures remain R09 completion blockers, not residual waivers.
- Issue 175 continues to own physical interruption/process isolation outside R09.

## 5. Accepted-plan commit scope

The local accepted-plan commit is authorized for exactly these eleven paths:

1. `docs/host/issues-implementation-control.md`
2. `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`
3. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-entry-controller-validation.md`
4. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-mimo.md`
5. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-ds.md`
6. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-controller-adjudication.md`
7. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-codex.md`
8. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-controller-validation.md`
9. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-mimo.md`
10. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-ds.md`
11. `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-controller-adjudication.md`

No product, test, README, design, prior R01-R08 artifact or unrelated path is authorized. Commit-time audit must verify exactly eleven staged paths, no unstaged/untracked path outside the known R09 set is absorbed, staged `git diff --check` passes and HEAD remains R08 completion commit `a31ded764da0621b6e7a6c7c6a083b4bb6593d21`.

## 6. Next gate

After the exact-scope local commit succeeds, Controller must record its full SHA, parent/tree/path manifest, revalidate source locks and issue a separate R09 implementation authorization. Implementation then begins with cumulative S1 Fins owner checkpoint followed by S2 Service/CLI mechanical cutover; S1 is not independently accepted or committed.

Final decision: `R09 PLAN ACCEPTED / LOCAL COMMIT AUTHORIZED / IMPLEMENTATION WAITS FOR COMMIT AND CONTROLLER ENTRY AUTHORIZATION`.
