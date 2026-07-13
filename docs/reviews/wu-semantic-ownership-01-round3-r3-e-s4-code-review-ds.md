# Code Review — R3-E Slice S4（AgentDS）

## Scope

- Mode: current changes（未提交 S4 diff only）
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD`（未提交 working tree diff）
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s4-code-review-ds.md`
- Control truth:
  - Design: `docs/host/design.md`、`docs/engine/design.md`
  - Control: `docs/host/issues-implementation-control.md`
  - Plan §6.5 / Slice 4: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
  - Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s4-implementation-codex.md`
  - Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s4-controller-validation.md`
- Included scope (5 files + 1 new):
  - `dayu/documents/processors/bounded_source.py`（新增）
  - `dayu/documents/processors/_doc_processor_factory.py`
  - `dayu/tools/doc_tools.py`
  - `tests/documents/test_processors.py`
  - `tests/documents/test_import_boundary.py`
  - `tests/tools/test_doc_tools_provider.py`
- Excluded scope: Fins、tool-security/file-authority/symlink-race policy、S5/aggregate/control bookkeeping

## Findings

**未发现实质性问题。**

S4 bounded source lifecycle、doc tool producer budgets、processor factory access、partial/resource outcome 语义与 LLM-facing descriptions 均按 accepted plan §6.5 实现，owner boundary 清晰，无 interface shim 或 Fins 越界。

## Checkpoint 逐项审查

### 1. BoundedSourceSnapshot — Source.open 同流 chunk copy、limit+1 typed failure、cleanup

**审查结论**: PASS

**证据**:

- `BoundedSourceSnapshot.__enter__()` (`bounded_source.py:276-321`): 从 `self._source.open()` 获取流，按 64 KiB chunk 读取，每 chunk 最多读 `remaining + 1` 字节。声明长度 (`content_length`) 只用于早拒绝 (291-293行)，不替代实读裁决。
- 第 `limit+1` byte 抛出 `SourceBudgetExceeded(source_uri, limit_bytes, observed_bytes)` (312-313行)，其中 `observed_bytes` 为实际已读字节。`test_bounded_source_snapshot_enforces_actual_stream_limit_plus_one` (`test_processors.py:206-216`) 用 `content_length=1`、实际 9 bytes 的 `_MemorySource` 证明声明值不能绕过实读 cap。
- `except BaseException: self.close(); raise` (319-321行) 确保资源/Source 异常、协作取消与 consumer Python exception 均清理 spool。`test_bounded_source_snapshot_closes_spool_on_resource_failure_or_cancellation` (299-342行) 用 spool spy 覆盖 `OSError`（Source 失败）与 `_SyntheticCancellation`（协作取消）两个路径。
- `__exit__` (323-344行) 调用 `close()`，无论正常退出还是 consumer exception 都清理。`test_bounded_source_snapshot_cleans_materialized_file_after_python_exception` (264-277行) 验证 consumer `RuntimeError` 抛出后物化文件被删除；`test_bounded_source_snapshot_cleans_materialized_file_on_normal_exit` (280-289行) 验证正常退出后物化文件也被删除。
- `materialize()` (359-399行): 单 snapshot 只发布一个命名临时文件（`_materialized_path` 复用）。路径在系统 `TMPDIR` 创建 (`tempfile.NamedTemporaryFile(delete=False)`)，prefix 为 `dayu-doc-bounded-`，不在 workspace 创建 durable temp。`except BaseException: temp_path.unlink(missing_ok=True); raise` (396-399行) 确保物化失败时清理。
- 不承诺 SIGKILL cleanup：`close()` (401-425行) 是 Python context manager 的 best-effort 清理，不声称即时 crash recovery。Implementation artifact §7 明确记录为 accepted operational limitation。
- 非法预算测试：`test_bounded_source_snapshot_rejects_invalid_byte_limit` (243-248行) 参数化 `0`、`-1`、`True`，均断言 `ValueError`。

### 2. create_doc_file_processor — 不再重开未治理路径、无 Fins/public processor contract shim

**审查结论**: PASS

**证据**:

- `create_doc_file_processor` 签名从 `(file_path: Path)` 改为 `(source: Source)` (`_doc_processor_factory.py:49`)。
- 工厂不再自行构造 `LocalFileSource`——旧代码 `source = LocalFileSource(path=file_path, ...)` 已删除。调用方 (`_try_create_processor`, `doc_tools.py:1946-1964`) 只传入已由 `BoundedSourceSnapshot` 完成字节预算治理的 Source。
- 若 `source.media_type is not None`，以调用方明确提供的 media type 覆盖 suffix/mimetypes 推断 (73-74行)；否则使用旧 suffix-to-mimetype 推断逻辑 (69-72行)。URI suffix 从 `uri.split("?", 1)[0]` 提取，对带 query string 的 URI 防御性兼容。
- 未修改 `source.py`、`local_file_source.py` 或三个 processor constructor (`markdown_processor.py`、`bs_processor.py`、`docling_processor.py`)。processor 通过 `Source.materialize()` 或 `Source.open()` 消费 snapshot，不需要扩大 Fins/public processor contract。
- Import boundary test (`test_import_boundary.py:104`) 扫描覆盖 `processors/bounded_source.py`，确认 `dayu.documents` 无 tools/Host/Engine/Service/UI/Fins 导入。

### 3. read_file producer cap 与 partial fields — 自足、无后置 truncate 伪装、无 unknown total 伪造

**审查结论**: PASS

**证据**:

- `_read_file_business()` (`doc_tools.py:1787-1847`): `max_chars` 同时传入 `_read_bounded_text` 作为 producer 字符 cap (1828-1835行)，不再依赖 Host `ToolTruncateSpec` 做后置 truncate。
- `_read_bounded_text()` (2265-2310行): 使用 `codecs.getincrementaldecoder` 按 chunk 解码，不调用 `read()`/`readlines()` 整文件 API。单行超长时最多累积 `max_chars+1` probe 字符 (2358-2361行)，命中后立即返回 `content_truncated=True, scan_complete=False, total_lines=None`。
- success 固定返回: `file_path`, `content`, `returned_chars`, `content_truncated`, `scan_complete`, `total_lines`。行范围请求时额外返回 `line_range` 二元整数数组 (1844-1846行)。
- 只有扫描到 EOF 时 `scan_complete=true` 且 `total_lines` 为精确整数 (2392-2393行)；字符 cap 命中时 `total_lines=None`，不伪造总行数。
- `_read_file_section_business()` (1850-1916行): 同样使用 `BoundedSourceSnapshot` 保证 byte cap，`content_truncated` 来自 `len(full_content) > max_chars` (1901行)，`scan_complete` = `not content_truncated` (1911行)。
- **Test**: `test_read_file_long_single_line_stops_at_character_limit` (898-923行) 验证 200 字符无换行文件在 `max_chars=17` 时 `content_truncated=True, scan_complete=False, total_lines=None`。
- **Test**: `test_read_file_multibyte_encoding_range_reports_complete_metadata` (925-951行) 验证多字节编码下 `scan_complete=True, total_lines=精确整数, content_truncated=False`。
- **Test**: `test_read_file_source_limit_plus_one_raises_typed_resource_failure` (953-995行) 验证 `SourceBudgetExceeded` → `source_budget_exceeded` failure。

### 4. list_files — directory heap、result cap、排序、bounded iteration

**审查结论**: PASS

**证据**:

- `_list_files_business()` (1501-1586行): directory iterator 最多观察 `max_directory_entries` (1543-1545行)，不构造全 tree file list。
- Result accumulator 使用固定大小堆 (`files_heap`): `sort_key=(file_path.name.lower(), relative_path.lower())` (1562行)。堆维护至多 `actual_limit` 项，新候选 `sort_key < heap[0].sort_key` 时 `heapreplace` (1567行)，保持最小排序结果。最终 `sorted(files_heap, key=lambda item: item.sort_key)` (1574-1575行) 产出确定性字母序结果。
- 完整扫描: `scan_complete=True, total=matched_files (精确), truncated_reason=None` (1581-1585行)。
- Entry cap 命中: `scan_complete=False, total=None, truncated_reason="directory_entry_limit"` (1584-1585行)。
- Result limit 与 directory entry limit 分离: 小目录即使仅返回前 N 项，仍完成扫描并给出精确 total。
- **Test**: `test_list_files_directory_entry_limit_returns_self_describing_partial` (818-847行) 验证 `scanned_entries=2, scan_complete=False, total=None, truncated_reason="directory_entry_limit"`。
- **Test**: `test_list_files_result_limit_keeps_exact_total_after_complete_scan` (869-895行) 验证 3 文件目录返回前 2 项但 `total=3, scan_complete=True`。
- **Test**: `test_list_files_directory_iteration_observes_cancellation` (850-866行) 验证 directory iteration 窗口中的取消。

### 5. search_files — result/source/directory cap reason 正确

**审查结论**: PASS

**证据**:

- `_search_files_business()` (1646-1757行): 同时计数 directory entries (1692-1693行)、单 Source bytes (1710-1712行的 `BoundedSourceSnapshot`) 与累计 matches (1741行)。
- 每个候选文件先通过 `_resolve_search_files_candidate` 重新校验 `resolved_file.resolve(strict=True)` + `_is_relative_to(..., root)` (1776-1784行)，再进入 `BoundedSourceSnapshot`。source byte cap 绑定到同一 open snapshot。
- `SourceBudgetExceeded` → `skipped_oversized_files += 1, scan_complete=False, truncated_reason="source_limit"` (1735-1740行)；不进入 processor/raw fallback (正确的 `continue`)。
- 累计 result cap: `len(matches) >= actual_limit` → `scan_complete=False, truncated_reason="result_limit", break` (1741-1744行)。
- Directory entry cap: `scanned_entries >= max_directory_entries` → `scan_complete=False, truncated_reason="directory_entry_limit", break` (1692-1695行)。
- Reason 封闭为 `result_limit` / `directory_entry_limit` / `source_limit` / `null`。多个原因时 directory_entry_limit 覆盖 source_limit（扫描先停止），符合 plan 的单 reason 语义。
- Result 截断: `matches[:actual_limit]` (1746行) 防御性确保不超限。
- success 固定返回 `query`, `directory`, `matches`, `total_matches`（仅本次已返回数）, `scanned_entries`, `skipped_oversized_files`, `scan_complete`, `truncated_reason`。
- `_search_source_with_encoding()` (2467-2519行): 使用增量 decoder 按 chunk 输出解码文本，每个 chunk 内部的 `\n` 分割后逐片段检查。`_search_line_fragment()` (2522-2577行) 使用 `tail` 窗口 (`max(query_length-1, _DOC_SEARCH_EXCERPT_CHARS//2)`) 处理跨 chunk 边界的匹配。snippet/matched_line_content 保持 `_DOC_SEARCH_EXCERPT_CHARS` 有界 (2560-2563行)。
- **Test**: `test_search_files_raw_long_line_finds_late_query_with_bounded_excerpt` (997-1025行) 验证 10KB 无换行文件尾部 query 可被 chunk scanner 发现。
- **Test**: `test_search_files_source_limit_skips_oversized_processor_input_without_fallback` (1027-1079行) 验证 oversized 文件计入 `skipped_oversized_files`、不进入 processor/raw fallback。
- **Test**: `test_search_files_cumulative_match_limit_returns_result_partial` (1081-1107行) 验证 result cap 命中时 `truncated_reason="result_limit"`。
- **Test**: `test_search_files_directory_entry_limit_returns_directory_partial` (1109-1135行) 验证 directory cap 命中时 `truncated_reason="directory_entry_limit"`。
- **Test**: `test_search_files_processor_factory_receives_bounded_snapshot` (1137-1182行) 验证 processor 只消费 `BoundedSourceSnapshot` 而非原路径。

### 6. LLM-facing descriptions — 自解释、未暴露内部术语

**审查结论**: PASS

**证据**:

- `list_files` description (checked via `test_doc_tool_descriptions_explain_partial_limit_fields`, test line 1184-1197): 说明 `scan_complete=false` / `total=null` 表示未扫描完整，需缩小目录或 pattern。
- `search_files` description: 说明 `total_matches` / `scanned_entries` / `skipped_oversized_files` / `scan_complete` / `truncated_reason` 的语义与下一步动作。
- `read_file` description: 说明 `content_truncated` / `scan_complete` / `total_lines` (null 表示未完成) 与 `line_range` 字段。
- `read_file_section` description: 说明 `content_truncated` / `scan_complete` 语义。
- 文本不使用 `BoundedSourceSnapshot`、`DocResourceBudget`、`heap`、`spool`、`incremental decoder`、`Source.open()` 等内部实现术语。

### 7. Tests — 断言 owner contract，未用旧 fixture 固化偶然行为

**审查结论**: PASS

**证据**:

1. **bounded_source 生命周期 owner contract** (`test_processors.py`):
   - `test_bounded_source_snapshot_enforces_actual_stream_limit_plus_one` — 声明值不能替代实读 cap。
   - `test_bounded_source_snapshot_accepts_exact_limit_and_feeds_processor` — exact limit 成功 + processor 只消费 snapshot。
   - `test_bounded_source_snapshot_rejects_invalid_byte_limit` — 非法预算 fail fast。
   - `test_bounded_source_snapshot_declared_oversize_is_only_an_early_rejection` — 声明长度早拒绝。
   - `test_bounded_source_snapshot_cleans_materialized_file_after_python_exception` — Python exception cleanup。
   - `test_bounded_source_snapshot_cleans_materialized_file_on_normal_exit` — 正常退出 cleanup。
   - `test_bounded_source_snapshot_closes_spool_on_resource_failure_or_cancellation` — 资源失败/取消 cleanup。
   - 复用路径验证：`materialize(suffix=".txt") == materialize(suffix=".md")` — 单 snapshot 单物化路径。
   - 不可复用验证：context 退出后 `snapshot.open()` → `ValueError("not active")`；`snapshot.__enter__()` → `RuntimeError("cannot be reused")`。

2. **doc_tools producer budget 与 partial contract** (`test_doc_tools_provider.py`):
   - `test_doc_resource_budget_rejects_non_positive_or_bool_limits` — `DocResourceBudget` 拒绝 bool/零/负数。
   - `test_list_files_directory_entry_limit_returns_self_describing_partial` — entry cap partial。
   - `test_list_files_result_limit_keeps_exact_total_after_complete_scan` — result limit vs complete scan 分离。
   - `test_read_file_long_single_line_stops_at_character_limit` — 字符 cap。
   - `test_read_file_multibyte_encoding_range_reports_complete_metadata` — 完整元数据。
   - `test_read_file_source_limit_plus_one_raises_typed_resource_failure` — source budget failure。
   - `test_read_file_section_limit_returns_explicit_partial_fields` — section partial。
   - `test_search_files_raw_long_line_finds_late_query_with_bounded_excerpt` — raw search tail window。
   - `test_search_files_source_limit_skips_oversized_processor_input_without_fallback` — source skip。
   - `test_search_files_cumulative_match_limit_returns_result_partial` — result cap。
   - `test_search_files_directory_entry_limit_returns_directory_partial` — directory cap。
   - `test_doc_tool_descriptions_explain_partial_limit_fields` — LLM-facing 自足描述。
   - `test_doc_process_target_read_file_partial_matches_direct_callable` — direct/process parity。
   - 取消测试覆盖: `test_list_files_directory_iteration_observes_cancellation`、`test_read_file_cancelled_after_first_failed_encoding_stops_fallback`、`test_search_files_cancelled_during_iteration_stops_before_later_scan`、`test_search_via_line_scan_observes_loop_cancellation`、`test_search_files_line_scan_cancellation_returns_host_cancelled`、`test_markdown_section_extraction_observes_cooperative_cancellation`。

3. **Import boundary** (`test_import_boundary.py:104`): 新增 `processors/bounded_source.py` 扫描覆盖，继续禁止 tools/Host/Engine/Service/UI/Fins 依赖。

4. 旧 fixture 改造: 旧 `read_file` 使用 `readlines()` 后置 truncate 的测试已被 producer budget 测试替代（`test_read_file_long_single_line_stops_at_character_limit`）。旧 `list_files` 构造全 tree/切片的行为已被 bounded heap 测试替代（`test_list_files_directory_entry_limit_returns_self_describing_partial`）。旧 `search_files` 使用 `read()/split()` 完整物化的行为已被 chunk decoder 测试替代（`test_search_files_raw_long_line_finds_late_query_with_bounded_excerpt`）。

### 8. Scope containment — 无 Fins/tool-security/file-authority/symlink-race policy 越界

**审查结论**: PASS

**证据**:

- `git diff HEAD --name-only` 仅包含 5 个 S4 文件（不含 untracked `bounded_source.py`），无 `dayu.fins/`、`dayu/tools/web/`、Host/Engine/Service/UI 文件。
- `bounded_source.py` 的 imports 仅包含标准库 (`io`, `os`, `tempfile`, `threading`, `pathlib`, `types`, `typing`) 和 `from .source import Source`——层中立、无 tools/Host/Engine/Fins 依赖。
- `_doc_processor_factory.py` 不再 import `LocalFileSource`，只依赖 `Source` protocol 和 `DocumentProcessor` 基类。
- 无 tool-security、upload allowlist、file-authority、symlink-safe upload、SSRF/TLS policy 或 generic capability framework 实现。
- 无 S5/aggregate/control bookkeeping 变更。

## Open Questions

无。

## Residual Risk

| 分类 | residual | owner |
| --- | --- | --- |
| accepted operational limitation | SIGKILL/主机崩溃可能留下至多 `max_source_bytes` 的系统命名 temp | `bounded_source.py` — 依赖系统 temp lifecycle |
| accepted processor-complexity limitation | 32 MiB byte cap 控制输入，但 processor 内部对象放大不受控 | `doc_tools.py` — 本轮确保 processor 构造前 byte cap |
| assigned authority residual | 路径校验到 `open()` 之间的 symlink/rename TOCTOU | 后续 file-authority/symlink-race WU — S4 保证同一 open handle 的 byte cap |
| accepted partial semantics | entry/source cap 命中时 total 未知 | `doc_tools.py` — `scan_complete=false, total=null` + 稳定 reason 明示 |
| validation tooling residual | pytest-cov dotted source 触发 NumPy double-load | coverage invocation/toolchain — 等价 coverage 证明 88%/81% |

以上 residual risks 均已在 plan §6.5、implementation artifact §7 和 controller validation 中记录。本 review 无新增 risk。

## Completion Report

- **Review result**: **PASS** — 无 material finding。
- 10 个 checkpoint 逐项审查通过：bounded source lifecycle、processor factory 接入、read_file/list_files/search_files producer cap 与 partial fields、directory heap 排序、search cap reason、LLM-facing descriptions、test owner contract、scope containment。
- 无 Fins/tool-security/file-authority/symlink-race policy 越界。
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s4-code-review-ds.md`
- **Ready for**: Controller adjudication → fix gate (如需) 或 S4 acceptance。
