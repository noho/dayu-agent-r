# Phase 12.1 Slice 5 Code Review Controller Adjudication

## Verdict

- MiMo review：PASS_WITH_FINDINGS，blocking count = 0，提出 2 个低严重度 maintainability finding。
- DS review：PASS，blocking count = 0。
- Controller 裁决：进入 Slice 5 窄 fix。接受 MiMo F1 / F2 为当前修复项；DS PASS 与其它 residual risks 不阻塞。

## Accepted Current Fixes

### P12.1-S5-F1: `_find_smoke_tool` must not fall back to module-global mutable state

裁决：接受为当前 fix。

理由：Phase 12.1 的 smoke success signal 是验证真实 Service-like assembly，工具实例应来自 `ToolsDiscovery` 发现出的 effective `ToolBundle`。`_find_smoke_tool(tool_bundle)` 若在 bundle 查找失败后读取模块级 `_DISCOVERED_SMOKE_TOOL`，会让函数行为依赖历史调用顺序，而不是显式输入；这削弱了装配诊断和 fail-fast 边界。最佳实践是只从传入 bundle 查找，找不到就返回 `None`。

修复边界：只修改 `utils/smoke_host_public_multiturn.py` 与 focused runtime smoke assembly tests；不得恢复 manual `ToolBundle` 注入，不得修改 production Host / Engine / runtime config schema。

### P12.1-S5-F2: `discover_smoke_tools` docstring must describe ToolsDiscovery provider semantics

裁决：接受为当前 fix。

理由：该函数不是脚本默认注入点，而是可由 workspace `tool_discovery.json` 显式启用的 `ToolsDiscovery` provider callable。docstring 应精确表达调用权属于 `ToolsDiscovery`，避免维护者误以为 smoke 脚本内部会绕过配置注入工具。

修复边界：只改 docstring；不改变 provider callable public behavior。

## Accepted As Residual / Non-Blocking

- 默认包内 `tool_discovery.json` 的 `financial-tools` provider 为 disabled，直接运行 smoke 会在 Host 调用前因 scene tool tags 无匹配工具 fail fast。该行为符合 Phase 12.1 目标：暴露配置 / 工具发现缺口，而不是由 smoke 写业务默认值掩盖。
- `compose_open_host_options`、`compose_submit_followup_request`、`provider_extension_from_config` 仍为 smoke diagnostics 建议的后续 Service helper 名称；正式 helper 提取不属于 Slice 5。
- 极小 context window 的 ratio-first policy 行为没有在本 slice 新增专项覆盖；当前 compact smoke 只修正测试 setup，使其符合 Host command validation。

## Required Re-Review

修复完成后需要 MiMo 与 DS 对 P12.1-S5-F1 / P12.1-S5-F2 做 re-review，并确认没有新增 blocker。
