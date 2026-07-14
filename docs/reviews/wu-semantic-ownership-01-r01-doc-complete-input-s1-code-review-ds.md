# WU-SEMANTIC-OWNERSHIP-01 / R01-S1 Code Review — DS 路

## Scope

- **Mode**: current changes（相对 slice base 的 uncommitted workspace diff）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `1b4e5d33`（`docs: enter R01 source snapshot implementation`）
- **Accepted plan commit**: `54e35231`（`gateflow: accept R01 doc complete input plan`）
- **Implementation artifact**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-implementation-s1-codex.md`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-controller-validation.md`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-ds.md`
- **Review date**: 2026-07-14 18:45 CST
- **Included scope**: 全部 6 个 production/test tracked diff 文件 + 1 个新增 untracked `source_snapshot.py` + 2 个 doc artifact + 1 个 control doc 修改
- **Excluded scope**: 无；所有 diff 均在 accepted S1 allowlist 内
- **Parallel review coverage**: 无；本路为单 reviewer 完整走读

## Verification Baseline（独立重跑）

```text
pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q
75 passed in 2.46s

python -m pyright
0 errors, 0 warnings, 0 informations

rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit' dayu tests README.md
→ exit 1（零命中）

rg -n 'bounded_source|BoundedSourceSnapshot|dayu-doc-bounded' dayu tests
→ exit 1（零命中）

rg -n '_DOC_DIRECTORY_MAX_ENTRIES|max_directory_entries' dayu tests
→ 仅命中 accepted S1 保留的 list/search producer 及对应 tests（预期命中）
```

## Findings

### R01-S1-DS-F01 — 中 — `SourceSnapshot._read_at()` 与 `close()` 的锁保护不完整，并发 reader 在 close 后可能读到已关闭 spool 的 OSError

- **入口/函数**: `SourceSnapshot._read_at()` / `SourceSnapshot.close()` / `_SnapshotBinaryReader.read()`
- **文件(行号)**: `dayu/documents/processors/source_snapshot.py:355-369`（`_read_at`）、`383-410`（`close`）、`120-136`（reader `read`）
- **输入场景**: 线程 A 正在 reader 中调用 `read()`，线程 B（或 `__exit__` 触发的同一线程）调用 `snapshot.close()`。在单线程 context manager 正常使用中不会触发，但在以下场景可能出现：(a) 多个 reader 被分发到不同线程同时读；(b) 异步取消导致 `close()` 在 reader 仍活跃时被调用；(c) 异常路径中 `__exit__` → `close()` 与尚未完成的 reader 并发。
- **实际分支**: `close()`（行 403）设置 `self._spool = None` 和 `self._snapshot_size = None`，然后调用 `spool.close()`。这两个赋值不在 `self._lock` 保护下。`_read_at()`（行 355）在 `with self._lock:` 内检查 `self._spool is None` 然后执行 `spool.seek()` + `spool.read()`。如果 `close()` 在 `_read_at()` 拿到锁之后、`spool.read()` 返回之前执行 `spool.close()`，reader 会从已关闭的底层文件读取，得到 `ValueError("I/O operation on closed file")` 或 `OSError`。
- **预期行为**: reader 在 snapshot 关闭后应稳定抛出 `ValueError("source snapshot is not active")`，不应抛出底层 I/O 错误。
- **实际行为**: reader 在跨过锁内 `_spool is None` 检查后，如果 `close()` 恰好介入并关闭底层 spool，reader 抛出非确定性的底层 I/O 异常而非干净的 `ValueError`。
- **直接证据**: `close()` 行 403-404 的赋值不在 `self._lock` 保护下；行 405 的 `spool.close()` 会关闭 `SpooledTemporaryFile` 底层文件描述符，而行 355-369 的 `_read_at()` 在获取锁后不再重新检查 spool 是否仍活跃。
- **影响**: 并发/取消/异常场景中，reader 可能抛出非预期的底层异常，调用方（`_SnapshotBinaryReader.read()` 行 126-136）未对此做特殊处理，异常会作为未分类错误向上传播，绕过 Doc 工具的错误分类与投影。
- **建议改法和验证点**:
  1. `close()` 在设置 `_spool = None` 前先获取 `self._lock`，确保没有 reader 正在临界区内。
  2. 或者 `_read_at()` 在 `spool.read()` 返回后验证 `self._spool` 仍是当前 spool（但 `SpooledTemporaryFile` 对象引用不变，无法通过 identity check 检测 close）。
  3. 更稳健方案：`close()` 持锁设置 `_spool = None`，然后在锁外调用 `spool.close()`；`_read_at()` 持锁检查并保存 spool 引用后执行 I/O，I/O 本身不在锁内但已确保持有有效引用。
  4. 建议增加并发 close+read 测试（`threading.Thread` 并发）。
- **修复风险（低）**: 当前生产路径均为单线程 context manager 使用，修复不影响正常路径；锁开销可忽略。
- **严重程度（中）**: 当前生产路径不会触发，但异步取消和多线程使用场景可能在后续演变中暴露；属于状态机并发安全不完整。

---

### R01-S1-DS-F02 — 中 — `SourceSnapshot.materialize()` 无协作取消检查，大文件物化无法响应取消

- **入口/函数**: `SourceSnapshot.materialize()`
- **文件(行号)**: `dayu/documents/processors/source_snapshot.py:341-381`
- **输入场景**: 一个大文件（例如 >100 MiB）已被完整复制到 spool。调用方在 `materialize()` 执行期间请求取消。由于 `materialize()` 内部不调用 `_check_cancellation()`，取消信号在整个物化期间被忽略，直到写入完成或 I/O 失败。
- **实际分支**: `materialize()` 行 370-375 的 chunk 复制循环无取消检查。相比之下，`__enter__()` 行 285-293 的 chunk 复制循环每 64 KiB 调用一次 `_check_cancellation()`。
- **预期行为**: `materialize()` 应在 chunk 复制循环中周期性调用 `_check_cancellation()`，与 `__enter__()` 一致。
- **实际行为**: 取消信号在 `materialize()` 执行期间被忽略。
- **直接证据**: `materialize()` 行 370-375 为纯 `while True: chunk = reader.read(...); if not chunk: break; output.write(chunk)`，无 `_check_cancellation()` 调用；行 285-293 的 `__enter__()` 循环中 `self._check_cancellation()` 被调用两次（循环前一次、每次迭代一次）。
- **影响**: 大文件场景下，Host 取消请求被延迟到 `materialize()` 完成后才生效，违反协作取消契约。
- **建议改法和验证点**:
  1. 在 `materialize()` 的 chunk 复制循环中（行 370-375），每次迭代后添加 `self._check_cancellation()`。
  2. 由于 `materialize()` 不在 `try/except BaseException` 的保护下（它假设调用方在 context manager 内调用），取消异常会穿透到 consumer 并由 `__exit__` 清理——行为与设计一致。
  3. 增加 `materialize()` 取消测试：给 snapshot 传入 `_CancelAfterChecks(N)`，在循环中触发取消，验证异常透出且物化临时文件被清理。
- **修复风险（低）**: 仅在循环中增加一次函数调用；`_check_cancellation()` 内部只做 None check + call，热路径开销可忽略。
- **严重程度（中）**: 大文件场景下取消响应延迟可能长达数秒至数十秒，违反 Doc 工具协作取消契约。

---

### R01-S1-DS-F03 — 低 — 空 source（0 bytes）行为未测试，snapshot_size=0 时 reader/materialize 语义未验证

- **入口/函数**: `SourceSnapshot.__enter__()` / `_SnapshotBinaryReader` / `materialize()`
- **文件(行号)**: `dayu/documents/processors/source_snapshot.py:260-300`（`__enter__`）、`92-118`（seek）、`120-136`（read）、`341-381`（materialize）
- **输入场景**: Source 流返回 0 字节（空文件）。
- **实际分支**: `__enter__()` 行 290 第一次 `read()` 返回 `b""`，跳过循环体，`copied = 0`，行 296 `self._snapshot_size = 0`。snapshot 进入 active 状态，`snapshot_size = 0`。
- **预期行为**: (a) `content_length` 返回 0（active 后应是精确值）；(b) `open()` 返回可读 reader；(c) reader `read()` 返回 `b""`；(d) reader `seek(0, SEEK_END)` → `position = 0 + 0 = 0`（通过）；(e) `materialize()` 创建空临时文件或返回已有路径；(f) `__exit__` 正常清理。
- **实际行为**: 代码路径分析表明行为正确，但无测试验证。
- **直接证据**: 代码逻辑走读确认 `copied = 0` 路径可达且 clean——`spool.seek(0)` 后 spool 为空，reader 在 spool 上 `read()` 返回 `b""`。但 `tests/documents/test_processors.py` 中无 `payload=b""` 的测试用例。最小 payload 为 `b"# Overview\n"`（~12 bytes）和 `b"0123456789" * 20_000`（~200 KiB）。
- **影响**: 空文件是合法财报输入场景（例如空白 notes 文件），虽然当前行为正确，但缺少回归保护。
- **建议改法和验证点**: 增加 `test_source_snapshot_empty_source`：验证 snapshot_size=0、reader 可打开、reader.read() 返回 b""、reader.seek(0, SEEK_END)=0、content_length=0（active 后）。
- **修复风险（低）**: 仅新增测试，不改变生产代码。
- **严重程度（低）**: 当前行为正确，缺少边界测试而非功能缺陷。

---

### R01-S1-DS-F04 — 低 — `source.open()` 自身 OSError 未测试，现有测试只覆盖 stream read 失败

- **入口/函数**: `SourceSnapshot.__enter__()`
- **文件(行号)**: `dayu/documents/processors/source_snapshot.py:286`（`self._source.open()` 调用点）
- **输入场景**: `Source.open()` 在 `__enter__()` 内部抛出 OSError（例如本地文件在路径校验后被删除、权限撤销）。
- **实际分支**: `self._spool` 在行 282 已赋值（在 `try` 块之前），若 `source.open()` 行 286 抛出，进入 `except BaseException` → `self.close()`（行 298-299），close 清理已创建但未写入的 spool，然后重新抛出 OSError。
- **预期行为**: spool 被正确关闭，异常原样透出。行为正确但无测试。
- **实际行为**: 代码路径分析确认正确，`close()` 会调用 `spool.close()` 清理未写入的 `SpooledTemporaryFile`。
- **直接证据**: 行 282 的 `self._spool = spool` 在 `try` 块（行 284）之前执行，若行 286 抛出 OSError，行 298-299 的 `except BaseException` handler 调用 `self.close()`。现有测试 `test_source_snapshot_closes_spool_on_io_failure_or_cancellation` 的 `_FailingSource` 只在 `open()` 返回的流的 `read()` 上失败，不测试 `open()` 自身失败。
- **影响**: `LocalFileSource.open()` → `path.open("rb")` 在 TOCTOU 场景下可能抛出 `FileNotFoundError`，当前没有测试保证 spool 清理。
- **建议改法和验证点**: 增加 `_FailingOpenSource` 测试 fixture（`open()` 直接 `raise OSError`），验证 spool 被关闭且异常透出。
- **修复风险（低）**: 仅新增测试。
- **严重程度（低）**: 行为正确但缺少回归保护。

---

### R01-S1-DS-F05 — 低 — `materialize()` 中 I/O 写入失败（磁盘满、权限）未测试，partial file 清理和异常传播未验证

- **入口/函数**: `SourceSnapshot.materialize()`
- **文件(行号)**: `dayu/documents/processors/source_snapshot.py:370-381`
- **输入场景**: `materialize()` 的 `output.write(chunk)`（行 375）因磁盘满或权限错误抛出 OSError。
- **实际分支**: `NamedTemporaryFile` context manager 退出（`delete=False` 不自动删除），进入 `except BaseException`（行 378），`temp_path.unlink(missing_ok=True)`（行 380）删除部分写入的临时文件，重新抛出异常。
- **预期行为**: 部分写入文件被删除，异常透出。行为正确但无测试。
- **实际行为**: 代码逻辑正确——`delete=False` 时 `NamedTemporaryFile.__exit__` 不删除文件，但 `except` 块显式 unlink。
- **直接证据**: 行 363-368 的 `NamedTemporaryFile(delete=False)` 不会在 context manager 退出时自动删除；行 378-381 的 `except BaseException` handler 调用 `temp_path.unlink(missing_ok=True)`。无测试覆盖此路径。
- **影响**: 缺少回归保护。
- **建议改法和验证点**: 增加 monkeypatch 测试：替换 `output.write` 为 `raise OSError`，验证 partial file 不存在且异常透出。
- **修复风险（低）**: 仅新增测试。
- **严重程度（低）**: 行为正确但缺少回归保护。

---

### R01-S1-DS-F06 — 低 — spool disk-spill 路径（>1 MiB payload）未测试

- **入口/函数**: `SourceSnapshot.__enter__()` / `_read_at()` / `materialize()`
- **文件(行号)**: `dayu/documents/processors/source_snapshot.py:22`（`_SPOOL_MEMORY_BYTES = 1024 * 1024`）、`278-280`（spool 创建）
- **输入场景**: Source payload 超过 1 MiB，`SpooledTemporaryFile` 从内存回退到磁盘临时文件。
- **实际分支**: `SpooledTemporaryFile(max_size=_SPOOL_MEMORY_BYTES)` 自动管理回退——超过阈值时内部将数据写入磁盘临时文件。
- **预期行为**: 所有 `seek()`/`read()`/`open()`/`materialize()` 操作对内存和磁盘 spool 透明。
- **实际行为**: `SpooledTemporaryFile` 的磁盘模式是其核心设计保证，行为应与内存模式一致。但无测试验证大文件场景下 seek、read、cursor 独立性和 materialize 正确性。
- **直接证据**: 最大测试 payload 为 `b"0123456789" * 20_000` ≈ 200 KiB（`test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors`），未触及 1 MiB 阈值。`_SPOOL_MEMORY_BYTES = 1024 * 1024`（行 22）是磁盘回退阈值。
- **影响**: `SpooledTemporaryFile` 是标准库组件，磁盘回退可靠性高；但缺少对项目特定使用模式（独立 cursor、seek、materialize 二次复制）在磁盘模式下的回归保护。
- **建议改法和验证点**: 增加 `test_source_snapshot_disk_spill_large_source`：构造 >2 MiB payload，验证 snapshot_size 精确、两个独立 cursor 读写正确、materialize 产物与原始 payload 一致。
- **修复风险（低）**: 仅新增测试，但测试执行时间可能增加（大文件 I/O）。
- **严重程度（低）**: 标准库组件可靠性高，缺少边界测试而非功能缺陷。

---

### R01-S1-DS-F07 — 低 — `_SnapshotBinaryReader.seek()` 非法 whence（非 0/1/2）和负 seek 位置的测试缺失

- **入口/函数**: `_SnapshotBinaryReader.seek()`
- **文件(行号)**: `dayu/documents/processors/source_snapshot.py:92-118`
- **输入场景**: (a) `seek(0, whence=3)`——非法 whence 值；(b) `seek(-100, SEEK_SET)`——负绝对位置。
- **实际分支**: (a) 行 113 → `raise ValueError(f"unsupported whence: {whence}")`；(b) 行 115-116 → `raise ValueError("negative seek position")`。
- **预期行为**: 两者均应抛出 ValueError。行为确认正确但无测试。
- **实际行为**: 代码逻辑正确。但现有测试中 `seek()` 仅覆盖 `SEEK_END`（行 131 `seek(-10, io.SEEK_END)`）和默认 `SEEK_SET`（隐式）。
- **直接证据**: 行 107-113 的 whence 分支，行 115-116 的负位置检查。无对应测试 node。
- **影响**: 缺少回归保护，但与 `RawIOBase` 标准契约一致。
- **建议改法和验证点**: 增加 `test_snapshot_reader_seek_rejects_invalid_whence` 和 `test_snapshot_reader_seek_rejects_negative_position`。
- **修复风险（低）**: 仅新增测试。
- **严重程度（低）**: 行为正确但缺少回归保护。

---

### R01-S1-DS-F08 — 低 — `test_doc_tool_descriptions_explain_retained_partial_fields` 中 search description 使用精确字符串 `==` 断言，任何 LLM-facing 文本调整都会破坏测试

- **入口/函数**: `test_doc_tool_descriptions_explain_retained_partial_fields()`
- **文件(行号)**: `tests/tools/test_doc_tools_provider.py:1232-1242`
- **输入场景**: 未来任一维护者修改 search_files 的 LLM-facing 描述文本（例如改进措辞、增加标点、调整语序），改动完全在语义上等价但字符串不匹配。
- **实际分支**: 测试行 1238-1242 使用 `assert search_description == (精确中文字符串)`，包含完整中文描述共三段。
- **预期行为**: 测试应验证关键语义元素的存在（如已有 `"result_limit" in search_description` 和 `"directory_entry_limit" in search_description`），而非完整字符串精确匹配。
- **实际行为**: 测试已经做了语义元素检查（行 1234-1235），精确字符串断言是冗余的过度约束。
- **直接证据**: 行 1238-1242 的 `assert search_description == (...)`——如果描述文本中任何一个字、标点或换行变化，测试失败，即使 LLM-facing 语义未变。
- **影响**: 未来 LLM-facing 描述改进（例如 S2 删除 directory entry 引导文本）时需要同时修改测试的精确字符串，增加不必要的维护成本。但项目 `CLAUDE.md` LLM-facing 文本约束要求精确控制 LLM 输入——此断言可被视为对 LLM-facing contract 的强保护。两者存在张力。
- **建议改法和验证点**: (a) 保留当前断言，接受其作为 LLM-facing contract lock-in 的代价；(b) 或改为关键子串集合断言（`"result_limit"`, `"directory_entry_limit"`, `"scan_complete"`, `"matches"`, `"scanned_entries"` 都必须存在，但允许措辞变化）。由 controller 裁决，本 finding 标记为 informational。
- **修复风险（低）**: 仅修改测试断言策略。
- **严重程度（低）**: 不影响 correctness，影响可维护性。按项目 LLM-facing 文本约束，保留精确断言也有其合理性。

---

### R01-S1-DS-P01 — 逐项 pass 确认：SourceSnapshot 状态机主路径

以下 SourceSnapshot 状态机路径经逐行走读确认正确：

| 检查项 | 入口/行号 | 结论 |
|---|---|---|
| 单次 `Source.open()` 调用 | `__enter__:286` — 仅在 `with self._source.open() as source_stream:` 中调用一次 | **PASS** — `open_count` 测试（`test_processors.py:136`）在 active snapshot 上下文结束后断言 `source.open_count == 1` |
| 复制到真实 EOF（非 byte limit） | `__enter__:287-293` — `while True: chunk = source_stream.read(_COPY_CHUNK_BYTES); if not chunk: break` | **PASS** — 无 byte limit 逻辑，纯 EOF 循环 |
| declared `content_length` 不作拒绝依据 | `content_length` property `:222-224` — active 后返回 `_snapshot_size`，active 前返回 `_source.content_length`；`__enter__` 不使用 `content_length` 做任何判断 | **PASS** — 测试 `test_source_snapshot_ignores_declared_length_and_feeds_processor` 验证 declared_length=payload×100000 时不拒绝 |
| active 后 `content_length` = 精确值 | `content_length:222-223` — `if self._snapshot_size is not None: return self._snapshot_size` | **PASS** — 测试 `test_source_snapshot_ignores_declared_length_and_feeds_processor` 行 61-62 断言 active 前后 content_length 变化 |
| 独立 cursor 不共享位置 | `_SnapshotBinaryReader` 各自维护 `_position`；`_read_at` 持锁 seek+read 后释放 | **PASS** — 测试 `test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors` 行 132-135 验证两个 cursor 独立 tell/seek/read |
| 单次进入拒绝 | `__enter__:275-276` — `if self._entered: raise RuntimeError(...)` | **PASS** — 测试行 139 验证 |
| 幂等 close | `close()` 设置所有状态为 None，重复调用无害 | **PASS** — 测试行 141-142 验证两次 `snapshot.close()` 不抛异常 |
| 单 materialized path 复用 | `materialize:359-360` — `if self._materialized_path is not None: return self._materialized_path` | **PASS** — 测试 `test_source_snapshot_cleans_materialized_file_on_normal_exit` 行 150 验证 `.materialize(".txt") == materialized_path` |
| 异常路径中 spool+materialized file 清理 | `__enter__:298-299` — `except BaseException: self.close(); raise`; `close:396-410` — unlink materialized + close spool | **PASS** — 测试覆盖 consumer exception（`test_source_snapshot_cleans_materialized_file_after_python_exception`）和 I/O failure/cancellation（`test_source_snapshot_closes_spool_on_io_failure_or_cancellation`） |
| reader 在 close 后 open 被拒 | `open:338` — `self.snapshot_size` → `ValueError("not active")` | **PASS** — 测试行 137-138 验证 |
| `Source.content_length` 仅作 metadata 透传 | `content_length:222-224` — 只在 active 前返回 source 声明值，active 后返回精确值；`__enter__` 不使用 `content_length` 做任何控制流决策 | **PASS** — `content_length` 不在 `__enter__` 的 if/while/raise 条件中 |
| 模块零反向依赖 | import 仅 `标准库` + `.source` | **PASS** — `test_documents_do_not_import_forbidden_layers` 通过 |
| materialized prefix 更新 | `_MATERIALIZED_PREFIX = "dayu-doc-source-"` | **PASS** — 测试 `test_source_snapshot_cleans_materialized_file_after_python_exception` 行 127 验证 `materialized_path.name.startswith("dayu-doc-source-")` |
| `snapshot_size` 在 active 前/close 后抛 ValueError | `snapshot_size:256-257` — `if self._spool is None or self._snapshot_size is None: raise ValueError(...)` | **PASS** — `snapshot.open()` 间接验证（行 338 调用 `self.snapshot_size`） |

---

### R01-S1-DS-P02 — 逐项 pass 确认：Doc tools consumer 链

以下 consumer 链检查项经逐行走读确认：

| 检查项 | 入口/行号 | 结论 |
|---|---|---|
| `_DocProcessTarget` 不含 `resource_budget` | `doc_tools.py:403-407` — fields: `tool_name`, `arguments`, `allowed_root_locators`, `limits`, `timeout_seconds` | **PASS** — `resource_budget` 已删除 |
| `_DocProcessTargetFactory` 不含 `resource_budget` | `doc_tools.py:449-496` — fields: `allowed_root_locators`, `limits` | **PASS** — `resource_budget` 已删除 |
| `build_doc_tool_definitions` 不创建 `DocResourceBudget` | `doc_tools.py:558-588` — 直接创建 `_DocProcessTargetFactory`，无 budget 对象 | **PASS** — 行 560-562 仅 `allowed_root_locators` + `limits` |
| 五个 `_build_*_definition` 不传递 `resource_budget` | `doc_tools.py:617-930` — 所有 definition builder 签名和调用均不含 `resource_budget` | **PASS** |
| `_execute_doc_business_value` 不含 `resource_budget` | `doc_tools.py:1050-1057` — params: `tool_name`, `call`, `parameters`, `allowed_roots`, `limits`, `cancellation_token` | **PASS** |
| `_route_doc_business` 不含 `resource_budget` | `doc_tools.py:1142-1148` — params: `tool_name`, `arguments`, `allowed_roots`, `limits`, `cancellation_token` | **PASS** |
| `get_file_sections` 不含 `max_source_bytes` | `doc_tools.py:1507-1512` — params: `file_path`, `limit`, `max_sections`, `cancellation_token` | **PASS** |
| `read_file` 不含 `max_source_bytes` | `doc_tools.py:1690-1696` — params: `file_path`, `start_line`, `end_line`, `max_chars`, `cancellation_token` | **PASS** |
| `read_file_section` 不含 `max_source_bytes` | `doc_tools.py:1751-1756` — params: `file_path`, `ref`, `max_chars`, `cancellation_token` | **PASS** |
| `search_files` 不含 `max_source_bytes` | `doc_tools.py:1562-1571` — params: `directory`, `query`, `include_types`, `limit`, `max_results`, `max_directory_entries`, `allowed_roots`, `cancellation_token` | **PASS** — `max_source_bytes` 已删除 |
| `SourceBudgetExceeded` catch 块已删除 | 旧 `_execute_doc_business_value` 中 `except SourceBudgetExceeded as error:` 块已完全删除 | **PASS** — source scan 零命中确认 |
| search 不再有 oversized skip/counter/result 字段 | `_search_files_business:1598-1660` — 无 `skipped_oversized_files` 变量或字段，无 `source_limit` 原因，无 `SourceBudgetExceeded` try/except | **PASS** — 测试 `test_search_files_complete_source_enters_processor_and_returns_match` 行 1114-1120 验证结果 key 集合不含 `skipped_oversized_files` |
| search LLM-facing 描述不含 source cap 引导 | `_build_search_files_definition:791-796` — description 仅提及 `result_limit` 和 `directory_entry_limit` | **PASS** — 测试 `test_doc_tool_descriptions_explain_retained_partial_fields` 验证精确描述字符串 |
| 五工具 `with _source_snapshot(...) as snapshot:` 模式一致 | `doc_tools.py:1532`, `1622`, `1728`, `1776` — 四处调用均为 `with _source_snapshot(path, cancellation_token) as snapshot:` | **PASS** |
| `_DocProcessCancellationToken` 语义不变 | `doc_tools.py:330-381` — 永不取消 token，仅在 process target 中使用 | **PASS** — 未修改 |
| `_DocSourceCancellationCheck` 语义不变 | `doc_tools.py:114-130` — 将 CancellationToken 投影为无参 callable | **PASS** — 未修改 |
| process target 序列化不含 live object | `_DocProcessTarget` fields 为 `str`, `dict`, `tuple`, `DocToolLimits`, `float | None` | **PASS** — 测试验证 pickle round-trip 且 repr 不含 `provider_lock`, `DocumentProcessor`, `CancellationToken` |
| `_invoke_doc_business` 错误分类不变 | `doc_tools.py:948-1047` — `_DocBusinessFailure`, `_DocCancelledError`, `_DocToolArgumentError`, `_DocFileAccessError` 分类保持不变 | **PASS** — 仅删除了 `SourceBudgetExceeded` catch 路径（该异常类本身已删除） |

---

### R01-S1-DS-P03 — 逐项 pass 确认：S1 机械保留 directory cap，无新 seam

| 检查项 | 入口/行号 | 结论 |
|---|---|---|
| `_DOC_DIRECTORY_MAX_ENTRIES` 直接传递到 list/search | `doc_tools.py:1176`, `1193` — `max_directory_entries=_DOC_DIRECTORY_MAX_ENTRIES` | **PASS** — 无 wrapper/validator/assertion/dataclass |
| `_DOC_DIRECTORY_MAX_ENTRIES` 定义不变 | `doc_tools.py:84` — `_DOC_DIRECTORY_MAX_ENTRIES: Final[int] = 10_000` | **PASS** |
| `list_files` directory cap 行为不变 | `_list_files_business:1461` — `if scanned_entries >= max_directory_entries: scan_complete = False; break` | **PASS** |
| `search_files` directory cap 行为不变 | `_search_files_business:1605` — `if scanned_entries >= max_directory_entries: scan_complete = False; truncated_reason = "directory_entry_limit"; break` | **PASS** |
| directory cap 相关测试保留 | `test_list_files_directory_entry_limit_returns_self_describing_partial`, `test_search_files_directory_entry_limit_returns_directory_partial` | **PASS** |

---

### R01-S1-DS-P04 — 逐项 pass 确认：symlink/containment 边界未改变

| 检查项 | 入口/行号 | 结论 |
|---|---|---|
| `list_files` 不使用 `_resolve_search_files_candidate` | `_list_files_business:1450` — `if not file_path.is_file(): continue`（不验证 entry containment） | **PASS** — 与 accepted plan R01-PF-01 一致：list 保持 directory-entry 语义，不添加 containment |
| `search_files` 使用 `_resolve_search_files_candidate` | `_search_files_business:1612-1615` — `resolved_file = _resolve_search_files_candidate(file_path=file_path, allowed_roots=allowed_roots)` | **PASS** — `_resolve_search_files_candidate` 行 1663-1687 仍做 `resolve(strict=True)` + containment re-check，未改变 |
| direct read 使用 `_project_doc_paths` | `_execute_doc_business_value:1085-1090` — `_project_doc_paths()` 在路由前校验所有路径参数 | **PASS** — `_project_doc_paths` 行 1310 使用 `.resolve(strict=False)` + `_is_relative_to` containment check，未改变 |
| symlink containment 测试保留 | `test_search_files_does_not_read_symlink_escape` — 符号链接逃逸返回空 matches | **PASS** |
| 无新增 containment 策略 | 无新增 `_resolve_search_files_candidate` 调用、无新增 `_is_relative_to` 调用、无新增 path resolve 逻辑 | **PASS** |

---

### R01-S1-DS-P05 — 逐项 pass 确认：cancellation/fencing/output 边界未改变

| 检查项 | 入口/行号 | 结论 |
|---|---|---|
| `_raise_if_doc_cancelled` 仍存在 | `doc_tools.py:2539-2569` | **PASS** — 所有 cancellation check 调用点不变 |
| `_DOC_LOOP_CANCELLATION_CHECK_INTERVAL` 不变 | `doc_tools.py:83` — `= 1_000` | **PASS** |
| process-backed execution 不变 | `_tool_definition` 行 2655 — `ProcessBackedToolExecutionCapability` 仍用于所有五工具 | **PASS** |
| `_DocProcessCancellationToken` 不变 | `doc_tools.py:330-381` — 永不取消 stub | **PASS** |
| `_invoke_doc_business` cancellation 分类不变 | 行 979-983 — pre-lock + post-lock cancellation check | **PASS** |
| `ToolTruncateSpec` 仅用于 read_file / read_file_section | `_build_read_file_definition:872`, `_build_read_file_section_definition:943` — `truncate=_text_content_truncate(...)`；其他三个工具 `truncate=None` | **PASS** |
| `_text_content_truncate` 不变 | `doc_tools.py:2863-2883` | **PASS** |
| `fetch_more` 无 Doc business tool | `test_no_old_fetch_more_business_tool` 仍通过 | **PASS** — `fetch_more` 未在 S1 创建或修改 |
| search `result_limit` 不变 | `_search_files_business:1645-1648` — `if len(matches) >= actual_limit: scan_complete = False; truncated_reason = "result_limit"; break` | **PASS** |
| cancellation tests 全部通过 | 7 个 cancellation 相关测试：pre-cancel (x5)、in-flight cancel (x6)、governed ToolRuntime cancel (x2) | **PASS** — 75 passed |

---

### R01-S1-DS-P06 — 测试迁移 75 vs 83 nodes 逐项确认

| 检查项 | 证据 | 结论 |
|---|---|---|
| 删除节点数: 8 | baseline 83 → 当前 75 | **PASS** |
| 删除原因: 旧 budget contract 测试 | 删除的测试只固化已删除的 `BoundedSourceSnapshot`, `SourceBudgetExceeded`, `DocResourceBudget` contract | **PASS** |
| 替换对照 | 旧 `test_bounded_source_snapshot_enforces_actual_stream_limit_plus_one` → 新 `test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors`；旧 `test_bounded_source_snapshot_accepts_exact_limit_and_feeds_processor` → 新 `test_source_snapshot_ignores_declared_length_and_feeds_processor`；旧 `test_bounded_source_snapshot_rejects_invalid_byte_limit` (parametrized x3) → 删除（max_bytes 概念已不存在）；旧 `test_doc_resource_budget_rejects_non_positive_or_bool_limits` (parametrized x4) → 删除（DocResourceBudget 已删除）；旧 `test_read_file_source_limit_plus_one_raises_typed_resource_failure` → 新 `test_read_file_reads_complete_source_without_source_byte_limit`；旧 `test_search_files_source_limit_skips_oversized_processor_input_without_fallback` → 新 `test_search_files_complete_source_enters_processor_and_returns_match` | **PASS** — 3+4+1+1 = 9 nodes 被移除（有重叠），新增测试覆盖新 contract |
| 无遗漏的 failure path | 旧 `SourceBudgetExceeded` 异常路径已随异常类一起删除——没有 consumer 需要再处理它 | **PASS** |
| 无 `hasattr`/`getattr` | 三个测试文件零命中 | **PASS** |
| process target 字段精确断言 | `test_doc_process_target_factory_is_pickle_round_trippable` 验证字段 tuple = `("tool_name", "arguments", "allowed_root_locators", "limits", "timeout_seconds")` | **PASS** |

---

### R01-S1-DS-P07 — 逐项 pass 确认：allowlist / README / pyright / S1-S2 边界

| 检查项 | 证据 | 结论 |
|---|---|---|
| Diff 仅含 6 个 allowlist 文件 + 1 control doc | `git diff --stat 1b4e5d33` 显示 6 文件，无其他 tracked 文件变更 | **PASS** |
| 无 README 修改 | `tests/README.md` 不在 diff 中 | **PASS** — 符合 accepted plan §13.1：S1 不写中间态 README，S2 统一更新 |
| pyright 零错误 | `0 errors, 0 warnings, 0 informations` | **PASS** |
| `ruff check` 通过 | controller validation 已确认 | **PASS** |
| `git diff --check` 通过 | controller validation 已确认 | **PASS** |
| 无 S2 代码 | 无 directory cap 删除、无 `_DOC_DIRECTORY_MAX_ENTRIES` 新抽象、无 deterministic iterator、无 `list_files` scan_complete/truncated_reason 删除 | **PASS** |
| 无 Issue 177 代码 | 无 `TruncationManager` wiring、无新 `ToolTruncateSpec`、无 `fetch_more` 业务工具 | **PASS** |
| 无 unified tool authorization | 无新 authorization framework、无跨工具统一 containment wrapper | **PASS** |
| 无 control/design doc 修改 | `docs/host/issues-implementation-control.md` 仅更新 gate status 文本（行 158, 188, 194），无设计决策变更 | **PASS** |
| `DocResourceBudget` 源码扫描零命中 | `rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit' dayu tests README.md` → exit 1 | **PASS** |
| `bounded_source` 源码扫描零命中 | `rg -n 'bounded_source|BoundedSourceSnapshot|dayu-doc-bounded' dayu tests` → exit 1 | **PASS** |

---

## Open Questions

1. **OQ-1**: `SourceSnapshot.materialize()` 的取消缺口（R01-S1-DS-F02）在当前生产路径是否可触发？当前 `materialize()` 仅由 `create_doc_file_processor()` 间接调用（通过 `source.materialize()`），而 processor factory 只在 get-sections 和 search 的工具调用中使用。如果这些工具处理超大文件，取消延迟可达数秒。但 `create_doc_file_processor()` 实际调用 `SourceSnapshot.materialize()` 吗？——需要验证 `_doc_processor_factory.py:77` 的 `source.materialize()` 调用是否实际走到 `SourceSnapshot.materialize()` 的 chunk 复制循环。从 type 角度看，`SourceSnapshot` 实现了 `Source` 协议的 `materialize(suffix)`——但 `_try_create_processor` 传来的 `source` 参数类型是 `Source`（Protocol），`create_doc_file_processor` 调用 `source.materialize()`，而 `SourceSnapshot.materialize()` 确实会被调用。因此 OQ 答案是 **是的，可触发**。但当前 `_doc_processor_factory.py` 中 `create_doc_file_processor` 行的 `source.materialize()` 调用后是否还有其他代码路径？——已确认 `create_doc_file_processor` 在 line 77 调用 `source.materialize()`，然后基于返回的 Path 的 suffix 选择 processor。该 materialize 调用在 snapshot active context 内执行，取消无法响应——**这是真实可触发的缺口**。

2. **OQ-2**: 当前 `_DOC_DIRECTORY_MAX_ENTRIES` 值为 10,000——S2 删除此常量和对应参数后，list 和 search 的 `max_directory_entries` 行为变更是否需要在 S2 之前做 smoke test？Accepted plan 提到 S2 引入 deterministic iterator 替代 `rglob/iterdir` + counter——此变更是 S2 的独立合约，S1 不前置。但 R01-S1-DS-F02 的 materialize 取消缺口在 S2 之前可能一直存在。

## Residual Risk

| 风险区域 | 分类 | 处置 |
|---|---|---|
| materialize() 取消缺口（F02） | S1 可在本 slice 修复 | 建议修复后进入 re-review |
| _read_at/close 并发不安全（F01） | S1 可在本 slice 修复 | 当前单线程使用安全，可 defer 但建议记录 |
| 空 source / disk-spill / open() 失败 / materialize I/O 失败无测试（F03-F06） | 测试缺口 | 可在 S1 补充，或作为 R01-S2/R01 completion smoke 的一部分 |
| seek 边界测试缺失（F07） | 测试缺口 | 低优先级，标准 RawIOBase 契约已覆盖 |
| search description 精确字符串断言（F08） | 可维护性 | 由 controller 裁决是否调整断言策略 |
| >32 MiB / >10,000 entries 真实 smoke 未运行 | 已在 accepted plan 分类为 S2/R01 completion smoke | S1 不阻塞 |
| `tests/README.md` 中间态仍描述旧 source/directory contract | 已在 accepted plan 分类为 S2 终态迁移 | S1 不阻塞 |
| Issue 177（TruncationManager 完整 wiring） | 独立 Issue，不在 R01 scope | 不阻塞 |

---

## Verdict

**PASS** — 存在 2 个中等严重度 finding（F01 并发锁不完整、F02 materialize 无取消检查）和 6 个低严重度 finding（F03-F08 测试缺口 + 可维护性），均为可修复项。所有 accepted plan S1 contract 逐项验证通过：SourceSnapshot owner 正确、consumer chain clean、directory cap 机械保留无新 seam、symlink/containment/cancellation/fencing/output/ToolTruncateSpec/fetch_more 边界未改变、测试迁移合理、allowlist/README/pyright/S1-S2 边界正确。

建议 R01-S1-DS-F01 和 R01-S1-DS-F02 修复后进入双路 re-review；F03-F08 可由 controller 裁决 defer 到 R01-S2 或本 slice 补充。
