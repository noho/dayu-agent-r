# Code Review — WU-CLI-SMOKE-01 awaiting poller fix

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-awaiting-poller-review-ds.md`
- Review target: `with_entrypoint_wait_poller_policy` helper 及其在 `prepare_entrypoint_runtime` 中的集成链路
- Included scope:
  - `dayu/service/host_assembly.py`: `with_entrypoint_wait_poller_policy`, `_scene_selects_fins_awaiting_tools`, 及其依赖的 `_fins_awaiting_registry_inputs_from_provider_configs` 等辅助函数
  - `dayu/service/entrypoint_runtime.py`: `prepare_entrypoint_runtime` 中 poller policy 补齐调用
  - `dayu/cli/commands/interactive.py`: interactive 入口与 `_prepare_interactive_existing_session_execution`
  - `dayu/cli/commands/session.py`: `session resume --mode interactive` 入口
  - `dayu/cli/commands/prompt.py`: prompt 入口
  - `dayu/host/api.py`: `OpenHostOptions.wait_poller_policy` 字段
  - `dayu/host/wait_adapter.py`: `WaitPollerRuntimePolicy`
  - `docs/host/design.md`: 相关 wait/poller/resolve_wait 设计真源
  - `dayu/host/README.md`: 相关 poller 说明
  - `dayu/service/README.md`: 相关 poller 说明
  - `tests/service/test_host_assembly.py`: `with_entrypoint_wait_poller_policy` 单元测试
  - `tests/service/test_entrypoint_runtime_interactive_path.py`: interactive 集成测试
  - `tests/service/test_entrypoint_runtime_prompt_path.py`: prompt 集成测试
  - `tests/cli/test_interactive_command.py`: CLI interactive 测试
  - `tests/cli/test_session_command.py`: CLI session resume 测试
- Excluded scope: 本 branch 中与本 fix 无关的其他变更（runtime_display、thinking renderer、fmp_company_info resolver、workspace_paths 等）
- Parallel review coverage: 无

## Findings

### 1-未修复-中-`_scene_selects_fins_awaiting_tools` 在 ALL 模式下的过度启用

- **入口/函数**: `_scene_selects_fins_awaiting_tools`
- **文件(行号)**: `dayu/service/host_assembly.py:2016-2044`
- **输入场景**: scene `tool_selection.mode = "all"`（即 `selected_tool_names is None`）但 tool bundle 中实际没有任何 Fins awaiting 工具（例如只有 fins-read 和 web 工具的部署环境）
- **实际分支**: 第 2039 行 `if selected_tool_names is None: return True`
- **预期行为**: 当 tool bundle 中不存在任何 Fins awaiting 工具时，即使 scene 声明 `mode: all`，也不应启动 poller（因为没有 wait record 会产生）
- **实际行为**: 只要 scene 声明 `mode: all`，无论 tool bundle 中是否实际存在 Fins awaiting 工具，都会启用 poller
- **直接证据**:
  - 第 2038-2040 行：`selected_tool_names is None` 直接返回 `True`，未检查 `registry_inputs.tool_names` 是否非空
  - `registry_inputs` 在第 2032-2035 行已经计算完成——若为 `None`（无 awaiting 工具），函数已在第 2036-2037 行返回 `False`
  - 因此走到第 2038 行时 `registry_inputs is not None`（必然有 Fins awaiting 工具），第 2039 行的 `return True` 实际上是正确的——因为 `registry_inputs` 非 None 意味着至少有一个 Fins awaiting 工具在 bundle 中
- **结论**: 此 finding 经进一步走读后**不成立**。`registry_inputs` 在第 2032-2037 行已过滤：若没有 Fins awaiting 工具在 bundle 中，`registry_inputs` 为 `None`，函数在第 2037 行返回 `False`。因此到达第 2038 行时 `registry_inputs` 必非 `None`，意味着至少有一个 Fins awaiting 工具实际存在，`return True` 是正确的。

### 2-未修复-低-`with_entrypoint_wait_poller_policy` 显式 `WaitPollerRuntimePolicy(enabled=False)` 覆盖语义

- **入口/函数**: `with_entrypoint_wait_poller_policy`
- **文件(行号)**: `dayu/service/host_assembly.py:283-284`
- **输入场景**: 调用方显式传入 `ServiceAssemblyOverrides(wait_poller_policy=WaitPollerRuntimePolicy(enabled=False))`
- **实际分支**: 第 283 行 `if overrides.wait_poller_policy is not None: return overrides`
- **预期行为**: 显式 `enabled=False` 应被尊重，不覆盖
- **实际行为**: 函数正确保留显式值，当前行为正确
- **直接证据**: 第 283-284 行 `is not None` 检查会保留任何非 None 值（包括 `enabled=False`）
- **影响**: 无功能问题。但如果调用方期望"只要 scene 有 awaiting 工具就必须有 poller"，显式 `enabled=False` 会绕过该保障。当前无调用方使用此路径。
- **建议改法和验证点**: 可考虑在 docstring 中明确说明显式 override 的优先级语义，当前已在 docstring 第 276 行说明。无需代码变更。
- **修复风险（低）**:
- **严重程度（低）**:

## Open Questions

1. `session resume --mode interactive` 的测试 (`test_session_command.py`) 使用 fake `_prepare_interactive_existing_session_execution` 注入，因此不直接验证 `with_entrypoint_wait_poller_policy` 在 resume 路径被调用。这由单元测试和集成测试间接覆盖，但缺少端到端的 resume → poller enabled 断言。当前 risk 低，因为 interactive 和 session resume 都调用同一个 `prepare_entrypoint_runtime` 函数。

2. 如果未来新增 Fins awaiting 工具类型（例如 `fins-query`），需要同步更新 `_fins_awaiting_tool_name_from_provider_config` 中的 provider_id/import_path/source_id 匹配三元组。当前通过显式常量集合（`_FINS_DOWNLOAD_PROVIDER_IDS` 等）管理，扩展路径清晰但需要人工同步。

## Residual Risk

- **测试覆盖**: `with_entrypoint_wait_poller_policy` 的测试覆盖了 interactive 启用、prompt 不启用、以及 `compose_open_host_options` 默认不设置 poller。`_scene_selects_fins_awaiting_tools` 的边界条件（空 tool_names、None tool_names、无交集）通过上述测试间接覆盖。缺少对以下场景的显式测试：
  - scene `mode: none` 时 poller 不启用
  - Fins awaiting provider 被 disable（`enabled: false`）时 poller 不启用
  - 多个 Fins awaiting provider 不同 workspace_root 时的 fail-fast 行为
- **集成验证**: 缺少真实 Host opener + wait poller + Fins download 的端到端 smoke 测试。当前测试使用 fake Host，不验证 poller 实际 resolve_wait 行为。
- **README 准确性**: `dayu/service/README.md` 第 24 行准确描述了 poller 判定逻辑；`dayu/host/README.md` 第 66 行准确描述了 `wait_poller_policy=None` 默认契约和 `wait_poll_adapter_registry` 必须同时提供的约束。

## Summary

**Pass / no blocker.** 修复的 root cause 成立：Fins awaiting 工具返回 observation handle 后 Run 进入 `WAITING` 状态，必须通过 `resolve_wait` 恢复；没有 poller 的情况下无人调用 `resolve_wait`，Run 永久 WAITING。

修复方案符合设计真源：
- Host design doc (line 1195) 明确 `resolve_wait` 是唯一的 wait resolution 入口
- production wait poller 通过 `resolve_wait` 恢复 Run，不绕过 Host command path
- Host 默认 `wait_poller_policy=None` 契约不变（`OpenHostOptions` line 1048）
- Fins tool 不直接通知 Host，只通过 `ToolAwaitingOutcome` → ToolRuntime → Host accept → wait record → poller → `resolve_wait` 链路

`with_entrypoint_wait_poller_policy` helper 位置正确（Service 层 assembly helper），类型/docstring 合规（无 Any/object，完整中文 docstring），无反向依赖（只依赖 `dayu.service`、`dayu.runtime`、`dayu.host`、`dayu.fins` 的 public contracts，不 import Engine 内部或 CLI 模块），无 CLI scene 魔法分支（判断基于 `PreparedSceneInputs.tool_selection.tool_names` 与 `discovered_tools.effective_provider_configs` 的交集）。

interactive 和 `session resume --mode interactive` 都通过同一个 `prepare_entrypoint_runtime` → `with_entrypoint_wait_poller_policy` 路径获得 poller。
