# WU-TOOLS-01-F01-02-R3 Slice 1 Re-Review (DS)

## Scope

- Mode: current changes re-review
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: controller adjudication of S1-CR-01 through S1-CR-04
- Input artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r3-slice1-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice1-fix-codex.md`
- Reviewed files:
  - `dayu/tools/doc_provider.py` (full rewrite — legacy adapter retired)
  - `dayu/tools/doc_tools.py` (full rewrite — native ToolDefinition / ToolCallable migration)
  - `tests/tools/test_doc_tools_provider.py` (test rewrite + new fix coverage)
  - `docs/host/issues-implementation-control.md` (status-only update)
- Excluded scope:
  - S1-CR-05 (empty allowed_roots defensive branch): rejected by controller, no new evidence from fix
  - S1-CR-06 (processor timeout): deferred, no new evidence from fix
  - S1-CR-07 (misc signature/encoding cleanups): deferred, no new evidence from fix
  - Web, Fins, Host, Engine, Service, ToolRuntime, legacy adapter deletion scope

## Review Method

1. Read controller adjudication to confirm exact fix requirements per accepted finding.
2. Read fix-codex report to understand claimed changes.
3. Read full `git diff` (unstaged) covering every changed line.
4. Read current `doc_provider.py`, `doc_tools.py`, and `test_doc_tools_provider.py` in whole.
5. For each finding, traced the critical code path entry → branch → outcome, and verified the corresponding test's trigger, assertion, and determinism.
6. Performed adversarial pass: checked for new correctness, type, boundary, and test gaps.

## Findings

### S1-CR-01 — Path Validation: Allowed-Root Check Before Exists ✅ Fixed

**入口/函数**: `_project_doc_paths` (`dayu/tools/doc_tools.py:789-846`)

逐行走读确认：
- Line 826: `Path(value).expanduser().resolve(strict=False)` — 解析候选路径。
- Lines 827-832: **先执行 `_is_relative_to` 判断**，白名单外直接返回 `permission_denied`。
- Lines 833-837: **仅当路径在白名单内时才调用 `candidate.exists()`**，不存在返回 `file_not_found`。

旧代码顺序为 `exists()` → `_is_relative_to`（见原始 DS/MiMo review），修复后顺序已颠倒。

**直接证据**: `doc_tools.py:827` 的 `if not any(_is_relative_to(candidate, root) for root in allowed_roots)` 在 `doc_tools.py:833` 的 `if not candidate.exists()` 之前执行。

**测试覆盖**: `test_disallowed_nonexistent_path_returns_permission_denied` (`test_doc_tools_provider.py:278-296`)
- 创建 `allowed/` 和 `blocked/` 两个目录，引用 `blocked/missing.md`（不存在）。
- 断言 `outcome.result.error == "permission_denied"`，非 `"file_not_found"`。
- 路径白名单外且不存在 → `permission_denied`。测试精确命中修复点。

**结论**: 完全修复，无 residual。

---

### S1-CR-02 — Provider Lock Serialization Test ✅ Fixed

**入口/函数**: `_invoke_doc_business` (`dayu/tools/doc_tools.py:702-786`)

逐行走读确认：
- Line 729: `async with provider_lock:` — 同一 provider 的五个 callable 共享同一个 `asyncio.Lock`。
- Line 733: `await asyncio.to_thread(business_call, token)` 在持有锁的 async context 中执行，锁在 `to_thread` await 期间持续持有，阻塞其他 callable 进入。
- 五个 builder 均传入同一个 `provider_lock` 实例（`doc_tools.py:293`）。

**直接证据**: `doc_tools.py:293` 的 `provider_lock = asyncio.Lock()` 传给所有五个 `_build_*_definition` 调用；`doc_tools.py:729` 的 `async with provider_lock:` 确保串行化。

**测试覆盖**: `test_same_provider_different_doc_callables_are_serialized` (`test_doc_tools_provider.py:349-472`)
- 选 `list_files` 和 `read_file` 两个不同 Doc callable，同一 provider。
- 替换 `asyncio.to_thread` 为 `fake_to_thread`，在首次进入后通过 `asyncio.Event` 悬挂第一个 callable。
- Line 456: `await asyncio.sleep(0)` 让出事件循环。
- Line 457: `assert to_thread_entries == ["enter"]` — 证明第二个 callable 尚未进入同步体。
- Line 470: `assert observed_overlap is False` — 证明从未出现重叠。
- 无 sleep-based 时序断言；使用 `asyncio.Event` 作为确定性同步原语。

**结论**: 完全修复，测试设计优秀。

---

### S1-CR-03 — Line Scan Cancellation Checkpoint ✅ Fixed

**入口/函数**: `_search_via_line_scan` (`dayu/tools/doc_tools.py:1972-2028`)

逐行走读确认：
- 签名 `cancellation_token: CancellationToken` — 非 optional。
- Line 2010-2011: 行循环内 `_raise_if_doc_cancelled_at_interval(cancellation_token, line_num)` — 每 1000 行检查一次。
- `_raise_if_doc_cancelled_at_interval` (`doc_tools.py:2031-2049`)：`item_index % _DOC_LOOP_CANCELLATION_CHECK_INTERVAL == 0` 时调用 `_raise_if_doc_cancelled`。
- 取消信号通过 `_DocCancelledError` → `_invoke_doc_business` except 分支 → `_cancelled_outcome` → `host_cancelled_outcome` 投影为 `ToolCancelledOutcome(reason="host_cancelled")`。

**直接证据**: `doc_tools.py:2010-2011` 的 checkpoint；`doc_tools.py:734` 的 `except _DocCancelledError` catch；`doc_tools.py:1659-1665` 的 `host_cancelled_outcome` 投影。

**测试覆盖**:
- `test_search_via_line_scan_observes_loop_cancellation` (`test_doc_tools_provider.py:656-682`)：直接验证 helper 抛出 `_DocCancelledError`。通过 monkeypatch `_DOC_LOOP_CANCELLATION_CHECK_INTERVAL = 1` 确保检查立即触发。
- `test_search_files_line_scan_cancellation_returns_host_cancelled` (`test_doc_tools_provider.py:685-731`)：验证公共 callable 投影为 `ToolCancelledOutcome`。
- `test_search_files_cancelled_during_iteration_stops_before_later_scan` (`test_doc_tools_provider.py:593-653`)：验证文件级迭代取消后不再扫描后续文件。

**结论**: 完全修复，helper + 集成覆盖完整。

---

### S1-CR-04 — Markdown Section / Line Count Cancellation ✅ Fixed

**入口/函数**: `_extract_markdown_sections` (`doc_tools.py:1315-1374`), `_count_file_lines` (`doc_tools.py:1266-1288`)

逐行走读确认：

`_extract_markdown_sections`:
- Line 1334-1335: 标题提取循环内 `_raise_if_doc_cancelled_at_interval(cancellation_token, line_num)`。
- Line 1367-1368: preview 生成循环内 `_raise_if_doc_cancelled_at_interval(cancellation_token, section_index)`。
- 签名 `cancellation_token: CancellationToken` — 非 optional。

`_count_file_lines`:
- Lines 1283-1284: `for total_lines, _line in enumerate(file, start=1)` 循环内 `_raise_if_doc_cancelled_at_interval(cancellation_token, total_lines)`。
- Line 1285: 循环后 `_raise_if_doc_cancelled(cancellation_token)`。
- 签名 `cancellation_token: CancellationToken` — 非 optional。

传递链路验证：
- `_sections_via_processor` → `_count_file_lines(path, cancellation_token)` (line 1229) ✅
- `_fallback_single_section` → `_count_file_lines(path, cancellation_token)` (line 1399) ✅
- `_get_file_sections_business` → `_extract_markdown_sections(lines, cancellation_token)` (line 968) ✅
- `_get_file_sections_business` → `_fallback_single_section(..., cancellation_token)` (lines 963, 980) ✅

**直接证据**: `doc_tools.py:1335/1368/1284` 的 checkpoint 调用；各调用点 cancellation_token 传递一致。

**测试覆盖**:
- `test_markdown_section_extraction_observes_cooperative_cancellation` (`test_doc_tools_provider.py:796-806`)：直接验证 `_DocCancelledError` 抛出。使用 monkeypatch `_DOC_LOOP_CANCELLATION_CHECK_INTERVAL = 1`。
- `test_count_file_lines_observes_cooperative_cancellation` (`test_doc_tools_provider.py:809-822`)：直接验证 `_DocCancelledError` 抛出。同样 monkeypatch interval 为 1。

**结论**: 完全修复，无修改范围外的 Host/Engine 行为变更。

---

## Adversarial Pass — New Issue Check

对全部改动执行了 adversarial 检查，重点扫描 correctness、type、boundary、test 四个维度：

1. **`_raise_if_doc_cancelled` 仍接受 `CancellationToken | None`** — 这是有意保留的兼容签名（`doc_tools.py:2094`）。新代码路径（`_raise_if_doc_cancelled_at_interval`、所有 `_*_business` 函数）全部传非 optional token。预取消检查 `token.is_cancelled()` 在 `_invoke_doc_business:1209` 使用 `context.cancellation_token` 直接调用，无 None 风险（Host 始终提供 token）。**非问题**。

2. **`_is_relative_to` 实现正确性** — 使用 `candidate.parents` 遍历而非 `Path.is_relative_to()`（Python 3.9+ 可用）。实现等价且正确：`candidate == root` 处理精确匹配，`root in candidate.parents` 处理子树判断。**无问题**。

3. **`_fallback_single_section` 中 `del file_path`** — `file_path` 参数声明后立即 `del`（`doc_tools.py:1398`），未在函数体内使用。这是调用兼容性保留，非新引入 —— 旧代码中该参数也未使用（仅用于 `path` 的备用）。**非新问题**。

4. **`_sections_via_processor` 中 `processor.list_sections()` 无内部取消检查** — 处理器调用本身不可中断。这是已知设计限制（cooperative cancellation only），已在 fix-codex residual risk 中记录。**非新问题**。

5. **`_count_file_lines` 异常吞没** — `UnicodeDecodeError` 和 `OSError` 被 catch 并返回 0（`doc_tools.py:1287-1288`）。此行为与旧代码一致，对调用方（`_sections_via_processor`、`_fallback_single_section`）无副作用。**非新问题**。

6. **`_search_via_line_scan` 全文读取前无取消检查** — 文件读取 `file.read()` 不可中断。这是已知的 cooperative cancellation 限制。**非新问题**。

7. **双重 `expanduser().resolve()` in allowed_roots** — `_parse_allowed_paths:159` 和 `build_doc_tool_definitions:292` 各解析一次。双重解析无害但冗余。**非 correctness 问题，low maintainability 但非本 slice scope**。

8. **所有已移除的 `_DocFileAccessError` → `permission_denied` 投影一致** — `_invoke_doc_business:745-753` 将 `_DocFileAccessError` 统一映射为 `permission_denied`。检查了所有 raise 点（`_list_files_business`、`_search_files_business`、`_read_file_business`）：全部通过 `_DocFileAccessError` 抛出，异常类型一致。**无问题**。

9. **类型安全** — 所有新增/修改函数签名使用具体类型，无 `Any`、`object`、无类型参数。pyright 0 errors。**无问题**。

10. **旧测试迁移完整性** — 原测试中 `test_file_path_params_metadata_is_collected_and_used`、`test_collector_allowed_paths_are_not_trusted`、`test_doc_declarations_request_execution_context_injection`、`_collected_by_name`、`_by_name` 被移除。这些测试依赖于已删除的 `LegacyToolDeclarationCollector` / `adapt_collected_tool` / `register_doc_tools` API。新增测试覆盖了等价语义（`test_doc_provider_discovers_native_async_callables`、`test_disallowed_path_returns_failed_outcome`、`test_native_doc_path_projection_accepts_allowed_absolute_paths`）。**无覆盖回退**。

## Open Questions

无。

## Residual Risk

- Doc helper 取消仍为 cooperative-only：已开始的 `file.read()`、`processor.list_sections()`、`processor.search()` 调用不可物理中断。
- `_search_via_line_scan` 全文 `file.read()` 在大文件上可能阻塞较长时间才到达第一个行循环 checkpoint。
- Web / Fins native migration, legacy adapter 物理删除, 长运行 processor timeout 策略不在本 Slice 1 范围内。

## Conclusion

**pass**

四个 accepted findings (S1-CR-01 ~ S1-CR-04) 全部完全修复，有直接代码证据和精确测试覆盖支撑。Adversarial pass 未发现新引入的 correctness、type、boundary 或 test 问题。
