# WU-TOOLS-01 Plan Fix — AgentCodex

Gate: plan fix  
Work unit: WU-TOOLS-01  
Status: ready-for-rereview

## Changed Plan Sections

- `Status`: 更新为 `ready for plan re-review`。
- `Design Document Alignment / ToolRuntime`: 明确迁移工具只声明当前 `ToolTruncateSpec`，adapter 只收集和转发当前截断声明。
- `Package Placement Decisions / Adapter`: 收紧 `_legacy_adapter` helper 允许范围，禁止未分类 helper，禁止 collector 承担 OLD registry 执行、路径 enforcement、truncation 或 fetch-more 语义。
- `Contract / Schema / State / Public Interface Changes`: 补齐 input projection、response projection、current truncate mapping、path metadata/enforcement 边界。
- `Exact OLD Source Scope`: 增加 import-closure inventory 规则，并要求 `utils_tools.py` 等 helper 先分类再决定。
- `Implementation Decisions`: 增加 `asyncio.to_thread` 并发策略、Fins ingestion 保守默认和 blocker artifact。
- `Slice S2`: 补齐 collector / definition adapter 的类名、函数名、 typed signatures、collector 输出形态、adapter 输出形态和测试断言。
- `Slice S3/S4/S5/S6`: 补齐路径安全测试、import closure stop condition、Fins ingestion blocker、provider concurrency 和 ToolRuntime accept stop condition。

## Accepted Findings Fixed

- A1 Adapter API Is Not Code-Generation-Ready: 已定义 `CollectedLegacyTool`、`LegacyToolDeclarationCollector`、`ToolPathValidationPolicy`、`ProjectedLegacyCall`、`LegacyToolConcurrencyPolicy`、`adapt_collected_tool(...)`、`adapt_collected_tools(...)` 等签名；明确 provider slices 消费 `tuple[CollectedLegacyTool, ...]`，输出 current `ToolDefinition` with async `ToolCallable`。
- A2 Path Metadata And Enforcement Boundary Must Be Unambiguous: 已声明 `file_path_params` 只从 decorator metadata 收集；`register_allowed_paths(...)` 若存在也不提供 trusted enforcement；路径失败映射当前 `ToolFailedOutcome(error="permission_denied")`；S3 增加 Doc function body 不被调用的测试要求。
- A3 Current `ToolTruncateSpec` Declaration Must Be Fully Specified: 已要求迁移声明使用 current `dayu.contracts.tool_schema.ToolTruncateSpec` / `ToolTruncationStrategy`；adapter helper 只接受/存储 current `ToolTruncateSpec | None`；补齐 OLD strategy/limits/target_field/continuation_hint 到当前 spec 的规则；测试禁止 OLD `ToolTruncateSpec`、OLD `TruncationManager`、OLD `fetch_more` 和 OLD projection。
- A4 Input And Response Projection Needs Concrete Adapter Contract: 已定义 `project_tool_call_arguments(...)`、`project_legacy_return(...)`、`project_legacy_exception(...)`；明确 direct pass-through 条件、coercion/validation 条件、projection failure 行为、success/failure envelope 和异常映射；S2-S6 增加 direct/projected input 与 success/failure response 测试。
- A5 Fins Ingestion Conditional Stop Needs Artifact Destination: 已指定 `docs/reviews/wu-tools-01-s4-ingestion-blocker-codex.md`；写明 blocker 必填内容；默认先迁移 read tools，仅在同步 completed/failed mapping 有直接证据时纳入 ingestion。
- A6 `asyncio.to_thread` Requires Concurrency Boundary: 已指定默认 per-tool serialization，provider 可选择 provider-wide serialization；只有有直接证据和并发 ToolRuntime 测试时才允许 concurrent；S2/S5/S6 增加并发测试/stop condition。
- A7 Slice Stop Conditions And Ambiguous `may` Wording Need Tightening: 已收紧 helper 允许范围，新增 import-closure inventory；S6 增加 provider ToolRuntime accept 失败 stop condition；Doc/Fins/Web slices 增加未分类 helper / OLD 禁用依赖 stop condition。
- N1 Exact Old Helper Import Closure needs-more-evidence: 未猜测最终 helper 列表；改为每个迁移 slice copy 前必须 inventory 并分类为 `included`、`excluded-with-reason` 或 `blocker`。

## Residual Risks After Fix

- OLD helper import closure 仍需 implementation slice 用直接 import evidence 分类；plan 已阻止未分类 helper 被复制。
- Web shared sessions / Playwright fallback 的并发安全仍需 S5 直接证据确认；默认策略保守序列化。
- Fins ingestion 是否纳入仍是条件性事项；若同步 completed/failed mapping 不能证明，S4 必须写 blocker artifact。

## Files Written

- `docs/host/wu-tools-01-migration-plan.md`
- `docs/reviews/wu-tools-01-plan-fix-codex.md`

## Status

ready-for-rereview
