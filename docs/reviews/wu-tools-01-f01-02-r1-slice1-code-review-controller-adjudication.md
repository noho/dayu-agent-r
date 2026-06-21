# WU-TOOLS-01-F01-02-R1 Slice 1 Code Review Controller Adjudication

## Scope

- work unit: `WU-TOOLS-01-F01-02-R1`
- slice: Slice 1 `Host accepted-wait activation hook`
- gate: code review
- base checkpoint: `6c930566`
- accepted plan commit: `478f5f77`
- implementation artifact: `docs/reviews/wu-tools-01-f01-02-r1-slice1-implementation-codex.md`
- review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-ds.md`

## Review Summary

- AgentMiMo conclusion: `pass`; no substantive findings.
- AgentDS conclusion: `pass`; three low-severity findings / residual risks.
- Controller conclusion: Slice 1 implementation is directionally correct, but should enter a small code-review fix pass before accepted slice commit.

## Adjudication

### CR-F01 accepted: cancel-after-accept-before-activation guard lacks direct regression coverage

The production code has the correct second cancellation gate after `ToolAwaitingAcceptedAck`, but the current pre-cancelled test does not prove the accepted-then-cancelled interleaving. This is a small test gap and directly relates to the accepted plan requirement that activation and cancellation ordering be explicit.

Required fix:

- Add a focused test proving that when cancellation becomes true after awaiting accept has returned but before activation, activation is not called.
- Keep the test local to the existing Host ToolRuntime test harness. Do not introduce a new scheduler, lifecycle abstraction, or broad concurrency framework.

### CR-F02 accepted: activation failure warning should not log raw exception payload

The diagnostic path is already bounded, but `_LOGGER.warning(..., exc_info=True)` can include the raw exception message in logs. Because activation adapters may wrap provider/job errors, the minimal safer behavior is to log only bounded metadata for this specific best-effort activation failure.

Required fix:

- Remove traceback/raw exception logging from the wait activation failure warning.
- Preserve bounded metadata such as exception class, session, run, attempt, tool name, and adapter key.
- Add or update a focused assertion if practical so a raw provider-like exception message is not emitted by this activation failure path.

### CR-F03 accepted: `WaitActivationRequest` defensive validation lacks direct tests

The defensive validation is simple and not expected to fire in the normal ToolRuntime path, but the branches are new public Host-internal contract checks and are cheap to cover.

Required fix:

- Add focused tests for empty `tool_name` and invalid `await_spec` raising `ValueError`.
- Do not expand the runtime contract or add compatibility behavior.

### CR-F04 deferred-with-owner: Fins adapter must not leak Host governance ack fields

AgentDS raised an open question about `ToolAwaitingAcceptedAck` being available to later Fins activation adapters. The Host-defined activation request intentionally carries accepted-wait ack material so adapters can bind activation to durable Host truth. The leakage risk belongs to Slice 2 / Slice 3 implementation: Fins must not write Host governance identifiers into LLM-facing output, observation business facts, or user-visible conclusions unless explicitly required and self-explained.

Owner:

- Later WU-TOOLS-01-F01-02-R1 Fins / Service slices.

## Next Gate

Enter code-review fix gate for Slice 1. AgentCodex should implement only CR-F01, CR-F02, and CR-F03, update the implementation/fix artifact, run the focused Host test and pyright, then return for re-review.
