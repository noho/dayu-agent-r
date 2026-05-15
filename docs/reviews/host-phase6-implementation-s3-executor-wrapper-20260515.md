# Host Phase 6 P6-S3 Implementation Artifact

- **gate**: Gateflow implementation
- **work unit**: Host Phase 6 ToolRuntime
- **slice**: P6-S3 - ToolExecutor Wrapper, Ack Retry, Side-effect Policy, Awaiting Guard
- **approved plan**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`
- **artifact path**: `docs/reviews/host-phase6-implementation-s3-executor-wrapper-20260515.md`

## Motivation Judgment

动机成立，严重性评估未被高估。P6-S1 / P6-S2 已经建立 effective `ToolBundle` 同源投影与 Host accept barrier，但 `ToolRuntimeHandle.tool_executor` 仍无法执行真实业务工具。若不在 P6-S3 固定 executor wrapper、accepted ack barrier、rejected / timeout fallback、side-effect 幂等 key guard 与 awaiting unsupported guard，Engine 可能消费未被 Host durable accepted 的工具结果，或让 replay / no-tool 范围绕过 Host 工具治理。

## Scope And Non-goals

本 slice 只实现 P6-S3 指定范围：

- `ToolRuntimeExecutor.execute`
- callable lookup / async invocation / exception normalization
- pass-through duplicate governance allow stub
- bounded accept retry
- rejected / timeout governed error fallback
- side-effect / paid missing idempotency key pre-call guard
- awaiting unsupported guard
- direct ToolRuntime / Engine integration tests

未实现 `fetch_more`、truncation / cursor、完整 duplicate matrix、Remote wire protocol、durable table、Engine public contract 变更、wait record、`WAITING`、recovery 或业务工具发现。

## Changed Files

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_phase6_toolruntime_integration.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/host-phase6-implementation-s3-executor-wrapper-20260515.md`

## Implemented Items

- `DefaultToolRuntimeFactory` 在提供 `ToolRuntimeExecutionScope` 与 `HostToolFactAcceptPort` 时创建真实 `ToolRuntimeExecutor`；缺少 accept barrier 时仍不会执行业务 callable。
- `ToolRuntimeExecutor` 对批内 call 按输入顺序执行 policy、duplicate allow stub、dispatcher、awaiting normalization、truncation no-op、Host accept retry；只有 accepted ack 后返回原 outcome。
- `DefaultToolDispatcher` 从同一个 `EffectiveToolBundle` 查找 callable 并执行，未知工具或 callable 异常归一为 `ToolFailedOutcome`。
- `ToolRuntimePolicyView` / `ToolRuntimeToolPolicy` 提供 Host 内部 side-effect / paid 工具幂等 key 参数绑定；缺失 key 时不调用 callable。
- `ToolFactRejectedAck` 与 `ToolFactAcceptTimedOut` 均返回 governed `ToolFailedOutcome`，不暴露 raw result。
- `ToolAwaitingOutcome` 映射为 `ToolFactKind.GOVERNED_ERROR`，policy reason 为 `unsupported_awaiting`。
- 新增 direct executor tests 覆盖 accepted ack、rejected ack、timeout retry、side-effect guard、awaiting guard、no-tool scope、mixed batch。
- 新增集成测试覆盖 Engine 第一轮 tool call 经 ToolRuntime durable accepted 后进入第二轮 continuation。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_phase5_local_execution_integration.py -q`
  - Result: PASS, `17 passed`.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: PASS, `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: PASS.

## Docs Decision

已按触发规则更新：

- `dayu/host/README.md`：同步当前 Host-owned ToolRuntime executor、accept barrier、timeout / rejected 行为、side-effect guard、awaiting unsupported boundary。
- `tests/README.md`：同步新增 Host ToolRuntime executor / Phase 6 integration 测试入口与覆盖范围。

## Residual Risks

- P6-S3 duplicate governance 是 pass-through allow stub，完整 duplicate matrix 由 P6-S5 接管。
- P6-S3 truncation port 是 no-op；结果截断、cursor 与 `fetch_more` 由 P6-S4 接管。
- 本 slice 没有改 Remote transport；远端等价 ack 语义仍是后续 phase owner。
