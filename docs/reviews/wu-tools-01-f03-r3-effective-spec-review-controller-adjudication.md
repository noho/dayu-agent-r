# WU-TOOLS-01-F03-R3 Effective Spec Review Controller Adjudication

## Scope

本裁决覆盖 AgentMiMo 与 AgentDS 对当前 effective spec assembly 改动的 review 结果：

- `docs/reviews/wu-tools-01-f03-r3-effective-spec-review-mimo.md`
- `docs/reviews/wu-tools-01-f03-r3-effective-spec-review-ds.md`

## Adjudication

### DS F1 / MiMo F3: web-tools 默认启用会让所有 scene 暴露 Web tools

结论：不接受原 finding。

直接证据：

- `dayu.runtime.scene_prepare._select_tools` 按 scene manifest 的 `tool_selection` 计算 per-run 工具白名单；`mode=none` 返回空集合，`mode=select` 只返回显式工具名或 tag 命中的工具，只有 `mode=all` 才返回 `None` 表示全量。
- `dayu.host.tool_runtime._selected_business_definitions` 会按 `SubmitFollowupRequest.tool_names` 过滤 construction-time `ToolBundle`；`None` 才表示全量，非空集合只启用指定工具。
- 包内 manifest 当前不是全部 `all`：例如 `prompt.json` 显式选择 `web/fins/ingestion` tag，`overview.json` 使用 `mode=none`。
- `allow_empty=true` 只允许 provider 成功返回空工具集合；`resolve_provider_callable` 的 import path 解析失败仍抛 `ToolsDiscoveryError`，不会被 `allow_empty` 静默吞掉。

更准确的风险表述：如果某个 Service / UI 调用点绕过 `scene_inputs.tool_selection.tool_names`，直接向 Host 传 `tool_names=None`，才会暴露 construction-time 全量工具。这不是 `web-tools.enabled=true` 的 root cause。本轮未发现当前生产调用点存在该绕过。

### MiMo F1 / DS F3 / DS F4: discovery 与 wait adapter registry effective config 一致性

结论：接受并修复。

修复：

- `ServiceDiscoveredTools` 新增 `effective_provider_configs`，保存 `discover_service_tools(...)` 本次 discovery 实际使用的 effective provider configs。
- `compose_open_host_options(...)` 复用 `request.discovered_tools.effective_provider_configs` 构造 Host tooling / Fins wait adapter registry，不再从 `request.config.tool_discovery.providers` 独立重算。
- 新增 Service 集成测试，证明 discovery 阶段注入的 Fins workspace config 会进入 compose 阶段；即使 raw config 后续被污染为相对路径，compose 也不会回读 raw config。

### DS F2: Fins workspace-bound provider 识别边界测试不足

结论：接受并修复。

修复：新增边界测试覆盖普通非 Fins provider、read provider source id + entry point、download import path、preprocess source id 与 upload provider id。

### DS F5: identity 比较脆弱

结论：不接受为本轮修复项。

`_effective_tool_provider_config` 是私有 helper，当前返回原始 mapping 或新 dict 的约定由 focused tests 覆盖。引入额外返回 envelope 会增加代码复杂度，当前收益不足。

### DS F6: Service assembly 测试耦合 Web provider 实现

结论：不接受为本轮修复项。

该测试是有意的 Service + real Web provider integration guard，用于证明 `ConfigLoader.load()` 到 `discover_service_tools()` 的生产式链路可发现 Web tools。Web provider 自身细节仍由 `tests/tools/web/` 覆盖。

### DS F7: search provider diagnostic 分类测试不足

结论：接受并修复。

修复：新增确定性测试覆盖 HTTP status 分类、错误文本分类、ConfigLoader hard failure、discovery hard failure、callable timeout diagnostic-only 与 completed empty result diagnostic-only。

## Result

Accepted findings 已修复。需要重新运行 focused tests、pyright、Web smoke，并派 AgentMiMo / AgentDS re-review。
