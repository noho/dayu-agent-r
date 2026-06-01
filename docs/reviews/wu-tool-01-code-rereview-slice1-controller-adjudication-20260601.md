# WU-TOOL-01 Slice 1 Code Re-review Controller Adjudication

## Gate

- Work unit: WU-TOOL-01 Duplicate Governance Concurrency and Cross-attempt Semantics
- Slice: Slice 1 - Typed Policy And Attempt-scoped Duplicate State
- Gate: code re-review
- Controller role: adjudication only；不直接实施 specialist code change。

## Inputs

- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Implementation report: `docs/reviews/wu-tool-01-implementation-slice1-codex-20260601.md`
- First code review:
  - `docs/reviews/wu-tool-01-code-review-slice1-mimo-20260601.md`
  - `docs/reviews/wu-tool-01-code-review-slice1-ds-20260601.md`
- Controller first review adjudication: `docs/reviews/wu-tool-01-code-review-slice1-controller-adjudication-20260601.md`
- Fix report: `docs/reviews/wu-tool-01-fix-slice1-codex-20260601.md`
- Code re-review:
  - `docs/reviews/wu-tool-01-code-rereview-slice1-mimo-20260601.md`
  - `docs/reviews/wu-tool-01-code-rereview-slice1-ds-20260601.md`

## Adjudication

CR1 至 CR6 全部关闭，Slice 1 code re-review 通过。

- CR1: `tool_runtime.py` 不再通过 `__all__` 重新导出 duplicate governance typed contracts；真源为 `dayu.host.tool_duplicate_governance`。
- CR2: run-scoped duplicate registry protocol/class 与 dispatch 持有的 registry lifecycle 已删除，dispatch 测试不再依赖 `_duplicate_governance_registry`。
- CR3: `DuplicateGovernancePort` 已迁移到 `dayu.host.tool_duplicate_governance`。
- CR4: 已增加 owner cancellation 下的同 Attempt 并发 duplicate durable-missing 行为测试。
- CR5: accept timeout / durable-missing 路径测试已强化，断言 waiter 不执行第二次真实工具调用。
- CR6: hardcoded `_duplicate_message()` fallback 已删除，duplicate message 来自 typed policy messages。

## Deferred Items

- `tool_trace.py` 的 `duplicate_scope` 透传属于 approved plan Slice 3，当前 Slice 1 不关闭。
- awaiting fanout 的更宽并发治理风险没有形成当前 duplicate state 的直接失败证据，按 future WU-TOOL awaiting hardening deferred-with-owner 追踪。
- `test_reactive_recovery_does_not_clear_duplicate_registry` 的测试名残留旧术语，但测试体已不再访问 registry；该命名清理由 Slice 2 的 dispatch behavior 改写负责。
- README 同步按 approved plan Slice 4 处理，Slice 1 不提前改写稳定文档。

## Controller Verification

Controller 在 re-review 后补跑本地验证：

```bash
source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_duplicate_governance.py
source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py
source .venv/bin/activate && pyright
```

结果：

- `tests/host/test_toolruntime_duplicate_governance.py`: 26 passed
- `tests/host/test_dispatch_scheduler.py`: 57 passed
- `pyright`: 0 errors, 0 warnings, 0 informations

## Decision

Slice 1 达到 accepted slice checkpoint，可提交本地 accepted commit，并进入 Slice 2 handoff。
