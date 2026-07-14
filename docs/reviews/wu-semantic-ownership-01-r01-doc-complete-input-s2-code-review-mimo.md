# WU-SEMANTIC-OWNERSHIP-01 / R01-S2 Code Review — AgentMiMo

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `547c926e`（`docs: enter R01-S2 directory completeness implementation`）
- Output file: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s2-code-review-mimo.md`
- Included scope:
  - `dayu/tools/doc_tools.py`（79 added, 31 removed）
  - `tests/tools/test_doc_tools_provider.py`（313 added, 37 removed）
  - `tests/README.md`（3 added, 3 removed）
- Excluded scope: control, design, Host, Engine, runtime, contracts, config, Fins, UI, Service, other production/test/README files
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Findings Detail

对 controller validation 指定的六项重点挑战逐一验证：

### 1. 共享 iterator 的稳定 depth-first 顺序、取消/异常/symlink 行为

`_iter_directory_entries`（`doc_tools.py:1432-1469`）实现正确：

- **稳定排序**：每层先 `directory.iterdir()` 收集全部 entry 到 `list[Path]`，再按 `_directory_entry_sort_key` 即 `(name.casefold(), name)` 排序。`casefold` 消除大小写差异后仍以原名保序，符合 Python 3.11 Unicode 排序语义。
- **depth-first 递归**：`yield entry` 后检查 `recursive and not entry.is_symlink() and entry.is_dir()`，对普通子目录递归 `yield from`。顺序确定：先产出当前层全部 entry（已排序），再递归每个子目录。
- **取消观察**：`_raise_if_doc_cancelled(cancellation_token)` 在 `iterdir()` 循环内每个 entry 前、排序后产出每个 entry 前、递归调用前共三处调用。取消快速收口，不伪造 complete。
- **异常透出**：`OSError` 不被捕获，沿既有错误路径透出给 `_DocFileAccessError` 或上层 consumer。
- **symlink**：`entry.is_symlink()` 优先于 `entry.is_dir()` 检查。目录 symlink 作为 entry 产出但不递归其 target（`not entry.is_symlink()` 为 `True` 时才检查 `is_dir()`）。File symlink 的 `is_file()` 在 `_list_files_business` 中由 `file_path.is_file()` 检查，`Path.is_file()` 对 symlink 跟随 target。

**验证**：`test_directory_symlink_entry_is_yielded_without_recursing_target` 断言 `linked-directory` 在 entries 中、`linked-directory/inside.txt` 不在、`target/inside.txt` 在。`test_list_and_search_order_is_stable_across_reversed_creation_order` 断言两棵内容相同但创建顺序相反的目录返回完全相同的 list/search 顺序。

### 2. list 有界 heap 的精确 total/scanned_entries 与稳定前 N

`_list_files_business`（`doc_tools.py:1472-1555`）实现正确：

- **完整遍历**：`for file_path in _iter_directory_entries(...)` 遍历全部 entry，无 counter break。`scanned_entries` 在每个 entry 上递增。
- **精确 total**：`matched_files` 在每个通过 `is_file()` 和 `fnmatch` 的文件上递增。最终 `total = matched_files` 是完整匹配数，不再有 `scan_complete` 条件分支。
- **有界 heap**：`_ListedFileCandidate` 使用 `heapq`，`sort_key` 是 4-tuple `(name.casefold(), name, relative_path.casefold(), relative_path)`。当 `len(files_heap) < actual_limit` 时 push，否则当新 candidate 的 sort_key 小于堆顶时 heapreplace。`__lt__` 使用 `>` 实现反向比较（最大堆），堆顶是当前最大 sort_key。最终 `sorted(files_heap, key=lambda item: item.sort_key)` 按升序输出前 N 项。
- **list 删除 `scan_complete` / `truncated_reason`**：result dict 只含 `directory / files / total / returned / scanned_entries`。

**验证**：`test_list_files_observes_all_entries_and_omits_partial_only_fields` 断言 4 个 entry 扫描 4 个、total=3、returned=2、无 `scan_complete`/`truncated_reason`。`test_list_files_result_limit_keeps_exact_total_after_complete_scan` 断言 3 个匹配文件返回 2 个、total=3、scanned_entries=3。

### 3. search 只有 result_limit partial 且 containment 不漂移

`_search_files_business`（`doc_tools.py:1613-1708`）实现正确：

- **共享 iterator**：`for file_path in _iter_directory_entries(dir_path, recursive=True, ...)` 与 list 使用同一排序逻辑。
- **containment 不漂移**：每个 file_path 在正文读取前仍经 `_resolve_search_files_candidate` 做 resolved containment 与 file 检查。外部 symlink target 在该 helper 中返回 `None` 并被跳过。
- **result_limit 合法 partial**：`if len(matches) >= actual_limit` 时设 `scan_complete=False, truncated_reason="result_limit"` 并 `break`。否则遍历到 EOF，`scan_complete=True, truncated_reason=None`。
- **search 删除 `directory_entry_limit`**：不再有目录 cap 产生的 partial；只有合法 output result_limit。

**验证**：`test_search_files_scans_to_eof_when_result_limit_is_not_reached` 断言 3 个 entry 扫描 3 个、total_matches=1、scan_complete=True、truncated_reason=None。`test_search_files_cumulative_match_limit_returns_result_partial` 断言达到 limit 时 scan_complete=False、truncated_reason=result_limit。

### 4. source/directory cap 的 schema/prompt/test/production 传播是否清零

- **常量删除**：`_DOC_DIRECTORY_MAX_ENTRIES` 已从 `doc_tools.py:81` 删除。
- **参数删除**：`max_directory_entries` 已从 `_route_doc_business`、`_list_files_business`、`_search_files_business` 的签名、docstring 和调用中完全删除。
- **schema 收敛**：list description 不再包含 `scan_complete`、`truncated_reason`、`directory_entry_limit`。search description 只保留 `result_limit` 语义。
- **result 字段删除**：list result 不再有 `scan_complete`、`truncated_reason`。search result 的 `truncated_reason` 只允许 `result_limit` 或 `null`。
- **测试迁移**：旧 `test_list_files_directory_entry_limit_returns_self_describing_partial` 改为 `test_list_files_observes_all_entries_and_omits_partial_only_fields`。旧 `test_search_files_directory_entry_limit_returns_directory_partial` 改为 `test_search_files_scans_to_eof_when_result_limit_is_not_reached`。旧 `test_doc_tool_descriptions_explain_retained_partial_fields` 改为 `test_doc_tool_descriptions_explain_only_retained_output_facts`，断言精确 description 字符串。
- **README 迁移**：`tests/README.md` 的 Documents processors 和 Tools doc tools provider 段落已更新为完整 source snapshot / 完整目录遍历 / 真实阈值 smoke 语义。

**验证**：controller validation 报告 `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files` 在 `dayu tests README.md` 零命中。`bounded_source|BoundedSourceSnapshot|dayu-doc-bounded` 在 `dayu tests` 零命中。`547c926e..worktree` 对 `dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json` 零 diff。

### 5. 真实 10,001 文件与 >33 MiB smoke 是否确经 discovery->callable

`test_doc_complete_input_real_smoke_above_legacy_thresholds`（`test_doc_tools_provider.py:1389-1486`）实现正确：

- **fixture**：创建 10,001 个 17-byte `.txt` 文件、1 个 34 MiB+ 大文件（34 次 1 MiB chunk + 换行 + marker）、1 个 allowed root 内指向 outside marker 文件的 file symlink。总 entry 数 = 10,001 + 1 大文件 + 1 symlink = 10,003。
- **调用链**：`_spec(allowed_root) -> discover_tools(spec) -> definitions["list_files"].callable(...)` 等，经真实 `ToolsDiscoveryProviderSpec -> doc_provider.discover_tools -> ToolDefinition.callable`。
- **list 断言**：pattern 只匹配大文件，`total=1, returned=1, scanned_entries=10003`，无 `scan_complete`/`truncated_reason`。
- **read 断言**：成功，`returned_chars=2000, content_truncated=True`，`ToolTruncateSpec.target_field == "content"` 保留。
- **search 断言**：tail marker 命中且唯一 file 是大文件，`scanned_entries=10003, total_matches=1, scan_complete=True, truncated_reason=None`。outside symlink 零命中。
- **direct read 断言**：传入 outside symlink path，返回 `permission_denied`。

**验证**：独立运行 `1 passed in 2.04s`。

### 6. ToolTruncateSpec/fetch_more、安全机制与 Issue 177 边界是否保持

- **ToolTruncateSpec**：`_text_content_truncate` 仍用于 read/read-section 定义（`doc_tools.py:871`）。四个 ToolRuntime owner tests 通过（controller validation 报告 4 passed）。
- **fetch_more**：`TruncationManager|FetchMoreToolCallable|fetch_more` 对 `doc_tools.py` / `doc_provider.py` 零命中。Issue 177 未被实施。
- **安全机制**：`allowed_paths`、`_project_doc_paths`、`_resolve_search_files_candidate`、`_raise_if_doc_cancelled`、`ProcessBackedToolExecutionCapability` 仍有预期 owner/test 命中。search symlink escape、direct read containment、process cancel no-late-accept 测试通过。
- **Issue 177 边界**：`547c926e..worktree` 对 `dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json` 零 diff。Doc 与 TruncationManager 的完整接通仍由 Issue 177 负责。

### 7. 无关变更、下游补偿、兼容 shim、统一 authorization framework 或 deferred Issue 偷带

- **无关变更**：controller 已移除首次实现中的 formatter churn。当前 tracked semantic diff 仅限 accepted S2 owner、contract tests 和 README owner 段落。
- **下游补偿**：无。list/search/direct-read 的三条不同 symlink/containment 边界保持原样，未统一为新 authorization contract。
- **兼容 shim**：无。旧 `max_directory_entries` 参数、`_DOC_DIRECTORY_MAX_ENTRIES` 常量、`scan_complete`/`truncated_reason` list 字段均完全删除，无 re-export、alias 或 fallback。
- **统一 authorization framework**：未实施。controller discussion Topic 9 裁决"不实施统一 tool authorization framework"。
- **deferred Issue 偷带**：Issue 177（TruncationManager wiring）、symlink/TOCTOU hardening 均未进入本 slice。

## Open Questions

无。

## Residual Risk

| residual | classification | owner/destination |
|---|---|---|
| 极大目录可能增加磁盘、时间与 inode 消耗 | accepted product semantic | 后续 input-governance 设计；R01 按 accepted contract 保留完整遍历 |
| 五工具 output/remainder 尚未全部通过 TruncationManager 无损续读 | tracked by existing issue | GitHub Issue #177 |
| search 达到合法 result limit 后不扫描剩余 entry，total_matches 仍只是返回命中数 | tracked by existing issue | Issue #177 若未来形成 complete result + continuation contract |
| symlink/TOCTOU 仍是既有三条局部边界，不是统一 authorization contract | assigned to later work unit | 独立 filesystem/tool authorization hardening WU |

## Verification Summary

| 验证项 | 结果 |
|---|---|
| `pytest tests/tools/test_doc_tools_provider.py -q` | 66 passed in 4.13s |
| `pytest <real smoke node> -v` | 1 passed in 2.04s |
| `pytest <four ToolTruncateSpec/fetch_more owner nodes> -q` | 4 passed |
| `pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q` | 84 passed in 3.97s |
| `python -m pyright` | 0 errors, 0 warnings |
| `python -m ruff check dayu/tools/doc_tools.py tests/tools/test_doc_tools_provider.py` | All checks passed |
| `git diff --check 547c926e --` | pass |
| 删除语义 scan（`DocResourceBudget` etc.）| 零命中 |
| `bounded_source`/`BoundedSourceSnapshot` scan | 零命中 |
| Host/runtime/contracts/config diff | 零 diff |
| `scan_complete`/`truncated_reason` 生产逐命中分类 | 全部合法：search result_limit + read 字符 output，无 list producer/list schema 残留 |
| `dayu/tools/doc_tools.py` 覆盖率 | 620/770 statements, 80.519%（>=80% pass） |

## Verdict

**PASS**。R01-S2 的目录 cap 删除、共享 deterministic cancellable iterator、list 完整事实、search 合法 result_limit partial、symlink/containment/cancellation/process/output owner 保持、真实阈值 smoke、schema/prompt/test/README 收敛均实现正确，无 material finding。
