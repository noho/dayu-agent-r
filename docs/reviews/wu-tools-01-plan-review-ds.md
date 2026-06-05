# WU-TOOLS-01 Plan Review — AgentDS

**日期**：2026-06-05 21:43
**Plan Review Gate**：planreview
**Review Target**：`docs/host/wu-tools-01-migration-plan.md`
**Design 真源**：`docs/host/design.md`、`docs/engine/design.md`
**总控文档**：`docs/host/issues-implementation-control.md`
**Reviewer**：AgentDS
**Review Posture**：adversarial — 基于证据寻找 plan 中公开或隐藏的漏洞，不证明 plan 可行

---

## 1. Reviewed Target and Scope

### 1.1 Plan Summary

WU-TOOLS-01 是一个 migration / cross-layer tool contract work unit，目标是把 OLD `dayu-agent` 仓库中的 Doc tools、Fins tools 和 Web tools 迁移到当前 `dayu-agent-r` 仓库，同时引入共享文档基础组件（`dayu/documents/`）、OLD-to-NEW 工具适配器（`dayu/tools/_legacy_adapter/`）、及 provider config 透传。迁移原则是搬迁代码 + 最小 adapter，不修改 OLD class/function 签名和函数体。

### 1.2 Review Scope

按用户指令，重点审查 10 个维度的迁移合规性、分层边界、package placement、slice 可实施性，以及是否过度设计。

### 1.3 Evidence Sources

- Plan artifact：`docs/host/wu-tools-01-migration-plan.md`
- Host 设计真源：`docs/host/design.md`（Section 2-3, 3.1 节）
- Engine 设计真源：`docs/engine/design.md`（Section 1-2, 10-11, 16 节）
- 控制文档：`docs/host/issues-implementation-control.md`
- 当前代码：
  - `dayu/contracts/tool_declaration.py`：`ToolDefinition`、`ToolBundle`、`ToolCallable`、`tool()` 装饰器
  - `dayu/contracts/tool_schema.py`：`ToolTruncateSpec`、`ToolTruncationStrategy`
  - `dayu/contracts/tool_call.py`：`ToolCallRequest`、`BatchToolExecutionContext`
  - `dayu/contracts/tool_result.py`：`ToolResultSuccess.value`
  - `dayu/contracts/tool_outcome.py`：`ToolCompletedOutcome`、`ToolFailedOutcome`
  - `dayu/runtime/tools_discovery.py`：`ToolsDiscovery`、`ToolsDiscoveryProviderSpec`（已有 `config: Mapping[str, JsonValue]`）
  - `dayu/runtime/config_loader.py`：`ToolDiscoveryProviderConfig`（当前**没有** `config` 字段）
  - `dayu/service/host_assembly.py`：`_tool_discovery_specs()`（当前 hardcode `config={}`）
  - `dayu/host/tool_runtime.py`：`FrameworkToolName.FETCH_MORE`
  - `dayu/engine/agent.py`：`_project_tool_success_for_llm()` 直接读 `result.value`
  - `dayu/config/tool_discovery.json`：单 provider `financial-tools`（disabled）
  - OLD 源目录存在：`/Users/leo/workspace/dayu-agent/dayu/engine/tools/`（doc_tools.py, web_*.py 等）
  - 当前仓库无 `dayu/fins`、`dayu/documents` 目录

---

## 2. Design Alignment Summary

### 2.1 Host Boundary

Plan 明确 Host 不扫描/import 具体工具，只接收 assembly-time 已发现的 `ToolBundle`（L97-100）。与 Host 设计真源一致：Host 拥有 ToolRuntime 执行治理，不做工具发现（设计真源 L71）。

### 2.2 Engine Boundary

Plan 明确 Engine 只消费 `tool_schemas` 和 `ToolExecutor`，不 import `ToolDefinition` 或工具实现（L103-105）。与 Engine 设计真源一致：`AgentRunRequest.tool_schemas` 是强制快照入参（设计真源 Section 4），`ToolExecutor.execute` 是唯一工具调用协议（设计真源 Section 10）。

### 2.3 `dayu.runtime` 边界

Plan 明确 `dayu.runtime` 不依赖 `dayu.fins`、Web tools、Doc tools、Host、Engine、Service（L119-122）。与设计真源 L65-66 一致。

### 2.4 `dayu.fins.storage` 边界

Plan 要求 Fins 文档存取只走 `dayu.fins.storage` 仓储协议（L125-128）。与 Engine 设计真源 L26、Host 设计真源 Section 2 一致。

### 2.5 分层总结

Plan 对分层边界的处理与两个设计真源一致，无架构违规。

---

## 3. Findings

### Finding 1 — 高 — `_legacy_adapter` 核心 adapter 接口规格不足

- **位置**：Slice S2，L337 (`definition_adapter.py`)、L338 (`registry_collector.py`)
- **问题类型**：不可直接实施
- **当前写法**：S2 列出了 9 个 adapter 文件，但对核心文件 `definition_adapter.py` 和 `registry_collector.py` 只给出了功能描述（L351-357），没有具体的函数/类签名。例如：
  - `definition_adapter.py` 的公开 API 是什么？`convert_old_tool_to_definition(...)` 的输出类型？接收什么输入？
  - `registry_collector.py` 的 `register_allowed_paths` 方法签名、`tools` 属性的返回类型？
  - adapter 如何把 OLD `@tool` 的 `truncate` metadata 转换为当前 `ToolTruncateSpec`？转换规则是什么？
- **反例/失败场景**：implementation agent 拿到 "Implement OLD schema to current `ToolSchema` conversion" 这个描述后，需要自行设计 adapter API 签名。不同的 implementation agent 可能做出不同的 design 决策（例如返回值是 `ToolDefinition` 还是 `tuple[ToolSchema, ToolCallable, ...]`），导致后续 slices S3/S4/S5 需要 adapter 提供的接口不一致。
- **为什么有问题**：plan 要求 slices 必须 "code-generation-ready"（控制文档 Section "Slice 切分原则"），但核心 adapter 的公开接口未达到该标准。adapter 是 S3/S4/S5 三个 provider slices 的共同依赖，接口规格不足会放大风险。
- **直接证据**：
  - Plan L351-357：功能描述，无函数签名
  - Plan L334-338：文件列表，无 API contract
  - 控制文档 L130-135：slice 必须有 "明确输入、输出"
- **影响**：实施 Agent 可能做出与后续 slice 需要的接口不一致的设计，导致返工；review 无法验证 adapter 是否满足 provider slices 的契约
- **建议改法和验证点**：
  1. 在 S2 中追加 `definition_adapter.py` 和 `registry_collector.py` 的核心函数/类签名（至少包括输入类型、输出类型、关键方法名）
  2. 明确 OLD `@tool` truncate metadata → 当前 `ToolTruncateSpec` 的转换规则（哪些字段直接映射、哪些需要构造默认值）
  3. 明确 `register_allowed_paths` 的方法签名为纯 metadata 收集（不执行路径校验），与 Doc provider 的路径 enforcement 区分
- **修复风险**：低（只需补充接口规格，不改变 plan scope）
- **严重程度**：高

---

### Finding 2 — 中 — `register_allowed_paths` 方法名可能造成 metadata collection vs. enforcement 混淆

- **位置**：Slice S2 L351；Slice S3 L418
- **问题类型**：架构边界
- **当前写法**：S2 L351 说 "Implement a new minimal registry collector with `register`, `register_allowed_paths` and `tools` metadata"。S3 L418 说 Doc provider "registers path whitelist externally, then calls `register_doc_tools(..., allowed_paths=None)`"。
- **反例/失败场景**：implementation agent 看到 `register_allowed_paths` 方法名，可能误认为该方法承担 path safety enforcement（因为在 OLD `ToolRegistry` 中 `register_allowed_paths` 正是做 enforcement 的）。如果 adapter 层面执行了路径校验（例如在 `registry_collector.register_allowed_paths` 中做 fail-closed 校验），则违反了 "path safety 属于外层 provider/adapter，不属于共享 adapter" 的设计裁决（L226-229）。
- **为什么有问题**：方法名 `register_allowed_paths` 承载了 OLD 语义（enforcement），但在新架构中该方法的唯一职责是收集 `file_path_params` metadata。方法名与语义不一致，是 implementation agent 的陷阱。
- **直接证据**：
  - Plan L351：`register_allowed_paths` 出现在 registry collector
  - Plan L226-229："Doc tools do not own path safety after migration"
  - OLD `engine/tool_registry.py` 的 `register_allowed_paths` 是做 enforcement + registration（plan L60）
- **影响**：实施 Agent 可能将 path enforcement 逻辑误放入共享 adapter，违反用户裁决（审查维度 #6）
- **建议改法和验证点**：
  1. 将 `register_allowed_paths` 重命名为 `register_path_params` 或 `collect_file_path_params`，明确其仅为 metadata 收集
  2. 在 plan 中增加明确的禁止项：registry collector 不得做路径白名单校验
- **修复风险**：低（仅重命名 + 补充禁止项）
- **严重程度**：中

---

### Finding 3 — 中 — Fins ingestion tools 的 conditional scope 缺少具体的 blocker artifact 目的地

- **位置**：Slice S4 L270 ("Fins provider should start with read tools. Ingestion tools may be migrated...")；L522-524 (stop condition)
- **问题类型**：open question 未收敛
- **当前写法**：S4 的 ingestion tools 迁移是条件性的。如果 ingestion tools "require current `ToolAwaitingOutcome` / wait adapter design beyond this work unit"，则 "stop and classify"。但停止后生成的 blocker artifact 写到哪个路径、什么格式、由谁裁决，plan 没有指定。
- **反例/失败场景**：implementation agent 在 S4 发现 ingestion tools 需要等待语义，但不知道 blocker artifact 应该放在哪里（`docs/reviews/`？`docs/host/`？），也不知道是否需要立即通知 Controller。如果 agent 自作主张跳过或硬塞，会产生 residual risk。
- **为什么有问题**：控制文档 Section "Slice 切分原则" 要求 slice 有 "明确的 issue handoff"。conditional stop 的交付物规格缺失，属于 handoff 定义不完整。
- **直接证据**：
  - Plan L270："only if they can return current completed/failed outcomes without inventing new wait adapter semantics; otherwise stop and record a classified residual for Controller review"
  - Plan L523-524："Stop and classify if ingestion tools require current `ToolAwaitingOutcome` / wait adapter design beyond this work unit."
  - 未指定 blocker artifact path 或 Controller notification 方式
- **影响**：conditional stop 的执行不可验证；Controller 可能收不到 blocker 通知；residual risk 可能被遗漏
- **建议改法和验证点**：
  1. 在 S4 中指定 ingestion blocker artifact 的路径约定（如 `docs/reviews/wu-tools-01-s4-ingestion-blocker-{timestamp}.md`）
  2. 明确 artifact 需要包含的内容：哪些工具、什么等待语义、建议的后续 work unit 或 phase
- **修复风险**：低
- **严重程度**：中

---

### Finding 4 — 中 — `asyncio.to_thread` 未讨论 OLD 工具的线程安全性和 GIL 影响

- **位置**：Implementation Decisions #3 (L263)
- **问题类型**：契约缺失
- **当前写法**："Build current async `ToolCallable` wrappers with `asyncio.to_thread` for blocking sync OLD tool calls."
- **反例/失败场景**：OLD Doc/Web/Fins 工具中可能使用 `threading.local`、非线程安全的全局状态、或依赖 `asyncio` event loop 的上下文（例如 OLD Web 工具中的 Playwright async backend）。如果 OLD 代码假设单线程执行（在 OLD 架构中它们通过同步 `ToolRegistry` 调用），`asyncio.to_thread` 可能在并发 batch 执行时暴露线程安全问题。ToolRuntime 可能在同一个 batch 内并发执行多个工具调用，多个 `asyncio.to_thread` 可能同时运行不同的 OLD 工具函数。
- **为什么有问题**：迁移原则是 "不修改 OLD function bodies"，但如果 OLD 函数有隐式的线程不安全假设，`asyncio.to_thread` 会引入非确定性的并发 bug。plan 没有讨论这个风险。
- **直接证据**：
  - Plan L263："Build current async `ToolCallable` wrappers with `asyncio.to_thread`"
  - Plan L19："ToolRuntime 拥有 batch execution, truncation, fetch_more, duplicate governance"
  - ToolRuntime 可以在 batch 内并发调度多个工具（engine design L274）
- **影响**：潜在的线程安全 bug，非确定性失败（数据竞争、Playwright session 冲突等）
- **建议改法和验证点**：
  1. 在 plan 中增加 `asyncio.to_thread` 的线程安全风险分析
  2. 对于已知非线程安全的 OLD 函数，要求在 adapter 中序列化执行（或使用 `asyncio.Lock` 保护）
  3. S6 的集成测试应覆盖并发 batch 执行场景
- **修复风险**：低（增加风险分析 + 测试覆盖）
- **严重程度**：中

---

### Finding 5 — 中 — OLD `tool` decorator metadata → 当前 `ToolTruncateSpec` 转换规则不够具体

- **位置**：Slice S2 L355-356；L219-222
- **问题类型**：契约缺失
- **当前写法**："Implement OLD truncate declaration metadata to current `ToolTruncateSpec` conversion at declaration time."（L355-356）
- **反例/失败场景**：OLD `@tool` 装饰器的 truncate metadata 格式可能与当前 `ToolTruncateSpec` 不同（OLD 可能使用不同的 truncation strategy 名称、不同的 limit key、或者有额外的字段）。plan 没有描述 OLD truncate metadata 的实际格式，也没有给出映射表。implementation agent 必须自行去读 OLD 代码推断映射规则。
- **为什么有问题**：truncation 是 ToolRuntime 执行时的关键治理机制。如果转换出错（例如 strategy 名称不匹配、limit 字段映射错误），截断行为会不正确——要么不截断导致上下文超限，要么过度截断导致信息丢失。
- **直接证据**：
  - Plan L355-356：仅一句话描述，无具体映射规则
  - Plan L63：OLD `base.py` 的 `@tool` stores "truncate" — 但未列出当前 OLD truncate 是什么格式
  - 当前 `ToolTruncateSpec` 结构（`dayu/contracts/tool_schema.py` L121-195）：`enabled`, `strategy: ToolTruncationStrategy | None`, `limits: Mapping[str, int]`, `target_field`, `field_path`, `ttl_seconds`
- **影响**：转换错误导致截断行为不正确；review 无法验证转换规则的正确性
- **建议改法和验证点**：
  1. 在 S2 中补充 OLD truncate metadata 的已知格式（至少包括 OLD 的 strategy 名称、limit keys）
  2. 给出 OLD → 当前 `ToolTruncateSpec` 的字段映射表
  3. adapter 测试必须覆盖至少一种 truncation strategy 的转换
- **修复风险**：低
- **严重程度**：中

---

### Finding 6 — 低 — S6 集成 slice 对 provider 测试的顺序依赖可能导致阻塞

- **位置**：Slice S6 L609-651
- **问题类型**：切片过粗
- **当前写法**：S6 需要 S1-S5 全部完成后才能验证，且要求 "ToolRuntime executes one representative tool from each provider"（L626）
- **反例/失败场景**：如果 S3/S4/S5 中任一 provider 有问题（例如 Doc provider 的路径校验逻辑错误、Web provider 的 URL safety 配置解析错误），问题只能在 S6 集成测试中发现。而 S6 的 stop condition 是 "integration requires Host public API changes" 和 "unclassified residual remains"（L653-656），provider 实现错误不在 stop condition 中。
- **为什么有问题**：S6 同时依赖 5 个前置 slices，且 provider 实现错误不在 S6 stop condition 中。如果 provider 有问题，需要在 S6 发现后回到对应的 provider slice 修复，增加迭代成本。
- **直接证据**：
  - Plan：S3/S4/S5 各自有独立的单元测试覆盖，但 "Current ToolRuntime can execute at least one Doc tool through accept barrier"（S3 L446）已经是一个集成式断言
  - S6 L653-656 的 stop conditions 不包含 "provider tool fails ToolRuntime accept barrier"
- **影响**：跨 slice 迭代修复成本；集成问题发现延迟
- **建议改法和验证点**：S6 的 stop condition 增加 "Stop if any provider tool fails ToolRuntime accept barrier at integration level." 或在 S3/S4/S5 各自末尾增加 ToolRuntime accept 级别的 quick smoke（不要求完整集成环境，但要求 adapter + ToolRuntime 的最小链路工作）
- **修复风险**：低
- **严重程度**：低

---

### Finding 7 — 低 — Plan 中的 "may" / "only if" 模糊措辞降低了 code-generation-readiness

- **位置**：
  - L169："This package **may** contain copied OLD helper pieces..."
  - L243："**only as** a reference for metadata translation"
  - L270："**may** be migrated... **only if**..."
- **问题类型**：不可直接实施
- **当前写法**：使用 "may"、"only as a reference" 等措辞，留给 implementation agent 自行判断的空间过大。
- **反例/失败场景**：implementation agent 看到 `_legacy_adapter __init__.py` "This package may contain..."，不确定哪些 OLD helper 应该迁移、哪些不应该。可能迁移过多（引入不必要的 OLD 依赖）或不足（adapter 无法工作）。
- **为什么有问题**：plan gate 的验收标准是 "code-generation-ready"（控制文档 Section "Slice 切分原则"），意味着 implementation agent 不应该还需要做 scope boundary 判断。
- **直接证据**：
  - L169：`may contain` 在明确性上与 code-generation-ready 不一致
  - L243：`only as a reference` — 但 reference 中哪些内容应该精确复制、哪些应该改写，不明确
- **影响**：实施 Agent 可能做错 scope 判断，引入不该引入的代码或遗漏必要代码
- **建议改法和验证点**：将 "may" 替换为精确的文件清单（S2 的 "Support OLD helpers" 已经列了大部分，但 `_legacy_adapter/__init__.py` 中的 "may" 应改为确定的文件列表）
- **修复风险**：低
- **严重程度**：低

---

## 4. Open Questions

| # | 问题 | 建议裁决方 |
|---|------|-----------|
| Q1 | OLD `@tool` 装饰器存储的 truncate metadata 的实际格式是什么？是否有 strategy name 映射不一致？ | Implementation agent 应在 S2 启动前检查 OLD 代码并确认映射规则 |
| Q2 | OLD Web 工具（Playwright backend）是否有 async 依赖？`asyncio.to_thread` 是否安全？ | Implementation agent 应在 S5 启动前检查 OLD Web 代码的 async/sync 边界 |
| Q3 | Fins ingestion tools 如果确实需要等待语义，后续由哪个 work unit 承接？ | Controller 应在 S4 conditional stop 触发时裁决 |
| Q4 | OLD `register_doc_tools(..., timeout_budget=None)` 中 `timeout_budget` 在迁移后如何映射？Plan 说 S3 L418 传入 `timeout_budget=None`，但未说明 timeout_budget 的语义在迁移后是否仍有意义 | Implementation agent 应在 S3 中确认 |

---

## 5. Residual Risks Classification

| Risk | Severity | Owner | Destination |
|------|----------|-------|-------------|
| R1: `_legacy_adapter` API 设计漂移 | 高（如果实现 agent 自由发挥） | Implementation agent | S2 adapter tests + S3/S4/S5 提供者实现时的接口反馈 |
| R2: OLD 工具线程安全性（`asyncio.to_thread`） | 中 | Implementation agent | S2 adapter 测试 + S6 并发 batch 集成测试 |
| R3: truncate metadata 转换错误 | 中 | Implementation agent | S2 adapter tests（显式测试至少一种 strategy 转换） |
| R4: Fins ingestion tools 未完成 | 低（plan 已提供 stop condition） | Controller | S4 conditional stop 时生成的 blocker artifact |
| R5: 路径安全 enforcement 误入共享 adapter | 低（plan 已明确禁止） | Implementation agent | S3 Doc provider tests (assert 路径校验在 provider code，不在 registry_collector) |
| R6: OLD 弱类型签名 + pyright 兼容 | 中（已知约束） | Implementation agent | 全局 pyright 验证；如无法通过则 stop |

---

## 6. Final Plan Review Conclusion

**结论：PASS-WITH-RISKS**

Plan 的迁移原则、architectural boundary、package placement 和 exclusion rules 均与设计真源一致，且覆盖了用户指定的全部 10 个审查维度。没有发现 blocking finding。

6 个 material findings 均为可修复的 clarity/specificity 问题，不阻止 plan 进入 implementation gate。建议在 plan fix gate 中优先修复：

1. **Finding 1 (高)**：补充 `definition_adapter.py` 和 `registry_collector.py` 的核心 API 签名
2. **Finding 2 (中)**：将 `register_allowed_paths` 重命名为语义准确的方法名
3. **Finding 5 (中)**：补充 OLD → 当前 `ToolTruncateSpec` 的字段映射规则

其余 findings 可作为 implementation notes 在对应 slice 中处理，不强制要求 plan 修改。

---

## Appendix A: Evidence Traceability Matrix

| Plan Claim | Code Evidence | Verdict |
|-----------|---------------|---------|
| `ToolsDiscoveryProviderSpec.config` already exists (L188) | `dayu/runtime/tools_discovery.py` L106: `config: Mapping[str, JsonValue] = field(default_factory=dict)` | Confirmed |
| `ToolDiscoveryProviderConfig` lacks `config` field (L188) | `dayu/runtime/config_loader.py` L2023-2034: allowed fields do NOT include `config` | Confirmed |
| `_tool_discovery_specs()` passes `config={}` (L191) | `dayu/service/host_assembly.py` L747: `config={}` hardcoded | Confirmed |
| Engine reads `ToolResultSuccess.value` for LLM (L53) | `dayu/engine/agent.py` L312: `value = result.value` | Confirmed |
| `_RESERVED_FRAMEWORK_TOOL_NAMES` includes `fetch_more` (L116) | `dayu/runtime/tools_discovery.py` L32: `frozenset({"fetch_more"})` | Confirmed |
| `FrameworkToolName.FETCH_MORE` exists (L265) | `dayu/host/tool_runtime.py` L128: imported; L4770: `FrameworkToolName.FETCH_MORE.value` | Confirmed |
| OLD source directory exists | `ls /Users/leo/workspace/dayu-agent/dayu/engine/tools/` shows doc_tools.py, web_*.py | Confirmed |
| No current `dayu/fins`, `dayu/documents` | Glob of `dayu/` shows no `fins/` or `documents/` subdirectory | Confirmed |
| `dayu.runtime` doesn't import business layers | `dayu/runtime/tools_discovery.py` imports only from `dayu.contracts` and `dayu.runtime._digest` | Confirmed |
