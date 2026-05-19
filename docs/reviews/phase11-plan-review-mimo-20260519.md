# Phase 11 Plan Review — AgentMiMo 2026-05-19

## Review Target

`docs/host/phase11-host-lifecycle-recovery-plan.md`

## Review Truth

- Design truth: `docs/host/design.md` §1, §2, §10, §17, §27, §27.1
- Control truth: `docs/host/implementation-control.md` 当前状态 & Phase 11 条目

## Review Lens

逐项检查 plan 是否满足指定 review lens。

---

### Lens 1: Host 设计目标（durable facts 可恢复、Host 是 lifecycle truth、多进程不误杀、Engine 不拥有 Host 状态）

**Verdict: PASS**

Plan 正确覆盖四项设计目标：

1. **Durable facts 可恢复**：Recovery scan 只读 Run / Attempt indexes、EventLog canonical facts、dispatch record、host instance liveness row。明确排除 projection / memory / read model（plan L2711, design §27 L2711）。
2. **Host 是 lifecycle truth**：Recovery coordinator 属于 `dayu/host/recovery.py`，不修改 Engine。所有状态迁移通过 Host durable transaction 完成。
3. **多进程不误杀**：Positive orphan proof 必须同时满足 heartbeat stale + pid 证据 + CAS recheck。Suspect 路径只记录 diagnostic，不写 `ATTEMPT_LOST`。
4. **Engine 不拥有 Host 状态**：Non-goals 明确禁止修改 Engine 代码，Stop Condition 要求 implementation 发现必须改 Engine 时停下。

---

### Lens 2: P10.5 frozen public contract 保持

**Verdict: PASS**

- 不新增 public API、不新增 `OpenHostOptions` 字段（plan L73-74）。
- `open_host(options)` 的 startup side effect 扩展为内部 recovery scan，不改变 Service 调用方式（plan L74）。
- `watch_session_events(session_id)` 必须能看到 recovery 提交的普通 Host events，不引入 recovery 专用 stream（plan L75）。
- Non-goals 明确列出不改变 P10.5 public API surface（plan L67-68）。

---

### Lens 3: positive orphan proof 基础是否正确

**Verdict: PASS**

Plan 的 positive orphan proof classifier 输入（plan L104-108）正确基于：

1. **Durable dispatch record** — `owner_host_instance_id` 关联到 host instance row。
2. **Host instance durable row** — `pid`、`process_start_token`、`heartbeat_at`、`status`。
3. **Process evidence** — 本机 pid-exists probe，可选 pid-reused mismatch。
4. **CAS recheck** — closeout 时重新读取 Run / Attempt / dispatch / host instance row 确认一致性。

Plan 明确排除以下作为 orphan proof（plan Non-goals L30, design §27 L2748, L2762）：
- heartbeat stale 单独不够
- lane token 不是 truth
- projection / memory / audit / trace / outbox 不参与
- watcher 存在性不参与
- "当前进程不可确认控制"不构成 orphan proof

Classifier 输出 typed union：`PositiveOrphanProof` / `OwnerStillLive` / `OrphanProofInconclusive`（plan L104-108）。Inconclusive 路径不推进 recovery。

---

### Lens 4: startup 分类覆盖

**Verdict: PASS**

| 状态 | Plan 处理 | Design §27 要求 | 一致 |
| --- | --- | --- | --- |
| `ACCEPTED` | 原地保留，schedule accepted-run wake | 原地保留 | ✓ |
| `QUEUED` | 原地保留，schedule queue promotion check | 原地保留 | ✓ |
| `WAITING` | 原地保留，optional wait observation wake | 原地保留 | ✓ |
| `RUNNING` | classify current Attempt + positive orphan proof | positive orphan proof 才能 `LOST` | ✓ |
| `CANCELLING` | classify current Attempt + positive orphan proof; `LOST` 不恢复 | positive orphan proof 才能 `LOST` | ✓ |
| `RECOVERING` | evaluate cancel/limit → dispatch or `LOST` | 继续按 policy 创建新 Attempt 或 `LOST` | ✓ |

Terminal 收口：recoverable → `ATTEMPT_LOST` + `RUN_RECOVERING` → new Attempt; unrecoverable → `ATTEMPT_LOST` + `RUN_LOST`; RECOVERING 超限 → `RUN_LOST` with structured reason。

---

### Lens 5: CANCELLING orphan → LOST、不恢复执行

**Verdict: PASS，符合设计目标**

Plan decision（plan L111）：`CANCELLING` orphan positive proof 后以 `ATTEMPT_LOST + RUN_LOST` 收口，reason 说明 `cancel_in_flight_attempt_lost`；不创建新 Attempt。

直接证据：design §27 L2705-2707 要求 "RUNNING / CANCELLING Run 的 active Attempt 只有在具备 positive orphan proof 时，才能进入 LOST"。design §27 L2743 "RUNNING / CANCELLING 的旧 Attempt 只有在 positive orphan proof 成立后才能写入 ATTEMPT_LOST"。

用户已 durable append cancel fact（`CANCEL_REQUESTED`），表达停止意图。创建新 Attempt 继续回答会违背用户意图。Plan 的 LOST 收口符合 durable facts 尊重原则。

---

### Lens 6: recovery count 通过 EventLog 计数、默认不 schema change

**Verdict: PASS，可实现且可测试**

Plan（L79-80, L110）：第一版 recovery attempt count 通过 EventLog 中同一 Run 的 `RUN_STARTED` 且 `start_reason=recovery` 计数。默认不新增 schema 字段。

实现路径：
- `run_transition.py` 已有 `start_recovery_run_with_starting_attempt_in_transaction` 创建 `RUN_STARTED` event。
- 新增 `RUN_STARTED` payload 中 `start_reason=recovery` 字段。
- 新增读 helper 扫描同一 Run 的 `RUN_STARTED` events，count `start_reason=recovery`。
- 计数比较 recovery policy 上限（默认 1）。

可测试性：
- Seed EventLog with known `RUN_STARTED(start_reason=recovery)` events。
- Assert count helper returns expected count。
- Assert recovery dispatch blocked when count >= limit。
- Assert `RUN_LOST` with `startup_recovery_dispatch_limit_exceeded` reason。

Plan 已设置 Stop Condition（L331）："A schema change becomes necessary for recovery count" 时停下。

---

### Lens 7: Recovery dispatch 是否通过 pending dispatch + RunInputBuilder

**Verdict: PASS**

Plan（L110-111, L196-199）明确：

1. Recovery coordinator 创建新 Attempt / execution_id / dispatch record id。
2. 在一个 write transaction 内 commit `RUN_STARTED(start_reason=recovery)` + `ATTEMPT_STARTED` + pending dispatch record。
3. After commit, wake `HostDispatchScheduler.wake_dispatch(...)`。
4. Recovery 不调用 WorkerProxy。
5. Dispatch path 的 RunInputBuilder 从 canonical EventLog facts 重建 messages。

与 design §17 一致：Attempt Dispatch 只消费已提交的 dispatch record / attempt snapshot，负责 LocalProxy / RemoteProxy 派发。Recovery 不绕过 Attempt Dispatch。

---

### Lens 8: multi-process tests 与 crash/restart E2E 是否足够 deterministic

**Verdict: PASS with risk noted**

Plan Slice 5（L259-268）定义三个 multi-process harness 场景：

1. **Live second process not harmed**：process A owns active Attempt + heartbeats; process B scans, no `ATTEMPT_LOST`。Deterministic: process B sees heartbeat fresh → `OwnerStillLive`。
2. **Crash after USER_INPUT_ACCEPTED**：killed owner pid + stale heartbeat → restart produces answer。Semi-deterministic: 依赖 stale threshold 超时，但 plan 建议 "deterministic stale heartbeat setup or bounded waits"。
3. **Projection lag**：stop/lag projection, recovery still uses EventLog/Run/Attempt rows。Deterministic: 直接验证 recovery 不读 projection。

Risk: crash E2E 测试的 timing sensitivity。Plan 已在 Risks 中说明（L347），并建议 deterministic stale heartbeat setup。

---

### Lens 9: runtime lane hardening 是否被过度夹带

**Verdict: PASS，未过度夹带**

Slice 5（L249-268）的 lane hardening 范围严格限制：
- 只修 close/acquire race（`LaneController.close()` must wake pending acquire）。
- close/acquire concurrent tests。
- stale claim cleanup remains runtime capacity cleanup only。

implementation-control.md 追踪区（L1653-1657）明确 lane close/acquire race owner 为 Phase 11。Plan 的 lane changes 不引入 Host truth、不改变 lane token 语义。

Plan Non-goals（L59）明确 `dayu/runtime/lane.py` "只允许修 close/acquire race、stale cleanup、active count invariant；不得引入 Host truth"。

---

### Lens 10: slices 是否足够小、file ownership 是否清晰、验证命令是否完整

**Verdict: PASS**

| Slice | Files | 验证命令 | 评估 |
| --- | --- | --- | --- |
| S1: Host Instance Lifecycle & Process Proof | 5 files | pytest + pyright | 聚焦，可独立验证 |
| S2: Startup Recovery Scan & CAS Closeout | 6 files | pytest + pyright | 依赖 S1，范围清晰 |
| S3: RECOVERING Dispatch & RunInputBuilder | 7 files | pytest + pyright | 依赖 S2，集成切面合理 |
| S4: RECOVERING Cancel, Graceful Shutdown | 8 files | pytest + pyright | 依赖 S3，public contract 聚焦 |
| S5: Multi-process & Lane Hardening | 7 files | pytest + pyright + full host | 依赖 S1-S4，E2E 收口 |

File ownership 清晰：每个 slice 列出 allowed files。Phase acceptance 验证命令完整（L289-297）。

---

## Findings

### F1 — process_start_token 熵保证未在 plan 中显式约束

**严重程度**: Medium
**证据**: Plan Slice 1（L135）要求 `process_start_token` 必须是 "本进程启动生成的不可猜测 token"，但未指定熵要求或生成方式。当前代码 `dispatch.py:2964` 使用 `f"dispatch-{host_handle_id}"` 为可预测占位。
**影响**: 若 implementation 使用低熵 token（如 timestamp），pid reuse 场景下 positive orphan proof 可能产生 false negative。
**建议修复**: 在 plan 中明确 `process_start_token` 应使用 `uuid4().hex` 或等效高熵随机值，与 `host_instance_id` 分开生成。
**是否 blocking**: No

### F2 — WAITING Run recovery 的 wait adapter observation 可恢复性未展开

**严重程度**: Medium
**证据**: Plan（L163）说 "WAITING: keep, no Attempt creation; optional wait observation wake if existing adapter supports it"。Design §27 L2704 说 "WAITING Run 保持 WAITING，等待 wait record resolution"。但 wait adapter state 是内存态，crash 后 adapter 不存在。
**影响**: 若 wait adapter 不支持 durable resume，WAITING Run 在 Host 重启后可能 stuck，直到 wait record TTL 或外部 resolve。
**建议修复**: 在 plan Risks 或 Deferred 中显式说明 WAITING recovery observation 的 adapter re-attach 限制，以及第一版的兜底行为（如 wait poller restart 或 wait record TTL expiry）。
**是否 blocking**: No

### F3 — heartbeat background task failure mode 未覆盖

**严重程度**: Low
**证据**: Plan Slice 1（L136）新增 heartbeat background task，但未说明 task 本身 crash（如 unhandled exception）时的行为。
**影响**: 若 heartbeat task 静默退出，host instance row 停止刷新，可能导致 stale → false positive orphan proof by other processes。
**建议修复**: heartbeat task 应 catch 并 log 异常，或在 task exit 时 best-effort mark instance stopping。可在 Slice 1 implementation 中处理，不需 plan 变更。
**是否 blocking**: No

### F4 — RECOVERING cancel 幂等 replay 的 "不 cancel 后来新 Runs" 语义需更精确

**严重程度**: Low
**证据**: Plan Slice 4（L231）说 "Idempotency replay for RECOVERING cancel must return same result and not cancel later new Runs"。
**影响**: 若 recovery dispatch 创建新 Attempt 后 replay 旧 cancel request，需要确保 idempotency scope 绑定到特定 Run 而非 session。
**建议修复**: 确认 `cancel_run` 的 idempotency scope 已绑定 `run_id`，而非 session-level。当前 P10.5 实现应已满足，但 plan 可显式说明。
**是否 blocking**: No

### F5 — recovery dispatch count helper 的 EventLog scan 性能边界未说明

**严重程度**: Low
**证据**: Plan（L171）要求 "Add EventLog recovery dispatch count helper by scanning canonical RUN_STARTED payload/reason for start_reason=recovery"。每次 startup scan 需要为每个 RECOVERING Run 扫描 EventLog。
**影响**: 若 Run 数量大或 EventLog 长，scan 可能有性能影响。但第一版每个 Run 最多 1 次 recovery，scan 范围有限。
**建议修复**: 可在 implementation 中加 EventLog filter（如 `EventPayloadTextEqualsFilter` on `start_reason`），限制 scan 范围。Plan 可注明此优化方向。
**是否 blocking**: No

### F6 — Slice 2 与 Slice 3 的 run_transition.py 修改可能冲突

**严重程度**: Low
**证据**: Slice 2（L151-152）和 Slice 3（L189）都允许修改 `run_transition.py`。Slice 2 新增 startup orphan closeout helper，Slice 3 新增 recovery dispatch helper。
**影响**: 若两个 slice 并行实现，可能产生 merge conflict。
**建议修复**: Slice 应顺序实现（S2 → S3），plan 已隐含此依赖（S3 依赖 S2 的 CAS closeout）。无需 plan 变更，implementation agent 按序执行即可。
**是否 blocking**: No

---

## Summary

| 严重程度 | Count |
| --- | --- |
| Blocking | 0 |
| High | 0 |
| Medium | 3 (F1, F2, F3) |
| Low | 3 (F4, F5, F6) |

## Conclusion

**PASS, blocking count = 0。**

Plan 正确覆盖 design §1/§2/§10/§17/§27/§27.1 的所有关键要求，保持 P10.5 frozen public contract 不变，positive orphan proof 基于 durable facts + process evidence + CAS recheck，startup 分类覆盖全部六种状态且 terminal 收口合理，CANCELLING orphan → LOST 符合用户意图尊重原则，recovery count 通过 EventLog 计数可实现可测试，Recovery dispatch 通过 pending dispatch + RunInputBuilder 不绕过 Attempt Dispatch，multi-process tests 设计合理，runtime lane hardening 未过度夹带，slices 足够小且 file ownership 清晰。

所有 findings 为 non-blocking，可在 implementation 阶段处理。建议 controller 后续裁决 F1（process_start_token 熵）和 F2（WAITING recovery 限制）作为 implementation 注意事项。
