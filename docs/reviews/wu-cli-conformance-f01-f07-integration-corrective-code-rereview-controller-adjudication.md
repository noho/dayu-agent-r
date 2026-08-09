# WU CLI Conformance F01-F07 — Integration Corrective Re-Review Controller Adjudication

## Gate verdict

- Gate: corrective implementation code re-review
- Entry HEAD: `df99f858`
- MiMo re-review: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-rereview-mimo.md`
- DeepSeek re-review: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-rereview-ds.md`
- Verdict: `ACCEPT`
- Next entry: accepted corrective gate commit，随后恢复 S8 integration / real-evidence slice。

## Closure adjudication

| Item | Controller verdict | Evidence |
|---|---|---|
| DS-02 | `CLOSED` | `host_attempt_dispatch_records` 的 COUNT 已由单 `run_id` 收敛为 `(run_id, attempt_id)`；MiMo 与 DeepSeek 均逐行验证，DeepSeek 独立运行 Phase5 9/9。 |
| DS-08 | `CLOSED` | implementation 与 fix artifacts 记录的五文件 SHA-256 与两路 reviewer 独立重算完全一致；顺序固定为 fix → focused/full/static validation → fingerprint → artifact，artifact 写入不会改变被验证集合。 |
| DS-01/03/04/05/06/09/10/11 | `DISPOSITION-UPHELD` | 两路 re-review 均未发现能推翻 controller 初裁的直接反例；fix 未实现被拒绝的重构或弱化。 |
| DS-07 | `DISPOSITION-UPHELD` | DeepSeek 在 re-review 中以 typed contract 重新核对并撤回严重性主张：`session_summary.source_labels` 没有 kind 排他限制，coverage 是“至少一个业务区 represented 或 drop”，`_represented_sections` 允许多 section；两个 fake 是不同但都合法的 candidate strategy。 |
| MiMo-R1 | `RESIDUAL-OWNER-ASSIGNED` | 当前 dispatch barrier 的 commit-before-consume 时序有直接代码证据；未来若 Host dispatch owner 改时序，须同步 owner test，非当前 blocker。 |

## Integrity and validation

- corrective scope 无 production code delta；S8 README 与 S8 artifact 的入口 hash 保持不变；frozen oracle/scenario hash 保持不变。
- Phase5 focused：`9 passed`。
- 四类 corrective focused：`187 passed, 3 warnings`。
- 完整 suite：`6571 passed, 10 skipped, 6 deselected, 3 warnings in 219.51s`。
- changed Python Ruff：通过。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- publication/frozen JSON、hash、`git diff --check`、空 index 审计：通过。
- 两次 full-suite load 的偶发现象已保留为后续 S8 验证 residual；没有稳定 reproduction，未用 timing 放宽或 production 特例掩盖。

本 gate 没有 open finding 或 blocking open question，可以只提交 corrective data/test 与本轮 durable
Gateflow artifacts；不得把四份 S8 README 或 S8 implementation artifact 混入该 commit。
