# Host Design Review — Phase Design Readiness

**Reviewed document**: `docs/host/design.md` (当前终态设计草案)
**Reference document**: `dayu/README.md` (术语真源)
**Date**: 2026-05-13
**Review type**: Adversarial design review for phase design / phase plan readiness

---

## Summary

28 findings: 4 blocking, 10 high, 9 medium, 5 low — covering state machine gaps, terminology consistency, and inter-module coupling. No over-design or responsibility leak findings; the design is architecturally sound and internally consistent.

---

## Findings

### Finding 1 — Attempt 状态集合术语不一致

- **ID**: DS-001
- **Severity**: blocking
- **Lines**: design.md:196, dayu/README.md:51
- **Problem**: design.md 定义 Attempt 状态包含 `STARTING`（line 196），而 dayu/README.md 的 Attempt status 集合不包含 `STARTING`（line 51）。`STARTING` 是本次设计草案引入的关键中间状态——表示 "Host 已创建 Attempt 但 worker 尚未接受 dispatch"（line 219, 335-336）。dayu/README.md 自称为"项目级术语真源"（line 40-42），两者对核心状态机的表述不一致。
- **Why blocks phase design**: Phase plan 拆分时，实现者会从两份权威文件读到不同的 Attempt 状态集合，无法确定 `STARTING` 是否为正式状态机节点。`STARTING` 影响 dispatch 事务边界、`ATTEMPT_STARTED`→`ATTEMPT_RUNNING` 的时序、dispatch 失败语义和 recovery scan 分类逻辑。
- **Recommended fix**: 在 dayu/README.md 的 Attempt status 集合中补充 `STARTING`，并添加简短语义说明。design.md 的 `STARTING` 语义已经是权威定义，dayu/README.md 只需对齐。

---

### Finding 2 — `host_instance_id` 语义未定义，影响 recovery scan 分类逻辑

- **ID**: DS-002
- **Severity**: blocking
- **Lines**: design.md:1611, 1571
- **Problem**: dispatch record schema 包含 `host_instance_id`（line 1611），recovery scan 的分类规则依赖于"存在当前 Host 可确认控制的 dispatch record"（line 1571）的判断。但 `host_instance_id` 的语义未被定义：它是进程 UUID？主机标识？每次 Host 启动重新生成的值？如何判断一个 dispatch record 是否"属于当前 Host 实例"？
- **Why blocks phase design**: Recovery scan 是 Host 启动的关键路径。没有 `host_instance_id` 语义，无法安全实现"判断旧 Attempt 是否仍受当前进程控制"的分类逻辑。phase plan 需要知道这个标识的生命周期和生成策略才能拆分 recovery 模块。
- **Recommended fix**: 在 section 26 中明确 `host_instance_id` 是 Host 每次启动时生成的 UUID，dispatch record 携带创建该 record 时的 `host_instance_id`。Recovery scan 通过比较 dispatch record 的 `host_instance_id` 与当前实例的 `host_instance_id` 判断可确认性——相同则说明旧 Attempt 由本进程创建（可能仍存活），不同则不可确认。

---

### Finding 3 — steer 对 `WAITING` Run 的行为未指定

- **ID**: DS-003
- **Severity**: blocking
- **Lines**: design.md:248-254, 617-644
- **Problem**: `WAITING` 属于 active Run 状态（line 254），steer 的前置条件是"active Run"（line 617）。但 steer 路径（line 627-634）假设当前 Attempt 是 `RUNNING` 状态且可通过 cancellation source 发起停止请求。对于 `WAITING` Run，Attempt 已经是 `SUSPENDED` 终态。此时 steer 应该如何操作？
  - 选项 A：拒绝 steer，返回 `invalid_state`（因为无 running Attempt 可停止）。
  - 选项 B：取消 wait record，旧 Attempt 标记 `STEERED`，创建新 Attempt。
  - 选项 C：直接创建新 Attempt，不改变 wait record。
- **Why blocks phase design**: steer 是 `submit_followup(behavior=steer)` 的核心路径，WAITING Run 是正常流程中必然出现的高频状态。phase plan 需要知道 steer 在这种状态下的行为才能安全拆分 see 模块。
- **Recommended fix**: 明确 steer 对 `WAITING` Run 的行为。推荐选项 A（拒绝，返回 `invalid_state`），因为 steer 语义是重定向"正在进行的"工作；WAITING Run 的工作已完成一轮并挂起，不应被中途 steer。用户应该 cancel 后 steer，或 resume 后 steer。如果需要 B 或 C，需新增对应的状态迁移表条目。

---

### Finding 4 — `resolve_wait` 在 wait record 非 `waiting` 状态时的行为未指定

- **ID**: DS-004
- **Severity**: blocking
- **Lines**: design.md:1257, 1231
- **Problem**: `resolve_wait` 是所有等待结果进入 Host 的统一入口（line 1257）。wait record 的状态集合包含 `waiting`、`resolved`、`failed`、`cancelled`、`lost`（line 1231）。`resolve_wait` 在 wait record 已经 `cancelled`（被 cancel_run 抢先）、`lost`（被 recovery 标记）或已经 `resolved`（重复调用）时的行为未定义。
  - line 1275 提到迟到结果应进入 diagnostic/tool trace，这是对 poll/callback adapter 的约束，但 `resolve_wait` pipeline 本身如何响应未说明。
- **Why blocks phase design**: `resolve_wait` 被 poll adapter、callback handler、manual admin 三个入口共享。如果它的错误语义未定义，三个入口的实现者需要各自猜测如何处理非 `waiting` 状态的 wait record，导致分散的错误处理逻辑。
- **Recommended fix**: 明确 `resolve_wait` 对非 `waiting` wait record 必须返回 `invalid_state` 或 `conflict`。在 section 10 的公共错误分类中，`conflict` 场景应包含"wait record 已 resolved/cancelled/lost"。

---

### Finding 5 — `resolve_wait` 的幂等 scope 未定义

- **ID**: DS-005
- **Severity**: high
- **Lines**: design.md:548-553, 1258
- **Problem**: `ResolveWaitRequest` 携带 `idempotency_key`（line 549），Public API 签名是 `resolve_wait(host, wait_id, request)`（line 439），内部 pipeline 形式是 `resolve_wait(wait_id, outcome, source, idempotency_key)`（line 1258）。但幂等 scope 未定义：idempotency_key 对什么去重？同一 wait_id？同一 session？如果同一 idempotency_key 用不同 outcome 调用是否返回 `idempotency_conflict`？
- **Why phase design needs clarification**: `idempotency_key` 与 `wait_id` 的关系直接影响 poll adapter 的 retry 策略和 callback handler 的重放防护。若不明确，三个 adapter 各自实现幂等语义。
- **Recommended fix**: 明确 `resolve_wait` 的幂等 scope 是 `(wait_id, idempotency_key)`。同一 wait_id + 同一 idempotency_key 重试返回已接受结果；同一 wait_id + 不同 idempotency_key + 不同 outcome 返回 `idempotency_conflict`。

---

### Finding 6 — `RETRY_REQUESTED` / `REPLAY_REQUESTED` 与关联新 Run 的引用不明确

- **ID**: DS-006
- **Severity**: high
- **Lines**: design.md:797, 321-323
- **Problem**: `RETRY_REQUESTED` 和 `REPLAY_REQUESTED` 在 canonical event contract matrix 中 scope 为 `run_id?`（line 797）。design 明确这两者创建关联的新 Run（line 321-323），但 matrix 中只标注了"创建关联新 Run，不重开源 Run"作为状态副作用。缺少以下关键信息：
  - 新 Run 的 `run_id` 在哪条 canonical event 中标定？是在 `RUN_ACCEPTED` 中？
  - `RETRY_REQUESTED` 的 `run_id` 是源 Run 还是新 Run？如果是源 Run，如何把新 Run 与源 Run 关联？
  - 是否需要在 `RUN_ACCEPTED` 事件中增加 `source_run_id` / `retry_of_run_id` / `replay_of_run_id` 字段？
- **Why phase design needs clarification**: retry/replay 创建的新 Run 需要通过某种方式与源 Run 关联，用于 session timeline 展示和 audit 追溯。如果关联方式未定义，phase plan 中的 EventLog schema design 会缺失必要字段。
- **Recommended fix**: 在 canonical event contract matrix 中为 `RUN_ACCEPTED`（被 retry/replay 触发时）增加 `source_run_id` 和 `source_run_relation: retry | replay` 字段。`RETRY_REQUESTED` / `REPLAY_REQUESTED` 的 `run_id` 明确标注为源 Run，新 Run 的 identity 由随后的 `RUN_ACCEPTED` 事件中的 `run_id` 表达。

---

### Finding 7 — `RECOVERING -> FAILED` 状态迁移缺失

- **ID**: DS-007
- **Severity**: high
- **Lines**: design.md:327-329
- **Problem**: `RECOVERING` 的退出路径只有 `RECOVERING -> RUNNING`、`RECOVERING -> CANCELLED`、`RECOVERING -> LOST`（line 327-329）。但 recovery 期间创建的新 Attempt 可能执行失败（Engine 返回 `run_failed` 且非 context_compaction_required）。此时 Run 应从 `RECOVERING` 转到 `FAILED`，而不是 `LOST`（因为执行失败是已确认失败）。当前退出路径缺少这个常规分支。
- **Why phase design needs clarification**: 如果没有 `RECOVERING -> FAILED`，实现者需要猜测：recovery 后的新 Attempt 执行失败时是回退到 `RECOVERING` 重试（受 policy 上限约束），还是进入 `FAILED` 终态。这影响 recovery policy 的计次逻辑和状态机实现。
- **Recommended fix**: 在 `RECOVERING` 退出路径中增加 `RECOVERING -> FAILED`：Host 创建的恢复 Attempt 以 `ATTEMPT_FAILED` 收口且 non-recoverable 时，Run 进入 `FAILED`。同时说明：如果失败是可恢复的（如 context_compaction_required），应返回 `RECOVERING` 继续，这是 recovery retry 的正常路径。

---

### Finding 8 — `STEER_REQUESTED` 的 `run_id` 被标记为可选，与语义矛盾

- **ID**: DS-008
- **Severity**: high
- **Lines**: design.md:799
- **Problem**: canonical event contract matrix 中 `STEER_REQUESTED` 与 `FOLLOWUP_QUEUED`、`CANCEL_REQUESTED` 等共享同一行，scope 为 `run_id?`（line 799）。但 steer 必须命中 active Run（line 617），`STEER_REQUESTED` 的 `run_id` 应该是 required。`FOLLOWUP_QUEUED` 的 `run_id` 可选（因为 follow-up 可能正在排队），但这不应淹没 `STEER_REQUESTED` 的强制约束。
- **Why phase design needs clarification**: EventLog schema 生成时，如果 `STEER_REQUESTED` 的 `run_id` 被当作可选，validation rules 会允许缺少 run_id 的 steer event 通过，这将破坏审计追溯和状态机正确性。
- **Recommended fix**: 拆分行，至少将 `STEER_REQUESTED` 与其他可选 `run_id` 的事件分开，明确标注 `STEER_REQUESTED` 的 `run_id` 为 required。

---

### Finding 9 — ToolRuntime duplicate index 在 steer 场景下的行为未指定

- **ID**: DS-009
- **Severity**: high
- **Lines**: design.md:1124-1125, 617-634
- **Problem**: ToolRuntime 维护 run-local in-memory duplicate index（line 1124）。Host 崩溃后新 Attempt 不继承该索引是明确的（line 1125）。但 steer 在同一次 Run 内通过新 Attempt 继续执行——新 Attempt 的 ToolRuntime duplicate index 取决于 run_scope。
  - 如果 index scope 是 run-local: steer 后的新 Attempt 应该继承旧 Attempt 的 duplicate index，因为 Run 未变。
  - 如果 index scope 是 attempt-local: 新 Attempt 不继承，可能导致 steer 后重复执行已在旧 Attempt 中执行过的工具。
  - 如果 index 通过与 Host accept barrier 同步重建：需要说明重建机制。
- **Why phase design needs clarification**: steer 是高频操作路径。如果新 Attempt 的 duplicate index 为空，模型可能在 steer 后再次调用同一工具，造成浪费。如果继承，需要设计 index 的 snapshot 和恢复机制。
- **Recommended fix**: 明确 ToolRuntime duplicate index 的 scope 是 run-local（同 Run 内所有 Attempt 共享），且在创建新 Attempt 时，ToolRuntime snapshot 中包含已接受工具事实的 duplicate key set，新 Attempt 的 ToolRuntime 基于 snapshot 恢复 duplicate index。

---

### Finding 10 — `STARTING` Attempt 的 dispatch 失败 / 拒绝路径终端状态未在状态迁移表中列出

- **ID**: DS-010
- **Severity**: high
- **Lines**: design.md:310, 337-338
- **Problem**: 状态迁移表（section 8.1）中 `start_run` 和 queue promotion 的路径终点直接是 Run `RUNNING` / Attempt `STARTED`（随后 `ATTEMPT_RUNNING`）。但 line 337-338 明确说"dispatch 失败、startup timeout、cancel during STARTING 都必须有明确状态事实或 diagnostic path"。dispatch 失败时 Attempt 应进入什么终态？`FAILED` 还是 `LOST`？Run 进入 `FAILED`、`RECOVERING` 还是 `LOST`？状态迁移表中没有对应条目。
- **Why phase design needs clarification**: dispatch 失败是正常错误路径，发生在 worker 不接受或启动超时时。如果不在架构级指定它进入哪个终态，实现者会自行选择 `FAILED`（语义不符，因为未执行）或 `LOST`（语义不符，因为可以确认失败），导致不一致。
- **Recommended fix**: 在状态迁移表中增加一行：`STARTING` Attempt dispatch 失败 -> Attempt `FAILED`，Run 按 policy 进入 `FAILED` 或进入 admission（新建 Run / queue promotion）。

---

### Finding 11 — CANCELLING 的四个退出路径之间缺乏具体的判定条件

- **ID**: DS-011
- **Severity**: high
- **Lines**: design.md:180, 320
- **Problem**: `CANCELLING` Run 的退出路径有四个：`CANCELLED`、`WAITING`、`RECOVERING`、`LOST`（line 320）。其中 `CANCELLED` 与 `WAITING` 的判定条件可推导——取决于旧 Attempt 收口为 `CANCELLED` 还是 `SUSPENDED`（tool_awaiting 先到）。但 `CANCELLING -> RECOVERING` 与 `CANCELLING -> LOST` 的分支条件未说明：cancel 过程中的 Attempt `LOST` 后，什么算"可恢复"、什么算"不可恢复"？这依赖 Run 的 canonical facts 完整性，但判定边界未定义。
- **Why phase design needs clarification**: 这是 cancel + recovery scan 的交集路径。若 attempt 在 cancel 过程中丢失，Host 需要判断是恢复执行（让 Run produce answer）还是放弃（LOST）。判定标准不明确会导致实现者在两个路径之间猜测。
- **Recommended fix**: 明确 `CANCELLING -> RECOVERING` 的条件：`USER_INPUT_ACCEPTED` 和必要的 canonical tool facts 已持久化，且 recovery policy 允许。`CANCELLING -> LOST` 的条件：必要 facts 缺失或 recovery policy 放弃。这实际上与 recovery scan 的分类逻辑相同，可以在 section 26 中统一表述。

---

### Finding 12 — `replay(run)` 状态迁移表中前置条件"output dirty"未定义

- **ID**: DS-012
- **Severity**: medium
- **Lines**: design.md:322
- **Problem**: 状态迁移表中的 `replay(run)` 前置条件写为"Run `SUCCEEDED` 或 output dirty"（line 322）。`SUCCEEDED` 是明确的状态，但"output dirty"不是 Run 状态，也不是已定义的概念。它在 line 1316 中展开为"final answer 脏数据、schema invalid、违反输出 policy，或用户要求在不重复昂贵工具的前提下重新生成"——这是 replay 的触发条件，不是 Run 的前置状态。
- **Why it matters**: 实现者可能误解为存在一个"dirty output"标志位，需要在 Run 对象中建模。
- **Recommended fix**: 将前置条件明确为"Run `SUCCEEDED`"——replay 只能对已成功的 Run 执行。触发条件（数据脏、schema 无效等）属于用户/系统判断，不是状态机前置条件。

---

### Finding 13 — `CONTEXT_COMPACTION_FAILED` 后 Run 状态不明确

- **ID**: DS-013
- **Severity**: medium
- **Lines**: design.md:802, 1501
- **Problem**: canonical event contract matrix 中 `CONTEXT_COMPACTION_FAILED` 的状态副作用是"failed 后按 policy 失败或保持 recoverable"（line 802）。但 compact failed 后 Run 的具体状态未定：`FAILED` 或仍 `RECOVERING`。line 1501 的 compact 路径中，`CONTEXT_COMPACTION_FAILED` 后续没有"创建新 Attempt"的步骤（与 `CONTEXT_COMPACTED` 不同）。这是否意味着 compact failed 总是不可恢复？
- **Why it matters**: compact failed 是 context overflow 场景的关键收口，实现者需要知道在此之后 Run 进入什么状态。
- **Recommended fix**: 明确 `CONTEXT_COMPACTION_FAILED` 后：如果 compact retry policy 允许且未超过上限，Run 保持 `RECOVERING` 并重试 compact；如果放弃或超过上限，Run 进入 `FAILED`。compact retry 次数应纳入 context governance policy provider。

---

### Finding 14 — `SessionSnapshot` 中 "active run" 的表示粒度未指定

- **ID**: DS-014
- **Severity**: medium
- **Lines**: design.md:583
- **Problem**: `SessionSnapshot` 定义包含"active run"（line 583）。但未说明 active run 是仅 `run_id` 引用，还是内嵌 `RunSnapshot`。如果是引用，调用方需要额外调用 `get_run` 获取详情，增加一次查询。但 `SessionSnapshot` 的职责是快照——它应在加载时决定是否包含完整 Run 信息。
- **Why it matters**: phase plan 需要决定 `SessionSnapshot` 的内存结构和 SQL 查询模式。如果 active run 是嵌套的 RunSnapshot，需要定义其与 `get_run` 的 RunSnapshot 是否一致。
- **Recommended fix**: 明确 `SessionSnapshot.active_run` 是 `RunSnapshot | None`——如果 Session 有 active Run，`SessionSnapshot` 携带该 Run 的完整 snapshot。`queued_runs` 可以仅携带 `(run_id, queued_at_cursor)` 摘要，因为数量可能较多。

---

### Finding 15 — `CONTEXT_COMPACTION_REQUESTED` 的 `attempt_id` / `execution_id` 对 proactive trigger 为空时的语义不明确

- **ID**: DS-015
- **Severity**: medium
- **Lines**: design.md:802, 1490-1492
- **Problem**: `CONTEXT_COMPACTION_REQUESTED` 有两种触发来源：proactive（Host dispatch 前判断预算）和 reactive（Engine 回传 context_compaction_requested）。proactive 触发时还没有 `attempt_id` 和 `execution_id`（因为 Attempt 尚未创建）。canonical event contract matrix 中这两个字段标记为可选（line 802），但对 proactive trigger 而言，缺少 attempt_id 的 compact event 如何与后续新 Attempt 的 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 关联？Reactive trigger 已有明确的 attempt scope；proactive trigger 缺少这个 scope 会导致 compact event 链路在 audit 中不连贯。
- **Why it matters**: audit / tool trace 需要完整解释 compact 决策链。如果 proactive compact request 不与任何 Attempt 关联，审计追溯会出现断链。
- **Recommended fix**: proactive trigger 的 `CONTEXT_COMPACTION_REQUESTED` 关联到当前的 Run（有 `run_id`），但不关联 `attempt_id`。同时为 `ATTEMPT_STARTED` 增加 `compact_version` 或 `context_snapshot_ref` 可选字段，用于关联前置 compact 事件。或更简单地：proactive compact 合并到 RunInputBuilder 的预算分配中，不作为独立 canonical event，只在 compacted 成功时产出 `CONTEXT_COMPACTED`。

---

### Finding 16 — Outbox delivery target 在 resume 创建的 Run 中未完整追溯

- **ID**: DS-016
- **Severity**: medium
- **Lines**: design.md:961, 316
- **Problem**: Outbox delivery target 来自 `HostCallContext`、Session binding 或 request 显式字段（line 961）。但 resume path（line 316）中创建的 Attempt / Run continuation 没有新的 `start_run` 调用，没有新的 `HostCallContext`。`resolve_wait` 的 `ResolveWaitRequest` 不携带 `delivery_target_hint`。如果 wait 完成后 Run 最终 `SUCCEEDED`，final answer 应投递到最初的 delivery target（来自最初的 `start_run`），但这个追溯没有显式声明。
- **Why it matters**: outbox delivery 的正确性是最终用户能否收到 answer 的关键。如果 delivery target 只在 initial `start_run` 时记录，resume path 不应丢失它——但这需要在 Run 或 wait record 中持久化 delivery target，需要明确设计。
- **Recommended fix**: 明确 Run 在创建时从 `HostCallContext` 中 durable 记录 `delivery_target`。`resolve_wait` 不需传递 delivery target，因为 Run 已经持有它。Outbox dispatch 从 Run terminal fact 的关联 Run 中读取 delivery target。

---

### Finding 17 — `resolve_wait` 公共接口与内部 pipeline 的形式不一致

- **ID**: DS-017
- **Severity**: low
- **Lines**: design.md:439, 1258
- **Problem**: 公共 API 签名为 `resolve_wait(host, wait_id, request) -> RunSnapshot`（line 439），其中 `request` 是 `ResolveWaitRequest`。内部 pipeline 形式为 `resolve_wait(wait_id, outcome, source, idempotency_key)`（line 1258），缺少 host handle 参数，缺少统一的 request 对象。虽然内部形式可能是简化表达，但容易让 phase plan 中的模块接口设计产生歧义。
- **Recommended fix**: 统一使用 `resolve_wait(host, wait_id, request)` 形式，内部 pipeline 也接收完整的 `ResolveWaitRequest`。删除 line 1258 的简化签名，或标注为"内部概念示意，非实际函数签名"。

---

### Finding 18 — `FOLLOWUP_QUEUED` 的 `run_id` 可选但语义存疑

- **ID**: DS-018
- **Severity**: low
- **Lines**: design.md:799
- **Problem**: `FOLLOWUP_QUEUED` 在 matrix 中 scope 为 `run_id?`（line 799）。follow-up 以 `queue` 行为提交时，如果当前没有 active Run，它按 `start_run` 语义创建新 Run——此时 `FOLLOWUP_QUEUED` 实际上对应一个新 Run，应该有 `run_id`。只有当 follow-up 被排队到已有 active Run 的后续队列时，它也有一个 queued Run。两种情况下 follow-up 都应关联到一个 Run（当前新建或排队创建）。`run_id?` 可选的理由不明确。
- **Recommended fix**: `FOLLOWUP_QUEUED` 的 `run_id` 应为 required。follow-up 要么创建新 Run，要么作为 queued Run 存在，无论哪种都有 run_id。

---

### Finding 19 — `QUEUED -> RUNNING` promotion 与 `RECOVERING` 的优先级未指定

- **ID**: DS-019
- **Severity**: low
- **Lines**: design.md:284-289
- **Problem**: queue promotion 在 Session 无 active Run 时触发（line 285），promotion trigger 包括"active Run 进入终态"和"Host 启动 recovery scan 后"（line 288）。但 recovery scan 可能同时产生 `RECOVERING` Run（它占 active slot）和 queued Run promotion 的触发条件。如果 Session 有一个 `QUEUED` Run 和一个刚被 recovery scan 标记为 `RECOVERING` 的 Run，promotion check 是否应该等待 `RECOVERING -> RUNNING` 或 `RECOVERING -> LOST` 后再 promotion？还是 promotion 和 `RECOVERING` 同时竞争 active slot？
- **Why it's low**: recovery scan 对同一 Session 只产生一个 `RECOVERING` Run（从单个 `RUNNING` / `CANCELLING` Run 恢复），且 promotion check 是正确的触发器。设计已说明 `RECOVERING` 是 active Run 状态，所以它自然阻止 promotion。实现者不易在此犯错。
- **Recommended fix**: 不需要架构级修改。在 phase design 的 recovery 详细设计中只需明确：recovery scan 将 Run 标记为 `RECOVERING` 后再触发 queue promotion check，此时 `RECOVERING` 已占有 active slot，promotion 自然无法成功。

---

### Finding 20 — `get_session` 与 `stream_run_events` 的职责边界有轻微模糊

- **ID**: DS-020
- **Severity**: low
- **Lines**: design.md:429, 434, 579
- **Problem**: `get_session(session_id) -> SessionSnapshot` 返回"timeline summary"（line 941），line 579 说"读取 Session timeline 通过 `get_session` 的 snapshot 或后续 read-model API 暴露；它必须从 EventLog / projection 读取，不触发执行"。但 Session timeline 是面向 UI 的多 Run 事件视图，与 `stream_run_events(run_id, cursor)` 是按 Run 的事件流不同。没有 session-level event stream 接口。如果 UI 需要跨 Run 的时间线体验，只能通过 `get_session` 定期轮询——这不够实时。
- **Why it's low**: 第一版 minimal API 不需要 session-level streaming，轮询 `get_session` 的 timeline cursor 已足够。后续 read-model API 可以扩展。
- **Recommended fix**: 不需要第一版修改。在 section 27 non-goals 或 outbox 附近注明"Session-level event stream 属于后续 read-model API 扩展，不在第一版"。

---

### Finding 21 — `resolve_wait` 成功后 `Queued Run` 的 promotion 链未明确

- **ID**: DS-021
- **Severity**: low
- **Lines**: design.md:288, 316
- **Problem**: `resolve_wait` 后 Run 重新进入 `RUNNING`（line 316），这会占用 Session 的 active slot。设计已明确 active Run 进入终态后必须触发 queue promotion check（line 288）。但 `resolve_wait` 将 Run 从 `WAITING` 变为 `RUNNING` 本身不释放 active slot——这是预期行为。问题是实现者可能忘记 `resolve_wait` 后 Run 仍占 active slot，认为需要在 `resolve_wait` 后触发 promotion。
- **Why it's low**: 这是一个实现提醒而非设计缺口。
- **Recommended fix**: 不需要架构级修改。在 `resolve_wait` 路径注释中加一句"本路径不释放 Session active slot，不触发 queue promotion"即可。

---

### Finding 22 — `CANCELLING -> LOST` 后 `RECOVERING` 的 Host policy 上限应区分 cancel-timeout LOST 与 crash LOST

- **ID**: DS-022
- **Severity**: low
- **Lines**: design.md:331, 1355
- **Problem**: recovery、retry、replay 和 context compaction retry 都有 policy 上限（line 331）。line 1355 描述了 cancel 超时路径："未引入 watchdog 强化治理前，cancel 请求发出后如果 active Attempt 超时仍无法确认，旧 Attempt 进入 LOST"。cancel 导致的 LOST 和 crash 导致的 LOST 都使用同一个 recovery policy 上限——但 cancel LOST 的 recovery 语义不同（用户已经要求取消，恢复后如果又 produce answer 可能需要特殊处理）。
- **Why it's low**: 这是 recovery policy 的精细化设计，不影响第一版最小可行实现。
- **Recommended fix**: 不需要第一版修改。在 recovery policy provider 的 phase design 中可以考虑区分 crash recovery 与 cancel-timeout recovery 的默认策略。

---

---

## Over-Coupling Analysis

以下为"过度耦合"独立审查维度的发现。审查对象为模块职责之间的不必要耦合、循环依赖风险、配置 / policy ownership 混乱。

---

### Finding C-001 — ToolRuntime accept barrier 在 RemoteProxy 场景下产生对 Host 的同步阻塞依赖

- **ID**: C-001
- **Severity**: high
- **Lines**: design.md:1074, 1077-1087, 1089
- **Problem**: ToolRuntime accept barrier 要求工具事实必须提交给 Host，收到 accepted ack 后才能把 tool result 返回给 Engine 继续推理（line 1077-1087）。design 明确该路径"对 LocalProxy 与 RemoteProxy 语义一致"（line 1089）。对于 LocalProxy，这条路径是进程内函数调用；对于 RemoteProxy，这意味着每次工具执行都需要 RemoteStub → RemoteProxy → Host → EventLog → ack 的完整往返。
  - 如果 Host 不可达（网络分区、Host 重启），远端 EngineWorker 的工具执行会阻塞在 accept barrier。
  - Engine 的 tool loop 被 accept barrier 的延迟直接影响——每个 tool call 都会增加一个 Host 往返延迟。
  - design 未区分"工具事实必须先被 Host durable accepted"的正确性约束与"ToolRuntime 必须同步等待 ack"的执行耦合。是否可以在 ToolRuntime 处异步提交、并在 ack 到达前 hold Engine？是否可以有 batch accept？
- **Why blocks phase design**: RemoteProxy phase plan 需要知道 accept barrier 的通信模式是同步 RPC 还是可以异步 / batch。如果 accept barrier 强制同步，RemoteProxy wire protocol design 必须为每条 tool result 承载 request-ack 语义；如果可以异步或 batch，protocol 设计完全不同。
- **Recommended fix**: 明确 accept barrier 的执行语义：
  1. 单个工具事实必须单独走 accept→ack，还是可以 batch accept？
  2. ToolRuntime 提交 fact candidate 后是否阻塞 Engine tool loop？如果阻塞，超时策略是什么？
  3. RemoteProxy 的 accept barrier 是否允许异步——ToolRuntime 提交后立即返回 pending handle，ack 到达后在 Engine side 解除阻塞？

---

### Finding C-002 — RemoteProxy 必须实现 accept barrier 协议，但 ToolRuntime governance ownership 属于 Host

- **ID**: C-002
- **Severity**: high
- **Lines**: design.md:1010-1014, 1089, 1074
- **Problem**: design 将 RemoteProxy 定位为"transport substitution, 不是 governance boundary"（line 1011-1012）。但 accept barrier（line 1089）要求 RemoteProxy 和 RemoteStub 之间的 wire protocol 承载 tool fact candidate → accept ack 语义。RemoteProxy 作为 transport 层需要理解以下 governance 概念：
  - 什么是"Host accepted ack"（区分 accepted vs rejected vs diagnostic）
  - 如何在 wire protocol 中表达 canonical event refs（ack 携带的内容）
  - accept barrier 的超时和重试策略（属于 ToolRuntime policy 还是 transport policy？）
  - 当前 design 把"tool fact accepted ack"定义为"ToolRuntime / EngineWorker 执行语义的一部分，不是 wire protocol 细节"（line 1014）——但这要求 transport 层实现 governance 语义，与"RemoteProxy 只是 transport substitution"矛盾。
- **Why blocks phase design**: 如果 accept barrier 的实现需要 RemoteProxy 理解 ToolRuntime governance 概念，RemoteProxy 的 phase design 需要包含 ToolRuntime 相关知识。这削弱了 transport 层的可替换性，也让 RemoteProxy 的职责边界模糊。
- **Recommended fix**: 二选一：
  - A. 在 ToolRuntime 与 Host accept path 之间定义一层 accept protocol contract（e.g., `ToolFactAcceptance` protocol），RemoteProxy 只传输该 protocol 的序列化 payload，不理解 governance 语义。
  - B. 承认 RemoteProxy 需要理解最小 accept barrier 语义（区分 accepted / rejected），并在 section 16 中明确 RemoteProxy 的"transport substitution"不包括 accept barrier——accept barrier 是跨 Host 和 ToolRuntime 的协议，transport 只承载其 wire format。

---

### Finding C-003 — RunInputBuilder 输入知识面过宽，与多个模块的内部结构隐式耦合

- **ID**: C-003
- **Severity**: medium
- **Lines**: design.md:1362-1376, 1391-1396
- **Problem**: RunInputBuilder 是"memory / EventLog / Service 场景输入进入 Engine 的唯一运行态入口"（line 1362）。其输入包含：
  - EventLog canonical facts（需要理解 EventLog 结构和 event_type 语义）
  - Memory snapshot 的 stable layer + history pool 结构（pinned_state, tool-verified facts, assumptions, episode summaries）
  - Compact artifact / context snapshot refs
  - Service 提供的 system messages / 场景参数
  - Tool schemas snapshot
  - Runner / policy config
  - messages 构造顺序（line 1391-1396）硬编码了对各输入源语义优先级的理解
  如果 Memory 的内部结构变化（例如 stable layer 增加新分区）、EventLog 增加新 canonical event type、或 compact artifact 格式演变，RunInputBuilder 都需要同步修改。当前 design 没有为 RunInputBuilder 定义输入 adapter 接口——它直接消费各模块的内部结构。
- **Why it matters**: RunInputBuilder 是 messages 正确性的关键路径。如果它与多个模块的内部结构紧耦合，任一模块的 schema 变更都会波及其实现。Phase plan 中 RunInputBuilder 的 phase 会隐含依赖 Memory phase、EventLog phase、compact phase 的完成——这些依赖需要显式化。
- **Recommended fix**: 为 RunInputBuilder 定义输入契约接口而非直接消费内部结构：
  - `CanonicalFactProjector`: 将 EventLog canonical facts 投影为 message-ready turns，而非直接消费 EventLog rows。
  - `MemoryBlockProvider`: 返回 message-ready stable facts 和 history pool，而非直接读 memory snapshot 内部结构。
  - 或者至少在 phase plan 中显式标注 RunInputBuilder phase 对 Memory phase、EventLog schema phase 的依赖关系。

---

### Finding C-004 — EventLog canonical event_type 命名空间同时服务状态机、RunInputBuilder、Memory、Audit、Outbox、ToolTrace，缺乏 per-consumer 的最小 contract

- **ID**: C-004
- **Severity**: medium
- **Lines**: design.md:648-662, 731-775, 783-803
- **Problem**: canonical event_type 集合（line 731-775）被至少 6 类消费者使用：状态迁移引擎、RunInputBuilder（message 重建）、Memory projection、Audit projection、OutboxSink、ToolTrace projection。design 在 canonical event contract matrix（section 12.3）中标注了每个 event_type 的"Resume / memory"和"Audit / Host event stream"列，但没有为 per-consumer 明确定义：
  - 哪些 event_type 是某个 consumer 的"必须消费"集
  - 哪些 event_type 该 consumer 必须忽略
  - 新增 event_type 时需要通知哪些 consumer
  这会导致两个风险：
  1. 新增 canonical event type 时，实现者不知道需要更新哪些 consumer。
  2. Consumer 实现者面对 30+ event types，不确定哪些与自己相关。
- **Why it matters**: Phase plan 中 EventLog schema phase 完成后，后续的 Memory phase、Audit phase、Outbox phase 的 implementer 需要从 matrix 中反向推导自己消费哪些 event——容易遗漏。
- **Recommended fix**: 在 canonical event contract matrix 中增加 per-consumer 的必选/可选标注列，或在 section 13 中为每个 sink 明确列出其消费的 event_type 子集。

---

### Finding C-005 — Host handle 持有 ToolRuntime factory，但 ToolRuntime 生命周期跨越 Host（创建）与 EngineWorker（执行）

- **ID**: C-005
- **Severity**: medium
- **Lines**: design.md:385-397, 1040-1048, 1056-1065
- **Problem**: Host handle 的依赖列表中包含"ToolRuntime factory"（line 393）。Host 创建 ToolRuntime 实例后，通过 attempt snapshot 传递给 EngineWorker（line 1045: "ToolExecutor capability snapshot"）。但 design 同时说"Host 持有 ToolRuntime 的治理 ownership"（line 1069）和"ToolRuntime 是 ToolExecutor"（line 1070）。生命周期耦合点：
  - Host 创建 ToolRuntime（factory ownership）。
  - ToolRuntime 被序列化（或引用传递）到 attempt snapshot。
  - EngineWorker 接收后调用其 `ToolExecutor.execute()`。
  - 但 ToolRuntime 在执行期间需要通过 accept barrier 回调 Host。
  - 当 Attempt 结束（SUCCEEDED / FAILED / SUSPENDED 等）时，ToolRuntime 的清理由谁负责？Host 还是 EngineWorker？
- **Why it matters**: Phase plan 拆分 ToolRuntime phase 时，需要明确其 lifecycle owner 和 cleanup 责任。如果 ToolRuntime 持有 TruncationManager 的资源（cursor store, artifact refs, short-lived cache, duplicate index），在 Attempt 终态时清理不干净会导致资源泄漏。
- **Recommended fix**: 明确 ToolRuntime 的生命周期边界：
  - 创建：Host 通过 ToolRuntime factory 创建实例。
  - 执行：EngineWorker 持有 ToolRuntime 引用并在 tool loop 中调用。
  - 清理：Attempt 终态时由 EngineWorker 调用 ToolRuntime 的清理方法（释放 duplicate index、short-lived cache、cursor resources）。Host 在 attempt snapshot 中提供清理策略（timeout, force cleanup on terminal）。
  - 或者：ToolRuntime 在执行期是 EngineWorker-local 对象，Host 只持有 factory 和 policy snapshot，不持有实例。

---

### Finding C-006 — Outbox delivery target 从三个不同来源解析，存在隐式优先级冲突

- **ID**: C-006
- **Severity**: low
- **Lines**: design.md:961, 451-457
- **Problem**: Outbox delivery target 的来源被描述为"`HostCallContext`、Session binding 或 request 显式字段的稳定来源"（line 961）。三个来源可能在同一 Run 中给出不同的 delivery target：
  - `start_run` 时的 `HostCallContext.delivery_target_hint`（line 455）
  - Session 的 slot binding 可能隐式关联到一个 channel（e.g., WeChat）
  - request 显式字段未在 `StartRunRequest` schema 中列出（line 502-510）
  在 resume 路径中（没有新的 `start_run`），delivery target 来自最初 Run 创建时的记录——但三个来源的优先级未定义。如果最初的目标是 CLI，但 Session slot 后来被 Web 入口复用，答案应该投递到哪？
- **Why it's low**: 这是 delivery policy 的精细化设计，不影响第一版最小可行实现。默认优先级（request > HostCallContext > Session binding）足够常见。
- **Recommended fix**: 明确 delivery target 的解析优先级，并明确 delivery target 在 Run 创建时固化到 Run durable state，不再受后续 Session slot 重绑定的影响。

---

## Readiness Verdict

**Ready with phase-local followups.**

总计 28 findings：4 blocking (DS-001 ~ DS-004)，10 high (DS-005 ~ DS-011 + C-001 ~ C-002)，9 medium (DS-012 ~ DS-016 + C-003 ~ C-005)，5 low (DS-017 ~ DS-022 + C-006)。

4 个 blocking finding 构成了最小的 pre-phase-design 修正集：一个术语对齐、两个状态机边界补全、一个语义定义。这些都可以在 phase design 启动前的 30 分钟内修完，不需要 re-architecture。

余下 high finding 是 phase design 各模块可以顺序消解的缺口——它们不会让 phase plan 的拆分产生错误的方向，但应分配到对应的 phase design doc 中作为"本 phase 需决定的问题"。

**耦合分析结论**: 设计整体耦合度可控。核心耦合路径（EventLog → all consumers, Host → ToolRuntime factory）是事件溯源和治理架构的正常耦合，不是过度耦合。两个 high 耦合 finding (C-001, C-002) 集中在 RemoteProxy 与 ToolRuntime accept barrier 的交界处——这是治理需求（Host 必须是 tool fact 真源）与传输解耦（RemoteProxy 应该是 transport substitution）之间的真实张力，不是设计疏漏。三个 medium 耦合 finding (C-003 ~ C-005) 是模块边界上的知识泄漏，可以在 phase design 中通过引入 adapter interface 或明确 lifecycle boundary 消解，不阻塞整体推进。

设计草案在架构边界、执行路径、semantic contract、EventLog schema、ToolRuntime accept barrier、TruncationManager / fetch_more、retry / replay 函数式语义、Outbox 隔离等关键维度上结构清晰、决策充分。**没有发现过度设计、重复设计或职责泄漏。**
