# WU-TOOLS-01 Plan Review — AgentMiMo

Reviewer: AgentMiMo
Review timestamp: 2026-06-05T22:09:37+08:00
Reviewed target: `docs/host/wu-tools-01-migration-plan.md`
Work unit type: migration / cross-layer tool contract

## 1. Reviewed Target And Scope

Plan 声称将旧 Doc tools、Fins tools 和 Web tools 迁移为单一 work unit，建立共享文档基础能力 owner，并通过当前 `ToolsDiscovery` / `ToolRuntime` 集成。

Scope 覆盖六个 slices：S1 共享文档基础、S2 工具适配器与 typed provider config、S3 Doc tools provider、S4 Fins storage 与 read tools provider、S5 Web tools provider、S6 组合发现/ToolRuntime 验收/文档收口。

## 2. Design Alignment

### 2.1 Engine 边界 — 对齐

- Engine design (`docs/engine/design.md`) 明确：Engine 只通过 `ToolExecutor` 协议调用工具，不消费 `ToolDefinition`，不读取配置文件，不从 `ToolExecutor` 查询 schema。Plan S6 验收断言要求 "Engine still does not import Fins" 且 Engine 只接收 `tool_schemas` 和 `ToolExecutor`，与此一致。
- Engine design 明确 `ToolTruncateSpec` 与 `ToolTruncationStrategy` 存在于 `dayu.contracts` 公共契约中，不属于 Engine 包根导出的稳定调用面。Plan 要求迁移工具声明当前 `ToolTruncateSpec`，与此一致。

### 2.2 Host / ToolRuntime 边界 — 对齐

- Host design 明确：ToolRuntime 是 `ToolExecutor`，Engine 只看见 `ToolExecutor` protocol；`ToolBundle` 是 `dayu.contracts` 已定义的工具声明集合；Host 只接收 `ToolBundle`，不参与工具发现。Plan 要求 "Host does not scan/import concrete business tool implementations"，与此一致。
- Host design 明确 `FrameworkToolName.FETCH_MORE` 由 ToolRuntime factory 注入，不由外部业务 `ToolBundle` 提供。Plan 要求 "current ToolRuntime injects `FrameworkToolName.FETCH_MORE`" 且 "OLD `fetch_more` is not emitted as business tool"，与此一致。
- Host design 明确 `fetch_more` 走普通 tool dispatch / policy / accept barrier。Plan 不迁移 OLD `fetch_more`，与此一致。

### 2.3 ToolsDiscovery 边界 — 对齐

- 当前 `ToolsDiscovery` (`dayu/runtime/tools_discovery.py`) 只按显式 provider spec 解析 provider callable、调用 provider 并聚合 `ToolDefinition`，不扫描包。Plan 要求 provider 通过显式配置进入，与此一致。
- 当前 `ToolsDiscoveryProviderSpec` 已有 `config: Mapping[str, JsonValue]` 字段。Plan 要求 ConfigLoader 和 Service assembly 传递该字段，是对现有契约的自然延伸，不引入新契约。

### 2.4 dayu.runtime 层中立 — 对齐

- 当前 `dayu.runtime.tools_discovery` 不 import Host/Engine/Service/UI/Fins。Plan 要求 "No shared document foundation code goes into `dayu.runtime`"，与此一致。

### 2.5 Fins storage 边界 — 对齐

- 总控文档明确 "财报文档存取必须且只能通过 `dayu.fins.storage` 下的仓储协议与仓储实现完成"。Plan S4 要求 "Fins tools and services access financial documents only through these repositories"，与此一致。

## 3. Findings (Ordered By Severity)

### F1-未修复-中-OLD @tool 装饰器 ToolTruncateSpec 兼容性未明确裁决

- **位置**: S3 Exact allowed changes "Preserve inner tool function signatures and bodies"；S2 Exact allowed changes "Implement OLD schema to current `ToolSchema` conversion"
- **问题类型**: 契约缺失 / 需要更多证据
- **当前写法**: Plan 要求 "Preserve `register_doc_tools(...)` signature" 和 "Preserve inner tool function signatures and bodies"。旧 `doc_tools.py` 从 `dayu.engine.tool_contracts` 导入 `ToolTruncateSpec` 并在 `@tool(truncate=ToolTruncateSpec(...))` 中直接实例化。
- **反例/失败场景**: 迁移后若 `doc_tools.py` 的 import 改为 `dayu.contracts.tool_schema.ToolTruncateSpec`，旧代码中的 `ToolTruncateSpec(enabled=True, strategy=..., limits=..., target_field=...)` 构造调用可能因新类的 `__post_init__` 校验（如要求 `field_path`/`ttl_seconds` 或更严格的 limits 校验）而失败。反之若保留旧 import 路径，则需要在 `_legacy_adapter` 中保留旧 `ToolTruncateSpec` 类定义，但 plan 说 "do not copy OLD `ToolTruncateSpec` as a runtime contract"。
- **为什么有问题**: Plan 在 S2 说 "Implement OLD truncate declaration metadata to current `ToolTruncateSpec` conversion at declaration time"，暗示适配器在声明阶段读取旧元数据并转换。但旧 `@tool` 装饰器在函数定义时就会执行 `ToolTruncateSpec(...)` 构造，如果 import 指向新类且构造失败，函数定义本身就无法完成。Plan 没有明确裁决这个 import 指向问题。
- **直接证据**:
  - 旧 `doc_tools.py` grep 结果显示 `from ..tool_contracts import ... ToolTruncateSpec`，且 `@tool(truncate=ToolTruncateSpec(enabled=True, ...))` 在函数定义时执行。
  - 当前 `dayu/contracts/tool_schema.py:ToolTruncateSpec.__post_init__` 有严格校验：disabled 时禁止 strategy/limits/target_field/field_path/ttl_seconds；enabled 时要求 strategy；limits 必须匹配策略。
  - Plan S3: "Preserve inner tool function signatures and bodies"。
- **影响**: 实施 Agent 面临两难：改 import 指向可能破坏旧函数定义；不改 import 则需要保留旧 `ToolTruncateSpec` 类，与 "do not copy OLD `ToolTruncateSpec` as a runtime contract" 矛盾。
- **建议改法和验证点**: Plan 应明确裁决：(a) 旧 `@tool` 装饰器的 `ToolTruncateSpec` import 指向哪里；(b) 若指向新类，旧构造调用是否兼容（需逐字段比对新旧 `ToolTruncateSpec` 的 `__post_init__`）；(c) 若不兼容，是否允许在 `_legacy_adapter` 中保留旧 `ToolTruncateSpec` 仅作为旧装饰器的构造目标，不作为 runtime owner。验证点：迁移后 `doc_tools.py` 能正常 import 并执行 `@tool` 装饰器。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### F2-未修复-中-path safety 在 adapter 层的 fail-closed 语义未细化

- **位置**: S3 Contract / Schema section "Doc tools do not own path safety after migration"；S3 Expected assertions "Missing path whitelist fails before tool execution"
- **问题类型**: 契约缺失
- **当前写法**: Plan 要求 "The adapter must enforce fail-closed path validation before calling OLD Doc function bodies" 和 "Do not pass path whitelist through `register_doc_tools(... allowed_paths=...)`；call that signature with `allowed_paths=None`"。
- **反例/失败场景**: 旧 `register_doc_tools` 中 `if allowed_paths: registry.register_allowed_paths(allowed_paths)` — 当传入 `None` 时不注册路径。但旧函数内部的 `@tool` 装饰器仍会标记 `file_path_params=["file_path"]`。如果最小 registry collector 不实现 `register_allowed_paths` 且不校验 `file_path_params`，路径安全完全依赖外层 adapter。但 Plan 没有明确说明最小 registry collector 是否需要处理 `file_path_params` 标记，还是完全忽略它。
- **为什么有问题**: 如果最小 registry collector 忽略 `file_path_params`，adapter 必须自己知道哪些参数是路径参数。这要求 adapter 读取 `file_path_params` 元数据并对其执行白名单校验。Plan 提到 adapter 会读取旧装饰器元数据，但没有明确说 `file_path_params` 是否在读取范围内。
- **直接证据**:
  - 旧 `base.py` grep 结果显示 `@tool` 存储 `file_path_params` 到函数对象。
  - 旧 `tool_registry.py` 有 `register_allowed_paths` 和基于 `file_path_params` 的路径校验。
  - Plan S2: "registry collector ... sufficient for old `register_*_tools` functions. This collector is not OLD `ToolRegistry`"。
- **影响**: 如果实施 Agent 不明确 `file_path_params` 的处理方式，可能遗漏路径安全校验或重复实现。
- **建议改法和验证点**: Plan 应明确：(a) 最小 registry collector 是否读取 `file_path_params` 元数据；(b) adapter 是否基于 `file_path_params` 自动对对应参数执行白名单校验；(c) 校验失败时返回 `ToolFailedOutcome` 的具体错误结构。验证点：S3 测试 "A disallowed path returns current failed outcome" 通过。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F3-未修复-低-OLD 代码 import 依赖链未完全列举

- **位置**: S1 Exact OLD Source Scope "Must migrate / inspect"
- **问题类型**: 切片过粗 / 需要更多证据
- **当前写法**: Plan 列出必须迁移的旧源码范围，包括 `dayu/fins/**`、`dayu/engine/tools/doc_tools.py`、`dayu/engine/tools/web_*.py`、`dayu/engine/processors/*`、`dayu/docling_runtime.py`。
- **反例/失败场景**: 旧 `doc_tools.py` 可能内部依赖 `dayu/engine/tools/utils_tools.py`（该文件存在于旧 tools 目录但未在迁移范围中列出）。如果存在此依赖，S3 迁移 `doc_tools.py` 时会因 import 失败而阻塞。
- **为什么有问题**: Plan 的 "Must migrate / inspect" 列表可能不完整。`utils_tools.py` 在旧 tools 目录中存在但未被提及。
- **直接证据**: 旧 `dayu-agent/dayu/engine/tools/` 目录 grep 结果显示存在 `utils_tools.py`，但 plan 的 Exact OLD Source Scope 未列出。
- **影响**: 实施 Agent 在 S3 可能遇到 import 失败，需要临时决定是否迁移 `utils_tools.py`。
- **建议改法和验证点**: Plan 应在 "Must migrate / inspect" 中补充 `utils_tools.py`，或在 "Explicitly excluded" 中说明排除理由。验证点：S1/S3 迁移后 import 链完整。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F4-未修复-低-Fins ingestion tools 等待语义裁决条件不够具体

- **位置**: S4 "Ingestion tools may be included only if their OLD completed/failed behavior maps to current outcomes without inventing new wait adapter semantics"；Implementation Decisions #10
- **问题类型**: open question 未收敛
- **当前写法**: Plan 要求 ingestion tools 只有在不需要等待语义时才迁移，否则 "stop and record a classified residual for Controller review"。
- **反例/失败场景**: 实施 Agent 可能无法判断某个 ingestion tool 是否需要等待语义，因为没有明确的判断标准（如：检查函数是否返回 `ToolAwaitingOutcome` 或等价物）。
- **为什么有问题**: "without inventing new wait adapter semantics" 是正确约束，但缺少可操作的判断标准。
- **直接证据**: Plan S4 Stop condition: "Stop and classify if ingestion tools require current `ToolAwaitingOutcome` / wait adapter design beyond this work unit"。
- **影响**: 低。实施 Agent 可以保守地排除所有 ingestion tools，只迁移 read tools。
- **建议改法和验证点**: 可接受现状，但建议 Plan 补充：ingestion tool 是否需要等待的判断标准为 "OLD 函数是否同步返回结果（completed/failed），不涉及外部 job/polling/callback"。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 4. 用户约束覆盖裁决

逐条裁决用户指定的 5 项必须重点审查约束：

| # | 约束 | Plan 覆盖 | 裁决 |
|---|---|---|---|
| 1 | 不迁移 OLD ToolRegistry / OLD TruncationManager / OLD fetch_more / OLD truncate 或 fetch_more projection | Plan Non-Goals、S2 Exact allowed changes、S2 Expected assertions、Residuals R4 均明确禁止 | **accepted** — 覆盖充分，有测试断言验证 |
| 2 | 迁移工具只使用当前新的 ToolTruncateSpec 声明；旧 truncate metadata 只能在 adapter/provider declaration time 转换，不得作为 runtime owner | Plan S2 "Implement OLD truncate declaration metadata to current `ToolTruncateSpec` conversion at declaration time. Do not copy OLD `ToolTruncateSpec` as a runtime contract"；S3 "read_file and read_file_section truncate declarations must be translated to current `ToolTruncateSpec` at declaration time" | **accepted** — 覆盖充分。但 F1 指出旧 `@tool` 装饰器的 import 指向问题需实施时解决 |
| 3 | ToolCallRequest.arguments 进入旧函数前的 input projection/coercion/validation 由 adapter/provider 裁决 | Plan "Input projection" 章节、S2 "Implement explicit input projection"、S3/S4/S5 各有 input projection decision | **accepted** — 覆盖充分，各 provider slice 都有明确的 projection 裁决 |
| 4 | 旧函数返回投影到当前 ToolCompletedOutcome/ToolFailedOutcome / ToolResultSuccess.value，不能把 OLD ok/value envelope 直接给 LLM | Plan "Tool result mapping" 章节、S2 "raw return / exception to current outcome conversion"、各 provider slice 的 response projection decision | **accepted** — 覆盖充分，明确要求 "OLD ok/value envelope" 不作为 LLM-facing value |
| 5 | Doc tools 不负责路径安全机制；路径白名单 / fail-closed 在外层 adapter/provider/assembly/ToolRuntime 边界 | Plan "Path safety" 章节、S3 "No path safety logic inside migrated Doc tool functions"、S3 Provider "fails closed when enabled without any allowed path" | **accepted** — 覆盖充分。但 F2 指出 `file_path_params` 元数据的处理方式需细化 |

## 5. 重点审查项裁决 (用户指定的 10 项)

| # | 审查项 | 裁决 | 备注 |
|---|---|---|---|
| 1 | 迁移原则：允许搬迁/import/最小 adapter；禁止修改旧签名/函数体 | **accepted** | Plan Non-Goals 和各 slice Exact allowed changes 均明确 |
| 2 | 明确禁止迁移 OLD ToolRegistry / OLD TruncationManager / OLD fetch_more / OLD truncate/fetch_more projection | **accepted** | S2 Expected assertions 逐项禁止，Residuals R4 跟踪 |
| 3 | 迁移工具使用当前 ToolTruncateSpec；旧 metadata 只在 declaration time 转换 | **accepted** | 见 F1 需细化 import 指向 |
| 4 | input projection/coercion/validation 在 adapter/provider，不改旧函数 | **accepted** | 各 provider slice 有明确 projection decision |
| 5 | response projection 到当前 outcome，不直接塞 OLD envelope | **accepted** | 各 provider slice 有明确 response projection decision |
| 6 | Doc tools 不负责路径安全；路径白名单/fail-closed 属外层 | **accepted** | 见 F2 需细化 file_path_params 处理 |
| 7 | Host/Engine/runtime 分层 | **accepted** | Plan Design Document Alignment 和各 slice Non-goals 均明确 |
| 8 | package placement 合理，shared foundations 不误放 dayu.runtime | **accepted** | `dayu/documents/` 放置合理，非 runtime 也非 Engine |
| 9 | slices code-generation-ready | **accepted** | allowed files、exact changes、tests、stop conditions、docs decisions、residual closure 均具体 |
| 10 | 无过度设计、隐藏兼容 wrapper、re-export、God adapter | **accepted** | Plan "Why This Plan Is Not Over-Designed" 论证合理；`_legacy_adapter` 是窄边界，不是 God adapter |

## 6. Open Questions

1. **OLD `@tool` 装饰器 `ToolTruncateSpec` import 指向** (见 F1): 迁移后旧 `doc_tools.py` 的 `from dayu.engine.tool_contracts import ToolTruncateSpec` 应改为指向哪里？新旧类的 `__post_init__` 是否兼容？
2. **`utils_tools.py` 是否在迁移范围内** (见 F3): 旧 `doc_tools.py` 是否依赖 `utils_tools.py`？
3. **Fins ingestion tools 等待判断标准** (见 F4): 哪些 ingestion tools 需要等待语义？

## 7. Residual Risks Classification

| Risk | 分类 | Owner | Destination |
|---|---|---|---|
| WU-TOOLS-01-R1 path safety adapter | 已覆盖 | implementation agent | S2 + S3 provider/adapter tests |
| WU-TOOLS-01-R2 typed config adapter | 已覆盖 | implementation agent | S2 + S3/S4/S5 provider tests |
| WU-TOOLS-01-R3 ToolDiscovery/ToolRuntime adapter | 已覆盖 | implementation agent | S2 + S6 integration tests |
| WU-TOOLS-01-R4 truncation/fetch_more ownership | 已覆盖 | implementation agent | S2/S3/S4/S5/S6 tests |
| WU-TOOLS-01-R5 input/response projection | 已覆盖 | implementation agent | S2 + S3/S4/S5/S6 tests |
| OLD @tool ToolTruncateSpec import 兼容性 | **needs-more-evidence** (F1) | implementation agent | 需比对新旧 `ToolTruncateSpec` 字段，或在 `_legacy_adapter` 中保留旧类作为装饰器目标 |
| Fins ingestion waiting semantics | 条件性 (F4) | implementation agent | S4 stop condition |
| OLD code weak typing | 已分类 | implementation agent | 保留 OLD 签名，新代码 precise，pyright 验证 |
| Optional heavy deps / live services | 已分类 | implementation agent | deterministic fixtures/mocks |

## 8. Pass/Fail Recommendation

**PASS** (with risks)

Plan 整体结构严谨、边界清晰、slices code-generation-ready。所有 5 项用户约束均被覆盖，10 项重点审查项均通过。Architecture boundary、layering、public contracts 均与设计真源对齐。

两个中等 finding (F1, F2) 不构成 blocker，但需要实施 Agent 在 S2/S3 开始前明确裁决：
- F1: 旧 `@tool` 装饰器的 `ToolTruncateSpec` import 指向和新旧类兼容性。
- F2: `file_path_params` 元数据在 adapter 层的读取和校验方式。

这两个 finding 的修复风险均为中/低，可在 S2 实施开始时作为 adapter 设计决策解决，不需要 Plan 重写。
