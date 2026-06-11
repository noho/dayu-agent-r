# WU-PROJ-01 Slice 3 Code Review - AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- Slice: `Slice 3 - Bounded memory projection catch-up / rebuild`
- Gate: code review
- Reviewer: AgentDS
- 日期: 2026-06-11
- 设计真源: `docs/host/design.md`; `docs/engine/design.md`
- Accepted plan: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- Implementation report: `docs/reviews/wu-proj-01-slice3-implementation-codex.md`
- Review artifact: `docs/reviews/wu-proj-01-slice3-code-review-ds.md`

## 范围

Review 当前未提交 diff，重点文件:

- `dayu/host/memory_repair.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `tests/host/test_memory_repair.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_logging.py`
- `docs/reviews/wu-proj-01-slice3-implementation-codex.md`
- `docs/host/issues-implementation-control.md`（仅 gate bookkeeping）

## 独立验证

```bash
source .venv/bin/activate && python -m pytest tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py tests/host/test_logging.py -v
# 25 passed

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations
```

验证结果与 implementation report 一致，可信。

## 逐项检查

### 1. MemoryProjectionCatchupBudget 字段

**PASS。** `MemoryProjectionCatchupBudget` 只有三个字段:

- `max_batches: int`
- `max_scanned_events: int`
- `purpose: MemoryProjectionRepairPurpose`

无 `timeout_seconds`。`__post_init__` 校验 `max_batches >= 1`、`max_scanned_events >= 1`、purpose 合法。

### 2. Bounded loop stop reasons

**PASS。** `MemoryProjectionRepairStopReason` 四个值:

- `IDLE = "idle"`
- `TARGET_REACHED = "target_reached"`
- `FAILURE = "failure"`
- `BUDGET_EXHAUSTED = "budget_exhausted"`

在 `_run_memory_projection_bounded` 循环中的 stop reason 裁决顺序:

1. `batches_used >= max_batches` → BUDGET_EXHAUSTED（未执行 batch）
2. `_bounded_batch_limit` 返回 0 → BUDGET_EXHAUSTED（扫描预算在 batch 前耗尽）
3. 执行 `run_once()` 后:
   - `failures > 0` → FAILURE
   - `finished_cursor >= max_event_sequence` → TARGET_REACHED
   - `events_scanned < limit` → IDLE
   - `events_scanned >= budget.max_scanned_events` → BUDGET_EXHAUSTED

裁决顺序正确: target reached 优先于 budget exhausted（若同一 batch 同时达成目标且用尽扫描预算，target reached 胜出）；failure 优先于一切。

### 3. batch_size vs budget 语义

**PASS。** `batch_size` 仍是单批扫描上限，直接传给 `ProjectionRunner.run_once(limit=...)`。`budget.max_batches` 是本次总批次数，`budget.max_scanned_events` 是本次总扫描事件数。`_bounded_batch_limit` 计算当前 batch 的 limit 为 `min(batch_size, remaining_events)`，防止单批超总预算。

### 4. budget exhausted ≠ projection failure

**PASS。** 在 bounded loop 中，budget exhausted 的两个检查点（batch count、scanned events）均在 `run_once()` 之前或之后单独裁决，不经过 `failures` 累加路径。`ConversationMemoryProjectionRepairResult.budget_exhausted` 仅在 `stop_reason is BUDGET_EXHAUSTED` 时为 True。`_log_memory_projection_result` 中 budget_exhausted 有独立日志分支（`.<operation>.budget_exhausted`），不经过 `.failed` 分支。budget exhausted 时 `failures` 必为 0（因 loop 在 batch 执行后先检查 failures，若有 failure 不会走到 budget exhausted 检查）。

### 5. dispatch before-worker catch-up 阻断 worker.accept

**PASS。** 在 `_start_worker`（dispatch.py:2688）中:

1. `_catch_up_memory_projection_before_worker(record)` 调用 catch-up + `_raise_if_memory_projection_target_not_reached`
2. 若 target 未覆盖，抛出 `_MemoryProjectionDispatchDiagnosticError`
3. `_start_worker` 的 `except _MemoryProjectionDispatchDiagnosticError` 捕获，调用 `_safe_closeout_worker_startup_timeout(reason=_MEMORY_PROJECTION_REPAIR_REQUIRED_REASON)`，释放 lane token，返回 `"timed_out"`
4. 不调用 `worker.accept`，不触发 recovery Attempt，不写 `RUN_RECOVERING`

`_raise_if_memory_projection_target_not_reached` 函数检查逻辑: `result.failures == 0 and result.target_reached` 时放行；否则抛出。这意味着即便仅存在 projection failure（failures > 0），无论 target 是否恰好覆盖，也阻断开。这是一个保守但正确的决策——projection failure 下不应信任 target_reached 的计算。

### 6. lag rebuild 只重建到 required cursor，预算耗尽按 repair failure 收口

**PASS。** `_build_run_input_with_lag_repair`（dispatch.py:2902-2939）:

1. `builder.build(snapshot)` 抛出 `MemoryProjectionRepairRequired(reason=SNAPSHOT_LAG_OVER_THRESHOLD)`
2. 使用 `REBUILD_BEFORE_DISPATCH` budget 调用 `rebuild_conversation_memory_projection`，传入 `max_event_sequence=exc.repair_request.required_event_sequence`
3. `_raise_if_memory_projection_target_not_reached` 检查 rebuild 结果
4. 若 rebuild target 未覆盖 → 抛出 `_MemoryProjectionDispatchDiagnosticError` → 在 `_start_worker` 中按 memory projection repair failure 收口
5. 若 rebuild target 覆盖 → 重建 `RunInputBuilder`，再次 `build(snapshot)`
6. 若二次 build 仍抛出 `MemoryProjectionRepairRequired` → 在 `_start_worker` 中由现有 `except MemoryProjectionRepairRequired` 分支收口

rebuild 不再无界追到 EventLog idle，正确。

### 7. open_host after-commit catch-up 为 bounded best-effort

**PASS。** `open_host.py` 的 `_after_commit_memory_projection_budget` 构造:

- `max_batches = 1`
- `max_scanned_events = batch_size * 1`
- `purpose = BEST_EFFORT_AFTER_COMMIT`

`_MemoryProjectionCatchupPort.catch_up_projection()` 将 budget 传入 `catch_up_conversation_memory_projection`，但不检查返回值（返回 `None`）。预算耗尽只产生 warning log，不抛出异常，不阻断 command path。

### 8. diagnostics/logging 完整性

**PASS。** 三层日志覆盖:

- **memory_repair 层**: rebuild/catch_up 的 `.start`、`.failed`、`.budget_exhausted`、`.committed` 均记录 consumer_id, started_cursor, finished_cursor, events_scanned, events_matched, events_applied, duplicates, batches_used, stop_reason, max_event_sequence, max_batches, max_scanned_events
- **dispatch 层**: `dispatch.memory_projection.repair_not_reached` 记录 operation, run_id, attempt_id, execution_id, required_event_sequence, started_cursor, finished_cursor, events_scanned, batches_used, stop_reason, budget_exhausted, failures, max_batches, max_scanned_events
- **error 层**: `_MemoryProjectionDispatchDiagnosticError` 的 `__init__` message 拼接了 operation, run_id, attempt_id, execution_id, required_event_sequence, finished_cursor, stop_reason

所有日志使用了业务可读字段名；event_id、cursor、batch 数均以结构化 key=value 形式记录；无裸 digest / cursor 作为唯一标识。

### 9. 测试覆盖

| 测试 | 覆盖场景 | 判定 |
|------|----------|------|
| `test_catch_up_stops_when_target_reached_before_idle` | catch-up 到 max_event_sequence 后停止，target_reached=True | PASS |
| `test_catch_up_budget_exhausted_stops_before_idle` | max_batches=1 预算耗尽，budget_exhausted=True, failures=0 | PASS |
| `test_rebuild_budget_exhausted_reports_target_not_reached` | rebuild 预算耗尽且未覆盖 required cursor | PASS |
| `test_catch_up_budget_exhausted_advances_only_processed_checkpoint` | 真实 durable partial checkpoint advance | PASS |
| `test_open_host_memory_projection_port_uses_best_effort_budget` | open_host port budget 注入 | PASS |
| `test_open_host_dispatch_memory_catchup_budget_exhausted_blocks_worker_accept` | dispatch budget exhausted 阻断 worker.accept, Run FAILED | PASS |
| `test_catchup_port_delegates_to_catch_up_function` | port budget 注入验证（更新） | PASS |
| `test_rebuild_resets_projection_and_finishes_empty_batch` | rebuild 含 max_event_sequence/budget（更新） | PASS |
| `test_catch_up_accumulates_batches_until_short_batch` | 累积批次验证 target_reached（更新） | PASS |
| `test_catch_up_stops_on_failure_and_counts_failure` | failure stop_reason/budget_exhausted 验证（更新） | PASS |
| `test_memory_catchup_logs_cursors_and_counts` | 日志 stop_reason/target_reached/budget 验证（更新） | PASS |

**轻微覆盖缺口:**

- `test_open_host_memory_projection_port_uses_best_effort_budget` 仅验证 port 构造/传递 budget，未验证 budget exhausted 时 port.catch_up_projection() 不抛异常。该行为可通过 `port.catch_up_projection()` 不设 try/except 的调用链验证——函数签名返回 None、内部不 raise budget related error——属于结构性保证，风险低。
- 无显式测试 "catch-up required cursor 已覆盖 → 继续构造 RunInput" 的 happy dispatch path。该路径由现有 dispatch 测试隐式覆盖（预算常量远大于测试 EventLog 规模）。
- 无显式测试 failure > 0 时 `_raise_if_memory_projection_target_not_reached` 必定 raise。该行为由 `test_catch_up_stops_on_failure_and_counts_failure` 间接验证（failure 导致 stop_reason=FAILURE），但未在 dispatch 层测试 `_MemoryProjectionDispatchDiagnosticError` 的 failure 分支。风险低——`_raise_if_memory_projection_target_not_reached` 的条件 `result.failures == 0 and result.target_reached` 逻辑简单且被所有非 failure 测试反复验证。

### 10. pyright/test validation 可信度

**PASS。** 独立运行确认 25 tests passed, pyright 0 errors。与 implementation report 一致。

### 11. 控制文档 bookkeeping

**PASS。** `docs/host/issues-implementation-control.md` 更新正确:

- gate 从 `implementation` 推进到 `code review`
- implementation status 更新为 Slice 3 implementation completed; awaiting two-lane code review
- next entry point 更新为 Slice 3 code review gate via AgentMiMo and AgentDS
- Slice 3 implementation gate 节新增 changed files、validation、controller decision、review artifacts expected
- review artifacts expected 列出 `code-review-mimo.md` 和 `code-review-ds.md`，与 two-lane review 一致

## 额外观察（非阻塞）

### O1: `_log_memory_projection_result` 三个分支日志相似度

`.failed`、`.budget_exhausted`、`.committed` 三个分支的日志格式串存在显著重复（consumer_id、cursor、events、batches、budget 字段几乎全同）。当前三个分支各自维护 6-9 个格式占位符，未来若新增 result 字段需同步修改三处。考虑到这是 Host 内部模块级 logger，且三个分支的 severity 级别不同（warning vs verbose），当前的重复是可接受的。若后续扩展 `ConversationMemoryProjectionRepairResult` 字段，建议抽取公共字段格式化逻辑。

### O2: `_raise_if_memory_projection_target_not_reached` 命名

函数名暗示只检查 target_reached，但实现同时检查 `failures == 0`。在 failure > 0 时也 raise。命名略微误导，但因为这是 dispatch 模块内的私有函数，实际影响小。

### O3: budget 常量不可配置

`_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES = 16`、`_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES = 32` 是模块级私有常量。plan 已明确这是第一版取值，不在此 slice 扩展配置。符合设计意图。

## 裁决

| 维度 | 判定 |
|------|------|
| correctness | 通过。所有 checklist 项符合 plan 规格，无逻辑错误 |
| stability | 通过。budget exhausted 与 projection failure 正确分离；不触发 recovery |
| maintainability | 通过。新增类型与 helper 均为 Host 内部私有，边界清晰 |
| test coverage | 通过。核心场景充分覆盖，minor gap 风险低 |
| diagnostics/logging | 通过。三层日志覆盖，结构化字段完整 |
| control doc bookkeeping | 通过。gate 推进与状态更新正确 |
| pyright/test validation | 可信。独立验证 25 passed, 0 errors |

**Verdict: APPROVE。** 无 correctness blocking 问题。

## Blocking open questions

无。

## Residual risks

1. **预算常量调参**: 当前 `REQUIRED_BEFORE_DISPATCH_MAX_BATCHES=16`、`REBUILD_BEFORE_DISPATCH_MAX_BATCHES=32` 是内部第一版取值。若 production profiling 发现某些 session 需要更大预算，需要后续设计/API 决策引入可配置项。plan 已记录此风险，不在本 slice 范围。

2. **Reactive ingest catch-up 调用**: 当前不在本 slice allowed files 内；它们不属于 ordinary dispatch command/admission hot path。若后续发现 reactive path 也需要 bounded catch-up，应另起 work unit。plan 已记录此风险。

3. **`rebuild_conversation_memory_projection` 签名 breaking change**: `max_event_sequence` 和 `budget` 改为 required keyword 参数。当前仓库内只有 `dispatch.py` 调用此函数，测试已同步更新。若存在未跟踪的外部调用方（如脚本、分析工具），会收到 TypeError。风险低，因为该函数在模块 docstring 定义了 Host 内部语义且仓库内 grep 未发现其他调用方。

4. **`ConversationMemoryProjectionRepairResult` 新增 7 个带默认值的字段**: 外部直接构造该 dataclass 的代码（如测试 monkeypatch）在不传新字段时得到默认值（batches_used=0, stop_reason=IDLE, budget_exhausted=False, target_reached=False, max_event_sequence=None, max_batches=None, max_scanned_events=None）。如果这些代码后续被用于需要 bounded 语义的场景，默认值可能导致误判。当前测试中所有 monkeypatch 返回的默认值均合理用于其测试上下文。风险低。
