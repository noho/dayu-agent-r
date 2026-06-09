# WU-TOOLS-01-F02 Plan Re-Review

## Gate

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- 当前 gate：re-review
- Reviewer：MiMo
- 日期：2026-06-09
- Plan artifact：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Controller adjudication：`docs/reviews/wu-tools-01-f02-plan-review-controller-adjudication.md`
- Fix artifact：`docs/reviews/wu-tools-01-f02-plan-fix-codex.md`

## Verdict

**pass**

所有 10 项 controller accepted findings 均已在 plan artifact 中修复，修复质量合格。未发现新 blocking issue 或 scope creep。

## Reviewed Scope

只检查 controller adjudication 中 accepted 的 10 项 findings 是否在 plan artifact 中得到修复，以及是否引入新 blocking issue 或 scope creep。

## Accepted Findings Status

| # | 来源 | Finding | 状态 | 证据 |
|---|---|---|---|---|
| 1 | MiMo F-1 | sync/async bridge 策略 | **已修复** | plan 第 211-213 行：CLI 入口保持同步；只在 `ToolDefinition.callable` 边界用 `asyncio.run(...)`；Playwright 继续用 sync API；F02 不支持嵌入已有 event loop。 |
| 2 | MiMo F-2 | raw headers 选择规则 | **已修复** | plan 第 246-252 行：优先复用 current Web helper 且不扩大 production public surface；否则用本地 diagnostic headers 并标注 `raw_requests_header_source="diagnostic_local"`。 |
| 3 | MiMo F-3 | CLI config 映射 | **已修复** | plan 第 218-228 行：完整 CLI→`WebToolsConfig`→JSON 类型映射表，覆盖 `request_timeout_seconds`、`fetch_truncate_chars`、`allow_private_network_url`、`playwright_channel`、`playwright_storage_state_dir` 及默认字段处理。 |
| 4 | MiMo F-4 | batch child crash 处理 | **已修复** | plan 第 283 行与第 363 行：`child_process_error` 非 comparison status，保留 `return_code`、有界 stderr/stdout prefix、`diagnostic_path=null`；`summary.json` / `summary.md` 单独统计。 |
| 5 | DS F-1 | `_DiagnosticCancellationToken` | **已修复** | plan 第 236-241 行：私有类实现 `CancellationToken` protocol，`is_cancelled()→False`、`cancel_reason()→None`、`requested_at()→None`；不连接 Host 取消状态。 |
| 6 | DS F-2 | `discover_tools` 路径歧义 | **已修复** | plan 第 215-216 行：指定 `dayu.tools.web.provider.discover_tools(spec)` 读取 `ToolsDiscoveryProviderOutput.definitions`；明确禁止使用 `dayu.runtime.tools_discovery.discover_tools(...)` 聚合入口。 |
| 7 | DS F-3 | tests vs utils 豁免说明 | **已修复** | plan 第 376 行：说明 parser/classifier/adapter 逻辑非平凡且产出 F03 evidence，shell wrapper / corpus 可轻量覆盖。 |
| 8 | DS F-4 | F03 最小稳定 schema | **已修复** | plan 第 202-207 行：定义 `schema_version`、`url`、`comparison_bucket` 顶层必稳字段；per-path `sampled`/`ok`/`elapsed_seconds`/`status`/`error`；`results.jsonl` 行级摘要字段；schema mismatch 留给 F03。 |
| 9 | DS F-5 | comparison bucket 决策树 | **已修复** | plan 第 281-296 行：13 步确定性分类，覆盖 child_process_error、current outcome shapes 归一化、requests/playwright sampled/ok 归一化、challenge detection 优先级、所有 bucket 组合。 |
| 10 | DS F-6/7 | 授权边界与 utils 编码约束 | **已修复（确认性证据）** | 无需 plan 修改；plan 原文已正确处理。 |

**已修复：10 / 10**

## New Findings

未发现新 blocking issue。

### NF-1：comparison bucket decision tree 第 5 步 challenge 例外条件略模糊（informational）

- **位置**：plan 第 288 行
- **当前写法**："若 Playwright 采样且 challenge signals 为真，优先返回 `playwright_challenge_detected`，除非所有路径均完全成功且 challenge 只作为低置信提示；该例外需由 deterministic test 固定。"
- **分析**："低置信提示"的判定标准未在 plan 中定义。但 plan 已明确该例外"需由 deterministic test 固定"，implementation 时可通过 test fixture 锁定行为。不阻塞。
- **严重程度**：informational
- **建议**：implementation 时在 test 中显式覆盖该例外 case，定义 challenge 信号的置信度阈值。

## Residual Risks

与 plan 声明的 residual risks 一致，re-review 确认无新增：

- live network 结果不稳定 → opt-in + evidence-only（confirmed）
- Playwright 安装差异 → diagnostic profile failure（confirmed）
- `fetch_web_page` internals 变化 → `ToolDefinition.callable` 低耦合（confirmed）
- diagnostic JSON schema 稳定性 → F03 最小子集已定义（confirmed）
- 敏感 header / storage-state path → 脱敏 + 不内联（confirmed）
- NF-1 challenge 例外条件 → deterministic test 固定（low risk）

## Recommendation for Next Gate

Plan 可以进入 implementation gate。所有 accepted findings 已修复，无新 blocking issue，scope 无漂移。

Implementation 应：

1. 按 Slice 1 → Slice 2 → Slice 3 顺序推进。
2. Slice 2 开始时先验证 adapter 路径可用（单 URL 调用 current `fetch_web_page` 产出有效 outcome）。
3. comparison bucket decision tree 的 challenge 例外（NF-1）在 deterministic test 中显式覆盖。
4. 若遇到 stop condition，立即停止并报告 Controller。
