# WU-CTX-04 plan review 总控裁决

## Gate metadata

- Work unit：`WU-CTX-04`
- Gate：plan review adjudication
- Plan：`docs/reviews/wu-ctx-04-plan-codex.md`
- Review artifacts：
  - `docs/reviews/plan-review-20260722-110302.md`（AgentMiMo，`pass-with-risks`）
  - `docs/reviews/plan-review-20260722-110343.md`（AgentDS，`pass-with-risks`）
- Design truth：`docs/host/design.md`
- Control truth：`docs/host/issues-implementation-control.md`
- Controller decision：`needs-fix`
- Blocking open questions：None

## First-principles judgment

两路 review 均确认 root cause、architecture direction、semantic owners 与主要 non-goals 成立；没有 finding 要求推翻 per-Session attachment registry、strict-native mutex、target recovery、single proactive operation 或 execution-owner cancel 方向。当前 plan 已接近 code-generation-ready，但仍有 public contract、close/drain、deterministic validation、cancel query 与 slice handoff 细节会迫使 implementation agent 自行设计，因此不能直接进入 accepted plan commit。

## Finding adjudication

### MIMO-001 — accepted

- 来源：AgentMiMo finding 001。
- 裁决：Host close 与 attachment close 的 drain 顺序必须精确化。当前 scheduler `close()` 会取消 promotion critical task；plan 必须明确在调用 scheduler close 前，registry 已 gate 新工作且所有 pre-start work leases 已自然收口，不能让 scheduler close 取消尚未收口的 proactive operation后再释放 mutex。
- Fix requirement：写出 Host close / attachment close 的精确顺序、lease completion condition、既有 Runner/provider timeout 边界，以及 in-flight proactive close/re-attach 验证。

### MIMO-002 — accepted

- 来源：AgentMiMo finding 002。
- 裁决：Slice 2 的现有测试迁移范围大，completion signal 需要显式确认每个 listed `open_host` fixture/helper 的 recovery/mutation expectation已迁移，避免测试静默失去 owner contract 覆盖。
- Fix requirement：补充 test migration checklist 与 completion assertion，不要求逐文件机械改动。

### MIMO-003 — deferred-with-owner

- 来源：AgentMiMo finding 003。
- Owner / destination：Slice 2 与 Slice 4 code review；AgentMiMo / AgentDS 双路 review。
- 理由：`dispatch.py` 已过大是真实维护风险，但 plan 已把 registry truth 与 proactive projection放到独立 owner模块；在没有实现 diff 前无法证明还需新增模块。实施 review 必须阻止 God function/module 继续增长，能由窄 helper/protocol owner承担的逻辑不得堆入 scheduler。

### MIMO-004 — accepted

- 来源：AgentMiMo finding 004。
- 裁决：periodic owned-session reconciliation 是 liveness correctness path，测试不能依赖 wall-clock sleep。
- Fix requirement：定义生产与测试共用的一次性 reconciliation step，production loop只负责按 interval 调用；测试用 barrier/显式 one-shot 调用验证 poll-bound、dedupe、closing removal 与 old-owner no-promotion。

### MIMO-005 — rejected-with-reason

- 来源：AgentMiMo finding 005。
- 理由：项目 schema 约束明确要求 fresh schema 且禁止兼容读取；plan 已要求旧字段 strict unknown-field rejection、明确错误与对应测试，也已把 upgrade需求定向到未来 migration WU。该 finding 未指出额外未覆盖行为。

### DS-F01 — rejected-with-reason

- 来源：AgentDS F-01。
- 理由：当前 `dayu.host.command.resolve_wait` 在 transaction 内创建稳定 Attempt/dispatch record，commit 后直接调用 `wake_dispatch(...)`；它不是 `wake_queue_promotion(...)`，也不依赖 attachment new-work eligibility。design truth 同样把 wait resolution定义为已有 durable continuation。finding 假设其 wake 会被 old scheduler promotion gate 丢弃，与直接代码路径不符。
- 保留约束：plan 继续明确 `resolve_wait` 不授予新用户 mutation资格，exact existing continuation仍由原 durable owner负责。

### DS-F02 — accepted

- 来源：AgentDS F-02。
- 裁决：问题不是单纯 UX。若同一 Host handle 对同一 Session 同时返回 RW 与 RO attachment，而 mutation gate 只检查 handle registry中是否存在任一 RW，则 RO caller无法被独立约束，违反 per-attachment mode public承诺。
- Fix requirement：plan 必须定义同一 Host handle / Session 只能有一个 live public attachment；重复 attach 在 native acquire前返回 typed conflict，不得返回与handle级RW资格矛盾的RO对象。多UI共享同一Host runtime时由其共同 lifecycle owner复用该唯一attachment；独立access竞争必须使用独立 `open_host`。

### DS-F03 — accepted

- 来源：AgentDS F-03；与 MIMO-001 合并修复。
- 裁决：不得新增 force unlock 或独立 detach timeout，但 plan 必须证明所有 pre-start/provider path由既有 bounded Runner timeout/cancellation收口，并把最坏等待组成与timeout测试写清；若发现任何无界调用路径，应回到 plan而不是实现默认超时。

### DS-F04 — accepted

- 来源：AgentDS F-04。
- 裁决：Run row 的 `cancel_request_event_id` 在 terminal 后仍保留，durable truth存在；但 plan 未把 exact owner reconcile query写到可直接实现的程度。
- Fix requirement：定义 typed query signature、输入 identity tuple、Run/Attempt/dispatch owner join、terminal Run读取规则、linked `CANCEL_REQUESTED` strict validation、返回类型与 stale identity过滤；不得用仅扫描 `CANCELLING` 的 query代替。

### DS-F05 — accepted

- 来源：AgentDS F-05。
- 裁决：Slice 2 target recovery 与旧 count-based proactive state machine并存时，crash后的 incomplete request可能被再次wake并创建第二operation。禁止临时兼容 branch或只在测试中绕过。
- Fix requirement：修订 slice handoff与completion语义，明确该 residual risk由后续已批准Slice 3收口且Slice 2 checkpoint不可发布，或调整依赖使中间状态不对外宣称production-complete；必须增加 Slice 2/3边界测试和最终同PR交付约束。若无法形成可审查的稳定checkpoint，应合并相关slice并解释上下文成本。

### DS-F06 — accepted

- 来源：AgentDS F-06。
- 裁决：当前已知产品调用方为CLI，但 `Host` 是public contract；非UI/headless/script/test harness必须有自足lifecycle说明。
- Fix requirement：明确任何直接 Host mutation caller都必须先持有唯一live attachment；Service不代持或推断；补public Host direct-call rejection与explicit attach测试。

### DS-F07 — rejected-with-reason

- 来源：AgentDS F-07。
- 理由：control doc要求考虑每个新增slice的review/gate成本。Slice 4 已把 cancel独立于普通attachment/recovery，且有focused cancel validation先于docs/full regression；另拆docs-only slice不增加独立业务回滚语义。若实现diff显示cancel范围超出单次review容量，再由code review裁决调整，不在plan阶段预增第五slice。

## Accepted fix requirements

1. 消除同 handle / Session 重复attachment的RW/RO契约矛盾，定义typed conflict与共享runtime owner规则。
2. 精确化attachment close与Host close的gate、actor drain、pre-start lease drain、mutex release、scheduler close顺序，并证明bounded timeout。
3. 为periodic owned-session reconciliation定义非flaky的一次性生产step与确定性测试机制。
4. 定义terminal后仍可读取的execution-owner exact cancel query contract。
5. 修正Slice 2→3 incomplete proactive crash residual的handoff、checkpoint发布边界与测试，不引入临时兼容代码。
6. 补充非UI/direct Host调用方attachment lifecycle contract与测试。
7. 补充Slice 2 listed fixture/helper的测试迁移completion checklist。

## Residual risk reconciliation

- Windows strict-native backend：仍由Slice 1与Windows环境验证；owner=`WU-CTX-04 Slice 1`。
- `dispatch.py`职责增长：deferred到Slice 2/4 code review；owner=`AgentMiMo / AgentDS reviewers`。
- Provider结果在crash窗口不可exactly-once：保留为已分类operational risk；destination=`Slice 3 implementation artifact/final closeout`。
- Fresh schema不兼容旧库/旧workspace config：design-approved，destination=`future migration WU only if user requests upgrade`。

## Completion status

- Plan review gate：`needs-fix`
- Accepted findings：8（其中 MIMO-001 与 DS-F03 合并为一个fix requirement）
- Rejected findings：3
- Deferred findings：1
- Needs-more-evidence findings：0
- Next gate：plan fix by AgentCodex
