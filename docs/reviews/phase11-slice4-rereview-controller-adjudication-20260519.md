# Phase 11 Slice 4 Re-review Controller Adjudication - 2026-05-19

## Scope

- Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening
- Slice: Slice 4 RECOVERING Cancel, Graceful Shutdown, And Public Contract Preservation
- Fix artifact: `docs/reviews/phase11-slice4-fix-codex-20260519.md`
- Re-review artifacts:
  - `docs/reviews/phase11-slice4-rereview-mimo-20260519.md`
  - `docs/reviews/phase11-slice4-rereview-ds-20260519.md`

## Verdict

接受 Slice 4。

AgentMiMo 与 AgentDS re-review 均为 PASS。S4-F1 / S4-F2 / S4-F3 全部收口，无新增 blocker。

## Fix Verification

- S4-F1: `cancel_session_runs` unsupported diagnostic 已列出 `RECOVERING`，且未改变 supported target 判定。
- S4-F2: `_cancel_recovering(...)` 的 `released_active_slot=True` 已补局部注释，明确释放的是 session active slot / queue promotion 资格，不是 active worker cancel。
- S4-F3: 新增 RECOVERING `cancel_run` 幂等 focused test，验证同一 `(run_id, client_request_id)` 重放不追加第二组 `CANCEL_REQUESTED` / `RUN_CANCELLED`，同一 key 用于不同 `run_id` 时仍按 run scope 隔离。

## Validation

Controller local validation after fix:

```bash
source .venv/bin/activate && pytest tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py tests/host/test_watch_session_events.py -q
# 20 passed

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```

Review agent validation:

- AgentMiMo: PASS, no new blocker, focused tests / pyright / diff check passed.
- AgentDS: PASS, no new blocker, focused tests / pyright / diff check passed.

## Residual Risk Tracking

Focused tests that directly mark `RECOVERING` remain accepted as current-slice no-action. Recovery creation and dispatch paths are already covered by Slice 2 / Slice 3 tests; multiprocess race hardening remains Slice 5 owner.

## Conclusion

Phase 11 Slice 4 is accepted and may enter local commit.
