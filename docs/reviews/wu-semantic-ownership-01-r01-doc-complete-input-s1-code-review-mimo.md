# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `1b4e5d33` (slice base)
- Output file: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-mimo.md`
- Included scope: 6 production/test files relative to slice base `1b4e5d33`（删除 `bounded_source.py`、新增 `source_snapshot.py`、修改 `doc_tools.py`、修改 `test_processors.py`、修改 `test_import_boundary.py`、修改 `test_doc_tools_provider.py`）
- Excluded scope: control/design/README/Host/Engine/runtime/config/Fins/UI/Service/contracts 无 diff
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下逐项证明五个 adversarial 审查维度均无 material defect。

---

### 1. SourceSnapshot 状态机反例分析

**状态图**: `__init__`（未进入）→ `__enter__`（单次 Source.open → 真实 EOF → active）→ `open()` / `materialize()` / `_read_at()` → `close()`（清理 spool + materialized path）→ 终态

**1.1 单次 stream / EOF**

- `source_snapshot.py:286-297`: `__enter__` 内 `self._source.open()` 只调用一次，`while True` 循环读 `_COPY_CHUNK_BYTES` 到 `not chunk`（真实 EOF）。无 `max_bytes` / `remaining + 1` 提前截断。
- 测试 `test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors`（`test_processors.py:208-244`）：`b"0123456789" * 20_000` 未知长度 payload，断言 `snapshot_size == len(payload)` 且 `source.open_count == 1`。
- 测试 `test_source_snapshot_ignores_declared_length_and_feeds_processor`（`test_processors.py:247-279`）：声明长度为 `len(payload) * 100_000`，断言进入后 `content_length == len(payload)`（实际值），`open_count == 1`。

**1.2 cursor 独立性**

- `_SnapshotBinaryReader` 每个实例维护独立 `_position`。`_read_at` 通过 `self._lock` + `spool.seek(position)` + `spool.read(size)` 实现线程安全的绝对定位读取。
- 测试：`test_processors.py:229-236` 断言两个 cursor 的 `read` / `tell` / `seek(SEEK_END)` 互不影响。
- 实测 probe：10 线程并发读同一 snapshot 不同区域，全部正确返回 50 字节。

**1.3 metadata 行为**

- `content_length`（`source_snapshot.py:209-224`）：active 前返回 `self._source.content_length`（声明值），active 后返回 `self._snapshot_size`（实际值）。两个测试均验证此转换。
- `snapshot_size`（`source_snapshot.py:243-258`）：active 前或 close 后抛出 `ValueError("source snapshot is not active")`。

**1.4 materialize 路径复用**

- `source_snapshot.py:359`: 重复 `materialize()` 复用 `self._materialized_path`。
- 测试 `test_source_snapshot_cleans_materialized_file_on_normal_exit`（`test_processors.py:309-328`）：断言 `materialize(suffix=".txt") == materialized_path`（同一路径）。

**1.5 close / 异常 / 取消 cleanup**

- `close()`（`source_snapshot.py:383-410`）：先 unlink materialized path（`missing_ok=True`），再 close spool；`OSError` 被 suppress。
- `__enter__` 的 `except BaseException`（`source_snapshot.py:298-300`）调用 `self.close()`，确保 Source I/O 失败和 cancellation 异常均触发 cleanup。
- 测试 `test_source_snapshot_cleans_materialized_file_after_python_exception`（`test_processors.py:282-306`）：consumer `raise RuntimeError` 后 `materialized_path` 被删除。
- 测试 `test_source_snapshot_closes_spool_on_io_failure_or_cancellation`（`test_processors.py:331-393`）：`_FailingSource`（`OSError`）和 `_CancelAfterChecks`（`_SyntheticCancellation`）均导致 spool 被关闭。monkeypatch 正确指向 `source_snapshot.tempfile.SpooledTemporaryFile`。
- 实测 probe：reader 在 context close 后使用正确抛出 `ValueError("source snapshot is not active")`。

**1.6 重复进入**

- `source_snapshot.py:275-276`: `if self._entered: raise RuntimeError("source snapshot cannot be reused")`。
- 测试 `test_processors.py:241-243`：`__enter__` 重复调用抛出 `RuntimeError`。

**1.7 并发安全**

- `_read_at` 使用 `self._lock`（`threading.Lock`）保护 spool 定位和读取。
- `__enter__` 的 stream 复制是单线程（snapshot 构造时），不存在并发写入。
- 实测 probe：10 线程并发 `open()` + `read()` 正确。

**结论**: 状态机无反例。异常、取消、close 后使用、重复进入、并发读取均有正确行为和直接测试/probe 证据。

---

### 2. Doc process/direct route 参数/序列化/错误投影

**2.1 参数删除完整性**

- `_DOC_SOURCE_MAX_BYTES`（原 `doc_tools.py:84`）：已删除。
- `DocResourceBudget`（原 `doc_tools.py:103-138`）：已删除，连同 `__post_init__` 校验。
- `_DocProcessTarget.resource_budget`：已删除。测试 `test_doc_process_target_factory_is_pickle_round_trippable`（`test_doc_tools_provider.py:394-401`）断言精确字段集合 `("tool_name", "arguments", "allowed_root_locators", "limits", "timeout_seconds")`。
- `_DocProcessTargetFactory.resource_budget`：已删除。
- `build_doc_tool_definitions` 内 `resource_budget = DocResourceBudget()` 构造：已删除。
- 五个 `_build_*_definition` 函数的 `resource_budget` 参数：已删除。
- `_execute_doc_business_value` 的 `resource_budget` 参数：已删除。
- `_route_doc_business` 的 `resource_budget` 参数：已删除。
- 五个业务函数的 `max_source_bytes` 参数：已删除（`_get_file_sections_business`、`_search_files_business`、`_read_file_business`、`_read_file_section_business`）。

**验证**: `rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit' dayu tests README.md` 零命中。

**2.2 _source_snapshot 替代 _bounded_local_source**

- `_source_snapshot`（`doc_tools.py:1815-1827`）：接收 `path` 和 `cancellation_token`，构造 `LocalFileSource` 和 `SourceSnapshot`，不再接收 `max_source_bytes`。
- `SourceSnapshot` 不验证 `max_bytes`（已删除参数）。
- `_DocSourceCancellationCheck` 投影 CancellationToken 到层中立检查器，模式不变。

**2.3 错误投影变更**

- `SourceBudgetExceeded` catch block（原 `doc_tools.py:1171-1180`）：已删除。search 不再产生 `source_budget_exceeded` 错误。
- Source I/O 错误现在由通用 `except Exception`（`doc_tools.py:1104-1111`）捕获为 `execution_error`。这是改进：I/O 失败不再被静默跳过。

**2.4 search 字段清理**

- `skipped_oversized_files`：已从返回 dict 删除（`doc_tools.py:1655`）。测试 `test_search_files_complete_source_enters_processor_and_returns_match`（`test_doc_tools_provider.py:1089-1097`）断言精确 key 集合不含此字段。
- `truncated_reason` 的 `"source_limit"` 值：已从搜索逻辑和 LLM-facing description 删除。description 现在只说 `"result_limit 或 directory_entry_limit"`。

**2.5 序列化安全**

- `_DocProcessTarget` 的 `resource_budget` 字段已删除，不再被 pickle 序列化。
- 测试验证 round-trip 后字段集合精确匹配，`repr` 不含 `"provider_lock"` / `"DocumentProcessor"` / `"CancellationToken"`。

---

### 3. S1 机械保留 directory cap 是否无新 seam

**3.1 directory cap 传递路径**

- `doc_tools.py:1176`（list route）和 `doc_tools.py:1193`（search route）：`max_directory_entries=_DOC_DIRECTORY_MAX_ENTRIES`，直接传常量。
- 旧路径：`resource_budget.max_directory_entries`（`DocResourceBudget` 默认值也是 `_DOC_DIRECTORY_MAX_ENTRIES`）。
- 语义不变：仍然是 10,000 entry cap。
- 没有新增 validator、wrapper、budget、config、optional 或 compat seam。

**3.2 未误动的边界**

| 边界 | 验证 |
|---|---|
| symlink containment | 测试 `test_search_files_does_not_read_symlink_escape` 仍存在且通过 |
| cancellation fencing | 测试 `test_search_files_cancelled_during_iteration_stops_before_later_scan`、`test_search_via_line_scan_observes_loop_cancellation`、`test_search_files_line_scan_cancellation_returns_host_cancelled` 均仍存在且通过 |
| output truncation / ToolTruncateSpec | 测试 `test_read_tools_expose_current_truncate_spec_and_no_old_imports` 仍存在且通过 |
| fetch_more / Issue 177 | 测试 `test_no_old_fetch_more_business_tool` 仍存在且通过；`fetch_more` 不在 `doc_tools_source` 中 |
| result_limit partial | 测试 `test_search_files_cumulative_match_limit_returns_result_partial` 仍存在且通过 |
| directory_entry_limit partial | 测试 `test_search_files_directory_entry_limit_returns_directory_partial` 仍存在且通过 |
| path authorization | 测试 `test_disallowed_path_returns_failed_outcome`、`test_path_validation_failure_does_not_enter_migrated_function_body` 均仍存在且通过 |
| process-backed execution | 测试 `test_all_doc_tool_definitions_declare_process_backed_execution`、`test_doc_process_target_fast_path_matches_callable_baseline` 均仍存在且通过 |

**3.3 _DOC_DIRECTORY_MAX_ENTRIES 残留位置**

`rg` 只命中预期的 list/search producer（`doc_tools.py:84`、`:1176`、`:1193`、`:1426`、`:1461`、`:1569`、`:1605`）和对应测试。无意外残留。

---

### 4. 测试迁移完整性

**4.1 node 数减少分析**

- baseline: 83 passed
- S1: 75 passed（减少 8 node）
- 删除的 4 个测试定义产生 8 个 node：

| 删除的测试 | node 数 | S1 替代 |
|---|---|---|
| `test_bounded_source_snapshot_enforces_actual_stream_limit_plus_one` | 1 | `test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors`（验证完整 EOF 而非 limit+1 截断） |
| `test_bounded_source_snapshot_accepts_exact_limit_and_feeds_processor` | 1 | `test_source_snapshot_ignores_declared_length_and_feeds_processor`（验证声明长度只作 metadata） |
| `test_bounded_source_snapshot_rejects_invalid_byte_limit`（`@pytest.mark.parametrize("max_bytes", (0, -1, True))`） | 3 | 无替代（`SourceSnapshot` 不接收 `max_bytes`，校验逻辑已删除） |
| `test_bounded_source_snapshot_declared_oversize_is_only_an_early_rejection` | 1 | 无替代（声明长度超限不再拒绝，完整复制到 EOF） |
| `test_read_file_source_limit_plus_one_raises_typed_resource_failure` | 1 | `test_read_file_reads_complete_source_without_source_byte_limit`（验证完整读取而非 budget failure） |
| `test_search_files_source_limit_skips_oversized_processor_input_without_fallback` | 1 | `test_search_files_complete_source_enters_processor_and_returns_match`（验证完整源进入 processor） |

- `test_doc_resource_budget_rejects_non_positive_or_bool_limits`（`@pytest.mark.parametrize` 4 cases → 4 node）：已删除（`DocResourceBudget` 类已删除）。这些 node 在 S1 context 下无 owner-level contract 可断言。

**4.2 失败路径覆盖**

| 失败路径 | 测试 |
|---|---|
| Source I/O 失败 → spool cleanup | `test_source_snapshot_closes_spool_on_io_failure_or_cancellation`（`_FailingSource`） |
| 取消 → spool cleanup | `test_source_snapshot_closes_spool_on_io_failure_or_cancellation`（`_CancelAfterChecks`） |
| consumer exception → materialized cleanup | `test_source_snapshot_cleans_materialized_file_after_python_exception` |
| 正常退出 → materialized cleanup | `test_source_snapshot_cleans_materialized_file_on_normal_exit` |
| 重复进入 | `test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors`（`RuntimeError` 断言） |
| close 后使用 | `test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors`（`ValueError` 断言） |
| 取消传播（search iteration） | `test_search_files_cancelled_during_iteration_stops_before_later_scan` |
| 取消传播（line scan loop） | `test_search_via_line_scan_observes_loop_cancellation` |
| 取消传播（read encoding fallback） | `test_read_file_cancelled_after_first_failed_encoding_stops_fallback` |
| 路径拒绝 | `test_path_validation_failure_does_not_enter_migrated_function_body` |

**4.3 逐文件 coverage**

- `source_snapshot.py`: 134/147 statements, 91% ≥ 80% gate
- `doc_tools.py`: 616/768 statements, 80% ≥ 80% gate

两个文件均通过 `coverage report --include=... --fail-under=80`。`source_snapshot.py` 的 13 miss 主要是 `seek` 的 `SEEK_CUR` / `SEEK_END` 分支和 `materialize` 的 `OSError` 分支——这些是标准 io 行为或 cleanup 分支，不构成 owner-level contract gap。

---

### 5. allowlist / README trigger / pyright / scans

**5.1 allowlist**

相对 `1b4e5d33` 的 tracked semantic diff 只有 6 个 accepted S1 文件路径。implementation artifact 和 controller validation 是 untracked 新文件（plan 允许）。

**5.2 README trigger decision**

| README | decision | 依据 |
|---|---|---|
| `tests/README.md` | S1 不修改，R01-S2 统一更新 | accepted plan §8.5/§13.1；修改 tests 命中 trigger 但 S1 不写中间态 |
| 其它 README | 无需更新 | 安装/入口/参数/输出/分层/装配均未改变 |

**5.3 pyright**

`0 errors, 0 warnings, 0 informations`（pyright 1.1.408）。

**5.4 传播扫描**

- 删除符号零命中：`DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit` → 零命中
- 旧模块零命中：`bounded_source|BoundedSourceSnapshot|dayu-doc-bounded` → 零命中
- 保留符号只在预期位置：`_DOC_DIRECTORY_MAX_ENTRIES|max_directory_entries` → 只在 list/search producer 和测试

**5.5 S1/S2 边界**

- S1 删除了 source byte cap 全链
- S1 保留了 directory entry cap 作为 intermediate contract（R01-S2 删除）
- S1 不修改 README（R01-S2 统一更新）
- S1 不实现 Issue 177 / fetch_more / TruncationManager 接入
- 实测验证：所有 75 个 focused tests 通过

---

## Open Questions

无。

## Residual Risk

| residual area | classification | owner / destination |
|---|---|---|
| S1 仍保留 10,000 directory entry cap、list/search directory partial 与相关 LLM 文本 | covered by later approved slice | R01-S2 |
| `tests/README.md` 仍描述旧 source/directory contract | covered by later approved slice | R01-S2 |
| 极大输入可能消耗磁盘与处理时间 | assigned to later work unit | 后续 input governance；当前 contract 按完整 spool + process fencing + cancellation |
| 五工具尚未完整接入 `TruncationManager` / framework remainder continuation | tracked by existing issue | GitHub Issue #177 |
