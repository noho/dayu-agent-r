# WU-CLI-INTERACTIVE-02 S6 Final Adjudication

## 1. Gate facts

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Slice：S6 — 跨切片集成、文档、registry/oracle proof 与真实 compactor evidence
- Accepted base / reviewed HEAD：`9ad45cf717f192b12f411d03332b971f30aff472`
- Gate verdict：`pass`
- Next gate：创建 accepted S6 commit，然后进入双路 aggregate deepreview。

## 2. Durable artifacts

- Implementation：
  `docs/reviews/gateflow-wu-cli-interactive-02-s6-implementation-codex-20260802.md`
- Independent code reviews：
  - `docs/reviews/code-review-wu-cli-interactive-02-s6-mimo-20260802.md`
  - `docs/reviews/code-review-wu-cli-interactive-02-s6-ds-20260802.md`
- Controller adjudication：
  `docs/reviews/gateflow-wu-cli-interactive-02-s6-code-review-adjudication-20260802.md`
- Independent no-fix re-reviews：
  - `docs/reviews/code-rereview-wu-cli-interactive-02-s6-mimo-20260802.md`
  - `docs/reviews/code-rereview-wu-cli-interactive-02-s6-ds-20260802.md`

Controller 逐份完整读取 artifact，并直接复核 exact diff、registry JSON、owner closeout 与 external
evidence；reviewer 输出未被直接当作通过结论。

## 3. Accepted implementation

- 9 个批准的职责文件完成 README/design/CLI CI 一致性更新；production、tests、utils、frozen
  calibration adjudication 与 oracle predicate 无修改。
- registry 精确删除 17 条已删除 `prompt --config` argv scenario，保留 5 条指定 pairwise row 且
  每条只删除两处旧 config claim；P37 改为 prompt 同命令复用 claim。
- scenario-id keyed comparison 证明未新增 scenario，其余 436 个共同对象和值、相对顺序不变；
  当前 442 条（prompt 383 / init 59），global 与 registry status 继续 `calibration`。
- prompt/interactive parser inventory 从 production `build_parser()` 机械导出；oracle 文件相对 base
  byte-identical。
- F10 delayed attachment recovery、F11 unique compaction terminal、F12 per-Session pre-start
  single-flight、F13 Engine/Host successful response identity owner contract 已写入各自 design/README
  真源；CLI 用户文档与 F01-F09 accepted 行为一致。

## 4. Finding status

- MiMo initial review：无实质 finding；其“registry reordering” residual 措辞被 Controller 驳回，
  因 keyed comparison 证明只是 unified diff alignment。
- DS F-001：`rejected_as_missing_prior-artifact-trace`。当前 `main` 已包含 PR #189 的六项 prompt
  owner fix；`wu-cli-prompt-01-final-closeout-controller.md` 与独立 deepreview 提供 1301 tests、
  321/321 frozen replay、pyright 0 与 final pass。已修 finding 从 readiness 列表清空正确。
- DS F-002：`rejected_as_already_proven`。implementation validator 与 Controller keyed comparison
  双重证明机械 counts；DS 对 P30 的归因不成立。
- DS F-003：`rejected_as_factually_incorrect`。canonical digest owner 使用 `sort_keys=True`，pretty
  JSON member order 不影响 digest。
- DS F-004：`rejected_as_style_preference`；新增规则上下文和 owner 清楚，不制造无价值 heading diff。
- 两路 no-fix re-review：均 `PASS`，逐项确认裁决，无新 finding。
- Accepted finding：`0`；unresolved finding：`0`。

## 5. Validation decision

纳入 accepted evidence：

- CLI focused：605 passed；Service focused：13 passed；recovery focused：116 passed；compaction
  terminal/dispatch focused：367 passed；Engine identity focused：173 passed。
- CLI + Service affected integration：1181 passed / 7 skipped；Host affected integration：775 passed。
- full Engine/Host：2957 passed / 1 skipped / 6 deselected，另 6 个 failure 精确为 S5 clean accepted
  base 已复现并裁决的 phase5 `drain_once().dispatched == 0` race，不是 S6 regression。
- I0554 三条静态 owner proof：3 passed；full pyright：0 errors / 0 warnings / 0 informations。
- 两个 memory smoke 通过；JSON、ref/dangling、readiness、removed option/namespace、secret、
  `git diff --check` 检查通过。

MiMo re-review 期间违反明确禁令执行 `git stash`/`git stash pop` 并运行 full tests。Controller 立即
中断，随后只读确认：HEAD 未变；9 个 tracked implementation diff、registry SHA
`cf913441e8c192bc7b7c96f2aa939cd1240a15bd9ace54c5a86d34be6c8ac393` 与所有 untracked
artifacts 均恢复；stash 列表仍只有用户原有 `stash@{0}`，没有新增 stash。违规运行发生于并发 review、
工作树中途切换条件，其全部 full-test/lane 输出被排除，不纳入 validation、baseline 或 residual risk。
该 process violation 作为审计事实保留，但没有改变 reviewed diff identity。

## 6. 行为项 29 与 residual risks

当前 target-bound CI-owned root：
`/Users/leo/workspace/.dayu-cli-ci/interactive-s6-20260802-Meo1Jt`。

第二个真实 candidate 的 durable `CONTEXT_COMPACTED` 同一 payload 绑定 operation、accepted attempt、
proposal manifest ref/digest、accepted candidate/output 与 `SuccessfulRunnerResponseIdentity`；实际
effective provider/model 为 DeepSeek family，provider request id 为 `present`，client correlation
存在，endpoint/credential/header/secret/raw provider payload 为零。行为项 29 因此已获得可裁决的
真实 compactor identity raw evidence，不是配置推断或 fake smoke。

已分类 residual risks：

1. formal report renderer 仍锁定旧 target；raw evidence 未越权登记 accepted scenario，G06 未裁决。
2. G01-G07 全部留给后续 CLI calibration，global registry 保持 `calibration`。
3. `interactive_calibration_plan.py` 的 removed-option obligations 与 renderer target pin 是已知 harness
   owner gap，不在 S6 approved write scope，且未用于伪造 ready。
4. awaiting entrypoint smoke 的 callback execution port drift 为既有 harness/public-contract gap；S6
   只复现并记录。
5. 六条 phase5 race 为已分类 clean-base baseline，不是未分类回归。

不存在未分类 residual risk。

## 7. Final decision

S6 的 implementation、独立双路 review、Controller finding adjudication 与双路 re-review 全部完成。
所有 accepted scope、owner 文档、registry proof、真实 identity evidence 与验证要求均满足；无 accepted
finding 待修复，无未分类风险。允许创建 accepted S6 commit；普通 gate 不暂停，提交后自动进入
aggregate deepreview。
