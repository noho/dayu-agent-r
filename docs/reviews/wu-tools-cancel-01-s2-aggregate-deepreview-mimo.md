# WU-TOOLS-CANCEL-01 S2 Aggregate Deepreview - AgentMiMo

## Scope

- Mode: aggregate review (current branch)
- Branch: `phase/wu-tools-cancel-01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-cancel-01-s2-aggregate-deepreview-mimo.md`
- Included scope: S2A1 `32030ca9`, S2A2 `0fea8da0`, S2B `03e546f5`, S2C `834b0df6`, S2D `94b3c196` 合并后的完整 typed execution 实现；S2E validation artifact `docs/reviews/wu-tools-cancel-01-s2e-aggregate-validation-codex.md`
- Excluded scope: S1 interrupt capsule、Host cancel public API、Engine public contract、durable schema、WU-WAIT-03 / Fins WAITING lifecycle
- Parallel review coverage: contract/declaration/digest、Host factory wiring、Doc/Fins/Web providers、test coverage 四个维度由 subagent 并行深挖

## Findings

### 01-未修复-低-`FinsToolLimits` 缺少 `slots=True`

- **入口/函数**: `dayu/fins/tools/fins_limits.py:8` `FinsToolLimits` 类定义
- **文件(行号)**: `dayu/fins/tools/fins_limits.py:8`
- **输入场景**: 所有 Fins read process-backed 工具的 limits 参数
- **实际分支**: `@dataclass(frozen=True)` — 无 `slots=True`
- **预期行为**: 与 `DocToolLimits`（`dayu/tools/doc_tools.py:86`，`@dataclass(frozen=True, slots=True)`）保持一致的 dataclass 声明风格
- **实际行为**: `FinsToolLimits` 使用 `@dataclass(frozen=True)` 而无 `slots=True`，导致实例有 `__dict__` 而非 `__slots__`
- **直接证据**: `dayu/fins/tools/fins_limits.py:8` vs `dayu/tools/doc_tools.py:86`；`hasattr(FinsToolLimits, '__slots__')` 返回 `False`
- **影响**: 功能无影响——`frozen=True` dataclass 仍可 pickle round-trip、multiprocessing spawn 序列化正常。但缺少 `slots=True` 会增加每个实例的内存开销（`__dict__` vs `__slots__`），且与项目内同类 limits dataclass 风格不一致
- **建议改法和验证点**: 在 `FinsToolLimits` 的 `@dataclass` 装饰器加 `slots=True`：`@dataclass(frozen=True, slots=True)`。验证 `pytest tests/fins/` 仍通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-process envelope fail-closed 测试未覆盖 `completed` 缺 `value`

- **入口/函数**: `dayu/host/tool_runtime.py:6555` `_completed_outcome_from_process_envelope()`
- **文件(行号)**: `tests/host/test_toolruntime_executor.py:1679-1694` parametrized test
- **输入场景**: 子进程返回 `{"status": "completed"}` 但缺少 `value` 字段
- **实际分支**: 代码正确处理——`_completed_outcome_from_process_envelope` 检查 `_PROCESS_ENVELOPE_COMPLETED_VALUE_FIELD not in envelope`，返回 `process_backed_tool_malformed_envelope`
- **预期行为**: 测试矩阵应覆盖此信封形态
- **实际行为**: `test_process_backed_capsule_fail_closes_unsupported_envelopes` 的 7 个 parametrized case 覆盖了 missing `status`、`awaiting`/`cancelled`/`timeout`/`host_cancelled`、`unknown`、`failed` with empty `error_type`，但未覆盖 `{"status": "completed"}` 缺 `value`
- **直接证据**: `tests/host/test_toolruntime_executor.py:1683-1694` parametrized 列表中无 `{"status": "completed"}` case；`dayu/host/tool_runtime.py:6563-6567` 代码路径存在但无测试覆盖
- **影响**: 若未来重构 `_completed_outcome_from_process_envelope` 时遗漏 `value` 字段检查，无测试能捕获回归
- **建议改法和验证点**: 在 parametrized 列表增加 `({"status": "completed"}, "process_backed_tool_malformed_envelope")` case
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 03-未修复-低-process target 抛异常路径无独立测试

- **入口/函数**: `dayu/host/tool_runtime.py:1775` `ProcessBackedToolExecutionCapsule.run()`
- **文件(行号)**: `tests/host/test_toolruntime_executor.py`
- **输入场景**: process target 的 `__call__()` 抛出异常（如 `OSError`、`pickle.UnpicklingError`）而非返回 JSON 信封
- **实际分支**: `InterruptibleProcessHandle.wait()` 返回 `InterruptibleProcessFailed`，capsule 映射为 `ToolFailedOutcome(error="process_backed_tool_failed")`
- **预期行为**: 测试应覆盖 process target 抛异常的场景
- **实际行为**: 所有测试 target 均返回 JSON 信封；无 target 抛异常的测试。`InterruptibleProcessFailed` → `ToolFailedOutcome` 路径仅被 `test_interruptible_process.py` 的底层测试隐式覆盖
- **直接证据**: `tests/host/test_toolruntime_executor.py` 中无 `_RaisesProcessTarget` 或等价异常测试 target；`dayu/host/tool_runtime.py:1795-1798` 的 `InterruptibleProcessFailed` 分支无 Host-level capsule 测试
- **影响**: 若 `InterruptibleProcessHandle` 的异常传播行为变化，Host capsule 层无回归保护
- **建议改法和验证点**: 增加一个 `ProcessBackedToolExecutionCapsule` 测试，target `__call__` 抛 `RuntimeError`，断言 outcome 为 `ToolFailedOutcome` 且 error 为 `process_backed_tool_failed`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 04-未修复-低-`ToolRuntimeBuildRequest.execution_capsule_factory` docstring 轻微失准

- **入口/函数**: `dayu/host/tool_runtime.py:2722` `ToolRuntimeBuildRequest.execution_capsule_factory` 字段
- **文件(行号)**: `dayu/host/tool_runtime.py:2722`
- **输入场景**: 开发者阅读 `ToolRuntimeBuildRequest` 的 docstring 理解该字段用途
- **实际分支**: docstring 写"测试用内部 execution capsule factory override"
- **预期行为**: 该字段是通用 DI 注入点（`ToolExecutionCapsuleFactory | None`），当 `None` 时回退到 `DeclaredToolExecutionCapsuleFactory`；docstring 应准确描述其为通用注入 seam
- **实际行为**: "测试用内部"措辞暗示该字段仅供测试，低估了其作为通用 DI 机制的生产相关性
- **直接证据**: `dayu/host/tool_runtime.py:2722` docstring vs `dayu/host/tool_runtime.py:3984-3986` 实际 fallback 逻辑
- **影响**: 当前无功能影响——生产 dispatch 不注入该字段。但对考虑扩展该注入点的开发者可能造成误导
- **建议改法和验证点**: 将 docstring 改为"execution capsule factory 注入点；无则按 effective ``ToolDefinition.execution`` 声明创建 capsule；生产默认不注入，测试可覆盖"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。所有审查维度的证据链完整，无阻碍 confident judgment 的问题。

## Residual Risk

| 风险 | 当前证据 | 分类 | Owner / 目标 |
|---|---|---|---|
| Web process 冷启动成本 | Web 使用 per-call process-backed；测试验证正确性非性能 | Accepted, non-blocking。#87 closeout 优先可抢占性与 late-result 隔离 | 后续性能工作，若生产遥测显示显著成本 |
| Process failed envelope 无独立 `hint` 字段；Doc/Fins/Web 通过 `message` 附带 hint | 测试覆盖 hint 文本保留在 message 中；Host capsule 契约当前只消费 `error_type` 和 `message` | Accepted，非当前修复。修改 envelope 是 Host process contract hardening 任务 | 后续 Host process envelope contract hardening |
| Playwright nested process cleanup under process-backed Web cancel | Web 测试覆盖 process-backed cancel、Playwright cancel projection、pre-cancel no-start、unpicklable worker fail closed；未在 ToolRuntime cancel 下启动真实浏览器进程树 | Accepted with explicit residual。当前生产不再回落到同进程执行，父进程 cancel 仍阻止 late accept | 后续 Web/Playwright cleanup smoke 或 stress test |
| `query_xbrl_facts` spawned child 无真实 XBRL instance fixture | S2C 覆盖 9 个 definition、fast/processor/table path、`get_financial_statement` spawned child、`query_xbrl_facts` cooperative cancellation；缺失的是 spawned child 内真实 XBRL 实例解析 | Accepted low residual, non-blocking | 后续 Fins XBRL fixture 扩展 |
| Doc FIFO fixture 扩展了 `read_file` 支持的文件类型 | S2B review 接受，因 allowed-root 边界保持且风险由 process-backed cancel/timeout 约束 | Accepted residual, non-blocking | 后续 Doc test strategy / security review |
| `FinsToolLimits` 缺少 `slots=True`（Finding 01） | `frozen=True` 仍可 pickle；与 `DocToolLimits` 风格不一致 | Accepted low residual | 后续 style cleanup |
| `completed` 缺 `value` 信封测试缺失（Finding 02） | 代码正确处理，仅缺测试 | Accepted low residual | 后续 test hardening |
| process target 抛异常测试缺失（Finding 03） | `InterruptibleProcessFailed` 路径被底层测试隐式覆盖 | Accepted low residual | 后续 test hardening |

## Verification Matrix Review

S2E validation artifact 记录的验证命令和结果：

| 验证项 | 结果 | 备注 |
|---|---|---|
| `pytest tests/host/test_toolruntime_executor.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/web/test_web_tools_provider.py -q` | 219 passed, 3 warnings | warnings 来自第三方 `edgar` deprecation |
| `pytest tests/contracts tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q` | 92 passed | 覆盖 S2A1/S2A2 contract、discovery digest、declaration-backed wiring |
| `pyright` | 0 errors, 0 warnings | |
| `git diff --check` | no output | |

验证矩阵足够。S2A1 contract/discovery 测试和 S2A2 Host wiring 测试均已纳入 S2E aggregate 验证范围。

## Production Execution Mode Matrix Review

| 工具族 | 工具数 | 模式 | 语义闭环 |
|---|---|---|---|
| Doc | 5 | `process_backed` | ✅ factory 不捕获 lock/processor/runtime；child 内路径校验；cancel 后无 late result |
| Fins read | 9 | `process_backed` | ✅ factory 不捕获 runtime/repository/lock；child 重建 `DefaultFinsRuntime`；cancel 后无 late result |
| Fins download/preprocess/upload | 3 | `async_direct` (awaiting) | ✅ 返回 `EXTERNAL_JOB`；不纳入 process-backed closeout |
| Web | 2 | `process_backed` | ✅ factory 不捕获 Session/Browser/Playwright；child 内创建 session；cancel 后无 late result |

## Architecture Constraint Compliance

| 约束 | 状态 |
|---|---|
| 分层：UI → Service → Host → Engine | ✅ execution capability 在 `dayu.contracts`，Engine 不消费 |
| `dayu.runtime` 不 import Host/Engine/Service/UI/Fins | ✅ `tools_discovery.py` 只依赖 `dayu.contracts` |
| 类型严格：无 `Any`、无 `object`、无无类型参数 | ✅ 所有新增签名强类型 |
| 完整中文 docstring | ✅ 所有新增模块/类/函数/docstring 完整 |
| 无兼容胶水/兼容 wrapper | ✅ 无旧接口兼容读取 |
| 无过度设计 | ✅ 最小化 execution capability 契约 |
| Host 不按工具名特判 | ✅ `DeclaredToolExecutionCapsuleFactory` 按 capability type dispatch |
| 业务工具不 import Host internals | ✅ provider 只依赖 `dayu.contracts` |
| 无 `extra payload` / raw dict | ✅ 显式 typed field |

## README / Design Sync

| 文档 | 状态 | 依据 |
|---|---|---|
| `dayu/host/README.md` | ✅ 已同步 | 记录了 process-backed 执行形态、accept barrier、Engine schema 边界 |
| `dayu/fins/README.md` | ✅ 已同步 | 记录了 read tools `process_backed`、awaiting activation/cancel 语义 |
| `tests/README.md` | ✅ 已同步 | 记录了 execution capability、Doc/Fins/Web process-backed 和 late-result 测试覆盖 |
| `docs/host/design.md` | 无需更新 | S2E artifact 不改变设计意图 |
| `docs/engine/design.md` | 无需更新 | Engine 边界未变 |
| 根 `README.md` | 无需更新 | 最终用户手册，不触发 |

## Verdict

**PASS**。

S2A1-S2D 合并后，typed execution contract 在 contract 声明、Host ToolRuntime factory wiring、Doc/Fins/Web process-backed 迁移、late-result accept barrier、WAITING 工具隔离和 digest 稳定性上形成单一语义闭环。4 个低严重度 findings 均为 test coverage 或 docstring 精度问题，不阻塞当前 production cancel closeout。Residual risks 全部分类且有 owner。

READY_FOR_CONTROLLER
