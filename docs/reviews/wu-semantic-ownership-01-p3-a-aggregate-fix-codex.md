# WU-SEMANTIC-OWNERSHIP-01 P3-A aggregate fix — AgentCodex

## Gate / scope

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A`。
- Gate：controller accepted aggregate findings fix。
- Accepted finding 真源：`docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-deepreview-controller-adjudication.md`。
- Fix scope：只处理 `P3-A-AGG-F01` 与 `P3-A-AGG-F02`。
- Non-goals：不处理 deferred `P3-A-AGG-F03`，不做 aggregate re-review，不修改 control doc，不 commit、push 或创建 PR。
- Decision：两项 accepted finding 均已修复；等待 controller aggregate re-review。

## 第一性原理与 owner boundary

Run status 集合的 owner 链为：

```text
RunStatus + durable row terminal rules
  -> TERMINAL_RUN_STATUSES
  -> NON_TERMINAL_RUN_STATUSES
  -> START_BLOCKING_RUN_STATUSES = NON_TERMINAL_RUN_STATUSES - {QUEUED}
  -> serialized_run_status_values（按 RunStatus 定义顺序稳定序列化）
  -> run_status_in_clause（生成 placeholder 与 params）
```

设计与代码证据共同确认五处 SQL 的集合语义均等于 `START_BLOCKING_RUN_STATUSES`：

- `ACCEPTED` 表示尚未启动、但已经占据 start-blocking 顺序的 Run；`RUNNING`、`WAITING`、`CANCELLING`、`RECOVERING` 是 active lifecycle；`QUEUED` 不占 active slot，也不阻塞更早 Run 的启动。
- `_read_active_run_id` 为 `SessionSnapshot.active_run_id` 投影最早的 start-blocking Run，与 `read_active_run_for_session` 是同一 durable read 语义。
- `promote_queued_run_row` 与 `start_unstarted_run_row` 在目标 Run 进入 `RUNNING` 前，必须排除同 Session 的其它 start-blocking Run。
- `resume_waiting_run_row` 与 `start_recovering_run_row` 通过 `active_run.run_id <> target_run_id` 排除目标自身；它们同样必须排除其它 start-blocking Run，不能使用缩小或独立复制的集合。
- 未发现任何一条 guard 需要不同 status set 的直接设计或代码证据，因此可以统一消费现有 owner helper；无需新增 helper、模块常量或兼容 wrapper。

## Finding fix status

### P3-A-AGG-F01 — 已修复

Root cause：S2 只迁移了公开 `read_active_run_for_session`，遗漏了 `SessionSnapshot.active_run_id` 使用的 `_read_active_run_id`。私有 projection 因而复制了五个 placeholder 与五个 status 参数，存在与公开 read 漂移的风险。

修复：

- `_read_active_run_id` 在查询执行前直接调用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`。
- SQL 使用 owner 生成的 `status_clause`；参数使用 `(session_id, *status_params)`，placeholder 数量、参数数量和顺序全部由 owner helper 决定。
- 没有让 private read 透传 public read，也没有新增仅为兼容或测试服务的 seam。

测试：

- `test_session_snapshot_active_run_matches_owner_derived_public_read` 使用真实 SQLite durable rows，并精确把 owner set 替换为仅 `QUEUED`。
- 公开 `read_active_run_for_session` 与 `session_snapshot_from_rows(...).active_run_id` 对同一 Session 同时返回该 queued Run；旧硬编码实现会返回 `None`，因此该测试能证明两条消费者动态从 owner material 派生。
- 既有 `test_run_status_in_clause_placeholder_count_matches_params` 与 serialization 测试继续证明 placeholder 数量等于参数数量，frozenset 参数顺序由 `serialized_run_status_values` 按 `RunStatus` 定义顺序决定。

最终状态：**已修复**。

### P3-A-AGG-F02 — 已修复

Root cause：四个底层 start transition 把 active-run CAS guard 错当成各自局部 SQL 细节，分别复制了相同五状态 placeholder/params；read/admission owner 已统一，但 write guards 尚未进入同一传播链。

修复：

- `promote_queued_run_row`、`start_unstarted_run_row`、`resume_waiting_run_row`、`start_recovering_run_row` 均直接调用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`。
- 四条 `NOT EXISTS` 使用同一个 owner-generated clause，并以 `*status_params` 在原有 target/session/CAS 参数之后稳定展开。
- 未复制 tuple、模块常量、状态字符串或兼容 wrapper；既有目标状态、current Attempt、terminal ref 与 CAS 条件保持不变。

测试：

- `test_start_transition_guards_derive_blocking_material_from_owner_set` 参数化覆盖四条 transition。
- 测试使用真实 SQLite durable rows，把 owner set 精确替换为仅 `QUEUED`，为每条 transition 放置一个同 Session queued sibling。四条 guard 均返回 `CAS_LOST`；旧五状态硬编码不会把 queued sibling 作为 blocker，因此测试能证明 SQL status material 动态来自 owner set。
- 删除 synthetic blocker 后，同一 transition 返回 `UPDATED`，目标 Run 进入 `RUNNING`，同时证明 owner 化没有改变无冲突 happy path。
- 原有 transition、public API、recovery、active cancel、scheduler 与本地 execution 回归继续覆盖生产 transaction/event/CAS 路径。

最终状态：**已修复**。

## Run status propagation audit

### 1. 产生与校验

```text
RunStatus enum + durable terminal row rules
  -> TERMINAL_RUN_STATUSES
  -> NON_TERMINAL_RUN_STATUSES
  -> START_BLOCKING_RUN_STATUSES
```

`test_start_blocking_run_statuses_are_explicit_current_assumption` 同时锁定当前精确成员和“所有非终态减 `QUEUED`”派生关系；新增非终态状态时必须显式审查 start-blocking 假设。

### 2. SQL material

```text
START_BLOCKING_RUN_STATUSES
  -> serialized_run_status_values
       frozenset 按 RunStatus 定义顺序序列化
  -> run_status_in_clause
       placeholder 数量 == params 数量
```

五个本次修复的消费者都在执行时调用该 helper，没有缓存第二份 clause、params 或 status tuple。

### 3. Read / snapshot projection

```text
owner-generated clause/params
  -> read_active_run_for_session
  -> _read_active_run_id
  -> session_snapshot_from_rows
  -> SessionSnapshot.active_run_id
  -> public Host get_session / list-session consumers
```

公开 durable read 与 snapshot private projection 对同一 Session 使用相同 owner material、相同 accepted sequence / run id 排序，不再分别维护状态集合。该事实是 Host lifecycle projection，不进入 LLM-facing prompt；没有新增或改写 LLM-facing 文本。

### 4. Write CAS guards

```text
owner-generated clause/params
  -> promote_queued_run_row NOT EXISTS guard
  -> start_unstarted_run_row NOT EXISTS guard
  -> resume_waiting_run_row NOT EXISTS guard
  -> start_recovering_run_row NOT EXISTS guard
  -> target Run CAS to RUNNING
```

生产调用方仍在各自 durable transition transaction 中写入相应 `RUN_STARTED` / `ATTEMPT_STARTED` canonical facts、Attempt/dispatch rows与 Run status index。此次修改只统一 guard 的 status material，不改变 canonical event type、payload、event ordering、Attempt identity 或 first-committer-wins 行为。

### 5. 持久化、审计与可见输出一致性

- 持久化真源仍是同一 transaction 中的 EventLog canonical facts 与 `host_runs.status` index；guard 不产生第二份业务事实。
- recovery、scheduler、cancel、read model、outbox、memory、audit 与 diagnostic 继续消费既有 committed EventLog/status truth；本 fix 没有新增下游重建或展示层特例。
- 用户可见 `SessionSnapshot.active_run_id` 与 durable public active read 已由行为测试证明同源；write CAS guards 使用同一 owner 集合后，不会再出现“read 判定阻塞、write guard 却允许启动”的集合漂移。
- 没有 LLM-facing schema、prompt、memory material 或 tool text 变更。

Audit conclusion：从 owner set、稳定 SQL material、read/snapshot projection 到四条 write CAS guard 的传播链已统一；未发现显示、持久化、trace、memory 或 LLM-facing 输出从不同真源重建该 status 事实。

## Validation

```text
source .venv/bin/activate && pytest \
  tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_public_run_api.py \
  tests/host/test_recovery_dispatch.py \
  tests/host/test_active_cancel_dispatch.py -q
144 passed in 1.52s
```

```text
source .venv/bin/activate && pytest \
  tests/host/test_lifecycle_events.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_public_cancel_session_runs.py \
  tests/host/test_phase5_local_execution_integration.py \
  tests/host/test_dispatch_scheduler.py -q
193 passed in 2.90s
```

```text
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

```text
git diff --check
clean
```

Source scans：

- `state.py` 中 `status IN (?, ?, ?, ?, ?)`：0 匹配。
- `_read_active_run_id` 与四条目标 guard：均匹配 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)` 及生成的 `status_clause`。
- terminal `_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)` producer：0 匹配。
- synthetic `EngineEvent(` / `EngineEventType.RUN_FAILED` / `RunFailedData(`：0 匹配。
- legacy mixed `_TerminalPlan`：0 匹配。
- Engine ingest nullable `terminal_event_id is None/is not None` status proxy：0 匹配。
- command direct-cancel 对 `worker_accepted_at` / `worker_accept_event_id` / `worker_accept_event_sequence` 的直接读取：0 匹配。

## README decision

- `dayu/host/README.md`：不更新。已读取 `Agent更新约束【必须遵守】` 并核对当前内容；本 fix 不改变 Host 公共契约、架构边界、稳定状态机或开发接口，只让既有 start-blocking owner 在内部 read/write SQL 中完整传播。README 已说明 admission/active slot 由 durable Run 状态决定，无需记录文件级 helper 迁移。
- `tests/README.md`：不更新。已读取 `README 更新边界`；本 fix 只在现有 `tests/host/` durable state/transition 测试层内补充行为覆盖，没有新增测试层级、运行方式或维护规则。

## Changed files

- `dayu/host/durable/state.py`
- `tests/host/test_state_schema.py`
- `docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-fix-codex.md`

未修改 `docs/host/issues-implementation-control.md`、既有 aggregate review/adjudication artifacts、`docs/cli_ci.md` 或 P3-B/P3-J 代码。

## Residual owners / risks

| Residual | Classification | Owner / destination |
|---|---|---|
| 非 terminal EventLog taxonomy 仍分散 | deferred-with-owner，非本 fix finding | `WU-SEMANTIC-OWNERSHIP-01 P3-J` |
| P3-B final answer / outbox continuity | later approved work unit，未受本 fix 影响 | P3-B owner |
| Engine-origin 与 Host-lifecycle 跨进程 terminal stress | existing uncovered area，未由本 fix 扩大 | production stress / EventLog hardening owner |

没有未分类 residual risk；两项 controller accepted finding 均为 **已修复**。

## Completion

- `P3-A-AGG-F01`：**已修复**。
- `P3-A-AGG-F02`：**已修复**。
- Blocking open question：none。
- Artifact：`docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-fix-codex.md`。
- Next entry point：controller aggregate re-review。
