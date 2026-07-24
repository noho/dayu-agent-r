# WU-CTX-01 Aggregate Deepreview Controller 裁决

## 1. Gate metadata

- Work Unit：`WU-CTX-01`
- WU base：`5afe71fe`
- accepted tip：`fad15d39`
- AgentMiMo：
  `docs/reviews/code-review-20260724-074017.md`
- AgentDS：
  `docs/reviews/code-review-20260724-073108.md`
- Controller decision：`needs-fix`
- accepted findings：9 个去重后的 actionable findings
- rejected findings：10 个 reviewer finding 编号
- deferred findings：0
- needs-more-evidence：0
- blocking questions：None

`docs/host/issues-implementation-control.md` 是 Controller-owned，排除在
aggregate implementation diff 外。

## 2. First-principles verdict

WU-CTX-01 的实现动机与主体架构成立。三路 Slice 已形成同一条可证明链路：

1. `CONTEXT_BUDGET_EVALUATED` canonical fact 与 context-budget 预估算法保持独立：
   canonical fact 对 anchored 与 conservative 两种结果都成立，usage 缺失不会阻止
   fact 或 Run 继续推进。
2. estimator、manifest/link、actual usage、accepted completion、compact boundary 与
   public projection 均有明确 owner；signed delta 只来自 strict compatible anchor，
   不从 provider request id、时间戳、显示文本或当前 tooling/config 反推。
3. provider 不返回 usage 时，resolver 返回 closed `USAGE_MISSING`，当前完整 candidate
   继续使用原 conservative estimator；没有 provider-name branch，也没有把
   `supports_stream_usage` 当作实际 usage presence。
4. ordinary、post-compact、reactive、dispatch-fallback 与 continuation producer 都先
   冻结 exact candidate/manifest，再追加同源 budget fact；recovery 与 wait continuation
   不重读当前 tooling/policy。

两路 review 没有发现 anchor 错配、错误 provider 分支、canonical/public fact 耦合、
transaction ordering 破坏或 Run 因 usage 缺失失败的现有 production path。因此主体不是
重做设计；本 gate 只修复 review 已用直接证据证明的 strict type / invariant / maintainability
缺口，并补两条关键组合回归。

## 3. Accepted findings

### CTRL-AGG-01 — usage pairing status/reason 改为封闭类型

来源：MiMo F01。裁决：`accept`。

`_UsageManifestPairing.status: str` 与 `reason: str | None` 表达的是封闭状态机，
但 producer 与 consumer 只能靠字符串常量约定。该状态的 owner 是
`engine_ingest.py` 内 pairing result；必须改为 private `StrEnum` 或等价的封闭 typed
contract，所有分支和 consumer 使用 enum identity，durable JSON 边界只投影 `.value`。
不得把 pairing reason 错误复用为 context sizing fallback reason。

### CTRL-AGG-02 — continuation frozen source 使用 complete/unavailable 判别联合

来源：MiMo F02。裁决：`accept`。

`_ContinuationFrozenSources` 同时承载 unavailable 与 complete 两种互斥状态，导致
complete consumer 在 guard 后用 8 个 `cast()` 绕过可选字段。必须拆成 typed
complete/unavailable variants：complete variant 的 estimator、provider/model、
policy、request semantics、context window 与 source budget 都是非 Optional；
unavailable variant 只承诺 closed reason 及可证明的 partial tool atoms。loader
继续固定 projection → tool → policy → request 的失败优先级；consumer 对联合类型
显式穷举，不能用 `cast`、`getattr`、默认值或 loose fallback 补偿。

### CTRL-AGG-03 — 拆分 reactive recovery start God method

来源：MiMo F03。裁决：`accept`。

`_StartReactiveRecoveryOperation.__call__` 是本 WU 新增的 245 行方法，同时承担 CAS、
source/candidate、sizing、hard closeout、start transition、manifest/fact 与 dispatch
projection。它违反项目对 God function 的明确约束。必须提取模块级私有 typed helper，
让 `__call__` 只负责可读编排；不得拆 transaction、改变 manifest → budget fact →
RUN_STARTED / ATTEMPT_STARTED 顺序、改变 CAS rollback 或将 lifecycle policy 下沉到
`context_budget.py`。

### CTRL-AGG-04 — provider 无 usage 的 public Host 成功终态组合测试

来源：MiMo F04。裁决：`accept`。

用户已明确把“provider 不支持返回 usage 时不比当前算法差”作为成功信号。现有测试分别
证明 missing usage resolver fallback、dispatch ordering 与 public terminal，但没有一条
测试把三者连成同一 public Host lifecycle。新增一条使用合法 scripted runner（成功但不发
usage event）的集成测试，至少证明：

- Run 达到成功终态；
- 对应 candidate 产生 `CONTEXT_BUDGET_EVALUATED`；
- `estimate_method=conservative_fallback` 且 closed reason 是 `usage_missing`；
- dispatch / terminal 不因 usage 缺失失败。

测试不得依赖真实 provider、provider 名称分支或 monkeypatch resolver 返回值。

### CTRL-AGG-05 — steer 同一 candidate 只估算一次

来源：MiMo F07。裁决：`accept`。

`admission.py` 对同一 frozen candidate 与同一 policy 先构造 pre-start sizing snapshot，
随后为 anchored fact 再调用一次 estimator。两次输入相同，第二次重算会制造不必要的双真源
机会。必须复用第一次 `BudgetEstimate`；行为、fact identity 与 decision 不变，并保留
owner-level steer 回归。

### CTRL-AGG-06 — soft/hard threshold 严格不变量统一

来源：DS F01、F04（重复 finding）。裁决：`accept-as-one`。

`ContextBudgetPolicy` 的 owner contract 是
`soft_threshold_tokens < hard_threshold_tokens`，但 `ContextSizingResult`、
`context_sizing_pressure_and_decision` 与 durable payload parser 使用 `>`，会接受
`soft == hard`。所有 result 构造、派生与 replay 边界必须统一为 strict `<`；补测试证明
typed result、matrix helper 与 durable parser 都拒绝 equality。错误文本同步表达
“soft 必须小于 hard”，不得只在下游 parser 局部修补。

### CTRL-AGG-07 — utilization basis-point 比例单一真源

来源：DS F02。裁决：`accept`。

`10_000` 在 `context_budget.py` 与 `context_events.py` 四处重复，既违反魔法数字约束，
也让 canonical payload 校验和 result owner 可能漂移。由 `context_budget.py` 拥有一个
命名 constant 或 typed calculation helper，result 构造/校验和 durable parser 全部复用；
不得在 `context_events.py` 再定义第二个同值常量。

### CTRL-AGG-08 — 删除错误 owner 下的 continuation dead fallback reasons

来源：DS F03。裁决：`accept`。

`ContextSizingFallbackReason` 的四个 `CONTINUATION_*_UNAVAILABLE` 成员没有 producer。
真实语义由 runner-call manifest 的 `RunnerCallSizingUnavailableReason` 拥有，source
不可用时 manifest 写 `UNAVAILABLE`，而不是产生 context-budget fallback fact。删除四个
dead members，并更新 exact enum/docs/tests；不得新增 consumer 让死枚举“活起来”，也不得
合并两个不同 owner 的 enum。

### CTRL-AGG-09 — compactor manifest 不得成为 usage anchor 的直接测试

来源：DS F11。裁决：`accept`。

`context_anchor.py` 会消费并排除 `compactor_identity is not None` 的 manifest/link/usage/
completion，但 resolver owner tests 的 fixture 只构造普通 manifest。补 direct test，
证明 compactor call 的 usage 既不能被选择为 anchor，也不能以 orphan evidence 误阻断正确
lineage；测试断言 resolver contract，不在 fixture 或下游消费者实现特殊补偿。

## 4. Rejected findings

### MiMo F05 — rejected-false-type-premise

`HostTransaction.fetchall()` 的精确签名就是 `tuple[HostRow, ...]`，
`_required_page_tail_sequence` 已使用同一类型；full pyright 为 0。不存在 reviewer
所述注解不匹配。

### MiMo F06 — rejected-wrong-owner-abstraction

dispatch 的 post-compact producer 与 Engine reactive recovery producer分别拥有自己的
lifecycle stage 选择；它们复用的是 `context_budget.py` 的 sizing builders，不是同一条
lifecycle state machine。把 stage → strategy 抽到 `context_budget.py` 会让纯 sizing owner
反向拥有 dispatch/recovery policy，扩大耦合。

### MiMo F08 — rejected-impossible-partial-commit-scenario

reviewer 假设“manifest 已提交、budget fact 未提交后 crash”，但相关 recovery producer 在
同一 SQLite write transaction 内写 manifest、fact 与 start transition；异常会整体 rollback。
现有 deterministic append test 已证明同 identity 复用与 conflict fail-closed，startup
recovery test证明新 continuation fact 从 matching source truth 派生。不能为原子事务不可能
暴露的半提交状态编写伪端到端测试。

### DS F05 — rejected-semantically-distinct-source-boundaries

`_runner_call_kind_and_trigger` 服务 post-start legacy `RunInputBuilder` facts，
`_prepared_candidate_kind_and_trigger` 服务 pre-start frozen candidate。review 所述
“RECOVERY → followup”与代码直接相反：RECOVERY/fallback 是 post-compaction；RESUME/
CONTINUATION 才是 followup。两个入口在各自可用的 typed provenance 上得到一致 public
manifest kind，强行让其中一个重读另一个内部对象会破坏 source ownership。

### DS F06 — rejected-future-hypothesis

当前 `ContextSizingStage` 是封闭 enum，candidate 的 compact/fallback refs 才是区分 initial
与 post-compaction 的直接 provenance；stage 本身不是 runner-call kind 的完整 owner。
不存在“未知 stage 静默进入”当前路径。为未来可能新增 enum 提前复制五分支既不修当前 defect，
也会让 stage 与 provenance 形成双真源。

### DS F07 — rejected-intentional-base-fallback-contract

两个 conservative builder 的默认 `USAGE_MISSING` 正是“没有可信 anchor 时使用当前完整输入
原算法”的 base contract。特殊的 accepted-compact invalidation producer已经显式传 reason；
admission/wait continuation 的初始 conservative snapshot 则有意使用 base reason。删除默认值
只增加调用样板，不改变或强化现有语义。

### DS F08 — rejected-behaviorally-equivalent-and-out-of-scope

当前 threshold ratio 与 context window 都是正值，`int(positive_float)` 与
`math.floor(positive_float)` 行为相同；review 没有当前分歧输入。policy 配置转换与 sizing
frozen-atom helper 也不应为纯风格统一互相依赖。

### DS F09 — rejected-overbroad-and-partly-false

review 以 `test_context_anchor.py` 中未出现 enum 名称推断零覆盖，但
`PREDICTION_NON_POSITIVE` 与 `ARITHMETIC_RANGE_INVALID` 已由
`test_context_budget.py` 的 owner-level参数化测试直接覆盖；invalid/incomplete lineage、
missing usage、compatibility mismatch 与 compact invalidation也已有 direct tests。
本 gate 只接受证据明确缺失且业务关键的 compactor exclusion（CTRL-AGG-09），不机械为每个
enum 值复制 resolver fixture。

### DS F10 — rejected-redundant-cartesian-roundtrip

五阶段 × 三压力的 15 格行为已由唯一 matrix owner 全覆盖；payload builder/parser 对这些
enum 没有按组合分支，已有代表性五格 roundtrip 与 strict corruption tests。扩展到 15 个
roundtrip 只重复同一序列化路径，不能捕获新的 branch。

### DS F12 — rejected-misclassified-active-api

`DurableRunnerCallManifestRecorder` 仍由 ordinary tool/no-tool `RunInputBuilder` 生产调用，
不是 reviewer 所述“似乎无 caller 的旧 placeholder”。在该 post-start边界无法重新证明
pre-start context sizing，写 typed `UNAVAILABLE + ORDINARY` 是保守 contract；添加“old API”
注释反而会错误描述当前调用图。

## 5. Open questions and residual risk adjudication

- wait failed/lost terminal summary、超长未 compact Session scan 性能、多进程 append、
  真实 provider smoke 与外部 provider physical behavior 都没有本 WU regression 的直接
  证据；不转化为本 gate implementation obligation。
- fresh schema only 是用户明确约束，不是 residual defect。
- `RunnerCallSizingUnavailableReason` 与 `ContextSizingFallbackReason` 保持两个 owner；
  CTRL-AGG-08 删除错误重叠后边界更清晰。
- public no-usage lifecycle 的组合风险由 CTRL-AGG-04 关闭；long-session performance
  保留为非 blocking residual risk。

## 6. Required fix scope and validation

AgentCodex 只允许修改 accepted findings 直接需要的 production/test/README 与新的 fix
artifact。不得修改两个 reviewer artifact、本 Controller adjudication 或 Controller control
doc；不得顺带实现 rejected/deferred 建议。

至少执行：

```bash
source .venv/bin/activate
pytest -q <all directly affected owner and integration tests>
pytest -q tests/host
python -m pyright dayu/ tests/ utils/
git diff --check
```

还必须：

- 相对 `fad15d39` 做 changed-file allowlist 与 stale-symbol audit；
- 对 aggregate WU 全部 changed production Python 文件重新证明 branch coverage `>=80%`；
- 按 README 触发规则审计 `dayu/host/README.md` 与 `tests/README.md`，只在稳定职责内容变化时修改；
- fix artifact 逐项映射 `CTRL-AGG-01..09`、给出测试命令/结果、coverage 与 residual risk。

## 7. Decision

**`needs-fix`**

AgentCodex 完成 `CTRL-AGG-01..09` 后，由 AgentMiMo、AgentDS 相对
`5afe71fe..working-tree` 并行执行 aggregate implementation re-review。两路都必须核对
accepted finding closure、全 WU cross-slice contract 与是否引入新 actionable finding；
Controller 再作 final aggregate adjudication。不得在 re-review 通过前创建 accepted
aggregate commit、push 或 draft PR。
