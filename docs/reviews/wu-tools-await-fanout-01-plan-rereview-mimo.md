# WU-TOOLS-AWAIT-FANOUT-01 Plan Re-Review — AgentMiMo

## Review Target

- Plan artifact: `docs/host/wu-tools-await-fanout-01-plan.md`
- Plan fix artifact: `docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md`
- Prior review artifacts:
  - `docs/reviews/wu-tools-await-fanout-01-plan-review-mimo.md`
  - `docs/reviews/wu-tools-await-fanout-01-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-tools-await-fanout-01-plan-review-controller-adjudication.md`
- Work unit: WU-TOOLS-AWAIT-FANOUT-01 / GitHub Issue #111
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`

## Re-Review Decision

**pass**

## Accepted Findings Status

| Finding | Source | Status | Evidence |
|---|---|---|---|
| MIMO-01: `AWAITING_FANOUT` 当前可达性被高估 | AgentMiMo | **fixed** | Plan §1 明确 "当前 Host ToolRuntime production path 中，同一 batch 的第一个 `ToolAwaitingOutcome` 会让后续 calls 返回 `run_suspended_by_tool_awaiting` governed failure"；§8 Defensive Waiter Fanout 明确 "它是防御性 Host internal state，不是当前 Engine / ToolRuntime production end-to-end 必达路径"。Root cause 已收敛为 accepted awaiting 后 duplicate terminal marker 清理状态缺口。 |
| MIMO-02 / DS-F02: `DuplicateDecision` 字段互斥语义不明确 | AgentMiMo / AgentDS | **fixed** | Plan §7 Internal Contract 明确 "普通 completed / failed / cancelled duplicate reuse 使用现有 `prior_outcome`，且 `prior_awaiting_outcome=None`、`prior_wait_id=None`。防御性 `AWAITING_FANOUT` 使用 `prior_awaiting_outcome` 和 `prior_wait_id`，且 `prior_outcome=None`；awaiting 中间态不得伪装成普通 completed-result reuse。" |
| MIMO-03: Resume material 修改位置不具体 | AgentMiMo | **fixed** | Plan §8 Resolve Wait 后 Resume Material 明确 "在当前已有行之后追加自解释说明，不替换既有 result projection"，并给出完整示例文本。修改目标为 `_resume_wait_message_from_current_start(...)`。 |
| MIMO-04 / DS-F01: Engine alias confirmation 路径不明确 | AgentMiMo / AgentDS | **fixed** | Plan §6 明确 "不计划触及：`dayu/host/engine_ingest.py`，除非 implementation 先证明当前 Host ToolRuntime 会产生 alias awaiting records 到 Engine ingest"；§8 Engine Awaiting Confirmation 明确 "本 WU 默认不修改 `engine_ingest.py`"。Stop condition 覆盖：若必须修改 engine_ingest.py，必须停止并交回总控裁决。 |
| DS-F03: 3+ waiter 测试缺口 | AgentDS | **fixed** | Plan §10 测试矩阵明确 "如果保留防御性 `AWAITING_FANOUT`，`prior_outcome=None`，`prior_awaiting_outcome` / `prior_wait_id` 有值；普通 duplicate reuse 则反向互斥" 和 "如果保留防御性 `AWAITING_FANOUT`，owner accepted awaiting 后多个 waiter decision 均得到同一个 owner wait 的 fanout decision，无一重新竞争 owner"。 |

## New Findings

无新的 blocking findings。

Plan 已正确处理 controller adjudication 的所有要求：
1. Root cause 收敛为 accepted awaiting 后 duplicate terminal marker / suppress durable-missing cleanup。
2. 明确当前 batch 截断语义不应为制造 fanout 修改。
3. 默认不修改 engine_ingest.py。
4. Lightweight constraint 保留。
5. 测试矩阵与修正后 scope 匹配。

## Lightweight Constraint Assessment

**通过。**

Plan §5 明确声明轻量方案可满足 #111，并详细解释了为什么不需要重型 durable await 设计。

逐项对照：

| 约束 | 状态 | 证据 |
|---|---|---|
| 不新增重型 durable follower table | ✅ | Plan §7 — 不修改 `host_wait_records` schema |
| 不新增 durable duplicate ledger | ✅ | Plan §5 — "follower / alias 不进入 `host_wait_records`" |
| 不新增跨 Attempt duplicate table | ✅ | Plan §5 — fanout entry 只在当前 Attempt 内存中 |
| 不新增跨进程 waiter queue | ✅ | Plan §5 — attempt-local in-memory 索引 |
| 不新增 public await lifecycle contract | ✅ | Plan §7 — "不新增或修改 Host public contract" |
| 不实现 #129 two-phase activation | ✅ | Plan §2 — 列为 non-goal |
| 保留薄 wait record + lightweight observation handle | ✅ | Plan §5 — "durable truth 仍只有 owner 的 wait record" |
| 在 attempt-local duplicate governance 上补齐 terminal marker | ✅ | Plan §7 — 新增 `_InFlightDuplicateState.AWAITING_ACCEPTED` 或等价 terminal marker |

## Slice Principle Assessment

**通过。**

Plan 提出 1 个 implementation slice：`S1 轻量 awaiting cleanup terminal marker`。

对照 Control Doc Slice 切分原则：

| 原则 | 评估 |
|---|---|
| 语义闭环 | ✅ S1 包含 duplicate governance terminal marker、ToolRuntime cleanup suppression、current batch governed failure regression、RunInputBuilder resume wording — 共同构成 accepted awaiting cleanup 状态修复闭环 |
| 依赖顺序 | ✅ 不依赖其他 WU；所有变更在同一闭包内 |
| 可独立验证 | ✅ §10 定义了完整验证矩阵：pytest + pyright + specific assertions |
| 代码范围合理 | ✅ 3 个生产模块 + ~7 测试文件，均为小型增量变更 |
| 不产生孤立半成品 | ✅ S1 done signal 覆盖全部行为断言 |
| 非机械按模块拆分 | ✅ Plan §9 明确解释了为什么不应按文件拆分 |

Plan §9 的切分依据论述充分：本 WU 是小型 execution-correctness cleanup，duplicate governance terminal marker、ToolRuntime cleanup suppression、current batch governed failure regression、RunInputBuilder resume wording 共同构成一个行为闭环。单独实现任何一部分都会留下不完整的语义。

## Residual Risks

| 风险 | Owner / Destination |
|---|---|
| `record_awaiting_accepted` 失败只能 best-effort diagnostic | 本 WU implementation（plan §12 已记录） |
| Engine 当前对 waiting confirmation 的 owner `tool_call_id` 匹配较严格 | 本 WU implementation（plan §12 已记录，stop condition 覆盖） |
| Resume material 只能表达业务语义，不能为了精确说明 alias 暴露内部 refs | 本 WU implementation（plan §8 已约束） |
| 若保留防御性 `AWAITING_FANOUT`，unit-level tests 必须覆盖 field exclusivity 和 multiple waiter decisions | 本 WU implementation（plan §10 已要求） |

## Required Controller Follow-up

无。Plan 已通过 re-review，可进入 implementation gate。

## Validation Performed

复审期间执行的只读核对命令：

```bash
# 读取所有相关 artifacts
cat docs/host/wu-tools-await-fanout-01-plan.md
cat docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md
cat docs/reviews/wu-tools-await-fanout-01-plan-review-mimo.md
cat docs/reviews/wu-tools-await-fanout-01-plan-review-ds.md
cat docs/reviews/wu-tools-await-fanout-01-plan-review-controller-adjudication.md

# 验证 plan 是否满足复审重点
rg -n "run_suspended_by_tool_awaiting|batch.*calls|governed failure" docs/host/wu-tools-await-fanout-01-plan.md
rg -n "engine_ingest|default.*not.*modify|unless.*implementation.*prove" docs/host/wu-tools-await-fanout-01-plan.md
rg -n "lightweight|no.*schema|no.*public.*contract|no.*follower.*ledger|no.*two-phase" docs/host/wu-tools-await-fanout-01-plan.md
rg -n "durable-missing|DURABLE_MISSING|accepted.*not.*record|rejected.*timeout.*record" docs/host/wu-tools-await-fanout-01-plan.md
rg -n "wait_id|tool_call_id|internal.*ref|leak" docs/host/wu-tools-await-fanout-01-plan.md
```

## Completion Report

```text
Artifact: docs/reviews/wu-tools-await-fanout-01-plan-rereview-mimo.md
Decision: pass
Unfixed accepted findings: 0
New blocking findings: 0
Validation performed: read-only artifact inspection and targeted rg checks
```
