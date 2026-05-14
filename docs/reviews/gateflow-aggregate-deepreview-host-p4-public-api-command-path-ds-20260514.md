# Host Phase 4 Public API Command Path —— Aggregate Deep Review (AgentDS)

## 审查范围

- **Gate**: Phase 4 Implementation, Public API Command Path
- **Slices**: P4-S1 through P4-S4（4 slices）
- **Branch**: `docs/host-phase4-control-state`
- **Design truth**: `docs/host/design.md`
- **Control doc**: `docs/host/implementation-control.md`
- **Phase plan**: `docs/host/phase4-public-api-command-path-plan.md`
- **Implementation commits**:
  - `e004031` — plan accept
  - `9828fd1` — plan record
  - `b1e6eec` — P4-S1 (host handle, typed options, policy views, context validation)
  - `2958715` — P4-S1 record
  - `190d905` — P4-S2 (session APIs, snapshots)
  - `ee16e00` — P4-S2 record
  - `af61fe9` — P4-S3 (run/follow-up/cancel command path, admission)
  - `673a8db` — P4-S3 record
  - `34b1207` — P4-S4 (read APIs, event stream cursor, deferred facade)
  - `87fe87c` — P4-S4 record
- **Current tree**: uncommitted changes (P4-S4 fixes from re-review)
- **Review type**: Aggregate cross-slice deep review

## 验证结果

```
source .venv/bin/activate && pytest tests/host -q
→ 201 passed in 2.04s

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ passed (no whitespace issues)
```

## 变更文件总览

跨 15 个 production + test 文件，约 3966 insertions（vs Phase 3 baseline `d9c2ca9`）:

| 文件 | 角色 |
|------|------|
| `dayu/host/api.py` | Public type contracts, constants, error/status enums, request/snapshot dataclasses |
| `dayu/host/__init__.py` | Package root exports (types, command, read, tooling) |
| `dayu/host/command.py` | HostCommandHandle, factory, close, all public command/read/deferred functions |
| `dayu/host/read_api.py` | Public read facade: get_session, get_run, stream_run_events |
| `dayu/host/admission.py` | Internal admission: cancel_session_runs orchestration |
| `dayu/host/durable/state.py` | Durable row codec additions: read helpers, run_snapshot_from_row, session cancel support reading |
| `dayu/host/durable/event_log.py` | EventLog reader additions (if any for read_api support) |
| `dayu/host/durable/transaction.py` | Read transaction support |
| `dayu/host/README.md` | Host development manual: implemented facades, deferred facade, stream cursor contract, Phase 5/7/11 reminders |
| `tests/host/test_public_contracts.py` | Enum stability, dataclass frozen/slots, error/detail validation, constants |
| `tests/host/test_package_exports.py` | Export whitelist verification |
| `tests/host/test_command_handle.py` | Factory, lifecycle, public surface non-exposure, import boundary |
| `tests/host/test_public_session_api.py` | Session facade: ensure, create, close, get, idempotency, conflicts |
| `tests/host/test_public_run_api.py` | Run facade: start, follow-up, cancel, get_run, deferred functions |
| `tests/host/test_public_cancel_session_runs.py` | cancel_session_runs subset, idempotent replay, unsupported no-mutation |
| `tests/host/test_public_event_stream.py` | EventLog stream: filtering, cursor, limits, missing run, validation order |

## Cross-Slice Interaction Analysis

### 1. Idempotency Scope Consistency

各 command 函数的幂等 scope 模式统一使用 `(operation, scope_id, idempotency_key)` 三元组:

| Operation | Scope | Idempotency Key |
|-----------|-------|-----------------|
| `ensure_session` | `(scope, slot_key)` | N/A (slot-scope 唯一绑定) |
| `create_session` | `None` | `request.client_request_id` |
| `close_session` | `session_id` | `request.client_request_id` |
| `start_run` | `session_id` | `request.client_request_id` |
| `submit_followup` | `session_id` | `request.client_request_id` |
| `cancel_run` | `run_id` | `request.client_request_id` |
| `cancel_session_runs` | `session_id` | `request.client_request_id` |

**分析**: `cancel_run` 的 scope_id 是 `run_id`（per-run），而 `cancel_session_runs` 的 scope_id 是 `session_id`（per-session）。这个差异是正确的：`cancel_run` 是单 Run 操作，重放在该 Run 已 cancel 后应返回当前状态；`cancel_session_runs` 是 Session 级操作，其 semantic digest 不包含当前 Run 列表（见 `admission.py` docstring），重放不会取消首次操作后新接受的 Run。这是有意设计，经测试验证（`test_cancel_session_runs_idempotent_replay_does_not_cancel_new_run`）。

**结论**: ✓ 幂等 scope 模式跨 slice 一致且有意合理。

### 2. cancel_run (P4-S3) → Deferred Cancel State Detection (P4-S4)

`cancel_run` 在 `command.py` 中采用两级 deferred cancel 检测:

1. `admission.py` 内部 cancel 对无法处理的状态（WAITING/CANCELLING/RECOVERING、或 RUNNING 但非 pre-dispatch STARTING）抛出 `INVALID_STATE`
2. `command.py:374-382` 捕获 `INVALID_STATE`，再调用 `_is_deferred_cancel_state`（独立 read transaction）确认属于 deferred cancel 能力，转换为 `UNSUPPORTED_OPERATION`

`_is_deferred_cancel_state` (`command.py:804-812`):
```python
if run.status in (WAITING, CANCELLING, RECOVERING):
    return True
if run.status != RUNNING:
    return False
return not _is_predispatch_starting_run(transaction, run)
```

**分析**: 这个两级检测引入了两次读取（admission 内一次，deferred 判断一次）——admission 失败后 command 层打开新的 read transaction 判断原因。这是安全的，因为在 admission write transaction 提交失败后重新读取的方式不会产生竞争窗口：如果 admission 失败是因为真正的不支持状态（而非 transient CAS 竞争），那么状态在读 transaction 中仍是相同的。如果是 CAS 竞争导致的假阳性 INVALID_STATE，`_is_deferred_cancel_state` 的 read transaction 会看到最新状态，如果 Run 实际上应该能被 cancel（比如状态从 RUNNING 转为了可以取消的 pre-dispatch STARTING——但这不会发生，因为 pre-dispatch STARTING 就是可取消的），则该 read 不会误判为 deferred。

**结论**: ✓ P4-S3 cancel_run 与 P4-S4 deferred state detection 交互正确，两级检测不会产生竞争窗口误判。

### 3. cancel_session_runs (P4-S3) → Read Path Isolation (P4-S4)

`cancel_session_runs` 在 `admission.py:1138-1161` 中:
1. 先读取全部非终态 Run
2. 逐个调用 `_session_cancel_target_for_run` 判断是否属于 Phase 4 支持的 queued / pre-dispatch STARTING 子集
3. 若任意一个 Run 返回 `None`（unsupported），立即抛出 `UNSUPPORTED_OPERATION`，在此之前没有任何 EventLog 或 state mutation

`_session_cancel_target_for_run` (`admission.py:1862-1895`) 处理:
- `QUEUED` → 支持
- `RUNNING` + `attempt.status=STARTING` + `dispatch.status=PENDING` → 支持
- 其他 `RUNNING`、`WAITING`、`CANCELLING`、`RECOVERING` → `None`（unsupported）

**测试覆盖**: `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` 通过 `_mark_attempt_running` 把 active Run 的 Attempt 从 STARTING 改为 RUNNING，验证 cancel_session_runs 返回 UNSUPPORTED_OPERATION 且:
- EventLog 计数未变（无 cancel fact 被写入）
- active Run 仍为 RUNNING（未被取消）
- queued Run 仍为 QUEUED（未被部分取消）

**分析**: cancel_session_runs 的 all-or-nothing 语义跨 P4-S3（写入）→ P4-S4（读取）保持一致。P4-S4 的 get_run 和 stream_run_events 消费由 P4-S3 cancel 路径写入的 CANCELLED terminal facts。`read_non_terminal_runs_for_session` 读取所有非终态 Run（包括 QUEUED, RUNNING, WAITING, CANCELLING, RECOVERING），但这些状态除了 QUEUED 和 pre-dispatch STARTING 外都会被 `_session_cancel_target_for_run` 拒绝。

**结论**: ✓ cancel_session_runs 的 all-or-nothing 语义正确，partial mutation 防护经测试验证。cancel 产生的 terminal facts 被 read path 正确消费。

### 4. stream_run_events (P4-S4) → EventLog Written by All Prior Slices

`stream_run_events` 读取全局 EventLog（由 P4-S1 到 P4-S4 所有写操作追加），按 `event_sequence > cursor.event_sequence` 扫描，`next_cursor` 为扫描到的最大全局 sequence，不依赖 projection checkpoint 或内存状态。

跨 slice 交互验证:
- P4-S2: start_run → 写 EventLog (USER_INPUT_ACCEPTED → accepted → queued/started)
- P4-S2: submit_followup → 写 EventLog
- P4-S3: cancel_run → 写 EventLog (CANCEL_REQUESTED → cancelled terminal)
- P4-S3: cancel_session_runs → 写 EventLog（同上）
- P4-S4: stream_run_events → 读 EventLog，按 run_id 过滤

**validation order fix**: 经过 P4-S4 re-review，validation 顺序从 "limit 先于 Run 存在性检查" 修正为 "Run 存在性检查先于 limit 解析"，确保 missing run + invalid limit 组合返回 NOT_FOUND 而非 INVALID_STATE。

**结论**: ✓ stream_run_events 的 cursor contract 与所有 write slices 的 EventLog append 一致。

### 5. Deferred Function Stability Across All 4 Slices

4 个 deferred functions (`retry_run`, `replay_run`, `resolve_wait`, `purge_session`) 在 `command.py` 中实现，全部采用相同的 stable unsupported 模式:

```python
def retry_run(host, run_id, request):
    _raise_unsupported_operation("retry_run")
```

`_raise_unsupported_operation` 固定返回:
- `HostApiErrorCode.UNSUPPORTED_OPERATION`
- `retryable=False`
- `detail=None`
- 不打开 transaction，不写 EventLog，不写 idempotency

**测试覆盖**: `test_deferred_public_functions_are_stable_unsupported_without_writes` 验证 4 个 deferred functions 的错误码、可重试标记、detail 字段、EventLog 与 idempotency record 数量不变。

**结论**: ✓ deferred functions 跨所有 4 个 slice 保持完全一致的行为签名。

### 6. get_run (P4-S4) → States Written by All Prior Slices

`get_run` 读取由 P4-S2/S3 写入的 Run durable truth:
- P4-S2: RUNNING (direct start), QUEUED (queue accept), QUEUED→RUNNING (follow-up queue with no active)
- P4-S3: CANCELLED (queued cancel), CANCELLED (pre-dispatch cancel), CANCELLED (session-scope cancel)
- P4-S1: 提供类型契约

**event_cursor 计算**: `_run_event_cursor` 取 Run row 中 input/accepted/queued/started/terminal event_sequence 的最大非空值，不依赖 projection。

**terminal_result_summary**: 终态 Run 返回 status-only `TerminalResultSummary(status=..., summary_ref=None, summary_digest=None)`；Phase 4 不引入 typed terminal payload decoder。非终态 Run 的 `terminal_result_summary` 为 `None`。

**结论**: ✓ get_run 对跨 slice 状态的映射一致。

### 7. Architecture Boundary

`test_host_import_boundary_still_excludes_upper_layers` (`test_command_handle.py:173-185`) 通过 AST 解析验证 `dayu/host/` 所有 Python 文件不 import `dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui` 及其子模块。

`test_public_handle_does_not_expose_internal_mutable_dependencies` 验证 public `HostCommandHandle` 不暴露 `transaction_runner`、`durable_store`、`admission_service`、`store_connection`。

**结论**: ✓ 分层约束无违反。durable 内部模块不从包根导出，admission 不进入 public API。

### 8. Package Export Completeness

`__init__.py` 导出所有 P4-S1 到 P4-S4 新增的 public 符号，`__all__` 包含类型、常量、command 函数、read 函数和 tooling 类型。

`test_package_exports.py` 的 `EXPECTED_COMMAND_EXPORTS` 白名单包含所有新增导出符号，验证包根不泄漏 durable 内部模块。

**结论**: ✓ 导出完整，无遗漏，无泄漏。

## Findings

### Finding 1 [Info] cancel_session_runs Phase 5/7/11 follow-up 已追踪但非强制执行

- **文件**: `dayu/host/README.md:113`, `dayu/host/admission.py:1138-1161`, `docs/host/implementation-control.md:551-552`
- **严重性**: Info（无安全或正确性问题，属于架构转交提醒）

**证据**:

Phase 4 `cancel_session_runs` 只覆盖 queued Run 与 pre-dispatch STARTING（Attempt=STARTING, dispatch=PENDING）Run。`_session_cancel_target_for_run` 对 WAITING/CANCELLING/RECOVERING 状态以及已处于 active worker 的 RUNNING Run 返回 `None`，导致整个 session-scope cancel 返回 UNSUPPORTED_OPERATION。

README line 113 正确地记录了后续 phase 的 ownership:
> Phase 5 负责 dispatching / active worker cancel，Phase 7 负责 `WAITING` cancel，Phase 11 负责 `RECOVERING` cancel。

Control doc line 551-552 的 Phase 4 退出条件中的 "需要追踪到后续 phase 的事项" 也包含了完整的提醒。

**评估**: README 和 control doc 都明确记录了 Phase 5/7/11 的 cancel 扩展需求。当前实现有测试覆盖 `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` 验证 unsupported 时无部分 mutation。但是，`cancel_session_runs` 的 UNSUPPORTED_OPERATION 错误消息 ("cancel_session_runs supports only queued and pre-dispatch STARTING Runs in Phase 4") 明确提到了 "Phase 4"，这是一个清晰的提醒：后续 phase 的 reviewer 会立即看到这个消息需要升级。

**Risk**: 如果 Phase 5/7/11 的 implementer 不检查 cancel_session_runs 的 UNSUPPORTED_OPERATION 错误消息和 `_session_cancel_target_for_run` 的过滤逻辑，UNSUPPORTED_OPERATION 错误可能会被后续 phase 的新状态触发但未被正确处理——不过这属于后续 phase 的 review scope。

**结论**: ✓ 当前状态可接受。Phase 4 的 UNSUPPORTED_OPERATION 回退是正确的 defense，Phase 5/7/11 必须在各自 phase 中扩展 `_session_cancel_target_for_run` 支持各自的 Run 状态子集。

### Finding 2 [Info] _TERMINAL_RUN_STATUSES 重复定义

- **文件**: `dayu/host/read_api.py:37-39` 与 `dayu/host/durable/state.py` 的 `_is_terminal_run_status`
- **严重性**: Info（非阻塞，两处当前语义一致）

与 P4-S4 review 的 Finding 3 相同。read_api.py 为 public read facade 的 `_run_snapshot_from_public_read_row` 定义了终态判断的 frozenset，state.py 为 durable row codec 定义了语义相同的判断函数。当前 `RunStatus` 在 Phase 4 不会新增终态值，但如果后续 phase 新增终态（如 `SUSPENDED` 或类似迁移），需要同步更新两处。

**建议**: 非阻塞。可在后续 phase 中提取为 `dayu.host.api` 中的 public frozenset 或复用 state.py 的导出函数。

### Finding 3 [Info] submit_followup(queue) internal default execution target

- **文件**: `dayu/host/README.md:55`
- **严重性**: Info（已知限制，有文档记录）

README 明确记录:
> Phase 4 public `submit_followup(queue)` 暂使用 Host facade 内部默认 execution target 作为 policy resolution output；完整 policy provider / execution target resolution 装配不在当前实现范围。

这是 Control doc Phase 4 planned scope 内的已知 non-goal，非实现遗漏。

### Finding 4 [Info] create_session metadata 不持久化

- **文件**: `dayu/host/README.md:38`
- **严重性**: Info（已知限制，有文档记录）

README 明确记录:
> `create_session` public facade 不持久化 `request.metadata`；metadata 持久化语义尚未成为 public contract。

`ensure_session` 仍按 durable lifecycle 保存首次创建时的 metadata 摘要。这是有意设计选择，非缺陷。

### Finding 5 [Info] attach_active 无 canonical EventLog fact

- **文件**: `dayu/host/command.py`, `tests/host/test_public_run_api.py:281-293`
- **严重性**: Info（已知设计决策，符合 control doc 要求）

`start_run` 使用 `attach_active` policy 时只记录幂等结果并返回当前 active `RunSnapshot`，不追加 EventLog fact。Control doc Phase 4 关键设计问题中明确:
> `attach_active` 第一版不新增 canonical EventLog fact；返回当前 active `RunSnapshot`，幂等记录可解释 request，audit/read-model 由后续 projection 基于 refs 表达。

测试验证: `test_start_run_direct_running_and_attach_active` 断言 `_event_count` 在 attach_active 后不变。

**结论**: ✓ 符合有意设计。

## Scope / Invariant Verification

### Session Command Path
- `ensure_session`: 原子 slot bind + Session lifecycle ✓
- `create_session`: 幂等创建 + bind_slot 校验 ✓
- `get_session`: 只读事务读取 Session + active/queued Run 索引 ✓
- `close_session`: 幂等 close，保留 durable truth ✓
- 缺失 Session → NOT_FOUND ✓

### Run Command Path
- `start_run`: direct start / queue / reject / attach_active ✓
- `submit_followup(queue)`: active 存在时 QUEUED，无 active 时 RUNNING ✓
- `submit_followup(steer)`: UNSUPPORTED_OPERATION，不写 EventLog ✓
- `cancel_run`: queued + pre-dispatch STARTING cancel ✓
- `cancel_run` deferred states → UNSUPPORTED_OPERATION ✓
- `cancel_session_runs`: Phase 4 子集, all-or-nothing, no partial mutation ✓
- 队列 promotion 在 active slot 释放后触发 ✓

### Read Path
- `get_run`: event_cursor = max 非空 Run row sequence ✓
- `get_run`: 非终态 terminal_result_summary=None, 终态 status-only ✓
- `get_run`: current_attempt_id 来自 Run row ✓
- `get_session`: 包含 active_run_id 与 queued_run_ids ✓
- `stream_run_events`: 全局 EventLog cursor truth ✓
- `stream_run_events`: limit 作为扫描窗口 ✓
- `stream_run_events`: 按 run_id 过滤 ✓
- `stream_run_events`: next_cursor = max scanned global sequence ✓
- `stream_run_events`: 无扫描行时 next_cursor = 输入 cursor ✓
- `stream_run_events`: 无关 Run 事件推进 cursor ✓
- `stream_run_events`: HostEventView 不暴露 policy_decision/reason/payload JSON ✓
- `stream_run_events`: Run 存在性检查先于 limit 解析（re-review fix） ✓
- `stream_run_events`: missing run + invalid limit → NOT_FOUND（re-review fix） ✓

### Deferred Facade
- 4 个 deferred functions: UNSUPPORTED_OPERATION, retryable=False, detail=None ✓
- 不写 EventLog, 不写 idempotency ✓
- 签名稳定供后续 phase 扩展 ✓

### Idempotency
- idempotent replay 返回当前 durable truth ✓
- semantic digest 变更 → IDEMPOTENCY_CONFLICT ✓
- cancel_session_runs semantic digest 不包含当前 Run 列表 ✓

### Public Types
- 所有 public dataclass: frozen=True, slots=True ✓
- 枚举: StrEnum, stable snake_case values ✓
- HostApiError: code, message, retryable, detail (typed restricted) ✓
- HostApiErrorCode 包含 UNSUPPORTED_OPERATION ✓
- HostStreamCursor: event_sequence >= 0 ✓
- FollowupSnapshot: QUEUED/RUNNING accepted_run_status, queued_run_id 约束 ✓

### Architecture and Exports
- `dayu.host` 不 import engine/fins/service/ui ✓
- public handle 不暴露 durable store/admission/transaction runner ✓
- durable 内部模块不从包根导出 ✓
- `__all__` 完整 ✓
- `dayu.host.api.__all__` 只包含类型，不包含 command/read 函数 ✓

### Docs
- README 记录了已实现的 Session/Run/Read/deferred facade ✓
- README 记录了 stream cursor contract ✓
- README 记录了 terminal result summary Phase 4 限制 ✓
- README 记录了 cancel_session_runs Phase 5/7/11 提醒 ✓
- README 记录了 deferred facade 为 stable unsupported ✓
- Control doc Phase 4 退出条件记录了完整的追踪事项 ✓

### No P4-S3 Regressions
- `admission.py` cancel_run 行为未变 ✓
- `admission.py` cancel_session_runs 行为未变 ✓
- `admission.py` admission/follow-up/promotion 未变 ✓
- `state.py` 核心状态迁移未变 ✓

### Chinese Docstrings / Typing
- 所有新增函数/类/模块有中文 docstring: params, returns, raises ✓
- 无 `Any`, `object`, 无类型参数/返回值 ✓
- 无 `getattr`/`hasattr` 滥用 ✓
- 无 magic string scatter ✓
- 无兼容性 wrapper/compatibility re-export ✓

## Residual Risks

1. **Phase 5/7/11 cancel_session_runs 扩展**: Phase 4 的 `_session_cancel_target_for_run` 对 WAITING/CANCELLING/RECOVERING 和 active worker RUNNING 返回 None，整个 operation 回退为 UNSUPPORTED_OPERATION。Phase 5/7/11 的 implementer 必须扩展该函数支持各自的状态子集。当前 UNSUPPORTED_OPERATION 错误消息中包含 "Phase 4" 措辞是有意的提醒。
2. **_TERMINAL_RUN_STATUSES 重复定义**: read_api.py 和 state.py 各自定义终态集合。当前 RunStatus 不会新增终态值，但未来若新增需同步两处。
3. **submit_followup(queue) execution target 硬编码**: 后续需通过 policy provider 装配真实 execution target resolution。
4. **terminal_result_summary status-only fallback**: Phase 4 无 typed terminal payload decoder，终态 Run 只能返回 status-only summary。未来 Phase 需从 EventLog payload 或 typed decoder 提取完整 summary_ref 和 summary_digest。

## Conclusion

**Phase 4 Public API Command Path 跨 4 个 slice 的聚合审查通过。无 blocking finding。**

- 201 测试通过（跨所有 slice），pyright 0 errors。
- Cross-slice idempotency scope 一致，cancel 状态检测正确，read path 正确消费所有 slice 的 durable truth。
- cancel_session_runs all-or-nothing 语义正确，partial mutation 防护经测试验证。
- P4-S4 re-review fixes（validation order, test contiguity dependency）已正确合入。
- Phase 5/7/11 的 cancel_session_runs 扩展责任在 README 和 control doc 中明确追踪。
- 架构边界、包导出、类型纪律均通过验证。
- 5 个 Info-level findings: cancel_session_runs Phase 5/7/11 follow-up tracking, terminal status duplication, execution target hardcoding, metadata not persisted, attach_active no EventLog fact。全部为已知设计决策或已文档记录的限制，非缺陷。
