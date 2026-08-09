# wu-cli-interactive-02 ready-to-open-draft-PR

## Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：ready-to-open-draft-PR
- Branch：`codex/interactive-oracle`
- HEAD：`d7cedd71d2a76f092b196698322ecf878398810c`
- PR base：`main`
- Remote base：`github/main@113ea34d47b95812d79aa31705949bbb46bc6061`
- Merge base：`113ea34d47b95812d79aa31705949bbb46bc6061`
- Ahead/behind：`13/0`
- Decision：`PASS`
- Next gate：push current branch → create draft PR

## History and scope proof

2026-08-02 final fetch 后，本地 `main` 与 `github/main` 均为
`113ea34d47b95812d79aa31705949bbb46bc6061`；`main`、`github/main` 与当前
branch 的 merge-base 完全相同。工作树与 index 干净，没有 merge、rebase 或
unmerged state。

Draft PR 以 `main` 为 base，并包含以下 13 个提交；其中最初两个 calibration
提交按用户要求保留在同一 PR 中：

1. `ae6bb96f` `docs(cli): complete interactive calibration matrix`
2. `cc5c9d57` `docs(cli): adjudicate interactive oracle`
3. `34127db4` `gateflow: accept plan for wu-cli-interactive-02-conformance-fixes`
4. `d210444f` `gateflow: accept wu-cli-interactive-02 S1`
5. `057b5b9b` `gateflow: accept wu-cli-interactive-02 S2`
6. `eadee409` `gateflow: accept wu-cli-interactive-02 S3`
7. `331d38dc` `gateflow: accept wu-cli-interactive-02 S4`
8. `ec9342ed` `gateflow: amend S5 plan for required identity closure`
9. `e7f578dc` `gateflow: close S5 durable builder plan closure`
10. `ce7ef846` `gateflow: close S5 utils identity closure`
11. `9ad45cf7` `host: preserve compactor response identity`
12. `cf041c2c` `gateflow: accept wu-cli-interactive-02 S6`
13. `d7cedd71` `gateflow: accept wu-cli-interactive-02 aggregate deepreview`

唯一既有 stash
`stash@{0}: On phaseflow/wu-cm-01: partial WU-CM-01 Slice C typed contract attempt`
不属于本 work unit，始终未触碰。

## Gate closure

- Goal confirmation：用户已确认。
- Accepted plan：完成；两路独立 plan review 与 re-review 完成。
- S1–S6：全部 implementation、双路 code review、accepted finding fix 与
  re-review 完成并形成 accepted commits。
- Aggregate deepreview：两路独立 initial review、controller adjudication、
  AgentCodex fix、两路 re-review 与 final adjudication 完成；最终
  `4 fixed / 19 rejected / 0 deferred / 0 unclassified`。
- F01–F13：均有 owner-level implementation 与 validation evidence。
- Docs：design、CLI CI handbook/registry、职责范围内 README 与 tests README
  已按 S6 final implementation decision 更新；oracle byte-identical 保留。

## Validation readiness

- CLI focused：`605 passed`。
- Service focused：`13 passed`。
- recovery：`116 passed`，另有真实 POSIX SIGKILL immediate-reconnect、同 invocation
  越过 stale threshold 自动恢复 smoke。
- compaction terminal/dispatch：`367 passed`。
- Engine identity：`173 passed`。
- affected CLI/Service：`1181 passed, 7 skipped`。
- affected Host：`775 passed`。
- full Engine/Host：`2957 passed, 1 skipped, 6 deselected`，另有 6 个已在 clean
  base 复现的 phase5 scheduler/test race failures，不是本 branch regression。
- I0554 successful-without-final static owner proofs：`3 passed`。
- aggregate accepted finding fix：`185 passed`，production owner coverage
  86%/95%/84%，full pyright `0 errors, 0 warnings, 0 informations`。
- Controller aggregate focused matrix：`12 passed`；SQLite competition test
  `10 x 1 passed`。
- 全 work unit 各 slice full pyright 均为 0；diff、scope 与 secret scans 通过。

## Residual risks and validation blockers

- G01–G07 尚未进入正式后续 CLI calibration，不能在本 PR 中宣称已裁决或关闭。
- S6 已取得一次真实成功 compactor durable response identity evidence，包含安全的
  effective provider/model、client correlation 与 present provider request id，且
  与 operation、attempt、proposal manifest、candidate/output 同源绑定；没有
  endpoint、credential、header、secret 或 raw provider payload。因为 formal
  renderer target pin 与 G01–G07 尚未补跑，该 raw evidence 不冒充 accepted
  scenario。
- awaiting smoke 的 `callback_execution_port` drift 是既有 harness/public-contract
  gap；不属于 F01–F13 production regression。
- full Engine/Host 的 6 个 phase5 failures 已在 clean base 复现并分类；不修改
  scheduler/test oracle 来掩盖。
- 当前没有 deferred、blocking 或未分类 residual risk。

## PR action boundary

已授权且下一步自动执行：

1. push `codex/interactive-oracle`；
2. 创建 base=`main` 的 draft PR；
3. 创建后必须执行两路独立 PR deepreview；
4. accepted finding 只交 AgentCodex 修复，随后两路 re-review；
5. final push 后进入 draft-PR-pass 与 final closeout。

明确禁止：merge、approve、mark ready、request reviewers、删除 branch、创建 issue。
