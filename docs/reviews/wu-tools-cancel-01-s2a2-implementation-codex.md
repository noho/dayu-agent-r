# WU-TOOLS-CANCEL-01 S2A2 Implementation - Codex

## Verdict

READY_FOR_CODE_REVIEW

## Scope

本次 implementation gate 只实施 Host factory wiring：

- `ToolRuntime` 生产默认从 effective `ToolDefinition.execution` 选择 execution capsule。
- 保留 `ToolRuntimeBuildRequest.execution_capsule_factory` 作为 focused tests 的显式 override。
- process-backed 子进程 target factory 只接收 `ToolCallRequest` 与 `ProcessBackedToolContext`。
- Host capsule 继续通过 `InterruptibleProcessTarget -> JsonValue` 处理子进程结果，并在 Host 层解析工具 JSON 信封。

未迁移 Doc / Fins / Web 业务工具到 `process_backed`，未修改 Engine public contract、durable schema/migration 或 Host public cancel API。

## Changed Files

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_executor.py`
- `dayu/host/README.md`
- `docs/reviews/wu-tools-cancel-01-s2a2-implementation-codex.md`

## Behavior Summary

- 新增 `DeclaredToolExecutionCapsuleFactory`，持有 effective bundle 的 definition index，根据 `call.name` 读取 `ToolDefinition.execution`：
  - `AsyncDirectToolExecutionCapability` -> `AsyncDirectToolExecutionCapsule`
  - `ThreadBackedToolExecutionCapability` -> `ThreadBackedToolExecutionCapsule`
  - `ProcessBackedToolExecutionCapability` -> 调用声明内 target factory 构造 process target，再创建 `ProcessBackedToolExecutionCapsule`
- `DefaultToolRuntimeFactory` 在未显式注入 `execution_capsule_factory` 时使用 declaration-backed factory；显式注入仍优先，边界限定为 focused tests。
- `BatchToolExecutionContext` 到 `ProcessBackedToolContext` 的投影只包含 `run_id`、`session_id`、`iteration_id`、`timeout_seconds`、`correlation_id`。
- `ProcessBackedToolExecutionCapsule` 将子进程 `JsonValue` 信封解析为工具 outcome：
  - `{"status": "completed", "value": ...}` -> `ToolCompletedOutcome`
  - `{"status": "failed", "error_type": str, "message": str}` -> `ToolFailedOutcome`
  - malformed、unknown、`awaiting`、`cancelled`、`timeout`、`host_cancelled` -> fail closed
- 父进程 cancel / timeout 路径未转移给子进程信封，仍由 Host capsule 外层 interrupt / terminate / kill 治理。
- Host 内部重复的 `ToolExecutionMode` 真源收敛为 contracts 导入；未让 Engine 消费 execution capability。

## Tests / Pyright / Diff Check

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q`
  - `52 passed in 6.17s`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_effective_bundle.py tests/host/test_package_exports.py -q`
  - `20 passed in 0.27s`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed with no output

## README / Design Sync Decision

- `dayu/host/README.md` updated because `dayu/host/` behavior changed and the README owns current Host package execution boundaries.
- `tests/README.md` checked. No update needed: existing test layering already covers Host ToolRuntime executor focused tests and no new test directory or test layer was introduced.
- `docs/host/design.md` and `docs/engine/design.md` were used as design truth references; no design sync was required for this implementation slice because public architecture and Engine boundary did not change.

## Stop Conditions Checked

- No Host core branch by concrete business tool name.
- No Engine public request/event/runner contract change.
- No durable schema or migration change.
- No Host public cancel API change.
- No `dayu.runtime.interruptible_process` return type change.
- No runtime import of Host / Engine / Service / UI / Fins.
- No business tool import of Host internals.
- No raw dict / extra payload execution selector.
- No Doc / Fins / Web production tool migration in this slice.

## Residual Risks

- `thread_backed` remains only a wrapper-cancellation mode and cannot prove non-cooperative blocking production closeout; tests keep this guard explicit.
- S2B/S2C/S2D still need to migrate specific Doc / Fins / Web tools to `process_backed` or request-abort-capable async paths before #87 can be closed.
- process-backed target factories must remain careful not to capture repository/runtime/session/provider lock objects; S2A2 enforces the Host projection shape but cannot prove every future provider factory capture pattern.
