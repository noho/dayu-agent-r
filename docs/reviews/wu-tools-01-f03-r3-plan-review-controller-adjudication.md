# WU-TOOLS-01-F03-R3 Plan Review Controller Adjudication

## 裁决范围

本裁决只覆盖 `WU-TOOLS-01-F03-R3` plan gate，不裁决实现代码。设计真源为 `docs/host/design.md` 与 `docs/engine/design.md`；总控真源为 `docs/host/issues-implementation-control.md`。

## 输入 artifact

- Plan: `docs/host/wu-tools-01-f03-r3-web-config-search-smoke-plan.md`
- AgentMiMo plan review: `docs/reviews/wu-tools-01-f03-r3-plan-review-mimo.md`
- AgentDS plan review: `docs/reviews/wu-tools-01-f03-r3-plan-review-ds.md`

## Controller 裁决

R3 的动机成立。它不是单纯外部 provider 可用性 residual，而是默认 Web tools config 未完整迁入新 `tool_discovery.json`，且当前 smoke 没有证明 Web config 经过 `ConfigLoader -> discover_service_tools -> ToolsDiscovery -> web provider -> ToolDefinition.callable` 闭进工具。

两路 review 均为 `pass-with-fixes`。Controller 接受以下 plan fix 要求，并确认修订后的 plan 已写回：

- `utils/smoke_web_ci.py` 作为仓库级 smoke harness，允许 import `ConfigLoader`、runtime location helper 与 `discover_service_tools()`；不得为了 smoke 新增 production helper、wrapper 或 facade。
- local assembly 和 search provider smoke 必须显式使用 `package_config_dir=dayu/config` 与临时 `workspace_config_dir`，只 overlay `tool_discovery.json`，并调用完整 `ConfigLoader.load()`；不得降级为 `load_tool_discovery()`。
- `SmokeSummary` 使用 typed `search_cases`，`external_cases` 只保留外部 URL fetch cases；不得新增 `metadata` 弱类型字段。
- local assembly artifact 必须证明 `provider_config.fetch_truncate_chars` 和 `truncate_max_chars` 等于 overlay 值，避免只证明 fetch 成功。
- pytest 不做 live network 或真实 credential；smoke control-flow 测试可 monkeypatch `ConfigLoader.load()` 与 `discover_service_tools()`，真实 assembly 由 Service / Web provider tests 覆盖。
- Search provider 分类优先确定性 key-missing 信号与 `HTTPError.response.status_code`；关键词只作为补充，无法分类时落入通用 diagnostic bucket；artifact 不写 secret。

## Verdict

Plan gate 通过，可以进入 implementation gate。实现时必须按 plan 的 stop conditions 停止任何 Host / Engine public contract 变更、Runtime 反向依赖、外部 provider hard gate 化、secret 泄漏或绕过 `discover_service_tools()` 的方案。
