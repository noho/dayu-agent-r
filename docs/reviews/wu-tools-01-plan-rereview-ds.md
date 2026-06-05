# WU-TOOLS-01 Plan Re-Review — AgentDS

**日期**：2026-06-05 22:32
**Gate**：plan re-review
**Review Type**：Controller accepted findings 修复验证
**Review Target**：
- `docs/host/wu-tools-01-migration-plan.md`（已修复版本）
- `docs/reviews/wu-tools-01-plan-fix-codex.md`（修复报告）
- `docs/reviews/wu-tools-01-plan-review-controller-adjudication.md`（裁决基准）

**原 Review**：
- `docs/reviews/wu-tools-01-plan-review-ds.md`
- `docs/reviews/wu-tools-01-plan-review-mimo.md`

**Reviewer**：AgentDS
**Review Posture**：re-review only — 只验证 Controller accepted findings 是否已修复，不重新展开全量旧源码扫描，不修改文件。

---

## 1. Scope And Method

只检查 Controller adjudication 中标记为 `accepted` 的 8 项 findings（A1–A7, N1）在 plan fix 后是否已修复。每条 finding 对照 Controller 要求的 fix 项逐一验证，证据来源为 plan artifact 和 fix report。

不再展开新全量旧源码扫描。如 plan/fix artifact 本身证据不足，标 `needs-more-evidence`。

---

## 2. Accepted Findings 修复状态

### A1 — Adapter API Is Not Code-Generation-Ready

**Controller 要求**：
- 定义 adapter collector 和 definition adapter 的具体类/函数名和 typed signatures
- 定义 collector 输出形态供 provider slices 消费
- 定义 adapter 输出形态为 current `ToolDefinition` with async `ToolCallable`

**修复验证**：

Plan L403–440 新增 `Adapter API contract` 章节，逐一定义：

| 元素 | Plan 位置 | 状态 |
|------|-----------|------|
| `LegacyToolKeywordValue` 类型 | L405 | 已定义 |
| `LegacySyncToolCallable` protocol | L406–408 | 已定义（含 `__call__` 签名） |
| `CollectedLegacyTool` dataclass | L409–418 | 已定义（8 个字段，含类型） |
| `LegacyToolDeclarationCollector` 类 | L419–424 | 已定义（`register`, `register_allowed_paths`, `collected_tools`） |
| Collector 输出形态 | L424 | `tuple[CollectedLegacyTool, ...]` |
| `ToolPathValidationPolicy` dataclass | L425–428 | 已定义（3 个字段） |
| `ProjectedLegacyCall` dataclass | L430 | 已定义 |
| `LegacyToolConcurrencyPolicy` enum | L431 | 已定义（3 个值） |
| `project_tool_call_arguments(...)` | L433 | 已定义（含完整参数和返回类型） |
| `project_legacy_return(...)` | L434 | 已定义 |
| `project_legacy_exception(...)` | L435 | 已定义 |
| `adapt_collected_tool(...)` | L436 | 已定义（返回 `ToolDefinition`） |
| `adapt_collected_tools(...)` | L437 | 已定义（返回 `tuple[ToolDefinition, ...]`） |
| Adapter 输出绑定到 `ToolsDiscoveryProviderOutput` | L438–439 | 已明确 |

**裁决**：**已修复**。所有 Controller 要求的 API 元素均有具体类名/函数名、typed signatures 和输出形态。Provider slices 可基于 `tuple[CollectedLegacyTool, ...]` 和 `adapt_collected_tools(...)` 消费 adapter，implementation agent 不需要自行设计 API。

---

### A2 — Path Metadata And Enforcement Boundary Must Be Unambiguous

**Controller 要求**：
- 重命名或重述 collector API 使其不暗示 OLD `register_allowed_paths` enforcement
- 明确 `file_path_params` metadata 从旧 decorator 收集，由 provider/adapter 消费
- 明确路径校验失败映射到 current `ToolFailedOutcome`
- 增加测试证明 Doc function body 不负责路径安全

**修复验证**：

Plan 未选择重命名 `register_allowed_paths`，而是通过显式语义约束解决混淆：

| 要求项 | Plan 证据 | 状态 |
|--------|-----------|------|
| Collector 不承担 enforcement | L259: "must not treat `register_allowed_paths(...)` as OLD path enforcement" | 已满足 |
| 兼容方法明确禁止语义 | L422–424: "exists only so unmodified OLD registration functions remain callable... records no trusted whitelist, performs no path validation, and must not be consumed as path safety evidence" | 已满足 |
| `file_path_params` 元数据收集和使用 | L259: "`file_path_params` metadata is collected from migrated `@tool(...)` declarations and consumed by provider/adapter path validation" | 已满足 |
| 路径失败映射 | L262: "Failed path validation returns current `ToolFailedOutcome(ToolResultFailure(ok=False, error="permission_denied", message=..., hint=...))`" | 已满足 |
| Doc function body 不被调用测试 | S3 L527: "Tests prove Doc function bodies are not responsible for path safety by using a spy/fixture callable or call counter" | 已满足 |
| `file_path_params` 元数据消费测试 | S3 L528: "Tests prove `file_path_params` metadata is collected from old decorators and used by provider/adapter path validation" | 已满足 |
| Collector 不作为 trusted source 测试 | S3 L529: "Tests prove `LegacyToolDeclarationCollector.register_allowed_paths(...)` is not used as the trusted enforcement source for Doc tools" | 已满足 |

**关于未重命名的判断**：Controller adjudication 原文 A2 写的是 "Rename or restate the collector API so it does not imply old `ToolRegistry.register_allowed_paths` enforcement"。Plan 选择了 "restate" 路径——保留方法名以确保未修改的 OLD 注册函数可调用，但通过 L422–424 的显式语义约束和 S3 L529 的测试断言排除了 enforcement 语义。这是合理的替代方案，因为如果重命名，未修改的 OLD `register_doc_tools` 函数体中的 `registry.register_allowed_paths(...)` 调用将失败。

**裁决**：**已修复**。路径 metadata 收集与 enforcement 边界清晰，`register_allowed_paths` 语义被显式约束为 no-op，路径失败映射到 current outcome，Doc function body 安全测试已规划。

---

### A3 — Current `ToolTruncateSpec` Declaration Must Be Fully Specified

**Controller 要求**：
- 声明迁移工具使用 current `dayu.contracts.tool_schema.ToolTruncateSpec`
- 若保留旧 decorator/helper，只能接受/产出 current `ToolTruncateSpec`，不得作为 runtime contract
- 添加每个 OLD truncate 声明字段到 current `ToolTruncateSpec` 的映射表或显式规则
- 增加测试禁止 OLD `ToolTruncateSpec`、OLD `TruncationManager`、OLD `fetch_more`、OLD truncate/fetch-more projection

**修复验证**：

| 要求项 | Plan 证据 | 状态 |
|--------|-----------|------|
| 使用当前 `ToolTruncateSpec` | L235: "Migrated tools that need truncation must declare truncation using current `dayu.contracts.tool_schema.ToolTruncateSpec`" | 已满足 |
| Import 指向当前模块 | L236–237: "Migrated imports must point truncate declarations to current `dayu.contracts.tool_schema.ToolTruncateSpec` and `ToolTruncationStrategy`" | 已满足 |
| Adapter helper 只接受 current | L238: "The adapter declaration helper accepts only `ToolTruncateSpec \| None`, and the stored metadata must be `ToolTruncateSpec \| None` from the current contracts module" | 已满足 |
| 声明改写允许 | L239: "Migrated declaration-site edits are allowed to replace OLD string strategies such as `"text_chars"` with current `ToolTruncationStrategy.TEXT_CHARS`. This is a declaration import/argument rewrite, not a function signature or function body change." | 已满足 |
| 禁止复制 OLD 类 | L239–240: "Do not copy OLD `ToolTruncateSpec` as a runtime contract or as a declaration compatibility class" | 已满足 |
| OLD → current 映射规则 | L241–251: 完整映射表涵盖 `enabled`, `strategy` (4 种), `limits`, `target_field`, `field_path`, `ttl_seconds`, `continuation_hint` | 已满足 |
| 测试禁止 OLD | L252: "Tests must prove migrated declarations import/use current `ToolTruncateSpec`, and no OLD `ToolTruncateSpec`, OLD `TruncationManager`, OLD `fetch_more`, or OLD truncate/fetch-more projection is imported or used" | 已满足 |
| S2 断言覆盖 | S2 L463–465 预期断言逐项覆盖 | 已满足 |

**额外观察**：MiMo F1 关心的 OLD `@tool` 装饰器中 `ToolTruncateSpec(...)` 构造兼容性问题，plan L239 通过允许 declaration-site import/argument rewrite 处理——implementation agent 可将 OLD 的 `ToolTruncateSpec(enabled=True, strategy="text_chars", ...)` 改写为 current 兼容形式。但 plan 未逐字段比较新旧 `__post_init__` 的校验差异（例如旧类可能缺少 `field_path`/`ttl_seconds` 校验，新类可能拒绝旧参数组合）。这属于 implementation 执行细节，有 L239 的改写授权后 implementation agent 可自行处理，不构成 plan 层面的 blocker。

**裁决**：**已修复**。映射规则完整，测试覆盖充分，禁止项明确。

---

### A4 — Input And Response Projection Needs Concrete Adapter Contract

**Controller 要求**：
- 定义 input projection API 和错误行为
- 定义 direct pass-through 何时允许、何时需要 coercion/validation
- 定义 response projection API（success, OLD envelope, dict/list/string, business error, adapter validation failure）
- 添加 slice 级别测试

**修复验证**：

| 要求项 | Plan 证据 | 状态 |
|--------|-----------|------|
| Input projection API | L211–212: `project_tool_call_arguments(declaration: CollectedLegacyTool, call: ToolCallRequest, path_policy: ToolPathValidationPolicy \| None) -> ProjectedLegacyCall \| ToolFailedOutcome` | 已满足 |
| 错误行为 | L216–217: "Projection failures return `ToolFailedOutcome(ToolResultFailure(ok=False, error="invalid_argument", ...))` and the migrated function is not called" | 已满足 |
| Direct pass-through 条件 | L214–215: 6 项具体条件（schema field names match, required fields present, no path parameter, no coercion required, no execution-context injection, JSON types match） | 已满足 |
| Coercion/validation 条件 | L216: schema defaults, optional arrays, numeric bounds, enums, path normalization, string normalization, unknown-field rejection, execution-context injection | 已满足 |
| Response success API | L225: `project_legacy_return(tool_name, raw_value, started_at, finished_at) -> ToolCompletedOutcome \| ToolFailedOutcome` | 已满足 |
| Response exception API | L226: `project_legacy_exception(tool_name, error, started_at, finished_at) -> ToolFailedOutcome` | 已满足 |
| Plain value 映射 | L227: "Plain dict/list/string/number/bool/null returns become `ToolCompletedOutcome` with the value unchanged" | 已满足 |
| OLD envelope 解包 | L228: "OLD `{"ok": True, "value": ...}` envelopes are unwrapped to the `value` payload. OLD `truncation`, `continuation_hint`, `fetch_more_args` or projection-only fields are not carried" | 已满足 |
| OLD failure 映射 | L229: "OLD `{"ok": False, ...}` envelopes become `ToolFailedOutcome`" | 已满足 |
| 错误分类映射 | L230: `ToolBusinessError` → business error code, `ToolArgumentError` → `invalid_argument`, path validation → `permission_denied`, missing files → `file_not_found`, unexpected → `execution_error` | 已满足 |
| Slice 测试规划 | L217–218: 各 provider slice 必须测试 direct pass-through 和 projected/coerced input；L231: 各 slice 必须测试 success 和 failure response projection | 已满足 |
| S2 断言覆盖 | S2 L457–464 预期断言逐项覆盖 | 已满足 |

**裁决**：**已修复**。Input 和 response projection 的 API 契约、行为语义、错误分类和测试规划均完备。

---

### A5 — Fins Ingestion Conditional Stop Needs Artifact Destination

**Controller 要求**：
- 指定 blocker artifact 路径
- 指定 blocker 必填内容
- 保守默认：先迁移 read tools，仅在有直接证据时纳入 ingestion

**修复验证**：

| 要求项 | Plan 证据 | 状态 |
|--------|-----------|------|
| Blocker artifact 路径 | L311: `docs/reviews/wu-tools-01-s4-ingestion-blocker-codex.md` | 已满足 |
| Blocker 必填内容 | L588: "affected tools, direct evidence, why completed/failed mapping is insufficient, required wait/awaiting semantics, proposed owner/destination, and whether a later wait-adapter work unit is needed" | 已满足 |
| 保守默认 | L310–311: "Conservative default: migrate read tools first. Ingestion tools are included only when direct code evidence proves synchronous completed/failed mapping with no job polling, callback, external wait, or `ToolAwaitingOutcome` requirement." | 已满足 |
| S4 stop condition 完整 | L617–619: 明确 ingestion 的 stop/classify 条件与 blocker artifact 关联 | 已满足 |

**裁决**：**已修复**。Blocker 路径、内容和默认策略均明确。

---

### A6 — `asyncio.to_thread` Requires Concurrency Boundary

**Controller 要求**：
- 添加线程安全决策
- 定义 adapter execution 是 per-tool serialized、provider-serialized 还是显式允许 concurrent（需证据）
- 增加并发测试或 documented stop condition

**修复验证**：

| 要求项 | Plan 证据 | 状态 |
|--------|-----------|------|
| 默认序列化策略 | L313: "Default old sync callable execution is serialized per tool name with an adapter-owned `asyncio.Lock` around `asyncio.to_thread`" | 已满足 |
| Provider-wide 序列化 | L313: "A provider chooses provider-wide serialization for known shared mutable state" | 已满足 |
| Concurrent 的条件 | L313: "Concurrent execution is allowed only after direct code evidence and a concurrent ToolRuntime test prove the specific callable is safe" | 已满足 |
| ConcurrencyPolicy enum | L431: `LegacyToolConcurrencyPolicy` 含 `serial_per_tool`, `serial_per_provider`, `concurrent_after_evidence` | 已满足 |
| S2 并发测试 | S2 L466: "Default per-tool serialization is tested by concurrent adapter calls proving the same migrated callable is not entered concurrently" | 已满足 |
| S5 Web concurrency | S5 L689: "Web provider serialization policy is documented and tested if shared sessions/Playwright fallback are not proven concurrent-safe" | 已满足 |
| S6 并发 stop | S6 L748: "Concurrent ToolRuntime calls either pass under the declared concurrency policy or stop with a documented provider-specific concurrency blocker" | 已满足 |

**裁决**：**已修复**。策略分层清晰（per-tool → provider-wide → concurrent_after_evidence），有显式 enum 和测试覆盖。

---

### A7 — Slice Stop Conditions And Ambiguous "may" Wording Need Tightening

**Controller 要求**：
- 替换 ambiguous "may" 措辞为显式 helper 列表或 per-slice inventory 步骤
- 添加 S6 stop condition：provider ToolRuntime accept 失败
- 添加 old helper 文件的依赖 inventory 检查（分类为 included/excluded/needs-more-evidence）

**修复验证**：

| 要求项 | Plan 证据 | 状态 |
|--------|-----------|------|
| "may" 替换 | L169–174: `_legacy_adapter` 内容从 "may contain" 变为精确 6 个文件列表 | 已满足 |
| 未分类 helper 禁止 | L175: "Any additional OLD helper file is forbidden until an implementation slice writes an import-closure inventory classifying it as included, excluded-with-reason, or blocker" | 已满足 |
| Import-closure inventory 规则 | L286–289: 每个 slice copy 前必须运行 import-closure inventory，分类为 `included`/`excluded-with-reason`/`blocker` | 已满足 |
| 不猜测规则 | L288: "Do not guess final helper scope in this plan. A helper that is not classified must not be copied." | 已满足 |
| S6 accept failure stop | S6 L755–756: "Stop if any provider fails ToolRuntime accept integration at S6 combined level." | 已满足 |
| per-slice stop conditions | S3 L541, S4 L619, S5 L695: 均添加了未分类 helper 和 OLD 禁用依赖的 stop condition | 已满足 |
| S1/S3/S4/S5 inventory | S3 L498, S4 L572–573, S5 L657: 均明确要求 copy 前完成 import-closure inventory | 已满足 |

**裁决**：**已修复**。"may" 措辞已替换为精确文件列表和 inventory 规则，S6 有 accept failure stop condition，所有迁移 slice 均有 import-closure inventory 要求。

---

### N1 — Exact Old Helper Import Closure

**Controller 要求**：
- 添加显式 import-closure inventory 步骤（每个迁移 slice copy 旧文件前）
- 要求 implementation agent 将每个 old helper 分类为 included/excluded-with-reason/blocker

**修复验证**：

| 要求项 | Plan 证据 | 状态 |
|--------|-----------|------|
| Inventory 步骤 | L286–287: "Before S1, S3, S4 and S5 copy old files, the implementation agent must run an import-closure inventory for the files in that slice." | 已满足 |
| 分类体系 | L287: "classify every discovered OLD helper as `included`, `excluded-with-reason`, or `blocker`" | 已满足 |
| 不猜测原则 | L288: "Do not guess final helper scope in this plan." | 已满足 |
| 阻断规则 | L289: "If an import closure requires OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, OLD truncate/fetch-more projection, Host/Engine runtime state, or OLD UI files, stop and write a blocker instead of widening scope silently." | 已满足 |
| Inventory artifact 约定 | L287: "The inventory artifact can live in the slice implementation report" | 已满足 |

**裁决**：**已修复**。Import-closure inventory 已从 "needs-more-evidence" 转为具体可执行的要求——不猜测最终 helper 列表，但要求 implementation agent 在每个 slice 中按规则分类并写入 artifact。这与 N1 的 "不猜测" 精神一致：plan 不提供猜测列表，而是提供可验证的流程规则。

---

## 3. Findings 汇总

| Finding | 状态 |
|---------|------|
| A1 — Adapter API typed signatures | **已修复** |
| A2 — Path metadata vs enforcement boundary | **已修复** |
| A3 — Current ToolTruncateSpec declaration | **已修复** |
| A4 — Input/response projection adapter contract | **已修复** |
| A5 — Fins ingestion artifact destination | **已修复** |
| A6 — asyncio.to_thread concurrency boundary | **已修复** |
| A7 — Stop conditions and ambiguous wording | **已修复** |
| N1 — Old helper import closure | **已修复** |

**无新增 findings**。Plan fix 未引入新的 ambiguity、contract gap 或 scope 漂移。

---

## 4. Open Questions

| # | 问题 | 类型 | 说明 |
|---|------|------|------|
| Q1 | OLD `ToolTruncateSpec(...)` 构造调用的 `__post_init__` 兼容性 | deferred-to-implementation | Plan L239 允许 declaration-site import/argument rewrite，implementation agent 可改写构造参数以通过 current `ToolTruncateSpec.__post_init__` 校验。新旧 `__post_init__` 的逐字段差异由 S2 实现时确认。不构成 plan blocker。 |
| Q2 | Web shared sessions / Playwright fallback 并发安全 | deferred-to-implementation | Plan 已有保守默认（serialized），S5 要求直接证据确认后才允许 concurrent。不构成 plan blocker。 |
| Q3 | Fins ingestion 是否纳入 WU-TOOLS-01 | conditional | S4 已按 Controller 要求指定 blocker artifact 路径和保守默认。不构成 plan blocker。 |

---

## 5. Residual Risks

| Risk | Severity | Owner | Destination |
|------|----------|-------|-------------|
| OLD code weak typing + pyright 兼容 | 中 | Implementation agent | 全局 pyright 验证；plan 已分类为迁移约束风险 |
| OLD `@tool` 装饰器 `ToolTruncateSpec` import 改写执行细节 | 低 | Implementation agent | S2 adapter 实现时处理，plan L239 已授权改写 |
| Fins ingestion 未完成 | 低 | Controller | S4 conditional stop artifact |

---

## 6. Final Re-Review Conclusion

**结论：PASS**

所有 8 项 Controller accepted findings (A1–A7, N1) 均已修复。当前 plan (`docs/host/wu-tools-01-migration-plan.md`) 在以下维度达到 code-generation-ready：

- Adapter API 有完整的 typed signatures 和输出形态
- Path metadata 与 enforcement boundary 无歧义
- Current `ToolTruncateSpec` 声明规则完整，含 OLD→current 映射表
- Input 和 response projection 有具体的 adapter contract 和错误分类
- Fins ingestion 有明确的 blocker artifact 路径和保守默认
- `asyncio.to_thread` 有分层并发策略和验证路径
- Slice stop conditions 收紧，ambiguous wording 消除
- Import-closure inventory 从猜测转为流程规则

无 blocking open questions，无新增 findings。Plan 可以进入 implementation gate。
