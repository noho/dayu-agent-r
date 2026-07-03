# WU-WAIT-03 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: aggregate deepreview
- Review artifacts:
  - `docs/reviews/wu-wait-03-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-wait-03-aggregate-deepreview-ds.md`

## Controller Decision

Verdict: `fix-required`

Both aggregate reviews found no blocking correctness issue in Host lifecycle contract, durable schema, poller diagnostics, Fins adapter mapping, tests, layering, or state machine behavior. MiMo raised two low-severity README sync findings. The findings are current-scope and should be fixed narrowly because AGENTS.md requires README trigger checks after `dayu/host/` and `tests/` changes, and the affected READMEs already document the relevant developer-facing boundaries.

## Finding Adjudication

| Finding | Source | Decision | Required action |
|---|---|---|---|
| `tests/README.md` does not reflect external lifecycle wait test coverage | AgentMiMo F01 | accepted | Update `tests/README.md` without WU-specific process text. Add current-test-layer coverage for Host cancelled-wait lifecycle abandon diagnostics and Fins observation cancel / abandon runtime behavior. |
| `dayu/host/README.md` does not describe the new Host wait external lifecycle adapter contract | AgentMiMo F02 | accepted | Update `dayu/host/README.md` within existing section responsibilities. Describe stable wait adapter lifecycle result types and cancelled WAITING external job cleanup semantics without adding work-unit history or future roadmap. |
| `dayu.fins` imports `dayu.host` | AgentMiMo rejected finding | rejected-with-reason | Fins wait adapter already implements Host wait adapter protocols on `main`; WU-WAIT-03 only extends the existing adapter contract imports. This is not a new reverse dependency in the current WU. |
| unsupported/noop reason not stored in durable row | AgentDS F01 | informational | This is the accepted diagnostic granularity from the plan. Host durable truth stores bounded outcome categories; adapter-specific reason remains runtime diagnostic, not current persistent schema truth. |
| `CANCEL` / `REVOKE` actions have no provider implementation or dedicated test | AgentDS F02 | informational | Current Fins adapter returns `ABANDON`; `CANCEL` / `REVOKE` are contract vocabulary for future provider-specific adapters. No current behavior depends on them. |

## Required Fix Validation

After the README fix, run:

```bash
git diff --check
```

No code or behavior should change. Re-run tests or pyright only if the fix touches code, configuration, or test logic.

## Residual Risks

- Provider lifecycle cleanup remains best-effort and provider-specific.
- Poller-disabled deployments will not execute external lifecycle adapter actions until production polling is configured.
- Future provider adapters that implement `CANCEL` or `REVOKE` may need more granular durable diagnostics if operators require action-level distinction.
