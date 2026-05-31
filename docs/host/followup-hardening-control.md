# Host 后续 Hardening 实施总控

本文档是 Host 后续 hardening、契约收敛与生产化补强工作的实施总控文档，用于逐条讨论、设计、计划、实施和验收。

设计真源仍为 `docs/host/design.md`。若本文档与设计真源冲突，以设计真源为准；若需要改变 Host 公共契约、状态机、schema 或跨层边界，必须先回到 design gate。

## 管理范围

本文档只管理尚未完成、需要后续 work unit 或 design gate 的项目。已实施完成的项目不进入本文档。

## 推进规则

- 每次只进入一个 work unit 的 discussion / design / plan / implementation gate。
- discussion 阶段必须先核对代码现状，再判断原风险是否仍成立。
- 若风险已被后续代码覆盖，关闭或收敛该条，不做表面实现。
- 若风险成立，先明确 root cause、边界、非目标、验收信号和测试入口。
- 涉及 public contract、durable schema、状态机、跨层依赖或用户可见行为时，必须先更新设计或形成 design decision。
- implementation 完成前，必须给剩余风险指定 owner / destination。

## 当前入口

当前下一条讨论项：

- `WU-STRESS-01`：Host crash / recovery / watch / SQLite stress suite。

当前 gate：

- discussion：核对现有代码，确认追踪项中哪些已经完成、哪些仍需设计或实施。

## Work Units

### WU-CM-02 working_assumptions 生产者语义

Owner / destination：Conversation Memory / Context Governance design gate。

状态：已纳入 GitHub Issue #81 的 Conversation Memory 整体优化；本条保留留痕，不单独进入 discussion / implementation。

目标：

- 裁决 `working_assumptions` 是否保留。
- 若保留，定义它由哪些 compact / user / diagnostic event 生产。
- 若不保留，通过 schema / durable / renderer gate 删除该字段。

待讨论项：

- 当前字段已有类型、序列化、渲染、去重和 budget limit，但缺少生产路径。
- 保留该字段会增加 snapshot 契约面积；删除该字段会触及 durable schema 与 RunInputBuilder 渲染。
- 该字段不得承载工具事实或财报事实，避免绕过 evidence-backed fact 主链路。

验收信号：

- 字段存在即有明确生产者、消费者和测试。
- 字段不存在则 schema、snapshot codec、durable items、RunInputBuilder 和测试全部同步收敛。

### WU-CM-03 fact-candidate-only validation failure 策略

Owner / destination：Conversation Memory / Context Governance design gate。

状态：已纳入 GitHub Issue #81 的 Conversation Memory 整体优化；本条保留留痕，不单独进入 discussion / implementation。

目标：

- 裁决 `CONTEXT_COMPACTED` 中 fact candidates 非法但其它 compact output 合法时，是否继续 partial materialize。

待讨论项：

- 当前行为是记录 diagnostic，不物化 evidence-backed facts，但继续投影 episode summary、pinned state 和 minimum preserve。
- 继续 partial materialize 的收益是减少 compact 全量失败；风险是 memory 变短但 stable facts 缺失。
- fail closed 的收益是事实一致性更强；风险是 compact 更容易阻断上下文治理。

验收信号：

- quality check、payload validation、memory projection、diagnostic 与用户可见失败策略一致。
- 测试覆盖 fact candidates invalid / non-fact compact fields invalid 两类路径。

### WU-CM-04 minimum preserve 与 Fins 事实边界

Owner / destination：Conversation Memory / Fins tool provider integration design gate。

状态：已纳入 GitHub Issue #81 的 Conversation Memory 整体优化与后续 Fins integration 边界；本条保留留痕，不单独进入 discussion / implementation。

目标：

- 确认 `minimum preserve` 继续作为 bounded continuity item，而不是事实真源。
- 明确后续 Fins 接入时不得把 minimum preserve 文本当作财报事实引用。

待讨论项：

- minimum preserve 可保护指代解析和短期交互连续性，但不替代 accepted evidence 或 evidence-backed fact。
- Fins 工具若需要财报事实，必须通过 tool result accept path 形成 accepted evidence，再由 Host-governed compact extraction 生成 stable facts。
- 若 UI 或 Service 展示 minimum preserve，需要避免把它标成 verified / sourced fact。

验收信号：

- Fins / ToolRuntime / RunInputBuilder 文档和测试均不把 minimum preserve 当 stable fact。
- minimum preserve 的 source refs 只服务 continuity，不成为财报引用真源。

### WU-FINS-01 Fins provider and storage integration

Owner / destination：Fins / financial tool provider work unit。

状态：已纳入 GitHub Issue #82；本条保留留痕，不单独进入 discussion / implementation。Issue scope 是从 `dayu-agent/fins` 迁移长期运行验证可靠的 Fins 代码，只允许修改 `@tool` 与 ToolDiscovery 接口适配部分，不允许修改其它 Fins 业务代码。

代码核对：

- 当前代码树没有 `dayu/fins/` 与 `tests/fins/` 目录。
- Host / Service 侧已有工具发现和 Host public API 装配能力，但没有财报仓储 provider 接入点。

目标：

- 新增或接入 `dayu.fins.storage` 下的财报仓储协议与实现。
- 财报工具 provider 通过 ToolsDiscovery 进入 Host，而不是由 Host 扫描业务工具。
- 财报工具结果进入 accepted evidence 主链路。

非目标：

- 不把财报原文存取放入 Host / Service / runtime。
- 不把 minimum preserve 或 compact summary 当作财报事实真源。

验收信号：

- Fins storage、tool provider、ToolsDiscovery 和 ToolRuntime accept path 有端到端测试。
- `evidence_backed_facts` 仍只由 Host-governed compact extraction 生成。

### WU-SVC-01 Product entrypoint Host assembly contract

Owner / destination：Service / CLI / Web / GUI integration work unit。

状态：已拆分为 GitHub Issue #83、#84、#85；本条保留留痕，不单独进入 discussion / implementation。CLI issue 要求命令行参数对齐 `dayu-agent` CLI。

代码核对：

- `dayu/service/host_assembly.py` 已实现 ConfigLoader / ScenePrepare / ToolsDiscovery 到 Host public API 的装配 helper。
- `tests/service/test_host_assembly.py` 已覆盖装配 helper 的核心映射。
- 当前剩余风险不在 helper 本身，而在真实产品入口是否全部复用该边界。

目标：

- 为真实 CLI / Web / GUI / workflow 入口补齐 contract 或 smoke tests。
- 证明入口只通过 Service assembly 与 Host public API 交互。
- 证明入口不传 raw config fragment、manifest raw patch 或业务仓储实现细节给 Host。

非目标：

- 不重写已落地的 Service assembly helper。
- 不在 Host 内新增 UI / CLI 专用分支。

验收信号：

- 每个真实产品入口至少有一个不绕过 Host public API 的集成测试。
- Service 仍在 Host 外完成 override merge、runner / agent mapping、tool bundle subset selection、prompt injection、parser / retry / replay / stop policy。

### WU-AUDIT-01 Purge audit cross-medium orphan reconciliation

Owner / destination：Host purge / audit durability hardening work unit。

状态：discussion 裁决已写入设计真源；待后续统一按 phaseflow / gateflow 实施。

代码核对：

- purge tombstone 审计会写 JSONL，也会写 SQLite tombstone。
- JSONL append 是 SQLite commit 之外的外部副作用；若 append 成功后 SQLite commit 失败，可能留下 tombstone-less audit line。

目标：

- 将 purge audit JSONL 语义收敛为 destructive 操作流水，而不是 purge 完成真源。
- 至少区分 `purge_started` 与 `purge_completed`：started 只表示 purge attempt；completed 必须在 SQLite tombstone commit 成功后写入并引用 tombstone id / digest。
- 可选写入 `purge_failed`，记录失败阶段和原因。
- audit 查询 / analyze 必须以 SQLite tombstone 判断 purge 是否完成；只有 started 而无 completed / tombstone 时，只能报告 incomplete attempt，不得报告 purge 已完成。

非目标：

- 不扩大为通用审计管道治理。
- 不让 audit JSONL 反向成为 Host durable truth。

验收信号：

- 测试覆盖 started audit 写入成功但 SQLite purge / tombstone commit 失败的路径，并断言不会误报 purge 已完成。
- 测试覆盖 tombstone commit 成功后 completed audit line 引用 tombstone id / digest。
- audit analyze / diagnostic 能解释 started-only、completed-with-tombstone、failed 三类状态。

### WU-STRESS-01 Host crash / recovery / watch production stress suite

Owner / destination：Host production stress work unit。

代码核对：

- 代码已有多类单元和集成测试覆盖 recovery、transaction、projection、lane 与 public lifecycle。
- SQLite 多进程写入已有普通 deterministic / stress 覆盖，包括 EventLog append、同 `event_id` 多进程异体写入压力、admission、recovery 与 runtime lane；GitHub Issue #38 是这条 SQLite 多进程压力测试链路的高规格版本，负责在慢硬盘 / Docker Linux 环境下放大验证。
- 当前普通 SQLite 多进程压力测试足够作为日常语义回归：可以防住主要 EventLog sequence、identity conflict、admission invariant、recovery takeover 与 runtime lane capacity 回归；但它不宣称覆盖慢盘 / Docker Linux / 高延迟文件系统下的 WAL、busy retry、fsync、checkpoint 与 IO jitter 风险，这部分仍归 GitHub Issue #38。
- 本条不重复拆出 SQLite 多进程写入压力；剩余缺口集中在 Host 组合行为压力：crash recovery、watch 轮询 / cursor lag、scheduler / liveness 长时间运行，以及这些行为同时发生时的可恢复性。

目标：

- 建立可重复运行的生产 hardening stress suite。
- 覆盖 repeated startup / recovery / crash E2E：反复启动 Host、提交 Run、在 worker accepted / running / terminal closeout 附近制造进程退出，再 reopen，验证不会重复 terminal、不会漏 recovery event、不会错误恢复 live owner。
- 覆盖 sustained watch stress：多个 session / run 持续产生日志与 terminal event，watcher 长时间消费、慢消费、断开后重连时，验证 cursor 不倒退、不漏关键 terminal、observer lag 有上界且有诊断输出。
- 覆盖 scheduler / liveness long-run stress：大量 queued / active / terminal / cancel / recovery 混合流转下，验证 scheduler 不停摆、host instance heartbeat / stale 判断可解释、close 后无遗留 active task。
- 覆盖 mixed Host stress：在 fake worker / fake clock / deterministic fault injection 下组合 crash、recovery、watch 和 scheduler 压力，证明 Host 仍然可恢复、可观察、可终止。
- 与 GitHub Issue #38 互补：#38 不是全新测试类别，而是现有 SQLite 多进程压力测试的高规格环境版，负责在慢硬盘 / Docker Linux 下放大 SQLite WAL、busy timeout、fsync、文件锁和 IO jitter 风险；本条负责 Host 组合行为在压力条件下是否仍然可恢复、可观察、可终止。

非目标：

- 不用 stress suite 替代精确单元测试。
- 不放进默认常规测试入口；pressure / stress 测试必须与 unit / integration / public smoke 分开，后续 GitHub workflow 可以选择不纳入这些长耗时测试。
- 不在测试中依赖不可控睡眠或外部服务。
- 不重复实现 GitHub Issue #38 负责的 SQLite 多进程压力测试高规格运行形态。

验收信号：

- stress suite 有独立运行入口、明确 marker / 命令、超时预算和失败诊断；默认快速 pytest / 常规 GitHub workflow 可以排除它。
- 每类压力测试输出结构化摘要，包括 session / run 数、crash 次数、recovery 次数、watch lag、scheduler drain 状态、liveness stale 判断和 terminal 去重结果。
- 压测失败能定位到 durable、scheduler、watch、liveness 或 recovery 边界。

### WU-DUR-01 Schema bootstrap / DDL atomicity / WAL checkpoint policy

Owner / destination：Host durable hardening work unit。

代码核对：

- durable transaction 已有 `BEGIN IMMEDIATE`、WAL、busy retry 和 after-commit 多错误聚合测试。
- `bootstrap_host_durable_store(...)` 当前按 `HOST_DURABLE_DDL` 逐条执行 `CREATE ... IF NOT EXISTS`，最后写 `PRAGMA user_version` 并 `commit`；代码没有显式把 fresh bootstrap DDL 与 `user_version` 写入包进同一个 bootstrap transaction。
- `validate_host_schema_version(...)` 当前只校验 `PRAGMA user_version`；若 current-version DB 缺表 / 缺索引，当前 bootstrap 的 `IF NOT EXISTS` 语义可能静默补建，而不是把损坏 schema 作为 durable corruption / unsupported repair 诊断出来。
- connection PRAGMA 已启用 WAL、`foreign_keys=ON`、busy timeout 和固定 `wal_autocheckpoint=256`，并有测试覆盖；但没有 Host-owned manual checkpoint / maintenance policy、checkpoint 失败诊断或 WAL 增长观测入口。
- `run_read(...)` 使用普通 `BEGIN` read transaction；SQLite snapshot 在单个 read transaction 内稳定，可能看不到 transaction 开始后其它 connection 的新提交。代码已有 read busy retry，但没有把 stale-read 允许窗口、刷新方式和 public read / recovery governance 的新鲜度要求写成契约。

目标：

- 明确 fresh bootstrap 原子性：fresh DB 的全量 DDL 与 `PRAGMA user_version` 必须同成同败；DDL 中途失败不得留下带 current `user_version` 的半初始化 durable store。
- 明确 current-version schema validation：普通 opener 不得把缺表 / 缺索引的 current-version DB 静默修好；需要结构化失败或显式 offline repair / rebuild 工具，避免把 durable corruption 当成正常启动。
- 设计 WAL checkpoint 策略：现有 auto-checkpoint 是 baseline；后续 maintenance checkpoint 必须有独立触发点、运行时机、失败诊断、WAL size / checkpoint result 观测，不得把 checkpoint 成功作为 EventLog correctness 前置条件。
- 定义 read stale 语义：单个 read transaction 内允许稳定旧快照；需要 fresh truth 的 public read / recovery / scheduler governance 必须开启新的短 read / write transaction，不得复用长 read transaction 或 projection snapshot 作为治理真源。

非目标：

- 不重做已存在的 busy retry、after-commit aggregation 或基础 transaction wrapper。
- 不引入旧 schema 兼容迁移。
- 不在 Host hot write path 内做阻塞型 WAL checkpoint。
- 不把 read model / projection lag 当作 Host governance truth。

验收信号：

- 有直接测试模拟 bootstrap DDL 中途失败，断言不会留下 current `user_version` + 半初始化 schema；下一次 open 要么从 fresh 状态完整成功，要么以结构化 schema / corruption 错误失败。
- 有直接测试构造 current `user_version` 但缺少 required table / index 的 DB，断言 opener 不静默补建并继续运行。
- WAL checkpoint 行为可观测、可测试，且不破坏并发读写；checkpoint busy / failure 有诊断，不改变 EventLog / state truth。
- read stale 语义有直接测试：长 read transaction 可观察旧快照，新 read transaction 必须观察到已提交事实；public read / recovery governance 不依赖长 read transaction 或 projection lag。

### WU-DUR-02 Durable concurrency conflict matrix

Owner / destination：Host durable hardening work unit。

代码核对：

- projection checkpoint、memory snapshot、transaction retry 已有专门测试。
- 仍需要把 EventLog append、idempotency write、session ensure、projection CAS、memory CAS、liveness update 放入同一个并发冲突矩阵验证。

目标：

- 本条首先是测试 hardening：先整理 durable 并发冲突矩阵，核对已有测试覆盖，再只补缺口测试；不预设需要重写 durable 层。
- 梳理 durable 写入面的唯一键冲突、CAS 失败、busy retry、rollback failure 与 liveness update 行为。
- 补齐直接单元测试和必要的多进程压力测试。
- 只有当新增测试暴露错误分类、诊断或并发语义不稳定时，才修改生产代码。

非目标：

- 不把所有 durable 操作抽象成同一个 God helper。
- 不用 broad exception catch 掩盖 SQLite extended result code。
- 不为了统一测试而重构已有稳定 durable API。

验收信号：

- durable concurrency matrix 明确列出每类场景的已有测试、缺口测试、期望错误分类和是否需要多进程验证。
- 每类冲突都有稳定 reason / diagnostic。
- 并发测试能区分可重试 busy、业务冲突、CAS stale 和不可恢复 I/O 错误。

### WU-PROJ-01 Projection catch-up budgeting for memory pre-dispatch path

Owner / destination：GitHub Issue #86（memory pre-dispatch projection catch-up budgeting）。

代码核对：

- Audit / Tool Trace / Outbox 在设计上已经明确是 committed EventLog 的异步 sink；它们不应影响 EventLog append、Host command path 或 dispatch path 性能，若有影响应作为 bug 修复，而不是本条优化范围。
- Session timeline / RunResult 是 minimal read model / UI projection，不是事实真源；当前 public read path 从 durable Session / Run / EventLog truth 构造 snapshot，不依赖 projection checkpoint。`repair_minimal_read_models(...)` 已有 batch 参数，主要保留为 repair / rebuild helper。
- Conversation Memory snapshot 是特殊 read model：RunInputBuilder 在 dispatch 前必须校验 snapshot cursor 覆盖所需 EventLog cursor，因此 memory projection catch-up 会进入 pre-dispatch 路径。
- 当前 `catch_up_conversation_memory_projection(...)` 有 `batch_size`，但会循环直到 idle 或 failure；`batch_size` 只限制单批 transaction 大小，不限制一次 catch-up 的总批数、总扫描事件数或总耗时。

目标：

- 由 GitHub Issue #86 跟踪并实施。
- 聚焦 memory projection catch-up / rebuild 在 pre-dispatch 路径上的预算、背压和诊断边界。
- 为 memory catch-up 定义总预算，而不仅是单批大小，例如 max batches、max scanned events、timeout 或等价 bounded execution policy。
- 明确 admission after-commit 的 catch-up 只能是 bounded best-effort 或 wake background supervisor，不得在 command path 上无上限追平。
- 明确 dispatch 前 catch-up / rebuild 的行为：成功追到 required cursor 时继续 dispatch；超预算或失败时产生结构化 diagnostic；不得把 memory projection lag 当作 Run recovery；不得改变 EventLog / Run / Attempt truth。

非目标：

- 不改变 EventLog 作为投影真源的语义。
- 不让 projection lag 影响 recovery truth。
- 不把 Audit / Tool Trace / Outbox 纳入本条；这些 sink 若影响 EventLog append 或 command latency，应按 bug 处理。
- 不重写 ProjectionRunner 为大型调度系统。
- 不把所有 projection sink 合并成 God runner。

验收信号：

- memory projection catch-up 的单批大小与单次总预算边界均有明确代码或配置表达。
- admission after-commit catch-up 不会无上限同步追平大量 EventLog。
- dispatch 前 memory catch-up / rebuild 超预算或失败时有结构化 diagnostic，且不会改写 EventLog / Run / Attempt governance truth。
- 测试覆盖 bounded catch-up、required cursor 已覆盖、lag / failure / rebuild 超预算不误触发 recovery，以及 Audit / Tool Trace / Outbox 不被改成 command-path blocking sink。

### WU-LIFE-01 Recovery lifecycle proof and diagnostics

Owner / destination：Host dispatch / recovery lifecycle work unit。

代码核对：

- Host 已有 startup recovery、public lifecycle 和 orphan/recovery 相关测试。
- 剩余项和 WU-DUR-02 类似，主要是 recovery lifecycle 决策矩阵与测试矩阵补强，而不是单个 API 缺失，也不预设需要重写 recovery 生产逻辑。
- 当前已有测试覆盖 `ACCEPTED` / `QUEUED` startup wake、`WAITING` diagnostic-only、`RUNNING` positive orphan recover、`CANCELLING` orphan lost、`RECOVERING` dispatch limit、recovery dispatch、late old execution rejection、multiprocess crash reopen recovery 与 projection lag 不阻断 recovery。
- 未覆盖或覆盖不成矩阵的部分集中在：不同 Run 非终态、owner liveness / process proof、startup timeout closeout、promotion deferred result、fatal stream / cancel / close diagnostic 之间的组合解释是否唯一。

目标：

- 先整理 recovery lifecycle matrix，列出 Run 状态、owner proof、dispatch / startup / stream 失败点、期望 decision、期望 durable mutation、期望 diagnostic reason。
- 对照已有测试只补缺口测试；只有当测试暴露 reason 不可区分、diagnostic payload 不足或状态转换不稳定时，才修改生产代码。
- 补齐 liveness proof、promotion deferred result、startup timeout closeout diagnostic、recovery orphan proof 的组合验证。
- 明确 `WAITING` startup recovery 仅 diagnostic 的用户可见语义。

非目标：

- 不改变 WAITING 本身的 durable 状态语义，除非先通过 design gate。
- 不把 recovery proof 写成只验证实现细节的 brittle test。

验收信号：

- recovery 后每类 orphan / deferred / startup-timeout 状态都有唯一解释路径。
- diagnostic payload 足以区分恢复、关闭、取消和 fatal stream。
- 测试矩阵能标注每个场景是已有覆盖、新增覆盖还是明确非目标；新增测试不依赖竞态运气或实现私有顺序。

### WU-LIFE-02 Scheduler close / cancel_all lifecycle hardening

Owner / destination：Host scheduler lifecycle work unit。

代码核对：

- 当前 scheduler close 已设置 `_closed`、取消 heartbeat / dispatch drain / promotion drain task、调用 `ActiveWorkerRegistry.cancel_all("scheduler_close")`、取消 active consume tasks、关闭 lane controller，并将当前 host instance best-effort 标记为 stopping / stopped。
- `ActiveWorkerRegistry.cancel_all(...)` 当前是快照语义：只取消调用瞬间 registry 中已有的 active worker；后续新注册 worker 需要由 scheduler close 的 `_closed` gate、active task cancel 与 lane close 共同兜底。
- 现有测试已覆盖 active worker close 释放 lane / registry、handle cancel / close 异常不打断 close、close 后 wake fail closed、重复 close 幂等、promotion task close cancel、drain loop durable retry exhausted fail-close、dispatch empty-window wakeup 不遗留等。
- 剩余风险集中在 close / cancel_all 的极端窗口矩阵，而不是常规 close API 缺失：例如 cancel_all 快照后 worker 才注册、close 时 dispatch / promotion queue 非空、worker 已 accept 但 consume task 尚未稳定注册、close 中途被外部取消、close 期间不得隐式写 terminal facts。

目标：

- 先整理 scheduler close / cancel_all lifecycle matrix，明确 close 前、close 中、close 后各窗口的期望行为。
- 明确 `cancel_all` 是快照取消语义；后续注册 / 启动窗口必须由 close gate、active task cancellation、lane close 与 next-open recovery 兜底，而不是要求 `cancel_all` 无限追踪未来 worker。
- 明确 close 不无限 drain dispatch / promotion queue；内存队列剩余项不在 close 中强行执行，durable pending / running 状态由下次 open 的 recovery / promotion / dispatch 解释。
- 明确 scheduler close 本身不写 cancel / failed / lost terminal facts；只有已经进入明确 worker stream / engine ingest closeout 的路径可以写 terminal facts。
- 对照已有测试只补缺口测试；只有测试暴露资源泄漏、terminal fact 误写或诊断不可解释时，才修改生产代码。

非目标：

- 不把 close 设计成无限 drain。
- 不让 close 隐式创建新 Run terminal 状态。

验收信号：

- close 中途取消、重复 close、queue 非空、worker 已启动但未入 durable 状态、cancel_all 快照后新注册窗口都有稳定行为。
- close 后 wake 方法 fail closed；close 不无限 drain，也不静默丢失 durable truth。
- scheduler close 不因自身动作追加 cancel / failed / lost terminal facts；相关非终态由下一次 open 的 recovery / promotion / dispatch 解释。
- 测试矩阵能标注每个场景是已有覆盖、新增覆盖还是明确非目标；新增测试不依赖竞态运气。

### WU-LIFE-03 Active cancel watchdog and post-cancel timeout

Owner / destination：GitHub Issue #91 / Host lifecycle watchdog target work unit。

状态：已纳入 GitHub Issue #91；GitHub Issue #87 已调整为 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 active Attempt cancel watchdog target，不单独引入第二套 watchdog runtime。

代码核对：

- active cancel 已有基础路径：`cancel_run` / `cancel_session_runs` 在 durable transaction 中把 active `RUNNING` Run 推进到 `CANCELLING`，commit 后返回 `ActiveCancelTarget`，command 层再通过 `ActiveWorkerRegistry` best-effort 传播 cancel。
- registry 会设置 Host 注入 worker 的 cancellation token，并调用 worker handle `on_cancel(reason)`；worker 若配合产出 `RUN_CANCELLED`，Engine ingest 会把 Run / Attempt 收口为 `CANCELLED`。
- 现有测试覆盖 worker 配合取消、late cancel 不覆盖已完成 terminal、session cancel replay 重新传播 active cancel。
- 剩余问题是 active worker 取消后，外部 provider / stream 不返回、不结束或不检查 cancellation token 时，当前缺少明确 watchdog 与 post-cancel timeout closeout policy。

目标：

- 本条是较大的 lifecycle governance feature，不作为普通测试矩阵 hardening 顺手实施。
- 复用 #87 的 Host lifecycle watchdog / supervisor，不另建 active cancel 专属 watchdog。
- 先裁决 active cancel watchdog owner、timeout policy、Run / Attempt 终态、diagnostic payload、late terminal race 与 session cancel replay 语义。
- 明确 post-cancel timeout 后 Run / Attempt / diagnostic 的收敛路径，以及 first-committer-wins / late rejection 规则。

非目标：

- 不直接 kill 不属于 Host 管理的外部进程。
- 不把 provider-specific cancel API 硬编码进 Host 核心。
- 不把 scheduler close 设计成 active cancel timeout closeout。

验收信号：

- provider 卡死、stream 不结束、worker task 不响应 cancellation 时都有可测试 closeout。
- terminal event 与 diagnostic 不重复、不互相矛盾。
- GitHub Issue #87 明确跟踪设计问题、非目标和验收测试；实施前需要先回到 design gate。

### WU-GOV-01 Host governance terminal taxonomy

Owner / destination：GitHub Issue #88（Host governance schema / state-machine design gate）。

状态：已裁决需要引入 `REJECTED`；后续由 GitHub Issue #88 跟踪设计与实施。

代码核对：

- `RunStatus` 当前没有 `REJECTED`。
- pre-dispatch governance failure 使用 attempt-free `RUN_FAILED`。

目标：

- 引入 `RunStatus.REJECTED`，用于表达 Host governance 在执行前或执行外拒绝 Run，而不是复用执行失败语义。
- 裁决 rejected Run 的 canonical EventLog taxonomy，例如是否新增 `RUN_REJECTED`。
- 明确 hard threshold / compact failure / pre-dispatch governance failure 等场景哪些进入 `REJECTED`，哪些仍保留为 `FAILED`。
- 同步 Run status、EventLog reason、projection、public contract、retry / replay 前置条件、outbox / HostEvent 映射、文档与测试。

非目标：

- 不为单个 failure reason 临时增加状态。
- 不让 Attempt terminal taxonomy 承担 Run-level governance 语义。

验收信号：

- 用户可见 terminal status 与治理失败 reason 单一、不重叠。
- public contract freeze test 同步更新。

### WU-CTX-01 Provider tokenizer / sizing adapter

Owner / destination：GitHub Issue #20（Context Governance provider tokenizer / sizing adapter）。

状态：已由 GitHub Issue #20 跟踪；Issue 已更新为 WU-CTX-01 当前 scope。

代码核对：

- Context budget 已有估算与 compact 流程。
- 未看到 provider-specific tokenizer / sizing adapter 作为公共能力接入。

目标：

- 为不同 provider 的 token / context sizing 建立 typed adapter。
- 让 proactive / reactive compact 决策使用同一 sizing 入口。

非目标：

- 不在 Context Governance 中硬编码 provider 名称分支。
- 不让 Engine provider 实现反向依赖 Host。

验收信号：

- provider sizing 差异有单元测试。
- compact 前后 budget estimate 与 provider adapter 输出一致。

### WU-CTX-02 Compact failure user-visible policy and E2E matrix

Owner / destination：Context Governance failure-policy work unit。

定位：本条主要补 compact failure 策略矩阵和端到端测试，不预设要重写 compact 核心逻辑。Compact 是 Host 核心组件，因此不允许无解释失败、半成功提交或状态不清；但 LLM compactor、provider、artifact I/O 和 token sizing 都可能失败，生产语义必须是分层兜底与 fail-safe，而不是假设组件永不失败。

代码核对：

- LLM compaction adapter 与多种 compaction failure / retry 测试已经存在。
- 剩余风险是用户可见策略矩阵是否覆盖 proactive、reactive、semantic repair、post-compact overflow 的组合。

目标：

- 建立 compact failure 策略矩阵，列出触发来源、失败类型、retry / repair 策略、是否允许 deterministic fallback、最终 EventLog、Run 终态、用户可见结果和测试入口。
- 明确 compact failure 何时 retry、何时 partial materialize、何时 fail closed、何时只记录 diagnostic。
- 补齐 proactive / reactive compact failure E2E。
- 将默认 `max_compaction_attempts_per_operation` 提升到 5 次；同时对齐 execution profile 默认值与 Host policy code fallback 默认值，避免配置默认与代码默认语义分裂。
- 默认 compact 模型使用低延迟 flash-tier 模型。Compact 是低温度、无工具、结构化 JSON proposal 任务，优先需要快、稳定、可重试；不默认使用 thinking / pro 模型。若高规格 profile 需要更强模型，应通过 execution profile 显式切换。
- 清理 compactor model 默认来源不一致：`execution_profiles.json` 的 `compactor_baseline.model_id` 与 `conversation_compaction` scene manifest 的 `model.default_model_id` 不应给出互相矛盾的 packaged default。实施时需要明确 execution profile 是 compactor model selection 的治理真源，并让 scene manifest 默认与 packaged profile 对齐，或将 scene manifest 默认降级为非治理 fallback。
- 为核心 compact 可靠性定义分层兜底：优先 deterministic material selection / 去重 / 分段缩小输入；其次 LLM compactor bounded repair；LLM compact 仍失败时退回 deterministic recent-window fallback；最后才进入明确的 rejected / failed terminal。
- deterministic recent-window fallback 不是 compact 成功：它不提交 `CONTEXT_COMPACTED`，不生成 episode summary、minimum preserve 或 stable facts，只为本次 dispatch 构造类似首次 compact 前的 bounded input view，例如当前输入、最新 N 轮 raw turns、至少 M 轮 recent raw floor、已有 stable facts、answer anchors、open task state 和必要 refs。
- fallback 后必须重新估算预算；能放下才 dispatch，仍超预算则按 WU-GOV-01 的 `REJECTED` / fail closed 策略收口。
- 若 WU-GOV-01 引入 `REJECTED`，pre-dispatch proactive compact 无法收敛时应优先归入 governance rejection，而不是混入普通 execution failure。

非目标：

- 不改变 `WU-CM-03` 的 fact-candidate-only 裁决；若需要改变，先回 design gate。
- 不吞掉 compactor 失败。
- 不承诺 LLM compactor 永不失败；本条要求失败可解释、可恢复或可安全收口。
- 不让 deterministic fallback 生成 evidence-backed facts 或替代 accepted evidence。
- 不把 deterministic recent-window fallback 写成 durable memory projection；它只是本次 RunInputBuilder 的有界输入视图。

验收信号：

- 每类 compact failure 都有用户可见或 diagnostic 结果。
- 默认 compact retry budget 为 5 次 semantic proposal / repair attempts；测试覆盖首轮失败、repair 成功、repair 耗尽与 fallback 收口。
- packaged 默认 compact model 与 scene / execution profile 配置一致；默认路径使用 flash-tier 模型，高规格模型只能由 profile 显式选择。
- post-compact budget estimate 失败不会产生 silent overflow。
- proactive / reactive / semantic repair / post-compact overflow 的组合矩阵标注已有测试、新增测试或明确非目标。
- deterministic recent-window fallback 若被采用，只能保留 bounded recent continuity / refs / current input / 已有 stable facts，不得伪造 stable facts；仍超预算时必须明确 terminal，不得继续 dispatch。
- compact failure 不会留下 orphan Attempt、重复 terminal、partial compacted event 或 memory projection 半物化。

### WU-CTX-03 Reactive overflow dispatch loop E2E

Owner / destination：Context Governance / dispatch integration work unit。

定位：本条是小型 E2E 测试补强，不是大 feature。deterministic recent-window fallback 落地后，reactive overflow 反复 compact / dispatch 的概率会显著降低；但仍需要一条 dispatch-loop E2E 证明 fallback 未兜住、估算偏差或 provider 持续 overflow 时，Host 会按 `max_reactive_compactions_per_run` 明确收口，不会无限创建 Attempt / compact / dispatch。

代码核对：

- policy 中已有 `max_reactive_compactions_per_run` 一类上限概念。
- ingest 层已有重复 overflow 达到上限后 fail closed 的测试；dispatch scheduler 层已有一次 overflow -> compact -> recovery Attempt -> final answer 的 E2E。
- 仍需从完整 dispatch loop 入口补一条连续 overflow E2E，验证多次 worker/provider overflow 经过 scheduler / ingest / recovery 串联后，最多执行指定次数并 fail closed。

目标：

- 建立 reactive overflow 从 RunInputBuilder、compaction、retry 到 terminal / diagnostic 的端到端测试。
- 确认循环上限和失败收敛路径。
- 验证 deterministic recent-window fallback 未能放下输入或 policy 不允许继续时，仍由 reactive 上限兜底收口。

非目标：

- 不提高默认 compact 次数来掩盖 sizing 错误。
- 不把 overflow 处理放进 Engine。
- 不重复测试 ingest 层已经覆盖的单点计数逻辑；本条只补 dispatch-loop 组合路径。

验收信号：

- 连续 overflow 不会无限循环。
- terminal / diagnostic 能说明 compact 次数、最后一次失败原因和是否已 fail closed。
- E2E 能观察到 Attempt 数、`CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 事件数和最终 Run terminal 状态均符合上限策略。

### WU-TOOL-01 Duplicate governance concurrency and cross-attempt semantics

Owner / destination：ToolRuntime hardening work unit。

定位：本条不是单纯补测试，而是 ToolRuntime duplicate concurrency 的生产行为变更。当前实现按 run-scope 记忆 duplicate；后续需要改为 attempt-scope，只治理同一次 LLM 调用 / 同一 Attempt 内的重复工具执行风险。

代码核对：

- ToolRuntime 已有 truncation / fetch_more / cursor / duplicate governance 基础测试。
- 当前设计与代码都是 run-local duplicate governance；讨论裁决已改为 attempt-scoped execution guard，需要同步修改设计、实现和测试。
- duplicate governance 的目标收敛为防止同一次 LLM 调用 / 同一 Attempt 内模型复读式工具循环；跨 Attempt 的同 tool + 同 args 调用默认视为新的工具请求，不由 duplicate governance 复用或阻断。

目标：

- 将 duplicate governance key / index 从 run-local 改为 attempt-scoped，scope 必须包含 `attempt_id`。
- 验证同一 Attempt 内同工具同 args 并发调用只执行一次、复用已有 accepted result、提示或按 policy 明确拒绝。
- 明确 cross-Attempt ToolRuntime state 不继承 duplicate index；resume、steer、recovery 或 compact recovery 创建的新 Attempt 中，重复工具调用按新的工具请求处理。
- 清理或改写当前 run-local duplicate index 代码路径，避免 worker-local cache 成为跨 Attempt correctness 前提。
- 修改生产行为：旧 Attempt 已 accepted 的 duplicate entry 不得影响新 Attempt 的工具执行；新 Attempt 内首次同 key 调用应进入正常 tool execution / accept path，而不是 reuse / hint / hard_stop 旧 Attempt 的结果。
- 修改 duplicate concurrency 控制：同一 Attempt 内并发同 key 调用仍必须共用当前 Attempt 的治理结果，不能因为改成 attempt-scope 而退化成无保护的重复执行。
- 修改 diagnostic / trace：`TOOL_CALL_GOVERNED` 或等价 diagnostic 必须能表达 duplicate scope 是当前 Attempt，并记录当前 Attempt 内 prior event refs；不得把旧 Attempt accepted result refs 当作 duplicate 命中的依据。
- 同步清理测试 fixture、helper 和命名，避免继续使用 run-local duplicate index / run-local duplicate key 术语表达当前行为。

非目标：

- 不改变 accepted evidence 的事实语义。
- 不让 worker-local cache 成为 durable correctness 依赖。
- 不引入 tool result freshness、汇率 / 行情当前性、side-effect 幂等或跨 Attempt retrieval 复用策略；这些属于工具 policy、prompt assembly 或后续 retrieval 设计。
- 不从 EventLog 重建 durable duplicate ledger。

验收信号：

- 同一 Attempt 内并发 duplicate 有明确测试，且不会无解释重复执行。
- 跨 Attempt duplicate 有明确测试，证明不会命中旧 Attempt 的 duplicate index；新的 Attempt 按新工具请求执行或由工具自身 policy 处理。
- worker restart / Host restart 后不要求继承 duplicate index，测试或文档明确该行为不是 correctness 前提。
- diagnostic 能区分 attempt-scoped dedup 命中、重复拒绝、执行失败和 durable 缺失。
- 现有依赖 run-scope duplicate 命中的测试被删除或改写；不得通过兼容分支同时保留 run-scope 与 attempt-scope 两套行为。

### WU-TOOL-02 Accept candidate structure cleanup

Owner / destination：ToolRuntime / Conversation Memory cleanup work unit。

定位：本条是结构清理，不是工具行为变更。核心是把当前过大的 `ToolFactAcceptCandidate` / accept candidate dataclass 拆成一个顶层 candidate 组合若干个语义明确的小 dataclass，避免 identity、tool call、result payload、duplicate governance、policy、diagnostic、accept idempotency 和 evidence envelope 字段长期混在一个 god dataclass 里。

代码核对：

- `ToolFactAcceptCandidate` / accept candidate 结构仍属于 ToolRuntime 与 memory fact contract 的连接面。
- 该项是结构清理，和 duplicate governance 行为风险相关度不高，可以独立实施。
- 当前 `ToolFactAcceptCandidate` 同时承载 Attempt identity、tool call identity、schema / args digest、outcome / payload、truncation、duplicate governance、policy decision、diagnostic refs、accept idempotency、semantic digest 与 raw tool outcome，字段职责已经过宽。

目标：

- 收敛 accept candidate 的 typed structure、命名、producer 和 consumer。
- 将大 candidate 拆成组合结构，例如 identity、call、result、governance、accept idempotency、diagnostics 等分组；具体命名以实现时的局部代码边界为准，不预设 public API。
- 让普通 result、reuse、governed error 等不同 fact kind 的构造路径只填充各自需要的子结构，避免所有路径共享一个超宽构造器。
- 删除无生产者或无消费者的字段。
- 更新 `TOOL_RESULT_ACCEPTED` payload 构造、accept barrier validation、tool trace / memory / compaction 消费路径，使其通过新的 typed 子结构读取字段。
- 在 WU-TOOL-01 将 duplicate governance 改为 attempt-scoped 后，再整理 duplicate / reuse 相关子结构，避免围绕旧 run-scope 语义返工。

非目标：

- 不改变 evidence-backed fact 的生成门槛。
- 不引入兼容 wrapper 或旧字段 re-export。
- 不把内部 accept candidate 变成 Host public API。
- 不借结构清理改变 duplicate、freshness、side-effect、wait 或 accepted evidence 语义。

验收信号：

- ToolRuntime、compaction extraction、memory projection 和测试使用同一 candidate 类型。
- 类型检查不依赖 `object` / `Any` / magic payload。
- 测试 helper 不再到处手写超宽 `ToolFactAcceptCandidate` 构造参数；新增 / 修改测试可以按子结构覆盖局部字段。
- 拆分后无 god dataclass / god builder 回流，普通 result、reuse、governed error 的校验逻辑各自清晰。

### WU-WAIT-01 Callback endpoint / auth / replay

Owner / destination：GitHub Issue #89 / wait adapter integration work unit。

状态：research 已写入 GitHub Issue #89；本条后续按 callback adapter -> common `resolve_wait` pipeline 的方向实施。Claude Code 的 background subagent / lifecycle completion 行为可作为参考；Codex 具备 subagent orchestration，但公开 callback / hook surface 不应被假设为稳定生产 primitive。

代码核对：

- 当前 `wait_adapter` 是最小 poll adapter，不实现 callback endpoint 或外部协议。
- polling、abandon、adapter error isolation 已有基础测试。

目标：

- 设计 callback endpoint 的认证、幂等 replay、payload digest 和错误分类。
- 将 callback 与现有 wait resolve / idempotent replay 语义对齐。
- 明确 callback endpoint 只是 transport adapter：认证、解析、校验 envelope 后调用 Host `resolve_wait`；不得直接写 EventLog、Run、Attempt 或 wait record。
- callback / poller / manual resolve 必须共用同一个 durable wait resolution pipeline。

非目标：

- 不把 HTTP framework 细节放入 Host 核心。
- 不绕过 durable wait state。
- 不追求 Claude Code background subagent UI parity；本条只跟踪 Host wait completion callback 语义。

验收信号：

- callback 重放、乱序、摘要不匹配、未知 wait id 都有测试。
- endpoint 层只映射输入，状态裁决仍由 Host wait 语义完成。
- 认证失败、cancelled / lost wait 的迟到 callback、同 key 不同 outcome digest 的 idempotency conflict 都有明确 diagnostic。

### WU-WAIT-02 Production poller loop / backoff / fencing / retry

Owner / destination：GitHub Issue #90 / wait adapter polling-scale work unit。

状态：已确认是较大的 production feature，并已用 GitHub Issue #90 跟踪。Issue 中记录了初步设计建议，但本条实施前仍需回到 design gate 讨论并更新 `docs/host/design.md`；当前总控文档只冻结问题定位与实施方向。

代码核对：

- `WaitPoller.poll_once` 已覆盖单次 poll 和 error isolation。
- 缺口是后台 loop、backoff、in-flight fencing、adapter retry 与 `LIMIT` / `CANCELLED` abandon backoff。

目标：

- 实现或接入 production poller loop。
- 为 adapter error、rate limit、cancelled abandon 和 repeated not-ready 设计 backoff。
- 防止同一 wait 被并发 poller 重复处理。
- 明确 poller loop 只负责推进 Host wait 状态，不直接向 UI 返回事件；UI / Service 仍通过 `watch_session_events` 观察 `resolve_wait` 产生的 Host events。
- 设计短生命周期 in-flight claim / fencing，防止多 poller 同时 poll / resolve 同一 wait；该 claim 不是 Attempt owner、不是 EventLog truth、不是外部 job owner。

非目标：

- 不把 poller 做成通用 scheduler God object。
- 不让 backoff 状态污染 wait durable contract。
- 不在本条内实现 callback auth / replay；该项由 WU-WAIT-01 / GitHub Issue #89 跟踪。
- 不在未完成 design gate 前修改 `docs/host/design.md` 的 poller production 细节。

验收信号：

- 同一 wait 在多 poller 下不会并发 resolve。
- adapter intermittent failure 不会丢 wait，也不会 tight loop。
- production loop 能后台运行并可被 Host close / supervisor clean stop。
- ready / lost outcome 仍必须通过 common `resolve_wait` pipeline，事件由现有 Host watch path 观察。

### WU-WAIT-03 External job physical cancel / revoke / abandon

Owner / destination：GitHub Issue #92 / wait adapter external job lifecycle target work unit。

状态：已纳入 GitHub Issue #92；GitHub Issue #87 是共享 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 WAITING external job cancel / revoke / abandon target，不单独引入第二套 watchdog runtime。

代码核对：

- 当前已有 abandon wait 的最小 adapter path。
- 外部 job 的 physical cancel / revoke / abandon contract 未形成生产级语义。

目标：

- 为外部 job 定义 best-effort cancel / revoke / abandon 协议。
- 明确外部取消失败、超时、重复取消和晚到结果的处理方式。
- 复用 #87 的 Host lifecycle watchdog / supervisor，外部 job 作为 WAITING-state watch target；target-specific adapter 只负责 provider cancel / revoke / abandon 能力。

非目标：

- 不要求所有 provider 都支持 physical cancel。
- 不把外部 job id 当作 Host durable 主键。
- 不另建独立 wait-job watchdog；不得与 #91 的 active Attempt watchdog target 形成两套 runtime。

验收信号：

- 支持取消和不支持取消的 adapter 都有契约测试。
- late result 与已 abandon / cancelled wait 的 diagnostic 一致。

### WU-WAIT-04 UI / Service production-grade awaiting E2E smoke

Owner / destination：Service / Host public production smoke work unit。

状态：依赖 WU-WAIT-01 / GitHub Issue #89、WU-WAIT-02 / GitHub Issue #90、WU-WAIT-03 / GitHub Issue #92；不是可独立实施的 work unit，不进入独立 implementation-control。前置能力完成后，本条才作为 production-grade end-to-end smoke 进入 implementation gate。

前置条件：

- 本条必须在 WU-WAIT-01 / GitHub Issue #89、WU-WAIT-02 / GitHub Issue #90、WU-WAIT-03 / GitHub Issue #92 的 callback、production poller、external job lifecycle 生产能力完成后实施。
- 若前置能力尚未完成，只允许保留为讨论 / 设计项，不应降级实现为 manual resolve 桥接 smoke。
- 前置未满足时，不进入 implementation gate，不接受通过测试私有 durable wait id 或直接 `resolve_wait(wait_id, ...)` 构造的替代 smoke。

代码核对：

- 普通 Service 已通过 `open_host(options)` 获取异步 Host handle，并通过 `ensure_session`、`submit_followup(queue)`、`watch_session_events`、`get_run`、`cancel_run` 和 `resolve_wait` 使用 Host public API。
- Host public read model 已暴露 `RunSnapshot.status=WAITING`；当前 public `HostEvent` 对非终态事件只提供 `progress` 形状，因此 UI 等待态展示应由 watch 触发后再 `get_run(run_id)` 读取状态。
- 现有测试已覆盖 awaiting accept、`resolve_wait`、public scheduler awaiting integration、WAITING cancel 与 late result；但缺少一条明确模拟正常 UI / Service 消费方式的 production-grade E2E smoke：提交 prompt 后拿 `accepted_run_id`，观察 `WAITING`，由生产 poller 或 callback 入口完成 wait resolution，最后从同一个 watcher / outbox 收到 terminal event。

目标：

- 增加一条 production-grade public E2E smoke，冻结 UI / Service 正常接入 Host wait governance 的生产工作流。
- 流程应覆盖：`open_host` 装配、`ensure_session`、提交 `submit_followup(queue)`、记录 `accepted_run_id`、watch / `get_run` 观察 `WAITING`、生产 poller 或 callback 入口发现外部 job 完成并进入 Host wait resolution、同一 Run 最终产生 terminal `HostEvent` / outbox item。
- 验证 UI / Service 不直接依赖 ToolRuntime、EngineEvent、dispatch row、scheduler internals 或 wait record durable row 作为展示契约。
- 验证 `WAITING` 期间 UI / Service 可以继续保持 watch、刷新 Run snapshot、展示等待态，并在恢复后收到同一 Run 的最终结果。
- 验证 wait resolution 由 WU-WAIT-01 / 02 / 03 落地后的生产入口触发；smoke 不应为了构造 `resolve_wait(wait_id, ...)` 直接读取 durable wait id。

非目标：

- 不在本条重新实现 callback endpoint、production poller loop、backoff、fencing 或外部 job physical cancel；这些必须先由 WU-WAIT-01 / 02 / 03 提供。
- 不新增 UI 专用 Host 分支。
- 不把 wait record 列表查询提升为普通 UI 必需契约；普通 UI 只需要 `RunStatus.WAITING` 和 terminal event。
- 不接受仅用 manual resolve 或测试私有 durable wait id 桥接完成的 smoke 作为 production-grade 验收。

验收信号：

- smoke 测试能证明同一个 public watcher 在 Run 进入 `WAITING` 后继续接收由生产 poller / callback 恢复后的 terminal event。
- smoke 测试断言 `get_run(run_id).status == WAITING` 时 UI 可展示等待态，生产 wait resolution 后 Run 继续推进并最终成功。
- offline / reconnect 场景至少通过 outbox 证明 terminal item 可补读，避免 UI 断线时丢失最终结果。
- 测试代码不从 UI / Service 路径导入 Host 内部 ToolRuntime、dispatch、scheduler 或 durable wait mutation API。

### WU-ENGINE-01 Provider state neutralization and runner abstraction

Owner / destination：Engine runner / provider abstraction work unit。

状态：discussion 裁决为降级处理。现有 typed provider class / sealed union（例如 `GeminiToolCallState`）已经是避免 raw JSON provider payload 泄漏的正确方向；不需要围绕 provider state 做大改。

代码核对：

- Engine 已有 stream / non-stream、finish reason、idle timeout、context overflow、partial tool call 等多类测试。
- provider-specific tool call state 已通过 typed provider class / sealed union 进入中立契约，不再视为主要缺口。
- 剩余可疑点主要是 runner error / diagnostic 中的 `raw_payload` 是否过宽，以及 stream / non-stream error object 是否一致。

目标：

- 不推倒现有 typed provider state；后续新增 provider state 继续通过 typed class / sealed union 扩展。
- 将本条收窄为 Engine runner diagnostic payload audit：核查 `RunnerProtocolErrorData` / `RunnerHTTPErrorData` / `ProviderProtocolErrorData` 中 raw payload 的边界、脱敏、安全性和大小约束。
- 补或核对 stream / non-stream error object consistency 测试。

非目标：

- 不把 Host 状态机逻辑下沉到 Engine。
- 不为单个 provider 保留兼容 facade。
- 不把 typed provider class 退回 raw JSON / metadata bag。
- 不重写已稳定的 provider extension config / reasoning / tool call state 投影。

验收信号：

- OpenAI / Gemini 等 provider state 继续通过统一 typed contract 暴露，且无 raw SDK object 泄漏。
- stream / non-stream error object consistency 有测试。
- diagnostic raw payload 若保留，必须有明确边界；若删除或摘要化，Host / Engine 测试同步收敛。

### WU-LAYER-01 Durable row primitive / type owner cleanup

Owner / destination：Host durable layering cleanup work unit。

状态：discussion 裁决为保留显式 SQL / 轻量 Data Mapper，不引入 ORM。Host durable 是状态机治理数据库，不是普通 CRUD；CAS、短事务、DDL CHECK、partial index、EventLog append 与状态迁移需要 SQL 语义可见、事务边界可控。

代码核对：

- import boundary 与 weak typing guard 已有测试。
- 剩余清理集中在 row primitive、public type owner、durable bootstrap 和 schema CHECK / terminal CAS null-check 一致性。
- 当前 `HostRow -> SessionRow / RunRow / AttemptRow / WaitRecordRow` 的方向合理；问题不在于“不用 ORM”，而在于 row codec、validation owner 与 schema invariant 还需要收敛。

目标：

- 保留显式 SQL、显式 transaction 和 typed durable row dataclass。
- 收敛 durable row primitive 与 public type owner。
- 清理 durable bootstrap、schema CHECK、terminal CAS null-check 的重复规则。
- 让 row decode / encode / validation 有统一 owner，避免 Python dataclass 校验、SQLite CHECK 与 CAS null-check 三套规则漂移。

非目标：

- 不引入 ORM，不让 ORM 自动生成 schema、隐式迁移或隐藏 CAS 条件。
- 不改变 public contract。
- 不创建仅透传的兼容 re-export。
- 不把 durable row dataclass 扩展成承载业务行为的 domain object。

验收信号：

- durable 层不向上依赖 Host 业务实现细节。
- row decode / encode 失败有稳定错误类型和测试。
- current-version DB 缺表、缺索引或 schema invariant 缺失时，普通 open path 结构化失败；不得因 `CREATE IF NOT EXISTS` 静默补齐后继续运行。
- terminal Run / Attempt / WaitRecord 的 schema CHECK、Python validation 与 CAS null-check 语义一致。

### WU-LAYER-02 Shared validation / redaction / JSON helper consolidation

Owner / destination：runtime / Host helper cleanup work unit。

状态：discussion 裁决为有边界的小清理，不做大扫除式重构。只有层中立、无业务语义、跨层确实重复的 helper 才考虑下沉到 `dayu.runtime`；Host durable 专用 canonical format、状态机规则和业务字段校验不得为了复用强行搬迁。

代码核对：

- runtime 已承担层中立基础能力，Host / Engine import boundary guard 已存在。
- validation、JSON、redaction、token estimate helper 仍可能存在跨模块重复实现，需要按实际代码再做收敛。
- 现有 `dayu.runtime._digest` 已提供层中立 `canonical_json_digest`；`dayu.host.durable.codec` 仍是 Host durable facts 的 canonical JSON / digest / UTC timestamp 真源，不能被机械替换。
- `dayu.service.host_assembly`、`dayu.runtime.scene_prepare`、`dayu.runtime.tools_discovery`、`dayu.host.evidence`、`dayu.host.outbox`、`dayu.host.tool_runtime` 等存在相似文本 / digest 校验 helper，需要逐项判断是否真重复。
- `dayu.engine.agent`、`dayu.host.compaction_operation`、`dayu.host.llm_compaction` 存在异常消息 redaction / truncation 规则重复，适合优先审计是否能形成层中立安全 helper。

目标：

- 核对并合并层中立 helper 到合适 runtime 模块，优先处理跨层 redaction / bounded diagnostic helper。
- 删除 Host / Engine / Service 内语义重复但实现分叉的 helper。
- 保持 digest、canonical JSON、timestamp 的 truth owner 清晰：runtime digest 与 Host durable codec 各自边界明确，不互相偷换。

非目标：

- 不把业务层专用规则搬到 runtime。
- 不为了复用制造过宽抽象。
- 不机械迁移 Host durable canonical JSON / digest / timestamp helper。
- 不改变既有 digest 文本、JSON canonicalization、audit / tool trace / EventLog 语义。

验收信号：

- 合并后的 helper 有直接测试。
- runtime 不 import Host / Engine / Service / UI / Fins。
- 被保留在业务层的 helper 必须有明确 owner 理由，不把“看起来重复”当作重构理由。

### WU-CM-05 LLM compaction proposal typed parsing

Owner / destination：GitHub Issue #93，作为 GitHub Issue #81 的后续子任务；Conversation Memory / Context Governance cleanup work unit。

状态：deferred behind #81。#81 会调整 Conversation Memory 与 compact JSON 的目标 shape；本条不应抢先实施，避免先按旧 JSON 做 typed parsing 后又随 #81 返工。#81 确定 post-optimization compact proposal contract 后，再实施本条。

代码核对：

- LLM compaction proposal parsing 仍存在 typed parsing 收敛空间。
- 当前 `LLMContextCompactor` 已经会解析 strict JSON 并构造 Host-owned `CompactionCandidate`，但 raw proposal boundary 仍是 `Mapping[str, JsonValue]`，存在顶层 `cast` 与分散字段 validator。
- 该项本质是解析边界问题，但 compact JSON shape 会受 #81 影响；因此实施顺序必须跟随 #81。

目标：

- 在 #81 确定新的 compact JSON shape 后，将 LLM proposal parsing 收敛为显式 typed validation。
- 消除 unchecked cast、宽 payload 和模糊错误分类。
- 固定转换边界：LLM raw final answer -> parse JSON -> typed LLM compaction proposal -> Host-owned `CompactionCandidate` 或 #81 后等价 typed contract。

非目标：

- 不在 #81 前抢先实现。
- 不改变 compact output 的业务含义。
- 不放宽非法 proposal 的接受条件。

验收信号：

- 每个 post-#81 proposal 字段都有直接验证路径。
- invalid proposal 的 diagnostic 能定位字段和原因。
- malformed JSON、缺必填字段、字段类型错误、未知 label / ref、数组超限、非法 enum / patch operation 都有测试。

### WU-CM-06 Terminal summary text policy convergence

Owner / destination：GitHub Issue #94，作为 GitHub Issue #81 的后续子任务；Conversation Memory / terminal summary policy work unit。

状态：deferred behind #81。terminal summary、assistant conclusion、episode summary、answer anchor 与 continuity 的语义边界会受 #81 Conversation Memory 整体优化影响；本条应等 #81 固定相关 memory semantic boundary 后再实施。

代码核对：

- terminal summary text policy 与 compaction / rendering 的边界仍需单独核对。
- 该项会影响用户可见 summary，但不应改变 evidence-backed fact 语义。
- 当前 `engine_ingest` 会为 final answer / failure 写 terminal summary payload，`terminal_summary_payload.py` 提供 summary 文本提取 helper，memory projection 也可能读取 terminal summary 补 assistant conclusion continuity；这些路径需要在 #81 后按新语义统一。

目标：

- 在 #81 后收敛 terminal summary 的来源、截断、渲染和 fallback policy。
- 避免 terminal summary 与 compact summary、assistant conclusion 语义重叠。
- 固定成功、失败、取消、lost、governance failure 与 compacted episode summary 的文本 policy 矩阵。

非目标：

- 不在 #81 前抢先实现。
- 不把 terminal summary 变成事实引用源。
- 不改变 Run terminal taxonomy。
- 不让 compact / episode summary 冒充 terminal summary 或 final answer。
- 不借本条引入新的 public result read API。

验收信号：

- terminal summary 在 success、failure、cancel、governance failure 下语义一致。
- 渲染测试覆盖空 summary、长 summary 和 compact 后 summary。
- memory projection 只在 policy 允许时把 terminal summary 用作 continuity，不得升级为 evidence-backed fact。

### WU-CM-07 Evidence validation and pinned state cleanup

Owner / destination：obsolete；Conversation Memory semantic model cleanup is tracked by GitHub Issue #81。

状态：过期失效，不再作为独立 work unit 推进。#81 的目标方向是把现有 `pinned_state` 这类混合抽象拆成更准确的 semantic memory / task state 分类；继续保留本条会误导实现去修补并延续 `pinned_state` 作为目标顶层结构。

代码核对：

- evidence validation invariant 仍然重要，但应作为 #81 后续语义模型的一部分处理，不再和 `pinned_state` cleanup 捆成独立实施单元。
- `pinned_state / confirmed_subjects` 的目标归属需要等待 #81 裁决；不预设 `pinned_state` 是未来结构。

目标：

- 无独立实施目标。
- 后续若 #81 仍需要 evidence validation 子任务，应按新的 semantic memory 分类重新建 issue / work unit，不复用本条。

非目标：

- 不再围绕 `pinned_state` 做局部 cleanup。
- 不在 #81 前为 confirmed subjects、current goal、open questions 等字段预设最终 owner。

验收信号：

- 无独立验收信号；由 #81 及其后续 scoped issues 重新定义。

### WU-CM-08 Compaction material readability and smoke maintenance

Owner / destination：GitHub Issue #95，作为 GitHub Issue #81 的子任务；Conversation Memory smoke / maintainability work unit。

状态：保留为 #81 子任务，定位为测试可维护性和 compaction material readability cleanup；不负责裁决 Conversation Memory 语义模型。

代码核对：

- public conversation memory smoke 与 public memory scenario smoke 属于维护性覆盖。
- compaction material readability / chunking 与 smoke 维护相关度高，可合并推进。
- 当前 material pack 已有四段 LLM-facing section、prompt-local label、evidence chunk provenance 与 public compact smoke；本条不从零建设能力，而是提升小测试、fixture 和失败定位质量。

目标：

- 改善 compaction material 的 chunking、可读性和测试 fixture 可维护性。
- 保持 public memory scenario smoke 覆盖关键用户路径。
- 让 smoke 失败能定位到输入构造、material pack / chunking / prompt-local labels、compactor request / proposal、memory projection 或 RunInput rendering 边界。

非目标：

- 不改变 memory snapshot schema。
- 不裁决或实现 #81 semantic memory categories。
- 不用 snapshot 大量金文件掩盖语义测试缺失。
- 不引入新的 compactor JSON 语义。

验收信号：

- compaction material 结构稳定、易读，且变更有小范围测试。
- smoke 失败能定位到输入构造、compaction、projection 或 rendering 边界。
- LLM-facing material 保持可读，不暴露 EventLog ledger wrapper、payload descriptor、digest 或 Host provenance internals。
