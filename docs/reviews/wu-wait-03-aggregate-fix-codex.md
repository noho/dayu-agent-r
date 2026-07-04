# WU-WAIT-03 Aggregate Fix Codex

## Scope

- Work unit: WU-WAIT-03 / GitHub Issue #92
- Gate: aggregate deepreview fix
- Source artifact: `docs/reviews/wu-wait-03-aggregate-deepreview-controller-adjudication.md`
- Accepted findings fixed:
  - `dayu/host/README.md` lacked the current Host wait external lifecycle adapter contract.
  - `tests/README.md` lacked current external lifecycle wait coverage notes.

## README Constraint Check

- `dayu/host/README.md`: read and followed its `Agent更新约束【必须遵守】`. The update stays inside current implemented Host package contract and stable waiting lifecycle semantics. It does not add work-unit history, future roadmap, installation guidance, or test checklist text.
- `tests/README.md`: read existing testing manual scope. The update only records current test-layer coverage already present under `tests/host/` and `tests/fins/`; it does not add WU process history.

## Changes

- Updated `dayu/host/README.md` Waiting section to document the implemented cancelled `WAITING` poller lifecycle adapter contract:
  - cancel command transaction writes Host durable wait / Run / Attempt facts only and does not execute provider I/O;
  - production wait poller later calls provider `abandon_wait` from the cancelled wait row path;
  - adapter lifecycle results are `WaitExternalJobLifecycleApplied`, `WaitExternalJobLifecycleUnsupported`, and `WaitExternalJobLifecycleNoop`;
  - Host poller persists bounded durable outcomes `abandoned`, `abandon_unsupported`, `abandon_noop`, or retry/error diagnostics;
  - Fins currently uses `ABANDON` as best-effort observation cancel / cleanup.
- Updated `tests/README.md` current coverage descriptions:
  - Host wait coverage now mentions cancelled wait lifecycle applied / unsupported / noop / error / missing-adapter / CAS / late-result / schema coverage.
  - Fins coverage now mentions observation cancel / abandon valid, corrupt, missing, LOST, non-transient, transient, prepared, submitted, and artifact preservation coverage.

## Validation

- `git diff --check` passed.

No production code, configuration, or test logic was changed, so tests and pyright were not required by the accepted fix scope.

## Finding Status

| Finding | Status |
|---|---|
| `dayu/host/README.md` wait external lifecycle adapter contract sync | fixed |
| `tests/README.md` external lifecycle wait coverage sync | fixed |

## Residual Risks

- Provider lifecycle cleanup remains best-effort and provider-specific; owner: future provider adapter work if stronger provider guarantees are needed.
- Poller-disabled deployments still do not execute external lifecycle adapter actions until production polling is configured; owner: deployment configuration.
- Future provider adapters that implement `CANCEL` or `REVOKE` may need more granular durable diagnostics if operators require action-level distinction; owner: future adapter/schema work.
