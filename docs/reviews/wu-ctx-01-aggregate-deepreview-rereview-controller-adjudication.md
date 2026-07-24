# WU-CTX-01 Aggregate Deepreview Re-Review Controller 裁决

## 1. Gate metadata

- Work Unit：`WU-CTX-01`
- WU base：`5afe71fe`
- accepted Slice 3 tip / fix 前 HEAD：`fad15d39`
- initial aggregate reviews：
  - AgentMiMo：`docs/reviews/code-review-20260724-074017.md`
  - AgentDS：`docs/reviews/code-review-20260724-073108.md`
- initial Controller adjudication：
  `docs/reviews/wu-ctx-01-aggregate-deepreview-controller-adjudication.md`
  ，decision=`needs-fix`
- AgentCodex fix：
  `docs/reviews/wu-ctx-01-aggregate-deepreview-review-fix-codex.md`
- aggregate re-reviews：
  - AgentMiMo：
    `docs/reviews/wu-ctx-01-aggregate-deepreview-rereview-mimo.md`
  - AgentDS：
    `docs/reviews/wu-ctx-01-aggregate-deepreview-rereview-ds.md`
- Controller decision：`pass`
- unresolved accepted findings：0
- new actionable findings：0
- deferred findings：0
- blocking questions：None

`docs/host/issues-implementation-control.md` 是 Controller-owned，已排除在两路
re-review implementation diff 外。

## 2. First-principles final verdict

双路 re-review 均以 `5afe71fe..working-tree` 为范围，逐项复核了
`CTRL-AGG-01..09`，并独立执行 adversarial failure、semantic ownership drift、
over-coupling、typing、README、tests 与 coverage evidence 检查。两路结论均为
`pass`，没有新 actionable finding。

本 WU 的两个独立目标保持成立：

1. `CONTEXT_BUDGET_EVALUATED` 是 anchored 与 conservative 两种结果共同的 canonical
   fact/public projection contract，不以 provider 是否返回 usage 为存在条件。
2. context-budget 预估算法在 strict compatible usage anchor 存在时使用 signed delta；
   usage 缺失、非法、歧义或 lineage/compatibility 不可信时，严格回退当前完整 candidate
   的原 conservative estimator，不导致 Run 失败。

aggregate fix 没有把这两个目标重新耦合，也没有新增 provider-name branch、当前 tooling/
policy 重读、下游重算、loose parsing 或兼容 shim。

## 3. Accepted finding closure

### CTRL-AGG-01 — pass

`_UsageManifestPairing` 的 status/reason 已由 private `StrEnum` 封闭；producer/consumer
使用 enum identity，durable JSON boundary 只投影 `.value`。pairing reason 没有被错误
复用为 context sizing fallback reason。

### CTRL-AGG-02 — pass

continuation frozen source 已拆为 complete/unavailable typed union。complete variant 的
provider/model/estimator/policy/request/context-window/source-budget 均非 Optional；
consumer 显式判别 union，相关 8 个 `cast(str/int, frozen_sources...)` 已消失。
projection → tool schema → policy → request semantics 的失败优先级保持不变。

### CTRL-AGG-03 — pass

`_StartReactiveRecoveryOperation.__call__` 已收敛为薄编排，职责拆到模块级 typed helper。
两路 review 直接确认：

- 所有写入仍处于同一 `HostTransaction`；
- manifest → `CONTEXT_BUDGET_EVALUATED` → `RUN_STARTED` /
  `ATTEMPT_STARTED` 顺序不变；
- hard fallback 保持 budget fact → terminal closeout；
- source/start CAS miss 仍触发同一 rollback；
- lifecycle policy 未下沉到 `context_budget.py`。

### CTRL-AGG-04 — pass

public `open_host` 集成测试使用合法 scripted runner，完整走 submit/dispatch/terminal
lifecycle，不发 `USAGE_REPORTED`、不 monkeypatch resolver，且断言 Run `SUCCEEDED`、
存在 conservative `CONTEXT_BUDGET_EVALUATED`、fallback reason=`usage_missing`。
这直接关闭用户强调的 provider 无 usage success signal。

### CTRL-AGG-05 — pass

steer 对同一 frozen candidate / policy 只调用一次 estimator，pre-start manifest snapshot
与后续 anchored result 复用同一 `BudgetEstimate`；测试直接断言 steer 增量调用次数为 1。

### CTRL-AGG-06 — pass

`context_budget.py` 的 `validate_context_threshold_ordering` 是 strict
`soft_threshold_tokens < hard_threshold_tokens` 的唯一 owner。typed result、五阶段
decision matrix 与 durable parser 全部复用，并直接测试 equality fail-closed。

### CTRL-AGG-07 — pass

`_UTILIZATION_BASIS_POINTS_SCALE = 10_000` 只在 `context_budget.py` 定义一次；
result builders、typed result 与 `context_events.py` durable parser 共用
`context_utilization_basis_points`，没有第二真源。

### CTRL-AGG-08 — pass

四个 continuation unavailable 成员已从 `ContextSizingFallbackReason` 删除，只保留在
正确 owner `RunnerCallSizingUnavailableReason`。exact enum-set owner test 防止错误
成员回流；没有为了保留 dead plan residue新增 producer。

### CTRL-AGG-09 — pass

resolver direct test 构造普通 call 与更近的 strict compactor manifest/link/usage/
completion，证明 compactor usage 不被选择，也不会形成 orphan barrier 阻断正确 ordinary
anchor。测试只断言 owner contract，没有下游特例。

## 4. Rejected finding / residual risk closure

initial adjudication 驳回的 10 个 reviewer finding 均没有新的当前 failure evidence，
不重新打开：

- `HostRow` 类型前提错误；
- lifecycle producer strategy 下沉到 sizing owner 的错误抽象；
- 同一 SQLite transaction 下不可达的 manifest/fact partial commit；
- 两个 source boundary 的 runner-call kind classifier 强行合并；
- 未来 enum/stage 假设；
- intentional base `USAGE_MISSING` default；
- positive ratio 下行为相同的 floor/int 风格差异；
- 以 enum 名称 grep 推断零覆盖；
- 无组合分支的重复 15-cell roundtrip；
- 被误判为 unused old API 的 active conservative recorder。

long-session keyset scan、真实 provider 差异、多进程并发与 opt-in stress 保持非 blocking
residual risk；它们不是本 fix 引入的 regression，也不扩大为本 gate obligation。

## 5. Final validation evidence

AgentCodex 最终 working tree：

- focused owner/integration tests：`209 passed`
- clean full Host：`2259 passed, 2 skipped, 6 deselected`
- project standard suite：
  `5704 passed, 11 skipped, 6 deselected, 3 third-party deprecation warnings`
- full pyright：`0 errors, 0 warnings, 0 informations`
- `git diff --check`：pass
- stale/allowlist/README audit：pass

从 WU base `5afe71fe` 到最终 working tree 的 production Python union 为 25 个文件。
同一次 branch-enabled标准 suite 对 25 个文件逐文件执行 `--fail-under=80` 全部通过：
最低 `dayu/host/run_input.py=82%`，union 总覆盖率 `86%`。

AgentMiMo re-review 独立复跑：

- focused：`209 passed`
- full Host：`2259 passed, 2 skipped, 6 deselected`
- changed-production pyright：`0 errors`

AgentDS re-review 独立复跑：

- focused：`209 passed`
- full Host：`2259 passed, 2 skipped, 6 deselected`
- full pyright：`0 errors, 0 warnings, 0 informations`

## 6. Final decision

**`pass`**

`CTRL-AGG-01..09` 全部关闭；双路 aggregate re-review 均为 `pass`，没有未分类
finding、未解决 blocking question 或新 actionable defect。允许创建 accepted aggregate
deepreview protected commit，然后进入 ready-to-open-draft-PR preflight。

本裁决不授权自动 merge、将 draft PR 标记 ready、请求外部 reviewer、评论/关闭 Issue
或执行其它超出既定 Gateflow 的外部动作。
