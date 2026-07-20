# WU-SEMANTIC-OWNERSHIP-01 P3-A Plan Review — AgentDS

## 审查范围

- **审查对象**: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`
- **审查角色**: AgentDS（adversarial plan review）
- **审查日期**: 2026-07-10
- **参考真源**:
  - `AGENTS.md`
  - `docs/host/design.md`（已核对相关 lifecycle/worker 章节）
  - `docs/engine/design.md`
  - `docs/host/issues-implementation-control.md`
  - `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
  - Source review artifacts: `docs/reviews/repo-review-20260710-092911.md`, `docs/reviews/repo-review-20260710-091608.md`, `docs/reviews/2026-07-10-semantic-ownership-drift-review.md`
- **代码核对**: 已核对 `lifecycle_events.py`, `run_transition.py:88-112,5536-5571`, `engine_ingest.py:225-244,2453-2498,3320-3337`, `command.py:1721-1740`, `_row_rules.py:1-40`, `state.py:65-84,1590-1611`, `admission.py:4557-4569`

## 总体裁决

**Verdict: pass-with-findings**

P3-A plan 从第一性原理确认了动机成立：Host durable state 是 Run/Attempt status 与 lifecycle event type 的真源，但当前代码在 4–7 处独立定义同一语义事实。plan 的 owner boundary 分析正确，non-goals 和 stop conditions 清晰，3 个 slices 的切分在语义上闭环且符合小型跨模块 cleanup 的 slice budget（≤3）。

但存在 2 个 blocking finding：S3 synthetic EngineEvent 移除的 closeout identity scheme 设计不够具体，以及 S2 的 source scan 验证被标记为"可接受"而非强制。这 2 个问题必须在 plan 进入 implementation gate 前修复。

## Finding 裁决复核

### SM-5 (rejected-with-reason)：裁决正确

`state.py:2070-2074` 明确说明 cancelled wait row 返回给 poller 以执行 best-effort abandon，`state.py:2188-2190` 的 CAS guard `poll_abandoned_at IS NULL` 保证同一 cancelled record 不会被重复 claim。这与 Host design 中"adapter 观察到 wait record cancelled 后可以 best-effort cancel/revoke/abandon 外部 job"的边界一致。`CANCELLED` wait 不进入 `resolve_wait`，也不是 Run terminal truth。归属 wait poller / external job lifecycle WU，不进入 P3-A。

### SM-7 (needs-more-evidence)：裁决合理但缺少验证步骤

当前直接证据只显示 `FollowupSnapshot.__post_init__` 在 `api.py:2399-2402` 拒绝 `accepted_run_status=RECOVERING`。plan 正确指出没有证据证明生产 submit path 能产生 recovering accepted followup。但 plan 应在 S1 前要求 implementation agent 做一次快速验证：搜索生产代码中构造 `FollowupSnapshot(accepted_run_status=RunStatus.RECOVERING, ...)` 的调用点。若不存在，确认 deferred；若存在，升级为 P3-A scope。

→ **见 Finding H-1**。

### SM-8 (rejected-with-reason)：裁决正确

`_session_timeline_cursor` 返回 `closed_event_sequence` 或 `created_event_sequence`，这是 EventLog sequencing 事实，不是 Session status 判定。Session row shape validation 已要求 open session 的 closed refs 为空。改成由 `status` 派生会丢失具体 EventLog cursor 精度。不属于 P3-A scope。

### 其余 accepted findings：裁决一致

AgentCodex 12、AgentDS 1/9/10/11/17、AgentMiMo SM-1/2/3/4 的 accepted 裁决均与代码直接证据一致。SM-2 的 solution correction（拒绝 flat Engine→Host map，改为 Host lifecycle event source-of-truth + terminal closeout predicates）正确反映了 Engine terminal event 与 Host lifecycle transition 不是一对一映射。SM-3 的 schema non-goal（不做 broad dispatch status redesign）与 P3-A scope 一致。

## Findings

### B-1 [BLOCKING] S3 synthetic EngineEvent 移除的 closeout identity scheme 设计不够具体

- **evidence**: plan S3 提出 `_HostLifecycleCloseoutCandidate`、`_host_lifecycle_event_id`、`_host_lifecycle_engine_event_ref`，以及"抽取一个内部 `_TerminalCloseoutCandidate` protocol-like dataclass"。但 identity scheme 只给了字段名素描（`envelope, observed_at, worker_event_index, event identity seed, optional Engine event ref`），没有给出具体的 event_id 派生公式。
- **直接代码证据**: 当前 `_close_worker_lifecycle`（`engine_ingest.py:2453-2471`）构造完整的 `EngineEvent(type=RUN_FAILED, data=RunFailedData(...))` 作为 `EngineEventCandidate.engine_event`，然后走 `_duplicate_terminal_result` → `_late_rejection_reason` → `_close_terminal` 管线。`_duplicate_terminal_result` 依赖 `EngineEventCandidate` 的 event_id 做去重。如果新的 Host lifecycle path 生成不同格式的 event_id，可能与 Engine-origin event_id 碰撞；如果 event_id 缺少 `engine_event_ref`，后续 audit/trace 可能丢失 Engine 关联。
- **why it matters**: `_close_worker_lifecycle` 是 worker EOF/crash 的关键 closeout 路径。event_id 碰撞会导致 legitimate terminal closeout 被误判为 duplicate 而拒绝；event_id 格式不一致会导致 audit/trace 无法关联。当前 plan 的"字段名素描"不足以让 implementation agent 做出正确实现。
- **required fix**: plan S3 必须补充具体的 `_host_lifecycle_event_id` 派生公式，至少包含：
  - event_id 的组成部分及其顺序（例如 `f"event-host-lifecycle-{execution_id}-{worker_event_index}-{event_class}-{event_type}-{sub_index}"`）
  - 与现有 `_EVENT_ID_PREFIX = "event-engine-"`（`engine_ingest.py:222`）的命名空间隔离策略
  - `_duplicate_terminal_result` 如何区分 Engine candidate 和 Host lifecycle candidate 的 event_id
  - 如果 `_close_terminal` 当前强依赖 `EngineEventCandidate.engine_event.type` 做路由（例如 `_late_rejection_reason` 中 `context.candidate.engine_event.type in (EngineEventType.FINAL_ANSWER, EngineEventType.RUN_FAILED)`），新的 Host lifecycle candidate 如何表达等效路由信息

### B-2 [BLOCKING] S2 source scan 验证标记为"可接受"而非强制

- **evidence**: plan S2 写道 "Source scan test 可接受：对生产代码运行 `rg ...`，只允许 `lifecycle_events.py` 或测试/diagnostic whitelist"。但紧接着又说"若当前非 terminal usage必须保留，测试 whitelist 应精确到文件和常量，不能泛化"——这暗示可能存在需要 whitelist 的合法非 terminal usage，但 plan 没有枚举或确认这些 usage。
- **why it matters**: 如果 S2 完成后的 source scan 发现残留的 `_EVENT_TYPE_RUN_SUCCEEDED` 等裸字符串在非 owner 模块中，但被 whitelist 泛化放过，等于没有真正消除 duplicate source-of-truth。这是 P3-A 的核心成功信号之一。
- **required fix**: 将 source scan 从"可接受"升级为强制验证步骤。plan 必须：
  - 明确 whitelist 的精确范围：只允许 `lifecycle_events.py` 中的 `HostRunEventType` / `HostAttemptEventType` enum member 定义，以及测试文件中显式引用 enum member 的断言
  - 禁止 whitelist 中出现"非 terminal usage 必须保留"的泛化条目——如果 engine_ingest.py 中的 `_EVENT_TYPE_RUN_RECOVERING` 等非 terminal 常量需要保留，必须在 plan 中显式列出哪些常量、在哪个文件、为什么不能迁移
  - 将 rg 命令的具体 pattern 和预期结果写入 S2 validation 命令

### H-1 [HIGH] SM-7 缺少 pre-implementation 验证步骤

- **evidence**: plan 对 SM-7 的裁决是 "needs-more-evidence"，理由是"没有证明当前生产 submit path 能产生 recovering accepted followup"。但 plan 没有要求 implementation agent 在进入 S1 前做验证。
- **why it matters**: 如果生产代码中确实存在构造 `FollowupSnapshot(accepted_run_status=RunStatus.RECOVERING, ...)` 的路径，而 P3-A 将其 deferred，则 `RECOVERING` followup 的 admission contract 漏洞会继续存在。反过来，如果验证后确认不存在该路径，可以安全 deferred 并记录关闭依据。
- **required fix**: 在 plan 的 pre-implementation checklist 或 S1 的前置条件中增加一条：搜索生产代码中构造 `FollowupSnapshot` 且 `accepted_run_status` 包含 `RECOVERING` 的调用点。若找到，将 SM-7 升级为 P3-A scope 或新增 deferred-with-owner 记录；若未找到，记录关闭依据。

### H-2 [HIGH] `_late_rejection_reason` 的 CANCELLING 特判与 worker lifecycle closeout 交互未定义

- **evidence**: `engine_ingest.py:3331-3336` 对 `CANCELLING + (FINAL_ANSWER | RUN_FAILED)` 有特殊处理：返回 `_REASON_LATE_TERMINAL_AFTER_ACTIVE_CANCEL`。plan S3 说"Host lifecycle closeout 不能再因为 synthetic RUN_FAILED 进入该特判；如 lifecycle closeout 在 CANCELLING 中有特殊规则，必须显式用 Host lifecycle reason 判断"。但 plan 没有定义 worker EOF/crash 发生在 active cancel 期间时，`_late_rejection_reason` 应该返回什么——是 `_REASON_LATE_TERMINAL_AFTER_ACTIVE_CANCEL`（与 Engine-origin RUN_FAILED 相同），还是走 Host lifecycle 专用路径，还是直接允许 closeout？
- **why it matters**: 当前 synthetic `RUN_FAILED` 在 active cancel 期间会触发 `_REASON_LATE_TERMINAL_AFTER_ACTIVE_CANCEL`，这阻止了 worker crash 在 cancel 期间写入 terminal facts。如果移除 synthetic event 后，Host lifecycle closeout 在 CANCELLING 期间的行为没有明确定义，implementation agent 可能错误地允许或拒绝 closeout，导致 Run 卡在 CANCELLING 或丢失 worker crash 事实。
- **required fix**: plan S3 必须补充 worker EOF/crash + active cancel 并发场景的决策表：
  - Engine origin `FINAL_ANSWER` / `RUN_FAILED` 到达时 CANCELLING → 当前行为（`LATE_TERMINAL_AFTER_ACTIVE_CANCEL`）
  - Host lifecycle worker clean EOF 到达时 CANCELLING → ？
  - Host lifecycle worker lost 到达时 CANCELLING → ？
  - 上述之外的 Engine event 到达时 CANCELLING → ？

### H-3 [HIGH] `_TerminalCloseoutCandidate` 设计有 god-bag 风险

- **evidence**: plan S3 提出"抽取一个内部 `_TerminalCloseoutCandidate` protocol-like dataclass，包含 closeout 所需字段：envelope、observed_at、worker_event_index、event identity seed、optional Engine event ref"。这个 dataclass 同时承载 Engine-origin 和 Host-lifecycle-origin 两种不同语义的 closeout，其中 `optional Engine event ref` 对 Host lifecycle path 为 None，`worker_event_index` 对 Engine-origin path 可能无意义。
- **why it matters**: 一个 dataclass 承载两种互斥语义（Engine origin vs Host lifecycle origin），本质上是用 optional 字段做 tagged union。这与 AGENTS.md 的"禁止 God object、God function、God dataclass、god bag"约束冲突。下游 `_close_terminal` / `_duplicate_terminal_result` 需要根据哪个字段非空来判断走哪条路径，这会导致隐式分支。
- **required fix**: 使用明确的 tagged union 或两条独立类型路径：
  - 方案 A：保留 `EngineEventCandidate` 用于 Engine-origin closeout；新增 `HostLifecycleCloseoutCandidate` 用于 worker lifecycle closeout，各自有明确的必填字段，不混合 optional 字段。
  - 方案 B：抽取一个 `_TerminalCloseoutCandidate` 但使用 `TerminalCloseoutOrigin` 枚举 discriminator + 两个 typed payload 子对象，禁止 optional 互斥字段。
  - plan 应选择一个方案并在 S3 中明确，避免留给 implementation agent 做类型设计裁决。

### M-1 [MEDIUM] 非 terminal event 常量不进入 P3-A 但未记录为已知 residual

- **evidence**: plan S2 说"保留非 terminal event 常量如 `ENGINE_EVENT_REJECTED`、`PROVIDER_PROTOCOL_ERROR`、`RUN_WAITING` 可在本 WU 不处理"。`engine_ingest.py:225-243` 中还有 `_EVENT_TYPE_ENGINE_EVENT_REJECTED`、`_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR`、`_EVENT_TYPE_RUN_WAITING`、`_EVENT_TYPE_ATTEMPT_SUSPENDED`、`_EVENT_TYPE_RUN_RECOVERING`、`_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED` 等非 terminal 裸字符串。
- **why it matters**: P3-A 完成后，terminal event type 从 owner helper 派生，非 terminal event type 仍是裸字符串。后续新增 event type 时，开发者需要知道哪些走 owner helper、哪些写裸字符串。这不是 P3-A 的 bug，但如果不记录为 known residual，后续 WU（如 P3-J Host durable schema hardening）可能遗漏。
- **required fix**: 在 plan 的 non-goals 或 completion report 中显式记录：P3-A 不处理的非 terminal event type 常量列表及所在文件，作为 P3-J 或后续 EventLog schema hardening 的输入。不要求在 P3-A 中实施。

### M-2 [MEDIUM] `_TERMINAL_STATUS_PAIRS` 的保留理由不充分

- **evidence**: plan S2 说"`_TERMINAL_STATUS_PAIRS` 可保留在 `run_transition.py`，因为 Attempt status 与 Run status compatibility 属于 transition closeout invariant，不是 event type source-of-truth"。但 `_TERMINAL_STATUS_PAIRS`（`run_transition.py:107-112`）的内容——`(SUCCEEDED, SUCCEEDED), (FAILED, FAILED), (CANCELLED, CANCELLED), (LOST, LOST)`——与 `lifecycle_events.py:57-62` 的 `_RUN_STATUS_BY_TERMINAL_EVENT_TYPE` 是同一事实的不同投影：都表达了 terminal event ↔ status 的对应关系。如果将来新增 `RUN_TIMED_OUT`，两处都需要更新。
- **why it matters**: plan 的核心目标是消除 duplicate source-of-truth。如果 `_TERMINAL_STATUS_PAIRS` 确实是独立 invariant（例如表达"Attempt 和 Run 的终态必须成对出现且值相同"这一 transition 约束），它应该是 `_row_rules.py` 或 `state.py` 中的显式 invariant check，而不是与 event-type mapping 内容重复的 tuple。
- **required fix**: 在 S2 中明确 `_TERMINAL_STATUS_PAIRS` 的去留决策：
  - 如果它是 transition invariant，从 `state.TERMINAL_RUN_STATUSES` 和 `state.TERMINAL_ATTEMPT_STATUSES`（仅限 closeout-supported 子集）派生，不手写 tuple
  - 如果它确实是独立业务规则（如"SUCCEEDED/FAILED/CANCELLED/LOST 是唯一合法的 terminal closeout pair"），在 `_row_rules.py` 中显式定义为 `TERMINAL_CLOSEOUT_STATUS_PAIRS` 并补充 invariant 说明

### M-3 [MEDIUM] S1 `START_BLOCKING_RUN_STATUSES` 的自动派生可能引入意外状态

- **evidence**: plan S1 定义 `START_BLOCKING_RUN_STATUSES = NON_TERMINAL_RUN_STATUSES - {RunStatus.QUEUED}`，其中 `NON_TERMINAL_RUN_STATUSES = RunStatus - TERMINAL_RUN_STATUSES`。如果将来新增非终态（如 `SCHEDULED`），它会自动进入 `START_BLOCKING_RUN_STATUSES`，这可能不符合"start-blocking"的语义。
- **why it matters**: `START_BLOCKING_RUN_STATUSES` 被 `read_active_run_for_session` 等 admission 查询使用。如果新增的非终态不应 blocking admission，自动派生会导致 admission 查询范围错误扩大。
- **required fix**: 在 S1 的 docstring 或测试中显式说明 `START_BLOCKING_RUN_STATUSES` 的派生假设：当前所有非终态（除 QUEUED）都是 start-blocking。如果将来新增不应 blocking 的非终态，必须改为显式枚举。同时增加一个测试断言 `START_BLOCKING_RUN_STATUSES` 的具体成员集合，使新增 RunStatus 时测试失败提醒开发者审查。

### M-4 [MEDIUM] Propagation audit 缺少可执行验证标准

- **evidence**: plan section 6 列出 6 条 propagation audit 项目（"Run terminal event type: RunStatus / HostRunEventType owner helper -> durable transition producer -> EventLog event_type -> ..."），但只是描述性 checklist，没有说明如何验证每条路径的语义一致性。
- **why it matters**: AGENTS.md 要求"修复完成前必须做一次 propagation audit：列出该语义从产生、持久化、审计、投影到用户/LLM 可见输出的路径，并确认每一处语义一致"。当前 audit plan 只列出了路径，没有定义"确认一致"的方法——是对比 event_id？grep 确认无裸字符串？跑集成测试？
- **required fix**: 对每条 audit 路径补充一个具体的验证方法，例如：
  - "Run terminal event type" 路径：grep 确认只有 `lifecycle_events.py` 中定义 terminal event type 字符串；EventLog 写入的 event_type 与 `run_terminal_event_type_for_status` 返回值一致（通过 transition 测试断言）
  - "Run status predicate" 路径：grep 确认 `SUCCEEDED, FAILED, CANCELLED, LOST` 只出现在 `_row_rules.py` 的 `TERMINAL_RUN_STATUS_VALUES` 中，所有消费者通过 `state.TERMINAL_RUN_STATUSES` 或 `state.is_terminal_run_status` 获取

### L-1 [LOW] README 更新决策缺少实际核对

- **evidence**: plan 对 S1/S2/S3 的 README decision 均为"预计不更新"或"预计无需更新"。但 plan S1 在 `lifecycle_events.py` 中新增了 `HostAttemptEventType` 和 `attempt_terminal_event_type_for_status`——这是 `lifecycle_events.py` 模块文档声明（"本模块是 Host Run lifecycle event type... 的代码真源"）未覆盖的新语义。如果 `dayu/host/README.md` 描述了 lifecycle event 的 owner boundary，可能需要更新。
- **why it matters**: 按 AGENTS.md README 触发规则，`dayu/host/` 修改需检查 `dayu/host/README.md`。plan 的"预计不更新"是合理预测但不应替代实际检查。
- **required fix**: 在 S1/S2/S3 的 README decision 中将"预计不更新"改为"implementation agent 必须检查 `dayu/host/README.md` 的 lifecycle event 描述是否与变更一致；如 README 未描述 lifecycle event owner boundary，记录为不需要更新"。

### L-2 [LOW] S1 `event_type_values` 泛化策略的 hedging 可简化

- **evidence**: plan S1 说"`event_type_values(...)` 可泛化为接受 Run / Attempt event enum tuple；若类型签名复杂导致 pyright 压力，可保留 Run helper并新增 `attempt_event_type_values(...)`，不要使用 `Any`"。当前 `event_type_values`（`lifecycle_events.py:139`）接受 `tuple[HostRunEventType, ...]`，泛化到 `HostAttemptEventType` 需要 `TypeVar` bound 或 overload。
- **why it matters**: 两个独立函数（`run_event_type_values` + `attempt_event_type_values`）比一个泛化函数更简单、类型更安全、不需要 TypeVar。plan 的 hedging 增加了 implementation agent 的决策负担，而收益不明显。
- **required fix**: 建议 plan 直接选择"Run helper + 新增 `attempt_event_type_values(...)`"方案，删除泛化 hedging。`attempt_event_type_values` 接受 `tuple[HostAttemptEventType, ...]`，实现与 `event_type_values` 相同（`.value` 投影）。

### L-3 [LOW] Import cycle 风险已验证不存在但 plan 未记录验证结果

- **evidence**: 代码核对确认 `dayu/host/api.py` 不导入 `dayu/host/durable/` 下任何模块。`lifecycle_events.py` 只导入 `dayu.host.api`（`RunStatus`, `HostTerminalStatus`）。`durable/state.py` 导入 `dayu.host.api`。因此 `state.py → lifecycle_events.py → api.py` 和 `run_transition.py → lifecycle_events.py → api.py` 均不构成循环。plan 的 stop condition（"若出现 cycle，必须停止并裁决"）作为防御性措施是合理的，但 plan 没有记录已做的验证。
- **why it matters**: 不记录验证结果会使后续 review 重复质疑同一风险。
- **required fix**: 在 plan 中补充一句："已验证 `dayu/host/api.py` 不导入 `dayu/host/durable/` 下任何模块，`lifecycle_events.py` 的 import chain 不构成循环。若后续 implementation 发现新增 import 引入 cycle，按 stop condition 处理。"

## Slice 评估

### S1 评估：可实现、可独立验证

- **优点**: 只新增 helpers 和 tests，不改变行为路径；回滚风险低；验证命令明确。
- **风险**: `START_BLOCKING_RUN_STATUSES` 的自动派生假设（见 M-3）。
- **结论**: 可通过，需修复 M-3。

### S2 评估：可实现、可独立验证

- **优点**: 消费者迁移按模块逐个替换，行为等价；`_TERMINAL_STATUS_PAIRS` 的保留避免了过度重构。
- **风险**: source scan 验证不够严格（见 B-2）；`_TERMINAL_STATUS_PAIRS` 的去留需要更明确的决策（见 M-2）；涉及 10+ 文件的迁移可能超出单个 implementation agent 的上下文容量——plan 应在 S2 中说明为什么不需要进一步拆分。
- **结论**: 可通过，需修复 B-2 和 M-2。

### S3 评估：风险最高、设计最不完整

- **优点**: 正确识别了 synthetic EngineEvent 和 nullable refs 两个核心问题。
- **风险**: closeout identity scheme 不具体（见 B-1）；CANCELLING 交互未定义（见 H-2）；`_TerminalCloseoutCandidate` 有 god-bag 风险（见 H-3）。这三个问题叠加在 `engine_ingest.py` 的关键 closeout 路径上，如果 implementation agent 在设计不完整的情况下自行裁决，可能引入难以检测的 event_id 碰撞或 closeout 语义错误。
- **结论**: **不可通过**当前状态。必须修复 B-1、H-2、H-3 后才能进入 implementation gate。

### Slice 数量裁决

3 个 slices 的数量合理。S1（contract）+ S2（consumer migration）+ S3（closeout fix）形成语义闭环：先建 helpers → 再迁移消费者 → 最后修复合成的核心路径。S3 的复杂度显著高于 S1/S2，但这不是 slice 数量问题，而是 S3 自身设计完整性问题。不建议拆分 S3 为更多 slices——worker lifecycle closeout 是一个原子语义，拆分会引入中间态的 contract handoff 风险。

## 未发现的问题

以下方面经审查**未发现**问题：

- **Architecture drift**: 无。plan 严格限制在 Host lifecycle/status owner boundary 内，不触及 Engine contracts、Fins、CLI 或其他层。
- **过度设计**: 无。plan 明确拒绝 broad schema migration、wait lifecycle 变更、dispatch state machine 重构、Engine→Host flat mapping table。所有 slices 都是 current code 直接证据支撑的 owner-boundary cleanup。
- **Schema migration 漏判**: 无。plan 将 schema migration 列为 stop condition（"如果 implementation 发现 terminal status / terminal event 的正确修复必须新增 durable schema CHECK 或迁移，停止并先回 design truth"），当前代码证据不要求 schema 变更。
- **LLM-facing 文本泄漏**: 无。P3-A 的变更全部在 Host 内部 lifecycle/status 治理层面，不触及 tool schema、prompt、memory/compact material 或 Engine event 投影给 LLM 的文本。
- **下游 projection/test fixture 特例分支**: 无。plan 的 non-goals 明确"不修改下游 projection 以掩盖上游事实漂移"，stop conditions 明确"如果 tests 需要通过 raw SQL 特例构造违反 row shape 的状态才能通过，应迁移测试边界，而不是在生产代码保留兼容分支"。
- **Any/object/untyped 逃避**: 无。plan S1 明确禁止使用 `Any`。所有新增 helper 都有完整类型签名。
- **`dayu.runtime` 违规依赖**: 不涉及。所有变更限定在 `dayu/host/` 范围内。

## Completion Report

- **status**: completed
- **artifact**: `docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-ds.md`
- **verdict**: pass-with-findings
- **blocking findings count**: 2 (B-1, B-2)
- **nonblocking findings count**: 8 (H-1, H-2, H-3, M-1, M-2, M-3, M-4, L-1, L-2, L-3)
- **blockers**:
  - B-1: S3 synthetic EngineEvent 移除的 closeout identity scheme 设计不够具体
  - B-2: S2 source scan 验证标记为"可接受"而非强制

## 建议修复顺序

1. 先修 B-1（S3 identity scheme 具体化）——这是最复杂的修复，可能需要与 design truth 交叉验证
2. 再修 B-2（S2 source scan 强制化）+ H-2（CANCELLING 交互决策表）+ H-3（god-bag 消除）——这三项可以并行修复
3. 最后修 H-1（SM-7 验证步骤）+ M-1~M-4 + L-1~L-3 ——non-blocking items

修复后的 plan 应由 AgentMiMo 做 parallel re-review，controller 裁决后进入 implementation gate。
