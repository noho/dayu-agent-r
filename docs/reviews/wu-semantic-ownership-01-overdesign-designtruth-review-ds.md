# WU-SEMANTIC-OWNERSHIP-01 设计真源专项审查

## 结论

本次按"设计真源 only"门审查范围 `b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`（1317 文件），**确认 4 个 material finding：2 个高严重度、2 个中严重度**。另有已存在于 codex audit 的 3 个 finding（F-01/F-02/F-03）仍为未修复状态，本审查确认它们依然有效但不再重复报告细节。

核心发现：DocResourceBudget（32MiB/10000）、BoundedSourceSnapshot 状态机、list_files/search_files partial contract 三项关键设计在代码中存在、在 R3-E accepted plan 中授权、但在永久设计真源 `docs/host/design.md` 和 `docs/engine/design.md` 中**零引用**。这是严重的 canonicalization gap——accepted plan 是临时授权文档，不替代永久设计真源。

## Scope

- Mode: 专项 design-truth review（All Repository Mode 子集）
- Branch: phaseflow/host-issues-control
- Base commit: b1a0631f397967e7530b676a90ef7467d83a1817（包含在范围内）
- HEAD: 01bbf74c3c408b1b8eaafae20b5a9c68cb733c3f
- Included: b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD（1317 files, +191967 -19116）
- Design truth sources: `docs/host/design.md`（3654 lines）、`docs/engine/design.md`（547 lines）
- 不视为授权真源：WU plan、review artifact、implementation artifact、control doc、README、测试

## 审查方法

1. 对全部 1317 文件做顶层分类，按 Host/Engine/Runtime/Documents/Tools/Tests 分片并行深挖。
2. 对设计真源做穷举搜索：`budget`、`resource`、`limit`、`cap`、`32`、`10000`、`MiB`、`bounded`、`DocResourceBudget`、`BoundedSourceSnapshot`、`partial`、`scan_complete`、`truncated_reason`、`directory_entry_limit`、`source_limit`、`WebEgressPolicy`、`WebResourceBudget`、`allowed_path`、`egress`、`browser`。
3. 对 Host durable state/projection/event 做 schema-to-design 交叉比对。
4. 对 Engine contracts 做 error code/protocol field-to-design 交叉比对。
5. 对 Runtime config/schema 做 typed field-to-design 交叉比对。
6. 对测试做 assertion-to-design-authorization 交叉比对。
7. 将本文与既有 `wu-semantic-ownership-01-overdesign-audit-codex.md` 去重；相同 finding 只引用，不重复展开。

## Findings

### F-DS-01 — 高 — DocResourceBudget 32MiB / 10,000 硬上限在设计真源中无授权

**语义/contract**: 文档工具资源治理——数据源字节上限（32 MiB）和目录 entry 上限（10,000）。这是 security ceiling，决定哪些文档可被处理、目录扫描何时终止。

**正确 owner**: 根据 `docs/engine/design.md:22`，上下文预算治理属于 Host。根据 `docs/host/design.md:91`，Host 已定义 `context_budget_policy`（LLM 上下文窗口的 ratio-first 策略）和 `tool_truncation_policy`（工具结果截断）。但两个设计真源都没有文档资源预算的治理定义。

**漂移位置**:
- `dayu/tools/doc_tools.py:87-88` — `_DOC_SOURCE_MAX_BYTES: Final[int] = 32 * 1024 * 1024`、`_DOC_DIRECTORY_MAX_ENTRIES: Final[int] = 10_000`
- `dayu/tools/doc_tools.py:119-150` — `DocResourceBudget` 冻结 dataclass，`__post_init__` 校验拒绝 bool/零/负数
- `dayu/tools/doc_tools.py:606` — 无参构造 `DocResourceBudget()`，固化默认值

**直接证据**:
```bash
grep -i "DocResourceBudget\|_DOC_SOURCE_MAX_BYTES\|_DOC_DIRECTORY_MAX_ENTRIES\|32.*1024.*1024\|10_000" docs/host/design.md docs/engine/design.md
# (零结果)
```
3654 行 host/design.md 没有任何章节定义文档工具资源预算。`context_budget_policy` 仅管 LLM 上下文窗口，`tool_truncation_policy` 仅管工具结果截断——都不是文档资源 input ceiling。

**R3-E plan 授权但未 canonicalize**: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md:216` 精确冻结了 `DocResourceBudget(max_source_bytes=32*1024*1024, max_directory_entries=10_000)`。plan 本身是临时授权文档，其 line 9 声明设计真源就是 `docs/host/design.md` 和 `docs/engine/design.md`。plan 接受后这些值没有写入永久设计真源。

**为何失败 / 成本放大**:
- 32 MiB 和 10,000 是用户可见行为：超过则拒绝读文件、目录扫描返回 `scan_complete=false`、LLM 看到 `truncated_reason=source_limit/directory_entry_limit`。
- 设计真源缺失意味着后续任何对该值的修改都没有设计级裁决依据。方案设计者无法从设计真源知道"文档资源预算是否存在、owner 是谁、修改需要走什么 gate"。
- 如果 model context window 增大（如 1M→2M），32 MiB 是否要跟进？如果 file 越来越大，是否要放宽？这些决策没有设计级 guidance。

**推荐修正边界**: 在 `docs/host/design.md` 新增"文档工具资源治理"节，冻结 `DocResourceBudget` 的 owner（文档工具 provider）、字段、默认值与修改 gate。32 MiB 和 10,000 作为初始冻结值写入设计真源。

**验证点**: `docs/host/design.md` 可搜索到 `DocResourceBudget`、`max_source_bytes`、`max_directory_entries`；值与代码一致。

---

### F-DS-02 — 高 — BoundedSourceSnapshot 状态机在设计真源中无授权

**语义/contract**: 层中立有界文档源快照，含完整生命周期状态机：unentered → entered/active → closed，附带 SpooledTemporaryFile 管理、materialize()、open() 独立读游标、不可复用防护。

**正确 owner**: `dayu.documents` 模块。`docs/engine/design.md` 描述了 Runner/Agent 生命周期（run-scoped, one-shot），但 `BoundedSourceSnapshot` 是不同的状态机——它有 context manager、spool、materialization、teardown 语义。

**漂移位置**: `dayu/documents/processors/bounded_source.py:164-459`

**直接证据**:
- Line 164: `class BoundedSourceSnapshot` —— 全新状态机，不在设计真源中
- Line 205: `_entered: bool` —— 状态跟踪
- Line 276: `__enter__` —— 读 Source、spool 拷贝、执行预算、进入 active
- Line 323: `__exit__` —— 调用 `close()`，进入 closed
- Line 289: `RuntimeError("bounded source snapshot cannot be reused")` —— 不可复用防护
- Line 346: `open()` —— 验证 active 状态的独立读游标
- Line 359: `materialize()` —— 幂等写入系统临时文件
- Line 401: `close()` —— 幂等清理

```bash
grep -i "BoundedSourceSnapshot\|bounded_source" docs/host/design.md docs/engine/design.md
# (零结果)
```

两个设计真源都没有定义这个状态机及其 lifecycle contract。Engine design 描述 Agent/Runner 生命周期，但不包括文档源快照。

**R3-E plan 授权但未 canonicalize**: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md:158-160` 明确要求 `BoundedSourceSnapshot` with `limit+1` byte overflow 和 `SourceBudgetExceeded`。与 F-DS-01 同为 canonicalization gap。

**为何失败 / 成本放大**:
- `BoundedSourceSnapshot` 不是内部实现细节——它直接决定 `read_file`/`read_file_section`/`get_file_sections` 的行为。状态机行为（复用拒绝、spool 管理、materialize 语义）是公共 contract。
- 测试 `tests/documents/test_processors.py:206-341` 已固化该状态机行为，但设计真源没有这些测试所保护的 contract 定义。
- 如果需要新增文档源类型（如 remote S3）、改 spool 策略、或支持 streaming read，没有设计级 guidance 说明状态机边界。

**推荐修正边界**: 在 `docs/host/design.md` 的文档工具资源治理节中描述 `BoundedSourceSnapshot` 的生命周期、状态集合、不可复用语义和预算执行边界。

**验证点**: 设计真源可搜索到 `BoundedSourceSnapshot`、`SourceBudgetExceeded`；生命周期状态与测试断言一致。

---

### F-DS-03 — 中 — list_files/search_files partial contract 在设计真源中无授权

**语义/contract**: 自描述 partial result schema——`scan_complete: bool`、`truncated_reason: "directory_entry_limit" | "source_limit" | "result_limit" | null`、`total: int | null`（null 表示不完整扫描）、`skipped_oversized_files: int`。这些字段直接进入 LLM 上下文（tool description 中说明下一步动作）。

**正确 owner**: 文档工具 tool outcome projection。它是 LLM-facing contract，必须在设计真源中定义。

**漂移位置**:
- `dayu/tools/doc_tools.py:698-705` — `list_files` LLM-facing description
- `dayu/tools/doc_tools.py:846-854` — `search_files` LLM-facing description
- `dayu/tools/doc_tools.py:1578-1586` — `list_files` partial success payload
- `dayu/tools/doc_tools.py:1684-1757` — `search_files` partial success payload

**直接证据**:
```bash
grep -i "scan_complete\|truncated_reason\|directory_entry_limit\|source_limit\|result_limit\|partial.scan" docs/host/design.md docs/engine/design.md
# (零结果)
```

**R3-E plan 授权但未 canonicalize**: plan lines 161-163, 217-221 冻结了 partial 字段和模型下一步指令。

**为何失败 / 成本放大**:
- 这些字段是 LLM-facing contract：LLM 被告知 `scan_complete=false` 时 `total=null`，且理解 `truncated_reason` 的含义。如果设计真源不记录，未来修改这些 field 的语义需要从 plan artifact 考古而非从设计真源读取。
- `truncated_reason` 的三个枚举值（`directory_entry_limit`、`source_limit`、`result_limit`）构成闭集 contract，但设计真源未定义。

**推荐修正边界**: 在 `docs/host/design.md` 的文档工具资源治理节中冻结 partial success schema、字段含义、枚举值与 LLM-facing 说明。

**验证点**: 设计真源可搜索到 `scan_complete`、`truncated_reason`；枚举值与代码一致。

---

### F-DS-04 — 中 — Engine 内部异常消息截断 (_EXCEPTION_MESSAGE_MAX_LENGTH=240) 在设计真源中无授权

**语义/contract**: Engine Agent 内部将异常消息截断至 240 字符，附加 `"... [truncated]"` 后缀。该截断影响 `RunFailedData.message`——即 `run_failed` EngineEvent 中 LLM 和调用方可看到的错误消息。

**正确 owner**: Engine（`dayu/engine/agent.py`）。`docs/engine/design.md` 定义了 `run_failed` 终态和 `RunFailedData`，但没有定义消息长度限制。

**漂移位置**: `dayu/engine/agent.py:220` — `_EXCEPTION_MESSAGE_MAX_LENGTH: int = 240`

**直接证据**:
```bash
grep "message.*length\|message.*truncat\|exception.*truncat\|_EXCEPTION_MESSAGE_MAX\|240" docs/engine/design.md
# (零结果)
```

`docs/engine/design.md` 没有定义异常消息的长度上限。

**为何失败 / 成本放大**: 240 字符截断直接影响 run_failed 事件的诊断质量。如果 long chain traceback 或 provider error detail 超过 240 字符，调用方的错误恢复逻辑可能丢失关键信息。这不是高严重度（内部 safety measure），但作为 EngineEvent 中用户可见字段的格式化规则，应有设计级授权。

**推荐修正边界**: 在 `docs/engine/design.md` 的 run_failed 节中记录消息截断策略：owner、上限、后缀与 desensitization 规则。

**验证点**: 设计真源可搜索到 message truncation 策略描述。

---

## 已确认未修复 Finding（来自 codex audit）

以下 finding 已在 `docs/reviews/wu-semantic-ownership-01-overdesign-audit-codex.md` 中详细报告，本审查确认:

- **F-01（高，未修复）**: `dayu/host/accepted_result_projection.py:518-576` — Host 用参数字段名黑名单重定义 LLM-safe contract。合法工具调用（`file_path`、`scope_token`）被整体降级为 `arguments_summary_unsafe`。与 `docs/host/design.md:1613` 的 producer-owns-safe-projection 原则矛盾。
- **F-02（中，未修复）**: `dayu/host/accepted_result_projection.py:61-71, 644-735` — 未知 `OpaqueEvidenceRef` 被默认升格为业务来源，违反 plan 的 stop condition。
- **F-03（中，未修复）**: `dayu/tools/doc_tools.py:1163-1215` — Doc 暴露计划外公开错误码 `source_budget_exceeded`，与 R3-E plan 授权的 `source_too_large` 不一致。

## 工具安全专项说明

### 未授权工具安全代码

**F-01（高，未修复）** 是唯一确认的未授权 tool-security-like policy：`accepted_result_projection.py` 用参数字段名黑名单重定义 LLM-safe contract。它不是局部日志防护，而是同时进入 RunInput、Memory、CompactMaterial 和 Tool Trace 的共享 LLM-facing contract。详见 codex audit。

### 有明确授权的局部工具安全实现（不报告）

以下工具安全实现有 R3-E accepted plan 逐项授权（代码在执行，plan 已接受，但设计真源未 canonicalize——已在 F-DS-01/F-DS-02/F-DS-03 中覆盖）：

- **Web egress policy**: DNS-pinned per-hop `AuthorizedHttpTarget`、peer 验证、private-network fail-closed（`dayu/tools/web/web_egress_policy.py`）
- **Web resource budget**: `wire_body_bytes=25MiB` 等 7 字段（`dayu/tools/web/web_resource_budget.py`）
- **Doc allowed_paths**: provider config 白名单（`dayu/tools/doc_provider.py:27-30`）
- **Doc source/directory budgets**: 即 F-DS-01/F-DS-02/F-DS-03

### R3-E plan 明确拒绝的工具安全项

以下项在 R3-E plan `:526-547` 中明确拒绝为 repository-wide framework，本范围代码中未发现违规实现：
- Repository-wide tool-security framework
- Fins file authority
- Upload symlink policy
- Fins remote egress
- Generic browser sandbox
- Doc generic file authority

### 与既有 artifact 的一致性

`docs/reviews/wu-semantic-ownership-01-tool-security-artifact-code-audit.md:28-43` 的全局结论"WU to date 未加入 tool-security code"因关键词扫描遗漏 F-01 而不成立。详见 codex audit `:172-176`。当前 HEAD 的 tool-security 代码分为两类：有授权的局部实现（Web/Doc）和无授权的通用 policy（F-01）。

## 非 Finding 裁决

| 候选 | 代码位置 | 裁决 |
| --- | --- | --- |
| `HOST_EVENT_STREAM_MAX_LIMIT = 1000` | `dayu/host/api.py:79` | **不报告**。`docs/host/design.md:1300` 明确要求"超过 Host read 最大 limit 时返回 invalid_state...默认值和最大值必须集中定义"。 |
| `HOST_OUTBOX_TERMINAL_READ_MAX_LIMIT = 500` | `dayu/host/api.py:89` | **不报告**。同上 authorization；属于 Host read API 的防御上限。 |
| `HOST_WAIT_*_MAX_LENGTH = 128/256/512/2048` | `dayu/host/api.py:80-88` | **不报告**。SQLite column 长度约束，schema implementation detail，非 policy-level limit。 |
| `_RUNNER_SPECIFIC_ERROR_CODE_MAX_CHARS = 128` | `dayu/engine/contracts/error_codes.py:15` | **不报告**。防御性输入校验——provider 原生错误码超过 128 chars 的可能性极低。虽有设计真源未覆盖，但属于合理的 implementation safety measure。 |
| `_SPOOL_MEMORY_BYTES = 1 MiB` | `dayu/documents/processors/bounded_source.py:22` | **不报告**。内部 `SpooledTemporaryFile` 阈值，implementation detail。 |
| `DEFAULT_MEMORY_CONTEXT_WINDOW_SIZE = 8192` | `dayu/host/memory.py:49` | **不报告**。默认值虽小（8192 vs 真实窗口 256K-1M），但 `docs/host/design.md:95` 要求 Service/composition root 从 model config 传入真实 `context_window_tokens`，默认值只在未传时 fallback。属于调用方必须 override 的 sentinel，非 over-design。 |
| ConfigLoader `context_window_class` hard-coded taxonomy `{256k, 1m}` | `dayu/runtime/config_loader.py:54-60` | **不报告**。`docs/host/design.md:89` 授权 `context_window_class` 作为校验字段，且写作"可增加"（暗示 opt-in 但允许实现）。当前实现把 taxonomy 作为 closed set 是合理的配置校验，未超越 design doc 边界。 |
| `ToolDuplicateGovernancePolicyConfig` messages 字段 | `dayu/runtime/config_loader.py:382-417` | **不报告**。`docs/host/design.md:2162-2258` 以 90+ 行详细定义了 duplicate governance 的目标、scope、policy 和模型可见提示。7 个 message 字段是对 design 的 typed 实例化。 |
| `ContextOverflowDetectionKind` 含 `STRUCTURED_CODE` 和 `NOT_OVERFLOW` | `dayu/engine/contracts/runner_events.py:91-97` | **不报告**。`docs/engine/design.md` 仅显式提及 `message_marker_fallback`，但 Runner 内部需要三态分类才可正确驱动 Agent。这是 Runner 协议实现的内部分类，非 Engine 对外 contract。 |
| FinsToolLimits（`list_documents_max_items=300` 等） | `dayu/fins/tools/fins_limits.py` | **不报告**。Engine design 明确 Engine 不负责财报语义，Host design 明确 Host 不承载财报业务语义。Fins tool limits 是业务工具局部设计，其 owner 是 `dayu.fins.tools`，不在两个设计真源覆盖范围。 |
| Web/Playwright egress gating 与 resource budgets | `dayu/tools/web/` | **不报告**。R3-E accepted plan 逐项授权；本审查只确认设计真源 canonicalization gap（F-DS-01/02/03）。 |
| `_SECTION_CONTENT_CACHE_MAX_ENTRIES = 256` | `dayu/documents/processors/docling_processor.py:49` | **不报告**。LRU 缓存内部 bound，implementation detail。 |

## Open Questions

1. **DocResourceBudget 的正确 owner 层级**：当前 `DocResourceBudget` 在 `dayu/tools/doc_tools.py`（tool 层），但它管理的是 document processor 资源——是否应上提到 `dayu.documents` 或作为 Host policy？如果后续有 Fins document tools 需要不同的 budget，owner 层级需要明确。
2. **BoundedSourceSnapshot 是否应进入 `dayu.runtime`**：它的设计目标是"层中立"有界源快照。如果将来 Web tools 也用它做 bounded response body，它是否应移至 runtime 而非留在 documents 包？
3. **设计真源 canonicalization 的 gate 流程**：R3-E plan 接受后未写入设计真源。是否需要明确 gate：accepted plan 的持久化设计条款必须在 WU closeout 前写入对应设计真源？

## Residual Risk

- **设计真源与 accepted plan 的质量鸿沟**：3654 行 `docs/host/design.md` 没有"文档工具""Web 工具""外部资源"章节，但这些能力已在生产代码中。F-DS-01/02/03 只是这个鸿沟的 3 个实例；Web egress policy、Web resource budget、Doc allowed_paths 同样缺失。如果不建立 plan→design canonicalization gate，鸿沟会继续扩大。
- **F-01 的 cross-consumer 固化**：argument-key blacklist 已通过测试固化到 RunInput、Memory、CompactMaterial、Tool Trace 四个消费者。修复 F-01 需要同时修改四个消费者的测试，风险较高。
- **测试与设计真源的脱节**：`tests/documents/test_processors.py:206-341` 固化 `BoundedSourceSnapshot` 的溢出、cleanup、不可复用行为——这些测试保护的是 R3-E plan 定义的 contract，而非设计真源定义的 contract。如果未来设计真源修改了 contract，这些测试会成为反向阻力。
- **Host/Engine/Runtime 核心投影无新增 unauthorized content**：三个核心层（Host durable state/eventlog/memory、Engine contracts/events、Runtime lane/cancellation/config）经逐文件走读，未发现设计真源未授权的共享投影、状态机、error code 或 LLM-facing 语义写入。主要风险集中在 Documents 层和工具层的设计真源 canonicalization gap。
