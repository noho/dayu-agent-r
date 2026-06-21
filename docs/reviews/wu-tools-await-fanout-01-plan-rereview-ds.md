# WU-TOOLS-AWAIT-FANOUT-01 Plan Re-Review — AgentDS

## Re-Review Metadata

| 项目 | 内容 |
|---|---|
| Work unit | WU-TOOLS-AWAIT-FANOUT-01 |
| GitHub Issue | #111 |
| Gate | plan re-review |
| Plan artifact | `docs/host/wu-tools-await-fanout-01-plan.md` |
| Plan fix artifact | `docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md` |
| Prior review artifacts | `docs/reviews/wu-tools-await-fanout-01-plan-review-mimo.md`, `docs/reviews/wu-tools-await-fanout-01-plan-review-ds.md` |
| Controller adjudication | `docs/reviews/wu-tools-await-fanout-01-plan-review-controller-adjudication.md` |
| Re-review agent | AgentDS |
| Timestamp | 2026-06-21T14:25:40+08:00 |

## Re-Review Decision

**Decision: pass**

Re-review 确认 Codex plan-fix 已完全处理所有 7 条 accepted findings。更新后 plan 的 root cause 收敛正确，轻量约束完整保留，测试矩阵与修正后 scope 匹配。无新增 blocking findings。

## Accepted Findings Status

### MIMO-01: `AWAITING_FANOUT` Current Reachability Is Overstated

**Status: fixed**

证据：
- Plan §4（lines 84-86）明确当前生产可达性边界：Host ToolRuntime 在第一个 `ToolAwaitingOutcome` 后给后续 batch calls 返回 `run_suspended_by_tool_awaiting` governed failure，同批后续 waiter 当前不会命中 `AWAITING_FANOUT`。
- Plan §8 "Defensive Waiter Fanout"（lines 218-231）将 `AWAITING_FANOUT` 降级为防御性 Host internal state，不声明为当前 production e2e 必达路径。
- 代码证据核对：`tool_runtime.py:2238-2262` 中 `execute()` 确认 `run_suspended_by_awaiting = True` 后剩余 batch calls 走 `governed_failure_outcome`，与 plan 一致。
- Root cause 修正为 accepted awaiting 后 terminal marker 缺失（line 83），与 controller 裁决一致。

### MIMO-02 / DS-F02: `DuplicateDecision.prior_outcome` Vs `prior_awaiting_outcome` Semantics

**Status: fixed**

证据：
- Plan §7 "字段互斥语义"（lines 169-173）明确：
  - 普通 duplicate reuse：`prior_outcome` 有值，`prior_awaiting_outcome=None`，`prior_wait_id=None`。
  - 防御性 `AWAITING_FANOUT`：`prior_awaiting_outcome` 和 `prior_wait_id` 有值，`prior_outcome=None`。
- Plan 同时允许更简单的 terminal marker 方案（不新增 `AWAITING_FANOUT` decision），该方案不创建互斥字段（line 173）。
- 字段语义与代码事实一致：`tool_duplicate_governance.py:279` 已有 `prior_outcome: ToolExecutionOutcome | None`。

### MIMO-03: Resume Material Edit Location Underspecified

**Status: fixed**

证据：
- Plan §8 "Resolve Wait 后 Resume Material"（lines 286-308）明确：
  - 编辑目标：`_resume_wait_message_from_current_start(...)`（line 286）。
  - 操作：在现有 accepted wait result 行之后追加，不替换（line 287）。
  - 保留现有 `tool_name` / `resolution_kind` / `tool_fact_kind` / `result` projection（lines 288-296）。
  - 追加内容的具体语义已给出（lines 298-302）。
- 约束清单（lines 305-308）明确不泄漏 `wait_id`、`tool_call_id`、EventLog id 等内部 refs。

### MIMO-04 / DS-F01: Engine Alias Confirmation Path Underspecified

**Status: fixed**

证据：
- Plan §6 "不计划触及"（lines 127-128）将 `engine_ingest.py` 移出默认允许文件。
- Plan §8 "Engine Awaiting Confirmation"（lines 237-242）明确：默认不修改 `engine_ingest.py`；只有 implementation 先证明当前 Host ToolRuntime 会产生 alias awaiting records 到 Engine ingest 并提交给当前 gate 裁决后才允许修改。
- Plan §12 stop condition（lines 458-459）设定了明确阻断规则。
- 代码证据核对：`engine_ingest.py:3691` 严格 `len(data.awaiting_records) != 1` 校验，`engine_ingest.py:3699-3703` 严格 `tool_call_id` 匹配——当前路径不产 alias records，不应修改。

### DS-F03: 3+ Waiter Test Gap

**Status: conditional-fixed**（若保留防御性 `AWAITING_FANOUT` 则 fixed；否则 N/A）

证据：
- Plan fix 说明（lines 90-93 in fix artifact）明确：若保留 `AWAITING_FANOUT`，plan 要求 unit-level 测试覆盖多 waiter decision，所有 waiter 均得到同一 owner wait fanout，无一重新竞争 owner。
- 更新后 plan §10（lines 371-372）：若保留防御性 `AWAITING_FANOUT`，"owner accepted awaiting 后多个 waiter decision 均得到同一个 owner wait 的 fanout decision，无一重新竞争 owner"。
- 若 implementation 选择更简单的 terminal marker 方案（不新增 `AWAITING_FANOUT`），此测试不需要。

## No New Findings

经过对更新后 plan 的 6 个复审重点逐一核查，未发现新的 material finding。

复审覆盖：
1. Codex plan-fix 逐条核对 → 7/7 已处理（6 fixed + 1 conditional-fixed）。
2. Root cause 收敛 → 正确。Plan 当前 root cause 为 accepted awaiting 后 terminal marker 缺失，而非 overstated fanout waiter 可达性。
3. Batch governed failure → 明确。Plan §8 "Current Batch Behavior"（lines 210-217）列出现有生产的 4 条行为约束，且要求实现不得修改。
4. engine_ingest.py → 正确。默认不触及，stop condition 覆盖例外路径。
5. Lightweight constraint → 完整保留（见下方专项评估）。
6. 测试矩阵 → 与修正后 scope 匹配（见下方专项评估）。

## Lightweight Constraint Assessment

**评估：完整保留。**

逐项对照：

| 约束 | 状态 | 证据 |
|---|---|---|
| 无 durable schema 变更 | ✅ | Plan §7 — `host_wait_records` 不变，不新增列/表 |
| 无 public contract 变更 | ✅ | Plan §7 — Host/Engine public contract 不变 |
| 无 heavy follower ledger | ✅ | Plan §5 — follower/alias 不进入 `host_wait_records` |
| 无 #129 two-phase activation | ✅ | Plan §2 — 列为 non-goal |
| 无 durable duplicate ledger | ✅ | Plan §5 — fanout entry 只在当前 Attempt 内存中 |
| 无跨进程 waiter 队列 | ✅ | Plan §5 — attempt-local in-memory 索引 |
| 薄 wait record + lightweight observation handle | ✅ | Plan §5 — durable truth 仍只有 owner 的 wait record |

Plan §5 "为什么不回到重型 durable await 设计" 论证的 5 点与代码事实一致：
1. Root cause 发生在同一 Attempt 的 in-flight duplicate cleanup window（`_execute_one.finally` 在 awaiting owner 返回后执行）。
2. Host 已有 awaiting accept ack、wait record、resolve_wait、late rejection、WAITING cancel 和 resume Attempt 机制。
3. `host_wait_records_one_active_per_run` partial unique index（`durable/schema.py:1098-1102`）约束单 active wait per Run。
4. Run 恢复创建新 Attempt，不继承旧 Attempt duplicate index（`_InFlightDuplicateState` 是 attempt-scoped）。
5. #129 two-phase activation 修不同窗口（submit-before-accept），非本 WU scope。

## Slice Principle Assessment

**评估：通过。**

Plan 提出 1 个 implementation slice：`S1 轻量 awaiting cleanup terminal marker`。

对照 Control Doc Slice 切分原则：

| 原则 | 评估 |
|---|---|
| 语义闭环 | ✅ S1 包含 duplicate governance terminal marker、ToolRuntime cleanup suppression、batch governed failure regression、RunInputBuilder resume wording — 共同构成 accepted awaiting cleanup 行为闭环 |
| 依赖顺序 | ✅ 不依赖其他 WU |
| 可独立验证 | ✅ §10 定义完整验证矩阵：pytest + pyright + specific assertions |
| 代码范围合理 | ✅ 3 生产模块（`tool_duplicate_governance.py`、`tool_runtime.py`、`run_input.py`）+ 对应 focused tests |
| not 产生孤立半成品 | ✅ S1 done signal 覆盖全部 6 项行为断言（§9 lines 331-337） |
| not 机械按模块拆分 | ✅ Plan §9 明确解释为何不应按文件拆分 |

## Residual Risks with Owner/Destination

| Risk | Severity | Owner / Destination |
|---|---|---|
| R1: `record_awaiting_accepted` best-effort 失败后 waiter 重新竞争 | 已接受 | Implementation gate — plan §8 lines 207-208 已记录 |
| R2: Resume material "shared duplicate result" 文本在 LLM 推理中是否足够自解释 | 低 | Implementation gate + AgentMiMo LLM-facing review |
| R3: 若 implementation 保留防御性 `AWAITING_FANOUT`，其单元测试覆盖可能因无法触发 e2e 而看似死代码 | 低 | Implementation gate — plan 已明确只做 unit-level 覆盖 |
| R4: Future Engine 或 ToolRuntime 并发变更可能使 `AWAITING_FANOUT` 从防御性变为 production 必达 | Deferred | Future Engine/ToolRuntime concurrency WU |

## Required Controller Follow-up

1. **Gate dispatch**: 本 re-review 确认 plan-fix 已处理所有 accepted findings，plan 可以进入 implementation gate。
2. **Implementation gate 前置提醒**: implementation agent 必须严格遵循 §12 stop conditions，尤其是：
   - 若 accepted awaiting cleanup terminal marker 不能阻止 `record_durable_missing` 误记，必须停止并重新定位 root cause。
   - 若必须修改 `engine_ingest.py` alias confirmation，必须先提交直接证据并停止等待裁决。
3. **LLM-facing 审查**: resume material 文本应由 AgentMiMo 在 implementation gate 完成后按 LLM-facing 约束做专项 review。

## Validation Performed

只读核对命令：

```bash
# Timestamp
date +%Y%m%d-%H%M%S

# 关键文件存在性
ls docs/host/wu-tools-await-fanout-01-plan.md \
   docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md \
   docs/reviews/wu-tools-await-fanout-01-plan-review-mimo.md \
   docs/reviews/wu-tools-await-fanout-01-plan-review-ds.md \
   docs/reviews/wu-tools-await-fanout-01-plan-review-controller-adjudication.md

# Plan fix 覆盖验证
rg -n "MIMO-01|MIMO-02|MIMO-03|MIMO-04|DS-F01|DS-F02|DS-F03" \
   docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md

# 更新后 plan 关键条款
rg -n "run_suspended_by_tool_awaiting|engine_ingest|prior_outcome|prior_awaiting_outcome|\
_resume_wait_message_from_current_start|AWAITING_ACCEPTED|terminal marker|stop condition" \
   docs/host/wu-tools-await-fanout-01-plan.md

# 代码证据核对
grep -n 'record_duplicate_accepted\|record_awaiting' \
   dayu/host/tool_runtime.py
grep -n 'record_accepted\|record_awaiting\|record_durable_missing' \
   dayu/host/tool_duplicate_governance.py
```

直接代码证据核对：
- `dayu/host/tool_runtime.py:2708-2711` — `_accept_awaiting` 成功路径 `del duplicate_request`，无 `duplicate_terminal_recorded = True`，确认 root cause。
- `dayu/host/tool_runtime.py:2421-2426` — `finally` 块在 `duplicate_terminal_recorded=False` 时调用 `record_durable_missing`，确认误记路径。
- `dayu/host/tool_runtime.py:2238-2262` — `execute()` 中 `run_suspended_by_awaiting = True` 截断剩余 batch calls，确认现存 governed failure 行为。
- `dayu/host/tool_duplicate_governance.py:40-45` — `_InFlightDuplicateState` 只含 `OWNER_RUNNING`、`ACCEPTED`、`DURABLE_MISSING`，确认无 `AWAITING_ACCEPTED` 状态。
- `dayu/host/engine_ingest.py:3691` — `len(data.awaiting_records) != 1`，确认严格单记录校验。
- `dayu/host/run_input.py:3984-4030` — `_resume_wait_message_from_current_start` 只投影单个 accepted wait result，确认 append 位置。
- `dayu/host/tool_duplicate_governance.py:287-331` — `DuplicateGovernancePort` 协议当前无 `record_awaiting_accepted`，确认协议扩展需求。

Tests 和 pyright 未在 plan review gate 运行（plan §10 明确这是 implementation gate 的职责）。

## Completion Report

Artifact: `docs/reviews/wu-tools-await-fanout-01-plan-rereview-ds.md`

Decision: pass

Unfixed accepted findings: 0

New blocking findings: 0

Validation performed: read-only 核对命令 + 直接代码证据核对（`tool_runtime.py`, `tool_duplicate_governance.py`, `engine_ingest.py`, `run_input.py`）+ plan/fix/controller artifacts 全文读取；tests 和 pyright 未在 plan gate 运行。
