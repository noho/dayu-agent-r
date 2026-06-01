# WU-DUR-01-02 Slice 2 Code Review Fix - Codex

## Gate

- Gate: code review fix
- Work unit: WU-DUR-01 + WU-DUR-02
- Slice: Slice 2 - Internal WAL Maintenance Primitive And Read-stale Proof
- Controller adjudication: `docs/reviews/wu-dur-01-02-code-controller-adjudication-slice2-20260601.md`
- Source review artifacts:
  - `docs/reviews/wu-dur-01-02-code-review-slice2-mimo-20260601.md`
  - `docs/reviews/wu-dur-01-02-code-review-slice2-ds-20260601.md`

## Scope

仅修复 controller accepted findings DS-C2-A / DS-C2-B。未改变 checkpoint control flow、public API、checkpoint semantics，未触碰 Slice 3/4。

## Finding Fix Status

### DS-C2-A - 已修复

- **问题**: WAL 文件 stat 的 `OSError` 分支与 checkpoint PRAGMA failure 共用 `Host durable WAL checkpoint failed`。
- **修复**: `_read_wal_size_bytes` 的非 `FileNotFoundError` `OSError` 分支改为抛出 `HostDurableError("Host durable WAL checkpoint failed to read WAL file size")`。
- **验证**: 新增 `test_wal_checkpoint_wal_size_stat_failure_has_precise_message`，使用真实 Host durable store / SQLite checkpoint 路径，仅对目标 WAL 路径 stat 注入 `PermissionError`，断言精确错误消息。

### DS-C2-B - 已修复

- **问题**: checkpoint row length unexpected shape 与 no row 共用 `Host durable WAL checkpoint returned no result`。
- **修复**: row length 不等于 SQLite checkpoint 预期 3 列时改为抛出 `HostDurableError("Host durable WAL checkpoint returned unexpected result shape")`。
- **验证**: 未新增 direct unit test。该分支在真实 SQLite `PRAGMA wal_checkpoint` 正常实现下不可达；要触发只能伪造 cursor/connection 返回非 3 列 row，会 over-mock SQLite correctness 并把测试绑定到不可达防御路径。通过代码检查与现有测试 / pyright 覆盖确认未改变正常 checkpoint 行为。

## Changed Files

- `dayu/host/durable/maintenance.py`
- `tests/host/test_durable_connection.py`
- `docs/reviews/wu-dur-01-02-fix-slice2-codex-20260601.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q`
  - Result: pass, `22 passed in 0.32s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: pass, `0 errors, 0 warnings, 0 informations`

## Documentation Decision

未更新 README。当前修改仅调整内部 diagnostic 错误消息并补充测试断言，不改变用户手册、Host 开发手册的稳定接口、命令、架构边界或执行路径说明。

## New Risks / Open Questions

- 无新增 blocking risk。
- DS-C2-B 的防御分支没有 direct unit test；原因是测试该路径需要伪造 SQLite 不会真实返回的 checkpoint row shape，风险低，且当前修复为字符串级改动。
- Source review artifact 标题状态未回写；本 handoff 的 allowed edits 不包含 source review artifacts，因此状态映射记录在本 fix artifact 中。

## Stop Status

fix-complete
