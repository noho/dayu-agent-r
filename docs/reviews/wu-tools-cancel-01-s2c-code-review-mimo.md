# Code Review

## Scope

- Mode: current changes (workspace diff only)
- Branch: phase/wu-tools-cancel-01
- Base: workspace unstaged changes against HEAD
- Output file: docs/reviews/wu-tools-cancel-01-s2c-code-review-mimo.md
- Included scope:
  - `dayu/fins/tools/fins_tools.py`
  - `dayu/fins/tools/provider.py`
  - `tests/fins/test_fins_storage_provider.py`
  - `dayu/fins/README.md`
  - `tests/README.md`
  - `docs/reviews/wu-tools-cancel-01-s2c-implementation-codex.md`
- Excluded scope: Host / Engine / durable / runtime contract, Web tools, Fins WAITING tools
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐项证据如下。

### 1. 九个 Fins read definitions 全部声明 ProcessBackedToolExecutionCapability

`fins_tools.py` 九个 `_build_*_definition` 函数均：
- 接收 `process_target_factory: _FinsReadProcessTargetFactory` 参数
- 向 `@tool` 传入 `execution=ProcessBackedToolExecutionCapability(target_factory=process_target_factory)`

`provider.py:49-53` 正确传递 `workspace_root` 给 `build_fins_read_tool_definitions`。

`test_fins_read_definitions_declare_process_backed_execution` 断言九个 definition 的 `execution` 均为 `ProcessBackedToolExecutionCapability` 实例。

Host `_declared_capsule_for_execution` 读取 `ProcessBackedToolExecutionCapability.target_factory`，调用 `build_process_target(call, context)` 构造 capsule，不按工具名特判。生产默认路径正确进入 process-backed。

### 2. Process target/factory 只保存可序列化标量

`_FinsReadProcessTargetFactory`（`fins_tools.py:296-342`）：`frozen=True, slots=True`，字段为 `workspace_root_locator: str` 和 `limits: FinsToolLimits`。

`_FinsReadProcessTarget`（`fins_tools.py:219-293`）：`frozen=True, slots=True`，字段为 `workspace_root_locator: str`、`tool_name: str`、`arguments: dict[str, JsonValue]`、`limits: FinsToolLimits`、`timeout_seconds: float | None`。

`FinsToolLimits`（`fins_limits.py`）：`frozen=True`，字段全为 `int`。

`test_fins_read_process_target_factory_pickle_round_trip` 验证 factory 和 target pickle round-trip 成功，并断言序列化 payload 不含 `FinsReadRuntime`、`Repository`、`provider_lock`、`CancellationToken`、`session-fins`、`run-fins` 等片段。不捕获运行时对象。

### 3. 子进程通过 DefaultFinsRuntime.create 和 storage 仓储路线重建

`_FinsReadProcessTarget.__call__`（`fins_tools.py:249-293`）：
```python
runtime = DefaultFinsRuntime.create(workspace_root=Path(self.workspace_root_locator))
read_runtime = runtime.get_read_runtime(processor_cache_max_entries=self.limits.processor_cache_max_entries)
```
然后通过 `_execute_fins_read_business_value` → `_route_fins_read_business` 路由到 `read_runtime` 的九个方法。所有 Fins 文件访问仍通过 `dayu.fins.storage` 仓储边界。未绕过 storage。

### 4. Schema、成功 payload、failure code/message/hint、truncate spec、LLM-facing 文本

- 参数 schema：九个 `_*_parameters()` 函数未变。
- 成功 payload：`_route_fins_read_business` 直接返回 `read_runtime.*` 的原始 JSON 值，cast 为 `JsonValue`。
- 失败：`_FinsReadBusinessFailure` 保持 `error`/`message`/`hint` 三字段。process envelope 把 hint 折入 message（`_process_failure_message`），因为 Host process envelope 无独立 hint 字段——与 Doc process-backed 模式一致。
- truncate spec：未变。
- LLM-facing 文本：工具 description、参数 description、failure message/hint 均保持自解释。无 regressions。

### 5. Direct callable fallback 仅为测试/非生产 fallback

`_invoke_fins_read_business` docstring（`fins_tools.py:975-989`）明确：
> 生产默认路径不再经过本函数；九个 Fins read ToolDefinition.execution 均声明为 process-backed，由 Host ToolRuntime 在父进程治理取消与超时。本函数只保留给直接调用 ToolDefinition.callable 的测试和非生产 fallback。

`_FinsProcessCancellationToken`（`fins_tools.py:132-183`）在子进程中使用，`is_cancelled()` 始终返回 `False`。process target 不观察 Host cancellation token；真实取消由父进程 process capsule 独占治理（terminate / kill）。direct callable fallback 使用 Host 注入的真 token。

### 6. 测试覆盖

新增测试：
- `test_fins_read_definitions_declare_process_backed_execution`：九个 definitions 声明 process-backed。✅
- `test_fins_read_process_target_factory_pickle_round_trip`：factory/target pickle round-trip 且不含运行时对象。✅
- `test_fins_read_process_target_fast_path_uses_default_runtime`：fast path（list_documents）。✅
- `test_fins_read_process_target_processor_and_table_paths`：processor path（search_document）+ table path（list_tables）。✅
- `test_fins_read_process_target_failure_envelope`：参数失败返回 failed JSON 信封，不含 host_cancelled/awaiting/timeout。✅
- `test_fins_read_process_target_runs_in_spawned_child`：真实 `ProcessBackedToolExecutionCapsule` spawned child。✅
- `test_fins_read_process_backed_cancel_drops_late_result`：ToolRuntime 取消后不接受迟到结果。✅

existing direct callable cancellation tests 保留为 fallback coverage。

minor gap：XBRL query path 未通过 process target 覆盖。`_route_fins_read_business` 中 `query_xbrl_facts` 与其它工具走相同 cast 路径，风险低。

### 7. 不影响 WAITING tools / Host/Engine/durable/runtime contract

diff 仅触及 `dayu/fins/tools/` 和测试。download_tools.py、preprocess_tools.py、upload_tools.py 各仅增加 `FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS` guard（已存在于 main），不影响 WAITING 行为。未修改 Host/Engine/durable/runtime JsonValue contract。

### 8. AGENTS.md 硬约束

- 类型：所有函数签名有完整类型注解。无 `Any`、`object`、无类型参数。
- docstring：所有新增/修改函数有完整中文 docstring，含 Args/Returns/Raises。
- 无无根据 `getattr`/`hasattr`。
- README 触发：`dayu/fins/` 修改 → `dayu/fins/README.md` 已更新；`tests/` 修改 → `tests/README.md` 已更新。

## Open Questions

无。

## Residual Risk

- XBRL query path 通过 process target 的测试覆盖缺失。当前 `_route_fins_read_business` 中 `query_xbrl_facts` 与其它工具走相同 cast 路径，且已有 direct callable cancellation 测试覆盖。风险低。
- `FinsToolLimits` 未使用 `slots=True`（在 S2C 之前已存在），不影响 pickle 序列化或正确性。

## Conclusion

**PASS**

S2C 实现完整、正确、可验证。九个 Fins read tools 全部声明 process-backed execution；process target 只保存可序列化标量；子进程通过 `DefaultFinsRuntime.create` 和 storage 仓储路线重建；schema/payload/failure/LLM-facing 文本无 regressions；direct callable fallback 明确限定为非生产路径；测试覆盖真实 spawned child、fast path、processor path、table path、failure envelope 和 cancel-drops-late-result；不影响 WAITING tools 和 Host/Engine/durable/runtime contract；符合 AGENTS.md 硬约束。
