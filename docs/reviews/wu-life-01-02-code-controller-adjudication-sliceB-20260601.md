# WU-LIFE-01 + WU-LIFE-02 Slice B Code Review Controller Adjudication

日期：2026-06-01
总控：AgentController
当前 gate：code review slice B
Implementation artifact：docs/reviews/wu-life-01-02-implementation-sliceB-codex-20260601.md
Code reviews：
- docs/reviews/wu-life-01-02-code-review-sliceB-mimo-20260601.md
- docs/reviews/wu-life-01-02-code-review-sliceB-ds-20260601.md

## 裁决结论

Slice B code review 通过，无 accepted blocking finding。实现严格限定在 `tests/host/test_dispatch_scheduler.py`，未修改生产代码、schema、EventLog、Host public API、public cancel command 或 Run / Attempt 状态机。新增 tests-first 证据覆盖 scheduler close / `cancel_all` lifecycle matrix、close non-drain、lane wait、promotion non-drain、close cancellation retry cleanup 与 close 不写 terminal facts。

基于 design_doc 的 Host close lifecycle 目标和第一性原理，当前最佳实践是不进入 fix gate：review 提出的事项均为低风险维护观察，若为了它们继续修改会扩大测试与实现耦合，收益不足以抵消 churn。

## Finding 裁决

| ID | 来源 | 裁决 | 原因 |
|---|---|---|---|
| B-MIMO-01 | AgentMiMo | rejected | `_run_scheduler_drain_once` 是测试中为 `Task[None]` 形态提供类型清晰 wrapper，虽然语义很薄，但不影响 correctness，也不值得单独 churn。 |
| B-MIMO-02 | AgentMiMo | deferred-with-owner | worker-started-but-not-accepted window 确实未单独直接测试，但 plan 允许 deterministic fixture 不可得时 stop/report；当前 lane-wait 与 active-worker close tests 已覆盖相邻稳定窗口，后续若需要更细粒度 worker startup instrumentation，再由 future scheduler hardening owner 处理。 |
| B-DS-01 | AgentDS | rejected | `_SCHEDULER_CLOSE_REASON` 重复私有常量是测试对私有 close reason 的必要断言；生产常量未导出，当前不为测试常量引入 public export 或生产代码变更。 |
| B-DS-02 | AgentDS | rejected | close cancellation retry cleanup 需要验证 scheduler 内部 cleanup 状态；当前私有状态访问是 focused lifecycle test 的最小可行证据，不替换为更弱的外部观察。 |
| B-DS-03 | AgentDS | deferred-with-owner | `_SCHEDULER_CLOSE_TERMINAL_EVENT_TYPES` 需随未来 terminal event type 扩展同步维护；当前没有新增 EventLog terminal type，未来 schema/event type work unit 负责同步检查。 |
| B-DS-04 | AgentDS | rejected | `_RegisteringCancelHandle.cancel_reasons` 是测试 fake 自有观测字段，不改变 LocalWorkerHandle 协议；无需修复。 |

## Validation Required Before Commit

controller 需重新运行：

```bash
source .venv/bin/activate
pytest tests/host/test_dispatch_scheduler.py -q
pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_cancel_session_runs.py -q
python -m pyright dayu/ tests/ utils/
```

## Blocking Open Questions

none
