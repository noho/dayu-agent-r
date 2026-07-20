# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN3-F01 code re-review Controller adjudication

## Re-review inputs

- baseline：`4814b7dc93052f5742ab8b7f33a8dff9377c5ff6`。
- AgentMiMo：`docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-rereview-mimo-20260720-004719.md`，SHA-256 `dcbfa5520d0e65de5295a5d3a883fe0c91fdcd5172bb3a19d93228dfcd78ec95`，结论 `PASS / material finding 0 / READY FOR ACCEPTED COMMIT`。
- AgentDS：`docs/reviews/code-review-20260720-004740.md`，SHA-256 `260ae2b31386c131ab8b02604d5a15e7691722bb742abe0aaab74ce6a73c858c`，结论 `PASS / MATERIAL_CODE_FINDING=1（文档级，非代码） / READY_FOR_ACCEPTED_COMMIT_AND_WINDOWS_RERUN`。
- implementation target 是四个 test/README path；初审、Controller 裁决、AgentCodex zero-change disposition、Controller zero-change validation 与两路 re-review 构成完整新树。两路均确认四个 implementation paths、binary diff、owner/security/deferred boundaries 无漂移，并且没有把 Darwin skip 当作 Windows pass。

## Finding 裁决

### DS REREVIEW-01：`REJECTED-WITH-REASON / NOT-A-FINDING / NO FIX`

DS 把两个名称近似但语义与生成时序不同的 Controller validation artifact 混淆了。

AgentCodex zero-change disposition 第 91 行实际记录的是：

```text
docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-controller-validation.md
1596a71226bbadbfce84ad89d401704f91e21b338b37cdcf607bf2e33a515c1b
```

该路径没有 `code-review-fix` 片段，指向 WIN3-F01 implementation 后的原始 Controller validation。Controller 独立计算该文件 SHA-256 仍为 `1596a71226bbadbfce84ad89d401704f91e21b338b37cdcf607bf2e33a515c1b`，所以 disposition 中的路径与 hash 完全匹配。

DS 用来反驳的另一个文件是：

```text
docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-fix-controller-validation.md
042f2ecd90e6fdf30ede1eab5103007456dfa138ffd7eebf951737c53e327472
```

这是 AgentCodex zero-change disposition 之后才由 Controller 生成的 validation，既不在 AgentCodex disposition 的入口树中，也不能被要求预先写入该 artifact。两个文件内容和 hash 本来就应不同。DS 所称“第 91 行列出 code-review 变体”与文件原文直接矛盾，因此不是文档完整性 finding；不得修改正确的历史 evidence 或重算不存在的 manifest。

## Accepted / rejected / residual ledger

- accepted re-review finding：0。
- rejected-with-reason：1，即 DS REREVIEW-01；它是文件名误读，不是当前缺陷。
- accepted/open code finding：0。
- design contradiction、local blocker、unclassified residual：0。
- WIN3-F01 保持 `LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`。
- WIN2-F01/F02/F03 保持 `EVIDENCE_POSITIVE / OPEN UNTIL CLEAN RERUN`。
- 第三轮 `setx` timeout 与 R11 generated script `returncode=1` 保持 `NEEDS_REMOTE_EVIDENCE / NO CURRENT FIX`；第四轮真实 Windows 若仍发生，必须保留 strict UTF-8 output 并重新建立唯一 root cause，不能沿用证据不足的单因推断。

## Boundary confirmation

- 七个 strict UTF-8 declarations 只位于实际消费 Dayu CLI 或生成脚本转发输出的 test subprocess；产品、workflow、native command、prewarm 与 recorder 零 diff。
- 没有 loose decode、兼容 shim、全局环境编码修复或测试驱动产品 fallback。
- Config/Host internal SQLite/EventLog 继续属于 trusted-local domain；Tool Trace、audit、public、LLM-facing、logs/outputs/reviews/diff 保持 configured-secret plaintext-zero。
- 未实施统一 tool authorization framework，也未实施 Issue 142、151、175、177、178 或 Web/WeChat/render tracker 能力。

## Decision 与下一 gate

结论：`PASS / ACCEPTED_REREVIEW_FINDING=0 / READY_FOR_ACCEPTED_LOCAL_COMMIT`。

因为没有 accepted finding，re-review fix gate 为空；为错误 finding 制造一次无语义修改会破坏 evidence truth。下一 gate 只允许：Controller fresh validation、精确 stage 当前 WIN3-F01 implementation/control/review evidence、accepted local commit、非强制 push，然后触发并下载第四轮真实 R11/R12 Windows artifacts。只有 R11 全部节点、R12 init 全部节点和内嵌 R11 全部节点通过，且 `setx`/generated CLI 非零 residual 有最终实证裁决，AR-F07 才可关闭。
