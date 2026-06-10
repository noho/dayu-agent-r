# WU-TOOLS-01-F02 Goal Confirmation Controller

## Gate

- Work unit: `WU-TOOLS-01-F02`
- Type: issue-backed feature follow-up
- Current gate: goal confirmation
- Design source: `docs/host/design.md`; `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- GitHub issue: `https://github.com/noho/dayu-agent-r/issues/120`

## First-principles judgment

该 work unit 成立，且严重性没有被高估。

当前 Web tools 已完成 deterministic contract migration，但 deterministic tests 只能证明当前 ToolDiscovery / ToolRuntime adapter、mock provider、requests 主路径与 Playwright fallback 的受控行为。它不能覆盖真实网络、真实站点反爬、真实浏览器安装、storage state、编码、跳转、provider API key、rate limit 与站点差异。Issue 120 的目标是迁移 live diagnostics pipeline，用它采集可分析证据，不是把 live network 变成普通 CI gate。

因此 F02 是必要的工程化诊断能力迁移。它不应被扩大成 Web smoke 判定、Web tools 重写、旧 ToolRegistry 恢复或默认 CI gate；这些都会偏离当前 issue owner 与 Host/Engine 分层边界。

## Direct evidence

- `gh issue view 120` 显示 Issue 120 仍为 open，明确 F02 是第一阶段：迁移 OLD `utils/diagnose_web_access.py`、`utils/diag_web.sh`、`utils/diag_web_batch.sh`、`utils/web_ci_urls.jsonl`，F03 才生成 Web smoke。
- 当前仓库 `rg --files | rg '(^|/)(diag_web|diagnose_web|web_ci_urls|web.*ci|ci.*web)'` 未找到 F02 目标脚本或 URL corpus。
- 当前 Web tools 位于 `dayu/tools/web/`；`dayu/tools/web/provider.py` 通过当前 `ToolsDiscoveryProviderSpec` 暴露 `search_web` 与 `fetch_web_page`，并以当前 `ToolDefinition` 作为输出。
- `dayu/tools/web/web_tools.py` 的 `fetch_web_page` 已包含 requests 主路径、Playwright fallback、storage state 目录、challenge detection 与 diagnostics payload，F02 应复用该当前 callable/adapter 入口。
- `tests/tools/web/test_web_tools_provider.py` 已有 deterministic provider tests，并显式禁止 Web modules import OLD `dayu.engine.tool_registry`、OLD truncation/fetch_more 或 `dayu.web` UI。
- OLD `/Users/leo/workspace/dayu-agent/utils/diagnose_web_access.py` 存在，但导入 OLD `ToolRegistry` 和 OLD `dayu.engine.tools.web_tools` 私有入口；迁移时必须改为当前 contract，不能照搬旧边界。
- OLD shell entrypoints 和 corpus 存在：`diag_web.sh`、`diag_web_batch.sh`、`web_ci_urls.jsonl`，其中 corpus 覆盖 foreign/news/finance 等代表性站点。

## Goal

迁移 OLD Web CI diagnostics pipeline 到当前 repo 的 `utils/`，使开发者能显式 opt-in 地运行单 URL 和批量 live Web diagnostics，采集 raw requests、当前 `fetch_web_page`、可选 Playwright browser path、storage state 与 summary bucket 的同源证据。

## Motivation

该 pipeline 解决的是“真实外部网页访问失败时如何稳定采证和分类”的工程问题。没有它，后续 Web tools 优化只能依赖临时手工复现或一次性脚本，难以把失败 bucket 转成可验证的 deterministic fixes 或 F03 Web smoke。

## Success signal

- `utils/diagnose_web_access.py`、`utils/diag_web.sh`、`utils/diag_web_batch.sh`、`utils/web_ci_urls.jsonl` 存在并可在当前 repo 运行。
- 单 URL 诊断能调用当前 `fetch_web_page`，并采集 raw requests 与可选 Playwright/network/storage state evidence。
- 批量入口能读取 JSONL/TXT URL corpus，输出 per-url diagnostics、`results.jsonl`、`summary.json` 和 Codex 可读 summary。
- 缺少 live network、Playwright/browser、API key 或 storage state 时输出清晰 diagnostic/skip，不进入普通 deterministic CI。
- README / tests README 说明 deterministic tests 默认无 live network；F02 只提供显式 Web CI diagnostics，F03 才定义 Web smoke gate。

## Non-goals

- 不定义 Web smoke 的 pass/fail/skip gate，不关闭 `WU-TOOLS-01-S5-R2`。
- 不把 live network 或 real browser diagnostics 放入默认测试或普通 CI。
- 不恢复 OLD `ToolRegistry`、OLD truncation manager、OLD `fetch_more` 或 OLD `dayu.web` UI。
- 不重写 Web search/fetch/Playwright pipeline，不改变 Web tools production behavior。
- 不把单个网站偶发失败直接判定为 production regression；F02 只输出证据和分类。

## Scope boundary

Allowed source scope for the next plan gate:

- Current repo: `utils/diagnose_web_access.py`, `utils/diag_web.sh`, `utils/diag_web_batch.sh`, `utils/web_ci_urls.jsonl`
- Focused tests under `tests/` for parser/classifier/diagnostic adapter behavior, with live paths opt-in or mocked
- `tests/README.md` and any existing relevant README required by repository update rules
- Current Web tools callable/provider adapter only as needed for a clean invocation boundary

Out of scope:

- `dayu.engine`, `dayu.host`, `dayu.service`, `dayu.ui`
- Web production behavior changes outside a minimal callable boundary needed by diagnostics
- Any default CI workflow change that runs live network/browser access

## Overdesign explicitly avoided

本轮不设计新的 Web observability platform、不引入 Host durable event、不引入 Engine event 或 ToolRuntime contract change、不创建通用 smoke framework。F02 只迁移已有 diagnostics pipeline，并把 OLD imports 改成当前 repo 的明确调用边界。

## Blocking open questions

None for goal confirmation.

Plan gate must decide the exact adapter shape and test split, especially how to call current `fetch_web_page` without reintroducing OLD `ToolRegistry` or leaking internal governance text into LLM-facing diagnostics.

## User confirmation

用户已确认 `WU-TOOLS-01-F02` goal，并补充授权：除移植 OLD diagnostics pipeline 代码外，plan 可以基于代码证据评估是否需要修改当前 repo 的 CI / diagnostics 相关代码来增强 CI 效果。该授权不改变非目标：F02 仍不定义 Web smoke pass/fail gate，不把 live network/browser diagnostics 放入默认 CI，不关闭 `WU-TOOLS-01-S5-R2`，也不恢复 OLD ToolRegistry / truncation / fetch_more / UI 路径。
