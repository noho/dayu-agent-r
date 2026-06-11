# WU-TOOLS-01-F01-02-R3 Slice 4 Implementation

## Gate / Scope

- Gate: implementation
- Slice: Slice 4, Legacy Adapter Deletion and Boundary Closeout
- Work unit: WU-TOOLS-01-F01-02-R3
- Accepted predecessor commit: `2a914234`
- Objective: 删除 `dayu/tools/_legacy_adapter` 和 legacy adapter 专属测试，收口 import boundary、combined acceptance 与 README 事实。

## First-principles Judgment

动机成立。Slice 0/1/2/3 已经把 Doc、Web、Fins read tools 迁移为 current `ToolDefinition` / `ToolCallable` 原生实现，并把 Host cancellation token 导致的停止投影为 `ToolCancelledOutcome(reason="host_cancelled")`。继续保留 legacy adapter 只会保留旧同步 callable、collector/decorator metadata 与错误 outcome 投影路径，和 Issue #130 的目标冲突。

本 slice 不实施 WU-TOOLS-01-F08，不改 documents processor registry，不重构 Doc/Web/Fins native 实现，不修改 Host / Engine / ToolRuntime 状态机。

## Changed Files

- 删除 `dayu/tools/_legacy_adapter/**`。
- 删除 `tests/tools/test_legacy_tool_adapter.py`。
- 更新 `tests/tools/test_combined_tools_acceptance.py`：旧 runtime import 扫描对象改为当前 native provider 源文件，不再允许 adapter 目录存在。
- 更新 `tests/host/test_import_boundary.py`：移除 legacy adapter 的 `fetch_more` defensive allowlist，`fetch_more` 只允许留在 ToolRuntime / tooling owner。
- 更新 `tests/README.md`：移除 legacy adapter 测试说明，补充 runtime tool call projection helper、native Doc/Web provider 与 combined acceptance 当前事实。
- 更新 `dayu/fins/README.md`：把 read provider 装配示例和扩展点从旧注册函数名更新为 `build_fins_read_tool_definitions(...)`。
- 更新 `tests/tools/test_doc_tools_provider.py`：删除 adapter 符号名的负向断言字符串，使测试代码也不再引用 retired adapter 符号；保留 OLD runtime import、`fetch_more` 与 `TruncationManager` 防线。
- 新增本 artifact。

## Legacy Test Behavior Migration

| `tests/tools/test_legacy_tool_adapter.py` 行为 | Current 覆盖 | 结论 |
|---|---|---|
| 参数 schema validation、default projection、unknown / missing / enum / range / array item | `tests/runtime/test_tool_call_projection.py` 覆盖 default 注入、required、unknown field、wrong tool name、enum、string bounds、integer / number bounds、array item 与 unsupported schema fail-fast | 已由 Slice 0 runtime helper 测试覆盖 |
| 普通业务失败 exception-to-outcome mapping | `tests/runtime/test_tool_call_projection.py` 覆盖 `failed_outcome(...)` metadata；Doc/Web/Fins provider 测试覆盖领域 failure outcome | 已由 helper + provider tests 覆盖 |
| legacy `tool_cancelled` 投影为 failed outcome | 不迁移；这是 R3 删除的错误行为 | Doc/Web/Fins cancellation tests 已断言 `ToolCancelledOutcome(host_cancelled)` |
| path projection、allowed roots、`must_exist=True` | `tests/tools/test_doc_tools_provider.py` 覆盖白名单拒绝、缺失文件、绝对路径投影、路径失败不进入业务函数、list/search 返回路径可链 read tools | 已由 Slice 1 Doc provider tests 覆盖 |
| per-tool / per-provider serialization | `tests/tools/test_doc_tools_provider.py`、`tests/tools/web/test_web_tools_provider.py`、`tests/fins/test_fins_storage_provider.py` 与 combined acceptance 覆盖 provider 级共享 lock 并发行为 | 已由 Slice 1/2/3 provider tests 覆盖 |
| truncate / display / tags / schema conversion | Doc/Web/Fins provider tests 与 `tests/tools/test_combined_tools_acceptance.py` 覆盖 current `ToolTruncateSpec`、tags、schema 不泄露治理字段、combined bundle 稳定工具名 | 已由 Slice 1/2/3 + combined acceptance 覆盖 |
| `fetch_more` reserved 行为 | `tests/tools/test_combined_tools_acceptance.py` 覆盖 business bundle 不含 `fetch_more` 且 ToolRuntime 注入 framework `fetch_more`；`tests/host/test_import_boundary.py` 覆盖 token 只在 owner 中出现 | 已由 Slice 4 boundary closeout 覆盖 |
| collector / decorator OLD metadata 组装细节 | 不迁移；这是 adapter-only 实现细节 | 生产 provider 已使用 native builder；删除测试是正确收口 |

## README Decision

- `tests/README.md`: 触发并已更新，因为删除 legacy adapter 测试改变了 tests 当前分层事实。
- `dayu/fins/README.md`: 触发并已最小更新，因为 read provider 示例仍引用旧注册函数名，当前代码真源为 `build_fins_read_tool_definitions(...)`。
- `dayu/README.md`: 已检查，无需更新；当前总览已经描述 `dayu.tools` 输出 current `ToolDefinition` / `ToolBundle`，未提 OLD / legacy adapter。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py tests/host/test_import_boundary.py tests/service/test_import_boundary.py`
  - Result: 108 passed, 3 edgar deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations. Pyright 提示存在新版本 `1.1.410`，未影响验证。
- `git diff --check`
  - Result: passed, no output.
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests`
  - Result: no matches.

## Stop Condition Check

删除 adapter 后未发现非 Doc / Web / Fins read 生产工具依赖 adapter。最终 `rg` 在 `dayu` 和 `tests` 下无命中，停止条件未触发。

## Residual Risks

- fixed in current slice: legacy adapter 目录、adapter 专属测试、Host import boundary defensive allowlist 和 combined acceptance adapter allowance 已删除。
- fixed in current slice: tests README 和 Fins README 当前事实已收口。
- assigned to later work unit: WU-TOOLS-01-F08 documents processor registry naming cleanup 仍归后续 work unit，本 slice 未实施。
- uncovered areas: 未运行全仓库 pytest；本 slice 按 accepted plan 运行受影响子集、pyright、diff check 和 legacy 符号扫描。

## Completion Status

Slice 4 implementation complete. 未提交。
