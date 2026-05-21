# Phase 12.1 Slice 5 Re-Review Controller Adjudication

## Verdict

- MiMo re-review：PASS。
- DS re-review：PASS。
- Controller 裁决：P12.1-S5-F1 / F2 均已收口，无新增 blocker。Phase 12.1 Slice 5 可以进入 accepted local commit。

## Fixed Findings

### P12.1-S5-F1

状态：fixed。

证据：`_DISCOVERED_SMOKE_TOOL` 模块级全局状态已删除；`_find_smoke_tool(tool_bundle)` 只遍历传入 `ToolBundle.definitions`，未找到 `SmokeFactTool` callable 时返回 `None`。`tests/runtime/test_smoke_host_public_multiturn_assembly.py::test_find_smoke_tool_only_inspects_passed_tool_bundle` 先制造历史 provider 调用，再断言空 bundle 返回 `None`，覆盖回归点。

### P12.1-S5-F2

状态：fixed。

证据：`discover_smoke_tools` docstring 已明确其角色是 `ToolsDiscovery` provider callable，并说明只有 workspace `tool_discovery.json` 显式启用 provider spec 且 import path 指向该函数时才由 `ToolsDiscovery` 调用，不再保留脚本内部注入的歧义表述。

## Validation Evidence

- Controller 本地复跑 `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`：3 passed。
- Controller 本地复跑 `pytest tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`：60 passed。
- Controller 本地复跑 `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q`：8 passed。
- Controller 本地复跑 `python utils/smoke_host_public_multiturn.py --help`：退出码 0。
- Controller 本地复跑 `python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host`：0 errors。
- Controller 本地复跑 `git diff --check`：clean。

## Residual Risks

- 默认包内 `tool_discovery.json` 的 `financial-tools` provider 为 disabled，真实 smoke 仍会在 Host 调用前暴露缺少工具 provider 的配置缺口；这是 Phase 12.1 的预期 fail-fast 行为。
- 正式 Service helper 提取仍属后续 Service assembly work unit；本 slice 只提供 smoke-local adapter 与 diagnostics 建议名称。
