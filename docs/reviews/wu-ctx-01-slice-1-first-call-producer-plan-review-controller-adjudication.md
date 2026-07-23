# WU-CTX-01 Slice 1 first-call producer 第三次计划评审 Controller 裁决

## 1. 裁决范围

- 目标 plan：`docs/reviews/wu-ctx-01-plan-codex.md`
- amendment handoff：
  `docs/reviews/wu-ctx-01-slice-1-first-call-producer-plan-amendment-codex.md`
- MiMo review：`docs/reviews/plan-review-20260724-014131.md`
- DS review：`docs/reviews/plan-review-20260724-014307.md`
- design truth：`docs/host/design.md` §25
- production evidence：
  `dayu/host/run_input.py`、`dayu/host/admission.py`、
  `dayu/host/waiting.py`、`dayu/host/dispatch.py`、
  `dayu/host/durable/run_transition.py`、`dayu/host/open_host.py`

本裁决只判断 plan 是否已经可以无临场架构发明地生成代码，不接受“partial
implementation 尚未完成”本身作为 plan finding。

## 2. 总结论

结论：`needs-fix`。

第三次 amendment 已正确补齐 pending producer 双向总表、closed
`CONTINUATION` 与 5-stage/15-cell 目标语义，steer/wait 所在 transaction 也具备
在 start 前写 candidate/manifest 的原子性基础。但以下三项 correctness blocker
尚未闭合：

1. startup strict source loader 仍要求调用者先提供 `PolicySnapshot`，而 plan 又要求
   policy 从尚未 strict-load 的 source candidate 取得，形成循环依赖；
2. direct queue promotion 若只删除 admission caller，仍会留下可直接创建
   `RUN_STARTED`/`ATTEMPT_STARTED`/pending row 的 production transition；
3. plan 多处把 `ResolveWaitFailedOutcome` 纳入 resume continuity，但 production
   `waiting.py` 明确将 failed outcome 交给 terminal failure owner，只有 completed /
   cancelled 创建 resume Attempt。

这些问题必须由 AgentCodex 修订 plan 后再进入定向双路 plan re-review；当前不得恢复
Slice 1 implementation。

## 3. Review finding 裁决

### 3.1 MiMo findings

| finding | disposition | Controller 理由 |
| --- | --- | --- |
| MiMo-01 startup policy source | **accept / blocking** | `load_prepared_runner_call_source_in_transaction(..., policy_snapshot=...)` 无法同时满足“source candidate 是 policy 真源”。source Run 当前 `input_event_id` 指向 exact `USER_INPUT_ACCEPTED`，应先由共享 strict helper 从该 event 的 `effective_execution_config` 重建 typed policy，再加载并校验 candidate。scanner 不得接收 current policy。 |
| MiMo-02 enum/total function 尚未实现 | **reject as plan finding；merge DS-PR-001 guard** | “尚未实现”不是 plan finding；但实现必须显式穷举 closed 5-stage/15-cell，不能依赖 default fall-through。 |
| MiMo-03 steer policy parse 时序 | **accept clarification** | steer 已持有刚 append 的 `input_event` row 与 payload，无需 commit 后回读。plan 必须固定：append event 后直接 strict parse 同一 payload，再 prepare candidate；禁止 current config fallback。 |
| MiMo-04 wait planned/committed refs | **accept verification requirement** | deterministic `event_plan.tool_result_event_id` 会成为同 transaction 后续 committed event id，设计可行；需明确两条 projection path 使用同一 id，并以 owner test 断言 candidate digest 相同。 |
| MiMo-05 context policy wiring | **reject** | `OpenHostOptions.context_budget_policy -> HostLocalExecutionOptions.context_budget_policy` 已有直接 composition 路径，不需要新增 public option。 |
| MiMo-06 Engine continuation candidate payload | **reject with clarification** | Engine continuation 不是 worker first-call consumer；它从 accepted complete observed projection 写 limited-signal manifest，不应伪造 `PreparedRunnerCallCandidate`。plan 只需明确该路径不调用 pre-start candidate recorder。 |

### 3.2 DS findings

| finding | disposition | Controller 理由 |
| --- | --- | --- |
| DS-PR-001 exhaustive match | **accept** | 5-stage 是 closed state machine；实现必须显式覆盖每个 stage，unknown value fail closed，不能靠 generic else 恰好得到目标 action。 |
| DS-PR-002 `source_refs` construction sites | **accept** | `SessionContinuityView.source_refs` 是 required contract；plan 必须要求全 construction-site 审计，ordinary 显式传 `()`，不得增加默认值。 |
| DS-PR-003 queue promotion | **accept / blocking，强化** | 不能只删 `HostAdmissionService.promote_next_queued_run` caller 后把 direct transition 留成 production dead bypass。必须删除 admission method/operation、`promote_queued_run_in_transaction` 及仅服务该旁路的 typed inputs/exports，并迁移 tests 到 scheduler ordinary governance；因此撤销 `run_transition.py` 零 diff 承诺。 |
| DS-PR-004 allowlist duplicates | **accept** | focused list 去重；但 Slice 1 completion gate 仍是完整 `pytest tests/host -q`，allowlist 不能替代 full Host。 |
| DS-PR-005 recorder bare identity | **reject value-object expansion** | recorder owner-local runtime validation + producer 同一 locals 足以闭合；为两个字符串新增 value object 是过度设计。plan 应要求 identity mismatch fail closed 和 tests，不引入新 bag/type。 |
| DS-PR-006 wait payload projection | **accept clarification** | `run_input` 必须复用 existing accepted-result strict projection，而不是 loose parse arbitrary mapping；只覆盖 production 可 resume 的 completed/cancelled。 |
| DS-PR-007 steer rollback/idempotency | **reject** | 第一次 transaction rollback 后没有 durable duplicate；重试新 event id 不改变业务语义，现有 transaction-local idempotency record 与 CAS 足够。不得为了无 committed fact 的重试引入额外 deterministic-id coupling。 |
| DS-PR-008 source helper用途 | **accept，纳入 startup blocker 修复** | source helper 是 existing candidate loader 的严格超集；policy 必须先从 exact source input fact strict 重建，旧 loader 委托 source helper并校验 caller policy identity。 |
| DS-PR-009 “第三项产品修改” | **reject** | compact source boundary / memory pruning 是 exact candidate foundation 对既有 design truth 的 owner 修复，不新增 WU 的第三个 public product contract。plan 可保留“两项独立产品修改 + 必要 owner 修复”的准确表述。 |

## 4. Controller 新增 findings

### CTRL-PR-01-未修复-高-failed wait 被错误纳入 resume eligibility

- 直接证据：
  `DefaultHostResolveWaitService._resolve_in_transaction` 只把
  `ResolveWaitCompletedOutcome` 与 `ResolveWaitCancelledOutcome` 交给
  `_resolve_resume`；`ResolveWaitFailedOutcome` 交给 `_resolve_failed`，后者调用
  `fail_run_from_waiting_in_transaction` 收口 Run。
- 反例：若 failed wait 也冻结 continuation manifest，transaction 随后不会创建
  resume Attempt/pending row，留下与 terminal truth 冲突的 runner-call candidate。
- required fix：
  - `CONTINUATION` wait eligibility 只写 completed/cancelled resume；
  - `project_wait_resume_continuity` 只投影 completed/cancelled accepted result；
  - 删除 plan/handoff/test matrix 中所有 “completed/failed/cancelled resume”；
  - 增加 failed/lost outcome 零 manifest、零 new Attempt、原 terminal owner不变的反例。

### CTRL-PR-02-未修复-高-source policy strict load 循环依赖

- 直接证据：
  `_prepared_candidate_from_json(..., policy_snapshot=...)` 必须先取得 typed policy 才能
  digest-verify candidate；candidate payload只保存 policy ref/digest，不保存可独立
  重建的完整 policy。
- required fix：
  - 新增/指定 run_input-owned strict helper，从 source `RunRow.input_event_id` 指向的
    exact `USER_INPUT_ACCEPTED.effective_execution_config` 经现有共享 parser 重建
    `PolicySnapshot`；
  - helper 必须验证 input event 的 Session/Run/type/identity，并验证重建 policy 与
    manifest/candidate ref/digest/request-semantics一致；
  - startup、wait、Engine frozen-source consumers复用该 helper；
  - worker existing loader仍可接收 attempt-frozen policy，但必须委托同一 strict
    source loader并额外比较 policy identity；
  - 禁止 current opener policy、current config、candidate raw digest 反向构造 policy。

### CTRL-PR-03-未修复-高-direct queue promotion production bypass 未彻底删除

- 直接证据：
  `promote_queued_run_in_transaction` 本身会直接 append start facts、插入 Attempt 与
  pending dispatch；当前 production caller 虽只有 admission method，但只删 caller 会
  留下仍可绕过 governance 的 production API。
- required fix：
  - 删除 admission direct method/operation；
  - 删除 durable direct transition、专属 request/result/validation/export 与仅覆盖该
    旁路的 tests；
  - queue promotion 唯一路径为 scheduler `_read_startable_run` 选择 earliest queued
    后执行 ordinary candidate/sizing/manifest/start；
  - 保留 terminal/recovery `wake_queue_promotion` 语义，它只唤醒 scheduler，不直接
    promotion；
  - 将 `run_transition.py` 加入 Slice 1 production allowlist，并取消“零 diff”承诺。

### CTRL-PR-04-未修复-中-startup sizing/fact 用词跨 Slice 混淆

- Slice 1 只能复用 source candidate 与 sizing atoms，并把 stage 重绑定为
  `CONTINUATION`；此时尚无 `CONTEXT_BUDGET_EVALUATED`。
- Slice 2 才从 matching source manifest/fact 读取 canonical sizing atoms，以
  `CONTINUATION` 重新派生 action并追加 **new Attempt 的新 fact**。不得复用 source
  fact identity，也不得在 Slice 1 要求 fact 存在。
- Slice 3 才允许 eligible complete candidate 使用 usage anchor；三项顺序不得混写。

## 5. 必须修订的 plan 内容

AgentCodex 下一轮只允许修改 design/plan/amendment handoff，不得触碰 partial
production/tests/control doc：

1. 收敛 exact policy source helper、调用关系、failure matrix与 tests；
2. 把 wait resume closed set 修正为 completed/cancelled；
3. 明确彻底删除 direct queue promotion，允许 `run_transition.py` diff并迁移 tests；
4. 要求 5-stage显式穷举、`source_refs` 全 callsite 审计、focused list 去重；
5. 明确 planned/committed wait ref deterministic equality与 Engine limited manifest
   非 pre-start candidate recorder；
6. 消除 Slice 1 sizing / Slice 2 fact / Slice 3 anchor 的跨 Slice混写；
7. 保持用户两点提示：
   `CONTEXT_BUDGET_EVALUATED` 与 anchor estimate algorithm 独立；
   provider usage 缺失时 Slice 3 回退现有 conservative estimator，绝不劣于当前算法。

## 6. 下一 gate

修订完成后，AgentMiMo 与 AgentDS 只复审本裁决四项新增 finding及各自 accepted
finding。两路均无 blocking finding，Controller 才可提交 protected plan amendment
commit并恢复 Slice 1 implementation。
