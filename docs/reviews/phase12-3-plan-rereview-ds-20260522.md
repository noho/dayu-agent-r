# Phase 12.3 Plan Fix Re-Review — AgentDS

**日期**: 2026-05-22  
**审查对象**: `docs/host/phase12-3-config-usage-governance-plan.md`（fix 后版本）  
**被修复缺陷**: P12.3-PLAN-B1 (`provider_request_id` 数据缺口)  
**Controller 裁决引用**: `docs/reviews/phase12-3-plan-review-controller-adjudication-20260522.md`  
**审查 Agent**: AgentDS

## Verdict: PASS

B1 已正确关闭。无新增 blocking findings。

---

## B1 修复逐项验证

Controller 要求五项修改，逐一验证：

### 1. 从 Host usage projection 必需字段中移除 `provider_request_id`

**验证**: ✅

- §3.1 In Scope 第 52 行：`provider request id 不是当前 Engine usage event contract 的必需字段，只能作为可选关联信息。`
- Slice 2 第 262 行：`provider_request_id 是可选 payload 字段：当当前 Engine event/context 已经能在不改变 Engine usage contract、不增加脆弱 lookup 的前提下提供 provider request id 时可以写入；不可用时默认值必须为 None，并继续接受 usage projection。`
- Slice 2 第 278 行（必需字段断言列表）：仅含 `attempt_id`、`execution_id`、`session_id`、`run_id`、`policy_ref`、`estimator_digest`、`usage_observation_status` — **不含 `provider_request_id`**。

### 2. 删除要求 `UsageReportedData.provider_request_id` 的测试

**验证**: ✅

- Slice 2 第 285 行：`不允许测试要求从 UsageReportedData 或 RunnerUsageRecordedData 读取 provider_request_id；这些 Engine usage event contracts 在 Phase 12.3 保持不变。`

### 3. 声明 provider_request_id 为可选、不可用时默认为 None

**验证**: ✅

- 第 52 行："可选关联信息"
- 第 262 行："可选 payload 字段...不可用时默认值必须为 None"

### 4. 新增测试：缺失 provider_request_id 时仍接受 projection signal、Run / Attempt 状态不变

**验证**: ✅

- 第 284 行：`provider request id 缺失时，usage projection signal 仍被接受，payload 中对应值为 None，Run / Attempt 状态不变。`

### 5. Engine usage event contracts 保持不变

**验证**: ✅

- §6 第 121 行：`UsageReportedData`、`RunnerUsageRecordedData` 仍在禁止修改清单中。
- Slice 2 第 246 行：`不修改 Engine RunnerUsageRecordedData / UsageReportedData 字段，不修改 Engine Agent loop；本 phase 不建议、也不要求给 usage event contract 增加 provider_request_id。`
- 第 285 行：显式禁止测试从 Engine contracts 读取 `provider_request_id`。

---

## 回归检查：修复未引入新缺陷

对原 DS review PASS 的 12 个检查项做回归验证：

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | plan 不以 discussion 替代设计真源 | PASS | 第 7-8 行不变 |
| 2 | 不保留旧 schema 兼容读取 / alias / tests | PASS | §3.2 non-goals 不变，Slice 4 旧字段扫描不变 |
| 3 | 不误删 RunnerCallOptions.max_tokens explicit override | PASS | §6 第 123 行不变 |
| 4 | ConfigLoader / runtime assembly 不 import Host / Engine / Service | PASS | §5 不变 |
| 5 | usage observation 不影响 dispatch decision | PASS | §3.2 non-goals 不变 |
| 6 | 不引入 usage config override 或 supports_usage | PASS | §3.2 non-goals 不变 |
| 7 | Service helper 不自动选择 profile | PASS | Slice 3 不变 |
| 8 | Slice 不夹带 future workflow | PASS | §3.2 不变 |
| 9 | File ownership 合理 | PASS | §4 不变 |
| 10 | 测试覆盖充分 | PASS | Slice 2 新增第 284-285 行补充了 provider_request_id 缺失路径 |
| 11 | README sync 触发规则正确 | PASS | 各 slice README 决定不变 |
| 12 | 合并后与设计真源一致 | PASS | provider_request_id 变为可选不违反 design.md §3 L95（usage 缺失不导致 Run 失败） |

---

## 与 Controller 裁决的一致性

Controller 拒绝的修复路径（AgentDS 原建议：扩展 Engine event contracts）已在计划中体现为相反方向。计划明确：
- 第 246 行："本 phase 不建议、也不要求给 usage event contract 增加 provider_request_id"
- 第 285 行：禁止测试依赖 Engine contracts 提供 provider_request_id

Controller 接受的修复路径（provider_request_id 可选、不可用时 None）完整落地于第 52、262、284 行。与裁决完全一致。

---

## 结论

B1 已通过以下修正关闭：
- `provider_request_id` 从必需 payload 字段降级为可选字段
- 不可用时默认 `None`，不影响 Run / Attempt 状态
- Engine `UsageReportedData` / `RunnerUsageRecordedData` 完全不修改
- 测试覆盖了缺失 provider_request_id 的接受路径
- 禁止了要求 Engine contracts 提供 provider_request_id 的测试

**无新增 blocker。** Plan 可以进入 implementation。

---

*AgentDS re-review complete. Artifact: `docs/reviews/phase12-3-plan-rereview-ds-20260522.md`*
