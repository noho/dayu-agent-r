# Gateflow Controller Adjudication: Host P5-S5 Active Cancel And Session-scope Cancel

## Metadata

- Controller: AgentController
- Date: 2026-05-15
- Gate: Host Phase 5 P5-S5 Active Cancel And Session-scope Cancel
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Implementation artifact: `docs/reviews/gateflow-implementation-host-p5-s5-active-cancel-session-scope-20260515.md`
- Fix artifact: `docs/reviews/gateflow-fix-host-p5-s5-active-cancel-session-scope-20260515.md`
- Code review artifacts:
  - `docs/reviews/gateflow-code-review-host-p5-s5-active-cancel-session-scope-mimo-20260515.md`
  - `docs/reviews/gateflow-code-review-host-p5-s5-active-cancel-session-scope-ds-20260515.md`
- Code re-review artifacts:
  - `docs/reviews/gateflow-code-re-review-host-p5-s5-active-cancel-session-scope-mimo-20260515.md`
  - `docs/reviews/gateflow-code-re-review-host-p5-s5-active-cancel-session-scope-ds-20260515.md`

## Controller Decision

Verdict: accepted.

P5-S5 is accepted after review fix and two independent re-reviews. The current workspace satisfies the P5-S5 plan scope:

- `cancel_run` now supports waiting-for-lane / pre-accept dispatching direct cancel and active worker cancel propagation.
- `cancel_session_runs` now covers queued, pre-worker, and active worker subsets with no partial mutation for `WAITING` / `RECOVERING`.
- Active worker cancel propagation is post-commit and best-effort through a process-local registry keyed by `(attempt_id, execution_id)` with `run_id` mismatch protection.
- Worker event stream is connected to `EngineEventIngestor`; terminal closeout now uses the scheduler as wakeup port so queued Run promotion can wake promoted dispatch.
- Tests no longer fake active worker state with an illegal `Attempt RUNNING` / dispatch `PENDING` combination.

## Finding Adjudication

| Finding | Source | Controller adjudication |
|---|---|---|
| Session cancel replay returns at most one active target | MiMo F1 / DS Finding 2 | Accepted as residual risk, not blocking. Current Host invariant allows at most one active Run per Session; multi-active replay requires a future semantic expansion. |
| EngineEventIngestor default noop wakeup port in scheduler path | MiMo F2 / controller review | Accepted and fixed. Scheduler now passes `wakeup_port=self` and implements `wake_queue_promotion`. |
| Active worker tests used naked SQL state mutation | DS Finding 1 | Accepted and fixed. Tests now use durable transition helpers for active worker accepted state. |
| Phase 4 stale cancel text | DS Finding 8 / controller review | Accepted and fixed in code and README scope. |
| `cancel_run` idempotent replay does not re-propagate active cancel | DS Finding 3 | Accepted as non-blocking residual risk. The plan only required session replay best-effort re-propagation; per-run replay propagation can be revisited with crash-recovery hardening. |
| Duplicate direct-cancel helper logic | MiMo F4 / DS observation | Deferred as non-blocking cleanup. It does not affect state-machine correctness. |
| `wake_queue_promotion` exceptions can propagate through worker event task | DS re-review observation | Accepted as residual risk. Worker `finally` still unregisters, closes handle, and releases lane token. Future lifecycle hardening may add diagnostic logging around wakeup failures. |

## Validation

Controller re-ran the required validation after the fix:

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q
```

Result: 22 passed.

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result: 0 errors, 0 warnings, 0 informations.

```bash
git diff --check
```

Result: passed.

## Residual Risks

- Active cancel watchdog remains out of P5-S5 scope. If a worker receives cancel but never emits a terminal event, the Run can remain `CANCELLING`.
- Session cancel replay still anchors re-propagation to the idempotency record's first active cancel event. This is acceptable under the current single-active-Run invariant; future multi-active semantics must redesign replay target truth.
- `cancel_run` idempotent replay does not re-propagate active cancel. This is a small commit-after / propagate-before crash window and is deferred to later lifecycle or recovery hardening.
- Scheduler wakeup failure during terminal promotion can surface as an async task error after durable terminal commit; cleanup `finally` still releases runtime resources. Future hardening can add diagnostic suppression around promotion wakeup.

## Next Gate

Proceed to P5-S5 accepted slice commit, then update `docs/host/implementation-control.md` checkpoint and enter P5-S6 Integration, Docs And Validation Closeout.
