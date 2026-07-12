# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S4 Code Review Controller Adjudication

## 结论

`accepted`，无 fix gate。

AgentMiMo 与 AgentDS 均返回 PASS，未提出 evidence-backed material finding。Controller 接受两路 review 结论，S4 implementation 可进入 accepted slice commit。

## Review Artifacts

- AgentMiMo：`docs/reviews/wu-semantic-ownership-01-round3-r3-a-s4-code-review-mimo.md`
- AgentDS：`docs/reviews/wu-semantic-ownership-01-round3-r3-a-s4-code-review-ds.md`
- Implementation：`docs/reviews/wu-semantic-ownership-01-round3-r3-a-s4-implementation-codex.md`
- Controller validation：`docs/reviews/wu-semantic-ownership-01-round3-r3-a-s4-controller-validation.md`

## 裁决

Accepted as correct:

- `NonTerminalRunKeysetCursor(accepted_event_sequence, run_id)` 是 startup recovery keyset / watermark 的唯一 typed owner。
- S4 recovery call graph 不再调用全量 `read_non_terminal_runs()`，不使用 `OFFSET`，也不存在 unbounded recovery transaction。
- 新增 S4 `fetchall()` 位于 keyset page reader，SQL 带 `LIMIT ?`，参数来自 validated `batch_size`。
- 每批 recovery 使用独立 write transaction；transaction 成功后才投递该批 wake；失败 batch 不投递 rollback wake。
- Opener 通过 S2 durable actor 执行 recovery；`mark_ready()` 只在全部 batches 与 wake handoff 成功后发生，失败路径不 READY。
- `_classify_run()` 及 orphan、accepted-cancel、WAITING、QUEUED、ACCEPTED 分类未被分页改写。
- S3 health lease、S5 watchdog/cancel、Service、CLI、Fins、Engine 均未越界修改。

## Residual

- legacy `read_non_terminal_runs()` 仍保留给非 startup recovery 消费者；两路 review 与 controller source scan 均确认 S4 recovery call graph 不再使用它。删除该通用 reader 不属于 S4。
- 一个 batch commit 后多个 wake callback 之间不是跨 callback 原子事务；当前 accepted risk 与 implementation artifact 一致，durable pending truth 可由下一 healthy opener 幂等重放，且失败路径不会 READY。

## Controller Validation Reference

Controller 已独立验证：

- S4 focused matrix：`60 passed`
- Pyright：`0 errors, 0 warnings`
- `git diff --check`：通过
- Source scans：no recovery full reader call、no OFFSET、bounded `fetchall` / `LIMIT ?`、keyset/watermark/batch/fixed policy time owner 均符合 S4 plan。

## Next Gate

Stage and commit S4 accepted slice. Then update `docs/host/issues-implementation-control.md` with S4 artifacts, accepted commit, validation result, and next gate `Round3 R3-A S5 Active-cancel Watchdog 与 Transaction-local Classification implementation by AgentCodex`.
