# P1-P5 Design Conformance Review Controller Adjudication

## Scope Correction

本轮是 corrected design conformance gate。上一轮
`docs/reviews/p5-design-conformance-review-controller-adjudication-20260515.md`
只覆盖 P5 local dispatch slice，范围不足；它只能作为 P5 子集证据，不作为 P1-P5 当前全量 snapshot 的总控结论。

本轮审查范围为 P1-P5 已实现到当前 snapshot 的全部代码，设计真源为 `docs/host/design.md`，总控文档
`docs/host/implementation-control.md` 仅作为 phase 范围与历史交付物线索。

## Inputs

- AgentMiMo artifact: `docs/reviews/p1-p5-design-conformance-review-mimo-20260515.md`
- AgentDS artifact: `docs/reviews/p1-p5-design-conformance-review-ds-20260515.md`
- AgentCodex artifact: `docs/reviews/p1-p5-design-conformance-review-codex-20260515.md`
- Prior P5-only subset artifact: `docs/reviews/p5-design-conformance-review-controller-adjudication-20260515.md`

## Controller Verdict

PASS.

三路独立 review 均覆盖 P1-P5 当前代码，并一致给出 blocking design deviation 为 0。Controller 裁决：当前
P1-P5 snapshot 未发现偏离 `docs/host/design.md` 的 blocking 架构问题；PR 54 仍保持 draft review-ready。

## Accepted No-Issue Conclusions

- P1 public contract 与 runtime 边界符合设计：`dayu.runtime` 层中立，无 Host / Engine / Service / UI / Fins 反向依赖；Host public types 与 ToolBundle construction-input 边界清晰。
- P2 durable store 与 EventLog 符合设计：fresh schema、global `event_sequence`、unique `event_id`、append/read/idempotency、payload descriptor 与 liveness foundation 均保持 EventLog 真源边界。
- P3 session / run / attempt / admission 符合设计：active run invariant、CAS transition、queue promotion、cancel / terminal closeout 均在 Host durable governance 内完成。
- P4 public API command path 符合设计：`create_host_command_handle` 为同步 public facade，不隐式拥有 async scheduler lifecycle；unsupported operations 保持 stable fail-fast。
- P5 RunInputBuilder / local dispatch / local proxy / Engine ingest / cancel 符合设计：Host 仍拥有 Agent / AsyncAgent / AsyncOpenAIRunner 生命周期和取消治理；Engine 不理解 Host durable truth；LocalProxy envelope 承载 Host identity；dispatch record 未被建成 owner / lease / fencing truth。
- Cross-phase layering 符合设计：`UI -> Service -> Host -> Engine` 方向未反转；Engine 未 import Host；Host 到 Engine 依赖集中在设计允许的 local proxy / run input / ingest 边界；财报文档路径未绕过 `dayu.fins.storage`。
- 后续 phase 预留符合设计：ToolRuntime / fetch_more、WAITING / resolve_wait、Memory、Context Governance、Recovery、Observer / Sink、RemoteProxy、Retention / Purge 均未被提前实现为 P1-P5 业务真源。

## Non-Blocking Findings

### C1. `accept_worker_running_in_transaction` helper payload diagnostics 弱于 scheduler 生产路径

- Severity: non-blocking hardening
- Sources: AgentDS 9-NB-1, AgentCodex F1, prior P5-only controller C1
- Controller decision: accepted as non-blocking hardening
- Reason: P5 生产 scheduler 不使用该 helper 作为 worker accept truth；生产路径已写入完整 worker / lane / dispatch 诊断字段。风险在于后续维护者误用低层 durable helper，写出弱诊断 `ATTEMPT_RUNNING` canonical fact。
- Owner: Host durable transition hardening
- Destination: P5/P6 前 hardening 或后续 Host durable API cleanup

### C2. `mark_dispatching_after_lane_row` low-level CAS 能力宽于生产 scheduler 路径

- Severity: non-blocking hardening
- Sources: AgentDS 9-NB-2, AgentCodex F2, prior P5-only controller C2
- Controller decision: accepted as non-blocking hardening
- Reason: 当前生产 scheduler 走 `PENDING -> WAITING_FOR_LANE -> DISPATCHING` 受控路径，未把 dispatch record 误用为 owner / lease / fencing truth；风险在于底层 helper 允许 `PENDING` 直跳 `DISPATCHING`，未来调用方可能绕过诊断阶段。
- Owner: Host durable API tightening
- Destination: 后续 Host durable state helper 收口

### C3. `DEFAULT_ACTIVE_WORKER_REGISTRY` module-level singleton

- Severity: non-blocking hardening
- Source: AgentMiMo F1
- Controller decision: accepted as non-blocking hardening
- Reason: 当前单 handle 生产路径不触发跨 handle cancel 串扰；多 handle / 多 scheduler composition 时，module-level active worker registry 可能扩大 cancel 传播边界。该项不构成 P1-P5 当前设计偏离，但需要在 Host lifecycle composition 中收口。
- Owner: Host dispatch lifecycle hardening
- Destination: 后续 Host composition / active cancel hardening

### C4. compact artifact message slot 与 plan 摘要顺序不完全一致

- Severity: non-blocking doc clarification
- Source: AgentDS 9-NB-3
- Controller decision: accepted as non-blocking documentation cleanup
- Reason: 当前 compact provider 为 noop，运行时不改变 P5 行为；实际 code path 没有提前实现 Phase 10 compact governance。风险是 plan 摘要与 code slot 顺序表述不完全一致。
- Owner: Phase 10 / RunInputBuilder documentation cleanup
- Destination: Phase 10 Context Governance / compact artifact 接线时清理

## Residual Risk Ownership

| Risk | Owner | Blocking |
| --- | --- | --- |
| durable helper `accept_worker_running_in_transaction` diagnostics 弱于 scheduler 生产路径 | Host durable transition hardening | No |
| `mark_dispatching_after_lane_row` helper 能力宽于生产 scheduler | Host durable API tightening | No |
| module-level active worker registry 跨 handle 共享风险 | Host dispatch lifecycle hardening | No |
| terminal closeout 后 queue promotion wakeup failure 影响 worker event task | Host dispatch lifecycle hardening | No |
| active cancel watchdog / stuck `CANCELLING` / orphan recovery | Phase 11 lifecycle / recovery | No |
| LocalProxy cancel no-op 依赖 Engine runner 观察 cancellation token | Engine runner integration + Phase 11 | No |
| RemoteProxy 未实现 | Phase 14 | No |
| ToolRuntime / `fetch_more` 未实现 | Phase 6 | No |
| WAITING / `resolve_wait` 未实现 | Phase 7 | No |
| Memory / Context Governance / compact artifact 未实现 | Phase 9 / Phase 10 | No |

## Final Gate State

P1-P5 design conformance corrected gate 通过。当前 PR 54 不需要因本轮 review 进入 fix gate；状态维持 draft review-ready。
