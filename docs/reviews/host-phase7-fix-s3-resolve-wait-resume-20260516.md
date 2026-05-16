# Host Phase 7 P7-S3 Fix - resolve_wait Terminal Replay

日期：2026-05-16

## 修复项

- S3-F1：`ResolveWaitLostOutcome` 首次 resolve 后 wait record 进入 `LOST`，但终态重放分支只接受 `RESOLVED` / `FAILED`，导致同 `(wait_id, idempotency_key)`、同 digest 的 lost 重试返回 `INVALID_STATE`。

## Root Cause

`DefaultHostResolveWaitService._resolve_in_transaction` 将 `LOST` 排除在 `_replay_terminal_resolution` 入口之外。`LOST` 与 `FAILED` 一样是 resolve_wait 的终态 closeout outcome，也必须遵守同一 public idempotency contract。

## 代码变更

- `dayu/host/waiting.py`：终态重放入口加入 `WaitRecordStatus.LOST`。
- `tests/host/test_resolve_wait_command.py`：新增 `test_resolve_wait_lost_same_key_replays_terminal_snapshot`，断言 lost 同 key 重放返回同一终态 snapshot 且不追加 EventLog。
- `docs/reviews/host-phase7-implementation-s3-resolve-wait-resume-20260516.md`：同步 implementation artifact 的终态重放与测试事实。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py -q`
  - 结果：`6 passed`

