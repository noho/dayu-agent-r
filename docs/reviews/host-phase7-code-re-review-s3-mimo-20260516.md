# Code Re-Review

## Scope

- Mode: current changes (re-review of fix pass)
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-code-re-review-s3-mimo-20260516.md
- Included scope: S3-F1 修复验证 + 当前未提交改动全量 blocking finding 扫描
- Excluded scope: Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model
- Parallel review coverage: 无

## S3-F1 修复验证

### 问题

`DefaultHostResolveWaitService._resolve_in_transaction` 终态重放入口只检查 `RESOLVED` / `FAILED`，遗漏 `LOST`。`ResolveWaitLostOutcome` 首次 resolve 后 wait record 进入 `LOST`，同 `(wait_id, idempotency_key)`、同 digest 的 lost 重试会落入 `wait_record.status is not WaitRecordStatus.WAITING` 分支，返回 `INVALID_STATE`，违反幂等 contract。

### 修复证据

- `waiting.py:583-587`：终态重放条件已加入 `WaitRecordStatus.LOST`：
  ```python
  if wait_record.status in (
      WaitRecordStatus.RESOLVED,
      WaitRecordStatus.FAILED,
      WaitRecordStatus.LOST,
  ):
  ```
- `tests/host/test_resolve_wait_command.py:211-231`：新增 `test_resolve_wait_lost_same_key_replays_terminal_snapshot`，断言：
  - 首次 lost resolve 返回 `RunStatus.LOST`
  - 同 key 重放返回同一 `RunStatus.LOST`
  - `current_attempt_id` 不变
  - 无新 EventLog 追加

### 验证结果

- `pytest tests/host/test_resolve_wait_command.py -q` → `6 passed`
- `pyright dayu/host tests/host` → `0 errors, 0 warnings, 0 informations`

### 结论

S3-F1 已关闭。修复正确、测试充分。

## Findings

未发现新增 blocking finding。

对当前未提交改动全量扫描确认：

1. `command.py` resolve_wait command：handle 打开、service 委托、dispatch wakeup 条件均正确
2. `waiting.py` DefaultHostResolveWaitService：幂等 scope/digest、终态重放（含 LOST）、completed/cancelled resume、failed/lost terminal closeout 均正确
3. `run_transition.py`：resume 和 terminal 路径原子事务操作正确，dispatch record 只在 resume 路径创建
4. `run_input.py`：resume continuity 只从 RUN_STARTED + TOOL_RESULT_ACCEPTED canonical events 重建
5. 边界：未越界修改 Engine/contracts/fins/service/ui
6. README/test_public_run_api 迁移正确

## Open Questions

无。

## Residual Risk

- P7-S4 范围的 late result diagnostic、cancel-vs-resolve race 与 CAS_LOST 并发压力测试未实现，属于 P7-S4 非目标。
