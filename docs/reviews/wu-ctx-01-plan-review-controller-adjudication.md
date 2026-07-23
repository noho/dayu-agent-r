# WU-CTX-01 Plan Review Controller Adjudication

## Gate

- Work Unit：`WU-CTX-01`
- gate：`plan review`
- reviewed plan：`docs/reviews/wu-ctx-01-plan-codex.md`
- AgentDS review：`docs/reviews/plan-review-20260723-211859.md`
- AgentMiMo review：`docs/reviews/plan-review-20260723-212146.md`
- decision：`needs-fix`
- next entry point：`fix`

## 总体裁决

Plan 的目标、owner、两个独立修改和 3-slice 切分成立：

1. exact candidate / manifest / pairing foundation；
2. 不依赖 usage anchor 的 `CONTEXT_BUDGET_EVALUATED` + Host -> Service typed
   projection；
3. provider-neutral adaptive anchor integration。

该切分按语义闭环、依赖顺序和回滚风险形成，没有按文件或 reviewer ownership
机械拆分，也没有超过 control doc 默认上限。两项修改共享同一个 Host-owned
`ContextSizingResult` 是必要同源，不构成重新耦合。

当前 plan 尚不能直接交给 implementation。主要缺口是 pre-start candidate、
Attempt identity、manifest 与 start CAS transaction 的线性时序尚未冻结；此外，
iteration success evidence、continuation manifest source 和 conservative complete-input
行为变化仍需收敛。

## Finding 裁决

| Finding | 裁决 | Controller 理由与 required fix |
|---|---|---|
| DS-01 | `accepted` | 现有 start transition 在事务内生成 Attempt / execution identity，而 plan 又要求 allow candidate 的 manifest 在 `RUN_STARTED` 前携带这些 identity。Plan 必须冻结线性方案：sizing 不依赖 manifest；decision 为 allow 后，在同一 write transaction 内生成实际将被 start transition 消费的 identity，随后写 manifest / budget fact / start facts。compact/block candidate 不生成 runner-call manifest或未消费的 durable Attempt identity。不得引入新 durable candidate table 或兼容 shim。 |
| CTRL-PR-001 | `accepted` | DS-01 的正确方案若让 start transition 消费预生成 identity，预计必须触及 `dayu/host/durable/run_transition.py` 及 owner tests；当前 Slice 1 allowed files/tests 未包含该 owner。Fix 必须列出 exact transition interface、allowed file 与 tests，或给出不修改该 owner也能保证同一 identity 被实际消费的直接代码证据。 |
| DS-02 | `accepted` | Plan 只提出模糊 sentinel，未说明怎样让 CAS miss 不 commit 已 append 的 manifest/fact。Fix 必须选择一个具体 transaction 方案，说明 CAS/precondition、identity allocation、append ordering、rollback/normal return 与 caller handling；测试必须断言 CAS miss 后 EventLog 零孤立 manifest/fact。 |
| DS-03 | `accepted` | Plan 要求 “completed iteration” 却没有给出 durable eligibility predicate。Fix 必须基于现有 manifest/link/usage/Engine event/Run facts定义成功 ordinary runner-call evidence；若现有 durable evidence不足，应 fallback，而不是新增未经设计的 completion truth或从时间推断。tool loop、usage先到后失败、crash gap 和 terminal Run 都要有反例。 |
| DS-04 | `accepted` | complete candidate 会让 estimator 输入包含当前 subset 路径没有覆盖的 system/tool-schema/structured atoms，不能再表述为 “existing conservative behavior 保持不变”。Fix 必须说明保持的是 estimator公式与无 usage fallback，不是 token数逐值兼容；加入 complete-input范围扩大、threshold crossing和不低估回归验收。 |
| DS-05 | `accepted` | `context_anchor.py` 的 durable read interface尚未冻结。Fix 必须使用显式 typed 参数/transaction boundary，禁止模块级可变状态、隐式 singleton或 Service/UI 访问 durable store；同时说明 resolver 在同一 consistent transaction snapshot 内读取。 |
| DS-06 | `accepted` | Slice 2 assertion 必须限定为“policy存在但usage缺失”；policy缺失继续不产生 sizing fact/activity并保持既有 no-budget governance path。 |
| DS-07 | `rejected-with-reason` | Plan 已要求 Service 对 kind、estimate method、pressure 做 exhaustive closed-enum mapping并在未知值时 fail closed；固定私有 helper 名称不是 public contract，也不是 implementation agent 需要重新设计的语义。 |
| DS-08 | `rejected-with-reason` | `supports_stream_usage` 改变是否发送 `stream_options.include_usage`，属于 request serialization semantics。把它纳入 compatibility digest只会保守失效并 fallback，不等于按 capability猜 usage presence；这与设计中“request semantics改变使anchor失效”一致。 |
| MIMO-001 | `accepted` | 与 DS-01/DS-02 同属 pre-start ordering 风险，但有独立 consumer blast-radius价值。Fix 必须列出所有读取 `RUNNER_CALL_INPUT_ASSEMBLED` 或依赖 event ordering 的 production/tests，并说明 manifest-before-start 对 public stream、recovery、projection、Tool Trace 和 terminal/lifecycle consumers 的影响；遗漏 production consumer 时不得把它排除出 allowed files。 |
| MIMO-002 | `rejected-with-reason` | PR 182 已建立 strict-native per-Session execution owner；resolver还必须按 accepted DS-05 在单个 Host transaction snapshot内读取。另一个 scheduler在同一 resolver scan中提交该 Session compact的反例不成立。若实现跨 transaction 分页，则违反本裁决并必须停止。 |
| MIMO-003 | `accepted` | Engine continuation 的 complete manifest 不能只写“可重建时 complete”。Fix 必须冻结 selected tool schema、policy、request semantics与projection的唯一来源；crash/recovery无法直接重建时写 closed unavailable reason并fallback，不从当前 effective config重选。 |
| MIMO-004 | `rejected-with-reason` | Plan 的 manifest `sizing_snapshot`只冻结 conservative estimate/contract，不包含后来选择的 anchored/fallback method；同一 candidate 因 method变化导致 manifest digest变化的反例不符合 plan schema。`input_snapshot_digest` 与 manifest digest 的不同用途已足以从字段定义判断，不构成 material blocker。 |

## Fix 要求

AgentCodex 只修改原 plan artifact，并必须：

- 保持 3 slices 和两个独立修改，不借 findings 扩成新 durable table、provider
  adapter、completion state machine或额外 UI。
- 在 Slice 1 冻结 candidate -> sizing -> allow identity allocation -> manifest ->
  budget fact -> start transition 的 exact call path；soft/hard candidate不写
  runner-call manifest。
- 明确 CAS miss 的 transaction rollback机制和 owner tests。
- 定义 usage anchor 的 durable success / barrier predicate，不以 preview 文案、时间戳、
  request id或 provider name替代证据。
- 明确 continuation manifest的 frozen source。
- 明确 complete-input conservative fallback是“同一算法、完整输入”，不承诺与旧
  subset token数相等。
- 补齐 event-ordering consumer audit、allowed files/tests与 policy-none assertions。
- 逐项回写 accepted/rejected finding状态；不得实施代码。

## Residual Risks

- manifest v2 与 pre-start candidate refactor 的改动半径仍较大，但由 Slice 1 owner
  tests、consumer audit和 stop conditions承接。
- complete-input conservative estimate可能比旧 subset estimate更大；这是当前
  WU 的安全性目标，不是无 usage provider退化，但必须用阈值行为测试证明。
- schema v2 只支持全新数据库；旧 workspace不兼容是项目已接受政策。
- live provider差异仍是 non-blocking risk，owner为 provider-neutral usage-present /
  usage-absent contract tests。

所有 residual risks 均已分类；blocking open questions 将由 plan fix 收敛。
