# Phase 11 Aggregate Re-review Controller Adjudication - 2026-05-19

## Scope

- Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening
- Fix artifact: `docs/reviews/phase11-aggregate-fix-codex-20260519.md`
- Re-review artifacts:
  - `docs/reviews/phase11-aggregate-rereview-mimo-20260519.md`
  - `docs/reviews/phase11-aggregate-rereview-ds-20260519.md`

## Verdict

接受 Phase 11 aggregate fix。

AgentMiMo 与 AgentDS re-review 均为 PASS。P11-AGG-F1 / P11-AGG-F2 全部收口，未引入新 blocker。

## Fix Verification

- P11-AGG-F1: `cancel_recovering_run_row(...)` 已下沉到 `dayu.host.durable.state`，与 `start_recovering_run_row(...)` / `terminal_recovering_run_row(...)` 等同类 Run-row CAS helper 同边界；`run_transition.py` 不再直接引用 `TABLE_HOST_RUNS` 或私有 SQL helper。
- P11-AGG-F2: `recovery.py` 默认 stale threshold 常量旁已补 heartbeat interval 必须显著小于 stale threshold 的局部说明；不改变 policy 值或 public option。

## Validation

Controller local validation after fix:

```bash
source .venv/bin/activate && pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py tests/host/test_public_cancel_session_runs.py -q
# 50 passed

source .venv/bin/activate && pytest tests/host -q
# 793 passed, 1 skipped

source .venv/bin/activate && pytest tests/runtime -q
# 107 passed

source .venv/bin/activate && python -m pyright dayu/host dayu/runtime tests/host tests/runtime
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```

Review agent validation:

- AgentMiMo: PASS, focused tests / host tests / runtime tests / pyright / diff check passed.
- AgentDS: PASS, focused tests / host tests / runtime tests / pyright / diff check passed.

## Residual Risks

Residual risks remain as tracked in aggregate adjudication and phase plan: platform-specific pid fingerprinting, WAITING diagnostic EventLog hardening, production heartbeat/stale tuning, watch polling scale, and pre-existing dispatch module complexity. None blocks Phase 11 acceptance.

## Conclusion

Phase 11 aggregate gate is accepted. The work unit may enter accepted aggregate fix commit and then ready-to-open-draft-PR.
