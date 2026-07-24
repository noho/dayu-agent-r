# WU-CTX-01 PR #183 Deepreview Controller 裁决

## 1. Scope

- Work Unit：`WU-CTX-01`
- PR：[#183](https://github.com/noho/dayu-agent-r/pull/183)
- PR state：`OPEN / draft`
- base：`main@5afe71fe`
- reviewed head：`ae524fe0`
- AgentMiMo：
  `docs/reviews/wu-ctx-01-pr-183-deepreview-mimo.md`，verdict=`PASS`
- AgentDS：
  `docs/reviews/wu-ctx-01-pr-183-deepreview-ds.md`，verdict=`PASS`
- GitHub checks：
  - `windows-upload-script`：`SUCCESS`
  - `windows-init-transaction`：`SUCCESS`
- Controller decision：`needs-fix`
- accepted findings：1
- rejected findings：1
- blocking questions：None

`docs/host/issues-implementation-control.md` 是 Controller-owned，已排除在两路 PR
implementation diff 外。

## 2. First-principles verdict

PR 的主体 correctness、transaction ordering、replay、provider-no-usage fallback、
public projection shape 与测试证据成立。MiMo 没有 actionable finding；DS 也给出总体
`PASS`，并列出两条 informational observations。

Controller 不按 reviewer 的 severity/verdict 机械裁决。DS F-DS-01 虽被标为
informational，但直接证明 public DTO contract 与 canonical owner 的 threshold invariant
不一致：canonical sizing/fact 强制 `soft_threshold_tokens < hard_threshold_tokens`，
Host/Service public DTO constructor 却允许 equality。当前 production projection 上游会
拒绝 equality，不代表 public typed boundary 可以承诺一个 canonical fact 不可能产生的状态。
依据项目“durable state / public projection 同一业务事实必须同源一致”的硬约束，该项必须在
PR gate 修复。

该缺口不否定主算法，也不需要重开 aggregate 设计；它是两处 public boundary operator 与
owner contract 的最小同步。

## 3. Finding adjudication

### F-DS-01 — accept as `CTRL-PR-01`

位置：

- `dayu/host/api.py::HostContextUsageView.__post_init__`
- `dayu/service/entrypoint_runtime.py::EntrypointContextUsage.__post_init__`

直接证据：

- canonical owner
  `dayu.host.context_budget.validate_context_threshold_ordering` 在
  `soft >= hard` 时 fail closed；
- durable parser 复用该 owner；
- 两个 public DTO 当前只在 `soft > hard` 时拒绝，允许 `soft == hard`；
- 现有 Host/Service tests 没有 direct constructor equality rejection。

Required fix：

1. 两个 public DTO boundary 都必须拒绝 `soft >= hard`，错误文本明确 soft 必须小于
   hard；不得用默认值、projection 补偿或 loose fallback。
2. 分别补 Host public DTO 与 Service entrypoint DTO 的 owner-level direct tests，
   证明 equality fail closed，并保持合法 strict ordering。
3. 不改变 public 七字段 shape、canonical fact schema、projection mapping、threshold
   calculation 或 `context_budget.py` owner。
4. 检查 README 触发；本修复不改变稳定 public field shape 或用户工作流，预计无需 README
   更新。

### F-DS-02 — reject-nondefect

`DurableRunnerCallManifestRecorder` 与 tool/no-tool `RunInputBuilder` 仍有当前 production
callers。其 post-start boundary 不能重新证明 pre-start complete sizing，因此写
`UNAVAILABLE + ORDINARY` 是已裁决的 conservative contract，不是兼容 shim、dead API 或
错误 stage。aggregate Controller 已驳回同一 DS F12；PR review 没有提供新的 failure
evidence，不重开。

## 4. MiMo transient test observation

MiMo 的 full Host run 出现一次既有
`test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` 时序失败：
`2258 passed, 1 failed, 2 skipped, 6 deselected`。该节点立即复跑通过，AgentCodex 与
AgentDS 的同一最终 head clean full Host 都为
`2259 passed, 2 skipped, 6 deselected`。没有代码证据把抖动归因到 context sizing；
记录为非 blocking test residual，不接受 production fix。

## 5. Required validation

AgentCodex 只允许修改：

- `dayu/host/api.py`
- `dayu/service/entrypoint_runtime.py`
- 两个 owner boundary 对应的既有 Host/Service tests
- 新的 PR review-fix artifact

不得改当前 PR review artifacts、本 Controller adjudication、control doc、算法/schema、
其它 rejected path 或 commit。

至少执行：

```bash
source .venv/bin/activate
pytest -q <Host public DTO owner test> <Service entrypoint DTO owner test>
pytest -q tests/host tests/service
python -m pyright dayu/ tests/ utils/
git diff --check
```

还必须核对相对 `ae524fe0` 的 allowlist、两处 stale `soft > hard`、README 触发与 changed
production branch coverage `>=80%`。

## 6. Decision

**`needs-fix`**

完成 `CTRL-PR-01` 后，由 AgentMiMo、AgentDS 相对 PR head `ae524fe0` 并行执行 PR
review-fix re-review；Controller 最终裁决后才允许创建 accepted PR review commit、push
并进入 draft-PR-pass/final closeout。PR 保持 draft。
