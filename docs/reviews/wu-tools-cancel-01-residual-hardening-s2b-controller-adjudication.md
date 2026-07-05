# WU-TOOLS-CANCEL-01 Residual Hardening S2B Controller Adjudication

## Scope

- Work unit: WU-TOOLS-CANCEL-01 residual hardening
- Slice: S2B `Playwright Cleanup Smoke`
- Branch: `phase/wu-tools-cancel-01`
- Controller decision: accept S2B implementation after fix and targeted re-review
- Implementation artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-code-review-ds.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-rereview-ds.md`

## Decision

PASS.

S2B is accepted as a completed implementation slice. Both AgentMiMo and AgentDS targeted re-review reports returned PASS after AgentCodex fixed the accepted findings.

## Accepted Findings And Closure

- Accepted finding: sync cleanup path used `asyncio.run()` directly and would fail if invoked from a thread with a running event loop.
  - Closure: `_interrupt_playwright_process_sync(...)` now uses the direct `asyncio.run(...)` path only when the current thread has no running event loop, and uses a helper thread bridge otherwise.
  - Evidence: `test_playwright_worker_process_cleanup_supports_running_event_loop`.

- Accepted finding: Playwright cleanup diagnostics were returned but production callers discarded them.
  - Closure: `_terminate_playwright_process(...)` now logs terminate/kill cleanup diagnostics at debug level in the Web backend cleanup owner.
  - Evidence: synthetic nested-child cleanup test asserts the diagnostic log contains `reason=group_signaled` and `group_signal_sent=True`.

- Accepted finding: S2B timing assertions referenced the Host process capsule policy default instead of Web's production cleanup grace.
  - Closure: S2B assertions now use Web backend production grace constants, while implementation evidence separately records measured cleanup timing against the S1 policy default.

- Accepted finding: optional live browser cleanup smoke was missing.
  - Closure: `test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort` is added behind `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`.
  - Evidence: AgentCodex reported the explicit live smoke passed in the current environment.

## Controller Validation

Controller reran validation before accepting the slice commit:

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q
source .venv/bin/activate && DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest tests/tools/web/test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort -q
source .venv/bin/activate && pyright
git diff --check
```

Results:

- `pytest tests/tools/web/test_web_tools_provider.py -q`: 33 passed, 1 skipped.
- `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest tests/tools/web/test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort -q`: 1 passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

## Residual Risk

- Real Chromium cleanup evidence is environment-dependent. S2B now has a manual live smoke and current-environment pass evidence, but the process tree shape can vary by OS and Chromium build.
- PID/PGID reuse is the same POSIX limitation already recorded by S2A. S2B does not expand that risk.
- Web process cold-start remains deferred as performance-only; no S2B evidence showed it weakens cancellation robustness.

## Next Entry Point

Proceed to residual hardening Slice S3 `Tool Migration And Fins AAPL XBRL Fixture Breadth` after the S2B accepted slice commit is created and pushed.
