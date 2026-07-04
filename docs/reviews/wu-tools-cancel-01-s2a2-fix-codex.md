# WU-TOOLS-CANCEL-01 S2A2 Fix - Codex

## Verdict

READY_FOR_RE_REVIEW

## Scope

本次 fix gate 只处理 Controller 接受的 code review findings：

- F01：补 capsule build failure 完整 executor 链路测试。
- F02：修正 `DeclaredToolExecutionCapsuleFactory.create_capsule` docstring 的异常类型说明。
- F03：补 declaration-backed `async_direct` 与 `thread_backed` 默认路径集成测试。

未改生产行为，未进入 review gate，未 commit / push / PR。

## Changed Files

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_executor.py`
- `docs/reviews/wu-tools-cancel-01-s2a2-fix-codex.md`

## Fix Mapping

### F01

新增 `_RaisingCapsuleFactory` 和 `test_capsule_build_failure_bypasses_accept_barrier`：

- fake `create_capsule(...)` 抛出 `ValueError`。
- executor 返回 `ToolFailedOutcome`。
- `record.outcome.result.error == "tool_capsule_build_failed"`。
- `accept_port.candidates == []`，证明未进入 accept barrier。
- `callable_.call_count == 0`，证明未调用业务 callable。
- duplicate durable missing reason 分支当前不从 `_executor(...)` 测试边界暴露，未做直接断言；通过不进入 accept barrier 与返回原始 tool failure 覆盖 accepted finding 要求的可观测行为。

### F02

修正 `DeclaredToolExecutionCapsuleFactory.create_capsule` docstring：

- `ValueError`：工具声明缺失。
- `TypeError`：未知 execution capability。
- `Exception`：process target factory 构造目标失败时透传。

### F03

新增两个 declaration-backed 默认路径测试：

- `test_declared_async_direct_default_factory_calls_tool`：不注入 `execution_capsule_factory`，使用默认 `async_direct` 声明，验证 callable 正常调用并返回 accepted result。
- `test_declared_thread_backed_default_factory_calls_tool`：通过 `_executor(..., execution=ThreadBackedToolExecutionCapability())` 走 declaration-backed thread route，验证 callable 正常调用并返回 accepted result。

保留既有 `test_thread_backed_capsule_does_not_claim_thread_termination` guard，继续证明 `thread_backed` 不承诺停止 OS thread。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q`
  - `55 passed in 6.19s`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed with no output

## Stop Conditions Checked

- 未因测试需要修改生产行为。
- 未修改 Engine contract、runtime `JsonValue` 契约、durable schema、Host public cancel API。
- 未迁移 Doc / Fins / Web 业务工具。
- 未新增工具名分支、raw dict / extra payload execution selector 或业务工具对 Host internals 的依赖。

## Residual Risk

- MiMo finding 3 已由 Controller 裁决为 deferred/not required；本 fix 未新增 process envelope fail-closed executor wiring 测试。
- capsule build failure 的 duplicate durable missing reason 不在当前 focused test helper 的可观测边界内；本次用“不进入 accept barrier、不调用 callable、返回 tool failure”覆盖外部行为。
