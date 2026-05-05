# Engine Phase 0 Code Review

## 1. Review 结论

通过。

Phase 0 实施结果符合当前 `docs/engine/phase0-plan.md` 与最新契约归属范式：共享协作协议已落在 `dayu.contracts`，Engine 语义真源仍保留在 `dayu.engine.contracts`，`dayu.engine` 对公共契约的 re-export 是结构契约导出。当前实现未偷跑 Runner、Agent loop、ToolRegistry、doc/web/fins tools、processors，也未导出未实现的函数式入口或取消异常。

## 2. 阅读范围

实际阅读文件：

- `docs/engine/phase0-plan.md`
- `docs/engine/phase0-plan-review.md`
- `docs/engine/design.md`
- `AGENTS.md`
- `dayu/contracts/__init__.py`
- `dayu/contracts/cancellation.py`
- `dayu/contracts/json_value.py`
- `dayu/contracts/tool_await.py`
- `dayu/contracts/tool_call.py`
- `dayu/contracts/tool_executor.py`
- `dayu/contracts/tool_outcome.py`
- `dayu/contracts/tool_result.py`
- `dayu/contracts/tool_schema.py`
- `dayu/engine/__init__.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/contracts/agent_policy.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/finish_reason.py`
- `dayu/engine/contracts/messages.py`
- `dayu/engine/contracts/runner.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/runner_spec.py`
- `tests/contracts/test_package_exports.py`
- `tests/contracts/test_import_boundary.py`
- `tests/contracts/test_weak_typing_guard.py`
- `tests/contracts/test_protocols_surface.py`
- `tests/contracts/test_tool_outcome_exhaustive.py`
- `tests/contracts/test_tool_result_envelope.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_import_boundary.py`
- `tests/engine/test_weak_typing_guard.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_runner_event_contract.py`
- `tests/engine/test_metadata_boundary.py`
- `tests/engine/test_protocols_surface.py`
- `tests/engine/test_agent_message_union.py`

## 3. 验证结果

- `source .venv/bin/activate && pytest tests/contracts tests/engine -q`
  - 结果：通过，`43 passed in 0.07s`。
- `source .venv/bin/activate && pyright`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`。
  - 备注：pyright 仍提示 `utils` 目录不存在，并提示有新版本可用；命令退出码为 0。
- `git status --short`
  - 结果：
    - `M docs/engine/phase0-plan-review.md`
    - `M docs/engine/phase0-plan.md`
    - `?? dayu/`
    - `?? docs/engine/phase0-code-review.md`
    - `?? tests/`
  - 备注：`git status --short --ignored` 显示 `__pycache__` / `.pytest_cache` 等为 ignored，未进入普通提交范围。

## 4. 阻塞问题

无。

## 5. 重要问题

无。

## 6. 建议问题

无必须修改项。

提交前建议只确认 staging 范围不包含 ignored 生成文件，例如 `__pycache__`、`.pytest_cache`、`.DS_Store`。

## 7. 契约归属专项结论

- `dayu.contracts` 收纳范围是否正确？
  - 正确。`CancellationToken`、`ToolExecutor`、`ToolCallRequest`、`ToolExecutionRequest`、`ToolExecutionContext`、`ToolSchema`、`ToolResultEnvelope`、`ToolExecutionOutcome`、`ToolAwaitSpec`、`ToolAwaitSnapshot`、`JsonValue` 均在 `dayu.contracts`，符合 Host 与 Engine 双方产生 / 解释 / 持久化的层间协作协议定位。

- `dayu.engine.contracts` 保留范围是否正确？
  - 正确。`AgentMessage`、`RunnerSpec`、`RunnerCallOptions`、`AgentRunRequest`、`AgentPolicy`、`AgentRunResult`、`EngineEvent`、`RunnerEvent`、`AsyncRunner`、`FinishReason` 等仍在 `dayu.engine.contracts`，符合 Engine 语义真源定位。

- `RunnerSpec` 是否正确保留在 Engine 契约？
  - 是。`RunnerSpec` / `RunnerCallOptions` 描述 Engine 内 Runner 规约与调用参数，Host 只是装配并传入，不是 Host/Engine 双方独立解释的协作协议。

- `CancellationToken` 是否正确迁入公共契约？
  - 是。`CancellationToken` 位于 `dayu.contracts.cancellation`，`dayu.engine.contracts` 通过公共契约单向引用，符合 Host 产生 / Engine 观察的协作协议边界。

- 是否仍存在 `CancelledError` 或取消异常导出？
  - 未发现。`dayu.contracts.__all__` 与 `dayu.engine.__all__` 均不包含 `CancelledError`，测试也明确禁止该符号作为包属性访问。取消公共终态由 `RunCancelledData` / `EngineRunOutcomeCancelled` 表达。

- `dayu.engine` re-export `dayu.contracts` 是否只是结构契约导出？
  - 是。`dayu/engine/__init__.py` 的 docstring 明确说明 `dayu.contracts` 是源包，`dayu.engine` 只为 Engine 调用方提供单一 API surface；没有 wrapper / facade 方法体，也没有旧路径兼容语义。

## 8. 总体验收判断

- 是否建议进入总控验收？建议。
- 若不建议，必须先修哪些问题？不适用；当前无阻塞和重要问题。
