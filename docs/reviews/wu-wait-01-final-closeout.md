# WU-WAIT-01 Final Closeout

## Scope

- Work unit: WU-WAIT-01 / GitHub Issue #89
- Draft PR: https://github.com/noho/dayu-agent-r/pull/163
- Branch: `phase/wu-wait-01-issue-89`
- Base: `main`
- Accepted plan commit: `bf359ebb`
- Accepted Slice 1 commit: `6f919bb7`
- Accepted Slice 2 commit: `9d77e641`
- Accepted deepreview commit: `ab2a6997`
- Accepted PR review commit: `36eda549`
- Issue closeout comment: https://github.com/noho/dayu-agent-r/issues/89#issuecomment-4762516139

## Implemented Scope

- Added Host wait callback typed contract and adapter in `dayu.host.wait_callback`.
- Added command-layer callback port so callback completion enters the existing Host `resolve_wait` pipeline and preserves dispatch wakeup for non-replay completions.
- Centralized wait resolution digest material in `dayu.host.durable.wait_resolution_digest`, reused by callback and direct resolve paths.
- Added Service framework-neutral callback endpoint mapper in `dayu.service.wait_callback_endpoint`.
- Updated Host / Service / test READMEs and import-boundary tests for the new callback boundary.

## Callback Endpoint Delivery Form

The callback endpoint is provided as a framework-neutral mapper:

```text
handle_wait_callback_completion(request, adapter)
```

The caller supplies a `WaitCallbackHttpRequest` and an adapter implementing `WaitCallbackEndpointAdapter`. The mapper returns a `WaitCallbackHttpResponse`.

This WU intentionally does not register a real HTTP route and does not provide a secret backend, HMAC / bearer verifier, issue-90 poller, issue-92 physical cancel, Engine contract, or UI surface.

## Review Result

- Plan review / re-review: passed after accepted plan fixes.
- Slice 1 code review / re-review: passed after accepted fixes.
- Slice 2 code review / re-review: passed after accepted fixes.
- Aggregate deepreview: AgentMiMo and AgentDS both passed with no material finding.
- PR review: AgentMiMo and AgentDS both passed with no material finding.

## Final Validation

- `pytest tests/service/test_wait_callback_endpoint.py tests/service/test_import_boundary.py tests/service/test_weak_typing_guard.py -q` -> 47 passed.
- `pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q` -> 56 passed.
- `pyright` -> 0 errors.
- `git diff --check` -> passed.
- `gh pr checks 163` -> no checks reported on branch `phase/wu-wait-01-issue-89`.

## Residual Risk

Accepted non-blocking residual risks:

- Non-standard future endpoint adapters could raise through the Service mapper; current production adapter maps failures to typed callback results.
- Callback stale / late pre-read can race with later `resolve_wait`; current design deliberately collapses unresolved races into typed invalid-state behavior.
- Callback dispatch wakeup is owned by `HostCommandWaitCallbackPort`, while direct resolve wakeup remains owned by existing callers.
- Real route registration, secret verification, production polling, physical cancel, Engine contract, and UI integration remain explicit later-WU work.

## Final Gate

WU-WAIT-01 has reached final-closeout-pass locally. Draft PR #163 remains draft/open for user or maintainer handling. Do not mark ready, request reviewers, merge, close issue manually, or delete the branch without explicit authorization.
