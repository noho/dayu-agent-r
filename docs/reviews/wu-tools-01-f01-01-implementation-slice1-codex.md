# WU-TOOLS-01-F01-01 Implementation Slice 1 - Codex

## Work unit / gate / slice

- Work unit: `WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock`
- Gate: `implementation`
- Slice: `Slice 1 - Ingestion job store convergence`
- Accepted plan commit: `c20ac977`

## Files changed

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/README.md`

## Implementation summary

- `FsFinsIngestionJobStore` 的 6 个 `.store.lock` 临界区已从私有 `_StoreFileLock` 替换为直接使用 `dayu.runtime.filelock.file_lock(self.root_dir / _LOCK_FILE_NAME)`。
- 删除了 `dayu/fins/ingestion_runtime.py` 中的 `import fcntl`、`_StoreFileLock` 类、`TracebackType` 与 `TextIO` 相关 import。
- 未修改 `_read_record_locked`、`_write_record_locked`、临时文件写入、`os.replace` atomic replace、目录 fsync、job JSON schema、状态机、job path 或读写顺序。
- 未新增 Fins wrapper / facade；Fins 直接依赖 runtime filelock 公共 context manager。

## Tests changed

- 删除 `tests/fins/test_fins_ingestion_runtime.py` 对 `_StoreFileLock` 的 import。
- 删除旧 `test_store_file_lock_closes_stream_when_flock_fails`。
- 该删除不是覆盖缺口：Fins ingestion job store 不再打开 lock `TextIO` / stream，也不再直接管理 fd lifecycle；lock acquire / release 与底层文件描述符生命周期由 `dayu.runtime.filelock` 及第三方 `filelock` 管理。runtime filelock 已在 `tests/runtime/test_filelock.py` 覆盖 context manager 正常与异常路径 release、release 幂等和 timeout 包装。
- 保留 job store atomic replace failure cleanup 测试，继续覆盖临界区内写入失败后的临时文件清理。

## README decision

- 已读取 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`。本 slice 不改变 Fins capability 定位、公共契约、状态机、路径、job store 稳定语义或架构边界；文档中 “job store 使用文件锁、原子写和有界 JSON record” 仍为当前事实，因此未修改。
- 已读取 `tests/README.md` 的当前测试事实说明。删除旧 Fins 私有 stream close 测试后，原文 “文件锁失败关闭” 已不再是 `tests/fins/test_fins_ingestion_runtime.py` 当前覆盖事实，因此已删除该短语；未做机械同步。

## Validation commands and results

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: passed, `26 passed, 3 warnings`
  - Warnings: edgar dependency deprecation warnings only.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py --cov=dayu.fins.ingestion_runtime --cov-report=term-missing -q`
  - Result: passed, `26 passed, 3 warnings`
  - Coverage: `dayu/fins/ingestion_runtime.py` reached `92%`, above the required `80%` per-file target.
  - Warnings: edgar dependency deprecation warnings only.
- `source .venv/bin/activate && pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pyright`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed.
- `rg -n "_StoreFileLock|import fcntl|ingestion_runtime\.fcntl" dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - Result: no matches.

## Completion signal

- Slice 1 complete.
- `_StoreFileLock` is removed from Fins ingestion runtime.
- `import fcntl` is removed from Fins ingestion runtime.
- Fins ingestion job store now uses `dayu.runtime.filelock.file_lock` directly.

## Blocking open questions

- None.

## Residual risks classification

- Low: this slice changes only the lock primitive used by the ingestion job store; existing job store behavior tests and pyright pass.
- Deferred to later slices: storage batch convergence and deletion of `dayu/fins/_file_lock.py` are intentionally not attempted in this slice.

## Explicit non-changes

- Host / Engine / ToolRuntime contract: unchanged.
- Fins job schema: unchanged.
- Fins ingestion state machine: unchanged.
- Fins storage protocol: unchanged.
- Atomic replace semantics: unchanged.
- Storage batch code: unchanged.
- `dayu/fins/_file_lock.py`: unchanged.
