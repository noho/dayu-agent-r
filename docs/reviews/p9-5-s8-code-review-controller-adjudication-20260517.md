# P9.5 S8 Engine Wait Confirmation Matching-Ref — Controller Adjudication

## Gate

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR。
- Slice: S8 Engine Wait Confirmation Matching-Ref Hardening。
- Design source: `docs/host/design.md`。
- Control source: `docs/host/implementation-control.md`。
- Implementation artifact: `docs/reviews/p9-5-s8-engine-wait-confirmation-matching-ref-implementation-20260517.md`。
- Code review artifacts:
  - `docs/reviews/p9-5-s8-code-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s8-code-review-ds-20260517.md`

## Controller Judgment

Accepted。

S8 的动机成立：ToolRuntime Host accept path 是 awaiting canonical owner，Engine `TOOL_AWAITING` / `RUN_SUSPENDED` 只能作为 diagnostic confirmation。若 Host 仅凭 Engine event 或 `WAITING` / `SUSPENDED` 状态就确认，会弱化 `docs/host/design.md` 中 Host 对 wait record、Attempt closeout 与 EventLog facts 的强治理边界。

当前实现没有修改 Engine contract，也没有把 Host refs 塞进 Engine payload；而是在 `EngineEventIngestor` 的同一 Host transaction 内回读 durable accepted wait record 与 `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED` canonical refs，校验 envelope identity、wait id、event ref 链、Engine awaiting record 与 await spec 后才记为 confirmation。缺失或不匹配只写 diagnostic / rejection，不创建 wait record、不推进 Run `WAITING`、不关闭 Attempt、不追加 canonical tool fact。该路径符合 LocalProxy 当前语义，并保留未来 RemoteProxy 通过 envelope identity 做同源校验的空间。

## Review Findings

- AgentMiMo review：0 blocking findings，0 non-blocking findings。两个 info observation 分别为 mismatch reason 使用诊断字符串、canonical refs 回读较保守；均不影响 S8 目标。
- AgentDS review：0 blocking findings，0 non-blocking findings。Residual risks 指向未来多 active wait、未来事件顺序异常、Engine contract 不携带 Host refs、未来多 awaiting record 等范围变化；均不属于当前 S8 blocker。
- Controller 裁决：不需要 fix。当前实现以 fail-closed 方式处理 `RUN_SUSPENDED` 多 awaiting record，且 P9.5 / Phase 7 当前语义不支持同一 Run 多 active wait；相关风险继续由后续 phase 在语义扩展时重新设计。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_wait_awaiting_accept.py tests/host/test_phase7_waiting_integration.py tests/host/test_wait_cancel_late_result.py`：38 passed。
- `source .venv/bin/activate && pytest tests/host`：527 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`：0 errors。
- `git diff --check`：clean。
- Weak typing scan for S8 touched production/test files found no `Any` / `object` / `hasattr` / `getattr` usage.

## Residual Risk

- Engine contract 仍不携带 Host wait refs；这是本 slice 的刻意边界，不作为缺陷。Host confirmation 依赖 durable refs 回读。
- 当前实现依赖现有单 active wait record 不变量。若未来允许同一 Run 多 active wait，必须在对应 phase 重新设计 confirmation matching input 与 durable selection。
- RemoteProxy、callback endpoint、recovery、exactly-once remote delivery、external job physical cancel 仍归后续 phase / owner，不在 S8 实现。

## Final Decision

S8 accepted。可以提交 S8 implementation / review artifacts，并推进总控文档到 P9.5 S9。
