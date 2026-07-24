# WU-CTX-01 Plan Re-review Controller Adjudication

## Gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- gate：`plan re-review`
- revised plan：`docs/reviews/wu-ctx-01-plan-codex.md`
- fix artifact：`docs/reviews/wu-ctx-01-plan-fix-codex.md`
- AgentMiMo re-review：
  `docs/reviews/plan-review-20260723-215308.md`
- AgentDS re-review：
  `docs/reviews/plan-review-20260723-215320.md`
- Controller decision：`pass`
- blocking findings：None
- next gate：`accepted plan commit`

## Controller decision

两路 re-review 都基于 production 直接证据确认修订计划已达到
code-generation-ready：

- AgentMiMo verdict=`pass-with-risks`；
- AgentDS verdict=`PASS`；
- 两路都确认 9 个 Controller accepted findings 已修复；
- 两路都确认 4 个 rejected-with-reason findings 无新证据需要重开；
- 两路都没有 blocking new finding。

计划继续保持 3 个 implementation slices，并保持以下两个修改独立：

1. provider-neutral usage-anchored adaptive sizing；
2. 即使完全没有 usage anchor 也成立的
   `CONTEXT_BUDGET_EVALUATED`、ordering/idempotency 与 Host→Service typed
   projection。

两项修改共享 Host-owned `ContextSizingResult` 是单一语义真源要求，不构成重新耦合。

## Accepted finding final status

| finding | Controller final status | re-review evidence |
|---|---|---|
| DS-01 | 已修复 | sizing 只消费 identity-free complete candidate；仅 allow 后同事务生成并由 manifest/start transition 消费同一 identity；soft/hard 零 manifest 与 Attempt identity。 |
| CTRL-PR-001 | 已修复 | `StartGovernedRunInput` 已是 caller-owned exact interface；`run_transition.py` 不修改并有静态零 diff gate。 |
| DS-02 | 已修复 | precondition miss 通过 private exception 触发整笔 rollback；low-level CAS lost 沿既有 `HostDurableError` rollback 并传播；测试断言零孤立 payload/event/state。 |
| DS-03 | 已修复 | strict manifest + accepted link + unique valid usage + durable accepted `ITERATION_COMPLETED` preview 四证据 conjunction；Run/Attempt terminal 不补洞。 |
| DS-04 | 已修复 | 保持 estimator 公式/常量和无 usage fallback 语义，不承诺旧 subset 数值；complete candidate 有不低估、单次计数和 threshold-crossing 验收。 |
| DS-05 | 已修复 | resolver 显式接收 `HostTransaction`、`EventLogStore` 与 typed query；全部分页在同一 transaction snapshot；无隐式 store/cache。 |
| DS-06 | 已修复 | 仅 policy 存在且 usage 缺失时产生 conservative fact/activity；policy 缺失保持 no-budget/no-fact path。 |
| MIMO-001 | 已修复 | manifest-before-start 的 producer/consumer、public stream、Tool Trace、projection、recovery、outbox 与 terminal/lifecycle ordering 已进入 allowed scope 和验证矩阵。 |
| MIMO-003 | 已修复 | continuation projection、selected tool schema、policy 与 request semantics 都有唯一 frozen source；四类缺源 closed unavailable + fallback，禁止当前 config 重选。 |

## Rejected finding re-open decision

| finding | Controller decision | reason |
|---|---|---|
| DS-07 | 不重开 | Service closed-enum exhaustive mapper 与 fail-closed contract 已冻结；私有 helper 名称不是 public contract。 |
| DS-08 | 不重开 | `supports_stream_usage` 只作为 request serialization semantics atom；实际 usage presence 仍是唯一 eligibility 信号。 |
| MIMO-002 | 不重开 | per-Session execution owner与同一 Host transaction snapshot 使跨 transaction scan 反例不适用；实现若跨 transaction 分页即触发 stop。 |
| MIMO-004 | 不重开 | manifest sizing snapshot 不包含后选 estimate method；input snapshot digest、manifest digest 与 budget fact identity 职责已分离。 |

## New finding adjudication

| finding | Controller decision | reason / owner |
|---|---|---|
| MiMo NEW-001 | non-actionable / covered | continuation tool-schema payload 缺失或损坏已由 closed unavailable + complete conservative fallback 覆盖，并进入 Slice 3 crash-source tests。 |
| MiMo NEW-002 | non-actionable / covered | deterministic estimator、strict payload equality、same-identity conflict fail-closed 与 idempotency tests 已冻结。 |
| MiMo NEW-003 | non-actionable / covered | Slice 3 可单独回滚到 Slice 2 conservative-only contract 已在 slice rationale 明确；不是未决实现语义。 |
| DS-NEW-01 | evidence invalid / no gap | `NoBudgetDispatchStart` tagged union 与 `sizing_snapshot=unavailable` 已阻止 policy-missing manifest 成为 anchor；没有 sizing identity 混用。 |
| DS-NEW-02 | accepted as covered low implementation risk | 删除 display-text estimator 后的 diagnostic consumer 由 Slice 1 consumer scope和 `rg` 零命中 audit 承接；无需再改 plan。 |

没有 new finding 需要再次进入 fix/re-review loop。

## Gate acceptance

以下 implementation handoff 已冻结：

- Slice 1：complete candidate、estimator identity、manifest v2 direct pairing、
  allow-only identity allocation/consumption、continuation frozen source 与完整
  consumer ordering；
- Slice 2：完全无 anchor 也成立的 conservative-only canonical fact、
  same-transaction ordering/idempotency、Host public view 与 Service typed
  pass-through；
- Slice 3：provider-neutral durable anchor resolver 与 signed-delta adaptive sizing
  integration。

不得在 implementation 中新增 provider-name branch、tokenizer/count adapter、
candidate table、completion truth、compatibility shim、动态 ratio 或 UI 展示逻辑。
任一 slice 命中其 stop condition时必须回到 Controller，不得自行扩 scope。

## Validation

- Controller 已完整读取修订 plan、fix artifact 与两份 re-review artifacts。
- 两路 reviewer 都独立核对了 `StartGovernedRunInput`、transaction rollback、
  durable `ITERATION_COMPLETED`、当前 subset estimator 和 continuation manifest
  直接代码证据。
- 本 gate 只修改 Markdown artifacts/control bookkeeping，不运行代码测试或 pyright。
- `git diff --check` 在 accepted plan commit 前必须通过。

## Completion

- status：`complete`
- decision：`pass`
- blocking questions：None
- residual risks：均已分类，由各 slice stop conditions、tests、static audits 或既有
  fallback 承接
- next entry point：Controller 创建 protected local accepted plan commit，然后派发
  AgentCodex 实施 Slice 1
