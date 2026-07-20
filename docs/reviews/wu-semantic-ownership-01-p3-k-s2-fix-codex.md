# WU-SEMANTIC-OWNERSHIP-01 P3-K S2 Fix

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-K`
- Gate: `S2 code-review fix`
- Accepted finding: `P3-K-S2-CR-F01`
- Source review artifact: `docs/reviews/wu-semantic-ownership-01-p3-k-s2-code-review-ds.md`
- Stop status: `ready-for-controller-validation`

## Changed Files

- `tests/host/recovery_support.py`

## Finding Fixed

`P3-K-S2-CR-F01` 指出 `tests/host/recovery_support.py` 已引入 `_HOST_DB_FILENAME = "host.sqlite3"`，但
`attempt_count_for_run(...)` 与 `current_attempt_id_for_run(...)` 仍直接使用 `"host.sqlite3"`。

本次修复将这两个 helper 的 SQLite 路径统一改为：

```python
root_path / _HOST_DB_FILENAME
```

该变更只修复测试 harness 内部常量边界不一致，不改变 SQL 语义，不进入生产代码，不做 raw SQL 重构。

## Validation Results

- `rg -n '"host\.sqlite3"|_HOST_DB_FILENAME' tests/host/recovery_support.py`
  - 通过：`"host.sqlite3"` 只剩 `_HOST_DB_FILENAME` 定义；所有连接路径使用 `_HOST_DB_FILENAME`。
- `source .venv/bin/activate && pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q`
  - 通过：`9 passed in 5.65s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`
  - 备注：pyright 输出了新版本提示 `v1.1.409 -> v1.1.411`，不影响本轮验证。
- `git diff --check`
  - 通过：无输出。

## README Decision

已检查 `tests/README.md` 的 `README 更新边界`。本次仅统一既有测试 helper 内部常量使用：

- 未新增测试层级；
- 未改变测试运行方式；
- 未新增或改变测试维护规则；
- 未改变用户可见工作流。

因此无需更新 README。

## Residual Risks

- 无本轮新增 residual risk。
- S2 code review artifact 中提到的 stress 残留失败仍属于后续独立 work unit，不在本次 accepted finding 修复范围内。

## Completion

- Fix scope complete.
- No production code changed.
- No S1/S3 files changed.
- No control doc update, commit, push, PR, re-review, or broader refactor performed.
- Stop status: `ready-for-controller-validation`.
