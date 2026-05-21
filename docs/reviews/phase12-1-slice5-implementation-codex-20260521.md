# Phase 12.1 Slice 5 Implementation Artifact

## Gate / Scope

- 当前 gate：Slice 5 implementation。
- 目标：重写 `utils/smoke_host_public_multiturn.py`，使最终 smoke 默认走真实生产式 runtime assembly 路径，而不是脚本内 manual hardcoded 装配。
- 本次修改文件：
  - `utils/smoke_host_public_multiturn.py`
  - `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
  - `README.md`
  - `tests/README.md`
- 未执行：commit、push、PR、其它 gate。

## 动机判断

动机成立。前置 dirty 版本仍保留 `manual` 作为默认装配模式，并在脚本内用旧 schema 字段、手写 prompt guard、硬编码 DeepSeek runner、手工 mock `ToolBundle` 与路径 fallback 组装 Host。这会掩盖 Phase 12.1 要暴露的 schema / public contract gap。正确修复不是继续补脚本默认值，而是把 smoke 改成 Service-like composition：runtime location resolver + ConfigLoader + ToolsDiscovery + ScenePrepare + Engine provider extension helper + public `open_host(options)`。

## Pre-existing Dirty Hunk Audit

接管并保留的素材：

- README 中“Host public 多轮闭环 smoke”入口位置保留，改写为 runtime assembly 事实说明。
- smoke 的三轮 public Host handle 验证思路保留：`ensure_session`、`submit_followup`、`watch_session_events`、terminal HostEvent 摘要、compact artifact 摘要。
- `SmokeFactTool` 的工具事实观测意图保留，但不再在脚本默认路径中直接塞 raw `ToolBundle`；改为可由 workspace `tool_discovery.json` 显式引用的 provider callable。

丢弃的旧思路：

- 删除 `--assembly-mode manual/runtime`，不再允许默认 manual path。
- 删除脚本内 DeepSeek 专用 runner / compactor 硬编码、旧 context budget 字段、旧 execution profile 字段、旧 scene runtime hints 字段。
- 删除脚本内 prompt asset / manifest root fallback；路径只来自 `dayu.runtime.location.resolve_runtime_locations(...)`。
- 删除脚本内业务 system prompt guard；system messages 只来自 `ScenePrepare`。
- 删除 smoke 内自写 provider extension parser，改用 `dayu.engine.provider_extensions.provider_request_extension_from_json(...)` fail-closed helper。
- 删除脚本默认 mock `ToolBundle` 注入；scene 工具选择只在 `ToolsDiscovery` 已发现的 bundle 内发生。

## Service-like Assembly Path Summary

当前 smoke path：

1. CLI 解析 typed override：`workspace_root`、`scene_id`、`execution_profile_id`、`host_runtime_id`、`model_id`、`runner_option_hint_id`、scene context slots。
2. `resolve_runtime_locations(project_root, package_config_root)` 解析 `config_overlay_dir`、`prompt_asset_root`、`scene_manifest_root`。
3. `ConfigLoader(...).load(workspace_config_dir=locations.config_overlay_dir)` 加载五类 runtime config。
4. 按 config / CLI 选择 host runtime、runtime lane、execution profile。
5. 将 `tool_discovery.json` typed view 映射为 `ToolsDiscoveryProviderSpec`，通过 `ToolsDiscovery().discover(...)` 聚合工具。
6. 用 execution profile 的 `tool_truncation_policy` 对工具声明补齐 effective truncate spec。
7. `ScenePrepare` 使用 dedicated scene `smoke_host_public_multiturn`、location resolver 输出的 prompt / manifest root、context slots 与已发现工具目录装配 `PreparedSceneInputs`。
8. `select_runner_option_hint(...)` 合并 Run override > scene hints > execution profile baseline，选择 ordinary model / runner option hint；compactor 使用 execution profile compactor baseline。
9. `merge_agent_policy_config(...)` 合并 scene `agent_policy` override 与 execution profile agent policy profile。
10. `provider_request_extension_from_json(...)` 解析 provider extension DSL；未知 type / 字段 fail closed。
11. `_compose_open_host_options(...)` 映射为 public `OpenHostOptions`，只通过 `open_host(options)` 打开 Host。
12. `_compose_submit_followup_request(...)` 映射每轮 public `SubmitFollowupRequest`；不把 raw `ToolBundle` 放入 per-run request / metadata。

## Assembly Diagnostics Fields

smoke 在调用 Host 前输出：

- `config_overlay`
- `prompt_asset_root`
- `scene_manifest_root`
- `host_runtime_id`
- `execution_profile_id`
- `model_id` 与来源层
- `runner_option_hint_id` 与来源层
- `compactor_model_id`
- `compactor_runner_option_hint_id`
- `lane_name`
- `tool_provider_report`
- `tool_selection`
- `policy_refs`
- `agent_policy_sources`
- `provider_extension_status`
- `suggested_helpers`

## Suggested Adapter / Helper Names

当前仍是 smoke-local private adapter。diagnostics 输出建议后续 Service work unit 提取：

- `compose_open_host_options`
- `compose_submit_followup_request`
- `provider_extension_from_config`

Engine 侧已存在实际 helper：`dayu.engine.provider_extensions.provider_request_extension_from_json`。

## Tests / Validation

- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
  - 结果：通过，退出码 0。
- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
  - 结果：2 passed。
- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py -q`
  - 结果：57 passed。
- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
  - 结果：59 passed。
- `source .venv/bin/activate && python -m pyright utils/smoke_host_public_multiturn.py tests/runtime/test_smoke_host_public_multiturn_assembly.py`
  - 结果：0 errors。
- `source .venv/bin/activate && python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host`
  - 结果：0 errors。
- `git diff --check`
  - 结果：通过。

## Fix Addendum: Slice 5 Controller Accepted Findings

### Motivation

动机成立。Controller 接受的两个问题都指向同一个 runtime assembly 边界：smoke 脚本必须让工具发现结果成为唯一真源，不能用模块级可变状态把历史 provider 调用结果重新塞回当前 assembly。同时，`discover_smoke_tools` 是给 `ToolsDiscovery` 调用的 provider callable，不是脚本默认注入点，docstring 必须把触发条件讲清楚。

### Patch

最小修改 `utils/smoke_host_public_multiturn.py`：

- 删除模块级 `_DISCOVERED_SMOKE_TOOL`。
- `discover_smoke_tools(spec)` 改为只创建局部 `SmokeFactTool`，并把该实例放入返回的 `ToolsDiscoveryProviderOutput.definitions`。
- `_find_smoke_tool(tool_bundle)` 改为只遍历传入 `ToolBundle.definitions`；没有 `SmokeFactTool` callable 时返回 `None`，不再回退到任何历史发现状态。
- 澄清 `discover_smoke_tools` docstring：该函数是 `ToolsDiscovery` provider callable；仅当 workspace `tool_discovery.json` 显式启用 provider spec，且该 spec 的 import path 指向 `utils.smoke_host_public_multiturn:discover_smoke_tools` 时，才会由 `ToolsDiscovery` 调用。

最小修改 `tests/runtime/test_smoke_host_public_multiturn_assembly.py`：

- 新增 `test_find_smoke_tool_only_inspects_passed_tool_bundle`。
- 测试先调用 `discover_smoke_tools(...)` 制造历史 provider 调用，再断言 `_find_smoke_tool(ToolBundle(definitions=())) is None`，覆盖 P12.1-S5-F1 的回归点。

README 判定：

- 本修复不改变用户可见命令、配置入口、架构边界或测试手册职责，只收紧 smoke 内部工具查找语义；未更新 README 或 `tests/README.md`。

### Validation

- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
  - 结果：3 passed。
- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
  - 结果：60 passed。
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q`
  - 结果：8 passed。
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
  - 结果：通过，退出码 0。
- `source .venv/bin/activate && python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过。

### Residual Risk

- 本次只修复 Slice 5 controller accepted findings，未修改生产 Host、Engine、runtime config schema、配置资产、设计文档或总控文档。
- `_find_smoke_tool` 现在严格依赖当前传入 bundle；如果 workspace provider 未启用或 scene 未选中 smoke 工具，脚本会继续在 Host 调用前暴露配置/工具发现缺口，这是预期行为。
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q`
  - 结果：7 passed, 1 failed。
  - 失败项：`tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity`。
  - 精确失败原因：`open_host(options)` 进入 Host command options validation 时抛出 `ValueError: HostCommandHandleOptions.context_budget_minimum_protection_tokens must be smaller than input budget`。该失败发生在现有 host compact smoke 的小 context window test setup 中，未进入本 Slice 5 smoke 脚本，也不由本次修改文件触发。
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py`
  - 结果：退出码 1，调用 Host 前 fail fast。
  - 精确原因：默认包内 `tool_discovery.json` 中 `financial-tools` provider 为 disabled，且当前仓库没有启用 workspace overlay provider；dedicated scene 的 `tool_tags_any=["web","fins","ingestion"]` 没有匹配工具，`ScenePrepareError: tool_tags_any matched no tools: fins, ingestion, web`。这是预期暴露的配置/工具发现缺口，不是脚本内补默认值的场景。

## README Decision

- 根 `README.md` 已同步用户可见 smoke 入口事实：默认 runtime assembly、可显式 override、工具发现缺口会 Host 调用前 fail fast、diagnostics 字段。
- `tests/README.md` 已补充新增 focused test 的职责。

## Residual Risks / Deferred Items

- 真实 Service / CLI / Web / GUI composition helper 正式归属仍属于后续 Service assembly work unit；本 slice 只提供 smoke-local adapter 和 diagnostics helper 名称。
- 默认包内 `tool_discovery.json` 未启用可用财报工具 provider，且当前仓库没有 `dayu.fins` 包；默认真实 smoke 会在 Host 调用前暴露该 gap。后续需要由 Service / Fins / 配置 work unit 提供真实业务工具 provider。
- 指定 Host compact smoke 现有失败需要 Host/context budget test owner 分类处理；本 slice 未修改 Host public contract 或 Engine loop。
- 真实 provider smoke 未进入网络调用阶段，因为默认工具发现配置先 fail fast；若提供 workspace overlay 启用 smoke provider 或真实财报工具 provider，还需要在具备 provider key / quota / network 时复跑三轮真实 smoke。

## Completion Status

Slice 5 implementation 已完成到 implementation report。当前停在 implementation gate，等待 code review；未 commit、未 push、未开 PR。

## Follow-up Addendum: Host Compact Smoke Setup Fix

### Root Cause

Controller 复跑指定 Host smoke 组时，`tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity` 在 `open_host(options)` 阶段失败，错误为：

```text
ValueError: HostCommandHandleOptions.context_budget_minimum_protection_tokens must be smaller than input budget
```

直接证据：

- 测试使用 `_SOFT_CONTEXT_WINDOW_SIZE = 360` 构造 `ContextBudgetPolicy`。
- `open_host(options)` 会把 public opener 的 ratio-first `ContextBudgetPolicy.context_window_size` 映射到内部 `HostCommandHandleOptions.context_window_size`。
- 内部 command options 的 reserved output placeholder 由 `_internal_reserved_output_tokens_for_policy(context_window_size)` 派生：当 context window 为 360 时，reserved output 为 359，input budget 只剩 1。
- `HostCommandHandleOptions` validation 在未显式传入 hard threshold / minimum protection 时使用默认 minimum protection 256，因此 `256 >= 1` 被正确拒绝。
- 将 context window 提到 1400 后，input budget 虽大于 256，但内部默认 soft ratio 0.8 与 minimum protection 组合仍使 `soft_threshold_tokens >= hard_threshold_tokens`；这说明 command validation 要求 input budget > 1280。

结论：root cause 是 P12.1 context budget public contract 改为 ratio-first 后，该 real compact smoke 仍沿用旧的小 context window setup，没有为 opener 内部 command options validation 留出足够 input budget。生产校验是合理的，本 follow-up 不放宽 Host public contract 或 Engine loop。

### Patch

最小修改 `tests/host/test_public_compact_smoke.py`：

- 将 `_SOFT_CONTEXT_WINDOW_SIZE` 从 360 调整为 2400，使 opener 内部 command validation 的 input budget 足以同时满足默认 soft ratio 与 minimum protection。
- 新增 `_SOFT_THRESHOLD_TOKENS = 70`，让测试自身用于 `context_budget_policy_from_threshold_tokens(...)` 的 compact 触发阈值仍保持小阈值语义。
- 保留 `_SOFT_HARD_THRESHOLD_TOKENS = 300`，继续验证真实 compactor 路径和 continuity。
- 删除旧的 `_SOFT_RESERVED_OUTPUT_TOKENS` / `_SOFT_SAFETY_MARGIN_RATIO` 计算，避免继续表达旧 reserved-output mental model。

### Follow-up Validation

- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q`
  - 结果：8 passed。
- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
  - 结果：59 passed。
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
  - 结果：通过，退出码 0。
- `source .venv/bin/activate && python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host`
  - 结果：0 errors。
- `git diff --check`
  - 结果：通过。
