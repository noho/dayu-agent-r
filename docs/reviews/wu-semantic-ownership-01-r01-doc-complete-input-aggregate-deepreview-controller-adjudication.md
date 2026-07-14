# WU-SEMANTIC-OWNERSHIP-01 / R01 Aggregate Deepreview Controller 裁决

## 1. Gate 身份与输入

- 当前是既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation sub-WU `R01 Doc complete input` aggregate deepreview；不是新 WU。
- accepted R01 plan：`54e35231`。
- accepted slices：R01-S1 `1a94d798`；R01-S2 `aa875ea5`。
- aggregate validation：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-aggregate-validation.md`，validation HEAD `26a65b0e`。
- aggregate review artifacts：
  - `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-aggregate-deepreview-ds.md`

两路 reviewer 均审查 accepted plan 到当前组合状态的完整 production/test/README 行为，而非只看 S2 或 aggregate artifact 摘要；均独立运行 Documents/Doc provider、真实 threshold smoke、output-owner、pyright 与传播/安全边界验证。

## 2. Reviewer 结论与 Controller 决定

| 路径 | Reviewer 结论 | Controller 裁决 |
|---|---|---|
| AgentMiMo | PASS；零 material finding、零 open question | **接受**。完整覆盖 SourceSnapshot 状态机、cap 全链删除、output owner 分离、symlink/security 保持、S1/S2 finding ledger 与 cross-slice drift。 |
| AgentDS | PASS；零 material finding、零 open question | **接受**。逐入口/函数/失败路径给出直接证据，完整追踪 accepted/rejected finding、coverage、real smoke、allowlist 和 deferred-scope audit。 |

没有 accepted aggregate finding，因此不制造空的 AgentCodex fix 或双路 re-review gate。用户要求的“accepted findings 全部修复并 re-review”已满足：S1 的五个 accepted code-review findings 已修复并双路 re-review；S2 与 aggregate review 均无 accepted finding。

## 3. 组合 contract 裁决

Controller 接受以下组合结论：

1. `SourceSnapshot` 独占完整 source snapshot、独立 cursor、materialization、并发读/关闭和 cleanup 语义；Doc consumers 只消费该 owner contract，无 byte budget 或 declared-length 拒绝。
2. `doc_tools.py` 独占目录观察与 list/search result/schema；directory entry cap 与 partial business fact 已全链删除。
3. list 完整观察且 output 有界；search 只在 `result_limit` 合法 partial；read/read-section 的字符 output partial 保留。相同字段名没有跨 owner 合并或机械删除。
4. `ToolTruncateSpec` 与 Host-owned `fetch_more` 保留，Doc 未接 `TruncationManager`；Issue 177 未被提前实现。
5. list/search/direct-read 三条 symlink/containment owner、`allowed_paths`、取消、process fencing 和 late-publication governance 保持；没有统一 authorization framework。
6. S1/S2 无 compatibility seam、下游重算/fallback、deferred Issue creep 或 production allowlist 越界。

## 4. Finding 与 residual ledger 修正

两份 review 都没有 finding，但 residual 表中有几处必须由 controller 收窄，避免把观察误写成当前 obligation：

| Reviewer observation | 最终 classification / owner |
|---|---|
| 极大 source/目录的资源消耗 | accepted product tradeoff；当前保留 spool、process boundary、cooperative/parent cancellation 和 output limit。未来若出现直接需求，由后续输入治理设计先确定 owner/config/error/LLM-visible contract；Issue 177 只负责已登记的 Doc/TruncationManager output continuation，不自动拥有 input governance。 |
| search `total_matches` 是返回命中数 | accepted current contract；description 自解释。只有未来 Issue 177 的已授权设计明确要求 complete-result continuation 时才重构，当前不是 open finding。 |
| 五工具未完整接入 `TruncationManager/fetch_more` | existing destination：Issue 177；R01 明确 non-implementation。 |
| symlink/TOCTOU 局部边界 | retained security behavior；当前不创建独立 authorization WU/schema。未来若用户授权，最终 owner 是 Host ToolRuntime 或同级 Host governance boundary。 |
| R03 LLM-facing inventory | 当前 R01 completion gate 的必交 artifact 内容；不是 code defect，也不能推迟到 R03 自行反推。 |

AgentDS verdict 文本中“6 个 S1 rejected/deferred”是计数笔误；controller 初审实际拒绝的是 DS-F06、DS-F07、DS-F08 三项，另有一个 controller test-overdesign follow-up 后来闭合。该笔误不改变 code/finding 状态。两份 review 以 raw `Issue #177` 表示追踪号仅是开发 artifact 标识，不进入 LLM-facing product surface。

## 5. 验证证据

- Controller：Documents/Doc provider `84 passed`；output-owner `5 passed`；real smoke/security `3 passed`；`source_snapshot.py` 93.506%；`doc_tools.py` 80.519%；pyright 0 errors；diff/scans pass。
- MiMo：组合 owner/consumer `84 passed`；output-owner `4 passed`；real smoke `1 passed` + security `2 passed`；pyright、diff、semantic/LLM/Issue 177/security scans pass。
- DS：Documents/Doc provider `84 passed`；pyright 0 errors；完整代码、tests、README、finding chain 与 allowlist 走读通过。
- 真实 smoke：10,001 个普通文件、35,651,621-byte 大文件、10,003 directory entries 与 outside file symlink，经 discovery→callable 验证完整 list/read/search 及 containment。
- 数值 scan 的两个 `-10_000` 只属于未修改 HTML candidate scoring，已用直接代码证据分类，不是 producer cap 残留。

## 6. Gate 结论

R01 aggregate deepreview **accepted with no fix gate**。R01 仍未完成：accepted plan §13.2/§14.3 要求的 completion artifact 和 R03 handoff inventory 尚未落盘，controller 也尚未复核 final finding/residual/README/Issue 177 ledger，未创建 accepted aggregate commit。

下一 gate：AgentCodex 只创建 `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-completion.md`，逐项满足 accepted plan §13.2 与 §14.3；不得修改 production/tests/README/control，不得 commit，不得开启 R02/R03。完成后 controller 独立复核，必要时同任务 follow-up 修正 artifact，最终才可决定 R01 accepted aggregate commit。
