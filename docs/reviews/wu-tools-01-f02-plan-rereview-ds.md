# WU-TOOLS-01-F02 Plan Re-Review

## Gate

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- 当前 gate: re-review
- Reviewer: AgentDS
- 日期: 2026-06-09
- Plan artifact: `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Original review artifact: `docs/reviews/wu-tools-01-f02-plan-review-ds.md`
- MiMo review artifact: `docs/reviews/wu-tools-01-f02-plan-review-mimo.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f02-plan-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-tools-01-f02-plan-fix-codex.md`
- Re-review artifact: `docs/reviews/wu-tools-01-f02-plan-rereview-ds.md`

## Verdict

**pass**

All 10 Controller-accepted findings have been fixed in the plan artifact. No new blocking issues introduced. No scope creep detected.

## Accepted Findings Status

| # | Source | Finding | Status | Plan Evidence |
|---|---|---|---|---|
| 1 | MiMo F-1 | sync/async bridge strategy | 已修复 | 实现决策 #1 第 211–213 行：CLI 同步入口、`asyncio.run()` 仅包裹 async callable、Playwright 继续 sync API、F02 不支持嵌套 event loop |
| 2 | MiMo F-2 | raw requests headers rule | 已修复 | 实现决策 #2 第 245–252 行：优先复用 current helper 且不扩大 public surface；否则用本地 diagnostic headers 并标注 `raw_requests_header_source="diagnostic_local"` |
| 3 | MiMo F-3 | CLI config mapping | 已修复 | 实现决策 #1 第 219–227 行：完整映射表覆盖 `provider`/`request_timeout_seconds`/`max_search_results`/`fetch_truncate_chars`/`allow_private_network_url`/`playwright_channel`/`playwright_storage_state_dir`，含 JSON value 类型与规则 |
| 4 | MiMo F-4 | batch child crash handling | 已修复 | 决策树步骤 1 第 283 行 + Slice 2 error handling 第 363–364 行：`status="child_process_error"`、保留 `return_code`/`stderr_prefix`/`stdout_prefix`/`diagnostic_path=null`，不混入普通 comparison bucket，`summary.json`/`summary.md` 单独统计 |
| 5 | DS F-1 | `_DiagnosticCancellationToken` | 已修复 | 实现决策 #1 第 236–242 行：私有 dataclass/简单类实现 `CancellationToken` protocol，`is_cancelled()` 恒 False、`cancel_reason()` 恒 None、`requested_at()` 恒 None |
| 6 | DS F-2 | `discover_tools` path | 已修复 | 实现决策 #1 第 215–217 行：明确 `dayu.tools.web.provider.discover_tools(spec)` 或等价 provider entry，返回 `ToolsDiscoveryProviderOutput`，读 `.definitions`；禁止 `dayu.runtime.tools_discovery.discover_tools` |
| 7 | DS F-3 | tests vs `utils/` exemption rationale | 已修复 | Slice 3 test rationale 第 376–377 行：parser/classifier/adapter 非平凡且产出 F03 可能消费的 evidence，需 deterministic tests；shell wrapper/corpus 可轻量检查 |
| 8 | DS F-4 | F03 minimal schema subset | 已修复 | 第 202–207 行：F03 最小稳定子集含 `schema_version`/`url`/`comparison_bucket`/per-path `sampled`/`ok`/`elapsed_seconds`/`status`/`error`；schema mismatch 留给 F03 裁决 |
| 9 | DS F-5 | comparison bucket decision tree | 已修复 | 第 281–295 行：13 步确定性决策树，覆盖 child process crash、outcome 归一化（含 `ToolCancelledOutcome`/`ToolAwaitingOutcome`）、Playwright skip/failure、challenge signals 优先、全部 12 bucket 的判定条件与 fallback |
| 10 | DS F-6 / F-7 | authorization boundary / `utils/` coding | 证据保留 | 实现决策 #8 第 307–309 行保持授权边界；实现决策 #6 第 297–301 行保持强类型与中文 docstring；Controller 已确认无需修改 |

**修复统计**: 10/10 accepted findings 已修复或证据保留。

## New Findings

### NF-1 — LOW — decision tree 步骤 5 的 challenge 例外条件未量化

**Severity**: LOW（不影响 implementation，但 implementation 需自行定义阈值）

**Plan 行文证据**: 决策树步骤 5 第 287 行：`"除非所有路径均完全成功且 challenge 只作为低置信提示；该例外需由 deterministic test 固定。"`

**分析**: "低置信提示"没有量化标准——哪些 challenge signals 算"低置信"、哪些算"高置信"由 implementation 判断。Plan 将定义权委派给 deterministic tests 是合理的工程实践，但 implementation 需要在 test fixture 中显式定义阈值。

**裁决**: 不阻塞。Implementation 在写 challenge classification tests 时自然会定义具体信号分类。不要求 plan 回退。

## Scope Creep Check

- Plan artifact 位置正确：`docs/host/` 下，未扩散到 review/controller 目录。
- 修改范围未变：仍限于 `utils/diagnose_web_access.py`、shell wrapper、corpus、focused tests。
- 未新增 Host/Engine/ToolRuntime contract 变更。
- 未新增 CI workflow 定义。
- 未扩展 F03 scope 或 F02 成功信号。
- 新增内容（decision tree、schema subset、config mapping table、CancellationToken definition）均为 Controller 明确要求的 fix，属于 plan 内细化，非 scope creep。

结论：无 scope creep。

## Missing Evidence / Open Questions

无 blocking open questions。

以下 implementation 阶段需确认的 evidence（与 original review 一致）：

1. `WebToolsConfig` 的确切字段名和类型——plan 已提供 mapping table，implementation 需按表构造 `spec.config` dict。
2. `ToolCompletedOutcome.value` 的 `WebPayload` JSON 结构——影响 fetch profile 字段提取，implementation 需先验证。
3. Batch subprocess 环境假设——`python -m utils.diagnose_web_access` 在子进程中需要 `.venv` 激活和 `PYTHONPATH` 设置。

## Residual Risks Classification

| Risk | Severity | Mitigation Status | Residual |
|---|---|---|---|
| live network 结果天然不稳定 | MEDIUM | explicit opt-in + evidence-only 输出 | 接受——F02 不承诺稳定性 |
| Playwright 安装/浏览器 channel 差异 | MEDIUM | 缺失记录为 diagnostic profile failure | 接受——F02 只输出证据 |
| `fetch_web_page` internals 变化 | LOW | `ToolDefinition.callable` 耦合低于 private import | 接受 |
| diagnostic JSON schema 跨 WU 稳定性 | LOW | 已定义 F03 最小稳定子集 + schema_version | 接受——F03 需独立声明依赖 |
| 敏感 header/storage-state path 泄露 | LOW | 已添加脱敏规则 + 禁止内联 storage state 内容 | 接受 |
| `asyncio.run()` 与已有 event loop 冲突 | LOW | Plan 明确 F02 不支持嵌套 event loop | 接受——若后续需要 async entry，需独立 WU |
| decision tree challenge 例外阈值未量化 | LOW | 委派给 deterministic tests | 接受——implementation 时会自然定义 |

## Recommendation for Next Gate

Plan 已满足 accepted-plan commit 条件。建议进入 implementation gate，按 Slice 1 → Slice 2 → Slice 3 顺序推进。

Implementation 注意事项：

1. Slice 2 开始前，先用最小 `discover_tools` 调用验证 config mapping 和 `ToolCompletedOutcome.value` 结构。
2. 实现 `_DiagnosticCancellationToken` 作为 Slice 2 adapter 的第一步。
3. Decision tree implementation 必须与 plan 的 13 步顺序一致，并以 synthetic profile matrix 做 deterministic test。
4. Batch subprocess 实现时确认 `.venv` 和 `PYTHONPATH` 环境传递。
5. AST/import guard test 必须覆盖 `utils/diagnose_web_access.py` 文件。

## Review Methodology

- 逐条对照 Controller adjudication 的 required plan fix 与 plan artifact 对应行文。
- 验证每项 fix 的完整性：是否覆盖 Controller 要求的所有要素。
- 检查 plan 内部一致性：fix 之间是否有矛盾、是否与原始非目标/scope 冲突。
- 扫描 scope creep：是否引入超出 Controller fix scope 的新内容。
- 未修改 plan artifact 或任何生产代码。
