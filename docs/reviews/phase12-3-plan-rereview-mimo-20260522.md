# Phase 12.3 Plan Fix Re-Review — AgentMiMo

review Agent：AgentMiMo
review 日期：2026-05-22
review 对象：`docs/host/phase12-3-config-usage-governance-plan.md`（fix 后版本）
前置 review artifacts：
- `docs/reviews/phase12-3-plan-review-mimo-20260522.md`（PASS_WITH_FINDINGS, blocking 0）
- `docs/reviews/phase12-3-plan-review-ds-20260522.md`（PASS_WITH_FINDINGS, blocking 1: B1）
- `docs/reviews/phase12-3-plan-review-controller-adjudication-20260522.md`（accepts B1, modified fix direction）

## Verdict

**PASS**

blocking findings: 0
B1 status: closed

## 1. Fix 验证：P12.3-PLAN-B1 关闭检查

Controller adjudication 要求的 fix 条件逐项验证：

### 1.1 不扩展 Engine usage event contracts

| 条件 | 证据 | 结果 |
|---|---|---|
| 不修改 `UsageReportedData` 字段 | plan L246: "不修改 Engine `RunnerUsageRecordedData` / `UsageReportedData` 字段，不修改 Engine Agent loop；本 phase 不建议、也不要求给 usage event contract 增加 `provider_request_id`" | PASS |
| 不修改 `RunnerUsageRecordedData` 字段 | 同上 L246 | PASS |
| 不修改 Engine Agent loop | 同上 L246 | PASS |
| §6 Public Surface 禁止清单保留 `UsageReportedData` / `RunnerUsageRecordedData` | plan L121: "Engine `AgentRunRequest`、`AgentRunResult`、`EngineEvent`、`UsageReportedData`、`RunnerUsageRecordedData` public event contract" 仍在禁止修改清单中 | PASS |
| §3.2 Non-goals 保留 | plan L62: "不修改 Engine Agent loop 状态机、不修改 Runner usage event contract" | PASS |

### 1.2 provider_request_id 改为可选

| 条件 | 证据 | 结果 |
|---|---|---|
| 从必需 payload 字段列表中移除 | plan L254-261 列出必需字段为 `session_id`、`run_id`、`policy_ref`、`estimator_digest`、`estimated_input_tokens`、`usage_observation_status`、`usage_observation_digest`。`provider_request_id` 不在列表中 | PASS |
| 明确为可选字段 | plan L262: "`provider_request_id` 是可选 payload 字段：当当前 Engine event/context 已经能在不改变 Engine usage contract、不增加脆弱 lookup 的前提下提供 provider request id 时可以写入；不可用时默认值必须为 `None`，并继续接受 usage projection" | PASS |
| §3.1 In Scope 更新措辞 | plan L52: "provider request id 不是当前 Engine usage event contract 的必需字段，只能作为可选关联信息" | PASS |

### 1.3 缺失 provider request id 的测试要求

| 条件 | 证据 | 结果 |
|---|---|---|
| 新增缺失 provider request id 测试 | plan L284: "provider request id 缺失时，usage projection signal 仍被接受，payload 中对应值为 `None`，Run / Attempt 状态不变" | PASS |
| 禁止测试从 Engine event 读取 provider_request_id | plan L285: "不允许测试要求从 `UsageReportedData` 或 `RunnerUsageRecordedData` 读取 `provider_request_id`；这些 Engine usage event contracts 在 Phase 12.3 保持不变" | PASS |

### 1.4 Engine usage event contracts 不变的验收标准

| 条件 | 证据 | 结果 |
|---|---|---|
| Acceptance criteria 明确 | plan L311: "Engine usage chain tests 不需要改 production Engine contract" | PASS |

## 2. 引入新 blocker 检查

### 2.1 旧 schema 兼容性

fix 只修改了 Slice 2 的 `provider_request_id` 处理方式，从必需改为可选。Slice 1（config schema cleanup）和 Slice 3（execution profile 分档）未改动。不存在旧 schema 兼容读取、旧字段 alias 或兼容测试引入。

### 2.2 Profile 自动切换

Slice 3 未改动。Service helper 仍然只做显式选择和兼容性校验，不自动切换。

### 2.3 Import boundary

Slice 2 的 allowed files 未变化（`dayu/host/context_budget.py`、`dayu/host/engine_ingest.py` 及相关测试）。不涉及 `dayu.runtime` import boundary。

### 2.4 其余 MiMo O1-O7 观察

fix 未影响原 review 的 7 个 non-blocking observations。O1（session_id/run_id 来源路径）、O2（estimator_digest 失败模式）、O3-O7 均仍为实现细节层面建议。

## 3. Fix 一致性检查

fix 后 plan 内部不存在自相矛盾：

- §3.2 Non-goals L62 "不修改 Runner usage event contract" 与 §6 L121 禁止修改清单一致。
- §3.1 In Scope L51-52 "不改 Engine usage_reported event contract"+"provider request id 可选" 与 Slice 2 L246/L262 一致。
- Slice 2 Tests L284-285 测试要求与 L262 实现 decisions 一致。
- §7 L311 acceptance criteria 与 L246 实现 decisions 一致。

## 4. 关键证据索引

| 检查项 | 证据位置 |
|---|---|
| Engine contract 不变 | plan L62, L121, L246 |
| provider_request_id 可选 | plan L52, L262 |
| 必需字段不含 provider_request_id | plan L254-261 |
| 缺失测试要求 | plan L284-285 |
| acceptance criteria | plan L311 |

## 5. 结论

P12.3-PLAN-B1 已按 controller adjudication 的修改方向完整关闭。fix 不扩展 Engine usage event contracts，将 `provider_request_id` 从必需降为可选并默认 `None`，新增缺失场景测试要求，且明确禁止测试从 Engine event 读取该字段。fix 未引入新 blocker，未影响 Slice 1/3 内容，plan 内部一致性保持。原 review 的 O1-O7 non-blocking observations 均不受影响。
