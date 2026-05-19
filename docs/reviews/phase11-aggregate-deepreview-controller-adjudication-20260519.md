# Phase 11 Aggregate Deepreview Controller Adjudication - 2026-05-19

## Scope

- Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening
- Aggregate range: accepted plan commit `9223cbf` through accepted Slice 5 commit `4d32f66`
- Aggregate review artifacts:
  - `docs/reviews/phase11-aggregate-deepreview-mimo-20260519.md`
  - `docs/reviews/phase11-aggregate-deepreview-ds-20260519.md`

## Verdict

进入 aggregate fix pass。

两份 aggregate deepreview 均为 PASS，blocking count = 0，high count = 0。Phase 11 的核心 recovery truth source、positive orphan proof、CAS ordering、RECOVERING dispatch / cancel、startup scan、public API preservation、no Engine changes、no lease/fencing/takeover、runtime lane boundary、多进程 safety 和 projection lag non-truth 均通过审查。

## Accepted Current Fix Items

### P11-AGG-F1. Move RECOVERING cancel Run-row CAS to durable state boundary

- Source: AgentMiMo M1, controller code verification.
- Evidence: `dayu/host/durable/run_transition.py` 当前定义私有 `_cancel_recovering_run_row(...)` 并直接执行 `host_runs` SQL。虽然 `state.py` 尚无同名 helper，Phase 11 已在 `state.py` 中承载同类 Run row CAS owner（例如 `start_recovering_run_row(...)` / `terminal_recovering_run_row(...)`）。
- Decision: accepted current fix.
- Rationale: 功能正确但 ownership 不一致。把 row mutation helper 抽到 `dayu.host.durable.state`，让 `run_transition.py` 只编排 EventLog + state helper，可降低后续 CAS 分类逻辑漂移风险，符合“数据处理、存储、工具调用职责分离”和“重复逻辑必须抽取”。

### P11-AGG-F2. Document heartbeat interval vs stale threshold safety relationship

- Source: AgentDS M1.
- Evidence: `recovery.py` 默认 stale threshold 为 30s，dispatch heartbeat loop 当前 1s。两者行为正确，但缺少局部说明：heartbeat interval 必须显著小于 stale threshold，否则调参可能制造误判或 long recovery delay。
- Decision: accepted current fix as narrow comment/doc clarification.
- Rationale: 不改变 policy 值、不新增 public option；只在内部常量附近记录约束，避免后续调参破坏 positive orphan proof 假设。

## No-action / Deferred Items

- Pre-existing `dispatch.py` Engine import and dispatch module size are outside Phase 11 current fix. Phase 11 did not introduce or expand those dependencies.
- Runtime lane code未改但新增 race tests 通过；plan 的 "fix if reproduced" 条件未触发。
- Stdlib pid reuse fingerprinting remains deferred by Phase 11 plan. Current portable proof path correctly treats live pid without identity proof as inconclusive.
- WAITING recovery diagnostic-only EventLog is deferred to public lifecycle / wait observation owner. Current implementation does not create Attempt or mutate Run/Attempt state for WAITING, which preserves recovery safety.

## Required Fix Validation

Fix agent must run:

```bash
source .venv/bin/activate && pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py tests/host/test_public_cancel_session_runs.py -q
source .venv/bin/activate && pytest tests/host -q
source .venv/bin/activate && pytest tests/runtime -q
source .venv/bin/activate && python -m pyright dayu/host dayu/runtime tests/host tests/runtime
git diff --check
```

## Conclusion

Phase 11 aggregate review found no blocking correctness issue. The accepted aggregate fix is bounded to durable state ownership cleanup and internal policy documentation, then must return to aggregate re-review.
