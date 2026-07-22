# WU-HOST-SESSION-EVENT-DELIVERY-01 Plan Review Controller Adjudication

## Decision

- gate: `plan-review`
- decision: `fix-required`
- plan: `docs/host/wu-host-session-event-delivery-01-plan.md`
- AgentMiMo review: `docs/reviews/plan-review-20260721-185410.md`，conclusion=`pass`
- AgentDS review: `docs/reviews/plan-review-20260721-185406.md`，conclusion=`pass-with-risks`
- blocking open questions: None
- next entry point: AgentCodex plan fix；随后原 AgentMiMo / AgentDS 独立 re-review

Controller 不按 reviewer 票数裁决。以下每项均以设计真源、plan 文本和最新 main 代码证据独立判断。

## Finding adjudication

### MIMO-001 — S1 对 `entrypoint_runtime.py` 的边界不够机械

- decision: `accepted`
- evidence: plan S1 允许修改整个 `dayu/service/entrypoint_runtime.py`，但同一文件既包含唯一 production watch 调用点，也包含应在 S4 才删除的 `_WatchAndWaitRuntime.queue`、`_WatcherFailure` 与 drain task。
- required fix: S1 必须明确只传播 async factory/public iterator contract，不删除、不改写、不重构旧 relay 状态；S4 是 relay 与 exact-five 状态机的唯一修改 slice。S1 tests 不得固化 relay 行为。

### MIMO-002 — scheduler/coordinator 构造环需要更强 lifecycle barrier

- decision: `accepted-and-merged-with-DS-F2`
- evidence: 当前 `HostDispatchScheduler.open()` 在返回前启动 heartbeat/watchdog；plan 要求 non-optional port bind 先于任何 producer，但只描述构造 happy path，未冻结 Host close 与 construction failure 的 stop-before-coordinator-close 顺序。
- required fix: S3 明确 factory/bind 必须发生在 scheduler critical tasks 启动前；factory/bind failure 时 tasks 从未启动且资源精确关闭。Host close 必须先停止所有 scheduler-owned terminal producers并 await 收口，再关闭 coordinator/port。测试应覆盖 bind failure 不启动 task、Host close 的 stop-before-port-close 顺序；不得暴露可运行的未绑定 scheduler，也不得使用临时 no-op 过渡。

### MIMO-003 — `asyncio.to_thread` 共享默认 executor 可能把 UI 阻塞传播到 runtime

- decision: `accepted-in-narrowed-form`
- evidence: plan S4 使用 `asyncio.to_thread`，而 `dayu.runtime.lane` 等运行时能力也使用默认 executor。跨多个 Session 的慢 UI callback 可能占满同一默认 executor，违背“慢 UI / Service 不暂停 Agent / Engine”的边界。单 consumer 单 in-flight 只限制每个 watcher，不能限制 Host-global Session 数量。
- required fix: S4 必须指定显式 owner 的 Service/UI callback execution domain，不能与 event loop 默认 executor 或 Host/runtime blocking work共享。执行域保持串行、同一 consumer 至多一个 submitted/in-flight callback，不增加 Host event-copy queue、第二 observation channel或跨 Session quota；写清创建、正常关闭、异常关闭与测试边界。
- note: 不接受把“另一个默认 `to_thread` 偶尔仍能完成”作为充分验证；必须从 owner 和 executor 隔离上证明。

### DS-F1 — periodic reconciliation 驱动语义不够明确

- decision: `accepted`
- evidence: design 要求 mailbox-empty bounded periodic reconciliation，同时禁止 per-watcher background task。plan 的“periodic timer”未说明二者如何同时成立。
- required fix: S2 明确 reconcile 由 sole iterator `__anext__()` 的 readiness wait timeout 分支驱动；每次 timeout 只执行一次 bounded-page durable reconcile后重新等待，不创建 subscription/background timer task，不复用 wait-resolution cadence。interval 是 Host-internal 有界常量，不进入 public policy；测试用可控时钟/barrier证明空 mailbox、无 local notice时 eventual delivery且 Host close 能立即打断等待。

### DS-F2 — coordinator 可能早于 scheduler producer 关闭

- decision: `accepted-and-merged-with-MIMO-002`
- evidence: scheduler heartbeat/watchdog 是真实 background tasks；若 coordinator/port 先关闭，producer可能在 close 窗口提交 local notice。
- required fix: 同 MIMO-002；此外 closing coordinator 对已进入 owner loop 的 notice必须幂等完成或产生固定低基数 operator diagnostic，不能新建 subscription，也不能把 committed terminal伪装成 rollback。

### DS-F3 — callback thread 无超时导致 cancellation 悬挂

- decision: `rejected-with-reason`
- evidence: Python thread job 无法被安全取消。给 await 加 timeout 后继续 cleanup会允许仍在运行的 callback 在 iterator/controller close 后迟到触碰 renderer，破坏 plan 已冻结的串行 lifecycle与 late-commit safety；也不会真正回收 thread或executor容量。
- rationale: 当前 contract 明确 callback 必须快速、同步、非阻塞；本 WU 必须隔离执行域，使有限的慢 callback只减速当前 consumer并触发其Host mailbox policy，但不承诺安全终止违反 contract 的无限阻塞任意代码。plan 应明确这一 physical guarantee boundary，不增加“timeout后遗弃仍运行thread”的伪修复。
- verification: 保留可释放的 deterministic blocking callback barrier，证明 Host/Agent/Engine/promotion/第二 watcher继续；释放 barrier 后严格验证 primary/cleanup顺序。

### DS-F4 — 双 opener fixture 范围不具体

- decision: `accepted`
- evidence: 现有 watch tests 有同一 options 的顺序 reopen 和多 watcher，但没有可直接复用的 concurrent dual-opener helper；plan 的“为双openerfixture涉及的现有Host support files”不是可审查的 allowed boundary。
- required fix: S2 明确在 `tests/host/test_watch_session_events.py` 内用两个独立 `open_host` context共享同一 Host DB/lane DB options构造最小 deterministic fixture，并写清资源/worker ownership、无 local notice barrier与关闭顺序。若实施证据证明必须改其它 support file，先触发 slice stop condition并回到 plan gate，不得使用模糊 wildcard scope。

### DS-F5 — CLI renderer close 与 caller `finally` 同步点不明确

- decision: `accepted`
- evidence: plan 同时说 close 经 worker execution domain串行化、caller `finally` 是 lifecycle owner，但没有冻结 finally 必须 await display close完成后才能释放 renderer-local资源。
- required fix: S4 明确唯一 caller-finally close flow：停止新增 display work，await 当前 callback，在线程执行域串行执行 renderer close并await完成，返回 event loop后再释放 caller-local resource。close failure仍按现有 CLI lifecycle contract传播/聚合，且必须有 deterministic ordering test。

### DS-F6 — “慢 watcher 不反压”缺少 Host/Service边界限定

- decision: `accepted`
- evidence: Service sole consumer必须等待当前 callback完成才调用下一次 `anext()`；慢 callback会减速当前 consumer并可能导致当前 mailbox overflow，但 Host publish不能等待它。
- required fix: 在目标/非目标与 S4 明确：不反压承诺属于 Host publisher、Agent/Engine、promotion和其它 watcher；Service callback耗时可以减速当前 consumer，且只通过当前订阅的 item-bound overflow收口。不得为端到端“零背压”增加 event-copy relay、丢事件队列或 byte quota。

### DS-O1 — standalone command handle 与 manifest 关系

- decision: `accepted-as-clarification`
- evidence: `create_host_command_handle` 装配 admission/waiting terminal producers但没有 Session Event Delivery runtime；producer qualified-callsite闭集与 composition path 是两个维度。
- required fix: §5.3/S3 明确 admission/waiting等producer无论由完整 opener还是standalone command handle装配都属于同一 static manifest。standalone path必须显式注入private no-local-delivery port并由runtime fake证明producer仍调用port；它不是从manifest排除terminal producer的理由。该private port不public export、不兼容转发、不承担跨opener correctness。

### DS-O2 — source scan精度

- decision: `rejected-with-reason`
- evidence: plan 已精确扫描旧 `reason_code="slow_consumer"` 和 `session_live_stream`，并明确不能全仓删除真实 availability owner使用的 `HostUnavailableDetail`。
- rationale: 当前 scan足以约束本 WU旧语义；添加宽泛组合模式会产生无关 false positive。

## Severity normalization

AgentDS artifact 的摘要把 F3列为中严重度，但结论段又称 F3-F6均为低严重度。Controller按finding正文与failure scenario把 DS-F3视为 material concurrency concern并完成上述裁决；该artifact内部计数不影响逐项decision。

## Fix handoff

AgentCodex 只修改：

- `docs/host/wu-host-session-event-delivery-01-plan.md`
- 新增一个 plan-fix artifact，记录上述 accepted items 的修改位置与 rejected items未实施原因

不得修改 design、control、两份原review、生产代码、配置、测试、README或umbrella handbook；不得实施、commit、push或操作PR。修复完成后必须由原 AgentMiMo 与 AgentDS 独立 re-review全部 accepted items。
