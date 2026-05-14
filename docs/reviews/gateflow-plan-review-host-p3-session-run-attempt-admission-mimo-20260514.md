# Host Phase 3 Plan Review — Session / Run / Attempt Admission

- **review gate name**: Phase 3 plan review
- **reviewed target**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **reviewer**: AgentMiMo
- **artifact path**: `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-mimo-20260514.md`
- **conclusion**: plan 基本 handoff-ready，但存在 1 个 high finding 和 2 个 medium finding 需要 plan fix。

## 对照文档

- `docs/host/design.md` §5 Session 生命周期、§6 Session Slot、§7 Run 生命周期、§8 Attempt 生命周期、§9 Admission 与多进程并发、§9.1 状态迁移契约、§10 Durable Store、§11 Host 公共接口、§12 Follow-up 与 Steer、§22 Cancel、§27 Host Lifecycle / Recovery
- `docs/host/implementation-control.md` Phase 3 条目、强制约束、追踪区
- `docs/reviews/gateflow-phase-design-re-review-host-p3-controller-adjudication-20260514.md`
- `docs/reviews/gateflow-phase-design-additional-re-review-host-p3-f1-mimo-20260514.md`
- 当前代码事实：`dayu/host/durable/schema.py`（HOST_SCHEMA_VERSION=1，Phase 2 foundation tables only）、`dayu/host/api.py`（Phase 1 public types）、`dayu/host/durable/event_log.py`、`idempotency.py`、`transaction.py`

## 总体评估

plan 结构完整：6 个 slices 有明确 objective、allowed files、dependencies、exact allowed changes、implementation instructions、non-goals、tests、completion signal 和 stop condition。schema contract、canonical event types、idempotency contract、CAS preconditions、data flow 和 error semantics 均有具体定义。non-goals 正确排除了 Engine dispatch、scheduler、lane、WorkerProxy、EngineEvent ingest、ToolRuntime、wait、steer、retry/replay、context compaction 和 recovery。

以下 findings 需要 plan fix 后才能进入 implementation。

## Findings

### F1-已修复-高-submit_followup(queue) 无 active Run 时 data flow 缺少 RUN_STARTED / ATTEMPT_STARTED 事件追加

- **Plan位置**: §5 Implementation Decisions > Data Flow > `submit_followup(queue)` (行 556-558)
- **问题类型**: 契约缺失 / 不可直接实施
- **计划当前写法**:

```text
submit_followup(queue):
validate request/context, behavior == QUEUE, Session OPEN
-> same admission transaction as start_run, with scope_kind submit_followup_queue
-> active exists: create QUEUED Run
-> no active: create RUNNING Run + STARTING Attempt + pending dispatch record
```

- **为什么有问题**: data flow 的 "no active" 路径只写了 "create RUNNING Run + STARTING Attempt + pending dispatch record"，没有写追加 `RUN_STARTED(start_reason=initial)` 和 `ATTEMPT_STARTED` 事件。按 `docs/host/design.md` §9.1 状态迁移表，`submit_followup(queue)` 且无 active Run 时必须追加 `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_STARTED(start_reason=initial)`、`ATTEMPT_STARTED`。implementation agent 如果只按 data flow 写代码，会遗漏两个 canonical event append，导致 Run 进入 `RUNNING` 但 EventLog 缺少 `RUN_STARTED` 和 `ATTEMPT_STARTED` fact，破坏 EventLog 作为状态真源的完整性。
- **直接证据**: `docs/host/design.md` 行 559: `submit_followup(queue)` 且无 active Run 的 canonical facts 列表为 `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_STARTED(start_reason=initial)`、`ATTEMPT_STARTED`。plan data flow 只提及创建行对象，未提及事件追加。
- **影响**: implementation agent 可能实现一个不追加必要 canonical facts 的 submit_followup 路径，导致 EventLog 与 state indexes 不一致。
- **建议改法和验证点**: 在 data flow 的 "no active" 路径补充事件追加步骤，使其与 `start_run` 的 "no active Run" 路径一致：`append USER_INPUT_ACCEPTED -> append RUN_ACCEPTED -> append RUN_STARTED(start_reason=initial) -> insert host_runs RUNNING -> append ATTEMPT_STARTED -> insert host_attempts STARTING -> insert dispatch record pending -> update run.current_attempt_id`。验证点：测试断言 follow-up 创建 running Run 时 EventLog 包含完整的 4 个 canonical facts。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F2-已修复-中-submit_followup_queue 幂等契约 first event ref 不完整

- **Plan位置**: §4 Contract / Schema / State-machine / Public-interface Changes > Idempotency Contract > per-operation table (行 402)
- **问题类型**: 契约缺失
- **计划当前写法**:

```text
| submit_followup_queue | submit_followup_queue | session_id | client_request_id |
input_digest, behavior=queue, caller_semantic_digest | run | run_id | USER_INPUT_ACCEPTED |
```

- **为什么有问题**: `first event ref` 列只写了 `USER_INPUT_ACCEPTED`，但 `submit_followup(queue)` 有两种路径：有 active Run 时创建 QUEUED Run（first event 是 `USER_INPUT_ACCEPTED`），无 active Run 时创建 RUNNING Run（first event 也是 `USER_INPUT_ACCEPTED`）。两种路径的 first event ref 都是 `USER_INPUT_ACCEPTED`，这本身正确。但作为对比，`start_run` 的契约明确区分了 "new Run is created" 和 "queue_policy=attach_active returns already active Run" 两种情况的 first event ref。`submit_followup_queue` 缺少类似的 disambiguation：当无 active Run 时，`submit_followup(queue)` 创建的 RUNNING Run 也会有 `RUN_STARTED` 和 `ATTEMPT_STARTED` 事件，但这些不在 first event ref 列中体现。更关键的是，如果 implementation agent 只看到 `USER_INPUT_ACCEPTED` 作为 first event ref，可能误以为 `submit_followup(queue)` 总是创建 QUEUED Run。
- **直接证据**: `docs/host/design.md` 行 558-559 明确区分了 `submit_followup(queue)` 有 active Run（QUEUED）和无 active Run（RUNNING + STARTING Attempt）两种路径。plan idempotency table 没有体现这种区分。
- **影响**: implementation agent 可能误解 `submit_followup(queue)` 只创建 QUEUED Run，遗漏无 active Run 时创建 RUNNING Run 的路径。
- **建议改法和验证点**: 在 idempotency table 中为 `submit_followup_queue` 添加注释或拆分两行，说明：(1) 有 active Run 时创建 QUEUED Run，first event ref 是 `USER_INPUT_ACCEPTED`；(2) 无 active Run 时创建 RUNNING Run，first event ref 是 `USER_INPUT_ACCEPTED`（因为 `USER_INPUT_ACCEPTED` 是两种路径共有的第一个事件）。或者参考 `start_run` 的格式，在 first event ref 列添加 "when active exists: USER_INPUT_ACCEPTED; when no active: USER_INPUT_ACCEPTED" 的 disambiguation。验证点：两种路径的 idempotency 重试都返回同一个 Run。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F3-已修复-中-follow-up Run 的 execution_target 来源未明确

- **Plan位置**: §5 Implementation Decisions > Data Flow > `submit_followup(queue)` (行 556-558)；§4 Schema Contract > `host_runs` (行 216)
- **问题类型**: 契约缺失 / 不可直接实施
- **计划当前写法**:

data flow 中 `submit_followup(queue)` 没有提及 `execution_target` 来源。schema contract 中 `host_runs.execution_target TEXT NOT NULL`（行 216）。idempotency contract 中 `submit_followup_queue` 的 semantic digest 不包含 `execution_target`（行 402）。

- **为什么有问题**: `SubmitFollowupRequest`（`dayu/host/api.py` 行 674-727）不包含 `execution_target` 字段，但 `host_runs` 表的 `execution_target` 列是 `NOT NULL`。`start_run` 的 `execution_target` 来自 `StartRunRequest.execution_target`，但 `submit_followup` 没有这个输入。plan 没有说明 follow-up Run 的 `execution_target` 从何而来。implementation agent 必须自行决定：从 active Run 复制？从 Session metadata 推断？从 Host policy 默认值？这违反了 plan 的 "不留 implementation choice" 承诺。
- **直接证据**: `dayu/host/api.py` 行 674-727 定义 `SubmitFollowupRequest` 无 `execution_target`。`docs/host/design.md` 行 1064: "当前 Session 没有 active Run 时，follow-up 创建并启动新 Run；execution target 通过 Host policy 归一化并持久化"。plan 没有将 "Host policy 归一化" 转化为具体实现指令。
- **影响**: implementation agent 必须自行决定 `execution_target` 来源，可能导致不同 slice 或不同 agent 做出不一致的选择。
- **建议改法和验证点**: 在 plan 的 `submit_followup(queue)` data flow 或 implementation instructions 中明确 `execution_target` 解析规则。建议：(1) 有 active Run 时，从 active Run 的 `execution_target` 复制；(2) 无 active Run 时，使用 Host policy 默认值或 Session metadata 中的 `execution_target`。同时在 idempotency semantic digest 中说明 `execution_target` 不是 digest 字段（因为它由 policy 决定，不是调用方输入）。验证点：follow-up Run 的 `execution_target` 与 active Run 一致或符合 policy 默认值。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## 无 Finding 的确认项

以下方面经审查确认无问题：

1. **partial unique active Run invariant**: plan 明确使用 `CREATE UNIQUE INDEX host_runs_one_active_per_session ON host_runs(session_id) WHERE status IN ('running','waiting','cancelling','recovering')`，与 `docs/host/design.md` 行 668 一致。stop condition 要求如果 SQLite partial unique index 不满足约束，必须回到 design discussion。
2. **canonical event types / payload expectations**: 16 个 Phase 3 owned event types 均有具体 scope 和 payload 字段定义，与 design §9.1 一致。`FOLLOWUP_QUEUED` 正确排除。
3. **idempotency scope per operation**: 每个 operation 的 `scope_kind`、`scope_id`、`idempotency_key`、semantic digest fields、`result_kind`、`result_ref` 和 first event ref 均已定义。`ensure_session` 正确使用 slot PK 而非 idempotency_records。
4. **CAS preconditions / rowcount=0 handling**: §4 明确定义了每个 transition 的 CAS 条件更新和 `rowcount=0` 后的 loser handling 行为。
5. **promotion FIFO**: queued Run 按 `accepted_event_sequence ASC, run_id ASC` 排序，与 design §9 一致。
6. **cancel semantics**: cancel queued 不创建 Attempt，cancel pre-dispatch starting 标记 dispatch record cancelled 且不通知 WorkerProxy，与 design §22 一致。
7. **non-goals**: 正确排除了 Engine dispatch、scheduler、lane、WorkerProxy、LocalProxy、RemoteProxy、EngineEvent ingest、ToolRuntime、wait、resolve_wait、steer、retry/replay、context compaction、recovery。
8. **slice ordering / file ownership / dependencies**: P3-S1 (schema + codecs) → P3-S2 (session lifecycle) → P3-S3 (run/attempt transitions) → P3-S4 (admission + queue) → P3-S5 (cancel + terminal closeout) → P3-S6 (multiprocess + docs)。依赖链正确。
9. **schema version bump**: `HOST_SCHEMA_VERSION` 从 1 到 2，fresh bootstrap only，无兼容迁移。
10. **terminal closeout synthetic marker**: `reason='phase3_internal_closeout'` 用于测试 helper，不会被误认为 EngineEvent ingest。
11. **after-commit promotion**: 必须在新事务中运行，不能假设前一事务的 snapshot 仍然有效。
12. **HostPhase3WakeupPort**: no-op default，`notify_pending_dispatch` 不 dispatch，只创建 Phase 5 attachment point。
13. **dispatch record schema**: Phase 3 只允许 `pending` / `cancelled`，CHECK constraint 阻止其它状态。
14. **`host_runs` 不加 `UNIQUE(session_id, client_request_id)`**: plan 正确说明 idempotency 由 `idempotency_records` 拥有，不在 `host_runs` 加表级唯一索引。

## Open Questions / Residual Risk

1. **`SessionSnapshot` 是否足够表达 Phase 3 internal service 返回**: plan §5 说 "若现有 public dataclass 不足以表达 Phase 3 internal service 输入，必须优先新增 Host 内部 dataclass"。当前 `SessionSnapshot` 包含 `active_run_id` 和 `queued_run_ids`，应足够。但如果 implementation 发现需要更多字段（如 slot binding event ref），必须新增内部类型。
2. **`FollowupSnapshot` 是否足够表达 `submit_followup(queue)` 返回**: 当前 `FollowupSnapshot` 包含 `queued_run_id`（queue 时）或 `target_run_id`（steer 时）。但 `submit_followup(queue)` 无 active Run 时创建的是 RUNNING Run 而非 QUEUED Run，此时 `FollowupSnapshot.queued_run_id` 语义不匹配。implementation agent 可能需要新增内部 result 类型或复用 `RunAdmissionResult`。
3. **multiprocess test flakiness**: plan P3-S6 正确要求 "correctness over performance" 和 "assertions must inspect durable rows and EventLog sequences after processes join"。但如果 SQLite busy timeout 配置不当，测试可能 flaky。plan 已有 stop condition: "if tests are flaky due to SQLite busy policy rather than state bug, tune test storage policy within existing options"。
4. **`execution_target` policy 默认值**: 即使 F3 修复后，"Host policy 默认值" 本身可能需要一个具体的 typed default 或 injection point。这属于 implementation 细节，但 plan 应至少指定方向。

## Gate Decision

- **findings**: 3
- **blocking findings**: 1 (F1 high)
- **建议 plan fix**: 是。F1 必须修复后才能进入 implementation；F2、F3 建议一并修复。
- **controller decision status**: 每个 finding 均为 `pending-controller-decision`。
