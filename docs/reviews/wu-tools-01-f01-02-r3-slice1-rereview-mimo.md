# WU-TOOLS-01-F01-02-R3 Slice 1 Re-Review

## Scope

- Mode: current changes
- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: Slice 1, Doc Native Tools
- Gate: re-review after code review fix
- Base: `main`
- Fix artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice1-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-02-r3-slice1-code-review-controller-adjudication.md`
- Re-review scope: accepted findings S1-CR-01 through S1-CR-04 only; no re-opening of rejected/deferred findings unless fix introduces direct new evidence
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-slice1-rereview-mimo.md`

## Findings

未发现实质性问题。

### 逐项复核

#### S1-CR-01: Path Validation Leaks Existence Outside Allowed Roots — ✅ 完全修复

- **修复验证**: `_project_doc_paths` (`doc_tools.py:826-838`) 中 `_is_relative_to` 检查位于 `candidate.exists()` 之前。白名单外路径无论是否存在均返回 `permission_denied`。
- **回归测试**: `test_disallowed_nonexistent_path_returns_permission_denied` 创建白名单外不存在的 `blocked/missing.md`，断言 `permission_denied` 而非 `file_not_found`。
- **未引入新问题**: 检查顺序正确，错误码语义准确。

#### S1-CR-02: Provider Lock Serialization Lacks Direct Test — ✅ 完全修复

- **修复验证**: `build_doc_tool_definitions` (`doc_tools.py:293`) 创建单一 `asyncio.Lock()` 实例，五个 callable 共享同一把锁。`_invoke_doc_business` (`doc_tools.py:729`) 通过 `async with provider_lock` 序列化同步业务体。
- **回归测试**: `test_same_provider_different_doc_callables_are_serialized` 使用 `list_files` 和 `read_file` 两个不同 callable 并发执行。通过 monkeypatch `asyncio.to_thread`、`asyncio.Event` 确定性同步，验证第二个 callable 在第一个进入 `to_thread` 后才尝试进入，且 `observed_overlap` 为 `False`。不依赖 sleep。
- **未引入新问题**: 测试断言 `business_entries == ["list_files", "read_file"]` 确认两个业务体均执行但不重叠。

#### S1-CR-03: Line Scan Search Loop Lacks Cancellation Checkpoint — ✅ 完全修复

- **修复验证**: `_search_via_line_scan` (`doc_tools.py:1470`) 签名 `cancellation_token: CancellationToken`（非 Optional）。行扫描循环内 (`doc_tools.py:1504`) 调用 `_raise_if_doc_cancelled_at_interval(cancellation_token, line_num)`，按 `_DOC_LOOP_CANCELLATION_CHECK_INTERVAL`（默认 1000）间隔检查取消。
- **取消信号类型**: `_raise_if_doc_cancelled_at_interval` (`doc_tools.py:1524-1542`) 在检查点命中且 token 已取消时抛出 `_DocCancelledError`，由 `_invoke_doc_business` (`doc_tools.py:734`) 捕获并投影为 `ToolCancelledOutcome(reason="host_cancelled")`。
- **回归测试**:
  - `test_search_via_line_scan_observes_loop_cancellation`: monkeypatch interval=1，验证行扫描循环内抛出 `_DocCancelledError`。
  - `test_search_files_line_scan_cancellation_returns_host_cancelled`: 端到端验证 `search_files` callable 在 line scan 取消时返回 `ToolCancelledOutcome` 且 `reason == TOOL_CANCELLED_REASON_HOST_CANCELLED`。
- **未引入新问题**: token 从 `context.cancellation_token`（非 Optional `CancellationToken`）传入，类型收紧正确。

#### S1-CR-04: Markdown Section / Line Count Helpers Have Cancellation Gaps — ✅ 完全修复

- **修复验证**:
  - `_extract_markdown_sections` (`doc_tools.py:1315-1374`) 接受 `cancellation_token: CancellationToken`，在标题行循环 (`doc_tools.py:1335`) 和 preview 生成循环 (`doc_tools.py:1368`) 中均调用 `_raise_if_doc_cancelled_at_interval`。
  - `_count_file_lines` (`doc_tools.py:1266-1288`) 接受 `cancellation_token: CancellationToken`，在行枚举循环 (`doc_tools.py:1284`) 中调用 `_raise_if_doc_cancelled_at_interval`，循环结束后追加一次 `_raise_if_doc_cancelled`。
  - `_fallback_single_section` (`doc_tools.py:1377-1417`) 接受 `cancellation_token` 并传递给 `_count_file_lines`。
  - `_sections_via_processor` (`doc_tools.py:1206-1263`) 将 `cancellation_token` 传递给 `_count_file_lines`。
- **回归测试**:
  - `test_markdown_section_extraction_observes_cooperative_cancellation`: monkeypatch interval=1，预取消 token 下验证 `_extract_markdown_sections` 抛出 `_DocCancelledError`。
  - `test_count_file_lines_observes_cooperative_cancellation`: monkeypatch interval=1，预取消 token 下验证 `_count_file_lines` 抛出 `_DocCancelledError`。
- **未引入新问题**: 仅添加协作式检查点，未引入 timeout policy、物理取消或 Host/Engine 变更。

### 新引入代码额外检查

- **`_invoke_doc_business` 取消路径**: 取消检查在锁获取前 (`doc_tools.py:727`)、锁获取后 (`doc_tools.py:730`) 和业务执行中（通过 `_DocCancelledError` 捕获 `doc_tools.py:734`) 三处覆盖，无遗漏。
- **类型安全**: `cancellation_token` 从 `context.cancellation_token` 获取，`BatchToolExecutionContext` 签名保证非 Optional；`_search_via_line_scan` 签名收紧为 `CancellationToken` 正确。
- **编码约束遵守**: 新增函数均提供完整中文 docstring；无 `Any`、`object`、无类型参数；无魔法数字（`_DOC_LOOP_CANCELLATION_CHECK_INTERVAL` 为 `Final[int]`）。
- **架构边界**: `doc_tools.py` 不依赖 `_legacy_adapter`；`doc_provider.py` 不再 import 任何 legacy 模块。
- **`asyncio.Lock` 正确性**: lock 在 `build_doc_tool_definitions` 中创建一次，五个 callable 闭包共享同一实例；`async with provider_lock` 正确序列化同步业务体。

### 测试验证

- `pytest tests/tools/test_doc_tools_provider.py`: 28 passed ✅
- `pytest tests/tools/test_combined_tools_acceptance.py -k doc`: 1 selected, 7 deselected ✅
- `pyright dayu/tools/doc_tools.py dayu/tools/doc_provider.py`: 0 errors, 0 warnings ✅
- `git diff --check`: passed ✅

## Open Questions

- 无。

## Residual Risk

- Doc helper 取消仍为协作式设计；已运行的文件读取不会被物理中断。此为 Slice 1 设计范围内的已知行为。
- `_DOC_LOOP_CANCELLATION_CHECK_INTERVAL` 默认值 1000 意味着最多 1000 行才检查一次取消；对极大文件有微小延迟。生产影响低，且由测试覆盖。

## Conclusion

**pass**

S1-CR-01 至 S1-CR-04 全部完全修复，回归测试覆盖充分，未引入新 correctness / type / boundary / test 问题。
