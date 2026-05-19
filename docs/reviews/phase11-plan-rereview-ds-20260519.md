# Phase 11 Plan Re-Review — AgentDS 2026-05-19

## Review Target

`docs/host/phase11-host-lifecycle-recovery-plan.md` — 经 Codex fix pass 修复后的 plan artifact。

## Review Inputs

- Fix artifact: `docs/reviews/phase11-plan-fix-codex-20260519.md`
- Controller adjudication: `docs/reviews/phase11-plan-review-controller-adjudication-20260519.md`
- Original DS review: `docs/reviews/phase11-plan-review-ds-20260519.md`
- Original MiMo review: `docs/reviews/phase11-plan-review-mimo-20260519.md`
- Design truth: `docs/host/design.md` §1, §2, §10, §17, §27, §27.1
- Control truth: `docs/host/implementation-control.md` Phase 11

## Re-Review Scope

验证 controller 裁决的 6 项 accepted findings（DS 1-U、DS 2-U、MiMo F1-F5）已在 plan 中修复，MiMo F6 保持 no-action，plan 仍对齐 design §1/§2/§10/§17/§27/§27.1 与 P10.5 frozen public contract，无新 blocker 引入。

## Per-Finding Verification

### DS 1-U / MiMo F1 相关: RunInputBuilder canonical-fact hardening

**原始 finding**: Slice 3 仅要求 "Verify dispatch path uses RunInputBuilder..." 但 RunInputBuilder hardening 只在 non-blocking risk 中提及，未作为 Slice 3 exact change。

**Fix artifact 声明**: Slice 3 now allows necessary typed hardening inside RunInputBuilder / dispatch path, forbids projection/memory/read-model truth, and adds a stop condition if files outside Slice 3 allowed files are needed.

**Plan 现况验证**:

- Plan L202: "If current `RunInputBuilder` cannot rebuild recovery messages only from canonical EventLog facts and payload descriptors, Slice 3 may perform necessary typed hardening inside `RunInputBuilder` / dispatch-path ownership so the dispatched `AgentRunRequest.messages` are derived from canonical facts. Do not treat projection, memory snapshot, read model, audit, trace, outbox, timeline, `RunResult`, or projection checkpoint as truth. If this hardening needs files outside Slice 3 allowed files, stop and return to Controller before editing them."
- Plan L339（Stop Condition）: "Recovery message rebuild requires `RunInputBuilder` hardening outside Slice 3 allowed files" 对应 stop condition 已存在。

**Verdict**: ✅ **FIXED**。hardening 任务已从 non-blocking risk 提升为 Slice 3 exact change，truth boundary 和 stop condition 均明确。

---

### DS 2-U / MiMo F2: WAITING recovery observation fallback

**原始 finding**: Slice 2 只说 "optional wait observation wake if existing adapter supports it"，无 adapter 不可用时的 fallback。

**Fix artifact 声明**: Slice 2 now requires diagnostic-only fallback when wait adapter observation is unavailable, unsupported, or wake fails; no Run / Attempt mutation and no Attempt creation.

**Plan 现况验证**:

- Plan L163-164: "`WAITING` recovery 若 adapter observation 不可用、adapter 不支持重挂、或 wake 失败，必须走 diagnostic-only fallback：记录 structured diagnostic log 或 `event_class=diagnostic` 的 EventLog 事件；不得推进 Run / Attempt 状态，不得创建 Attempt，不得把 diagnostic 再读作 recovery truth。"

**Verdict**: ✅ **FIXED**。diagnostic-only fallback 已作为 Slice 2 明确要求，三种 fail 路径均已覆盖，且明确禁止状态推进和 Attempt 创建。

---

### MiMo F1 additional: process_start_token entropy

**原始 finding**: Plan 要求 "不可猜测 token" 但未指定熵要求或生成方式。

**Fix artifact 声明**: Slice 1 now requires `uuid4().hex` or equivalent stdlib high-entropy random value, generated separately from `host_instance_id`, and forbids timestamp / handle-id / pid derived tokens.

**Plan 现况验证**:

- Plan L135: "`process_start_token` 必须和 `host_instance_id` 分开生成，使用 `uuid4().hex` 或等效 stdlib 高熵随机值，不得使用 timestamp、handle id、pid 或这些值派生出的 token，也不得继续使用 `dispatch-{host_handle_id}` 这类可预测占位。"

**Verdict**: ✅ **FIXED**。熵要求已显式指定，禁止项明确，与 `host_instance_id` 分离生成已明确。

---

### MiMo F3: heartbeat background task failure mode

**原始 finding**: heartbeat background task 未说明 task crash 时的行为。

**Fix artifact 声明**: Slice 1 now requires heartbeat loop exception handling, structured diagnostic logging, and best-effort current-instance `STOPPING` mark on fatal heartbeat task exit, without touching other instances.

**Plan 现况验证**:

- Plan L137-138: "Heartbeat loop 必须捕获并输出 structured diagnostic logging。单次 refresh 异常可按 policy 继续重试；若 heartbeat task fatal exit，必须 best-effort 将当前 scheduler 自己的 host instance 标记为 `STOPPING`，不得标记或修改其它 host instance row。"

**Verdict**: ✅ **FIXED**。异常处理、diagnostic logging、best-effort STOPPING mark 与不误伤其它 instance 的约束均明确。

---

### MiMo F4: RECOVERING cancel idempotency scope

**原始 finding**: "not cancel later new Runs" 语义需更精确绑定 idempotency scope。

**Fix artifact 声明**: Slice 4 now explicitly scopes `cancel_run` to `(run_id, client_request_id)` and `cancel_session_runs` to `(session_id, client_request_id)`, with per-run result stability limited to Runs in the original session-scope result.

**Plan 现况验证**:

- Plan L233-234: "Idempotency scope is explicit and unchanged: `cancel_run` is scoped by `(run_id, client_request_id)`; `cancel_session_runs` is scoped by `(session_id, client_request_id)`. For `cancel_session_runs`, per-run result stability applies only to Runs included in the original session-scope command result and must not affect later newly created Runs in the same session."

**Verdict**: ✅ **FIXED**。idempotency scope 显式绑定，session-scope replay 对后续新 Run 的影响边界明确。

---

### MiMo F5: recovery dispatch count helper EventLog boundary

**原始 finding**: recovery dispatch count helper 的 scan 范围未说明过滤条件。

**Fix artifact 声明**: Slice 2 now requires a typed EventLog helper filtered by `run_id` and canonical `RUN_STARTED`, counting only payloads with `start_reason=recovery`.

**Plan 现况验证**:

- Plan L173: "Add typed EventLog recovery dispatch count helper in the durable/EventLog boundary: helper must filter by `run_id` and canonical `RUN_STARTED` events, and only count events whose payload has `start_reason=recovery`. It must not count projection/read-model rows, diagnostic events, old Attempt snapshots, or non-canonical payload text matches outside the typed event codec."

**Verdict**: ✅ **FIXED**。typed helper 边界、过滤字段和禁止误计范围均明确。

---

### MiMo F6: Slice 2 / Slice 3 both touching run_transition.py

**Controller 裁决**: Rejected as no-action.

**Plan 现况**: Slice 2（L151-152）与 Slice 3（L189）均允许修改 `run_transition.py`。Slice 顺序为 S2 → S3，sequential implementation 消除冲突风险。

**Verdict**: ✅ **NO-ACTION**，维持 controller 裁决。sequential slice ordering 足以防止 merge conflict。

---

## Design Alignment Verification

### §1 设计目标

| 设计要求 | Plan 对应 | 对齐 |
|---------|----------|------|
| Host 是 Session/Run/Attempt/EventLog 治理真源 | Goal L11; Recovery 输入为 EventLog + state indexes | ✓ |
| Engine 只执行单次 AgentRunRequest | Non-goals L27 "不修改 Engine 代码" | ✓ |
| 单机多客户端/多进程 | Slice 5 多进程 hardening | ✓ |

### §2 分层边界

| 设计要求 | Plan 对应 | 对齐 |
|---------|----------|------|
| Recovery 是唯一负责 Host startup scan、旧 Attempt LOST 收口和可恢复 Run 新 Attempt 创建的模块 | Recovery 位于 `dayu/host/recovery.py`，只做 startup scan/CAS closeout/dispatch | ✓ |
| 依赖方向不变 (UI→Service→Host→Engine) | Recovery 是 Host 内部模块，不跨层 | ✓ |
| Engine 不读取 Host durable store | Non-goals 禁止改 Engine | ✓ |
| Projection/timeline/audit/outbox 不能反向成为 EventLog 真源 | Slice 2 L174 "projection lag does not affect classification" | ✓ |

### §10 Durable Store

| 设计要求 | Plan 对应 | 对齐 |
|---------|----------|------|
| CAS-style 条件更新 | Slice 2 CAS recheck (L172) | ✓ |
| EventLog append + state index 同事务 | Slice 2 L94-96 "必须在一个 write transaction 内" | ✓ |
| governance truth 只能由 Host transaction 写入 | Recovery transition helper 通过 Host transaction 写 | ✓ |
| diagnostic/trace 不能参与状态恢复判定 | L106 "Suspect owner 只记录 diagnostic event" | ✓ |

### §17 WorkerProxy / EngineWorker

| 设计要求 | Plan 对应 | 对齐 |
|---------|----------|------|
| dispatching/dispatcher_instance_id 是诊断不是 lease/fencing | Non-goals L30 "不引入 lease/fencing/takeover" | ✓ |
| Attempt Dispatch 只消费已提交的 dispatch record | Slice 3 L200 "Recovery coordinator 只创建新 Attempt / pending dispatch，并 wake scheduler" | ✓ |
| lane token 不是 Host truth | Slice 5 L271 "stale claim cleanup remains runtime capacity cleanup only" | ✓ |

### §27 Host Lifecycle / Recovery

| 设计要求 | Plan 对应 | 对齐 |
|---------|----------|------|
| ACCEPTED/QUEUED/WAITING 原地保留 | Slice 2 L160-164 | ✓ |
| RUNNING/CANCELLING 只有 positive orphan proof 才能 LOST | Slice 2 L165-166 | ✓ |
| 恢复必须创建新 Attempt | Slice 3 "Recovery coordinator creates new Attempt id / execution id" | ✓ |
| 每个 Run 最多一次 automatic startup recovery dispatch | L110 "每个 Run 最多一次 automatic startup recovery dispatch" | ✓ |
| positive orphan proof = heartbeat stale + pid evidence + CAS recheck | L104-105, L172 | ✓ |

### §27.1 已接受 Prompt 的恢复语义

| 设计要求 | Plan 对应 | 对齐 |
|---------|----------|------|
| USER_INPUT_ACCEPTED durable 后才可恢复 | Slice 3 integration test "seed or crash a Run after USER_INPUT_ACCEPTED / before final answer" | ✓ |
| RunInputBuilder 从 EventLog 重建 messages | Slice 3 L201-202 RunInputBuilder canonical-fact hardening | ✓ |
| 新 Attempt + 新 execution_id | Slice 3 L199 | ✓ |
| final answer 通过 Host event stream 可见 | Slice 3 L204 "observe final answer through watch_session_events" | ✓ |

### P10.5 Frozen Public Contract

| 设计要求 | Plan 对应 | 对齐 |
|---------|----------|------|
| 不新增 public API | L73 "不新增 public API，不新增 public OpenHostOptions 字段" | ✓ |
| open_host(options) 入口不变 | L74 "startup side effect 扩展为内部 recovery scan" | ✓ |
| watch_session_events 可见 recovery events | L75 | ✓ |
| 不改变 P10.5 public API surface | Non-goals L32 | ✓ |

---

## New Blocker Check

逐项检查 fix 是否引入新问题：

1. **Slice 1 process_start_token entropy 要求**: 新增 `uuid4().hex` 要求不改变 schema、不改变 public API、不新增依赖。无新风险。
2. **Slice 2 WAITING diagnostic-only fallback**: 明确 diagnostic 不推进状态、不创建 Attempt、不被 Recovery 再读作 truth。与 design §27 中 diagnostic 不能参与状态恢复判定一致。无新风险。
3. **Slice 1 heartbeat task failure mode**: best-effort STOPPING mark 只限当前 instance，不误伤其它 instance。与 design §27 中 heartbeat 只能刷新自己 row 一致。无新风险。
4. **Slice 4 cancel idempotency scope**: 显式绑定 (run_id, client_request_id) 和 (session_id, client_request_id)，与 design §9 中 operation idempotency scope 设计一致。无新风险。
5. **Slice 2 recovery dispatch count helper**: typed EventLog helper 的 filter 和禁止误计范围明确。无新风险。
6. **Slice 3 RunInputBuilder hardening**: stop condition 已覆盖文件范围超界的场景。truth boundary（不依赖 projection/memory/read model）已明确。无新风险。

**No new blockers found.**

---

## Open Questions

无。

## Residual Risks

| # | 风险 | 去向 |
|---|------|------|
| R1 | portable pid-reuse proof 受限，部分场景只能输出 inconclusive | Plan non-blocking risk L350; 后续平台 capability |
| R2 | recovery E2E 多进程测试 timing-sensitive | Plan risk L352; implementation 使用 deterministic stale heartbeat setup |
| R3 | lane close/acquire race fix 影响 dayu.runtime，需 review 确保层中立 | Slice 5 scope 已限定; 后续 review 验证 |
| R4 | RunInputBuilder hardening 实际范围可能超过 Slice 3 allowed files | Slice 3 stop condition 覆盖; Controller 裁决 |
| R5 | watch polling 性能与 watcher close 行为 | Deferred to 后续 public lifecycle hardening |

## Conclusion

6 项 controller-adjudicated accepted findings（DS 1-U、DS 2-U、MiMo F1-F5）均已确认在 plan artifact 中修复。MiMo F6 维持 no-action。Plan 仍对齐 `docs/host/design.md` §1、§2、§10、§17、§27、§27.1 与 P10.5 frozen public contract。无新 blocker 引入。

**Verdict: PASS — blocking count = 0。**
