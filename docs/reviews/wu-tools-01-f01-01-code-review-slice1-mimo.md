# WU-TOOLS-01-F01-01 Code Review Slice 1 - MiMo

## Work unit / gate / slice

- Work unit: `WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock`
- Gate: `code review`
- Slice: `Slice 1 - Ingestion job store convergence`
- Reviewer: AgentMiMo
- Implementation artifact: `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md`

## Verdict

**pass-with-findings**

## Review scope

仅审查 Slice 1 未提交改动，未触碰 storage batch 或 `dayu/fins/_file_lock.py`。

Changed files (from `git diff HEAD`):

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/README.md`
- `docs/host/issues-implementation-control.md`（gate bookkeeping 更新）

## Findings

### F1 — 6 个公共方法 docstring `Raises` 仍声明 `OSError`，锁失败实际抛 `RuntimeFileLockError`

- severity: low
- file: `dayu/fins/ingestion_runtime.py` lines 698, 720, 751, 800, 838, 857
- impact: `create_job`、`save_job`、`save_succeeded_or_cancelled`、`claim_running_or_cancelled`、`read_job`、`request_cancel` 的 docstring `Raises` 均声明 `OSError: 文件系统写入失败时抛出` 或类似。替换 `_StoreFileLock` 后，锁 acquire 失败抛 `RuntimeFileLockError`（不继承 `OSError`）。调用方若按 docstring 只捕获 `OSError`，将漏过锁失败。`_read_record_locked` / `_write_record_locked` 的 `OSError` 仍正确。
- suggestion: 在各方法 `Raises` 中补充 `RuntimeFileLockError: 文件锁获取失败时抛出`（或等价措辞）。不改实现，只改 docstring。
- verdict: **accepted** — 低风险，文档准确性问题；不阻塞合并，可在后续 commit 修复。

### F2 — 未执行推荐的 coverage 命令

- severity: low
- file: `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md`
- impact: implementation artifact 未报告 `pytest --cov=dayu.fins.ingestion_runtime` 结果。计划 §10 推荐运行 coverage 以确认修改文件覆盖率 ≥ 80%。无法从 artifact 判断覆盖率是否退化。
- suggestion: 运行 `pytest tests/fins/test_fins_ingestion_runtime.py --cov=dayu.fins.ingestion_runtime --cov-report=term-missing -q` 并将结果补充到 implementation artifact 或作为 code review 验证。
- verdict: **accepted** — 推荐项而非强制项；当前行为测试通过，风险可控。

## Plan / slice conformance checklist

| 检查项 | 状态 | 证据 |
|---|---|---|
| 只完成 Slice 1，未触碰 storage batch 或 `_file_lock.py` | pass | `git diff HEAD` 只含 `ingestion_runtime.py`、`test_fins_ingestion_runtime.py`、`tests/README.md`、`issues-implementation-control.md`；`_file_lock.py` 未改动 |
| 6 个 `.store.lock` 临界区直接使用 `dayu.runtime.filelock.file_lock` | pass | `dayu/fins/ingestion_runtime.py:702,724,755,803,841,860` — 均为 `with file_lock(self.root_dir / _LOCK_FILE_NAME):` |
| 删除 `_StoreFileLock` 类 | pass | diff 显示删除 77 行（原 line 1945-2021）；当前文件 line 1940 后为 `_new_job_id`，无 `_StoreFileLock` 残留 |
| 删除 `fcntl` import | pass | `import fcntl` 已从 import block 移除；`rg` 无命中 |
| 删除 `_StoreFileLock` 测试 import 与测试用例 | pass | `from dayu.fins.ingestion_runtime import _StoreFileLock` 已删除；`test_store_file_lock_closes_stream_when_flock_fails` 已删除 |
| 未新增 Fins wrapper / facade / compatibility export | pass | 只 import `from dayu.runtime.filelock import file_lock`；无新增 `_fins_*` helper |
| job schema / 状态机 / 路径 / atomic replace / 读写顺序不变 | pass | `_read_record_locked`（line 889-909）和 `_write_record_locked`（line 911-941）代码无变化 |
| 删除旧 fd-close 测试合理 | pass | Fins 不再打开 lock `TextIO` / stream；fd 生命周期由 `dayu.runtime.filelock` + 第三方 `filelock` 管理；`tests/runtime/test_filelock.py` 已覆盖 context manager release 语义 |
| `tests/README.md` 更新符合测试事实 | pass | 已删除「文件锁失败关闭」短语；其余描述与当前测试覆盖一致 |
| 类型 / import boundary / 异常语义 | pass-with-findings | F1：docstring `Raises` 未更新为 `RuntimeFileLockError` |
| issues-implementation-control.md gate bookkeeping | pass | gate 已更新为 `code review`，implementation status 引用 implementation artifact；未越界 |

## Validation performed

| 验证命令 | 结果 |
|---|---|
| `pytest tests/fins/test_fins_ingestion_runtime.py -q` | **26 passed, 3 warnings** (edgar deprecation warnings only) |
| `pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` | **0 errors, 0 warnings, 0 informations** |
| `rg -n "_StoreFileLock\|import fcntl\|ingestion_runtime\.fcntl" dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` | **无命中** |
| `git diff --check HEAD` | **无 whitespace error** |
| 手动审读 `_read_record_locked`（line 889-909）和 `_write_record_locked`（line 911-941） | 代码无变化，atomic replace / fsync / tmp cleanup 逻辑完整 |
| 手动审读 `file_lock` context manager 行为（`dayu/runtime/filelock.py:182-215`） | `__enter__` acquire + `__exit__` release，异常路径 release；语义等价于原 `_StoreFileLock` |
| 手动审读 `file_lock` parent dir 创建（`dayu/runtime/filelock.py:263-284`） | `create_parent_dirs=True` 默认创建 parent directory；等价于原 `_StoreFileLock.__enter__` 的 `self._path.parent.mkdir(parents=True, exist_ok=True)` |

## Residual risks and uncovered areas

- **R1 (低)**: `RuntimeFileLockError` 不是 `OSError`。若存在外部调用方按 docstring 只捕获 `OSError`，锁失败将逃逸。当前 Fins job store 调用方均为 runtime 内部，风险可控。Owner: implementation agent，在后续 commit 补充 docstring。
- **R2 (低)**: implementation artifact 未运行 coverage 命令。无法确认 `ingestion_runtime.py` 覆盖率是否仍 ≥ 80%。Owner: code review / implementation。
- **Deferred**: storage batch convergence（Slice 2）和 `_file_lock.py` 删除（Slice 3）不在本 slice 范围内。

## Blocking open questions

无。
