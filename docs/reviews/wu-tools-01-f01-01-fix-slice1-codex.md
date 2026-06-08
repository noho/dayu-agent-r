# WU-TOOLS-01-F01-01 Fix Slice 1 - Codex

## Work unit / gate / slice

- Work unit: `WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock`
- Gate: `fix`
- Slice: `Slice 1 - code review accepted fixes`

## Accepted findings fixed

- A1 / MiMo F1 / DS F1: `FsFinsIngestionJobStore` 的 6 个公共方法 docstring 已补充 `RuntimeFileLockError` 锁获取失败说明。
- A2 / MiMo F2: implementation artifact 已补充 coverage 命令和本轮实际结果。

## Files changed

- `dayu/fins/ingestion_runtime.py`
- `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md`
- `docs/reviews/wu-tools-01-f01-01-fix-slice1-codex.md`

## Exact changes

- 在 `create_job`、`save_job`、`save_succeeded_or_cancelled`、`claim_running_or_cancelled`、`read_job`、`request_cancel` 的 `Raises` 中补充：`RuntimeFileLockError: 文件锁获取失败时抛出。`
- 未修改 `FsFinsIngestionJobStore` 实现逻辑、状态机、读写顺序、job schema、路径、atomic replace 或测试文件。
- 在 `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md` 的验证记录中补充 coverage 命令、`26 passed, 3 warnings` 结果和 `dayu/fins/ingestion_runtime.py` 覆盖率 `92%`。

## Validation commands and results

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: passed, `26 passed, 3 warnings`
  - Warnings: edgar dependency deprecation warnings only.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py --cov=dayu.fins.ingestion_runtime --cov-report=term-missing -q`
  - Result: passed, `26 passed, 3 warnings`
  - Coverage: `dayu/fins/ingestion_runtime.py` reached `92%`.
  - Warnings: edgar dependency deprecation warnings only.
- `source .venv/bin/activate && pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
  - Note: pyright printed an upstream version availability warning, not a type error.
- `source .venv/bin/activate && pyright`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
  - Note: pyright printed an upstream version availability warning, not a type error.
- `git diff --check`
  - Result: passed, no whitespace errors.

## Blocking open questions

- None.

## Residual risks classification

- Low: this fix changes docstrings and review artifacts only; runtime behavior is unchanged.
- Deferred: storage batch convergence remains Slice 2 work.
- Deferred: `dayu/fins/_file_lock.py` deletion remains Slice 3 work.
- No blocking or unclassified residual risk remains for Slice 1 fix.
