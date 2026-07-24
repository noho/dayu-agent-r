# WU-CTX-01 Final Closeout（Controller）

## Metadata

- work unit：`WU-CTX-01`
- GitHub Issue：`#20`（保持 OPEN；PR merge 后由 `Closes #20` 关闭）
- branch：`feat/wu-ctx-01`
- base：`main@5afe71fe`
- accepted PR review commit：`e2a627a2`
- draft PR：[#183](https://github.com/noho/dayu-agent-r/pull/183)
- PR state：`OPEN`、`draft=true`、`mergeable=MERGEABLE`
- decision：`final-closeout-pass`
- blocking questions：None

## Gate closure

- preflight：目标 base merge 状态、工作树与 `main` fast-forward 均通过；
- goal confirmation：用户确认 `WU-CTX-01` 的目标、非目标、scope boundary 与验收信号；
- accepted plan：`06c143f2`；
- plan amendments：`ff28cbc4`、`3f4190ed`、`ed43bcf2`；
- accepted Slice 1：`b6f297b4`；
- accepted Slice 2：`126e67ca`；
- accepted Slice 3：`fad15d39`；
- accepted aggregate deepreview：`798ba977`；
- ready-to-open-draft-PR：`ae524fe0`；
- draft PR whole-PR review：
  - `docs/reviews/wu-ctx-01-pr-183-deepreview-mimo.md`：`PASS`；
  - `docs/reviews/wu-ctx-01-pr-183-deepreview-ds.md`：`PASS`；
  - `docs/reviews/wu-ctx-01-pr-183-review-controller-adjudication.md`：
    decision=`needs-fix`，accepted finding=`CTRL-PR-01`；
- PR review fix：
  `docs/reviews/wu-ctx-01-pr-183-review-fix-codex.md`；
- PR review-fix re-review：
  - `docs/reviews/wu-ctx-01-pr-183-review-fix-rereview-mimo.md`：`PASS`；
  - `docs/reviews/wu-ctx-01-pr-183-review-fix-rereview-ds.md`：`PASS`；
  - `docs/reviews/wu-ctx-01-pr-183-review-fix-rereview-controller-adjudication.md`：
    decision=`pass`，`CTRL-PR-01=closed`，new actionable findings=0；
- accepted PR review protected commit：`e2a627a2`。

## Delivered outcome

- `CONTEXT_BUDGET_EVALUATED` canonical fact 与 adaptive context-budget estimator 是两个
  独立 contract：canonical fact 同时覆盖 usage-anchored 与 conservative-fallback 结果，
  estimator method 不决定 fact 是否存在；
- Host 在完整 runner-call input、manifest/link 与同 iteration usage 的 typed lineage 上计算
  usage anchor，不从 provider 名称、时间戳、日志字符串或下游展示反推 pairing；
- compatible anchor 使用 signed estimated delta 推导下一次输入；usage 缺失、非法、歧义、
  pairing 不可信或 anchor 不兼容时，回退到原有完整输入 conservative estimator；
- 不支持返回 usage 的 provider 不会令 Run 失败，fallback 路径不低于修改前算法；
- ordinary、post-compact、reactive fallback、recovery、wait-resume 与 steer 的 sizing /
  continuation source contract 已统一，repair replay 不读取当前 tooling；
- continuation manifest 不把 pre-start duplicate 错判为 post-start duplicate；
- steer 保留 `SUBSET / ALL / NONE` 与 policy-disabled 语义；
- source loader 以 typed `projection → tool → policy → request` precedence 决定来源；
- Host/Service public context-usage projection 保持同一七字段 shape，不暴露 raw
  `USAGE_REPORTED` payload、event id、payload ref 或内部 pairing metadata；
- canonical owner、durable parser、Host DTO 与 Service DTO 均严格要求
  `soft_threshold_tokens < hard_threshold_tokens`。

## Final validation evidence

- aggregate fix focused matrix：`209 passed`；
- clean full Host：`2259 passed, 2 skipped, 6 deselected`；
- project standard suite：`5704 passed, 11 skipped, 6 deselected`；
- full pyright：`0 errors, 0 warnings, 0 informations`；
- whole-WU 25 个 changed production Python files 的 branch coverage 均 `>=80%`，
  最低 `82%`，union `86%`；
- PR review fix owner files：`76 passed`；
- PR review fix clean full Host + Service：
  `2501 passed, 2 skipped, 6 deselected`；
- PR review fix changed production branch coverage：
  Host `90%`、Service `83%`、union `87%`；
- PR review-fix 双路 re-review：均 `PASS`，0 个新 actionable findings；
- relative-base diff-check、allowlist、stale operator 与 README trigger audit：pass；
- fresh fetch 后 `main == github/main == 5afe71fe`，feature branch ahead 10 / behind 0；
- accepted PR review head `e2a627a2` 已推送，PR #183 base/head/draft/mergeable 状态已读回；
- accepted PR review head GitHub checks：
  - R11 `windows-upload-script`：`SUCCESS`；
  - R12 `windows-init-transaction`：`SUCCESS`。

## Residual risks

1. cancel-watchdog 测试存在低概率时序抖动；失败节点立即复跑通过，且多次 clean full suite
   成立。当前没有调用链或数据证据将其归因到 context sizing，后续若稳定复现应进入 Host
   cancellation 独立 work unit；
2. macOS coverage instrumentation 与 process-backed ToolRuntime spawn 存在隔离冲突；
   无插桩完整 Host + Service clean，changed-file coverage 已通过排除无关 process/
   cancellation nodes 的独立全绿运行验证；
3. provider live evidence 不是本 work unit 的 correctness 前置条件。provider usage 缺失、
   非法或不可配对时，由 conservative fallback 保证不劣于原算法；
4. PR merge 后仍需由用户观察目标 provider 家族的生产 usage 质量与 anchor 命中率；这属于
   运维信号，不改变 fallback correctness。

所有 residual risk 均已分类，不阻塞 draft PR。

## External action boundary

已执行：

- 推送 feature branch；
- 创建并更新 draft PR #183；
- 读取 PR/Issue metadata 与 GitHub checks。

未执行：

- mark ready for review；
- request reviewer、approve、提交 GitHub review/comment；
- merge、关闭或修改 Issue #20；
- 删除分支、部署或发布 release。

## Next entry point

用户已选定下一个 Work Unit 为 `WU-OBS-00`。PR #183 手工 merge 后：

1. 切回目标 base，拉取最新 `main`；
2. 依次完成 merge 状态、工作树与 `main` fast-forward preflight；
3. 进入 `WU-OBS-00` goal confirmation；
4. goal confirmation 第一项先按
   `docs/host/issues-implementation-control.md` 的约束检查“当前实际 Tool Trace 是否已经
   具备日常 analyzer 所需项目/字段”，并产出
   `docs/reviews/wu-obs-00-goal-confirmation-tool-trace-sufficiency-controller.md`；
5. 前置检查区分真实 trace signal 缺口与 analyzer / operator ergonomics 缺口：若 signal
   足够则直接规划 analyzer；若项目/字段不足，则在同一 WU-OBS-00 先规划 Tool Trace contract /
   producer / projection completion，再规划 analyzer。该检查不取消或 defer analyzer。

## Final decision

`final-closeout-pass`。WU-CTX-01 已完成到 draft PR handoff；下一步由用户进行 GitHub review
与手工 merge，随后从最新 `main` 按上述入口启动 `WU-OBS-00`。Controller 不自动扩大权限。
