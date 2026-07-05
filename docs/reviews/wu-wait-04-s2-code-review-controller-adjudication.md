# WU-WAIT-04 S2 Code Review Controller Adjudication

## Reviewed Artifacts

- AgentDS: `docs/reviews/code-review-20260705-210415.md`
- AgentMiMo: `docs/reviews/code-review-20260705-210446.md`
- Implementation report: `docs/reviews/wu-wait-04-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-wait-04-s2-controller-validation.md`

## Review Summary

Both review agents concluded that S2 has no blocking findings.

- The smoke no longer imports `dayu.engine.agent` or `_AsyncAgent`.
- The smoke uses public Host / Service APIs for behavior assertions.
- `EngineEvent` is used only as the public `LocalWorkerHandle.events() -> AsyncIterator[EngineEvent]` protocol payload required by the public Host local worker contract.
- No durable wait row reads, dispatch row reads, scheduler internals, ToolRuntime internals, manual resolve, or test-private wait id bridges were found.
- Required validation passed: focused smoke, S1+S2 service tests, pyright, forbidden-path grep, weak-typing grep, and `git diff --check`.

## Findings Adjudication

### MiMo Observation 1: `_GatedReadyPollAdapter` uses `_OpaqueWaitInput`

- Severity from reviewer: Low.
- Controller decision: no fix required.
- Rationale: S2 intentionally does not import durable wait row types into the public-contract smoke. The adapter does not consume wait-record fields, and its parameter docstring states that the Host input is not inspected. This is consistent with the user constraint that the smoke can only use public contracts. Runtime and pyright validation both pass.

### MiMo Observation 2: `_AwaitingTool` class-level docstring is short

- Severity from reviewer: Low.
- Controller decision: no fix required.
- Rationale: AGENTS requires classes to provide a Chinese overview docstring; `_AwaitingTool` satisfies that. The callable contract is on `__call__`, whose docstring includes parameters, return value, and exceptions. No ambiguity affects maintainability or runtime behavior.

## Accepted Findings

None.

## Residual Risks

- S2 covers the production poller path, not callback resolution. This is intentional because the accepted plan identified no ordinary UI / Service public wait-id discovery contract for callback E2E.
- S2 uses deterministic tool and poll adapter fixtures rather than real Fins external systems. S1 and existing service assembly tests cover Fins poll adapter assembly.
- The smoke uses short poll intervals and bounded timeouts. The gate opens only after public WAITING activity and public Run snapshot confirmation, which reduces premature-resolution flake risk.

## Controller Decision

S2 code review gate passes. Proceed to accepted slice commit for WU-WAIT-04 S2.
