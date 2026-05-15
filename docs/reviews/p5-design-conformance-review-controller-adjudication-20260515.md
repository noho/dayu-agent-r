# P5 Design Conformance Review Controller Adjudication

## 结论

Controller 裁决：**PASS / no blocking design deviation**。

AgentMiMo、AgentDS、AgentCodex 三路独立 review 均确认：P5 当前实现没有阻塞性偏离 `docs/host/design.md`、`docs/host/implementation-control.md` 与 `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`。Host / Engine / Runtime 分层边界清晰；LocalProxy envelope 承载 Host identity，EngineEvent 仍保持 Engine 公共事件；dispatch record 未被用作 lease / fencing / owner truth；RunInputBuilder 通过 typed providers 读取 durable facts；后续 phase 能力未被提前硬编码。

## 输入证据

- `docs/reviews/p5-design-conformance-review-mimo-20260515.md`
- `docs/reviews/p5-design-conformance-review-ds-20260515.md`
- `docs/reviews/p5-design-conformance-review-codex-20260515.md`

## Reviewer Verdicts

| Reviewer | Verdict | Blocking design deviations |
| --- | --- | --- |
| AgentMiMo | PASS | 0 |
| AgentDS | PASS | 0 |
| AgentCodex | PASS | 0 |

Controller 接受三份 PASS 结论，但对部分 finding 做如下归并和裁决。

## Controller Findings

### C1 非生产 durable helper 的 ATTEMPT_RUNNING payload 形态弱于生产路径

- 来源：AgentDS Finding 1、AgentCodex Non-blocking Design Drift 1。
- 裁决：**accepted-nonblocking design drift**。
- 证据：
  - 生产路径 `HostDispatchScheduler._accept_worker_running` 使用 `dayu/host/dispatch.py` 内部 `_attempt_running_event_request(...)`，payload 包含 `local_worker_id`、`worker_accepted_at`、`lane_name`、`lane_claim_id`。
  - durable helper `accept_worker_running_in_transaction(...)` 使用 `dayu/host/durable/run_transition.py` 的 `_attempt_running_event_request(...)`，payload 只包含 attempt / execution / dispatch / worker kind / execution target / reason。
  - 当前生产 scheduler 未调用该 durable helper；它主要仍被测试与底层 transition primitive 路径使用。
- 影响：不破坏 P5 生产接线与治理真源，但同名 canonical fact 在不同 helper 路径上诊断字段不一致，后续维护者若误用 durable helper 可能写出弱诊断 `ATTEMPT_RUNNING`。
- Owner：Host durable transition hardening。
- Destination：后续 cleanup；若继续收紧 PR 54，可把 durable helper 输入扩展为完整 worker/lane diagnostics，或删除/限制该 helper 的生产可见性。

### C2 `mark_dispatching_after_lane_row` 能力宽于生产 scheduler 路径

- 来源：AgentCodex Non-blocking Design Drift 2。
- 裁决：**accepted-nonblocking API broadness**。
- 证据：
  - 生产路径先 `pending -> waiting_for_lane`，acquire lane 后 recheck，再 `waiting_for_lane -> dispatching`。
  - 底层 helper `mark_dispatching_after_lane_row(...)` 允许 `PENDING` 或 `WAITING_FOR_LANE` 进入 `DISPATCHING`，并在 pending 直跳时补齐 waiting/lane diagnostics。
  - helper docstring 明确这是两种安全来源；当前生产 scheduler 不依赖 pending 直跳。
- 影响：当前生产路径不偏离 design，但底层 helper 对未来调用方暴露了更宽的能力。
- Owner：Host durable API tightening。
- Destination：后续 cleanup；可通过命名、文档、测试 helper 隔离或更窄 CAS helper 降低误接线风险。

### C3 compact artifact message slot 与 phase plan 摘要顺序表述不完全一致

- 来源：AgentDS Finding 2。
- 裁决：**rejected-as-current P5 blocker / accepted-doc-clarification**。
- 理由：
  - P5 当前 compact provider 为 noop，运行时不会产生 compact artifact messages。
  - `docs/host/design.md` 已把 compact artifacts 作为 RunInputBuilder 后续输入层的一部分；P5 plan 的顺序摘要未列出该 noop slot，不等于禁止代码预留 typed provider slot。
  - 该点不影响 P5 行为。
- Owner：Phase 10 / RunInputBuilder doc cleanup。

### C4 command handle 不隐式打开 scheduler 是刻意生命周期边界

- 来源：AgentMiMo production wiring 表述与 AgentCodex production wiring risk 1。
- 裁决：**accepted-as-designed**。
- 理由：
  - 当前 `create_host_command_handle` 是同步 facade；对非空 `HostCommandHandleOptions.local_execution` fail-fast，避免隐藏 async scheduler lifecycle。
  - 真实 P5 本地执行路径通过调用方显式 `await HostDispatchScheduler.open(...)` 接线，测试也按该路径覆盖。
  - 这不是生产接线错误，而是已记录的 lifecycle composition 选择。
- Owner：后续 Host lifecycle composition。如需一体化生产入口，应新增明确 async factory，而不是让同步 facade 隐式持有 scheduler。

## Design Boundary Result

| Boundary | Controller verdict |
| --- | --- |
| Host 强治理真源 | PASS |
| EngineEvent 不携带 Host Attempt / dispatch / recovery identity | PASS |
| LocalProxy / EngineWorker envelope 承载 Host identity | PASS |
| dispatch record 不作为 lease / fencing / owner truth | PASS |
| `UI -> Service -> Host -> Engine` 依赖方向 | PASS |
| `dayu.runtime` 层中立 | PASS |
| RunInputBuilder typed provider boundary | PASS |
| production scheduler / lane / LocalProxy / ingest / promotion 接线 | PASS，存在 C1/C2 非阻塞 hardening |
| 后续 phase 能力未提前硬编码 | PASS |
| deferred phase owner | PASS |

## Residual Risk / Owner

| Risk | Owner | Blocking |
| --- | --- | --- |
| durable helper `accept_worker_running_in_transaction` payload diagnostics 弱于 scheduler 生产路径 | Host durable transition hardening | No |
| `mark_dispatching_after_lane_row` 底层 helper 能力宽于生产路径 | Host durable API tightening | No |
| terminal closeout 后 queue promotion wakeup failure 仍可能影响 worker event task 诊断 | Host dispatch lifecycle hardening | No |
| active cancel watchdog / stuck `CANCELLING` | Phase 11 lifecycle / recovery hardening | No |
| LocalProxy `cancel()` no-op 依赖 Engine runner 观察 cancellation token | Engine runner integration + Phase 11 watchdog | No |
| explicit scheduler + command handle 两段式生产装配需要更清晰 async composition entry | Host lifecycle composition | No |
| broader God module / test hardening | 后续 architecture / test hardening | No |

## Gate Status

P5 design conformance review gate 通过。无需当前 blocker fix。Controller 要求将三份 review artifact 与本 adjudication 记录到总控文档；C1/C2 作为后续 hardening item 保留 owner，不阻塞 PR 54 draft review-ready。
