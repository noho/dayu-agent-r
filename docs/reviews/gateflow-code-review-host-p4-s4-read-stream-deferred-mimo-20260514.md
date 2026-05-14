# Code Review: Host P4-S4 Read APIs, Event Stream And Deferred Facade Behavior

- **Reviewer**: MiMo
- **Date**: 2026-05-14
- **Baseline**: P4-S3 accepted slice commit `af61fe9`
- **Review target**: workspace uncommitted diff
- **Design truth**: `docs/host/design.md`
- **Plan truth**: `docs/host/phase4-public-api-command-path-plan.md` (Slice P4-S4)
- **Implementation artifact**: `docs/reviews/gateflow-implementation-host-p4-s4-read-stream-deferred-20260514.md`

## Conclusion

**1 blocking finding.** `stream_run_events` 的 limit 校验先于 Run 存在校验执行，违反 plan 契约中"先校验目标 Run 存在"的顺序。当 missing run + invalid limit 同时存在时，返回 `INVALID_STATE` 而非 plan 契约要求的 `NOT_FOUND`。其余实现正确，无 P4-S3 cancel 语义回归，HostEventView 不泄露敏感字段，deferred 函数无副作用，类型签名严格，无 `Any`/`object`/`getattr`/`hasattr` 滥用，无兼容性 wrapper，无反向依赖。

## Validation Results

```
pytest tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host -q  → 200 passed
python -m pyright dayu/host tests/host  → 0 errors, 0 warnings, 0 informations
git diff --check  → clean
```

## Findings

### F-1 [Blocking] stream_run_events limit 校验先于 Run 存在校验，违反 plan 契约

**文件**: `dayu/host/read_api.py:66-93`

**问题**: `stream_run_events` 在进入 read transaction 之前先调用 `_resolve_stream_limit(limit)` 校验 limit，Run 存在校验在 `_StreamRunEventsOperation.__call__` 内部执行（L164）。当 `limit` 非法且 Run 不存在时，返回 `INVALID_STATE` 而非 plan 契约要求的 `NOT_FOUND`。

**Plan 契约** (`docs/host/phase4-public-api-command-path-plan.md:465`):
> stream_run_events：**先校验目标 Run 存在**（NOT_FOUND if missing），再使用 public constants 和 cursor rules

**实测验证**:
```python
stream_run_events(host, "missing-run", cursor, limit=-1)
# 实际: HostApiError(code=INVALID_STATE, message="Host event stream limit is out of range")
# 契约: HostApiError(code=NOT_FOUND, message="Run not found")
```

**修复建议**: 将 `_resolve_stream_limit` 的调用移入 `_StreamRunEventsOperation.__call__` 中，在 `read_run_by_id` 校验之后执行；或在公开函数中先执行 Run 存在校验（需要一次 read transaction），再校验 limit。

**风险**: 当前测试未覆盖 missing run + invalid limit 的组合场景。`test_stream_run_events_rejects_invalid_limits` 使用已存在的 Run 测 limit 校验，`test_stream_run_events_missing_run_returns_not_found` 使用合法 limit 测 Run 存在校验。

---

### F-2 [Non-blocking / Advisory] bool 作为 limit 的 edge case

**文件**: `dayu/host/read_api.py:191-206`

**问题**: Python `bool` 是 `int` 的子类型。`limit=True` 隐式等于 `limit=1`，通过 `_resolve_stream_limit` 校验并进入数据库查询。签名 `limit: int | None` 不拒绝 `bool` 值。

**实测验证**:
```python
stream_run_events(host, "missing", cursor, limit=True)
# True == 1，通过 limit 校验，进入 Run 存在校验
```

**评估**: 这是 Python 类型系统的已知行为，pyright 也不会对此报错。实际调用方传入 `bool` 的概率极低。非 blocking，记录为 edge case awareness。

---

## Scope 合规性检查

| 检查项 | 结果 |
|--------|------|
| 只实现 P4-S4 允许的函数（get_run、stream_run_events、retry_run、replay_run、resolve_wait、purge_session） | ✅ 通过 |
| 只修改 P4-S4 允许的文件（read_api.py、command.py、测试文件、README） | ✅ 通过 |
| 未修改 P4-S3 cancel 子集语义（cancel_run、cancel_session_runs 代码未变） | ✅ 通过 |
| 未修改 durable foundation（event_log.py、state.py、transaction.py 未变） | ✅ 通过 |

## get_run 合规性检查

| 检查项 | 结果 |
|--------|------|
| missing Run 返回 NOT_FOUND | ✅ `read_api.py:138-144` |
| queued/running/cancelled snapshot status 正确 | ✅ 测试覆盖 `test_get_run_returns_durable_status_attempt_and_cursor` |
| `current_attempt_id` 来自 Run row | ✅ `run_snapshot_from_row` 透传 |
| `event_cursor` 是 max non-null sequence | ✅ `run_snapshot_from_row` 逻辑，测试用 `_known_run_event_cursor` 验证 |
| terminal `terminal_result_summary` 是 status-only fallback | ✅ `read_api.py:229-233`，`summary_ref=None, summary_digest=None` |
| 非终态 `terminal_result_summary=None` | ✅ `read_api.py:222-223` |
| `outbox_summary=None` | ✅ `read_api.py:237` |

## stream_run_events 合规性检查

| 检查项 | 结果 |
|--------|------|
| 先校验 Run 存在再扫描 EventLog | ✅ `read_api.py:164-169`（但 F-1：limit 校验更早） |
| 使用全局 EventLog `event_sequence` cursor | ✅ `read_events_after(transaction, cursor.event_sequence, limit)` |
| limit=None 使用 DEFAULT_LIMIT | ✅ `read_api.py:199` |
| limit<=0 或 >MAX 返回 INVALID_STATE | ✅ `read_api.py:200-205` |
| limit 是全局扫描窗口 | ✅ 传入 `read_events_after` 的 `limit` 参数 |
| 按 `run_id` 过滤 | ✅ `read_api.py:185`：`row.run_id == self.run_id` |
| empty filtered result + scanned unrelated rows → advance next_cursor | ✅ `read_api.py:178-180`，测试覆盖 |
| no scanned rows → next_cursor == input cursor | ✅ `read_api.py:175-176`，测试覆盖 |
| HostEventView 不暴露 policy_decision/reason/payload_json | ✅ `_event_view_from_row` 只映射 7 个字段 |

## Deferred 函数合规性检查

| 检查项 | 结果 |
|--------|------|
| retry_run raises UNSUPPORTED_OPERATION | ✅ `command.py:429` |
| replay_run raises UNSUPPORTED_OPERATION | ✅ `command.py:446` |
| resolve_wait raises UNSUPPORTED_OPERATION | ✅ `command.py:463` |
| purge_session raises UNSUPPORTED_OPERATION | ✅ `command.py:482` |
| retryable=False | ✅ `command.py:531` |
| detail=None | ✅ `command.py:533` |
| 不写 EventLog | ✅ 测试验证 event_count 不变 |
| 不写 idempotency record | ✅ 测试验证 idempotency_count 不变 |
| closed handle 行为 | ✅ 函数不读取 handle，直接 raise |

## 导出与 README 检查

| 检查项 | 结果 |
|--------|------|
| `__init__.py` 导出新增函数 | ✅ `get_run`, `stream_run_events`, `retry_run`, `replay_run`, `resolve_wait`, `purge_session` |
| `test_package_exports.py` 白名单同步 | ✅ `EXPECTED_COMMAND_EXPORTS` 已更新 |
| README 不声称 final cancel 语义 | ✅ 明确标注 Phase 5/7/11 |
| README 只写当前事实 | ✅ 无"未来设计" |
| Phase 5/7/11 reminder 保留 | ✅ README L49, L113 |

## 编码规范检查

| 检查项 | 结果 |
|--------|------|
| 中文 docstring（函数、类、模块） | ✅ 全部覆盖 |
| 严格类型签名（无 `Any`、`object`、无类型参数） | ✅ |
| 无 `getattr`/`hasattr` 滥用 | ✅ |
| 无兼容性 wrapper / re-export | ✅ |
| 无反向依赖（read_api 不导入 engine/fins/service/ui） | ✅ |
| `frozen=True, slots=True` dataclass | ✅ `_GetRunOperation`, `_StreamRunEventsOperation` |
| 无 God object / God function | ✅ |
| 无魔法数字 / 魔法字符串 | ✅ 常量来自 `dayu.host.api` |
