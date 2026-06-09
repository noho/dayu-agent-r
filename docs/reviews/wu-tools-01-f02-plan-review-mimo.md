# WU-TOOLS-01-F02 Plan Review

## Gate

- Work unit：`WU-TOOLS-01-F02`
- Type：issue-backed feature follow-up
- Current gate：plan review
- Reviewer：MiMo
- Date：2026-06-09
- Plan artifact：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Goal confirmation artifact：`docs/reviews/wu-tools-01-f02-goal-confirmation-controller.md`
- Design source：`docs/host/design.md`；`docs/engine/design.md`
- Control source：`docs/host/issues-implementation-control.md`
- GitHub issue：#120

## Verdict

**pass-with-findings**

Plan 是 code-generation-ready 的。3 个切片定义清晰，contract 对齐正确，scope 边界严格，stop conditions 完整。4 个 findings 均为 minor / informational，不阻塞 implementation gate。

## Reviewed Scope

- Plan 全文：目标、动机、成功信号、非目标、范围边界、设计真源对齐、实现决策、小切片计划、测试边界、schema、风险
- 交叉验证：Issue #120 原文、goal confirmation controller、总控真源中 F02/F03 条目、当前 `dayu/tools/web/` provider/contract、OLD `diagnose_web_access.py` 接口边界、forbidden import guard pattern

## Findings

### F-1：sync-to-async bridge 策略未显式说明（minor）

**Severity**：minor
**Plan 行文证据**：实现决策 #1（第 204-219 行）描述了通过 `asyncio.run(...)` 调用 `ToolDefinition.callable`，但未显式说明 CLI 脚本整体的 sync/async 架构策略。
**代码证据**：OLD `diagnose_web_access.py` 是同步脚本，用 `sync_playwright` 做浏览器导航。当前 `ToolDefinition.callable` 是 `async __call__` 协议。Plan 提到 `asyncio.run(...)` 调用 fetch，但 Playwright profile 部分提到 `optional Playwright import 只能在 browser-profile helper 内部`，未说明 Playwright 是继续用 sync API 还是改为 async。
**Challenge**：实现者需要决定：
1. CLI 入口是 `async def main()` + `asyncio.run(main())`，还是保持同步仅在 fetch adapter 处 `asyncio.run(coro)`？
2. Playwright profile 继续用 `playwright.sync_api.sync_playwright`，还是改为 async？
3. 若混合 sync/async，`asyncio.run()` 嵌套风险如何处理？

**裁决建议**：accepted — implementation 应在 Slice 2 开始前先确定 sync/async 架构，最简方案是 CLI 入口同步 + fetch adapter 用 `asyncio.run()` + Playwright 继续用 sync API，但需要在实现报告中显式确认。

### F-2：raw requests profile header 来源的复用/重复张力（minor）

**Severity**：minor
**Plan 行文证据**：实现决策 #2（第 221-225 行）说"若可直接复用当前 `dayu.tools.web.web_tools` 中已存在的 helper 且不需要新增 production export，可以复用；若需要扩大 production public surface，则不改 production code，改用本地诊断 headers"。
**代码证据**：`_build_fetch_headers(url)` 和 `_normalize_url_for_http(url)` 是 `web_tools.py` 的 private helper（下划线前缀）。`_get_no_retry_web_session()` 在 `web_http_session.py` 中也是 private。OLD 脚本直接 import 这些 private helper。
**Challenge**：Plan 将决策推迟到 implementation，但两条路径都有代价：
- 复用 private helper：diagnostics 脚本与 production internals 耦合，private 签名变化会 break diagnostics。
- 本地诊断 headers：与 production headers 不一致，raw requests profile 与 `fetch_web_page` 的对比价值降低。

**裁决建议**：accepted — 这是合理的 implementation-time 决策。建议 implementation 优先复用 private helper（因为 diagnostics 本身就是 developer utility，与 production internals适度耦合可接受），但应在 diagnostics 模块 docstring 中说明依赖了哪些 private helper，便于后续同步维护。

### F-3：`discover_tools` 配置映射路径未在 plan 中展开（informational）

**Severity**：informational
**Plan 行文证据**：实现决策 #1（第 206-209 行）列出 `request_timeout_seconds`、`fetch_truncate_chars`、`allow_private_network_url`、`playwright_channel`、`playwright_storage_state_dir` 作为 `WebToolsConfig` 字段，但未说明这些值从 CLI args 到 `ToolsDiscoveryProviderSpec.config` 的映射方式。
**代码证据**：`discover_tools(spec)` 从 `spec.config` 解析 `WebToolsConfig`，再传给 `register_web_tools(collector, ...)`。`ToolsDiscoveryProviderSpec` 的 `config` 字段类型是 `Mapping[str, JsonValue]`。
**Challenge**：CLI args（如 `--request-timeout`、`--playwright-channel`）需要映射为 `WebToolsConfig` 的字段名。映射关系在 OLD 脚本中是隐式的（直接构造 registry），在新方案中需要显式构造 spec config dict。

**裁决建议**：needs-more-evidence — 这不是 plan defect，但 implementation 需要确认 `WebToolsConfig` 的确切字段名和类型，确保 CLI args 映射正确。建议 implementation 在 Slice 2 开始时先写一个最小 `discover_tools` 调用验证 config 映射。

### F-4：batch subprocess 错误传播语义需要显式定义（informational）

**Severity**：informational
**Plan 行文证据**：Slice 2 error handling（第 317-319 行）说"batch 子进程失败是 batch-level error，因为 per-url artifact 不可信"，但未定义具体的错误传播格式。
**代码证据**：OLD 脚本用 `subprocess.run()` 启动 per-url children，检查 returncode，收集 stdout/stderr。
**Challenge**：当 child process crash（非 diagnostics failure）时，`results.jsonl` 中该 URL 的条目应包含什么字段？是 `crash` bucket、`error` 字段、还是跳过该条目？Plan 的 `comparison_bucket` 枚举中没有 `crash` 或 `child_process_error` 类别。

**裁决建议**：needs-more-evidence — implementation 应在 batch summary 中显式处理 child process crash 场景，建议新增 `child_process_error` bucket 或在 `results.jsonl` 中用 `status=crash` + `stderr_prefix` 字段记录。这不阻塞 plan approval，但应在 implementation report 中说明处理方式。

## Missing Evidence / Open Questions

无 blocking open questions。

以下为 implementation 阶段需要确认的 evidence：

1. `WebToolsConfig` 的确切字段名、类型和必填性 — 影响 CLI args 到 config 的映射代码。
2. `LegacyToolDeclarationCollector` 是否是 `discover_tools` 的唯一 collector 实现 — 影响 diagnostics 是否需要额外适配。
3. 当前 `fetch_web_page` 在 `ToolCompletedOutcome` 中返回的 `value` 结构（`WebPayload` 的 JSON 表示）— 影响 fetch profile 字段提取。

## Residual Risks

与 plan 声明的 residual risks 一致：

- live network 结果天然不稳定；F02 通过 explicit opt-in 和 evidence-only 输出降低风险。
- Playwright 安装与浏览器 channel 因机器而异；F02 将缺失记录为 diagnostic profile failure。
- current `fetch_web_page` internals 后续可能变化；通过 current `ToolDefinition.callable` 调用比导入 private fetch helper 更低耦合。
- diagnostic JSON 是 utility-level schema；F03 可能需要进一步裁决哪些字段进入 Web smoke evidence。
- 输出可能包含敏感 headers 或本地 storage-state path；implementation 必须脱敏。

## Recommendation for Next Gate

Plan 可以进入 implementation gate。Implementation 应：

1. 先确认 F-1 的 sync/async 架构策略，在实现报告中显式记录。
2. 在 Slice 2 开始时先写一个最小 `discover_tools` 调用，验证 config 映射和 `ToolCompletedOutcome.value` 结构（F-3）。
3. 处理 batch subprocess crash 场景（F-4），在实现报告中说明 bucket 策略。
4. 运行 `tests/tools/web/test_web_tools_provider.py` 确保 forbidden import guard 继续覆盖新增的 `utils/diagnose_web_access.py`（AST guard 是否扫描 `utils/` 需要确认，若不扫描则需要在 `test_diagnose_web_access.py` 中新增同等 guard）。
5. 确认 pyright 对 `utils/` 目录的覆盖范围，确保新增代码通过类型检查。
