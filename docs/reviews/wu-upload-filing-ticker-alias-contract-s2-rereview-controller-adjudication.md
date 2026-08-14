# WU upload-filing ticker alias contract — S2 re-review controller adjudication

## Gate decision

- MiMo: PASS（`docs/reviews/code-review-20260815-020224.md`）
- DS: PASS with two low findings（`docs/reviews/code-review-20260815-021015.md`）
- Controller: **FAIL / one narrow follow-up fix**

## Accepted low findings

1. `_commit_batch_with_publication_guard` 的 backup 存在性判定仍使用 `Path.exists()`。虽然当前 descriptor 使正常 corpus 非空、rename 失败会回滚，尚无已证实静默丢失路径，但该事实与本 work unit 已冻结的显式 lstat/I/O 分型属于同一 storage owner。必须改为复用 `_lstat_optional_storage_path`，仅 ENOENT 表示 missing，非目录与普通 I/O 均在 replace 前 fail closed，并补 tree/evidence 断言。
2. `begin_batch` 的 symlink/non-directory fail-closed 分支缺 owner test。补 symlink 与 regular-file 参数化测试，断言异常、published locator 不变、writer/reservation 可再次正常使用。

## Rejected / deferred

- material 缺 company name 在 pipeline-direct 场景的 generic runtime 投影是既有 admission 分层行为，不属于本 alias work unit；本轮不扩展。
- 不新增 durable cache/index，不修改已通过的 merge/lock/recovery 路径或 README。

## Next gate

AgentCodex 完成窄修复、focused + relevant regression + pyright + coverage/residue 后，两路 reviewer 只需复核这两个 accepted low findings 及回归影响；不得提交。
