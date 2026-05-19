# Phase 11 Slice 4 Code Review Controller Adjudication - 2026-05-19

## Scope

- Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening
- Slice: Slice 4 RECOVERING Cancel, Graceful Shutdown, And Public Contract Preservation
- Implementation artifact: `docs/reviews/phase11-slice4-implementation-codex-20260519.md`
- Review artifacts:
  - `docs/reviews/phase11-slice4-code-review-mimo-20260519.md`
  - `docs/reviews/phase11-slice4-code-review-ds-20260519.md`

## Verdict

进入 current fix pass。

两份 review 均为 PASS，blocking count = 0，high count = 0。Slice 4 的核心动机成立：`RECOVERING` 是 recovery dispatch 提交前的 durable recovery window，取消语义必须落在 Run-level facts，不应关闭旧 Attempt 或调用 WorkerProxy。实现与 `docs/host/design.md` §22 / §27 和 Phase 11 plan 一致。

## Accepted Current Fix Items

### S4-F1. `cancel_session_runs` unsupported error message stale

- Source: AgentDS M1
- Evidence: `dayu/host/admission.py` `_read_supported_targets_or_raise(...)` 的错误信息仍只列出 queued / pre-dispatch STARTING / active worker / WAITING，未包含 `RECOVERING`。
- Decision: accepted current fix.
- Rationale: 功能路径已支持 `RECOVERING`，错误信息作为 public-facing diagnostic 必须与当前 contract 保持一致。修复应只更新错误信息，不改变状态机或 supported target 判定。

### S4-F2. `released_active_slot=True` intent needs local clarification

- Source: AgentMiMo L1 / AgentDS L1
- Evidence: `dayu/host/admission.py` `_cancel_recovering(...)` 返回 `released_active_slot=True`。这里释放的是 session active slot / queue promotion eligibility，不是 active worker slot。
- Decision: accepted current fix as narrow comment/doc clarification.
- Rationale: 行为正确，不应改字段语义；但当前字段名容易被误读，局部注释可降低后续维护误判风险。

### S4-F3. Add `cancel_run` RECOVERING idempotency focused test

- Source: AgentDS L3
- Evidence: 当前新增测试覆盖 `cancel_run` RECOVERING facts、session-scope cancel 和 worker non-propagation，但没有 RECOVERING-specific `cancel_run` idempotency replay。
- Decision: accepted current fix.
- Rationale: 新增状态分支接入既有 idempotency scope，轻量测试可直接证明 `(run_id, client_request_id)` 未漂移，符合 Phase 11 plan 对 cancel idempotency scope 的 hardening 要求。

## No-action / Deferred Items

### S4-N1. Focused tests use direct DB transition into `RECOVERING`

- Source: AgentMiMo L2 / AgentDS L2
- Decision: accepted as current-slice no-action.
- Rationale: 这些测试目标是 public cancel semantics，不是 startup recovery creation path。Slice 2 / Slice 3 已覆盖 recovery scan / dispatch 创建路径；Slice 5 继续负责 multiprocess race hardening。当前 helper 不应膨胀成端到端 recovery setup。

## Required Fix Validation

Fix agent must run:

```bash
source .venv/bin/activate && pytest tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py tests/host/test_watch_session_events.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```

## Conclusion

Slice 4 不需要架构重开；进入 bounded current fix，修复 S4-F1 / S4-F2 / S4-F3 后回到 re-review。
