# WU-TOOLS-01-F01-01 Slice 1 Code Re-review (MiMo)

## Scope

- Work unit: `WU-TOOLS-01-F01-01`
- Gate: code re-review
- Slice: Slice 1 - ingestion job store convergence
- Fix artifact: `docs/reviews/wu-tools-01-f01-01-fix-slice1-codex.md`
- Implementation artifact: `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-01-code-review-slice1-controller-adjudication.md`

## Verdict

**pass**

## Re-review Status

### A1. `RuntimeFileLockError` missing from job store public method docstrings

- Status: **已修复**
- Evidence:
  - `dayu/fins/ingestion_runtime.py:698` — `create_job` Raises 包含 `RuntimeFileLockError: 文件锁获取失败时抛出。`
  - `dayu/fins/ingestion_runtime.py:721` — `save_job` Raises 包含 `RuntimeFileLockError: 文件锁获取失败时抛出。`
  - `dayu/fins/ingestion_runtime.py:752` — `save_succeeded_or_cancelled` Raises 包含 `RuntimeFileLockError: 文件锁获取失败时抛出。`
  - `dayu/fins/ingestion_runtime.py:802` — `claim_running_or_cancelled` Raises 包含 `RuntimeFileLockError: 文件锁获取失败时抛出。`
  - `dayu/fins/ingestion_runtime.py:842` — `read_job` Raises 包含 `RuntimeFileLockError: 文件锁获取失败时抛出。`
  - `dayu/fins/ingestion_runtime.py:861` — `request_cancel` Raises 包含 `RuntimeFileLockError: 文件锁获取失败时抛出。`
- Scope note: adjudication 要求的是 `FsFinsIngestionJobStore` 实现类的 6 个方法，不包括 `FinsIngestionJobStore` Protocol 桩方法（line 488-599）。Protocol 桩的 Raises 由实现类保证，不属于本次 fix 范围。

### A2. Coverage validation missing from implementation artifact

- Status: **已修复**
- Evidence:
  - `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md:40-42` — 记录了 coverage 命令和结果：
    - 命令: `pytest tests/fins/test_fins_ingestion_runtime.py --cov=dayu.fins.ingestion_runtime --cov-report=term-missing -q`
    - 结果: `26 passed, 3 warnings`
    - 覆盖率: `dayu/fins/ingestion_runtime.py` 92%
  - 92% >= 80% per-file target。✅

## Validation Performed

1. 逐行读取 `dayu/fins/ingestion_runtime.py`，确认 `FsFinsIngestionJobStore` 的 6 个公共方法 docstring `Raises` 段均包含 `RuntimeFileLockError` 条目。
2. 读取 `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md`，确认 coverage 命令、结果和覆盖率百分比已记录。
3. 读取 `docs/reviews/wu-tools-01-f01-01-fix-slice1-codex.md`，确认 fix artifact 声明的变更与实际代码一致。
4. 交叉比对 controller adjudication 的要求与实际修复内容，无遗漏。

## Residual Risks / Uncovered Areas

- 低风险：`FinsIngestionJobStore` Protocol 桩方法的 docstring 未补充 `RuntimeFileLockError`，但 Protocol 桩是抽象接口定义，实际锁行为由实现类保证，不属于 adjudication fix 范围。
- 延续 controller adjudication 的 deferred items：storage batch convergence（Slice 2）和 `dayu/fins/_file_lock.py` 删除（Slice 3）未在本次 fix 中处理，按计划推迟。

## Blocking Open Questions

- None.
