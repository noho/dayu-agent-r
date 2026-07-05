# WU-TOOLS-CANCEL-01 Residual Hardening Plan Review Controller Adjudication

## Scope

- Work unit: WU-TOOLS-CANCEL-01 residual hardening reopen
- Gate: plan review / fix / re-review
- Plan artifact: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md`
- Review artifacts:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-review-ds.md`
  - `docs/reviews/plan-review-20260705-141254.md`
- Fix artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-rereview-ds.md`

## Controller Judgment

The plan goal is valid and the reopened scope is correctly bounded. The user reclassified five residual risks as current-WU must-fix items:

- process envelope hint structure;
- Playwright cleanup smoke;
- Fins XBRL fixture breadth;
- process envelope contract single-source;
- process capsule grace tuning.

Web process cold-start remains deferred as a performance item unless implementation evidence shows it weakens cancellation robustness.

## Review Findings

AgentMiMo initial review verdict was PASS with five findings:

- F01: Playwright cleanup reuse vs mirror was ambiguous.
- F02: grace defaults lacked tuning guidance.
- F03: NaN / infinity grace validation needed explicit tests.
- F04: POSIX process-group signaling race needed an explicit strategy.
- F05: runtime process cleanup and Playwright smoke should be split or constrained.

AgentDS initial review verdict was PASS with five findings:

- F1: policy wiring omitted `DeclaredToolExecutionCapsuleFactory`.
- F2: fake Playwright smoke overclaimed real browser cleanup proof.
- F3: grep guard only covered status constants, not all envelope constants.
- F4: `ProcessBackedToolTarget` docstring would become stale after adding `hint`.
- F5: Web cold-start and process-group cleanup interaction remains a future cold-start concern.

## Accepted Fixes

AgentCodex updated the plan to:

- choose a shared `dayu.runtime.interruptible_process` process-group primitive used by both `InterruptibleProcessHandle` and the Playwright raw process path;
- spell out policy wiring through `HostToolingOptions`, `ToolRuntimeBuildRequest`, `DefaultToolRuntimeFactory`, `DeclaredToolExecutionCapsuleFactory`, `_declared_capsule_for_execution`, and `ProcessBackedToolExecutionCapsule`;
- require removal of active hard-coded process capsule grace constants from ToolRuntime;
- make typed policy defaults the single source of default truth;
- require bool / negative / NaN / infinity rejection tests for grace policy and runtime validation;
- specify direct-PID-first then confirmed-pgid process-group signaling;
- limit deterministic Playwright smoke claims to synthetic nested-child cleanup unless live browser smoke runs;
- broaden envelope constant grep guard to all `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, and `_WEB_PROCESS_*` envelope constants;
- require `ProcessBackedToolTarget` docstring sync;
- split S2 into S2A runtime primitive and S2B Playwright cleanup smoke.

## Re-review Decision

- AgentMiMo re-review: PASS; F01-F05 all closed.
- AgentDS re-review: PASS; nine prior findings closed and one Web cold-start interaction item deferred-with-owner.

The deferred item is accepted as:

- Finding: Web cold-start plus process-group cleanup interaction may need future validation.
- Decision: deferred-with-owner.
- Owner / destination: future Web cold-start / performance hardening if S2B evidence shows survivor processes or unstable process-group ownership that weakens cancellation robustness.
- Current WU impact: not blocking because Web cold-start remains performance-only unless implementation evidence proves otherwise.

## Plan Acceptance

The updated plan is accepted as code-generation-ready.

Approved implementation slices:

- S1: Process Envelope Contract And Cleanup Policy.
- S2A: Runtime Process Group Cleanup Primitive.
- S2B: Playwright Cleanup Smoke.
- S3: Tool Migration And Fins AAPL XBRL Fixture Breadth.
- S4: Docs, Control State, And Final Validation.

No blocking open question remains for entering implementation.

