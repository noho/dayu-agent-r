# Host Phase 6 P6-S4 Implementation: TruncationManager And fetch_more Normal Tool Path

- **gate**: Phase 6 P6-S4 implementation
- **work unit**: ToolRuntime / Truncation / fetch_more
- **approved plan**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`
- **scope**: 仅实现 P6-S4 run-scoped truncation 与普通 framework tool `fetch_more`
- **artifact status**: implementation complete

## 动机判断

动机成立，严重性没有被高估。P6-S1 到 P6-S3 已把 schema projection、callable dispatch、ToolExecutor wrapper 与 Host accept barrier 固定为同一治理路径；若 P6-S4 让 `fetch_more` 走 Host / Engine 特化分支，或让 RunInputBuilder 与 dispatcher 使用不同工具真源，会破坏 `LLM in the loop` 的 Host 强约束边界。

## 实施边界

本 slice 遵守以下 non-goals：

- 未新增 durable cursor table / descriptor。
- 未实现跨 Run、跨 Session、restart、recovery、replay 或 memory retrieval 后续读。
- 未修改 Engine public contracts、Remote wire protocol、Service、UI 或 Fins。
- 未实现 duplicate governance matrix 或 wait / resolve_wait 能力。

## 改动文件

- `dayu/host/tool_runtime.py`
  - 新增 `TruncatedRemainderRef` 严格 dataclass union、`ToolTruncationCursor`、`FetchMoreRequest` / `FetchMoreResult`。
  - 新增 run-scoped `TruncationManager`，从同一个 `EffectiveToolBundle.truncate_specs_by_name` 接收截断声明。
  - 对支持的 `ToolCompletedOutcome` 应用 `ToolTruncateSpec`，返回带 opaque cursor 与 scope token 的普通 completed outcome，并在 accept candidate 写入 `ToolTruncationFact`。
  - 新增 `FetchMoreToolCallable`，作为普通 framework tool callable 通过 `DefaultToolDispatcher` 执行。
  - `EffectiveToolBundleBuilder` 在 `FETCH_MORE` policy 启用且 truncation manager enabled 时注入名为 `fetch_more` 的 `ToolDefinition`。
  - cursor 校验覆盖 run scope、scope token digest、TTL、single-use、missing cursor 与 remainder digest mismatch，失败均返回普通 `ToolFailedOutcome`。
- `tests/host/test_toolruntime_truncation_fetch_more.py`
  - 新增 P6-S4 截断与 `fetch_more` 单元测试，覆盖 cursor / scope token 暴露、普通补读、`limit` 前缀补读、single-use 与失效路径。
- `tests/host/test_toolruntime_effective_bundle.py`
  - 补充 `fetch_more` schema / callable 同源注入与 disabled truncation 不注入测试。
- `tests/host/test_phase6_toolruntime_integration.py`
  - 补充 `fetch_more` 经同一 ToolRuntime / accept barrier / EventLog path 的集成测试。
- `tests/README.md`
  - 同步 Host ToolRuntime truncation / fetch_more 测试事实与收窄命令。
- `dayu/host/README.md`
  - 同步 Host ToolRuntime 当前已实现的 run-scoped truncation / `fetch_more` 普通工具路径与剩余未实现项。

## 实现要点

- `TruncationManager` 是 ToolRuntime-local、short-lived、run-scoped 内存能力；cursor 只保存在当前 manager 实例中。
- `fetch_more` 的 schema 与 callable 均来自同一个 `EffectiveToolBundle`；RunInputBuilder 仍通过同一个 `ToolRuntimeHandle` 暴露 schema 与 executor。
- `fetch_more` 没有 Host / Engine 特化分支；它以普通 `ToolCallRequest(name="fetch_more")` 进入 `ToolRuntimeExecutor -> DefaultToolDispatcher -> accept barrier`。
- 业务 `ToolBundle` 定义 `fetch_more` 仍由 reserved-name conflict 拒绝。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py -q`
  - PASS: 15 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - PASS: 0 errors
- `git diff --check`
  - PASS

## 文档同步

命中 `dayu/host/` 与 `tests/` README 触发规则，已同步 `dayu/host/README.md` 的 ToolRuntime 当前能力说明，以及 `tests/README.md` 中 Host ToolRuntime truncation / fetch_more 的测试事实与收窄运行命令。未修改根 README 或 `dayu/README.md`：本 slice 未改变用户命令或项目级分层关系。

## 残余风险

- 当前 cursor 为单进程内存能力，符合 P6-S4 non-goal；Host restart / recovery 后无法补读是明确不承诺行为。
- 当前 truncation 支持 `text_chars`、`text_lines`、`list_items` 与 base64 形式的 `binary_bytes`；更复杂业务 payload projection 不在本 slice 扩展。
- duplicate governance 仍沿用 P6-S3 pass-through stub，完整语义级重复治理属于后续 slice / phase。
