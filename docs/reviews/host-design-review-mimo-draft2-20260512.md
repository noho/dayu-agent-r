# Host design.md Adversarial Review — Draft 2

- Reviewer: MiMo
- Date: 2026-05-12
- Target: `docs/host/design.md` (current working tree)
- Context: `docs/host/implementation-control.md`, `dayu/README.md` (术语真源)
- 前序 review: `host-design-review-mimo-20260512.md` (round 1), `host-design-review-ds-20260512.md` (round 1)
- 约束: 只产出本 review artifact；不修改 design.md；不启动 Gateflow

## 总评

Round 1 的两个 blocking findings（EventLog sequence 语义、Host handle 定义）已在当前 design.md 中解决：§12 选定全局单调 `event_sequence`，§9.1 补了 Host Handle / Composition Root 最小依赖边界。Canonical event contract matrix（§12.3）已覆盖 29 个 event 的 scope、payload、状态副作用、resume/memory 角色和 audit 角色。RECOVERING 退出转移、steer-terminal 竞态规则、durable queue promotion 触发、wait record 恢复语义等 round 1 high findings 也均已收束。

design.md 作为架构真源，在概念建模、状态机、不变量和硬约束维度已达到可驱动 phase planning 的水平。但仍有 **3 个 blocking finding** 和 **8 个 high finding**，集中在以下方面：

1. 多进程并发的关键竞态路径缺少收束（cancel vs resume、promotion vs cancel）。
2. 语义级重复工具调用治理的 session-scope 查询边界未定义。
3. `scope_token` / cursor durable descriptor 的生命周期和恢复语义不完整。
4. 若干接口细节（`ensure_session` 幂等语义、`cancel_run` idempotency key、`dispatch_record` liveness 机制）留白过多，会导致 plan agent 自行发明。

以下 findings 按严重程度降序排列。

---

## Controller 状态标注（2026-05-13）

本 review 的 findings 已按 `docs/reviews/host-design-review-draft2-controller-adjudication-20260512.md` 裁决，并已写回 `docs/host/design.md`。下方原始严重度保留为 review-time 记录；后续 plan / implementation 以本节状态和当前 `design.md` 为准。

| Finding | 状态 | 归属 / 说明 |
| --- | --- | --- |
| 1 WAITING cancel vs resolve_wait | 已写回 | `WAITING` cancel 直接 `RUN_CANCELLED`；cancel / resolve_wait first-committer-wins。 |
| 2 QUEUED cancel vs promotion | 已写回 | CAS first-committer-wins；promotion/cancel 输方按最新状态处理。 |
| 3 session-scope duplicate boundary | 已裁决并收窄 | 第一版为同一 Run 内模型复读治理，run-local in-memory index，不做 session-scope ledger。 |
| 4 ensure_session 并发幂等 | 已写回 | `(scope, slot_key)` 唯一约束，Session 创建与 slot 绑定同事务。 |
| 5 scope_token / cursor descriptor durability | 已写回 | payload / descriptor co-durability、digest 校验、SQLite payload table + artifact 分层。 |
| 6 dispatch_record / liveness | 已写回到架构级 | `ATTEMPT_STARTED`=`STARTING`，`ATTEMPT_RUNNING` 表示 worker accepted；remote at-least-once 风险边界写入。 |
| 7 cancel_run idempotency key | 后续 phase 细化 | 已在总控追踪；具体 envelope / error taxonomy 进入 API / cancel phase。 |
| 8 tool governance ledger | 已裁决并收窄 | 不做 durable ledger；run-local duplicate governance。 |
| 9 SQLite contention | 后续 phase 细化 | `design.md` 固定 WAL / busy timeout / retry policy 方向；参数进入 storage phase。 |
| 10 RECOVERING retry limit | 已写回 | recovery / retry / replay / compaction retry 必须有 policy 上限。 |
| 11 GUIDANCE_INSERTED consumption | 后续 phase 细化 | 保持架构级 event / RunInputBuilder 边界；具体 guidance policy 进入 ToolRuntime / guidance phase。 |
| 12 SESSION_CLOSED ensure_session | 后续 phase 细化 | 进入 Session API phase。 |
| 13 FollowupSnapshot fields | 后续 phase 细化 | 进入 API snapshot phase。 |

---

## Finding 1 [BLOCKING] — `cancel_run` 与 `resolve_wait` 在 `WAITING` Run 上的竞态路径未定义

**严重程度**: BLOCKING

**位置**: §6 Run 生命周期, §19 Tool Awaiting / Wait Record, §21 Cancel, §10 公共接口

**问题**:

design.md 定义了两条独立路径：

- `resolve_wait` 路径（§19-20）：`WAITING` Run → `RESUME_REQUESTED` → tool terminal/result fact → new Attempt → `RUNNING`。
- `cancel_run` 路径（§21）：active Run → `CANCELLING` → 向当前 Attempt 传播 cancel。

但 `WAITING` 是 active Run 状态（§8），而 §21 的 cancel 路径假设 "active Run 有 active Attempt"。当 Run 处于 `WAITING` 时，当前 Attempt 已经 `SUSPENDED`（关闭），没有正在执行的 Attempt 可以传播 cancel。

design.md 未定义：

1. `cancel_run` 对 `WAITING` Run 的语义：是直接 `CANCELLED`？还是先 resolve wait 再 cancel？还是拒绝？
2. `cancel_run` 和 `resolve_wait` 并发到达时的裁决规则：两者都可以改变 `WAITING` Run 的状态，但方向相反。
3. `WAITING` Run 的 wait record 在 cancel 后的处理：wait record 是否标记为 `cancelled`？外部 job 是否需要通知取消？

**为什么阻塞**: 这是第一版就会遇到的路径——用户提交了问题，Agent 进入长事务等待（例如等待外部数据源），用户随后取消。plan agent 必须自行发明 `WAITING` Run 的取消语义，违反 implementation-control.md 约束。

**建议改法**: 在 §21 补充：

```
cancel_run on WAITING Run:
  - Host 检查 Run 是否有活跃 wait record。
  - 有活跃 wait record 时，Host 在同一事务中：
    append CANCEL_REQUESTED
    mark wait record as cancelled
    append RUN_CANCELLED (skipping CANCELLING — 无 active Attempt 需要收口)
    Run -> CANCELLED
  - 若 cancel 与 resolve_wait 并发到达：
    先到达的事务赢得；后到达的事务检测到 Run 已非 WAITING 后按各自语义处理。
    cancel 先到 -> resolve_wait 检测 Run 已 CANCELLED，忽略或记录 diagnostic。
    resolve_wait 先到 -> cancel 检测 Run 已 RUNNING，走正常 active Attempt cancel 路径。
  - 外部 job 取消通知属于 adapter 能力，不要求第一版实现。
```

**是否阻塞 phase planning**: 是。阻塞 cancel governance phase 和 tool awaiting phase 的 plan 生成。

---

## Finding 2 [BLOCKING] — `durable queue promotion` 与 `cancel_run` 在 `QUEUED` Run 上的竞态路径未定义

**严重程度**: BLOCKING

**位置**: §8 Admission 与多进程并发, §8.1 状态迁移契约, §21 Cancel

**问题**:

§8 定义了 promotion 事务："promotion 与 RUN_STARTED、ATTEMPT_STARTED、Attempt row 创建、dispatch record 创建必须在同一事务中完成"。§21 定义了 "QUEUED 且尚未创建 Attempt 的 Run 被取消时，直接进入 CANCELLED，不创建 Attempt"。

但在多进程场景下：

1. 进程 A 开始 promotion 事务：读取 QUEUED Run，准备 CAS 更新为 RUNNING。
2. 进程 B 同时收到 `cancel_run` 请求：读取同一 QUEUED Run，准备 CAS 更新为 CANCELLED。
3. 两个事务竞争同一行的 CAS 更新。

design.md 未定义：

- CAS 竞争时的裁决规则：promotion 优先还是 cancel 优先？还是"先到先得"（取决于 SQLite 事务提交顺序）？
- 如果 promotion 先提交、cancel 后提交：cancel 应该走 active Attempt cancel 路径（Run 已 RUNNING），还是仍按 QUEUED 短路？
- 如果 cancel 先提交、promotion 后提交：promotion 事务应检测到 Run 已 CANCELLED 并 abort，还是可能误创建 Attempt？

**为什么阻塞**: 多进程 CAS 竞争是 design.md 明确支持的场景（§8 "多进程竞争 promotion 时，只有一个事务能通过 CAS"）。cancel 与 promotion 的竞态是第一版多进程部署的必经路径。

**建议改法**: 在 §8.1 状态迁移契约表中补充：

```
| promotion 与 cancel_run 竞争 | Run QUEUED | CAS 先到先得；promotion 赢 -> Run RUNNING + Attempt；cancel 输方检测到 Run 已 RUNNING，走 active cancel 路径。cancel 赢 -> Run CANCELLED；promotion 输方检测到 Run 已终态，abort 事务。 |
```

并明确：CAS 条件更新的 WHERE 子句必须包含 `status = QUEUED`（cancel）或 `status = QUEUED`（promotion），保证后提交的事务因 status 不匹配而失败。

**是否阻塞 phase planning**: 是。阻塞 admission phase 和 cancel governance phase 的 plan 生成。

---

## Finding 3 [BLOCKING] — 语义级重复工具调用治理的 session-scope 查询边界未定义

**严重程度**: BLOCKING

**位置**: §17.1 语义级重复工具调用治理

**问题**:

§17.1 列出了重复判定信号，包括 "run / session / memory context"。§17.1 末尾说 "第一版可以只实现 run-level / session-level 的 deterministic duplicate key"。但 design.md 未定义 session-scope 查询的范围和成本：

1. **查询范围**：session-scope 重复判定需要扫描当前 Session 的所有历史 Run 的 `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` events。对于长期运行的 Session（例如 WeChat 稳定身份的持续会话），这可能涉及数百个 Run、数千个工具调用。
2. **查询方式**：是从 EventLog 全量扫描？还是维护独立的 tool governance ledger（§9 已列出但未定义）？如果是 ledger，它的 schema、更新时机和与 EventLog 的一致性是什么？
3. **查询成本**：每次工具调用前都需要做重复判定。如果查询成本为 O(N) where N = session 历史工具调用数，长 Session 下性能会退化。

§9 列出了 `tool governance ledger` 作为 durable store 的一部分，但全文未定义其 schema、写入时机或查询语义。它与 §17.1 的关系完全空白。

**为什么阻塞**: ToolRuntime 是 Host 的核心治理模块。如果 plan agent 在 tool governance phase 才决定 ledger schema，可能导致与 EventLog 的重复存储、查询性能问题或一致性问题。

**建议改法**: 在 §17.1 补充：

```
session-scope 重复判定边界：
  - 第一版使用 tool governance ledger 维护 per-session 的工具调用摘要索引。
  - ledger 字段至少包含：session_id, tool_name, normalized_args_digest,
    result_digest, evidence_scope_digest, event_ref, accepted_at。
  - ledger 在 TOOL_RESULT_ACCEPTED / TOOL_TERMINAL_RESULT append 后同步更新，
    与 EventLog append 在同一事务内。
  - ToolRuntime 查询时只读 ledger，不扫描 EventLog。
  - 跨多年长期记忆的语义重复不在第一版治理范围（已明确），但 ledger 设计
    不得封死后续扩展。
```

**是否阻塞 phase planning**: 是。阻塞 ToolRuntime / tool governance phase 的 plan 生成。

---

## Finding 4 [HIGH] — `ensure_session` 缺少幂等语义，多进程并发创建可能重复建 Session

**严重程度**: HIGH

**位置**: §5 Session Slot, §10 公共接口

**问题**:

§5 定义 `ensure_session(scope, slot_key)`："如果 slot 尚不存在，Host 原子创建并绑定一个新 Session"。§5 也明确 "ensure_session 的幂等键是 (scope, slot_key)"。

但在多进程场景下：

1. 进程 A 调用 `ensure_session("wechat", "user_123")`，发现 slot 不存在，开始创建 Session。
2. 进程 B 同时调用 `ensure_session("wechat", "user_123")`，也发现 slot 不存在，也开始创建 Session。
3. 两个进程都 INSERT 新 Session 并尝试绑定 slot。

design.md 说 "原子创建并绑定"，但未定义原子性机制。如果 slot 绑定和 Session 创建不在同一事务中，或者没有唯一约束保护，可能创建两个 Session 并只有一个绑定到 slot（另一个成为孤儿）。

此外，§5 说 `ensure_session` 不需要 `client_request_id`，因为 "不同 client_request_id 不应改变复用结果"。但没有 `client_request_id` 意味着没有幂等键——如果调用在创建 Session 后、绑定 slot 前崩溃，重试时会创建第二个 Session。

**建议改法**: 在 §5 补充：

```
ensure_session 并发安全：
  - slot 表对 (scope, slot_key) 有唯一约束。
  - ensure_session 使用 INSERT OR IGNORE + SELECT 的事务模式：
    先尝试 INSERT slot 绑定；若唯一约束冲突，SELECT 现有绑定。
  - Session 创建与 slot 绑定在同一事务内完成。
  - 不需要 client_request_id —— slot 唯一约束保证幂等。
```

**是否阻塞 phase planning**: 不阻塞整体编排，但阻塞 Session API phase 的 plan 生成。

---

## Finding 5 [HIGH] — `scope_token` / cursor durable descriptor 的生命周期和 Host restart 恢复语义不完整

**严重程度**: HIGH

**位置**: §18 TruncationManager / fetch_more

**问题**:

§18 定义了 `cursor` 和 `scope_token` 的语义，以及 "durable descriptor 保存的是 handle metadata、scope binding、artifact ref、digest、offset / page / path、expiry / retention policy 和 access policy"。§18 也明确 "跨 Host restart、Attempt LOST、resume、steer 或 replay 后，fetch_more 必须依赖 Host attempt snapshot / Host-governed cursor descriptor / artifact ref 恢复读取权限"。

但 design.md 未定义：

1. **durable descriptor 的存储位置**：是在 EventLog 的 `payload_ref` 中？在独立的 truncation descriptor 表中？在 tool governance ledger 中？
2. **durable descriptor 的生命周期**：何时创建？何时过期？Run 终态后是否清理？Session close 后是否清理？
3. **Host restart 后的恢复**：recovery scan 遇到 truncation cursor ref 在 messages 中但 descriptor 尚未持久化的情况怎么办？（例如：ToolRuntime 截断了结果、cursor 已进入 messages，但 Host 在 EventLog append 前崩溃。）
4. **replay / steer 时的 descriptor 复用**：replay 默认复用已接受工具事实——如果这些工具事实包含 truncation cursor，descriptor 是否也复用？还是需要重新生成？

**建议改法**: 在 §18 补充：

```
durable descriptor 生命周期：
  - 创建：Host 在接受 TOOL_RESULT_ACCEPTED 时，若结果包含 truncation hint，
    同事务持久化 cursor descriptor。
  - 存储：独立 truncation_cursor 表，字段至少包含 cursor_id, session_id, run_id,
    tool_call_id, artifact_ref, offset, scope_binding, expires_at, status。
  - 恢复：recovery scan 不需要特殊处理 truncation cursor——descriptor 已在
    TOOL_RESULT_ACCEPTED 事务中持久化。若 descriptor 缺失（事务未提交），
    对应 truncation hint 也未进入 EventLog，fetch_more 自然不可用。
  - 复用：replay / steer 复用已接受工具事实时，同时复用其 cursor descriptor。
  - 过期：Run 终态后 descriptor 标记为 expired；expired descriptor 的
    fetch_more 返回工具错误。
```

**是否阻塞 phase planning**: 不阻塞整体编排，但阻塞 ToolRuntime / truncation phase 的 plan 生成。

---

## Finding 6 [HIGH] — `dispatch_record` 与 host 进程 liveness 的关系未定义

**严重程度**: HIGH

**位置**: §26 Host Lifecycle / Recovery, §26.1 已接受 Prompt 的恢复语义

**问题**:

§26.1 定义了 `attempt dispatch record` 的最小语义，并明确 "dispatch record 不是 lease，也不是 fencing token。它只帮助 Host 判断旧 Attempt 是否仍能被当前进程确认控制"。

但 "当前进程确认控制" 的判定机制完全未定义：

1. `host_instance_id` 如何生成？UUID？hostname + PID？启动时间戳？
2. "可确认的本进程 dispatch record" 的判定条件是什么？是 `host_instance_id` 匹配？还是需要额外的心跳或 lease？
3. 如果 Host 进程崩溃后重启，新进程的 `host_instance_id` 与旧 dispatch record 不匹配——这是预期行为，旧 Attempt 进入 `LOST`。但如果 Host 进程没有崩溃，只是 GC pause 或网络分区导致暂时无法确认呢？
4. §26 说 "若 active Attempt 没有可确认的本进程 dispatch record 与可用执行通道"——"可用执行通道" 指什么？LocalProxy 的进程是否存活？RemoteProxy 的连接是否正常？

**建议改法**: 在 §26 补充：

```
host 进程 liveness 判定：
  - host_instance_id 由 UUID 生成，在 Host 启动时创建，进程生命周期内不变。
  - recovery scan 时，当前进程只确认 host_instance_id 匹配的 dispatch record。
  - 不匹配的 dispatch record 对应的 Attempt 进入 LOST（非本进程创建，无法确认）。
  - 不引入心跳或 lease；liveness 判定完全基于 host_instance_id 匹配。
  - GC pause / 短暂网络分区不触发 recovery scan（recovery scan 只在 Host 启动时执行）。
  - "可用执行通道" 在第一版指 LocalProxy 可用或 RemoteProxy 连接正常；
    具体判定属于 WorkerProxy phase。
```

**是否阻塞 phase planning**: 不阻塞整体编排，但阻塞 recovery phase 的 plan 生成。

---

## Finding 7 [HIGH] — `cancel_run` 的 idempotency key 语义在 active Run 路径上不完整

**严重程度**: HIGH

**位置**: §10 公共接口, §21 Cancel

**问题**:

§10 定义 `CancelRunRequest` 包含 `client_request_id`，§10 接口语义说 "cancel_run 按 (run_id, client_request_id) 幂等"。

但 §21 的 cancel 路径在 active Run 上是两阶段的：

1. 初始：`Run -> CANCELLING`，append `CANCEL_REQUESTED`。
2. 收口：`Run -> CANCELLED / RECOVERING / LOST`，append terminal fact。

幂等语义在哪一阶段生效？

- 如果 `CANCEL_REQUESTED` 已 append（阶段 1 完成），同一 `(run_id, client_request_id)` 的重复 `cancel_run` 调用应该返回什么？是返回当前 RunSnapshot（可能仍是 `CANCELLING`）？还是直接返回幂等结果？
- 如果 Run 已从 `CANCELLING` 进入 `CANCELLED`（阶段 2 完成），重复调用应该返回 `CANCELLED` 的 RunSnapshot？还是 `idempotency_conflict`？
- `CANCEL_REQUESTED` 的 `idempotency_key` 字段是否就是 `client_request_id`？还是独立字段？

**建议改法**: 在 §21 补充：

```
cancel_run 幂等语义：
  - (run_id, client_request_id) 是幂等键。
  - CANCEL_REQUESTED 已 append 且 Run 仍在 CANCELLING 时，重复调用返回当前 RunSnapshot。
  - Run 已进入终态（CANCELLED / FAILED / SUCCEEDED / LOST）时，重复调用返回终态 RunSnapshot。
  - CANCEL_REQUESTED 的 idempotency_key 即 client_request_id。
```

**是否阻塞 phase planning**: 不阻塞整体编排，但阻塞 cancel governance phase 的 plan 生成。

---

## Finding 8 [HIGH] — `tool governance ledger` 在 §9 中列出但全文未定义

**严重程度**: HIGH

**位置**: §9 Durable Store

**问题**:

§9 的 durable store 列表包含 "tool governance ledger"，但 design.md 全文（包括 §17 ToolRuntime、§17.1 语义级重复工具调用治理）从未定义这个 ledger 的：

- schema（哪些字段？）
- 写入时机（哪些 EventLog event 触发写入？）
- 查询语义（谁读取？用于什么场景？）
- 与 EventLog 的一致性要求（同事务？最终一致？）

§17.1 的重复判定信号列表暗示需要一个快速查询的工具调用摘要索引，但没有明确这就是 tool governance ledger 的用途。

**建议改法**: 在 §17.1 或新增 §17.2 补充 tool governance ledger 定义（见 Finding 3 的建议改法）。如果 tool governance ledger 的用途与 Finding 3 的 session-scope 重复判定相同，合并定义；如果是不同用途，分别定义。

**是否阻塞 phase planning**: 不阻塞整体编排，但阻塞 ToolRuntime phase 的 plan 生成（plan agent 不知道 ledger 的存在意义）。

---

## Finding 9 [HIGH] — SQLite 多进程写并发的 contention 特征和 busy timeout 策略未定义

**严重程度**: HIGH

**位置**: §8 Admission 与多进程并发, §9 Durable Store

**问题**:

§8 说 "SQLite 应使用 WAL 与明确 busy timeout；具体参数由实现 phase 决定"。§9 说 "多进程一致性依赖 SQLite 事务、唯一约束、CAS-style state transition"。

但 design.md 未定义：

1. **连接模式**：每进程一个连接？每请求一个连接？连接池？SQLite 的 WAL 模式允许并发读，但写仍然是串行的。
2. **busy timeout 值**：多进程竞争写时，等待多久算超时？超时后返回什么错误？
3. **写事务重试**：`SQLITE_BUSY` 返回后是否重试？重试策略是什么（指数退避？固定间隔？）？
4. **关键写路径的 contention 特征**：
   - EventLog append：每次 Host event ingest 都写，高频。
   - Run / Attempt 状态更新：每次状态迁移都写，中频。
   - Queue promotion：active Run 终态时写，低频但关键。
   - Slot 绑定：`ensure_session` 时写，低频。

这些不是 "实现细节"——它们直接影响 Host 的吞吐量和延迟特征，以及多进程部署是否可行。

**建议改法**: 在 §9 补充：

```
SQLite 多进程写并发策略：
  - 每进程一个持久连接，进程生命周期内复用。
  - WAL 模式，busy timeout 默认 5000ms（可配置）。
  - SQLITE_BUSY 超时后返回 internal_error，调用方按需重试。
  - EventLog append 与状态更新在同一事务内，减少写事务次数。
  - 不引入写队列或写合并；SQLite WAL 的写串行性在第一版可接受。
  - 具体 busy timeout 值和重试策略由实现 phase 结合测试调整。
```

**是否阻塞 phase planning**: 不阻塞整体编排，但阻塞 durable store phase 的 plan 生成。

---

## Finding 10 [HIGH] — `RECOVERING` 退出缺少收敛保证和重试上限

**严重程度**: HIGH

**位置**: §6 Run 生命周期, §26 Host Lifecycle / Recovery

**问题**:

§6 定义了 `RECOVERING` 的三种退出：`RUNNING`（成功恢复）、`CANCELLED`（用户取消）、`LOST`（放弃恢复）。§8.1 状态迁移契约表也确认了这些路径。

但 design.md 未定义：

1. **恢复重试上限**：如果新 Attempt 创建后又失败（例如 EngineWorker 不可用），Run 是否再次进入 `RECOVERING`？有上限吗？
2. **收敛保证**：§6 说 "RECOVERING 的退出必须收敛"，但没有定义收敛条件。如果每次恢复尝试都失败，Run 可能在 `RECOVERING <-> FAILED` 或 `RECOVERING <-> LOST` 之间振荡。
3. **恢复延迟**：恢复尝试之间是否有退避间隔？还是立即重试？

**建议改法**: 在 §6 补充：

```
RECOVERING 收敛保证：
  - 恢复尝试次数上限由 Host policy 控制（默认 3 次）。
  - 超过上限后 Run 进入 LOST，不再尝试恢复。
  - 恢复尝试之间无强制退避间隔（第一版简化）。
  - 每次恢复尝试的 success / failure 记录在 EventLog（ATTEMPT_STARTED / ATTEMPT_FAILED）。
  - Host policy 可配置恢复上限和放弃条件。
```

**是否阻塞 phase planning**: 不阻塞整体编排，但阻塞 recovery phase 的 plan 生成。

---

## Finding 11 [HIGH] — `RunInputBuilder` 消费 `GUIDANCE_INSERTED` 的时机和条件未定义

**严重程度**: HIGH

**位置**: §22 RunInputBuilder, §12.3 Canonical Event Contract Matrix

**问题**:

§12.3 的 contract matrix 说 `GUIDANCE_INSERTED` "不直接改 terminal；影响下一 Attempt messages"，§22 说 `GUIDANCE_INSERTED` "如果影响后续 iteration" 应进入 messages。

但 "如果影响后续 iteration" 的判定条件是什么？

1. 所有 `GUIDANCE_INSERTED` 都进入 messages？还是由 policy 过滤？
2. `GUIDANCE_INSERTED` 在 messages 中的位置：在 tool result 之后？在下一轮 user input 之前？在 system message 中？
3. `GUIDANCE_INSERTED` 是否有生命周期：过了一定 iteration 数后是否不再注入？
4. steer / replay 时，旧 Attempt 的 `GUIDANCE_INSERTED` 是否进入新 Attempt 的 messages？

Round 1 DS review Finding 5 建议了 guidance 的 EventLog 路径（tool result accepted → guidance policy → append GUIDANCE_INSERTED → RunInputBuilder 消费），当前 design.md 已补了 event matrix 但未补消费路径。

**建议改法**: 在 §22 补充：

```
GUIDANCE_INSERTED 消费规则：
  - RunInputBuilder 在构造 messages 时，读取当前 Run 的所有 GUIDANCE_INSERTED facts。
  - 每条 guidance 在 messages 中紧跟其 trigger tool result 之后注入。
  - guidance 无 iteration 过期——一旦 append，后续 Attempt resume 时仍可见。
  - steer / replay 时，旧 Attempt 的 guidance 随 canonical facts 一起进入新 Attempt messages。
  - guidance 不进入 memory stable layer，只在当前 Run 的 messages 中可见。
```

**是否阻塞 phase planning**: 不阻塞整体编排，但阻塞 context governance phase 的 plan 生成。

---

## Finding 12 [MEDIUM] — `SESSION_CLOSED` 后的 `ensure_session` 行为未定义

**严重程度**: MEDIUM

**位置**: §4 Session 生命周期, §5 Session Slot

**问题**:

§4 定义 `CLOSED` 为只读："拒绝新 Run、follow-up、steer"。§5 定义 `ensure_session` 返回 slot 当前 Session。

如果 slot 绑定的 Session 已 `CLOSED`，`ensure_session` 应该：

A. 返回已 CLOSED 的 Session（调用方需要处理 CLOSED 状态）？
B. 自动创建新 Session 并重绑定 slot？
C. 拒绝并返回错误？

design.md 未定义此行为。

**建议改法**: 在 §5 补充：

```
ensure_session 遇到 CLOSED Session：
  - 返回已 CLOSED 的 SessionSnapshot。
  - 调用方如需新 Session，应显式调用 create_session(bind_slot=true)。
  - ensure_session 不自动创建新 Session 替代已 CLOSED 的 Session。
```

**是否阻塞 phase planning**: 不阻塞。

---

## Finding 13 [MEDIUM] — `FollowupSnapshot` 的字段定义缺失

**严重程度**: MEDIUM

**位置**: §10 Host 公共接口, §15 Read Model / Host Event Stream / Outbox

**问题**:

§10 定义 `submit_followup -> FollowupSnapshot`，§15 补充了 Snapshot 最小语义：

```
FollowupSnapshot: accepted input ref、behavior、target run / queued run、current cursor
```

但这个定义不够具体：

1. `target run / queued run` 是 `run_id` 还是 `RunSnapshot`？
2. `behavior` 是 `queue | steer` 的枚举？还是包含更多状态？
3. `current cursor` 是 `event_sequence` cursor？还是别的 cursor？
4. steer 模式下，返回的是旧 Run 的 snapshot 还是新 Attempt 的信息？

Round 1 MiMo review Finding 9 已指出此问题，当前 §15 的定义比 round 1 略有进步但仍不够结构化。

**建议改法**: 在 §15 补充：

```
FollowupSnapshot:
  accepted_input_ref: str        # USER_INPUT_ACCEPTED event ref
  behavior: queue | steer
  run_id: str                    # queue 时为新 queued run_id；steer 时为当前 active run_id
  event_sequence_cursor: int     # 当前 EventLog cursor
  mode: queued | steered         # 实际执行结果
```

**是否阻塞 phase planning**: 不阻塞。

---

## Assumptions Tested

| 假设 | 验证结果 |
|------|---------|
| design.md 的状态机覆盖了所有合理路径 | **部分通过**。Run/Attempt 状态机本身完整，但跨状态的竞态路径（cancel vs resume、cancel vs promotion）缺失（Finding 1, 2）。 |
| EventLog contract matrix 足以驱动 typed code | **通过**。§12.3 的矩阵覆盖了 29 个 event 的 scope、payload、状态副作用、resume/memory 角色和 audit 角色，plan agent 可以直接翻译为 dataclass。 |
| 多进程一致性完全由 SQLite 事务 + CAS 保证 | **部分通过**。CAS 事务语义已定义，但 busy timeout、连接模式、写重试策略未定义（Finding 9）。 |
| ToolRuntime 的远程部署语义与 Host-owned 定位一致 | **通过**。§17 明确 "治理配置和真源来自 Host attempt snapshot"，远端 ToolRuntime 只执行不治理。 |
| `fetch_more` 的普通 tool 约束可以防止特化路径 | **通过**。§18 的 6 条硬约束足够严格。 |
| recovery scan 可以正确处理所有 active 状态 | **部分通过**。scan 对 QUEUED / WAITING / RUNNING / CANCELLING 的处理已定义，但 `RECOVERING` 的收敛保证不足（Finding 10）。 |
| canonical event 列表足够第一版使用 | **通过**。29 个 event 类型覆盖了 session、run、attempt、tool、context compaction、provider error 等所有治理面。 |
| Observer / Sink 的 checkpoint 机制足够可靠 | **通过**。§13 的 checkpoint + poll + 幂等消费语义清晰。 |
| RunInputBuilder 的 messages 构造顺序已定义 | **通过**。§22 的 5 步构造顺序清晰。 |
| `LOST` 与 `FAILED` 的区分在实现中可操作 | **通过**。§6 明确定义了两者的语义差异，§26 定义了 `LOST` 的触发条件。 |

---

## 与 Round 1 Findings 的交叉验证

| Round 1 Finding | 当前状态 | Draft 2 新发现 |
|---|---|---|
| EventLog sequence 语义 | **已解决**。§12 选定全局单调 `event_sequence`。 | 无。 |
| Host handle 定义 | **已解决**。§9.1 补了 Composition Root。 | 无。 |
| RECOVERING 退出转移 | **已部分解决**。§6 补了三种退出，但缺少重试上限（Finding 10）。 | Finding 10。 |
| Canonical event contract matrix | **已解决**。§12.3 补了完整矩阵。 | 无。 |
| Steer-terminal 竞态 | **已解决**。§11 补了竞态规则。 | 无。 |
| Durable queue promotion | **已部分解决**。§8 补了 FIFO 和 CAS，但未覆盖 promotion vs cancel 竞态（Finding 2）。 | Finding 2。 |
| Wait record 恢复 | **已解决**。§26 补了 poll/callback/manual 恢复语义。 | 无。 |
| TruncationManager 远程归属 | **已解决**。§18 补了 durable descriptor 语义。 | Finding 5（生命周期不完整）。 |
| Memory snapshot/checkpoint 一致性 | **已解决**。§23 补了同事务提交约束。 | 无。 |

---

## Readiness Verdict

**当前 design.md 可以驱动 phase planning，但有 3 个 blocking findings 需要先收束。**

理由：

1. **架构层面充分**：四对象模型（Session/Run/Attempt/EventLog）、状态机、admission、EventLog append-only 约束、projection 真源关系、remote boundary、ToolRuntime Engine 隔离——这些核心架构决策已稳定，不会因 blocking findings 而改变。
2. **Blocking findings 是路径补全，不是架构变更**：3 个 blocking findings 都是 "已定义的路径在特定竞态场景下缺少收束"，修正方式是在现有架构框架内补充规则，不需要重新设计。
3. **High findings 是 phase plan 的前置条件**：8 个 high findings 分别阻塞特定 phase 的 plan 生成，可以在进入对应 phase 前通过更新 design.md 解决，不阻塞整体 phase 编排。

**建议**：

1. 先修正 3 个 blocking findings（Finding 1: cancel vs resume, Finding 2: cancel vs promotion, Finding 3: tool governance ledger scope）。
2. 将 8 个 high findings 记录为 implementation-control.md 追踪区的 working assumption，按 phase 归属分配。
3. 修正后 design.md 可作为 plan 真源进入 phase 编排。
