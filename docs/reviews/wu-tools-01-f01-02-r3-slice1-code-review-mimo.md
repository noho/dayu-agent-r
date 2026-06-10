# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: `main` (unstaged changes)
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-slice1-code-review-mimo.md`
- Included scope: `dayu/tools/doc_provider.py`, `dayu/tools/doc_tools.py`, `tests/tools/test_doc_tools_provider.py`, `docs/host/issues-implementation-control.md`
- Excluded scope: Web/Fins tools, legacy adapter deletion (Slice 2/3/4), Host/Engine/Service changes
- Parallel review coverage: 无

## Findings

### 001-未修复-中-路径校验顺序导致 allowed_roots 外文件存在性泄漏

- **入口/函数**: `_project_doc_paths`
- **文件(行号)**: `dayu/tools/doc_tools.py:825-832`
- **输入场景**: LLM 传入一个 `allowed_roots` 之外但文件系统上不存在的路径
- **实际分支**: line 826 `candidate.exists()` 先执行，返回 `file_not_found`
- **预期行为**: 按 fail-closed 原则，应先检查路径是否在 `allowed_roots` 内，不在则返回 `permission_denied`，不向调用方泄漏该路径是否存在
- **实际行为**: `exists()` 在 `allowed_roots` 检查之前执行，导致 `allowed_roots` 外的路径能区分"不存在"和"存在但无权限"
- **直接证据**: `dayu/tools/doc_tools.py:826` — `if not candidate.exists():` 在 `dayu/tools/doc_tools.py:832` — `if not any(_is_relative_to(candidate, root) for root in allowed_roots):` 之前
- **影响**: 信息泄漏；调用方可通过错误码差异探测 `allowed_roots` 外的文件系统结构。对本地 doc tools 为低安全风险，但违反 fail-closed 原则
- **建议改法和验证点**: 交换 line 826-831 和 line 832-837 的顺序，先检查 `allowed_roots` 包含性，再检查 `exists()`。补充测试：`allowed_roots` 外不存在的路径应返回 `permission_denied` 而非 `file_not_found`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-未修复-中-缺少 provider lock 并发序列化测试

- **入口/函数**: `tests/tools/test_doc_tools_provider.py`
- **文件(行号)**: `tests/tools/test_doc_tools_provider.py`（缺失测试）
- **输入场景**: 两个不同 Doc tool callable 并发调用（如 `read_file` 和 `list_files`）
- **实际分支**: 当前所有测试使用 `asyncio.run()` 串行执行，无并发覆盖
- **预期行为**: plan Slice 1 Tests 明确要求 "concurrency 等价覆盖 legacy `SERIAL_PER_PROVIDER` 行为：同一 provider 的两个不同 Doc tool 并发调用时，不得并发进入同步业务体"
- **实际行为**: 无并发测试；`asyncio.Lock` 的序列化行为未被验证
- **直接证据**: `tests/tools/test_doc_tools_provider.py` 全文无 `asyncio.gather` 模式
- **影响**: 无法验证 provider lock 确实阻止并发进入业务体；若未来 lock 逻辑被误改，无回归测试捕获
- **建议改法和验证点**: 新增测试：用 `asyncio.gather` 同时调用两个不同 Doc tool callable，用 spy 记录业务函数进入/退出时间，断言无重叠。验证 `async with provider_lock:` 确实序列化
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 003-未修复-低-`_search_via_line_scan` 行扫描循环缺少取消检查

- **入口/函数**: `_search_via_line_scan`
- **文件(行号)**: `dayu/tools/doc_tools.py:1489-1505`
- **输入场景**: 大文件（数千行）中包含大量匹配行，且 Host 在扫描过程中发出取消请求
- **实际分支**: line 1477 在 `open` 前检查取消，但 line 1489-1505 的逐行扫描循环内无取消检查
- **预期行为**: 协作式取消应在可预见的长循环中提供中断点
- **实际行为**: 循环在文件所有行扫描完毕前不会响应取消信号
- **直接证据**: `dayu/tools/doc_tools.py:1489` — `for line_num, line in enumerate(lines, start=1):` 循环体内无 `_raise_if_doc_cancelled` 调用
- **影响**: 取消响应延迟；对大文件场景，线程在取消请求后仍持续运行直到循环结束。由于 `asyncio.to_thread` 运行在独立线程中，不会阻塞事件循环，但会延迟 `ToolCancelledOutcome` 的返回
- **建议改法和验证点**: 在循环内每 N 行（如 100 行）添加 `_raise_if_doc_cancelled(cancellation_token)` 调用。补充测试覆盖大文件扫描中途取消
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 004-未修复-低-`_extract_markdown_sections` 和 `_count_file_lines` 缺少取消检查

- **入口/函数**: `_extract_markdown_sections`, `_count_file_lines`
- **文件(行号)**: `dayu/tools/doc_tools.py:1309-1362`, `dayu/tools/doc_tools.py:1265-1282`
- **输入场景**: 大型 Markdown 文件的章节提取或行数统计
- **实际分支**: 两个函数的循环内均无取消检查
- **预期行为**: 可预见的长循环应提供协作式取消中断点
- **实际行为**: `_extract_markdown_sections` 遍历所有行无取消检查；`_count_file_lines` 读取整个文件无取消检查
- **直接证据**: `dayu/tools/doc_tools.py:1324` — `for line_num, line in enumerate(lines, start=1):` 无取消检查；`dayu/tools/doc_tools.py:1280` — `sum(1 for _ in file)` 无取消检查
- **影响**: 与 003 相同；取消响应延迟但不阻塞事件循环
- **建议改法和验证点**: 在 `_extract_markdown_sections` 循环内添加周期性取消检查。`_count_file_lines` 可接受为低优先级，因为它只统计行数不返回内容
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- Web 和 Fins read tools 仍依赖 legacy adapter，按设计属于后续 Slice 2/3 范围
- Legacy adapter 删除推迟到 Slice 4
- Doc 业务 IO 保持协作式取消，不引入物理中断
- 003/004 的取消间隙在实际生产中影响有限：Doc 工具处理的文件通常较小，且 `asyncio.to_thread` 运行在独立线程中不阻塞事件循环
- 002 的并发测试缺失不影响当前正确性（`asyncio.Lock` 是标准库保证），但影响回归防护

## Review Conclusion

**pass-with-findings**

实现正确完成了 Slice 1 的核心目标：

1. **Doc provider 不再依赖 legacy adapter** — `doc_provider.py` 和 `doc_tools.py` 中 `_legacy_adapter` 导入已完全移除
2. **五个 Doc tools 的名称、LLM-facing schema、display、tags、truncate、返回 shape 保持一致** — 测试验证五工具发现、schema 不暴露治理字段、truncate spec 声明正确
3. **参数校验和路径 allowed_roots must_exist fail-closed 在业务前完成** — `_project_doc_paths` 在 `_invoke_doc_business` 之前执行，路径校验失败时不进入业务函数（monkeypatch 测试验证）
4. **list/search 返回路径可链到 read tools** — 专用测试覆盖 `list_files` -> `read_file`/`get_file_sections` 和 `search_files` -> `read_file`/`read_file_section` 的全链路
5. **Host cancellation token 投影为 `ToolCancelledOutcome(host_cancelled)`** — 预取消（5 个工具参数化）、搜索中取消、编码 fallback 中取消均断言 `ToolCancelledOutcome` 且 reason 为 `host_cancelled`
6. **同一 provider 五个 callable 共享 lock** — `build_doc_tool_definitions` 内创建一把 `asyncio.Lock()`，五个 callable 闭包共享
7. **异常映射不吞掉取消** — `_DocCancelledError` 在 `_invoke_doc_business` 中先于 `Exception` 被捕获
8. **测试和 README 判断符合 AGENTS.md** — 测试覆盖主要行为路径，`tests/README.md` 检查后无需更新

三个中/低严重度 findings 均不影响当前正确性，但应在未来迭代中修复以提高防御深度。
