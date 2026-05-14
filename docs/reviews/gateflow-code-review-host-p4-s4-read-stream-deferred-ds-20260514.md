# Host P4-S4 Read Stream Deferred —— Adversarial Code Review (AgentDS)

## 审查范围

- **Gate**: Phase 4 Implementation
- **Slice**: P4-S4 Read APIs, Event Stream And Deferred Facade Behavior
- **Baseline**: P4-S3 accepted slice commit `af61fe9`
- **Design truth**: `docs/host/design.md`
- **Plan truth**: `docs/host/phase4-public-api-command-path-plan.md`
- **Review target**: 当前 workspace 未提交 diff（vs `af61fe9`）

## 验证结果

```
source .venv/bin/activate && pytest tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host -q
→ 200 passed in 2.02s

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ passed (no whitespace issues)
```

## Findings

### Finding 1 [Medium] `stream_run_events` 中 limit 验证在 Run 存在性检查之前执行，偏离 Plan 明确顺序

- **文件**: `dayu/host/read_api.py:86-93`
- **严重性**: Medium（Plan 偏离，但实际安全影响低）

**证据**:

Plan P4-S4 Exact changes 明确要求:
> - Implement `stream_run_events`.
>   - Validate run exists first; missing run returns `NOT_FOUND`.

当前实现流程:
1. `stream_run_events()` 第 86 行调用 `_resolve_stream_limit(limit)` —— 在事务外验证 limit
2. 第 87 行调用 `host._run_read(_StreamRunEventsOperation(...))` —— 在事务内检查 Run 存在性

结果: 当 `limit=0` 且 Run 不存在时，调用方收到的是 `INVALID_STATE` 而非 `NOT_FOUND`。`_resolve_stream_limit` (`read_api.py:199-205`) 在开启事务前就抛出 `INVALID_STATE`。

**测试缺口**: 当前没有覆盖 `missing run + invalid limit` 组合场景的测试。`test_stream_run_events_missing_run_returns_not_found` 使用了有效 limit (10)，`test_stream_run_events_rejects_invalid_limits` 需要先创建有效的 Run。

**评估**: Plan 说 "validate run exists first"，当前实现把 cheap input validation（limit）放在 DB read（run existence）之前。从 fail-fast 角度这是合理的输入校验优先策略，但确实与 Plan 文字描述不一致。实际场景中，调用方同时传入无效 limit 和不存在 run_id 的概率极低，安全影响可忽略。

**建议**: 
- 若认同当前 fail-fast 顺序，应在 plan 或 implementation artifact 中记录此设计决策，明确 "limit validation is a pre-transaction input guard, run existence check is the first step inside the transaction body"
- 或补充 `missing run + invalid limit` 测试用例，记录当前行为为有意设计

### Finding 2 [Low] `test_stream_run_events_default_limit_is_scan_window` 断言隐式依赖 EventLog 序列连续性

- **文件**: `tests/host/test_public_event_stream.py:272-273`
- **严重性**: Low（测试在当前条件下总是通过，但 contract 不应依赖实现细节）

**证据**:

```python
assert (
    stream.next_cursor.event_sequence
    == cursor.event_sequence + HOST_EVENT_STREAM_DEFAULT_LIMIT
)
```

该断言等价于 `next_cursor == cursor + 100`。它依赖于本次扫描的 100 行 EventLog 的 `event_sequence` 从 `cursor + 1` 开始严格连续。

**分析**:
- `read_events_after` 的 contract 是 "返回 `event_sequence > cursor` 的最多 `limit` 行，按 `event_sequence ASC` 排序"
- `next_cursor` 的 contract 是 "本次扫描到的最大全局 `event_sequence`"
- `/=/` 断言隐式依赖 SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` 在无删除/无回滚场景下的连续性
- 在当前单线程测试中，序列确实是连续的，断言总是通过
- 但 contract 不承诺 `next_cursor == cursor + scanned_count`，只承诺 `next_cursor` 是 max scanned sequence

**建议**: 改为 `>=` 断言或单独验证扫描行数:
```python
# 方式一：改为 >=
assert stream.next_cursor.event_sequence >= cursor.event_sequence + HOST_EVENT_STREAM_DEFAULT_LIMIT

# 方式二：验证扫描行数等于 limit 且 next_cursor 已推进
assert stream.next_cursor.event_sequence > cursor.event_sequence
# 并从 db 直接读取实际扫描行数来验证 limit 作为扫描窗口生效
```

### Finding 3 [Info] 终端 Run 状态集合在两层各自定义

- **文件**: `dayu/host/read_api.py:37-39` 与 `dayu/host/durable/state.py:2309-2321`
- **严重性**: Info（非阻塞，维护提醒）

**证据**:

`read_api.py` 定义:
```python
_TERMINAL_RUN_STATUSES = frozenset(
    (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.LOST)
)
```

`state.py` 定义:
```python
def _is_terminal_run_status(status: RunStatus) -> bool:
    return status in (
        RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.LOST
    )
```

两者语义相同（判断 Run 是否为终态），但处于不同层（public read facade vs durable codec）。当前集合一致，但如果 `RunStatus` 新增终态值，需要同步更新两处。

**建议**: 当前差异合理（不同层有不同职责），但可在 `state.py` 导出 `_is_terminal_run_status` 供 `read_api.py` 复用，或提取为 `dayu.host.api` 中的 module-level frozenset。非阻塞。

## Scope / Invariant Verification

以下检查项全部通过，无发现:

### get_run
- `event_cursor` 是 Run row 上 input/accepted/queued/started/terminal event_sequence 的最大非空值 → `_run_event_cursor()` (state.py:2348) ✓
- 非终态 Run 的 `terminal_result_summary` 为 `None` → `run_snapshot_from_row()` 始终设 `terminal_result_summary=None` (state.py:1827) ✓
- 终态 Run 返回 status-only `TerminalResultSummary(status=..., summary_ref=None, summary_digest=None)` → `_run_snapshot_from_public_read_row()` (read_api.py:222-238) ✓
- `current_attempt_id` 来自 Run row → `run.current_attempt_id` ✓
- `outbox_summary` 始终为 `None` → 构造时硬编码 `outbox_summary=None` (read_api.py:237) ✓
- 不存在 Run 返回 `NOT_FOUND` → `_GetRunOperation.__call__` (read_api.py:139-144) ✓

### stream_run_events cursor contract
- 全局 EventLog cursor truth → `read_events_after(transaction, cursor.event_sequence, limit=...)` ✓
- limit 是扫描窗口 → `self.limit` 传给 `read_events_after` ✓
- `event_sequence > cursor.event_sequence` → `read_events_after` SQL WHERE clause ✓
- 按 `run_id == self.run_id` 过滤 → `_StreamRunEventsOperation.__call__` (read_api.py:183-185) ✓
- `next_cursor` = max scanned global sequence → `scanned[-1].event_sequence` (read_api.py:178-179) ✓
- 无扫描行时 `next_cursor` = 输入 cursor → (read_api.py:175-176) ✓
- 无关 Run 事件推进 cursor → next_cursor 是扫描到的最大全局序列，不过滤 ✓

### HostEventView 不暴露敏感数据
- 只映射 `event_sequence, event_id, event_type, session_id, run_id, payload_ref, payload_digest` → `_event_view_from_row()` (read_api.py:248-256) ✓
- 不暴露 `policy_decision_json`, `reason_json`, `payload_json` ✓

### Deferred functions
- `retry_run`, `replay_run`, `resolve_wait`, `purge_session` 全部调用 `_raise_unsupported_operation` → (command.py:415-482) ✓
- `_raise_unsupported_operation` 抛出 `UNSUPPORTED_OPERATION, retryable=False, detail=None` → (command.py:520-528) ✓
- 不打开 transaction、不追加 EventLog、不写 idempotency → 函数体仅一行 raise ✓
- 测试验证: `test_deferred_public_functions_are_stable_unsupported_without_writes` 验证 error code/retryable/detail 以及 EventLog/idempotency count 不变 ✓

### Limit validation
- `None` → `HOST_EVENT_STREAM_DEFAULT_LIMIT` (100) ✓
- `limit <= 0` → `INVALID_STATE` ✓
- `limit > HOST_EVENT_STREAM_MAX_LIMIT` (1000) → `INVALID_STATE` ✓
- `bool` 作为 `int` 的子类行为正确: `True`→1 (valid), `False`→0 (INVALID_STATE) ✓

### Package exports
- `__init__.py` 导出所有新增 public 函数 → `get_run`, `stream_run_events`, `purge_session`, `replay_run`, `resolve_wait`, `retry_run` ✓
- `__all__` 列表与导出一致 → (__init__.py:78-142) ✓
- `test_package_exports.py` 白名单已更新 → `EXPECTED_COMMAND_EXPORTS` 包含所有新增导出 ✓
- `dayu.host.api.__all__` 不包含 command/read 函数 ✓

### Docs
- README 更新了 Run facade、deferred facade、stream cursor 说明 ✓
- README 不再声称 Run read/stream 未实现 ✓
- README 保留了 Phase 5/7/11 提醒 → "dispatching / active worker cancel propagation、wait cancellation、recovery classifier" ✓
- README 不包含 final cancel semantics 声明 ✓

### 编码规范
- 所有新增函数有中文 docstring，包含 params/returns/raises ✓
- `_raise_unsupported_operation` 使用 `NoReturn` 类型 ✓
- 无 `Any`、`object`、untyped 参数/返回值 ✓
- 无 `getattr`/`hasattr` 滥用 ✓
- 无 magic string scatter（`"retry_run"` 等是为 error message 提供 context，不属于 dispatch logic） ✓
- 无兼容性 wrapper/compatibility re-export ✓
- 无反向依赖（`dayu.host` 不 import `dayu.engine`/`dayu.fins`/`dayu.service`/`dayu.ui`） ✓

### P4-S3 cancel 语义未被修改
- `admission.py` 未在 diff 中 → cancel 语义完全不变 ✓
- `command.py` 中 `cancel_run`、`cancel_session_runs` 未在 diff 中修改 → ✓

### Test coverage
- `test_get_run_missing_returns_not_found` ✓
- `test_get_run_returns_durable_status_attempt_and_cursor` 覆盖 queued/running/cancelled ✓
- `test_stream_run_events_returns_only_target_run_events` ✓
- `test_stream_run_events_advances_cursor_for_unrelated_scanned_rows` ✓
- `test_stream_run_events_no_scanned_rows_returns_input_cursor` ✓
- `test_stream_run_events_rejects_invalid_limits` 覆盖 limit=0 和 over-max ✓
- `test_stream_run_events_default_limit_is_scan_window` ✓ (见 Finding 2)
- `test_stream_run_events_missing_run_returns_not_found` ✓
- `test_deferred_public_functions_are_stable_unsupported_without_writes` ✓

## Conclusion

**Accepted / no blocking finding.**

共发现 3 个 findings:
- 1 个 **Medium** (Finding 1): `stream_run_events` limit 验证顺序偏离 Plan 文字描述，但实际无安全影响，且 fail-fast 策略本身合理
- 1 个 **Low** (Finding 2): 默认 limit 测试断言隐式依赖序列连续性
- 1 个 **Info** (Finding 3): 终端状态集合在两处重复定义

所有 scope/correctness invariants 验证通过。P4-S3 cancel 语义未受影响。200 测试通过，pyright 0 errors。

## Residual Risks

- Finding 1 若被判定需修复，改动范围很小（将 `_resolve_stream_limit` 调用移到 transaction body 内部，置于 run existence check 之后），不影响其他逻辑
- Finding 2 的断言修正不改变测试覆盖率，仅提升 contract 鲁棒性
- 终端状态集合重复（Finding 3）当前无实际风险，`RunStatus` 在 Phase 4 不会新增终态值
