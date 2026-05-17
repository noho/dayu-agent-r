# P9.5 S7 LocalProxy Close / Events Race — Controller Adjudication

## Gate

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR。
- Slice: S7 LocalProxy Close / Events Race。
- Design source: `docs/host/design.md`。
- Control source: `docs/host/implementation-control.md`。
- Implementation artifact: `docs/reviews/p9-5-s7-local-proxy-close-events-implementation-20260517.md`。
- Initial review artifacts:
  - `docs/reviews/p9-5-s7-code-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s7-code-review-ds-20260517.md`
- Fix artifact: `docs/reviews/p9-5-s7-fix-20260517.md`。
- Re-review artifacts:
  - `docs/reviews/p9-5-s7-code-re-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s7-code-re-review-ds-20260517.md`

## Controller Judgment

Accepted。

S7 的动机成立：默认 LocalProxy handle 位于 Host 到 Engine 的本地执行边界。若同一 handle 可重复打开 EngineEvent stream，或 close 与 active `anext()` 竞争时不能稳定关闭底层 Engine generator，会削弱 Host 对 worker 生命周期、取消传播和资源释放的强约束。这与 `docs/host/design.md` 中 Host 作为 Attempt Dispatch / EngineEvent Ingest 治理边界的目标直接相关。

当前实现把默认 LocalProxy event stream 收紧为 single-use，并通过 private stream wrapper 在 close 时取消活跃读取、关闭底层 Engine generator。该方案没有把 Host 状态泄漏给 Engine，没有引入 RemoteProxy、wire protocol、exactly-once delivery、recovery 或新的 public facade；scope 与 P9.5 hardening 目标匹配。

## Review Findings

- AgentMiMo 初审：0 blocking findings；F1 info observation 指出 active `anext()` task 在极窄竞争窗口以非取消异常完成时，`close()` 可能跳过 `aclose()`；F2 info observation 为 task exception retrieve 风险，生产 scheduler 会观察异常，不构成 blocker。
- AgentDS 初审：0 blocking findings；确认 S7 scope、single-use events、scheduler active cleanup、terminal 后 late event 不消费与 README 同步均通过。
- Controller 裁决：接受 MiMo F1 作为资源边界 hardening 修复项；F2 不升级，因生产消费路径会观察异常，且不影响 S7 目标。
- Fix：`_DefaultLocalWorkerEventStream.close()` 使用 `try/finally` 包裹 `_suppress_task_cancel(task)`，确保 active cancel 路径下底层 Engine generator `aclose()` 总会执行；非取消异常仍在 `aclose()` 后传播。
- AgentMiMo re-review：F1 fixed，0 new blocking findings。
- AgentDS re-review：F1 fixed，0 blocking findings，0 new issues。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_local_proxy_engine_ingest.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py`：49 passed。
- `source .venv/bin/activate && pytest tests/host`：521 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`：0 errors。
- `git diff --check`：clean。

## Residual Risk

- `_DefaultLocalWorkerHandle.cancel()` 仍是 best-effort no-op，本地执行取消依赖 scheduler cancel active task 与 handle close；这是 Phase 5 既有语义，S7 不扩大该能力。
- `_suppress_task_cancel` 在 Host 内仍有 private 重复实现。当前调用上下文类型不同且无第三处扩散；不作为本 slice blocker。若后续出现更多同类 runtime helper，再按层中立原则抽取到 `dayu.runtime`。

## Final Decision

S7 accepted。可以提交 S7 implementation / review / re-review artifacts，并推进总控文档到 P9.5 S8。
