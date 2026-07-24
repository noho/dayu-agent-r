# WU-CTX-01 PR #183 Review-Fix Re-Review Controller 裁决

## 1. Scope

- Work Unit：`WU-CTX-01`
- PR：[#183](https://github.com/noho/dayu-agent-r/pull/183)
- PR state：`OPEN / draft`
- reviewed head：`ae524fe0`
- review range：`ae524fe0..working-tree`
- accepted finding：`CTRL-PR-01`
- AgentCodex fix：
  `docs/reviews/wu-ctx-01-pr-183-review-fix-codex.md`
- AgentMiMo re-review：
  `docs/reviews/wu-ctx-01-pr-183-review-fix-rereview-mimo.md`，verdict=`PASS`
- AgentDS re-review：
  `docs/reviews/wu-ctx-01-pr-183-review-fix-rereview-ds.md`，verdict=`PASS`
- Controller decision：`pass`
- new actionable findings：0
- blocking questions：None

## 2. First-principles verdict

`CTRL-PR-01` 的动机成立，但缺口仅位于两个 typed public DTO boundary：
canonical context sizing/fact owner 已强制
`soft_threshold_tokens < hard_threshold_tokens`，原 Host/Service DTO constructor
却允许 equality。正确修复不是改变 sizing 算法、schema、projection、fallback 或
legacy recorder，而是让公开 typed boundary 拒绝 canonical owner 不可能产生的状态。

最终实现正好落在该 owner boundary：

1. `HostContextUsageView.__post_init__` 与
   `EntrypointContextUsage.__post_init__` 都从拒绝 `soft > hard` 收紧为拒绝
   `soft >= hard`；
2. 两处错误文本都明确表达 `soft_threshold_tokens must be less than
   hard_threshold_tokens`；
3. 两个 owner-level direct tests 都先证明合法 `soft < hard` 可构造，再以
   `dataclasses.replace` 直接构造 `soft == hard`，验证 equality fail closed；
4. production zero-context diff 只有上述 operator 与错误文本变化，没有下游补偿、
   fallback、loose parsing、默认值或兼容 shim。

因此同一 threshold ordering 事实已在 canonical owner、durable fact parser、
Host public projection type 与 Service entrypoint type 保持一致。

## 3. Re-review evidence adjudication

### 3.1 `CTRL-PR-01` closure

两路 reviewer 均直接读取 canonical invariant、production diff 与 direct tests，并独立确认：

- 两个 public DTO 都拒绝 `soft >= hard`；
- 合法 strict ordering 保持；
- direct tests 精确覆盖 equality，而非只覆盖 `soft > hard`；
- stale `soft_threshold_tokens > hard_threshold_tokens` 搜索为 0；
- public 七字段 shape、`CONTEXT_BUDGET_EVALUATED` schema、projection mapping、
  threshold calculation 与 `context_budget.py` owner 均未变化；
- legacy recorder 没有修改，且没有新 failure evidence 重开已驳回 finding；
- 没有新增 actionable correctness、stability、maintainability、semantic ownership
  drift 或类型安全 finding。

Controller 接受两路 closure evidence，`CTRL-PR-01` 状态为 `closed`。

### 3.2 Validation

AgentCodex：

- focused owner files：`76 passed`
- clean full Host + Service：
  `2501 passed, 2 skipped, 6 deselected`
- changed production branch coverage：
  - `dayu/host/api.py`：`90%`
  - `dayu/service/entrypoint_runtime.py`：`83%`
  - union：`87%`
- full pyright：`0 errors, 0 warnings, 0 informations`
- diff-check、allowlist、stale operator 与 README trigger audit：pass

AgentMiMo：

- focused nodes：`4 passed`
- full pyright：`0 errors`
- full Host + Service 首跑只命中已记录的 cancel-watchdog 时序抖动：
  `2500 passed, 1 failed, 2 skipped, 6 deselected`；失败节点立即复跑
  `1 passed`
- diff、shape、mapping、stale 与 README audit：pass

AgentDS：

- focused nodes：`4 passed`
- clean full Host + Service：
  `2501 passed, 2 skipped, 6 deselected`
- full pyright：`0 errors`
- branch coverage：Host `90%`、Service `83%`、union `87%`
- diff、allowlist、protected input 与 README audit：pass

clean full-suite、类型检查与 coverage 证据由不同执行路径交叉支持，足以排除本修复引入
context usage boundary 回归。

## 4. Rejected path remains rejected

原 DS legacy recorder observation 没有新的 direct failure evidence。
`DurableRunnerCallManifestRecorder` 与 tool/no-tool `RunInputBuilder` 的 post-start
conservative boundary 仍是 active contract，不是本次 public DTO invariant drift 的 owner。
该 finding 继续维持 `reject-nondefect`，不得进入本修复或后续 closeout。

## 5. Residual risk

- cancel-watchdog 时序抖动：MiMo 与 AgentCodex 的部分 full-suite 首跑各命中一次，
  单节点立即复跑通过，AgentCodex 与 AgentDS 又取得 clean full Host + Service 结果。
  没有调用链或数据证据将其归因到 context usage DTO，维持非 blocking test residual；
- coverage instrumentation 与 macOS spawn 的 process-backed ToolRuntime 隔离冲突：
  coverage-only run 已排除该无关 process 文件；无插桩完整 suite clean。它不影响
  `CTRL-PR-01` correctness 裁决；
- provider live smoke 仍不是本 public DTO operator 修复的必要证据。provider 不返回 usage
  时由已接受的 conservative fallback 保证不劣于原算法，该独立 contract 未被本修复改动。

这些 residual 均没有形成 WU-CTX-01 draft PR 的 blocking condition。

## 6. Decision

**`pass`**

- `CTRL-PR-01`：`closed`
- new actionable findings：0
- blocking questions：None
- 下一入口：创建 accepted PR review protected commit，push feature branch；保持 PR #183
  为 draft，等待新 head checks 通过后进入 `draft-PR-pass / final closeout`。
