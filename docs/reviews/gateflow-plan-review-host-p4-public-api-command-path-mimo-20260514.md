# Gateflow Plan Review - Host Phase 4 Public API Command Path - AgentMiMo

## 结论

accepted

无 blocking finding。Plan handoff-ready 且 code-generation-ready；implementation agent 可按本文档 4 个 slice 直接实施，无需重新设计 public API、错误结构、EventLog cursor、cancel 子集语义或 deferred function 行为。

## 复核范围

- `docs/host/phase4-public-api-command-path-plan.md`：全部 9 节
- `docs/host/design.md`：§10.1 Host Handle / Composition Root、§11 Host 公共接口、§12 Follow-up 与 Steer、§13 EventLog cursor contract、§22 Cancel
- `docs/host/implementation-control.md`：Phase 4 条目、追踪区当前状态
- `docs/reviews/gateflow-phase-design-re-review-host-p4-mimo-20260514.md`
- `docs/reviews/gateflow-phase-design-fix-host-p4-codex-20260514.md`
- `docs/reviews/gateflow-phase-design-re-review-host-p4-controller-adjudication-20260514.md`
- 当前代码：`dayu/host/api.py`、`dayu/host/admission.py`、`dayu/host/durable/session_lifecycle.py`、`dayu/host/durable/state.py`、`dayu/host/durable/event_log.py`、`dayu/host/README.md`

## Review 重点逐项评估

### 1. Plan handoff-ready / code-generation-ready

**结论：是。**

Plan 结构完整：Goal / Motivation / Non-goals / Direct Evidence（§1）→ Affected Files / Modules（§2）→ Public Contract Changes（§3）→ Behavior Matrix（§4）→ Implementation Slices（§5）→ Cross-slice Invariants（§6）→ Documentation Decision（§7）→ Plan Risks / Open Questions（§8）→ Completion Report Format（§9）。

每个 slice 包含：Objective、Allowed files/modules、Exact changes、State transitions、Non-goals、Tests、Validation commands、Stop conditions。Implementation agent 可直接据此编码，无需重新设计任何边界决策。

Plan 明确声明"implementation agent 只能按本文档指定的 slice、文件边界、公共契约和状态迁移实施；不得重新设计"（第 9 行），handoff 语义清晰。

### 2. Phase 4 behavior matrix 对齐

**结论：严格对齐。**

逐函数核对：

| 函数 / 路径 | plan §4 | design.md §11 | control.md | 一致性 |
|---|---|---|---|---|
| `ensure_session` | 完整实现 | 完整实现 | 完整实现 | ✓ |
| `create_session` | 完整实现 | 完整实现 | 完整实现 | ✓ |
| `get_session` | 完整实现 | 完整实现 | 完整实现 | ✓ |
| `close_session` | 完整实现 | 完整实现 | 完整实现 | ✓ |
| `start_run` | 完整实现 | 完整实现 | 完整实现 | ✓ |
| `submit_followup(queue)` | 完整实现 | 完整实现 | 完整实现 | ✓ |
| `get_run` | 完整实现 | 完整实现 | 完整实现 | ✓ |
| `stream_run_events` | 完整实现 | 完整实现 | 完整实现 | ✓ |
| `cancel_run` queued/pre-dispatch | 完整实现 | 完整实现 | 完整实现 | ✓ |
| `cancel_session_runs` | 子集 queued/pre-dispatch | 子集 queued/pre-dispatch | 子集 queued/pre-dispatch | ✓ |
| `submit_followup(steer)` | UNSUPPORTED_OPERATION | deferred | deferred | ✓ |
| `retry_run` | UNSUPPORTED_OPERATION | deferred | deferred | ✓ |
| `replay_run` | UNSUPPORTED_OPERATION | deferred | deferred | ✓ |
| `resolve_wait` | UNSUPPORTED_OPERATION | deferred | deferred | ✓ |
| `purge_session` | UNSUPPORTED_OPERATION | deferred | deferred | ✓ |
| active dispatch cancel | deferred (no fake) | deferred | deferred | ✓ |
| wait cancel | deferred | deferred | deferred | ✓ |
| recovery cancel | deferred | deferred | deferred | ✓ |

`cancel_session_runs` 后续 owner 追踪明确：Phase 5 owns dispatching / active worker、Phase 7 owns `WAITING`、Phase 11 owns `RECOVERING`（plan §4、§8 non-blocking risks 第 4 项）。Plan 不允许把 Phase 4 子集写成最终语义（plan §1 non-goals、§5-S3 non-goals、§5-S3 stop conditions）。

### 3. Public contract changes 具体性

**结论：足够具体。**

逐项核对：

| 契约要素 | plan §3 表达 | 与 design.md §11 对齐 |
|---|---|---|
| `FollowupSnapshot` | §3 详细列出 7 个字段 + 5 条 validation rules | ✓ 与 design.md:1055 `accepted_run_id` + `accepted_run_status` + 可选 `queued_run_id?` + 可选 `target_run_id?` 一致 |
| `HostApiErrorCode.UNSUPPORTED_OPERATION` | §3 明确新增枚举值 | ✓ 与 design.md:1066, 1075 一致 |
| `HostApiError.detail` | §3 定义 `SteerConflictDetail` frozen dataclass + `HostApiErrorDetail` type alias + 禁止 god bag | ✓ 与 design.md:1077-1087 一致 |
| `SteerConflictDetail` | §3 列出 4 个字段：`target_run_id`、`target_run_status?`、`current_active_run_id?`、`current_active_run_status?` | ✓ 与 design.md:1080-1084 一致 |
| stream constants | §3 定义 `HOST_EVENT_STREAM_DEFAULT_LIMIT=100`、`HOST_EVENT_STREAM_MAX_LIMIT=1000` | ✓ design.md:1092 要求公共常量暴露，具体值属于 plan agent 可决定的实现细节 |
| `HostCommandHandleOptions` | §3 列出 10 个显式 typed fields + default 常量约束 | ✓ 与 design.md §10.1 composition root 运行参数约束一致 |

### 4. stream_run_events cursor plan

**结论：符合 EventLog global cursor truth，避免 projection truth。**

Plan §3 `stream_run_events` 语义：
- `cursor.event_sequence` 是最后消费的全局 EventLog sequence ✓
- `limit=None` 使用 `HOST_EVENT_STREAM_DEFAULT_LIMIT` ✓
- 扫描 `event_sequence > cursor.event_sequence` 的 EventLog rows ✓
- 过滤 `row.run_id == run_id` ✓
- `next_cursor` 是扫描过的最大全局 `event_sequence` ✓
- 过滤后空结果仍前进 `next_cursor`（扫描推进时）✓
- 不使用 projection checkpoint、session-local cursor、client sequence 或内存订阅状态 ✓

与 design.md:1089-1097 完全一致。Plan §5-S4 stop conditions 明确："Stop if `stream_run_events` needs projection checkpoint, memory state, outbox state or in-memory subscription position to satisfy tests."

### 5. Slices 粗细与 file ownership

**结论：切分合理，file ownership 清楚。**

4 个 slice 沿类型冻结边界（S1）→ handle/session 闭环（S2）→ run/admission/cancel 闭环（S3）→ read/stream/deferred 闭环（S4）切分。每个 slice 有明确的 allowed files 列表，不跨无关模块。

- S1 只改 `api.py`、`__init__.py`、tests；不触碰 durable store。
- S2 新建 `command.py`、`read_api.py`，改 `transaction.py`（read tx）和 `state.py`（snapshot helpers）。
- S3 改 `command.py`、`admission.py`、`state.py`，新建 tests。
- S4 改 `read_api.py`、`command.py`、`event_log.py`、`state.py`、`transaction.py`、README。

Tests 覆盖充分：
- 公共类型 idempotency（S1：`FollowupSnapshot` 验证、`HostApiError` detail 验证）
- Handle lifecycle（S2：factory、idempotent close、calls-after-close）
- Session API idempotency（S2：`ensure_session` repeated、`create_session` idempotent replay/conflict、`close_session` idempotent）
- Run API idempotency + race（S3：start_run public idempotency、submit_followup queue 两种分支、cancel queued/pre-dispatch、cancel_session_runs 多 Run 批量取消、idempotent replay、unsupported state no partial mutation、public cancel/promotion race）
- Stream + deferred（S4：run filtering、cursor advancement、empty result、limit validation、deferred UNSUPPORTED_OPERATION + no EventLog append）

### 6. 过度设计 / 禁止模式检查

**结论：未引入任何禁止模式。**

| 检查项 | 结果 |
|---|---|
| God object | ✗ `HostCommandHandle` 是 composition root，不暴露内部 store/service；只持有 private refs |
| God dataclass / god bag | ✗ `HostCommandHandleOptions` 是显式 typed fields；`HostApiError.detail` 是受限 union |
| 无结构 payload / extra metadata | ✗ plan §3 明确禁止 `extra`、`payload`、`metadata`、`dict[str, ...]` |
| 兼容 wrapper / re-export | ✗ plan §6 明确禁止 |
| 反向依赖 | ✗ plan §6 明确 `dayu.host` 不 import `dayu.engine`/`dayu.fins`/`dayu.service`/`dayu.ui` |
| Engine / ToolRuntime / Projection / Remote / wait / purge / full steer / retry / replay 夹带 | ✗ plan §1 non-goals 逐项列出，§4 行为矩阵明确 deferred，§5 各 slice non-goals 重申 |
| `hasattr`/`getattr` dispatch | ✗ plan §6 明确禁止 |
| lazy import | ✗ plan §6 只允许 documented import-cycle root cause |
| schema migration / old DB compat | ✗ plan §6 明确 fresh schema only |
| 魔法数字 / 魔法字符串 | ✗ stream limit 使用公共常量；default 值使用模块级常量 |

## Non-blocking Observations

### O1. `HostCommandHandleOptions` 字段与内部 `HostDurableStoreOptions` / `HostSQLiteStoragePolicy` 的映射点

Plan §3 指出"Factory maps this public options dataclass into internal `HostDurableStoreOptions`, `PayloadStoragePolicy` and `HostSQLiteStoragePolicy`"。S2 的 exact changes 也提到"mapping public options to internal durable options"。这个映射必须在 `command.py` 的 factory 函数中集中完成，不应散落到多个地方。Plan 已经表达了这个约束，implementation agent 只需遵守。

### O2. `cancel_session_runs` 与 `cancel_run` promotion 行为差异

`cancel_run` 单个 Run 取消后会释放 active slot 并触发 queue promotion（`admission.py` 现有行为）。Plan §5-S3 明确 `cancel_session_runs` "不触发 queue promotion during session-scope cancel; the operation is cancelling the session's current non-terminal subset, not freeing a slot to start more work"。这是一个有意的设计差异：session-scope cancel 取消全部 non-terminal subset，不存在"释放 slot 后 promote"的语义，因为全部未终态 Run 都被取消了。Implementation agent 必须确保 `cancel_session_runs` 内部不调用 `promote_next_queued_run`。

### O3. `submit_followup` session_id 参数校验

Plan §5-S3 明确"Validate `session_id` argument equals `request.session_id`; mismatch raises `HostApiErrorCode.INVALID_STATE`"。这是一个防御性校验，确保 facade 入口参数一致性。当前 `SubmitFollowupRequest` 已有 `session_id` 字段，public function 签名中的 `session_id` 参数与之重复。Implementation agent 应选择让 public function 只接收 `request`（包含 `session_id`），或者保留两个参数但做校验。Plan 选择了后者，这是一个安全选择。

### O4. `get_run` terminal summary 提取策略

Plan §5-S4 明确："Phase 4 should derive summary refs from terminal event payload only if it can do so via structured JSON parsing with typed validation; otherwise return a status-only `TerminalResultSummary(status=..., summary_ref=None, summary_digest=None)` and document the Phase 4 limitation in Host README"。这是一个合理的降级策略：不强求 Phase 4 解析所有 terminal event payload 结构。Implementation agent 应先尝试结构化解析，如果 terminal event payload 结构不满足 typed validation 则降级。

### O5. `read_non_terminal_runs_for_session` helper 归属

Plan §5-S3 提到"Add `read_non_terminal_runs_for_session` and any needed dispatch / attempt reader helpers in `state.py`"。这是一个合理的新增 durable read helper，属于 `state.py` 的 snapshot / reader 职责范围。Implementation agent 应确保该 helper 只读取不写入，且返回的 Run rows 包含足够信息供 `cancel_session_runs` 判定 supported subset（QUEUED vs RUNNING + STARTING Attempt + PENDING dispatch）。

### O6. `HostApiError.__init__` 扩展

当前 `HostApiError.__init__` 只接收 `code`、`message`、`retryable`。Plan §3 要求新增 `detail: HostApiErrorDetail | None = None`。这是一个签名变更，需要更新现有 `HostApiError` 构造和所有已有调用点（`admission.py` 中的 `raise HostApiError(...)` 调用）。由于新增参数有默认值 `None`，现有调用点无需修改。S1 tests 应验证 `detail=None` 的默认行为和显式传入 `SteerConflictDetail` 的行为。

## 设计真源对齐矩阵

| 契约要素 | design.md 位置 | plan 节 | control.md 位置 | 一致性 |
|---|---|---|---|---|
| Host handle composition root | §10.1:694-812 | §3 Handle / Factory / Facet | Phase 4 目标 | ✓ |
| FollowupSnapshot accepted_run shape | §11:1055 | §3 FollowupSnapshot | line 521 | ✓ |
| HostApiErrorCode.UNSUPPORTED_OPERATION | §11:1066,1075 | §3 HostApiErrorCode | line 522 | ✓ |
| HostApiError.detail typed union | §11:1077-1087 | §3 HostApiError.detail | line 522 | ✓ |
| SteerConflictDetail | §11:1080-1084 | §3 SteerConflictDetail | line 522 | ✓ |
| stream_run_events cursor | §13:1089-1097 | §3 Stream Constants | line 524 | ✓ |
| cancel_session_runs subset | §22:2156 | §4 behavior matrix | line 508 | ✓ |
| cancel deferred owners | §22:2156 | §4 + §8 | line 551 | ✓ |
| submit_followup steer unsupported | §12:1116-1117 | §4 behavior matrix | line 523 | ✓ |
| attach_active no canonical fact | §11:1021 | §4 behavior matrix | line 525 | ✓ |
| mutating path: tx → EventLog → commit | §10.1:726-733 | §5-S2/S3 state transitions | Phase 4 目标 | ✓ |
| idempotency scope contract | §11:919-925 | §5-S2/S3 exact changes | Phase 4 追踪区 | ✓ |
| HostCallContext required | §11:871-885 | §3 (implicit in request types) | Phase 4 范围 | ✓ |

## Residual Risks / Deferred Owners

| 项 | owner | 归属 |
|---|---|---|
| dispatching / active worker cancel propagation | Phase 5 | 已在追踪区 |
| `WAITING` cancel / wait record cancel | Phase 7 | 已在追踪区 |
| `RECOVERING` cancel / recovery dispatch cancellation | Phase 11 | 已在追踪区 |
| `purge_session` destructive cleanup | Phase 15 | 已在追踪区 |
| full steer Attempt switching | 后续 steer owner | 已在追踪区 |
| retry / replay execution semantics | 后续 retry/replay owner | 已在追踪区 |
| `created_event_sequence <= 0` 防御性校验测试 | Phase 4 或首个扩展 idempotency public consumer | 已在追踪区 P2 item |
| `SQLitePayloadWriteRequest.payload_json=None` 隐式 null 收紧 | Phase 4 public command path | 已在追踪区 P2 aggregate item |
| terminal summary 结构化解析降级 | Phase 4 S4（实施时决策） | plan §5-S4 stop condition |

## Plan Gate Recommendation

**推荐 accepted，进入 implementation gate。**

理由：
1. Plan 严格对齐 Phase 4 behavior matrix，cancel 子集边界清晰，deferred 函数均有 stable UNSUPPORTED_OPERATION 行为与明确后续 owner。
2. Public contract changes 足够具体：`FollowupSnapshot`、`HostApiErrorCode.UNSUPPORTED_OPERATION`、`HostApiError.detail` / `SteerConflictDetail`、stream constants、`HostCommandHandleOptions` 均有逐字段定义和 validation rules。
3. `stream_run_events` cursor plan 完全符合 EventLog global cursor truth，不引入 projection truth。
4. 4 个 implementation slices 沿类型冻结 → handle/session → run/admission/cancel → read/stream/deferred 边界切分，每个 slice 有明确 allowed files、exact changes、tests、validation commands 和 stop conditions。
5. 未引入过度设计、god object、无结构 payload、兼容 wrapper/re-export、反向依赖，或让 implementation 夹带 Engine/ToolRuntime/Projection/Remote/wait/purge/full steer/retry/replay。
6. Non-blocking observations 均为 implementation agent 可自行处理的细节，不阻塞 plan gate。
