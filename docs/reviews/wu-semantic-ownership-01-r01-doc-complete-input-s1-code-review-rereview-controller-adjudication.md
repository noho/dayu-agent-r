# WU-SEMANTIC-OWNERSHIP-01 / R01-S1 Code Re-Review Controller 裁决

## 1. Gate 身份与输入

- 当前仍是既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation slice R01-S1，不是新 WU。
- accepted plan 为 commit `54e35231` 中的 `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`。
- re-review 输入为当前相对 `1b4e5d33` 的完整 S1 workspace diff、初始两路 review、controller adjudication、AgentCodex fix artifact、fix controller validation，以及：
  - `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s1-code-review-rereview-ds.md`
- 两路 reviewer 均完整复核而非只看 fix patch，并独立运行测试、coverage、pyright、lint 与 source scans。

## 2. Re-review 裁决

| 路径 | Reviewer 结论 | Controller 裁决 |
|---|---|---|
| MiMo | PASS；无 material finding | **接受**。逐项证明 F01-F05 闭合、测试 seam 最小、source-limit consumer chain 删除完整、S1 directory 中间态与安全/取消/output owner 保留、S1/S2/Issue 177 边界正确。 |
| DS | PASS；无 material finding | **接受**。完成状态机、adversarial failure、semantic ownership drift、测试迁移、allowlist/README 与 residual risk 全量复核；未发现新 defect。 |

两份 artifact 中关于行号或 test node 历史数量的说明只作为验证索引，不成为产品 contract；其结论与 controller 直接复跑的 `80 passed`、`source_snapshot.py 94%`、pyright 零错误和 source scans 一致。

## 3. Accepted finding 最终状态

| Finding | 最终状态 | Owner-level closure |
|---|---|---|
| DS-F01 | **closed** | `SourceSnapshot` 的同一 lock 覆盖 active read、detach 与 actual close；确定性并发测试证明 close 等待 inflight read 且关闭后只得到 inactive error。 |
| DS-F02 | **closed** | `materialize()` 在创建输出、每轮复制与 path 发布前观察同一 cancellation check；取消原样透出并清理 partial/spool。 |
| DS-F03 | **closed** | 空 source exact size、EOF、`SEEK_END`、空物化与清理 contract 有 owner test。 |
| DS-F04 | **closed** | `Source.open()` 自身 `OSError` 原样透出且未发布 spool 被关闭。 |
| DS-F05 | **closed** | materialized output 写失败原异常透出，已写 partial path 删除。 |
| controller test-overdesign follow-up | **closed** | 删除通用 lock/spool、armable cancellation、成功/失败 output factory 层；只保留不可由真实 I/O 构造的单用途同步与失败注入 seam。 |
| DS-F06 | rejected / no current fix | accepted R01-S2 >33 MiB real smoke 将覆盖真实 rollover 和 consumer chain，不在 S1 重复实现细节测试。 |
| DS-F07 | rejected / no fix | 既有标准 seek 防御分支无本 remediation failure evidence。 |
| DS-F08 | rejected / no fix | exact LLM-facing assertion 是 accepted owner contract，不能放宽为关键词集合。 |

没有 accepted finding 留给后续优化；F06-F08 不是 accepted debt。

## 4. 最终验证与边界

- Controller fix validation：focused matrix `80 passed`；processor owner tests `15 passed`；`source_snapshot.py` coverage `94%`；full pyright `0 errors`；ruff、`git diff --check` 通过。
- MiMo re-review：`80 passed`、coverage `94%`、pyright 零错误、ruff/diff/scans 通过。
- DS re-review：`80 passed`、`source_snapshot.py 94%`、`doc_tools.py 80%`、pyright 零错误、ruff/diff/scans 通过。
- `DocResourceBudget`、`SourceBudgetExceeded`、`max_source_bytes`、source error/skip/result 字段和旧 bounded module symbols 零命中。
- `_DOC_DIRECTORY_MAX_ENTRIES/max_directory_entries` 只保留为 accepted S1 list/search 中间态；R01-S2 才能删除。
- `allowed_paths`、path projection、search containment、symlink 现状、process cancellation/fencing、`ToolTruncateSpec` 与 Host-owned `fetch_more` 未改变。
- README 终态迁移固定由 R01-S2 完成；当前 S1 不写错误中间态。
- 未实施 Issue 177、统一 tool authorization framework、其它 deferred Issue 或后续 remediation sub-WU。

## 5. Gate 结论

R01-S1 **accepted**，允许 controller 创建一个包含最终实现、测试、review/fix/re-review/controller artifacts 与当前 control state 的本地 accepted commit。该 commit 只接受 S1；不接受 R01-S2 或整个 R01。提交成功后 controller 必须单独更新 control doc 的 accepted hash 与下一入口，再进入 R01-S2 implementation gate。
