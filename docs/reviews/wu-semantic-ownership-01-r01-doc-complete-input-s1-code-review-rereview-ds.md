# WU-SEMANTIC-OWNERSHIP-01 / R01-S1 Code Re-Review — DS 路（修复后完整复核）

## Scope

- **Mode**: current changes（修复后完整 workspace diff 相对 slice base）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `1b4e5d33`（`docs: enter R01 source snapshot implementation`）
- **Accepted plan commit**: `54e35231`（`gateflow: accept R01 doc complete input plan`）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-rereview-ds.md`
- **Review date**: 2026-07-14 19:24 CST
- **Included scope**: 完整 workspace diff（6 tracked + `source_snapshot.py` untracked new），以及完整初始 review、controller adjudication、fix、fix controller validation 的全量证据链
- **Excluded scope**: 无
- **Parallel review coverage**: 无；本路为单 reviewer 完整走读

本 re-review 不是新 WU，不进入 R01-S2。根据 controller validation 指令，必须从 accepted plan、初始 review/adjudication、fix artifact、fix controller validation 和当前完整 S1 diff 出发做完整复核，不只看五个局部 patch。

---

## Verification Baseline（独立重跑）

```text
pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q
80 passed in 2.41s

python -m pyright
0 errors, 0 warnings, 0 informations

ruff check dayu/documents/processors/source_snapshot.py dayu/tools/doc_tools.py \
  tests/documents/test_import_boundary.py tests/documents/test_processors.py \
  tests/tools/test_doc_tools_provider.py
All checks passed!

git diff --check 1b4e5d33
pass

coverage report --include='dayu/documents/processors/source_snapshot.py' --fail-under=80
source_snapshot.py: 154 statements, 10 missed, 94%

coverage report --include='dayu/tools/doc_tools.py' --fail-under=80
doc_tools.py: 768 statements, 152 missed, 80%

rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit' dayu tests README.md
→ exit 1（零命中）

rg -n 'bounded_source|BoundedSourceSnapshot|dayu-doc-bounded' dayu tests
→ exit 1（零命中）
```

---

## 1. DS-F01 至 F05 逐项闭合验证

### DS-F01 — 同一 owner lock 覆盖 read/detach/actual close：**已闭合**

**生产代码证据**（`source_snapshot.py`）：

- `_read_at()`（行 452-457）：持 `self._lock` 检查 `self._spool`、执行 `spool.seek(position)` 和 `spool.read(size)`。lock 覆盖了从状态检查到 I/O 完成的完整临界区。
- `close()`（行 412-420）：持同一把 `self._lock` 执行 `self._spool` / `self._snapshot_size` 的 detach（设为 `None`）和 `spool.close()` 实际调用。`_materialized_path` 的 unlink（行 403-409）在锁外执行，与读取路径无冲突（`_read_at` 不访问 `_materialized_path`）。

**串行化保证**：已进入 `_read_at()` 临界区的读取先于 `close()` 的锁获取完成；`close()` 返回后，新的 `_read_at()` 调用在锁内发现 `self._spool is None`，稳定得到 `ValueError("source snapshot is not active")`。

**测试证据**（`test_processors.py:404-446`）：

- `_ConcurrentSpoolProbe` 提供确定性并发顺序观察点，不含 sleep/probability loop。
- 测试精确验证：reader 进入临界区 → close 的第二次 lock acquire 已开始但尚未完成 → 确认 `close_future.done() is False` 且 `spool.closed is False` → 放行 reader → inflight read 返回完整 payload → close 完成 → `spool.close_under_owner_lock is True` → close 后 reader 得到 `ValueError`。
- 使用 `ThreadPoolExecutor(max_workers=2)` + `threading.Event` 做确定性线程同步，超时设为 5.0 秒防止死锁。

**闭合确认**：read/detach/actual close 三者由同一把锁确定性串行化，无 race condition 窗口。测试提供确定性证据而非概率断言。

---

### DS-F02 — materialize 取消/partial cleanup：**已闭合**

**生产代码证据**（`source_snapshot.py:341-388`）：

- `materialize()` 在以下位置调用 `_check_cancellation()`：
  - 输出创建前（行 364）：首次取消检查。
  - 每轮 chunk 复制前（行 374）：与 `__enter__()` 的复制循环一致。
  - `_materialized_path` 发布前（行 379）：防止取消后残留已发布路径。
- 异常路径（行 382-388）：`except BaseException` 捕获取消异常和 I/O 异常，删除 `temp_path`（`unlink(missing_ok=True)`），然后重新抛出原始异常。
- spool 的最终清理由 `__exit__` → `close()` 保证（与 `__enter__` 的 `except BaseException` → `close()` 模式一致）。

**取消透出路径**：取消异常从 `_check_cancellation()` → 穿透 `materialize()` 的 `except BaseException`（因为 `raise` 保留原始异常）→ 穿透 consumer 代码 → 最终由 `__exit__` 清理。

**测试证据**（`test_processors.py:561-640`）：

- 使用单用途 `cancellation_check` 闭包 + `_SyntheticCancellation`，进入 snapshot 后才启用取消。
- 通过 monkeypatch `_COPY_CHUNK_BYTES = 4`（`_MATERIALIZE_TEST_CHUNK_BYTES`）精确控制物化循环步数。
- 在第三次 `_check_cancellation()` 时，验证真实 `NamedTemporaryFile` partial path 已存在（通过 `tmp_path.glob("dayu-doc-source-*.partial")`），然后抛出取消异常。
- 验证取消异常身份透出（`raised.value is cancellation_error`）、partial path 被删除（`not observed_partial_path.exists()`）、spool 被关闭（`spool_recorder.spool.closed is True`）。
- 将 `tempfile.tempdir` 定向到 `tmp_path`，所有临时文件在测试后自动清理。

**闭合确认**：物化全流程持续观察取消，取消异常原样透出，partial file 被删除，spool 由 context 退出清理。

---

### DS-F03 — 空 source (0 bytes)：**已闭合**

**测试证据**（`test_processors.py:449-474`）：

- `_MemorySource(payload=b"", content_length=0)` → 进入 `SourceSnapshot`。
- 断言 `snapshot_size == 0`、`content_length == 0`（active 后 exact 值）。
- `reader.read()` → `b""`；`reader.seek(0, io.SEEK_END)` → `0`；`reader.tell()` → `0`；`reader.read(1)` → `b""`。
- `snapshot.materialize(suffix=".empty")` → 创建空物化文件，`read_bytes() == b""`。
- Context 退出后 `not materialized_path.exists()`。

**生产代码走读确认**：`__enter__()` 行 290 第一次 `read()` 返回 `b""`，跳过循环体，`copied = 0`，`spool.seek(0)` 后 spool 为空。reader 在空 spool 上行为与标准 `io.BytesIO(b"")` 一致。materialize 创建空输出文件。

**闭合确认**：零长度边界的所有语义（EOF、SEEK_END、空物化、生命周期清理）均有确定性测试验证。

---

### DS-F04 — Source.open OSError：**已闭合**

**测试证据**（`test_processors.py:643-671`）：

- `_FailingOpenSource(open_error)` — `open()` 直接 `raise self.error`，不返回流。
- monkeypatch `SpooledTemporaryFile` 为 `_SpoolRecorder()` 观察 spool 生命周期。
- 断言 `raised.value is open_error`（同一实例身份透出）。
- 断言 `spool_recorder.spool.closed is True`（已创建但未写入的 spool 被关闭）。

**生产代码走读确认**：`__enter__()` 行 282 的 `self._spool = spool` 在 `try` 块（行 284）之前执行；若行 286 `source.open()` 抛出，进入 `except BaseException`（行 298）→ `self.close()`（行 299），close 清理 spool → 重新抛出原始 OSError。

**闭合确认**：`Source.open()` 失败的异常身份透出与 spool 清理均有确定性测试。

---

### DS-F05 — materialize write OSError：**已闭合**

**测试证据**（`test_processors.py:674-706`）：

- `_FailingMaterializedOutput` 是单用途 context-manager/callable：先写入部分字节（`max(1, len(data) // 2)`）、flush，然后抛出指定 `OSError`。
- 没有成功模式、策略字段或通用 factory 层。
- 断言 `raised.value is write_error`（同一实例身份）、`0 < output.bytes_written < len(payload)`（部分写入）、`not partial_path.exists()`（partial path 已删除）。

**生产代码走读确认**（`source_snapshot.py:382-388`）：

- `except BaseException` 捕获写入异常，`temp_path.unlink(missing_ok=True)` 删除 partial 文件，重新抛出原始异常。
- `unlink` 的 `OSError` 被抑制（`except OSError: pass`），保留原始写入异常不被覆盖。

**闭合确认**：写入失败时 partial path 被删除、原始异常透出、清理异常不覆盖写入异常。

---

## 2. 测试 seam 收敛性审查

### 2.1 当前 seam 清单与最小性评估

| seam | 用途 | 行数 | 是否过度？ |
|---|---|---|---|
| `_ConcurrentSpoolProbe` | F01 — 确定性并发顺序证明 | ~58 行 | **否**。必须同时作为 `SpooledTemporaryFile` replacement、lock provider 和 spool 观察点。去掉它只能退回 sleep/probability race。 |
| `_FailingMaterializedOutput` | F05 — 输出写入失败注入 | ~52 行 | **否**。必须同时替换 `NamedTemporaryFile`（构造+context manager）并提供自定义 `write()`。无成功分支、策略字段或工厂层。 |
| `_SpoolRecorder` | F02/F04 — 观察 spool 是否被关闭 | ~10 行 | **否**。只记录一个 `spool` 字段和一个 factory 调用。 |
| `_FailingOpenSource` | F04 — `Source.open()` 失败 | ~20 行 | **否**。`frozen/slots` dataclass，单一 `error` 字段，`open()` 只 `raise self.error`。 |
| `_CancelAfterChecks` | F02（兼复用） — cancellation 计数 | ~14 行 | **否**。slots dataclass，单字段 `remaining`，`__call__` 递减+抛出。无 arm/disarm/策略/工厂。 |

合计 6 个测试辅助，~154 行，无 builder/协议/配置/继承/可扩展策略或多层复用框架。每个 seam 对应一个无法通过真实 I/O 构造的注入点（并发顺序、写入失败、open 失败），且仅用于单一 finding 的验证。

### 2.2 与 controller 拒绝的过度设计对比

Controller 在首次 fix 中拒绝的通用层包括：
- `_ObservedLock`（通用 lock 观察者）
- `_BlockingReadSpool`（通用阻塞 spool）
- `_ArmableCancellationCheck`（可 arm/disarm 的取消检查）
- `_MaterializedOutput` / `_MaterializedOutputFactory`（成功/失败双模式输出工厂）

当前代码中这些符号全部零命中（已由独立的 source scan 确认）。当前保留的 seam 没有上述通用层的任何特征。

### 2.3 竞态/假阳性风险评估

- **F01 并发测试**：`_ConcurrentSpoolProbe` 使用 `threading.Event` + 超时（5.0s），确定性握手顺序为：reader 进入临界区 → close 第二次 lock acquire 开始 → 确认 close 未完成且 spool 未关闭 → 放行 reader → reader 返回 → close 完成。不存在概率窗口。
- **F02 取消测试**：通过 monkeypatch `_COPY_CHUNK_BYTES = 4` 精确控制循环步数，在第 N 次 `_check_cancellation()` 时触发。无时间依赖。
- **F05 写入失败测试**：`_FailingMaterializedOutput.write()` 确定性先写部分再抛异常。无 I/O 竞态。

**结论**：无竞态或假阳性风险。

---

## 3. 初始 pass 边界逐项复核

### 3.1 Source-limit 删除：**PASS**

- `_DOC_SOURCE_MAX_BYTES`（原 `doc_tools.py:84`）：已删除。
- `DocResourceBudget` 及其 `__post_init__`：已删除。
- `SourceBudgetExceeded` exception class：随 `bounded_source.py` 删除。
- `_execute_doc_business_value` 的 `SourceBudgetExceeded` catch block：已删除（行 1175-1183 原位置）。
- Source scan 零命中（已独立验证）。

### 3.2 Consumer chain：**PASS**

- `_DocProcessTarget` / `_DocProcessTargetFactory`：`resource_budget` 字段已删除。
- `build_doc_tool_definitions`：不创建 `DocResourceBudget`。
- 五个 `_build_*_definition`：不接收 `resource_budget`。
- `_execute_doc_business_value` / `_route_doc_business`：不接收 `resource_budget`。
- 五个业务函数（`get_sections/search/read_file/read_file_section/list_files`）：`max_source_bytes` 参数已删除。
- `_source_snapshot` helper 替代 `_bounded_local_source`，不接收 `max_source_bytes`。
- `_source_snapshot` → `LocalFileSource` → `SourceSnapshot(source, cancellation_check)` 调用链不经过任何 budget 逻辑。

### 3.3 S1 临时目录 cap：**PASS**

- `_DOC_DIRECTORY_MAX_ENTRIES = 10_000`（`doc_tools.py:84`）保留。
- `_route_doc_business` 行 1176（list）、1193（search）直接传递 `max_directory_entries=_DOC_DIRECTORY_MAX_ENTRIES`。
- 无 wrapper/validator/assertion/dataclass/optional/budget 类型。
- 临时签名封闭：删除 `DocResourceBudget` 后无替代 budget 对象，常量值直接传入既有参数。

### 3.4 allowed_paths/containment/symlink：**PASS**

- `_project_doc_paths`（`doc_tools.py:1307`）：逻辑不变，仍做 canonical resolve + containment check。
- `_resolve_search_files_candidate`（`doc_tools.py:1663`）：逻辑不变，仍做 `resolve(strict=True)` + containment re-check。
- `list_files` 不使用 `_resolve_search_files_candidate`（仍只用 `is_file()` / `stat()`）。
- Symlink containment 测试仍通过（`test_search_files_does_not_read_symlink_escape`）。
- 无新增 containment 策略、无新增 `_is_relative_to` 调用路径、无统一 authorization wrapper。

### 3.5 Process cancel/fencing：**PASS**

- `_raise_if_doc_cancelled` 仍存在，所有调用点不变。
- `_DOC_LOOP_CANCELLATION_CHECK_INTERVAL = 1_000` 不变。
- `ProcessBackedToolExecutionCapability` 仍用于所有五工具。
- `_DocProcessCancellationToken`（永不取消 stub）不变。
- `_invoke_doc_business` cancellation 分类（pre-lock + post-lock）不变。

### 3.6 ToolTruncateSpec / fetch_more：**PASS**

- `ToolTruncateSpec` 仅用于 `read_file`（`doc_tools.py:872`）和 `read_file_section`（`doc_tools.py:943`）。
- 其他三个工具 `truncate=None`。
- `_text_content_truncate` 不变。
- `TruncationManager` / `FetchMoreToolCallable` / `fetch_more` 在 `doc_tools.py` 和 `doc_provider.py` 中零命中（Issue 177 非实现证据）。
- Host/runtime/contracts/tool_discovery.json 无 diff。

### 3.7 LLM-facing：**PASS**

- 删除的 rejected guidance tokens（`较小文件`、`拆分文件`、`缩小文件范围`、`缩小目录`、`source_limit`、`skipped_oversized_files`、`source_budget_exceeded`）全部零命中。
- `directory_entry_limit` 仍存在于 list/search producer 和 LLM-facing description — 这是 accepted S1 中间态，S2 将删除。
- search description 更新为：`"truncated_reason 会是 result_limit 或 directory_entry_limit，应分别收紧关键词或目录后重试。"` — 删除了 `source_limit` 和"改用较小文件"引导。
- `dayu/config/prompts/base/tools.md` 的"大文件先看章节"保留（output/导航效率建议，按 accepted plan §12.3 不删除）。

### 3.8 测试/coverage/pyright/scans：**PASS**

- 80 tests passed（15 processor + 3 import_boundary + 62 provider）。
- `source_snapshot.py` coverage: 94%（≥80% gate）。
- `doc_tools.py` coverage: 80%（=80% gate）。
- pyright: 0 errors, 0 warnings, 0 informations。
- ruff: All checks passed。
- `git diff --check`: pass。
- 删除符号扫描零命中。
- 旧模块引用扫描零命中。

### 3.9 Allowlist / README / S1-S2-deferred Issue 边界：**PASS**

- Diff 文件：6 tracked + `source_snapshot.py` untracked（完全在 accepted S1 allowlist §8.3 内）。
- 无 README 修改（符合 accepted plan §13.1：S1 不写中间态 README，S2 统一更新）。
- 无 S2 代码（无 directory cap 删除、无 deterministic iterator、无 `list_files` scan_complete/truncated_reason 删除）。
- 无 Issue 177 代码（无 TruncationManager wiring、无新 ToolTruncateSpec、无 fetch_more 业务工具）。
- 无 control/design doc 语义修改（`issues-implementation-control.md` 仅更新 gate status 文本）。

---

## 4. 测试迁移完整性复核

### 4.1 Node 数变化

- Baseline: 83 passed（controller validation 基线）。
- Fix 后 S1: 80 passed（75 原始 + 5 新增 F01-F05 owner tests）。

### 4.2 旧 contract 测试替换对照

| 旧测试 | 新测试 | 验证点 |
|---|---|---|
| `test_bounded_source_snapshot_enforces_actual_stream_limit_plus_one` | `test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors` | 真实 EOF + 独立游标 |
| `test_bounded_source_snapshot_accepts_exact_limit_and_feeds_processor` | `test_source_snapshot_ignores_declared_length_and_feeds_processor` | 声明长度只作 metadata |
| `test_bounded_source_snapshot_rejects_invalid_byte_limit` (x3 parametrize) | 无替代 | max_bytes 概念已不存在 |
| `test_bounded_source_snapshot_declared_oversize_is_only_an_early_rejection` | 无替代 | 声明长度不再拒绝 |
| `test_read_file_source_limit_plus_one_raises_typed_resource_failure` | `test_read_file_reads_complete_source_without_source_byte_limit` | 完整读取而非 budget failure |
| `test_search_files_source_limit_skips_oversized_processor_input_without_fallback` | `test_search_files_complete_source_enters_processor_and_returns_match` | 完整源进入 processor + 返回命中 |
| `test_doc_resource_budget_rejects_non_positive_or_bool_limits` (x4 parametrize) | 无替代 | DocResourceBudget 类已删除 |

### 4.3 失败路径覆盖矩阵

| 失败路径 | 测试 node | 状态 |
|---|---|---|
| Source I/O 失败 → spool cleanup | `test_source_snapshot_closes_spool_on_io_failure_or_cancellation` (_FailingSource) | PASS |
| 取消 → spool cleanup | `test_source_snapshot_closes_spool_on_io_failure_or_cancellation` (_CancelAfterChecks) | PASS |
| consumer exception → materialized cleanup | `test_source_snapshot_cleans_materialized_file_after_python_exception` | PASS |
| 正常退出 → materialized cleanup | `test_source_snapshot_cleans_materialized_file_on_normal_exit` | PASS |
| 重复进入拒绝 | `test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors` | PASS |
| close 后使用拒绝 | `test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors` | PASS |
| 空 source | `test_source_snapshot_empty_source_has_exact_eof_and_materialization` | PASS (新增) |
| Source.open OSError | `test_source_snapshot_open_oserror_is_preserved_and_closes_spool` | PASS (新增) |
| materialize 写入失败 | `test_source_snapshot_materialize_write_oserror_removes_partial_path` | PASS (新增) |
| materialize 取消 | `test_source_snapshot_materialize_observes_cancellation_and_cleans_resources` | PASS (新增) |
| reader/close 并发安全 | `test_source_snapshot_close_serializes_inflight_read_and_actual_close` | PASS (新增) |
| 取消传播（search iteration） | `test_search_files_cancelled_during_iteration_stops_before_later_scan` | PASS |
| 取消传播（line scan loop） | `test_search_via_line_scan_observes_loop_cancellation` | PASS |
| 取消传播（read encoding fallback） | `test_read_file_cancelled_after_first_failed_encoding_stops_fallback` | PASS |
| 路径拒绝 | `test_path_validation_failure_does_not_enter_migrated_function_body` | PASS |

---

## 5. Adversarial Failure Pass

### 5.1 并发安全

- `_read_at()` 和 `close()` 使用同一把 `self._lock`，临界区覆盖 spool 状态检查 + I/O + detach + actual close。
- 无其他 writer 路径（spool 只在 `__enter__` 中写入，状态转换后不再写入）。
- `__enter__` 的 stream copy 是单线程的（snapshot 构造时），不对共享 spool 产生并发写入。
- `materialize()` 的 reader（`self.open()`）创建新的 `_SnapshotBinaryReader`，与其他 reader 不共享位置。
- 无 deadlock 风险：`_read_at` 持锁时间 = seek + read（I/O 在锁内），`close` 持锁时间 = detach + close（I/O 在锁内）。两者操作的是同一个底层 spool，但 close 只在最后一个 reader 使用完后才调用（context manager 保证）。

### 5.2 资源泄漏

- Spool（`SpooledTemporaryFile`）：正常退出、Python 异常、I/O 异常、取消 → 均由 `__exit__` → `close()` 清理。
- Materialized path：正常退出 → `__exit__` → `close()` unlink；异常 → `except BaseException` handler unlink + `close()` unlink（`missing_ok=True`）。
- `close()` 幂等：多次调用不会重复 close/unlink。
- `materialize()` 的 partial file：取消或写入失败 → `except BaseException` 中的 `temp_path.unlink(missing_ok=True)`。
- 没有 `__del__` 依赖（不使用 finalizer）。

### 5.3 状态机完整性

**SourceSnapshot 状态**: `new → active → closed`

- `new → active`：仅 `__enter__` 推进，单次进入（`_entered` flag），失败时回退到 `closed`。
- `active` 期间：`open()` 创建 reader、`materialize()` 创建物化文件、`_read_at()` 读取 spool。
- `active → closed`：`close()` 或 `__exit__` 推进，幂等。
- `closed` 是吸收终态：`open()` → `ValueError`，`materialize()` → `ValueError`，`__enter__()` → `RuntimeError`。
- 无 "re-open" 或 "re-enter" 路径。

### 5.4 空状态/边界条件

- 空 source（0 bytes）：已验证（F03）。
- Source.open 失败：已验证（F04）。
- Materialize 写入失败：已验证（F05）。
- Source.content_length 为 None：`_MemorySource(payload=payload)` → `content_length is None`，`SourceSnapshot` 正确进入 EOF 复制（`test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors`）。
- 重复 close：已验证（`snapshot.close(); snapshot.close()` 不抛异常）。

### 5.5 取消路径

- `__enter__` 复制循环：每 chunk 前 `_check_cancellation()`。
- `materialize` 复制循环：每 chunk 前 `_check_cancellation()` + 输出创建前 + 路径发布前（F02 修复）。
- `_read_at`：不检查取消（快照已建立，reader 只读，取消由 consumer 的循环控制）。
- 取消传播链：`_check_cancellation()` → cancellation_check callable（`_DocSourceCancellationCheck`）→ `CancellationToken.raise_if_cancelled()` → Host 取消异常 → 穿透 Doc 层 → 由 ToolRuntime 处理。

### 5.6 序列化安全

- `_DocProcessTarget` fields: `str`, `dict`, `tuple[str, ...]`, `DocToolLimits`, `float | None` → 全部可 pickle。
- 测试验证 round-trip 后字段 tuple 精确匹配，repr 不含 `provider_lock`/`DocumentProcessor`/`CancellationToken`。
- 无 Host live object（lock、CancellationToken、processor registry）泄漏到序列化边界。

### 5.7 参数有效性链

- `allowed_paths` → `_parse_allowed_paths()` → `resolve(strict=False)` → `_project_doc_paths()` → `_is_relative_to` containment check。
- `DocToolLimits` → `build_doc_tool_definitions()` → `_DocProcessTargetFactory` → `_DocProcessTarget` → `_execute_doc_business_value` → `_route_doc_business` → 业务函数。
- `_DOC_DIRECTORY_MAX_ENTRIES` → `_route_doc_business` → `_list_files_business` / `_search_files_business`。
- 无参数在链路中被重新默认化、覆盖、丢失或静默忽略。

---

## 6. Semantic Ownership Drift Pass

### 6.1 Source owner：**无漂移**

- Source 完整快照的唯一 owner 是 `dayu.documents.processors.source_snapshot.SourceSnapshot`。
- `doc_tools._source_snapshot` 是 `SourceSnapshot` 的 thin factory（`LocalFileSource` + `SourceSnapshot`），不增加语义。
- `LocalFileSource` 是本地文件 `Source.open()` 的唯一实现，不拥有快照语义。
- 无下游 fallback、loose parsing、`hasattr/getattr`、默认值或兼容 shim 来补偿 source 语义。

### 6.2 Directory completeness owner：**S1 中间态无漂移**

- S1 的 directory cap 仍由 `_DOC_DIRECTORY_MAX_ENTRIES` 常量 + `max_directory_entries` 参数拥有。
- 传递链从 `DocResourceBudget.max_directory_entries` → `_DOC_DIRECTORY_MAX_ENTRIES` 直接传入，语义不变。
- S2 将删除此常量/参数，目录完整性转为由"遍历到真实 EOF"拥有。

### 6.3 Result/schema owner：**无漂移**

- `search_files` result 字段：删除 `skipped_oversized_files`（source cap）→ owner 正确。
- `list_files` result 字段：保留 `scan_complete`/`truncated_reason=directory_entry_limit`（directory cap）→ S2 删除。
- `read_file`/`read_file_section` result 字段：`content_truncated`/`scan_complete` 不变（output char limit → `ToolTruncateSpec` owner）。
- `ToolTruncateSpec` / `fetch_more` 仍由 Host `ToolRuntime` 拥有。

### 6.4 LLM-facing contract owner：**无漂移**

- Schema descriptions 由 `_build_*_definition` 函数拥有。
- 删除的 rejected tokens 的语义 owner 已随 source byte cap 删除而消失。
- 保留的 `directory_entry_limit` 文本属于 S1 中间态 directory cap owner，S2 将删除。
- `dayu/config/prompts/base/tools.md` 的 "大文件先看章节"是 output 导航建议，不是 input cap，owner 正确。

### 6.5 Crossover 检查：**无跨 owner 补偿**

- search 不再 catch `SourceBudgetExceeded`（异常类已删除）。
- read/get-sections 不再传递 `max_source_bytes`。
- `_doc_processor_factory.create_doc_file_processor` 只消费 `Source` 协议（`source.open()` / `source.materialize()`），不感知 budget。
- Host/ToolRuntime 不参与 source 输入治理（仍只做 output truncation）。
- Engine 不感知 Doc/snapshot/budget。

---

## 7. Findings

未发现实质性问题。

以下逐项记录：五项 accepted finding（DS-F01 至 F05）均已闭合；初始 pass 的 source-limit 删除、consumer chain、S1 临时目录 cap、allowed_paths/containment/symlink、process cancel/fencing、ToolTruncateSpec/fetch_more、LLM-facing、测试/coverage/pyright/scans、allowlist/README 与 S1/S2/deferred Issue 边界均通过独立复核；收敛后的测试 seam 无过度设计或竞态/假阳性。

### R01-S1-REREVIEW-DS-P01 — 逐项 pass 确认：修复后 SourceSnapshot 状态机完整路径

| 检查项 | 入口/行号 | 结论 |
|---|---|---|
| 同一锁覆盖 read/detach/actual close | `close:412` / `_read_at:452` — 同一把 `self._lock` | **PASS** — F01 闭合 |
| 物化全流程取消检查 | `materialize:364,374,379` — 三次 `_check_cancellation()` | **PASS** — F02 闭合 |
| 取消/写入失败删 partial path | `materialize:382-388` — `except BaseException: unlink + raise` | **PASS** — F02/F05 闭合 |
| 空 source exact EOF/materialize | `test_processors.py:449-474` | **PASS** — F03 闭合 |
| `Source.open` OSError 透出+spool 关闭 | `test_processors.py:643-671` | **PASS** — F04 闭合 |
| materialize write OSError partial 删除 | `test_processors.py:674-706` | **PASS** — F05 闭合 |
| `__enter__` 复制到真实 EOF | `__enter__:287-293` — `while True: read; if not chunk: break` | **PASS** |
| declared length 不拒绝 | `__enter__` 不使用 `content_length` | **PASS** |
| independent cursor | `_SnapshotBinaryReader._position` 独立 | **PASS** |
| 单次进入拒绝 | `__enter__:275-276` | **PASS** |
| 幂等 close | `close:390-420` | **PASS** |
| materialized path 复用 | `materialize:360` — `if self._materialized_path is not None: return` | **PASS** |
| 异常 → spool/materialized 清理 | `__enter__:298-299` / `close:403-420` | **PASS** |
| reader close 后拒绝 | `open:338` → `snapshot_size` → `ValueError` | **PASS** |
| 模块零反向依赖 | import 仅 标准库 + `.source` | **PASS** |

### R01-S1-REREVIEW-DS-P02 — 逐项 pass 确认：Doc tools consumer 链完整删除

| 检查项 | 证据 | 结论 |
|---|---|---|
| `DocResourceBudget` 全链删除 | source scan 零命中 + `_DocProcessTarget`/`Factory`/`build_*`/`_execute_*`/`_route_*` 全部不含 `resource_budget` | **PASS** |
| `_DOC_SOURCE_MAX_BYTES` 删除 | source scan 零命中 | **PASS** |
| `SourceBudgetExceeded` 全链删除 | source scan 零命中 + import 删除 + catch block 删除 | **PASS** |
| `max_source_bytes` 参数全链删除 | 五个业务函数签名全部不含 `max_source_bytes` | **PASS** |
| `skipped_oversized_files` / `source_limit` 删除 | search result dict 不含 + source scan 零命中 | **PASS** |
| `_source_snapshot` 替代 `_bounded_local_source` | 行 1817-1827 — 不接收 `max_source_bytes` | **PASS** |
| search oversized catch 删除 | 行 1619-1642 — 无 `try/except SourceBudgetExceeded` | **PASS** |
| search LLM-facing 不含 source cap | description 仅提 `result_limit` 和 `directory_entry_limit` | **PASS** |
| 五工具 `with _source_snapshot(...)` 一致 | 行 1532, 1622, 1728, 1776 | **PASS** |

### R01-S1-REREVIEW-DS-P03 — 逐项 pass 确认：S1/S2/Issue 177/README 边界

| 检查项 | 证据 | 结论 |
|---|---|---|
| S1 保留 directory cap | `_DOC_DIRECTORY_MAX_ENTRIES` 直接传入 list/search | **PASS** |
| 无 S2 代码 | 无 deterministic iterator、无 list partial field 删除 | **PASS** |
| 无 Issue 177 代码 | `TruncationManager`/`fetch_more` 零命中 | **PASS** |
| 无 README 修改 | `tests/README.md` 不在 diff 中 | **PASS** |
| 无 control/design 语义修改 | `issues-implementation-control.md` 仅 gate status 更新 | **PASS** |
| Diff 仅 allowlist 文件 | 6 tracked + `source_snapshot.py` untracked | **PASS** |

### R01-S1-REREVIEW-DS-P04 — 独立验证矩阵

| 验证项 | 命令/结果 | 结论 |
|---|---|---|
| Focused tests | `80 passed in 2.41s` | **PASS** |
| Processor tests | `15 passed in 0.44s` | **PASS** |
| pyright | `0 errors, 0 warnings, 0 informations` | **PASS** |
| ruff | `All checks passed!` | **PASS** |
| git diff --check | exit 0 | **PASS** |
| source_snapshot.py coverage | `154 statements, 10 missed, 94%` | **PASS** |
| doc_tools.py coverage | `768 statements, 152 missed, 80%` | **PASS** |
| 删除符号 scan | 零命中 | **PASS** |
| 旧模块 scan | 零命中 | **PASS** |
| 安全 owner scan | 全部预期命中 | **PASS** |
| Issue 177 non-implementation scan | 零命中 | **PASS** |
| Host/runtime/contracts/config diff | 无 diff | **PASS** |

---

## Open Questions

无。

## Residual Risk

| 风险区域 | 分类 | 处置 |
|---|---|---|
| S1 仍保留 10,000 directory entry cap 与 LLM 文本 | covered by accepted R01-S2 | S2 删除 |
| `tests/README.md` 仍描述旧 source/directory contract | covered by accepted R01-S2 | S2 统一更新 |
| 极大输入可能消耗磁盘与处理时间 | assigned to later work unit | 当前 contract 按完整 spool + process fencing + cancellation |
| 五工具尚未完整接入 `TruncationManager` / framework remainder continuation | tracked by existing issue | GitHub Issue #177 |
| `doc_tools.py` coverage 80% 恰好位于 threshold | 当前 S1 测试集已达到 gate | S2 >33 MiB smoke 会进一步提高覆盖率 |
| F06 disk-spill rollover 未在 S1 验证 | covered by accepted R01-S2 >33 MiB smoke | 标准库 `SpooledTemporaryFile` rollover 可靠性高 |

---

## Verdict

**PASS** — 五项 accepted finding（DS-F01 至 F05）均在 `SourceSnapshot` owner 或其 owner tests 内完整闭合。收敛后的确定性测试 seam 无过度设计、竞态或假阳性。初始 pass 的 source-limit 删除、consumer chain、S1 临时目录 cap、allowed_paths/containment/symlink、process cancel/fencing、ToolTruncateSpec/fetch_more、LLM-facing、测试/coverage/pyright/scans、allowlist/README 与 S1/S2/deferred Issue 边界全部通过独立复核。未发现新的 material defect。
