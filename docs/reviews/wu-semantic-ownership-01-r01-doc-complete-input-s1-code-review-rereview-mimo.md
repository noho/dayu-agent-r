# WU-SEMANTIC-OWNERSHIP-01 / R01-S1 修复后完整 Code Re-Review — MiMo 路

## Scope

- **Mode**: current changes（相对 slice base `1b4e5d33` 的完整 workspace diff，含 fix）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `1b4e5d33`（`docs: enter R01 source snapshot implementation`）
- **Accepted plan commit**: `54e35231`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-controller-adjudication.md`
- **Fix artifact**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-fix-codex.md`
- **Fix controller validation**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-fix-controller-validation.md`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-rereview-mimo.md`
- **Included scope**: 6 个 production/test tracked diff 文件 + 1 个 untracked `source_snapshot.py` + control doc 修改 + review/fix/验证 artifacts
- **Excluded scope**: 无；所有 diff 均在 accepted S1 allowlist 内
- **Parallel review coverage**: 无；本路为单 reviewer 完整走读

## Verification Baseline（独立重跑）

```text
pytest tests/documents/test_processors.py tests/documents/test_import_boundary.py tests/tools/test_doc_tools_provider.py -q
80 passed in 2.46s

python -m pyright
0 errors, 0 warnings, 0 informations

coverage run -m pytest tests/documents/test_processors.py -q
15 passed
coverage report --include='dayu/documents/processors/source_snapshot.py' --show-missing --fail-under=80
source_snapshot.py: 154 statements / 10 miss / 94%

ruff check source_snapshot.py doc_tools.py test_import_boundary.py test_processors.py test_doc_tools_provider.py
All checks passed!

git diff --check
EXIT=0

rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit' dayu tests README.md
EXIT=1（零命中）

rg -n 'bounded_source|BoundedSourceSnapshot|dayu-doc-bounded' dayu tests
EXIT=1（零命中）
```

---

## Findings

未发现实质性问题。

以下逐项证明 DS-F01 至 DS-F05 已闭合、测试 seam 最小性合理、S1/S2 边界正确、安全/取消/output owner 未改变、coverage/pyright/scans 通过。

---

### 1. DS-F01 闭合验证：`_read_at()` / `close()` 锁保护

**修复内容**: `close()`（`source_snapshot.py:412-420`）现在使用 `self._lock` 保护 spool detach 与实际 close。`_read_at()`（`source_snapshot.py:452-457`）在 `with self._lock:` 内执行 `spool.seek` + `spool.read`。

**锁覆盖分析**:

| 操作 | 临界区 | 锁内操作 |
|---|---|---|
| `_read_at()` | `with self._lock:` 行 452-457 | check `_spool is None` → `spool.seek` → `spool.read` → 返回 |
| `close()` | `with self._lock:` 行 412-420 | `spool = self._spool` → `_spool = None` → `_snapshot_size = None` → `spool.close()` |

**串行化保证**: 两个操作在同一把 `threading.Lock` 上互斥。已进入 `_read_at` 临界区的 `seek+read` 先完成；`close` 不会在其间关闭底层对象。`close` 返回后的新 `_read_at` 调用只观察到 `spool is None` → `ValueError("source snapshot is not active")`。

**测试验证**: `test_source_snapshot_close_serializes_inflight_read_and_actual_close`（`test_processors.py:315-357`）使用 `_ConcurrentSpoolProbe`：
1. monkeypatch `SpooledTemporaryFile` 为 probe（`__call__` 返回自身）
2. monkeypatch `snapshot._lock` 为 probe（probe 的 `__enter__`/`__exit__` 实现锁语义）
3. ThreadPoolExecutor 并发：线程 A 读取 → probe `read_entered` event 信号 → 线程 B close → probe `second_acquire_started` event 信号
4. 断言 `close_future.done() is False`（close 等待锁）+ `spool.closed is False`（spool 未提前关闭）
5. 放行 `allow_read` → read 完成 → close 完成
6. 断言 `close_under_owner_lock is True`（close 在 owner 锁内执行）+ `reader.read(1)` 抛出 `ValueError`

**结论**: **PASS** — 同一锁覆盖 read/detach/actual close；确定性并发测试无 sleep/概率竞争。

---

### 2. DS-F02 闭合验证：`materialize()` 取消检查

**修复内容**: `materialize()`（`source_snapshot.py:364-388`）在三个点调用 `_check_cancellation()`：
1. 输出创建前（行 364）
2. 每个复制迭代前（行 374）
3. `_materialized_path` 发布前（行 379）

**路径分析**: 取消异常穿透 `except BaseException`（行 382）→ `temp_path.unlink(missing_ok=True)` 删除 partial → 重新抛出。`__exit__` → `close()` 清理 spool。与 `__enter__` 的取消行为一致。

**测试验证**: `test_source_snapshot_materialize_observes_cancellation_and_cleans_resources`（`test_processors.py:506-585`）：
1. monkeypatch `_COPY_CHUNK_BYTES=4`（12 字节 payload → 3 次迭代）
2. monkeypatch `SpooledTemporaryFile` 为 `_SpoolRecorder`（观察 spool 关闭）
3. monkeypatch `tempfile.tempdir` 为 `tmp_path`（真实 `NamedTemporaryFile`）
4. 第三次物化检查时：断言 `tmp_path` 中有 1 个 `dayu-doc-source-*.partial` 且存在 → 抛取消
5. 断言取消异常身份 → partial 路径不存在 → spool 关闭

**结论**: **PASS** — materialize 全复制阶段复用 cancellation check；真实临时文件路径观察 partial 存在/删除；异常身份精确匹配。

---

### 3. DS-F03 闭合验证：空 source 边界

**测试**: `test_source_snapshot_empty_source_has_exact_eof_and_materialization`（`test_processors.py:360-385`）

**断言链**:
- `snapshot_size == 0` + `content_length == 0`
- `reader.read() == b""`
- `reader.seek(0, SEEK_END) == 0` + `reader.tell() == 0`
- `reader.read(1) == b""`（EOF 后再读仍为空）
- `materialize(suffix=".empty")` 返回路径 → `read_bytes() == b""`
- context 退出后 materialized path 不存在

**结论**: **PASS** — 零长度边界完整覆盖。

---

### 4. DS-F04 闭合验证：`Source.open()` OSError

**测试**: `test_source_snapshot_open_oserror_is_preserved_and_closes_spool`（`test_processors.py:588-616`）

**断言链**:
- `_FailingOpenSource(open_error)` → `open()` 直接 `raise self.error`
- `pytest.raises(OSError)` 断言 `raised.value is open_error`（同一实例身份）
- `_SpoolRecorder` → spool 已创建且 `spool.closed is True`

**路径**: `__enter__` 行 282 `self._spool = spool`（`try` 块前）→ 行 286 `self._source.open()` 抛出 → 行 298 `except BaseException: self.close(); raise` → close 清理 spool。

**结论**: **PASS** — open 失败同一实例透出 + spool 清理。

---

### 5. DS-F05 闭合验证：materialize 写入 OSError

**测试**: `test_source_snapshot_materialize_write_oserror_removes_partial_path`（`test_processors.py:619-651`）

**断言链**:
- `_FailingMaterializedOutput(partial_path, write_error)`: 打开固定路径 → 写入半截数据 → flush → 抛错
- monkeypatch `NamedTemporaryFile` 为该 double
- `pytest.raises(OSError)` 断言 `raised.value is write_error`（同一实例）
- `0 < output.bytes_written < len(payload)`（确认有 partial 写入）
- `not partial_path.exists()`（partial 被删除）

**路径**: `materialize` 行 378 `output.write(chunk)` 抛出 → 行 382 `except BaseException` → 行 383-387 `temp_path.unlink(missing_ok=True)` → 重新抛出。

**结论**: **PASS** — 写入失败同一实例透出 + partial 路径删除。

---

### 6. 测试 seam 最小性审查

controller validation 已确认首次 fix 的通用 test-double 层（`_ObservedLock`、`_BlockingReadSpool`、`_ArmableCancellationCheck`、`_MaterializedOutput`、`_MaterializedOutputFactory`）已全部删除。当前保留：

| 辅助 | 用途 | 最小性证明 |
|---|---|---|
| `_ConcurrentSpoolProbe` | F01 并发锁序列化 | 同时提供锁与 spool 观察点；去掉它只能退回 sleep/概率 race |
| `_FailingMaterializedOutput` | F05 写入失败 | 无成功模式、无策略字段、无配置；单一职责 |
| `_SpoolRecorder` | F02/F04 spool 观察 | 只记录一个 spool 实例的 factory |
| `_FailingOpenSource` | F04 open 失败 | 最小 Source double |
| `_CancelAfterChecks` | 既有的取消测试 | 未修改 |

`_MemorySource` 从 `frozen=True` 改为 `slots=True`（新增 `open_count` 字段），这是测试必要的可观察性。

`test_processors.py` 当前 930 行（fix 前约 1148 行），净增 359 行。没有 builder、协议、配置、可扩展策略或多层复用框架。

**结论**: **PASS** — 测试 seam 最小化，每个辅助对应不可由真实 I/O 构造的确定性观察点。

---

### 7. SourceSnapshot 状态机主路径完整复核

| 检查项 | 入口/行号 | 结论 |
|---|---|---|
| 单次 `Source.open()` 调用 | `__enter__:286` | **PASS** — `open_count` 测试验证 |
| 复制到真实 EOF | `__enter__:287-293` — `while True: chunk = read(...); if not chunk: break` | **PASS** — 无 byte limit |
| declared `content_length` 不作拒绝依据 | `__enter__` 不使用 `content_length` 做任何判断 | **PASS** — 测试验证 declared=100000×actual 不拒绝 |
| active 后 `content_length` = 精确值 | `content_length:222-223` | **PASS** |
| 独立 cursor | `_SnapshotBinaryReader` 各自 `_position` + `_read_at` 持锁 | **PASS** |
| 单次进入拒绝 | `__enter__:275-276` | **PASS** |
| 幂等 close | close 设置所有状态为 None | **PASS** |
| 单 materialized path 复用 | `materialize:359-360` | **PASS** |
| 异常路径 cleanup | `except BaseException: self.close(); raise` | **PASS** |
| close 后 open 被拒 | `open:338` → `snapshot_size` → ValueError | **PASS** |
| materialize 取消 | `materialize:364,374,379` 三次 `_check_cancellation` | **PASS** |
| materialize 写失败 cleanup | `except: temp_path.unlink(missing_ok=True); raise` | **PASS** |
| close 持锁保护 spool | `close:412-420` — `with self._lock:` 覆盖 detach + close | **PASS** |
| 模块零反向依赖 | import 仅标准库 + `.source` | **PASS** |

---

### 8. Doc tools consumer 链完整复核

| 检查项 | 证据 | 结论 |
|---|---|---|
| `DocResourceBudget` 完全删除 | class、`__post_init__`、所有引用均删除 | **PASS** |
| `_DOC_SOURCE_MAX_BYTES` 删除 | 常量删除 | **PASS** |
| `_DocProcessTarget` 不含 `resource_budget` | 测试精确字段断言 | **PASS** |
| `_DocProcessTargetFactory` 不含 `resource_budget` | 同上 | **PASS** |
| 五个 `_build_*_definition` 不传 `resource_budget` | diff 确认 | **PASS** |
| `_execute_doc_business_value` / `_route_doc_business` 不含 `resource_budget` | diff 确认 | **PASS** |
| `_source_snapshot` 替代 `_bounded_local_source` | 行 1815-1827 | **PASS** |
| `SourceBudgetExceeded` catch 块删除 | diff 确认 + source scan 零命中 | **PASS** |
| search 不再有 oversized skip/counter/result 字段 | `_search_files_business` 无 `skipped_oversized_files` | **PASS** |
| search LLM-facing 不含 source cap 引导 | description 只说 `result_limit` 和 `directory_entry_limit` | **PASS** |
| `_DOC_DIRECTORY_MAX_ENTRIES` 直接传递到 list/search | 行 1176、1193 | **PASS** — 无 wrapper/validator |
| `_invoke_doc_business` 错误分类不变 | 仅删除 `SourceBudgetExceeded` catch | **PASS** |

---

### 9. S1 机械保留 directory cap 复核

| 检查项 | 证据 | 结论 |
|---|---|---|
| `_DOC_DIRECTORY_MAX_ENTRIES = 10_000` 定义不变 | 行 84 | **PASS** |
| `_route_doc_business` 直接传常量 | 行 1176、1193 | **PASS** |
| list counter break 不变 | `_list_files_business:1461` | **PASS** |
| search counter break 不变 | `_search_files_business:1605` | **PASS** |
| directory partial 测试保留 | `test_list_files_directory_entry_limit_returns_self_describing_partial`、`test_search_files_directory_entry_limit_returns_directory_partial` | **PASS** |

---

### 10. 安全/取消/output owner 边界复核

| 检查项 | 证据 | 结论 |
|---|---|---|
| `allowed_paths` / `_project_doc_paths` | `_execute_doc_business_value:1085-1090` | **PASS** — 未改变 |
| `_resolve_search_files_candidate` | `_search_files_business:1612-1615` | **PASS** — 未改变 |
| `_raise_if_doc_cancelled` | 27 处调用，全部保留 | **PASS** |
| `ProcessBackedToolExecutionCapability` | 五工具定义中使用 | **PASS** |
| `ToolTruncateSpec` | 仅 `read_file` / `read_file_section` 使用 | **PASS** |
| `result_limit` partial | search 逻辑不变 | **PASS** |
| symlink containment 测试 | `test_search_files_does_not_read_symlink_escape` 保留 | **PASS** |
| cancellation 测试 | 7+ cancellation 相关测试全部通过 | **PASS** |
| process target 序列化 | pickle round-trip 测试通过，无 live object | **PASS** |

---

### 11. 测试迁移 80 vs 75+5 说明

- S1 初始: 75 passed（83 → 75，删除旧 budget 测试）
- Fix 新增: 5 passed（F01-F05 各一个确定性测试）
- 当前: 80 passed

新增 5 个测试覆盖 controller accepted 的 5 项 finding。无遗漏的 failure path。

---

### 12. allowlist / README / pyright / scans / S1-S2 边界

| 检查项 | 证据 | 结论 |
|---|---|---|
| Diff 仅含 6 个 allowlist 文件 + control doc | `git diff --name-only 1b4e5d33` | **PASS** |
| 无 README 修改 | `tests/README.md` 不在 diff | **PASS** |
| pyright 零错误 | `0 errors, 0 warnings` | **PASS** |
| ruff 通过 | `All checks passed!` | **PASS** |
| git diff --check 通过 | EXIT=0 | **PASS** |
| 删除语义 scan 零命中 | `DocResourceBudget|SourceBudgetExceeded|...` → exit 1 | **PASS** |
| 旧模块 scan 零命中 | `bounded_source|BoundedSourceSnapshot|...` → exit 1 | **PASS** |
| `scan_complete`/`truncated_reason` 只在 search/read 合法位置 | rg 命中确认只在 search result_limit、list/search directory_entry_limit、read/read-section output | **PASS** |
| LLM-facing rejected token scan | `source_limit|skipped_oversized_files|source_budget_exceeded|较小文件|拆分文件|缩小文件范围|缩小目录` → exit 1（零命中） | **PASS** |
| `directory_entry_limit` 命中 | 只在 list/search producer、tests、schema description — S1 accepted intermediate | **PASS** |
| 无 S2 代码 | 无 directory cap 删除、无 deterministic iterator | **PASS** |
| 无 Issue 177 代码 | 无 `TruncationManager` wiring | **PASS** |

---

### 13. coverage 逐文件

| changed production file | statements | miss | coverage | gate |
|---|---:|---:|---:|---|
| `source_snapshot.py` | 154 | 10 | 94% | `>=80%` PASS |
| `doc_tools.py` | (fix 未修改此文件) | — | — | S1 initial 80% PASS |

10 miss 行为 `SEEK_CUR` 分支（行 110）、`SEEK_END` 负位置分支（行 114、116）、`etag` property（行 240）、`materialize` unlink 抑制（行 386-387）、`close` materialized unlink 抑制（行 408-409）和 `close` spool close 抑制（行 419-420）——均为标准库 fallback 分支或 cleanup 抑制分支，不构成 owner-level contract gap。

---

## Open Questions

无。

## Residual Risk

| 风险区域 | 分类 | 处置 |
|---|---|---|
| S1 仍保留 10,000 directory entry cap、list/search directory partial 与相关 LLM 文本 | covered by later approved slice | R01-S2 |
| `tests/README.md` 仍描述旧 source/directory contract | covered by later approved slice | R01-S2 |
| >32 MiB / >10,000 entries 真实 smoke 未运行 | covered by later approved slice | R01-S2 / R01 completion |
| 五工具尚未完整接入 `TruncationManager` / framework remainder continuation | tracked by existing issue | GitHub Issue #177 |

---

## Verdict

**PASS** — DS-F01 至 DS-F05 均已在 `SourceSnapshot` owner 或其 owner tests 内闭合。同一 `self._lock` 覆盖 read/detach/actual close（F01）；`materialize()` 全复制阶段复用 `_check_cancellation()`（F02）；空 source、`Source.open()` OSError、materialize 写入 OSError 均有确定性 owner test（F03-F05）。测试 seam 已从首次 fix 的 1148 行收敛至 930 行，删除了通用 lock/spool/cancellation/output factory 层，只保留最小必要单用途辅助。S1/S2 边界、安全/取消/output owner、coverage/pyright/scans、allowlist/README 均通过。无 material finding。
