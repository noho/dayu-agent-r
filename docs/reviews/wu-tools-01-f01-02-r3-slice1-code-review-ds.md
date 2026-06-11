# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: committed HEAD (Slice 0 already on branch)
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-slice1-code-review-ds.md`
- Included scope: unstaged changes to `dayu/tools/doc_provider.py`, `dayu/tools/doc_tools.py`, `tests/tools/test_doc_tools_provider.py`, `docs/host/issues-implementation-control.md`
- Excluded scope: committed Slice 0 files (`dayu/runtime/tool_call_projection.py`, `tests/runtime/test_tool_call_projection.py`), Web, Fins, legacy adapter, Host, Engine, Service, ToolRuntime — not modified in this slice
- Parallel review coverage: 无

## Findings

### 01-未修复-中-`_search_via_line_scan` 行扫描循环内无取消检查点

- **入口/函数**: `_search_via_line_scan` 被 `_search_files_business` 在遍历到无 processor 的文件时调用
- **文件(行号)**: `dayu/tools/doc_tools.py:1489-1506`
- **输入场景**: `search_files` 被调用，目标目录下存在一个或多个无法创建 processor 的大文本文件，且 Host 在扫描过程中请求取消
- **实际分支**: 代码先调用 `_raise_if_doc_cancelled(cancellation_token)` (`doc_tools.py:1477`)，成功（token 尚未取消），然后 `open(file_path, ...).read()` 读取整个文件内容 (`doc_tools.py:1478`)，之后进入 `for line_num, line in enumerate(lines, start=1):` 循环 (`doc_tools.py:1489`)，此循环内无任何 `_raise_if_doc_cancelled` 调用
- **预期行为**: 按 plan Slice 1 cancellation semantics 要求"搜索循环继续保留 checkpoint"，且在 `_search_via_line_scan` 的循环中也应在发现取消后尽快返回 `_DocCancelledError`
- **实际行为**: 循环遍历所有行直到找齐 `remaining` 个匹配或文件结束，期间不检查取消令牌。对于超大文件，这会延迟取消响应
- **直接证据**: `doc_tools.py:1489` 的 `for` 循环体 (`doc_tools.py:1489-1505`) 中，唯一可能提前退出的条件是 `len(matches) >= remaining` (`doc_tools.py:1504`)，没有任何 `_raise_if_doc_cancelled` 调用。对比同文件的 `_search_files_business` 每文件迭代都有 checkpoint (`doc_tools.py:1017`)，以及 `_list_files_business` 每文件迭代都有 checkpoint (`doc_tools.py:901`)
- **影响**: 对超大纯文本文件的 `search_files` 操作，Host 取消信号可能被延迟至多秒级才响应；不导致错误结果，但违反 plan 中"搜索循环保留 checkpoint"要求
- **建议改法和验证点**: 在 `doc_tools.py:1489` 的 `for` 循环内，每处理 N 行或每匹配到一个结果后调用 `_raise_if_doc_cancelled(cancellation_token)`；建议 N 取 1000（与 `_search_files_business` 中每文件 checkpoint 的分辨率相当）。补测试：mock 一个包含数万行文本的大文件 + 搜索关键词匹配每行，在 fake `_search_via_line_scan` 内通过 monkeypatch 验证取消后循环提前退出
- **修复风险（低）**: `_raise_if_doc_cancelled` 已是纯函数，无副作用；在循环内增加 checkpoint 不影响正确路径行为
- **严重程度（中）**: 实际影响仅限无 processor 的大文件场景且外部取消时机正好落入行扫描循环内；但违反 plan 中明确要求的搜索循环 checkpoint 契约，且与模块内其他循环的 checkpoint 密度不一致

### 02-未修复-低-`_search_via_line_scan` 的 `cancellation_token` 参数默认值不一致

- **入口/函数**: `_search_via_line_scan`
- **文件(行号)**: `dayu/tools/doc_tools.py:1457`
- **输入场景**: 不适用（所有现有调用者均传入非空 token），纯维护性问题
- **实际分支**: `cancellation_token: CancellationToken | None = None` — 声明为可选参数
- **预期行为**: 与同模块其他 `_*_business` 函数一致，`cancellation_token` 应为必填且非空（`CancellationToken`，非 `| None`）
- **实际行为**: 参数类型为 `CancellationToken | None` 且默认值为 `None`，但 `_search_files_business` (`doc_tools.py:1039`) 始终传入非空 token
- **直接证据**: `doc_tools.py:1457` 签名与 `doc_tools.py:1034-1040` 调用处对比：调用处传入 `cancellation_token`（非空），但函数签名允许 `None`
- **影响**: 不影响正确性（实际路径从不传 `None`）；增加代码阅读和维护负担，未来修改者可能误以为 line scan 支持无 token 调用
- **建议改法和验证点**: 将 `cancellation_token: CancellationToken | None = None` 改为 `cancellation_token: CancellationToken`，删除默认值；确认唯一调用点 `doc_tools.py:1039` 类型检查通过
- **修复风险（低）**: 仅改签名，调用点无需修改
- **严重程度（低）**: 纯维护性问题，无运行时影响

### 03-未修复-低-`_project_doc_paths` 中 `not allowed_roots` 检查对外部生产路径不可达

- **入口/函数**: `_project_doc_paths`
- **文件(行号)**: `dayu/tools/doc_tools.py:1331-1336`
- **输入场景**: 无（生产路径下 `_project_doc_paths` 仅由 callable 闭包调用，而 callable 仅在 `allowed_roots` 非空时被 `build_doc_tool_definitions` 创建）
- **实际分支**: `if not allowed_roots: return _DocPathFailure(...)` (`doc_tools.py:1331-1336`)
- **预期行为**: 防御性代码可以保留，但若意图是 fail-closed 则应当可测
- **实际行为**: 该分支在 `discover_tools` 的生产路径下无法被触发——`build_doc_tool_definitions` 已在 `doc_tools.py:289-290` 检查 `allowed_roots` 为空并返回空元组，不会创建任何 callable。该分支仅在直接以空 roots 调用 `_project_doc_paths` 时可达（仅可能在测试中）
- **直接证据**: `build_doc_tool_definitions` 在 `doc_tools.py:289-290` 早返回 `()`；`_project_doc_paths` 仅在五个 callable 闭包 (`doc_tools.py:352, 434, 510, 591, 669`) 内被调用，而 callable 只有 `allowed_roots` 非空时才会被构造
- **影响**: 不可达代码增加维护困惑，但不影响正确性；该防御性检查不会产生 false positive
- **建议改法和验证点**: 可保留作为防御性设计（若未来 `_project_doc_paths` 被其他调用者使用）；或改为 `assert allowed_roots, "path projection requires explicit roots"` 以明确表达前置条件。不强制修改
- **修复风险（低）**: 改为 assert 或不改均不影响现有路径
- **严重程度（低）**: 不影响正确性，属于代码清洁度问题

## Open Questions

1. `_fallback_single_section` (`doc_tools.py:1365`) 使用 `del file_path` 来"使用"一个未使用的参数——该参数因与原 OLD 函数签名兼容而保留。未来若确认无外部调用者依赖此签名，可移除 `file_path` 参数。当前不构成缺陷。

2. `_count_file_lines` (`doc_tools.py:1265`) 仅使用 utf-8 编码读取行数；当文件编码为 gbk 等时返回 0。该行为与 OLD 代码一致（预存行为），不影响 `get_file_sections` 主路径（processor 路径不依赖行数统计），仅影响降级路径的 `total_lines` 字段精度。是否应在 `_sections_via_processor` 中补齐多编码行数统计？

3. `_search_via_line_scan` 返回类型 `list[dict[str, JsonValue]]` 与 `_search_via_processor` 返回类型 `list[JsonValue]` 不一致。`_search_files_business` 将两者混入 `matches: list[JsonValue]` 无运行时问题，但增加了类型签名的不一致。是否统一为 `list[JsonValue]`？

## Residual Risk

1. **Concurrency 测试缺失**：当前测试未覆盖"同一 provider 的两个不同 Doc tool 并发调用时不得并发进入同步业务体"的并发等价行为。plan 要求的 `SERIAL_PER_PROVIDER` 等价覆盖（`docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md:470`）仅由代码结构保证（共享 `asyncio.Lock`），没有显式并发测试证明 lock 确实阻止了并发业务执行。建议在后续 slice 或独立测试中补齐。

2. **`search_files` 的 processor 搜索路径中 `processor.search(query)` 无超时保护**：若 processor 搜索挂起（例如 Docling 解析异常大文件），当前无超时机制。这属于预存风险，不是本 slice 引入。Engine 的 `tool_execution_timeout_seconds` 通过 `BatchToolExecutionContext.timeout_seconds` 提供超时，但本 callable 不消费该字段。

3. **`read_file_section` 的 `pre_cancel_arguments` 使用固定 ref `"section_1"`**：测试 `test_doc_tools_cancelled_before_work_return_host_cancelled[read_file_section]` (`test_doc_tools_provider.py:838-861`) 传 `ref="section_1"` 给 `read_file_section`，取消检查在进入业务逻辑前触发（因为 token 在 `_invoke_doc_business` 入口即已取消），因此 ref 是否实际存在不影响测试结果。若未来重构改变了取消检查顺序，此测试可能产生误报。

## Review Conclusion

**pass-with-findings**

理由：
- 五个 Doc tools 的 LLM-facing schema、display name、tags、truncate spec、返回 shape 保持与原一致（逐字段对比验证通过）
- Doc provider 不再依赖 `_legacy_adapter`（`rg` 在生产代码中无命中）
- 路径 allowed_roots / must_exist 在进入业务逻辑前完成 fail-closed（路径跟踪确认）
- list/search 返回路径已投影为绝对路径，可直接链入 read tools（测试 `test_list_and_search_return_paths_can_chain_to_read_tools` 覆盖）
- Host cancellation token 在所有路径正确投影为 `ToolCancelledOutcome(reason=host_cancelled)`（五个工具的预取消测试 + 搜索中取消 + 编码 fallback 中取消均通过）
- 五个 callable 共享同一 `asyncio.Lock`，非法参数/路径在 lock 获取前即返回失败（代码结构验证通过）
- `_DocCancelledError` 在 `except Exception` 之前独立捕获，取消语义不被吞掉（异常捕获顺序验证通过）
- 22 个 Doc provider 测试全部通过，pyright 0 errors 0 warnings
- 未越界修改 Web / Fins / adapter 删除

三条 findings 均为非阻塞：1 条中等（`_search_via_line_scan` 缺少循环内取消检查点），2 条低（参数默认值不一致、防御性死代码）。建议在 Slice 2 实施前修复 Finding 01-未修复-中，其余可择机处理。
