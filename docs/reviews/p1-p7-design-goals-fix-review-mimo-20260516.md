# P1-P7 Design Goals Fix Review — mimo — 2026-05-16

- **Gate**: fix review
- **Worker under review**: AgentCodex fix artifact (`docs/reviews/p1-p7-design-goals-fix-codex-20260516.md`)
- **Controller decision**: `docs/reviews/p1-p7-design-goals-controller-decision-20260516.md`
- **Branch**: `fix/host-p1-p7-awaiting-production-wiring`
- **Scope**: 当前未提交 diff（11 files, +132 / -54）

---

## Verdict: PASS

所有 controller decision 项（D2–D6）均已正确修复。无 Blocking / High / Medium finding。1 项 Low/Info observation。建议进入 controller final adjudication。

---

## Finding Summary

| Severity | Count |
|----------|-------|
| Blocking | 0 |
| High | 0 |
| Medium | 0 |
| Low/Info | 1 |

---

## Per-Decision Verification

### D2 — Active worker registry 注入 ✅

**验证结论**: 修复正确，无残留。

| 检查项 | 结果 |
|--------|------|
| `DEFAULT_ACTIVE_WORKER_REGISTRY` 已从 `dispatch.py` 删除 | ✅ `dispatch.py:275-276` 旧定义已移除 |
| `cancel_active_worker()` 已从 `dispatch.py` 删除 | ✅ `dispatch.py:281-288` 旧函数已移除 |
| `__all__` 已移除两个导出 | ✅ `dispatch.py:1266-1268` |
| 生产代码无残留引用 | ✅ `grep dayu/` 返回 0 matches |
| `HostCommandHandle.__init__` 接收 `active_registry` | ✅ `command.py:120` |
| `create_host_command_handle` 默认创建 fresh registry | ✅ `command.py:235-238` |
| `HostDispatchScheduler.__init__` 默认创建 fresh registry | ✅ `dispatch.py:310-311` |
| `_propagate_active_cancel_targets` 使用 `host._active_registry` | ✅ `command.py:852` |
| 测试：command handle 默认 registry 隔离 | ✅ `test_factory_default_active_registry_is_handle_local` |
| 测试：scheduler 默认 registry 隔离 | ✅ `test_default_active_registry_is_scheduler_local` |
| 测试：显式共享 registry 后 active cancel 传播 | ✅ `test_cancel_run_active_worker_propagates_and_closes_cancelled` |
| 测试：session cancel replay 重放 active cancel | ✅ `test_cancel_session_replay_repropagates_active_without_new_facts` |

**架构合规**: command path 与 scheduler 通过 composition root 显式注入共享 registry，不再依赖模块级 mutable singleton。设计 §10.1 "Host composition root 必须显式持有影响执行和外部通信的运行参数" 已满足。

### D3 — resolve_wait 幂等 digest ✅

**验证结论**: 修复正确。

| 检查项 | 结果 |
|--------|------|
| `_wait_resolution_digest` 只含 `wait_id` + `idempotency_key` + `outcome` | ✅ `waiting.py:1093-1098` |
| `source` 不参与 digest | ✅ 已移除 |
| `observed_at` 不参与 digest | ✅ 已移除 |
| 同 key + 同 outcome + 不同 `observed_at` 幂等重放 | ✅ `test_resolve_wait_same_key_same_outcome_replays_with_different_observed_at` |
| 同 key + 不同 outcome 返回 `IDEMPOTENCY_CONFLICT` | ✅ `test_resolve_wait_same_key_different_outcome_conflicts` |

**设计目标符合性**: 设计 §20 "resolve_wait 幂等范围是 `(wait_id, idempotency_key)`；同一 key + 同一 outcome 重试必须重放既有结果"。`observed_at` / `source` 保留在首次提交的 EventLog payload 中（`_tool_result_resolution_payload` 构造的 payload 仍包含这些字段），但不参与冲突判定。

**`_wait_late_rejection_digest` 仍含 `source`/`observed_at`**: `waiting.py:1123-1124`。这是正确的——late rejection 是 diagnostic event，每次独立审计，不适用 resolution 幂等语义。

### D4 — `TOOL_TERMINAL_RESULT` 设计口径 ✅

**验证结论**: 设计修改正确，不削弱 audit / RunInputBuilder / memory。

| 检查项 | 结果 |
|--------|------|
| `TOOL_TERMINAL_RESULT` 已从 canonical event 列表移除 | ✅ `design.md:1326` |
| `TOOL_RESULT_ACCEPTED` 描述已更新 | ✅ `design.md:1354` — "P1-P7 accepted waiting terminal result 不另建 `TOOL_TERMINAL_RESULT` canonical fact" |
| EventLog 规则已更新 | ✅ `design.md:1929` — "P1-P7 的 accepted waiting terminal result 同样使用 `TOOL_RESULT_ACCEPTED`" |
| 代码未变更 | ✅ 无代码 diff（只改 design.md） |

**不削弱 audit**: `TOOL_RESULT_ACCEPTED` payload 的 wait-specific fields（`wait_id`, `resolution_source`, `resolution_kind`, `resolution_idempotency_key`, `observed_at`, wait record status, adapter refs, resume Attempt refs）已足以解释等待完成来源。RunInputBuilder 从 `TOOL_RESULT_ACCEPTED` 重建 accepted wait/tool fact system message。

### D5 — `FOLLOWUP_QUEUED` 设计口径 ✅

**验证结论**: 设计修改正确，不削弱 audit。

| 检查项 | 结果 |
|--------|------|
| `FOLLOWUP_QUEUED` 已从 canonical event 列表移除 | ✅ `design.md:1316` |
| control event 表已更新 | ✅ `design.md:1354` — "STEER_REQUESTED / CANCEL_REQUESTED / ..." 不再包含 FOLLOWUP_QUEUED |
| control event `run_id` 绑定规则已更新 | ✅ `design.md:1369` — "`submit_followup(queue)` 不引入独立 `FOLLOWUP_QUEUED` canonical event" |
| 代码未变更 | ✅ 无代码 diff（只改 design.md） |

**不削弱 audit**: `USER_INPUT_ACCEPTED` + `RUN_ACCEPTED` / `RUN_QUEUED` / `RUN_STARTED` 构成完整审计链。`USER_INPUT_ACCEPTED` payload 的 `operation_kind` / call context digest 可解释 follow-up 来源。

### D6 — WAITING cancel docstring ✅

**验证结论**: 修复正确。

| 检查项 | 结果 |
|--------|------|
| `cancel_run` docstring 已更新 | ✅ `command.py:383-384` — "当前覆盖 ... active worker 与 `WAITING`；`RECOVERING` 取消由 Phase 11 负责" |
| `cancel_session_runs` docstring 已更新 | ✅ `command.py:436-437` — 同上 |

### fetch_more cursor 内存态 ✅

controller decision D1 明确接受当前设计，本轮未变更。diff 中无 fetch_more cursor 相关改动。

---

## Additional Checks

### 反向依赖 ✅

`command.py` 从 `dispatch.py` import `ActiveCancelMessage` 和 `ActiveWorkerRegistry`——这是 Host → Host 的同层依赖，方向正确。无新增跨层 import。

### 弱类型 ✅

diff 中无 `Any`、`object`、无类型参数或无类型返回值。所有新增参数均有显式类型注解。

### 过度设计 ✅

修复是最小化的：删除模块级全局变量、注入 typed registry、简化 digest、更新 docstring 和 design.md。无新增抽象层、Protocol 或 wrapper。

### 测试伪覆盖 ✅

| 测试 | 验证内容 | 非伪覆盖证据 |
|------|---------|-------------|
| `test_factory_default_active_registry_is_handle_local` | 不同 handle 的 registry 是不同对象 | 直接 `is not` 比较 |
| `test_default_active_registry_is_scheduler_local` | 不同 scheduler 的 registry 是不同对象 | 直接 `is not` 比较 |
| `test_cancel_run_active_worker_propagates_and_closes_cancelled` | 共享 registry 后 cancel 传播到 worker | 端到端：start_run → dispatch → cancel → worker terminal |
| `test_cancel_session_replay_repropagates_active_without_new_facts` | session cancel replay 不追加 facts 但重放 cancel | 端到端：start → dispatch → cancel session → replay cancel |
| `test_resolve_wait_same_key_same_outcome_replays_with_different_observed_at` | 同 outcome 不因 observed_at 变化冲突 | 端到端：seed waiting → resolve → resolve with different observed_at → verify same attempt, no new events |
| `test_resolve_wait_same_key_different_outcome_conflicts` | 不同 outcome 触发 idempotency conflict | 端到端：seed → resolve completed → resolve different completed → verify error, no new events |

全量测试套件：394 passed，0 failed。pyright：0 errors。

---

## Residual Risks

1. **Active cancel 传播仍为 best-effort / 进程内**：修复确保 command path 与 scheduler 可通过显式注入共享同一 registry，但未添加跨进程 worker 取消或 durable physical cancel 保证。这在 controller decision 和 codex fix artifact 中已记录为已知 residual risk，不影响当前 gate。

2. **`_wait_late_rejection_digest` 仍含 `source`/`observed_at`**：`waiting.py:1123-1124`。late rejection 是 diagnostic event 而非 resolution 幂等语义，每次独立审计合理。无需修改。

---

## Recommendation

**建议进入 controller final adjudication**。所有 D2–D6 修复已验证通过，无 Blocking / High / Medium finding。测试覆盖真实行为，pyright 零报错，全量 394 测试通过。
