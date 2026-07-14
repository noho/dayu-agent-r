# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input Plan Re-Review 总控裁决

## 1. 裁决对象

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`。
- 内部 remediation sub-WU：`R01 Doc complete input`；不是新 WU。
- 修后 plan：`docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`。
- plan-fix：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-fix-codex.md`。
- 第一路 re-review：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-rereview-mimo.md`。
- 第二路 re-review：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-rereview-ds.md`。
- 初轮总控裁决：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-controller-adjudication.md`。

两路 re-review 均返回 `PASS`，但 plan acceptance 仍由本裁决决定。

## 2. Accepted finding closure

| finding | MiMo | DS | controller conclusion |
|---|---|---|---|
| `R01-PF-01` symlink owner 边界 | closed | fully closed | **closed**。Python 3.11 当前不递归 directory symlink；list file-symlink entry、search candidate containment、direct-read input containment 分属现有边界，未新增 list containment 或统一授权。 |
| `R01-PF-02` S1→S2 临时签名 | closed | fully closed | **closed**。S1 只把既有 `int` 常量直传原参数，S2 同时删除参数与常量；无 wrapper、assertion helper、budget、optional/alias/compatibility seam。 |
| `R01-PF-03` list partial-only 分类 scan | closed | fully closed | **closed**。production-wide scan 可执行，逐命中 owner/disposition 与 stop 条件自足；不会把 search result limit 或 read 字符截断同名字段误删。 |
| `R01-PF-04` SourceSnapshot 调用链消歧 | closed | fully closed | **closed**。helper function、`LocalFileSource` 输入、unentered context manager 与 active snapshot consumer 已区分。 |

总控重新核对修后 plan 对应章节和当前生产扫描，没有发现 accepted finding 仅在 fix artifact 中声称关闭但未落入 plan 的情况。

## 3. Rejected / no-fix 非实施复核

两路 re-review 独立确认初轮总控拒绝的建议均未误进入 plan：

- 没有给 list 新增 resolved containment，也没有设计统一 tool authorization。
- 没有把 directory symlink 不递归描述成 R01 新安全修复。
- 没有给固定 directory 常量新增临时 assert/validator。
- 没有固定私有 iterator 函数名、签名、返回类型或具体 filesystem API。
- 没有给真实阈值 smoke 添加 skip、timeout、并行构造或无证据时长 contract。
- 没有给 SourceSnapshot 重复标注保留/新增，也没有把 spool threshold 配置化。
- 没有修改 self-disproved scan/sort finding、保留 prompt、coverage include 或其它 no-fix 项。
- 没有产品代码、测试、README、design 真源或 deferred Issue scope 变更。

## 4. Informational notes 裁决

DS 的 OQ-1/OQ-2 都不是新 finding：

1. S2 implementation/completion 必须实际重跑 §12.2.1 分类 scan，不能引用 plan re-review 结果替代实施验证。该要求已经在 plan 中，是后续 gate 的 pass signal。
2. `_BoundedTextRead.scan_complete` 是 read/read-section 字符输出 owner，必须作为合法同名字段保留。该分类已经在 plan 中，不需要再修 plan。

MiMo/DS 没有 blocking question。无需第三轮 plan fix/re-review。

Accepted-plan validation 发现 DS 初轮 review 有五处行尾空格；controller 仅做 whitespace hygiene 删除，不改变 finding、证据或 verdict。

## 5. Mandatory baseline 与边界

总控接受两路关于以下不变量未弱化的结论：

- R01 production/test/doc allowlist 保持闭集。
- Issue 177 的 Doc/TruncationManager 完整接通未被实施。
- `allowed_paths`、既有 search/direct-read containment、process cancellation/fencing、ToolTruncateSpec/fetch_more 均保留。
- >32 MiB / >10,000 entries 真实 smoke、逐文件 coverage ≥80%、受影响测试、full pyright、`git diff --check`、README decision、source/LLM/security scans 均仍是 mandatory。
- R03 LLM-facing handoff inventory 没有弱化。
- Topic 8/9 仍是 no-code decision；R01 未实现统一 authorization framework。

## 6. Final decision

R01 plan **accepted and code-generation-ready**。`R01-PF-01` 至 `R01-PF-04` 全部关闭；没有剩余 accepted plan finding、blocking question 或需要用户重新裁决的产品问题。

本裁决授权的下一步只有：

1. controller 形成 R01 accepted-plan local commit；
2. 记录 accepted-plan commit SHA；
3. 按 accepted plan 进入 `R01-S1` implementation gate。

它不授权跳过 slice review/fix/re-review，不授权提前实施 R01-S2，也不授权 Issue 177、统一 tool authorization 或其它 remediation sub-WU 的代码。
