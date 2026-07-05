# WU-TOOLS-CANCEL-01 Plan Review Controller Adjudication

## Scope

- Work unit: WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening
- Gate: plan review
- Plan artifact: `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md`
- Review artifacts:
  - `docs/reviews/wu-tools-cancel-01-plan-review-ds.md`
  - `docs/reviews/wu-tools-cancel-01-plan-review-mimo.md`

## Verdict

Plan direction is accepted, but implementation must not start yet. Plan fix is required before accepted plan commit.

## Adjudicated Findings

| Finding | Source | Decision | Rationale | Required Fix |
|---|---|---|---|---|
| F1 worker stream interruption mechanism unspecified | AgentDS | accepted | `LocalWorkerHandle.on_cancel(...)` is currently no-op, and `_consume_worker_events(...)` has materially different paths for `StopAsyncIteration`, `CancelledError`, and generic exceptions. Slice S1 cannot be code-generation-ready unless the default local worker interruption path is specified. | Plan must choose the default mechanism and define the propagation / suppression expectation. Preferred fix: `on_cancel(...)` calls the event stream `close()` path, which cancels active `anext`, closes the generator, is idempotent, and lets dispatch cleanup run in `finally`. |
| F2 process-backed capsule feasibility per tool path not assessed | AgentDS | accepted | The work unit cannot close issue-87 if the production tool families remain on non-interruptible `asyncio.to_thread(...)` or non-picklable process migration shapes. S1/S2 need a feasibility decision framework before implementation. | Plan must add a pre-migration feasibility matrix for doc / fins / web / Playwright paths and define fallback strategies such as process entrypoint refactor, async request abort, or explicit design stop. |
| 001 capsule execution mode not distinguished | AgentMiMo | accepted, merged into F2 | This is the same root issue as F2 at the contract level: thread-backed and process-backed capsules cannot share the same termination guarantee. | Plan must define typed execution modes and per-mode interrupt semantics. |
| F3 bounded close timeout value and configuration unspecified | AgentDS | accepted as non-blocking plan fix | Cleanup grace is not a second cancel timeout, but an unspecified value can still damage Esc responsiveness. | Plan must state a small bounded cleanup grace policy and forbid deriving it by extending `tool_execution_timeout_seconds`. |
| F4 Slice 3 public smoke lacks non-cooperative blocking fixture + new input progress | AgentDS | accepted as non-blocking plan fix | Public UX validation must prove the actual issue-87 closeout scenario, not only cooperative cancellation. | Plan must require a public or Host-public smoke using a non-cooperative blocking fixture where Run B progresses after Run A cancel. |
| F5 `dayu.contracts` modification ambiguity | AgentDS | accepted as non-blocking plan fix | Public/shared contract changes cannot be left as vague "maybe" language. | Plan must explicitly default to no `dayu.contracts` change unless S1 proves provider declarations are necessary, in which case implementation stops for design/contract update. |
| F6 cooperative async path regression coverage missing | AgentDS | accepted as non-blocking plan fix | Capsule integration must preserve existing pure async tool behavior. | Plan validation matrix must include cooperative async path regression tests. |
| 002 S2 migration scope may be underestimated | AgentMiMo | accepted as non-blocking plan fix | The 3-slice structure remains acceptable, but S2 needs a per-tool-family assessment step to keep reviewable scope. | Plan must require the S2 implementation report to include per-tool-family migration assessment and stop/defer classification. |
| 003 async HTTP abort path not explicitly covered | AgentMiMo | accepted as non-blocking plan fix | Async HTTP is not the main blocking-I/O root cause, but cancellation cleanup must be unambiguous. | Plan must clarify whether async HTTP uses `async_direct` capsule semantics or a parallel adapter abort hook, with response/client cleanup validation. |

## Slice Decision

The three-slice structure is retained:

- S1 remains the runtime boundary and local worker cleanup slice.
- S2 remains the production tool/provider migration slice.
- S3 remains the public interrupt UX and closeout validation slice.

The fix must strengthen S1/S2 entry and stop conditions rather than split the work mechanically by module.

## Next Gate

Move to plan fix gate. AgentCodex should update only the plan artifact unless it finds direct evidence that a design-source update is required before implementation.
