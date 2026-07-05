# Code Review — WU-TOOLS-CANCEL-01 S2C Fins read process-backed

## Scope

- Mode: current changes (uncommitted workspace diff)
- Branch: phase/wu-tools-cancel-01
- Base: main (committed HEAD)
- Output file: docs/reviews/wu-tools-cancel-01-s2c-code-review-ds.md
- Included scope:
  - `dayu/fins/tools/fins_tools.py` (uncommitted diff)
  - `dayu/fins/tools/provider.py` (uncommitted diff)
  - `tests/fins/test_fins_storage_provider.py` (uncommitted diff)
  - `dayu/fins/README.md` (uncommitted diff)
  - `tests/README.md` (uncommitted diff)
  - `docs/reviews/wu-tools-cancel-01-s2c-implementation-codex.md` (implementation note)
- Excluded scope: committed S2A1/S2A2/S2B slices, Host/Engine internals, download/preprocess/upload tools (only added mandatory `execution` field per S2A1 contract migration, no behavioral change)
- Parallel review coverage: 无（单 reviewer 逐行走读）

## Review Method

按 deepreview skill 定义的 Current Changes Mode 执行。沿九个 Fins read 工具的真实执行路径逐行走读：

1. `build_fins_read_tool_definitions` → 工具声明 → `ProcessBackedToolExecutionCapability`
2. `_FinsReadProcessTargetFactory.build_process_target` → `_FinsReadProcessTarget` 构造
3. `_FinsReadProcessTarget.__call__` → `DefaultFinsRuntime.create` → `_execute_fins_read_business_value` → `_route_fins_read_business`
4. `_invoke_fins_read_business` (direct callable fallback)
5. `discover_tools` → provider 装配 → validation

对照 S2C 审查清单逐项检查，并执行 adversarial failure pass。

## Findings

### 01-低-query_xbrl_facts 与 get_financial_statement 缺少 spawned-child process target 覆盖

- **入口/函数**: `test_fins_read_process_target_runs_in_spawned_child` (test_fins_storage_provider.py:837) 及 process target `_FinsReadProcessTarget.__call__` (fins_tools.py:249)
- **文件(行号)**: tests/fins/test_fins_storage_provider.py:837-853, dayu/fins/tools/fins_tools.py:1185-1279
- **输入场景**: 通过 spawned child 执行 `query_xbrl_facts` 或 `get_financial_statement` 工具
- **实际分支**: 当前 spawned-child 测试只覆盖 `list_documents`（line 841-845）；process target 覆盖 `search_document`（processor path）和 `list_tables`（table path），但 `query_xbrl_facts` 与 `get_financial_statement` 仅有 direct callable fallback 的取消测试，没有 process target 或 spawned-child 测试
- **预期行为**: typed plan Section "Fins read" 要求"九个 read tools 至少覆盖一条 fast path、一条 processor path、一条 XBRL / table path"，当前 `list_tables` 满足 table path 要求；但 `query_xbrl_facts` 与 `get_financial_statement` 通过 `FinancialDataProcessor` protocol（而非 `DocumentProcessor` protocol）调用，该 protocol 的 `query_xbrl_facts(...)` / `get_financial_statement(...)` 方法签名与 `DocumentProcessor` 不同
- **实际行为**: `list_tables` 的 spawned-child 成功不能证明 `FinancialDataProcessor` protocol 在子进程中正确装配。若 processor registry 在子进程中未正确注册 `FinancialDataProcessor` 实现，`query_xbrl_facts` 和 `get_financial_statement` 可能静默失败或返回不完整结果
- **直接证据**: `_route_fins_read_business` lines 1253-1278 调用 `read_runtime.get_financial_statement(...)` 和 `read_runtime.query_xbrl_facts(...)`，两者依赖 `FinancialDataProcessor` protocol；`test_fins_read_process_target_processor_and_table_paths` line 789 只覆盖到 `search_document` 和 `list_tables`；`test_fins_read_process_target_runs_in_spawned_child` line 837 只覆盖 `list_documents`
- **影响**: 若 `FinancialDataProcessor` 在子进程 `DefaultFinsRuntime.create()` 装配中缺失，`query_xbrl_facts` / `get_financial_statement` 的工具调用可能在生产 process-backed 路径返回 failed 信封或空结果，而 direct callable fallback 测试无法发现
- **建议改法和验证点**: 增加一条 spawned-child test，在真实临时 workspace 中通过 `ProcessBackedToolExecutionCapsule` 执行 `query_xbrl_facts` 或 `get_financial_statement`（或两者），验证 `completed` 信封包含合法的 facts/rows 结构
- **修复风险（低）**: 仅新增测试，不改变生产代码
- **严重程度（低）**: typed plan 中"XBRL / table path"的 `/` 可解释为 alternative（`list_tables` 已覆盖 table path），因此不构成 plan contract violation；但 `FinancialDataProcessor` 的 process-backed 可行性缺少直接证据，属于 residual risk 应明确记录

### 02-低-_cancelled_from_token 接受但未使用 cancellation_token 参数

- **入口/函数**: `_cancelled_from_token` (fins_tools.py:1396)
- **文件(行号)**: dayu/fins/tools/fins_tools.py:1396-1422
- **输入场景**: `_invoke_fins_read_business` 在 `cancellation_token.is_cancelled()` 返回 True 时调用
- **实际分支**: 函数签名接受 `cancellation_token: CancellationToken`，但函数体第一行 `del cancellation_token`（line 1415）立即丢弃该参数，后续硬编码取消消息
- **预期行为**: 函数名 `_cancelled_from_token` 暗示会从 token 提取信息构造 outcome；或应重命名为 `_cancelled_outcome_for_fins_read` 等更准确描述行为的名称
- **实际行为**: 消息与 hint 完全硬编码（lines 1416-1422），不读取 `cancellation_token.cancel_reason()`。虽然这是有意设计（避免 Host 治理原因泄漏到 LLM-facing 文本），但函数名和签名给人以"会使用 token"的假象
- **直接证据**: fins_tools.py:1415 `del cancellation_token` — 这是 unused parameter suppression pattern
- **影响**: 仅影响代码可读性，无运行时影响。未来维护者可能误以为该函数会使用 token 信息
- **建议改法和验证点**: 改为只接受 `tool_name: str, started_at: datetime` 并重命名为 `_build_fins_read_cancelled_outcome`，或在 docstring 中显式说明"不读取 token reason 以避免 Host 治理信息泄漏"
- **修复风险（低）**: 函数签名变更需要同步更新两处调用点（lines 1007, 1010）
- **严重程度（低）**: 纯可读性问题，无正确性影响

### 03-低-_FinsReadProcessTarget 通用异常处理丢失 hint 信息

- **入口/函数**: `_FinsReadProcessTarget.__call__` (fins_tools.py:249)
- **文件(行号)**: dayu/fins/tools/fins_tools.py:284-289
- **输入场景**: 子进程内 `DefaultFinsRuntime.create()` 或 `runtime.get_read_runtime()` 抛出非 `_FinsReadBusinessFailure` 异常
- **实际分支**: `except Exception` 捕获后构造 `{"status": "failed", "error_type": "execution_error", "message": "Tool ... execution failed."}`（line 284-289）
- **预期行为**: direct callable fallback 的同类异常处理（`_invoke_fins_read_business` line 1066-1074 和 `_execute_fins_read_business_value` line 1150-1155）会附带 `_UNEXPECTED_FAILURE_HINT`（"Inspect provider diagnostics or retry with narrower arguments."），为 LLM 提供恢复指导
- **实际行为**: process target 的通用异常处理只有错误类型和消息，缺少 hint。对比 `_process_failed_envelope`（line 1316）会将 hint 附加到 message，但该路径仅处理 `_FinsReadBusinessFailure`；基础设施级异常（`DefaultFinsRuntime.create` 失败等）的 LLM-facing 消息缺少恢复提示
- **直接证据**: fins_tools.py:284-289 vs fins_tools.py:1067-1073（direct callable 有 hint）
- **影响**: 基础设施故障时 LLM 收到的错误消息缺少恢复指导，可能触发无意义重试
- **建议改法和验证点**: 将 line 289 的 message 改为 `f"Tool {self.tool_name!r} execution failed. Hint: {_UNEXPECTED_FAILURE_HINT}"`，与 direct callable 路径保持一致
- **修复风险（低）**: 仅修改一条字符串拼接
- **严重程度（低）**: 只在罕见的子进程基础设施故障时触发，不影响正常业务流程

## Checklist Verification

### 1. 九个 Fins read definitions 全部声明 ProcessBackedToolExecutionCapability ✅

`build_fins_read_tool_definitions` (lines 114-123) 为所有九个工具声明 `ProcessBackedToolExecutionCapability(target_factory=process_target_factory)`。测试 `test_fins_read_definitions_declare_process_backed_execution` (test_fins_storage_provider.py:728) 逐一定位验证 `isinstance(definition.execution, ProcessBackedToolExecutionCapability)`。

S2A2 declaration-backed Host factory 已在上一个 committed slice 落地（`dayu/host/tool_runtime.py`），production default 从 `ToolDefinition.execution` 选择 capsule。

### 2. Process target/factory 只保存可序列化字段 ✅

`_FinsReadProcessTarget` (line 219) 字段：`workspace_root_locator: str`、`tool_name: str`、`arguments: dict[str, JsonValue]`、`limits: FinsToolLimits`、`timeout_seconds: float | None`。

`_FinsReadProcessTargetFactory` (line 296) 字段：`workspace_root_locator: str`、`limits: FinsToolLimits`。

pickle round-trip 测试 (test_fins_storage_provider.py:739) 验证 forbidden fragments 不在序列化 payload 中：`FinsReadRuntime`、`Repository`、`provider_lock`、`CancellationToken`、`session-fins`、`run-fins`。

`timeout_seconds` 在 `__call__` 中被赋给 `_`（line 263），子进程不消费该值——timeout 治理完全由父进程 capsule 独占，符合 typed plan 要求。

### 3. 子进程通过 DefaultFinsRuntime.create 和 storage 仓储路线重建 ✅

`_FinsReadProcessTarget.__call__` (line 272) 调用 `DefaultFinsRuntime.create(workspace_root=Path(self.workspace_root_locator))`，然后 `runtime.get_read_runtime(processor_cache_max_entries=self.limits.processor_cache_max_entries)`。所有财报文件访问仍通过 `dayu.fins.storage` 仓储协议。

`test_fins_read_process_target_runs_in_spawned_child` 通过真实 `ProcessBackedToolExecutionCapsule` 验证子进程内 `DefaultFinsRuntime` 重建可行性。

### 4. Schema、成功 payload、failure code/message/hint、truncate spec 自解释且无 regression ✅

- 参数 schema 保持自足说明（field name、type、description、required、enum），九个参数 schema 定义（lines 1425-1726）未修改
- Process completed 信封：`{"status": "completed", "value": <原始业务值>}`，与 `ProcessBackedToolTarget` 协议一致
- Process failed 信封：`{"status": "failed", "error_type": str, "message": str}`，hint 通过 `_process_failure_message` 附加到 message（line 1336），因为 Host process envelope 无独立 hint 字段
- 截断声明（`_text_truncate`、`_list_truncate`）未改变
- Finding 03 指出通用异常路径缺少 hint，但属低严重度

### 5. Direct callable fallback 仅为测试/非生产 fallback ✅

`_invoke_fins_read_business` docstring (lines 983-990) 明确声明："生产默认路径不再经过本函数；九个 Fins read `ToolDefinition.execution` 均声明为 process-backed...本函数只保留给直接调用 `ToolDefinition.callable` 的测试和非生产 fallback"。

测试 `test_fins_read_definitions_declare_process_backed_execution` 确认所有九个定义的 `execution` 为 `ProcessBackedToolExecutionCapability`，生产路径不会进入 `_invoke_fins_read_business`。

### 6. 测试覆盖真实 spawned child、fast/processor/table path、failed envelope、cancel drops late result ✅

| 测试 | 路径 | 覆盖 |
|------|------|------|
| `test_fins_read_process_target_runs_in_spawned_child` | spawned child + fast path (`list_documents`) | ✅ |
| `test_fins_read_process_target_fast_path_uses_default_runtime` | 同进程 fast path | ✅ |
| `test_fins_read_process_target_processor_and_table_paths` | processor path (`search_document`) + table path (`list_tables`) | ✅ |
| `test_fins_read_process_target_failure_envelope` | failed 信封（参数缺失） | ✅ |
| `test_fins_read_process_backed_cancel_drops_late_result` | ToolRuntime 取消 → late result 被丢弃 | ✅ |
| `test_fins_read_process_target_factory_pickle_round_trip` | factory + target pickle 序列化 | ✅ |

Finding 01 指出 `query_xbrl_facts` / `get_financial_statement` 缺少 spawned-child 覆盖，但 typed plan 的"XBRL / table path"中的 `/` 可解释为 alternative。

### 7. 不影响 download/preprocess/upload WAITING tools ✅

download/preprocess/upload tools 的唯一变更是新增 `execution=AsyncDirectToolExecutionCapability()` 字段（S2A1 contract 迁移要求所有 `ToolDefinition` 直接构造站点显式声明 execution），不改变 WAITING 工具行为。`test_read_provider_only_exposes_read_tools` 验证 read provider 不混入 download/preprocess/upload 工具。

### 8. AGENTS.md 硬约束 ✅

- **类型**: 所有函数/方法签名均有完整类型标注，无 `Any`/`object` 签名
- **docstring**: 所有新增/修改的函数、类、方法均有完整中文 docstring
- **无 `hasattr`/`getattr`**: 搜索结果为空
- **README 触发**: `dayu/fins/README.md` 已更新 read 路径描述（line 497-501），`tests/README.md` 已更新 Fins process-backed 覆盖记录（line 179）

## Open Questions

- 无。

## Residual Risk

1. **`FinancialDataProcessor` 子进程装配可行性未经直接验证**：`query_xbrl_facts` 和 `get_financial_statement` 依赖 `FinancialDataProcessor` protocol，该 protocol 的 `query_xbrl_facts(...)` / `get_financial_statement(...)` 方法与 `DocumentProcessor` 不同。当前 spawned-child 测试只覆盖 `list_documents`（使用 `DocumentProcessor`），未验证 `FinancialDataProcessor` 实现在子进程中正确注册。建议后续补充一条 focused spawned-child test。

2. **多工具并发 process-backed 的资源竞争未测试**：当前测试每次只执行一个 process-backed 工具。多个 Fins read tools 同时以独立子进程执行时，workspace-scoped file lock（`FsBatchingRepository`）是否会产生 contention 或 deadlock 未经验证。typed plan 明确 process-backed 绕过父进程 provider lock，子进程各自独立打开只读仓储，但文件系统级锁行为需要进一步确认。

3. **`FinsToolLimits` 序列化假设**：`FinsToolLimits` 是一个 dataclass，当前可以 pickle。但如果未来 `FinsToolLimits` 增加不可序列化字段，process target 的 pickle 会静默失败。该风险由现有 pickle round-trip 测试部分覆盖。

## Verdict

**PASS**

九个 Fins read tools 的 process-backed 迁移实现正确：全部声明 `ProcessBackedToolExecutionCapability`，process target/factory 只保存可序列化 locator 和标量，子进程通过 `DefaultFinsRuntime.create(workspace_root=Path(...))` 和 `dayu.fins.storage` 仓储重建 read runtime，schema/truncate/failure envelope 保持自解释，direct callable fallback 已降级为非生产路径，测试覆盖 spawned child、fast/processor/table path、failed envelope 和 cancel late result drop，download/preprocess/upload WAITING 工具不受影响，AGENTS.md 硬约束全部满足。

三个低严重度 finding（01: XBRL spawned-child 覆盖缺口，02: 函数命名误导，03: 通用异常缺少 hint）均不阻塞 merge，建议在后续 slice 中按优先级处理。
