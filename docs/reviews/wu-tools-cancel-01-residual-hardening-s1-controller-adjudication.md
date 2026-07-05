# WU-TOOLS-CANCEL-01 Residual Hardening S1 Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-CANCEL-01`
- Gate: implementation / code review / fix / re-review
- Slice: S1 `Process Envelope Contract And Cleanup Policy`
- Branch: `phase/wu-tools-cancel-01`
- PR: draft/open `#170`

## Evidence

- Implementation artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-implementation-codex.md`
- Initial code review:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-code-review-ds.md`
- Targeted re-review:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-rereview-ds.md`

## Findings Adjudication

| Finding | Source | Decision | Rationale |
|---|---|---|---|
| `InterruptibleProcessHandle.close()` hardcoded close grace | AgentMiMo F01 / AgentDS 01 | fixed | Runtime close now accepts `kill_grace_seconds` with a runtime-local named default, and `ProcessBackedToolExecutionCapsule.close()` passes `ProcessCapsuleInterruptPolicy.kill_grace_seconds`. Host close / terminate / kill cleanup paths now use the same Host policy value. |
| Host-layer non-string `hint` malformed regression test missing | AgentMiMo F02 | fixed | Host executor tests now cover failed process envelope with non-string `hint` and assert `process_backed_tool_malformed_envelope`. |

## Controller Decision

S1 is accepted for slice commit.

S1 establishes the process-backed envelope contract in `dayu.contracts`, switches Host parsing to the contract parser, maps failed-envelope `hint` into `ToolResultFailure.hint`, adds typed cleanup grace policy wiring from Host construction inputs to process-backed capsule cleanup paths, keeps runtime/config layering intact, and validates bool / negative / NaN / infinity rejection in Host policy, runtime config, and runtime process cleanup boundaries.

The default package `dayu/config/host_runtime.json` intentionally does not duplicate the `0.2` / `0.2` policy defaults. Missing config remains valid and falls through to typed constructors, preserving the typed policy as the Host default source of truth.

## Residual Risk

- S2A/S2B still own process-group cleanup primitive and Playwright cleanup smoke.
- S3 still owns Doc / Fins / Web concrete tool migration to contract helpers and the AAPL XBRL fixture breadth.
- Web process cold-start remains deferred as performance-only unless S2B evidence shows a cancellation robustness impact.
