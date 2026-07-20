# WU-SEMANTIC-OWNERSHIP-01 / R11 fixed-plan re-review Controller adjudication

## 1. Verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；R11 是内部 remediation sub-WU。
- reviewed fixed plan：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，
  773 lines / 61,810 bytes，SHA-256
  `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。
- AgentMiMo complete re-review：306 lines / 20,472 bytes，SHA-256
  `46a919c6c989ae1653c835fc613f030996d3990e7aec3aa27cf834f1718c8901`，verdict `PASS`，
  material finding 0。
- AgentDS complete re-review：332 lines / 30,417 bytes，SHA-256
  `f1644fbc489875d2cb3bc1f46dde81a9837e063ad004936f732b13ca30bd8c1d`，verdict
  `PASS / ZERO FINDING / ZERO BLOCKER`。
- Controller verdict：`PASS / R11 PLAN ACCEPTED / ZERO ACCEPTED OPEN FINDING`。

本 adjudication 接受 fixed plan，授权一次 exact-scope accepted-plan local commit。它不授权 implementation、
R12、push 或 PR；implementation 必须等 accepted-plan commit 成功并由 Controller 另发 authorization。

## 2. Review 完整性

两路 reviewer 均锁定相同 773 行 target，并完整读取初始双 review、Controller adjudication、AgentCodex fix、
Controller fix validation、design/control 与 CURRENT code/test/package evidence；均不是 delta-only review。
Controller 已逐行读取两份共 638 行 re-review artifact，并独立复核 target hash、fixture lock、staged-empty 与
`git diff --check`。

AgentMiMo artifact 的自引用 SHA 元数据已按同任务 follow-up 改为由 Controller 在冻结后独立锁定；substantive
review、verdict、finding 与 residual 内容未改变。上述 `46a919...c8901` 是冻结后的 Controller lock。

## 3. R11-PR-F01—F06 最终裁决

| Finding | 最终状态 | Controller 证据结论 |
|---|---|---|
| R11-PR-F01 | CLOSED | §5.3 typed field/enum/optional-to-current-flag checklist 与 §9.1 Controller-only S2→S1 owner 回返同时存在；禁止 adapter/fixture fallback、新 slice/WU/commit。 |
| R11-PR-F02 | CLOSED | source/output 都锁定 lexical+resolved containment、root-self/root-internal symlink rejection 与 external-ancestor allowance。 |
| R11-PR-F03 | CLOSED | `--infer`/`--overwrite` 均为 `store_true/default=False`；infer public resolver once、storage overwrite 与 publisher replacement 已消歧。 |
| R11-PR-F04 | CLOSED | exact-one wheel/dist-info selection、METADATA、entrypoint、extracted path 与 CSV RECORD 四个 zero oracle 完整。 |
| R11-PR-F05 | CLOSED | tracked AAPL fixture exact path、1,503,780 bytes、SHA、两个 `workspace/tmp` target name、no-network/no-mutation 均锁定。 |
| R11-PR-F06 | CLOSED | zero recognized filings 时 call cap=0/all call typed skipped；Ruff version verbatim oracle 与 full baseline 同树 lock/drift-stop/relock 完整。 |

初始 accepted/open 6 项全部关闭；本轮新增 accepted finding 0，blocker 0。

## 4. Rejected candidate preservation

Controller 接受两路一致证据：fixed plan 没有保留旧 `create` default、没有 `list2cmdline`/fallback/双算法，
没有删除 OLD structured auto-recursion，没有预猜 Windows quote algorithm 或 iteration count，没有跨平台
`--platform`、internal HTTP hop contract、raw enum UI、compatibility branch 或 test shim。

Windows 仍按真实 `cmd.exe` outcome/invariants 收敛；这正是此前 Controller 裁决，不是 plan 缺口。

## 5. 独立 adversarial challenge 裁决

- owner：Fins 唯一拥有 scan/classification/fiscal/material/priority/dedup/caps/skips；CLI 只拥有 input、一次
  public FMP resolve、current argv projection、renderer/publisher/summary；packaging 只发布真实 surface。
- slices：S1 typed plan → S2 current grammar/renderer/publisher → S3 placeholder/package/README/Windows gate，
  恰好三个 dependency-ordered slices；唯一 S2→S1 回返由 Controller 限定在原 owner。
- grammar：三个 direct/batch parser default `auto`；batch action 不含 delete；ticker/aliases/company precedence、
  infer/overwrite omission/propagation 与无 speculative IDs 均锁定。
- security：source/output containment、root 内 symlink rejection、external ancestor allowance、same-dir atomic
  replacement、POSIX mode、Windows delayed expansion off、argv injection 与 secret non-persistence 全部保留。
- packaging：placeholder scripts/packages/extra/requirements/package-data/README claims 删除，真实
  `dayu.tools.web` 与两个负向 import sentinel 保留；wheel 五层 oracle 闭合。
- validation：real filesystem、`/bin/sh` recorder、real CLI/Service/Fins storage、wheel、real `cmd.exe`、
  focused/full tests、per-file coverage、full pyright、同版本 Ruff、README/scans/diff gates均可执行。
- deferred：Issue 142、151、175、177、178、R12、真实 Web/WeChat/render、Topic 8/9 与统一 auth 仍为 no-touch。

## 6. Reviewer risk / observation 裁决

- Windows quoting 多轮反例迭代：接受为 R11-S2 执行风险，owner 是同一 renderer；真实 Windows run 是
  `PENDING_RELEASE_BLOCKER`，不是 accepted residual 或新 finding，不能在 umbrella closeout 前留 open。
- S2 首个 consumer 发现 typed gap：已由 §9.1 stop/owner-return/revalidation 治理，不是新 finding。
- wheel build frontend：现计划 install/build/smoke 会直接失败并 stop；不接受 AgentDS 提议的
  `pip wheel --dry-run` 作为新 requirement，也不修改 plan。
- workflow trigger allowlist 与 Ruff version drift：已有 exact allowlist review 和 version drift-stop/relock；
  都是 gate 检查，不是 material finding。
- fiscal-period mapping、material forms no-op、output help 更新、call cap“过滤后”含义：两路均有直接 plan
  contract 证明，维持 non-finding。

R11 plan acceptance 时 actual accepted residual = 0。Windows release blocker 状态保持 pending，必须由后续真实
GitHub-hosted evidence 关闭，不能重分类为 residual。

## 7. Accepted-plan commit authorization

授权 stage/commit 的 exact paths 只有：

1. `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-entry-controller-validation.md`
3. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-controller-validation.md`
4. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-mimo.md`
5. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-ds.md`
6. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-controller-adjudication.md`
7. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-fix-codex.md`
8. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-fix-controller-validation.md`
9. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-rereview-mimo.md`
10. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-rereview-ds.md`
11. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-rereview-controller-adjudication.md`
12. `docs/host/issues-implementation-control.md`

Commit 前必须 exact 12-path stage、staged diff check、无其它 unstaged/untracked path；commit message：
`docs: accept R11 upload workflow remediation plan`。不允许 product/test/README/design/workflow、R12、tmp、
secret artifact 进入此 commit。

READY_FOR_EXACT_SCOPE_ACCEPTED_PLAN_COMMIT
