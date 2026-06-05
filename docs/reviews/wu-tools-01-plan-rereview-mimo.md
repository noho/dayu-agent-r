# WU-TOOLS-01 Plan Re-Review — AgentMiMo

Reviewer: AgentMiMo
Review timestamp: 2026-06-05T22:31:40+08:00
Reviewed target: `docs/host/wu-tools-01-migration-plan.md` (plan fix by AgentCodex)
Fix report: `docs/reviews/wu-tools-01-plan-fix-codex.md`
Controller adjudication: `docs/reviews/wu-tools-01-plan-review-controller-adjudication.md`
Scope: Re-review only Controller accepted findings A1-A7 and N1; not a full re-scan.

## 1. Review Method

逐条检查 Controller accepted findings 是否已在 plan fix 中修复。证据来源为更新后的 plan artifact 和 fix report。不重新展开全量旧源码扫描；如证据不足，标为 needs-more-evidence。

## 2. Re-Reviewed Findings Status

### A1 Adapter API Is Not Code-Generation-Ready — 已修复

- **Controller 要求**: 定义 concrete class/function names 和 typed signatures for the new adapter collector and definition adapter；定义 collector output shape；定义 adapter output shape as current `ToolDefinition` with async `ToolCallable`。
- **Plan fix 内容**: Plan L403-439 新增完整的 Adapter API contract section，包含：
  - `LegacyToolKeywordValue` 类型定义
  - `LegacySyncToolCallable` protocol（typed `__call__` 签名）
  - `CollectedLegacyTool` dataclass（9 个 typed fields: `name`, `callable`, `schema`, `tags`, `truncate`, `file_path_params`, `execution_context_param_name`, `display_name`, `summary_params`）
  - `LegacyToolDeclarationCollector` class（`register(...)`, `register_allowed_paths(...)`, `collected_tools()` 方法签名）
  - `ToolPathValidationPolicy` dataclass（`allowed_roots`, `file_path_params`, `must_exist`）
  - `ProjectedLegacyCall` dataclass（`keyword_arguments: Mapping[str, JsonValue]`）
  - `LegacyToolConcurrencyPolicy` enum（`serial_per_tool`, `serial_per_provider`, `concurrent_after_evidence`）
  - `project_tool_call_arguments(...)`, `project_legacy_return(...)`, `project_legacy_exception(...)`, `adapt_collected_tool(...)`, `adapt_collected_tools(...)` 完整函数签名
- **裁决**: 接口具体到可实施。实施 Agent 可直接按签名编码，无需自行设计 API。
- **状态**: **已修复**

### A2 Path Metadata And Enforcement Boundary Must Be Unambiguous — 已修复

- **Controller 要求**: (a) collector API 不隐含旧 `ToolRegistry.register_allowed_paths` enforcement 语义；(b) `file_path_params` metadata 从旧 decorator 收集并由 provider/adapter 路径校验消费；(c) 路径校验失败映射 `ToolFailedOutcome`；(d) 测试证明 Doc function body 不负责路径安全。
- **Plan fix 内容**:
  - (a) L423: `register_allowed_paths(...)` 明确声明 "exists only so unmodified OLD registration functions remain callable... records no trusted whitelist, performs no path validation, and must not be consumed as path safety evidence"
  - (b) L259: "file_path_params metadata is collected from migrated @tool(...) declarations and consumed by provider/adapter path validation"
  - (c) L262: "Failed path validation returns current ToolFailedOutcome(ToolResultFailure(ok=False, error='permission_denied', ...)) before the migrated Doc function body is called"
  - (d) L527: "Tests prove Doc function bodies are not responsible for path safety by using a spy/fixture callable or call counter"; L528: "Tests prove file_path_params metadata is collected from old decorators and used by provider/adapter path validation"; L529: "Tests prove LegacyToolDeclarationCollector.register_allowed_paths(...) is not used as the trusted enforcement source"
- **裁决**: Doc function body 不负责路径安全；`file_path_params` 由 provider/adapter 使用；`register_allowed_paths` 仅为兼容旧调用签名的 metadata 收集，不提供 trusted enforcement。边界明确。
- **状态**: **已修复**

### A3 Current `ToolTruncateSpec` Declaration Must Be Fully Specified — 已修复

- **Controller 要求**: (a) 迁移工具使用 current `ToolTruncateSpec`；(b) retained old helper 只接受/emit current `ToolTruncateSpec`；(c) OLD truncate metadata → current `ToolTruncateSpec` mapping table；(d) 测试禁止 OLD `ToolTruncateSpec`/`TruncationManager`/`fetch_more`/truncate projection。
- **Plan fix 内容**:
  - (a) L236: "Migrated imports must point truncate declarations to current dayu.contracts.tool_schema.ToolTruncateSpec and ToolTruncationStrategy"
  - (b) L237-239: "The adapter declaration helper accepts only ToolTruncateSpec | None... Do not copy OLD ToolTruncateSpec as a runtime contract"
  - (c) L241-251: 完整 mapping rules 覆盖 `enabled=False/True`, `strategy="text_chars"/"text_lines"/"list_items"/"binary_bytes"`, `limits`, `target_field`, `field_path`, `ttl_seconds`, `continuation_hint`
  - (d) L252: "Tests must prove migrated declarations import/use current ToolTruncateSpec, and no OLD ToolTruncateSpec, OLD TruncationManager, OLD fetch_more, or OLD truncate/fetch-more projection is imported or used"; S2 L464-465 重复断言
- **裁决**: Mapping table 具体到每个旧策略/字段；测试断言明确禁止旧组件。实施 Agent 可直接按 mapping 规则编码。
- **状态**: **已修复**

### A4 Input And Response Projection Needs Concrete Adapter Contract — 已修复

- **Controller 要求**: (a) 定义 input projection API 和 error behavior；(b) 定义 direct pass-through 条件和 coercion/validation 条件；(c) 定义 response projection API for success/old envelopes/errors；(d) slice-level tests。
- **Plan fix 内容**:
  - (a) L211: `project_tool_call_arguments(declaration, call, path_policy) -> ProjectedLegacyCall | ToolFailedOutcome`；L214: projection failures return `ToolFailedOutcome(ToolResultFailure(ok=False, error="invalid_argument", ...))` and migrated function is not called
  - (b) L213: 6 项 direct pass-through 条件（schema field names match, required fields present, no path param, no enum/range/array/scalar coercion, no execution-context injection, JSON value types match）；L214: coercion/validation 条件（schema defaults, optional arrays, numeric bounds, enums, path normalization, string normalization, unknown-field rejection, execution-context injection）
  - (c) L224-230: response projection API（`project_legacy_return(...)`, `project_legacy_exception(...)`），覆盖 plain dict/list/string/number/bool/null、OLD ok/value envelope、OLD failure envelope、ToolBusinessError、ToolArgumentError、path validation、missing files、unexpected exceptions
  - (d) L215: "Provider slices must test at least one representative call where arguments pass directly and one call where adapter projection/coercion/validation is required"; L231: "Provider slices must test response projection for representative success and failure paths"
- **裁决**: API 签名、条件判定、错误映射和测试要求均具体。
- **状态**: **已修复**

### A5 Fins Ingestion Conditional Stop Needs Artifact Destination — 已修复

- **Controller 要求**: (a) blocker artifact path；(b) blocker content（affected tools, direct evidence, why mapping insufficient, required semantics, proposed owner/destination）；(c) conservative default（migrate read tools first）。
- **Plan fix 内容**:
  - (a) L311/S4 L587: `docs/reviews/wu-tools-01-s4-ingestion-blocker-codex.md`
  - (b) L588: "affected tools, direct evidence, why completed/failed mapping is insufficient, required wait/awaiting semantics, proposed owner/destination, and whether a later wait-adapter work unit is needed"
  - (c) L586: "Conservative default: migrate read tools first. Ingestion tools are included only when direct code evidence proves synchronous completed/failed mapping with no job polling, callback, external wait, or ToolAwaitingOutcome requirement"
- **裁决**: artifact 路径、必填内容和保守默认均已明确。
- **状态**: **已修复**

### A6 `asyncio.to_thread` Requires Concurrency Boundary — 已修复

- **Controller 要求**: (a) thread-safety decision for old sync callables；(b) 默认 per-tool serialized，provider-wide for known non-thread-safe，concurrent only after evidence；(c) tests 或 stop condition。
- **Plan fix 内容**:
  - (a) L313 (Implementation Decision #12): "Default old sync callable execution is serialized per tool name with an adapter-owned asyncio.Lock around asyncio.to_thread. A provider chooses provider-wide serialization for known shared mutable state. Concurrent execution is allowed only after direct code evidence and a concurrent ToolRuntime test prove the specific callable is safe."
  - (b) L431: `LegacyToolConcurrencyPolicy` enum with `serial_per_tool`, `serial_per_provider`, `concurrent_after_evidence`
  - (c) S2 L466: "Default per-tool serialization is tested by concurrent adapter calls proving the same migrated callable is not entered concurrently"; S6 L748: "Concurrent ToolRuntime calls either pass under the declared concurrency policy or stop with a documented provider-specific concurrency blocker"
- **裁决**: 三级并发策略明确，默认保守序列化，测试覆盖并发场景。
- **状态**: **已修复**

### A7 Slice Stop Conditions And Ambiguous "May" Wording Need Tightening — 已修复

- **Controller 要求**: (a) 替换 ambiguous "may" wording 为 explicit lists/inventory steps；(b) S6 stop condition for provider ToolRuntime accept failure；(c) dependency inventory checks for old helpers。
- **Plan fix 内容**:
  - (a) L168-178: Adapter 文件列表精确到 9 个文件；L175: "Any additional OLD helper file is forbidden until an implementation slice writes an import-closure inventory classifying it as included, excluded-with-reason, or blocker"; L282-289: import-closure inventory rule 明确每个 helper 必须分类，"A helper that is not classified must not be copied"
  - (b) L756: S6 stop condition "Stop if any provider fails ToolRuntime accept integration at S6 combined level"
  - (c) L286-289: "Before S1, S3, S4 and S5 copy old files, the implementation agent must run an import-closure inventory... must list each OLD helper as included, excluded-with-reason, or blocker... A helper that is not classified must not be copied"
- **裁决**: "may" 已替换为精确文件列表 + inventory 规则；S6 stop condition 覆盖 provider accept failure；import-closure inventory 作为每个 slice 的前置要求。
- **状态**: **已修复**

### N1 Exact Old Helper Import Closure — 已修复（作为 inventory requirement）

- **Controller 要求**: (a) explicit import-closure inventory step before each migration slice copies old files；(b) classify every old helper as included/excluded-with-reason/blocker。
- **Plan fix 内容**:
  - L284-289: Import-closure inventory rule section，要求 S1/S3/S4/S5 copy 前必须完成 inventory
  - L288: "A helper that is not classified must not be copied"
  - L289: "If an import closure requires OLD ToolRegistry, OLD TruncationManager, OLD fetch_more, OLD truncate/fetch-more projection, Host/Engine runtime state, or OLD UI files, stop and write a blocker instead of widening scope silently"
  - 各 slice (S3 L498, S4 L572, S5 L657) 均包含 "Before copying, complete an import-closure inventory" 要求
- **裁决**: Plan 未猜测最终 helper 列表，而是将 import-closure inventory 作为 implementation requirement。这是 N1 的正确处理方式。
- **状态**: **已修复**（作为 inventory requirement，不猜测）

## 3. New Findings

无新增 findings。Plan fix 对 A1-A7 和 N1 的修复覆盖完整，未引入新的架构边界问题或契约缺失。

## 4. Blocking Open Questions

无。所有 Controller accepted findings 均已修复，无新增 blocker。

## 5. Residual Risks

- OLD helper import closure 仍需 implementation agent 用直接 import evidence 分类；plan 已阻止未分类 helper 被复制。此为 by-design residual，不是 plan 缺陷。
- Web shared sessions / Playwright fallback 的并发安全仍需 S5 直接证据确认；默认策略保守序列化。此为 implementation-time 验证事项，plan 已覆盖。
- Fins ingestion 是否纳入仍是条件性事项；若同步 completed/failed mapping 不能证明，S4 必须写 blocker artifact。Plan 已指定 artifact 路径和必填内容。

## 6. Pass/Fail Recommendation

**PASS**

Plan fix 完整修复了 Controller adjudication 中的全部 8 项 accepted findings (A1-A7, N1)。Adapter API 具体到可实施，path metadata/enforcement 边界明确，ToolTruncateSpec mapping 规则完整，input/response projection contract 具体，Fins ingestion blocker destination 和保守默认已明确，asyncio.to_thread 并发策略三级分明，ambiguous "may" wording 已替换为精确文件列表 + inventory 规则，old helper import closure 作为 implementation inventory requirement 处理。Plan 可进入 implementation gate。
