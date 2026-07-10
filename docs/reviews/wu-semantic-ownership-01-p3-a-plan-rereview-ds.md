# WU-SEMANTIC-OWNERSHIP-01 P3-A Plan Re-Review — AgentDS

## 复审范围

- **复审对象**: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`（经 AgentCodex plan fix 更新后）
- **复审角色**: AgentDS（adversarial plan re-review）
- **复审日期**: 2026-07-10
- **参考真源**:
  - `AGENTS.md`
  - `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`（当前版本）
  - `docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-mimo.md`（AgentMiMo 初审）
  - `docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-ds.md`（AgentDS 初审）
  - `docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-controller-adjudication.md`（总控裁决）
  - `docs/reviews/wu-semantic-ownership-01-p3-a-plan-fix-codex.md`（AgentCodex plan fix）
- **复审任务**: 确认 PF-01 到 PF-13 是否全部在 plan 中有明确、可实施、可验证的修复；是否仍存在 blocking finding；是否有新的 plan blocker 或过度设计/owner boundary drift。

## PF-by-PF 逐项验证

### PF-01 [blocking] S3 Host lifecycle closeout identity scheme

- **Controller 要求**: 具体 event_id 派生公式、命名空间隔离策略、duplicate detection 处理、无 EngineEventCandidate 时的路由信息定义。
- **Plan 修复位置**: section 5, S3 exact changes，line 320–348。
- **实际内容**: 定义了 `_HostLifecycleCloseoutCandidate` typed fields（`envelope`, `observed_at`, `worker_event_index`, `plan`, `lifecycle_source`, `execution_id`）；event_id 公式为 `event-host-lifecycle-{sha256(...)}` 包含 10 个明确组件；命名空间与 `event-engine-` 前缀 disjoint；duplicate detection 按最终 event ids 查重不互吞；Host lifecycle ref 使用 `host-lifecycle:{execution_id}:...` 而非伪造 Engine event ref；late rejection routing 基于 `lifecycle_source` / `plan.reason`。
- **验证**: ✅ 满足全部要求。公式具体、命名空间 disjoint 说明清楚、duplicate 处理策略明确、路由信息定义完整。

### PF-02 [blocking] S3 CANCELLING 交互决策表

- **Controller 要求**: Engine FINAL_ANSWER/RUN_FAILED + CANCELLING、Host lifecycle clean EOF/lost + CANCELLING、other Engine events + CANCELLING 的决策表，含 decision 和 owner。
- **Plan 修复位置**: section 5, S3 exact changes，line 350–360。
- **实际内容**: 5 行决策表覆盖全部要求场景，每行含 Run 状态、Incoming fact、Decision、Owner/recorded fact。补充 stop condition：若实现发现 cancel/watchdog 要求 first-committer-wins 写 RUN_LOST，停止并要求 design truth 裁决。
- **验证**: ✅ 满足全部要求。决策表完整、语义明确、有安全停止条件。

### PF-03 [blocking] S3 candidate shape god-bag 消除

- **Controller 要求**: 两条独立 typed path 或 tagged union + discriminator，禁止 optional-field probing。
- **Plan 修复位置**: section 5, S3 exact changes，line 320–323。
- **实际内容**: 明确两条 typed path——Engine-origin 用 `EngineEventCandidate`，worker EOF/crash 用 `_HostLifecycleCloseoutCandidate`；若需共享 internal closeout core，只能用 `TerminalCloseoutOrigin` discriminator + typed payload；禁止一个 dataclass 同时塞入互斥 optional Engine/Host 字段。
- **验证**: ✅ 满足全部要求。god-bag 风险已消除。

### PF-04 [blocking] S2 terminal event source scan 强制化与精确化

- **Controller 要求**: source scan 升级为强制、精确 terminal pattern、定义允许位置、非 terminal 常量记录为 residual input。
- **Plan 修复位置**: section 5, S2 Tests，line 273–280。
- **实际内容**: source scan 标记为"强制 validation，不是可选测试"；regex 精确匹配 `_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)`；预期 `run_transition.py` 与 `engine_ingest.py` 不得残留此类常量；测试文件只能显式引用 enum member；禁止 diagnostic whitelist 泛化。非 terminal 常量完整枚举为 residual input（19 个常量，含文件和常量名），记录给 P3-J。
- **验证**: ✅ 满足全部要求。source scan 强制、精确、有明确 residual 记录。

### PF-05 [blocking] Import-cycle 预防具体化

- **Controller 要求**: import graph 依赖说明、验证命令、stop condition。
- **Plan 修复位置**: section 3 Import graph baseline，line 135–159；S1/S2 validation 命令。
- **实际内容**: 5 模块 import graph 逐一定向说明（`api.py` 不导入 `durable`、`lifecycle_events` 只依赖 `api` 不依赖 `durable.state`/`run_transition`/`engine_ingest`、`durable.state` 不导入 `lifecycle_events`、`run_transition` 与 `engine_ingest` 可导入两者）；已验证当前不构成循环；S1/S2 后强制运行 `python -c "from dayu.host.lifecycle_events import ...; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"`；stop condition 写明若引入 cycle 必须停止。
- **验证**: ✅ 满足全部要求。依赖图清晰、验证命令可执行、有 stop condition。

### PF-06 [high] SM-7 pre-implementation 验证步骤

- **Controller 要求**: 搜索 FollowupSnapshot 构造点中 `accepted_run_status=RECOVERING` 的调用，定义 found/not-found 处理。
- **Plan 修复位置**: section 2, SM-7 裁决，line 87–93。
- **实际内容**: 要求在进入 S1 前搜索 `FollowupSnapshot|accepted_run_status|RunStatus\.RECOVERING`（范围 `dayu/host dayu/service dayu/cli`）；found → 升级为 P3-A scope 或记录 deferred owner；not-found → 记录搜索命令、结果摘要和 closure basis。
- **验证**: ✅ 满足全部要求。搜索命令、范围、处理逻辑完整。

### PF-07 [medium] SQL status helper query plan / index 验证

- **Controller 要求**: S1/S2 增加 `EXPLAIN QUERY PLAN` 或等价验证。
- **Plan 修复位置**: section 5, S1 Tests line 225；S2 SQL/query-plan validation line 298。
- **实际内容**: S1 增加 SQL helper owner test（空集合 fail-fast、placeholder 数量一致、params 来自 serialized values）；S2 要求 targeted durable state test 通过 `EXPLAIN QUERY PLAN` 或等价行为断言验证 helper-generated `IN` 不破坏查询语义；若 planner 不稳定则至少断言结果等价并记录 planner 输出；禁止为 planner 顾虑保留手写 status list。
- **验证**: ✅ 满足全部要求。两层验证（单元 + 集成）互补。

### PF-08 [medium] `_TERMINAL_STATUS_PAIRS` owner 决策

- **Controller 要求**: 明确是 derived transition invariant 还是 separate durable row-rule truth。
- **Plan 修复位置**: section 5, S2 exact changes，line 261。
- **实际内容**: 明确定义为 derived transition invariant，从 `state.TERMINAL_RUN_STATUSES`、`state.TERMINAL_ATTEMPT_STATUSES` 和 lifecycle terminal event helper supported closeout 子集派生；只允许 4 对同名 terminal pair；必须命名/注释为 derived invariant，不是 event type mapping truth 或 durable row-rule truth。增加 derived invariant 测试：断言由 owner 集合派生，非法 pair fail-fast，新增 terminal status 触发测试失败。
- **验证**: ✅ 满足全部要求。去留决策明确、派生逻辑清晰。

### PF-09 [medium] `START_BLOCKING_RUN_STATUSES` 派生假设显式化

- **Controller 要求**: 说明假设、增加测试使新增非终态触发显式审查。
- **Plan 修复位置**: section 5, S1 exact changes line 212；S1 Tests line 224。
- **实际内容**: docstring 说明"所有 non-terminal except QUEUED 阻塞启动新 Run"的假设，用途限于 accepted/start-blocking admission；若未来新增不应 blocking 的非终态，必须改为显式枚举。测试断言精确成员集合，新增 RunStatus 非终态时必须失败。
- **验证**: ✅ 满足全部要求。假设显式、测试门控到位。

### PF-10 [medium] Propagation audit 可执行验证标准

- **Controller 要求**: 每条 audit path 补充具体验证方法。
- **Plan 修复位置**: section 6 Propagation audit plan，line 387–398。
- **实际内容**: 6 条 audit 路径各附 Verification 段——Run terminal event type: source scan + transition tests + read/projection tests；Attempt terminal event type: owner tests + engine ingest mapping tests + source scan；Run status predicate: state schema tests + source scan/review + SQL validation；Worker lifecycle closeout: event id format tests + payload check + projection/read tests；Late event rejection: status predicate tests + row validation tests + decision-table tests；Direct cancelability: state helper/command tests + source review。
- **验证**: ✅ 满足全部要求。每条路径有具体、可执行的验证方法。

### PF-11 [medium] P3-B interface boundary 保留

- **Controller 要求**: S3 closeout extraction 保持现有 `_close_terminal` 参数和行为，不预设计 P3-B 字段。
- **Plan 修复位置**: section 4 Non-goals，line 176。
- **实际内容**: 明确 S3 closeout core 抽取只能保持现有 `_close_terminal` 已有 final-answer / terminal descriptor 参数和行为；P3-B 后续可消费同一 closeout path，但 P3-A 不新增 final-answer-specific 字段，除非已由当前 `_close_terminal` 调用签名要求。
- **验证**: ✅ 满足全部要求。边界清晰、不泄漏 P3-B scope。

### PF-12 [low] README 实际检查要求

- **Controller 要求**: 将"预计不更新"替换为实际检查要求。
- **Plan 修复位置**: section 5, S1 line 236、S2 line 300、S3 line 383。
- **实际内容**: S1: "implementation 必须先阅读并检查 `dayu/host/README.md` 和 `tests/README.md` 的 Agent 更新约束...再记录'更新'或'不更新'的实际依据。不能用'预计不更新'替代检查"。S2: "implementation 必须实际检查 `dayu/host/README.md` 和 `tests/README.md`；只有确认 README 未描述或无需同步 lifecycle/status owner、测试运行类别时，才能记录不更新"。S3: "S3 implementation 必须实际检查...不能用预计结论替代检查"。
- **验证**: ✅ 满足全部要求。三个 slice 均要求实际检查而非预测。

### PF-13 [low] Event type value helper 策略具体化

- **Controller 要求**: 选择简单分离 helper，不做 TypeVar/overload 泛化。
- **Plan 修复位置**: section 5, S1 exact changes，line 210。
- **实际内容**: "event type value projection 采用简单分离 helper，不做 TypeVar / overload 泛化：保留 Run event value helper 只接收 `tuple[HostRunEventType, ...]`，新增 `attempt_event_type_values(events: tuple[HostAttemptEventType, ...]) -> tuple[str, ...]`。禁止用 `Any` 或宽泛 enum bag 规避类型。"
- **验证**: ✅ 满足全部要求。策略明确、类型安全、无歧义。

## 关键风险点复核

### S3 closeout identity — 无新风险

event_id 公式设计完整（10 组件 sha256），命名空间 disjoint（`event-host-lifecycle-` vs `event-engine-`），duplicate detection 按最终 event ids 查重。唯一 residual risk 是 sha256 依赖 `plan.reason` 字符串稳定性——若 `plan.reason` 在 worker lifecycle 不同阶段变化，同一 closeout 可能产生不同 event_id。但这属于 implementation 阶段需验证的细节，非 plan 层面 blocker。

### Active cancel race — 无新风险

决策表覆盖全部 5 个场景，且补充了 stop condition（若 cancel/watchdog 要求 worker crash first-committer-wins 写 RUN_LOST 则停止）。当前决策表语义正确：worker lifecycle 在 CANCELLING 期间只写 diagnostic，不写 terminal Run fact，cancel transition 保持 terminal owner。

### God-bag — 已消除

两条 typed path 明确分离：`EngineEventCandidate` 与 `_HostLifecycleCloseoutCandidate`，禁止 optional-field probing。可选 tagged union 方案也被约束为 discriminator + typed payload。

### Import cycle — 已验证无风险

当前 import graph 验证完成，`lifecycle_events → api`、`state → api`、`run_transition → lifecycle_events + state` 不构成循环。验证命令写入 S1/S2 validation。

### 过度设计 — 无

Plan 的 non-goals 和 stop conditions 明确拒绝 broad schema migration、Engine flat mapping、wait lifecycle 变更、dispatch state machine 重构。所有 slices 仍是 current code 直接证据支撑的 owner-boundary cleanup。

### Owner boundary drift — 无

6 个语义事实的 owner boundary 表（section 3）与修复边界一致，所有修复落在 owner 或其直接上游校验处。Propagation audit plan 已具体化验证方法。

## 总结

PF-01 到 PF-13 共 13 个 controller-accepted findings 全部在更新后的 plan 中有明确、可实施、可验证的修复。无残留 blocking finding。无新增 plan blocker、过度设计或 owner boundary drift。

Plan 已具备进入 implementation gate 的条件。

## Completion Report

- **status**: completed
- **artifact**: `docs/reviews/wu-semantic-ownership-01-p3-a-plan-rereview-ds.md`
- **verdict**: pass
- **blocking findings count**: 0
- **nonblocking findings count**: 0
- **blockers**: none
