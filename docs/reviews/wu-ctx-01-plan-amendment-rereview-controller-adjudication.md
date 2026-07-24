# WU-CTX-01 Slice 1 Plan Amendment Re-Review Controller Adjudication

## 0. Gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- gate：`plan amendment re-review`
- Controller：AgentController
- reviewed amendment：
  `docs/reviews/wu-ctx-01-slice-1-plan-amendment-codex.md`
- reviewed plan：
  `docs/reviews/wu-ctx-01-plan-codex.md`
- AgentDS review：
  `docs/reviews/plan-review-20260723-231956.md`
- AgentMiMo review：
  `docs/reviews/plan-review-20260723-232040.md`
- decision：`pass`
- blocking questions：`None`
- partial implementation status：`not accepted`

## 1. First-principles judgment

两路 reviewer 均以 production 直接证据确认两个原 blocker 成立，并一致判定 amendment
已在正确 owner 关闭：

1. persisted compact coverage 由 `compact_payload` strict typed boundary 拆分为
   `current_input_ref` 与 `compacted_source_refs`，Conversation Memory 是
   `selected_recent_window` 删除 covered raw、保留 post-compact delta 的唯一 owner；
   RunInput 不增加第二套 coverage filter。
2. `pressure_level` 只表达预测值与阈值的比较，实际 action 消费 sizing stage；
   ordinary / post-compact / dispatch-fallback 的 9-cell matrix、soft pressure 保真、
   hard terminal closeout 与同 snapshot 单 proactive operation 已冻结。

用户提示的两个产品修改仍保持独立：Slice 1 只建立 complete candidate、保守估算、
stage-aware action 与 direct pairing foundation；Slice 2 独立增加
`CONTEXT_BUDGET_EVALUATED` canonical fact / public projection；Slice 3 才引入 usage
anchor 与新 `context_budget` 估算算法。provider 不返回 usage 时仍走当前 complete
candidate 的 conservative fallback。

## 2. Controller direct-evidence reconciliation

- `compact_payload.py::source_boundary_refs` 当前按
  `current_input_ref -> material/evidence/fact refs` 顺序写入并用
  `dict.fromkeys` 保序去重；typed parser 可以且只能在 owner boundary 一次性拆分角色。
- `SelectedRecentWindowItem` 的 production exact fields 确为
  `event_id: str` 与 `source_refs: tuple[str, ...]`；plan §5.8 已精确定义 canonical
  source set 为 `event_id + source_refs`。
- plan §5.5 已明确要求 `ContextSizingResult.__post_init__` 先独立复核 pressure，再用
  `stage + pressure` 复核 action；§8.2 同时要求 producer 采用 stage-aware action，
  因而 producer / validator 同源不是未定义 contract。
- plan §6.5 已明确禁止继续返回模糊的
  `PendingDispatchRecord | None`，要求 closed outcome 只能表达 pending dispatch 或
  terminal notice，并冻结 `fail_unstarted_run_in_transaction` 为 hard closeout owner。
  production 已有 `_GovernanceStageResult` /
  `_ProactiveCompactionExecutionResult` 的 pending + terminal typed pattern；是否复用或
  定义更窄 private result type 是实现组织，不是新的业务语义。
- plan §9 的 source-boundary static audit 已明确：raw `source_boundary_refs` 只能由
  `compact_payload` owner 读取；RunInput 出现 raw-list reader 即失败。

## 3. Finding adjudication

| finding | disposition | Controller reason |
| --- | --- | --- |
| DS-3-1：必须冻结两个 private helper 的精确函数名/签名 | `rejected-with-reason` | plan 已冻结 pressure 与 action 的输入、输出、9-cell total function以及 `__post_init__` 的两阶段校验。私有 helper 是拆成两个函数还是单函数内分段，不改变 owner contract；强制命名会把实现组织误当业务语义。producer 与 validator 同步更新保留为 Slice 1 必测 checkpoint。 |
| DS-3-2：closed terminal outcome 缺 exact method signature | `rejected-with-reason` | plan §6.5 已明确返回语义、禁止的旧 union、terminal transition owner、transaction/notifier boundary和 post-compact/fallback 差异；production 也已有 pending + terminal typed result pattern。要求额外冻结 private tagged-union 名称没有 correctness 增益。 |
| DS-3-3：`__post_init__` split validation 未给代码 | `rejected-with-reason` | plan §5.5 已逐步规定先复核 pressure、再复核 `stage + pressure` action；code-generation-ready 不等于在计划复制 production 代码。9-cell constructor tests 是 acceptance 条件。 |
| DS-3-4：增加 raw function import-boundary test | `rejected-with-reason` | raw-list consumer 已由 owner contract、consumer audit与 static grep覆盖；用 `__all__` 或私有命名不能证明 Python consumer 没有索引 payload，反而固化无效实现约束。 |
| DS-3-5：`SelectedRecentWindowItem` 字段未确定 | `rejected-as-false` | production exact fields 与 plan 均明确为 `event_id`、`source_refs`；不存在字段歧义。 |
| MIMO-01：plan 未要求 `__post_init__` stage-aware | `rejected-as-false` | plan §5.5 明文要求 pressure/action 分离校验；review finding 的反例已被该条 contract直接覆盖。 |
| MIMO-02：plan 未指出 hard `return None` 修改点 | `rejected-as-false` | plan §6.5 明文禁止 `PendingDispatchRecord | None` 混淆 hard 与 CAS miss，§8.2 exact change 8要求 closed terminal outcome并复用既有 failure owner。 |
| MIMO-03：producer 未要求消费 stage | `rejected-as-duplicate` | plan §5.5 的 action total function与§8.2 exact change 3均明确 action 按 stage 派生；与 DS-3-1 同一已覆盖风险。 |

两路 review 没有发现新的 architecture、schema、ownership、slice boundary 或
allowlist blocker。所有被驳回项均不授权 implementation agent 改写 plan contract；
以下 implementation checkpoints 仍为强制验收条件：

- producer 与 `ContextSizingResult.__post_init__` 必须消费同一 stage-aware action真源；
- 9-cell constructor/action matrix必须穷举验证；
- post-compact/fallback hard必须在当前 transaction写Run terminal fact并产生typed
  terminal notice，零 dispatch record、零 silent accepted Run；
- post-compact/fallback soft必须允许dispatch但保留soft pressure；
- current input、uncovered protected raw与new delta保留，covered older raw删除；
  rebuild/incremental/repair/reload同源。

## 4. Scope and gate decision

- design amendment：`accepted`
- revised 3-slice plan：`accepted`
- plan fix：`not required`
- 两项产品修改独立性：`preserved`
- implementation slices：仍为 `3`
- expanded Slice 1 owner scope：`accepted`
- partial production/tests：仍为 `not accepted`

下一步先创建只包含本次 design/plan/amendment/review/controller/control artifacts 的
protected local plan-amendment commit；不得把 partial production/tests 混入该提交。
随后更新 control doc 并由 AgentCodex恢复 Slice 1 implementation。

## 5. Residual risks

| risk | classification / owner |
| --- | --- |
| partial implementation仍有失败测试、fixture migration、rollback/manifest matrix与coverage未完成 | resumed Slice 1 implementation；通过完整 focused tests、full pyright与per-file coverage关闭 |
| private closed outcome 的具体代码组织可能扩大 caller diff | Slice 1 implementation detail；优先复用现有 pending + terminal typed pattern，不改变业务 contract |
| compacted refs 与 selected recent source set若出现 production 证据不一致 | Slice 1 stop condition；不得在RunInput或fixture补偿 |
| README职责是否实际命中 | Slice 1先读目标README约束后裁决并记录 |

没有未分类 residual risk，没有 blocking question。
