# WU-SEMANTIC-OWNERSHIP-01 / R08 累积验证计划修正 Re-Review — Controller Adjudication

## 裁决结论

- umbrella work unit 仍是 `WU-SEMANTIC-OWNERSHIP-01`；本 gate 只关闭同一 R08 内部 plan-drift remediation，不创建新 WU。
- final plan SHA-256：`87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`。
- protected S1 14-path binary diff SHA-256：`0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57`。
- AgentMiMo verdict：`PASS / 0 material finding / 0 blocker`。
- AgentDS verdict：`PASS / 0 new finding`。
- Controller final disposition：`PASS`；`R08-CVPF-01..03` 与其覆盖的五个 accepted source findings 全部关闭，新增 accepted/deferred/blocking finding 为 `0/0/0`。
- 下一入口是 exact-scope accepted plan-correction local commit；随后在同一未提交 S1 product/test tree 上进入 S2 cumulative implementation。Reviewer 结论本身不授权其它 WU、push、PR 或 deferred issue 实施。

## Re-review artifacts

- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-rereview-ds.md`

两路 reviewer 均完整审查 final plan，而非只看 review-fix 增量；均独立重算 plan hash 与 protected S1 hash，并确认 staged tree 为空。

## Finding closure

### R08-CVPF-01 — CLOSED

Git top-level glob pathspec 直接产生 production Python NUL manifest；coverage checker 以 repo-relative exact key 验证每个 changed production path，并在 manifest 空、key 缺失或 `<80.00%` 时失败。不得使用 basename、suffix、absolute-path、路径规范化或其它 loose fallback。

### R08-CVPF-02 — CLOSED

Git top-level glob pathspec 直接产生 `dayu/fins` 与 `tests/fins` actual-changed Python NUL manifest；同一 Python 环境机械执行 Ruff，空 manifest fail-closed。人工占位符、手抄 allowlist 与漏测 tests 风险已消除。

### R08-CVPF-03 — CLOSED

任一 aggregate deepreview accepted finding 修复改变 reviewed tree 后，旧累计 validation、content manifest、binary diff hash 与两路 aggregate deepreview 全部失效；必须完整重跑 §6.6/§6.7，在新 hash 上双路 aggregate re-review 并由 Controller 逐条关闭。

## Rejected findings

- DS F4：继续拒绝；严格 Host/Fins public key-set equality proof 保留。
- MiMo F2：继续拒绝；§6.7 是 §6.6 纳入 scans 的具体展开，不新增第二真源。
- MiMo F3：继续拒绝；S1→S2 由同一 Agent 在同一 tree 顺序实施，不新增行号、并发或 compatibility seam。

两路 re-review 均确认上述拒绝项及其替代 fallback 没有进入 final plan。

## Controller adjudication of residual observations

Reviewer 记录的三个实施期观测——逐文件 coverage 能否达到 80%、forced-truncation 三段公开链是否成立、coverage JSON key 是否与 repo-relative path 精确一致——均已由 final plan 的 S2 cumulative validation 与 stop conditions 直接拥有。它们不是当前 plan finding，不获得豁免，也不转成后续优化：任一失败都会阻止 R08 implementation review/commit，必须在当前 R08 owner boundary 内修复或停回 Controller。

## Scope and safety boundary

- S1 仍是 blocked intermediate evidence，不是已接受 product state；S1/S2 不单独 commit。
- Topic 8 的 Engine 240 字符脱敏/截断语义不修改；Topic 9 不实施统一 tool authorization framework。
- 不实施 Issues 142、151、175、177、178 或 R09-R12；不修改 Host/Engine/Service/UI。
- 保留 R07 citation/provenance/snapshot/revision、Host truncation、filesystem containment 与既有安全机制；本 gate 无安全行为修改。
- 不允许 compatibility field、wrapper、re-export、fallback、loose parsing、阈值弱化、skip/xfail 或测试驱动 shim。

## Validation

- Controller 完整读取两份 re-review artifacts 并逐项核对其 evidence 与 conclusion。
- Controller 独立重算 final plan SHA-256 与 protected S1 binary diff SHA-256，均精确匹配。
- §6.6 精确命令体 `zsh -n` 通过；两路 reviewer 均验证 coverage/Ruff fail-closed 逻辑。
- `git diff --check` 通过；staged tree 为空。

## Next entry point

Controller 只提交 plan-correction、Controller/reviewer evidence 与 control 状态；不得把 S1 product/test 或 S1 implementation artifact 混入该提交。提交后更新 control 进入 S2 cumulative implementation，并派发 AgentCodex 按 final plan 完成 S2；S2 必须在同一 S1 tree 上闭合全量累计验证、双路 code review/fix/re-review 与 aggregate deepreview，才能产生唯一 R08 implementation commit。
