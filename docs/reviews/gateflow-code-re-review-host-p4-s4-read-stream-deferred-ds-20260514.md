# Host P4-S4 Read Stream Deferred —— Re-Review (AgentDS)

## 审查范围

- **Re-review target**: 上一轮 AgentDS review 中 Finding 1 (Medium) 与 Finding 2 (Low) 的 fix，以及所有 collateral changes
- **Baseline**: 上一轮 AgentDS review artifact `docs/reviews/gateflow-code-review-host-p4-s4-read-stream-deferred-ds-20260514.md`
- **Gate**: Phase 4 Implementation, Slice P4-S4

## 变更摘要

### `dayu/host/read_api.py` —— 验证顺序修正

**修复前** (`_resolve_stream_limit` 在事务外，先于 Run 存在性检查):
```python
def stream_run_events(...):
    resolved_limit = _resolve_stream_limit(limit)  # ← 在事务外
    return host._run_read(_StreamRunEventsOperation(..., limit=resolved_limit))
```

**修复后** (Run 存在性检查在事务内先于 limit 解析):
```python
def stream_run_events(...):
    return host._run_read(_StreamRunEventsOperation(..., limit=limit))  # 传原始值

class _StreamRunEventsOperation:
    limit: int | None  # ← 从 int 改为 int | None

    def __call__(self, transaction):
        if read_run_by_id(transaction, self.run_id) is None:  # ← 先检查 Run
            raise HostApiError(NOT_FOUND)
        resolved_limit = _resolve_stream_limit(self.limit)     # ← 再解析 limit
        scanned = read_events_after(...)                       # ← 最后扫描
```

关键变化:
- `_StreamRunEventsOperation.limit` 类型从 `int` 改为 `int | None`，直接接收原始调用方参数
- `_resolve_stream_limit` 从 `stream_run_events` 函数体移入 `_StreamRunEventsOperation.__call__`，置于 Run 存在性检查之后
- EventLog 扫描仅在 Run 存在且 limit 合法后执行

### `tests/host/test_public_event_stream.py` —— 测试加固

**新增辅助函数** `_max_scanned_event_sequence(db_path, cursor, limit)`:
- 用独立 DB 查询计算 scan-window contract 下应推进到的 event_sequence
- 使用 `LIMIT 1 OFFSET (limit - 1)` 获取窗口内最后一行
- 窗口超出实际行数时 fallback 到 `MAX(event_sequence) WHERE event_sequence > cursor`
- 完全不依赖 SQLite auto-increment 连续性假设

**新增测试** `test_stream_run_events_missing_run_invalid_limit_returns_not_found`:
- 覆盖 `limit=0 + missing run` → NOT_FOUND
- 覆盖 `limit=-1 + missing run` → NOT_FOUND
- 覆盖 `limit=max+1 + missing run` → NOT_FOUND

**修正测试** `test_stream_run_events_default_limit_is_scan_window`:
- 断言从 `next_cursor == cursor + HOST_EVENT_STREAM_DEFAULT_LIMIT` 改为 `next_cursor == _max_scanned_event_sequence(db_path, cursor, DEFAULT_LIMIT)`
- 不再隐式依赖 EventLog 序列连续性

**文档微调** `test_stream_run_events_rejects_invalid_limits` docstring:
- `"""stream_run_events 拒绝非正 limit 和超过 public 最大值的 limit。"""` → `"""已有 Run 时 stream_run_events 拒绝非法 limit。"""`

## 逐项验证

### 1. Missing Run 在 _resolve_stream_limit 之前验证

- **read_api.py:163-168**: `read_run_by_id(transaction, self.run_id) is None` → 抛出 NOT_FOUND
- **read_api.py:169**: `_resolve_stream_limit(self.limit)` 仅在 Run 存在后才执行
- **结论**: ✓ Fixed

### 2. Missing Run + limit 0 / 负值 / 超 max 均返回 NOT_FOUND

- **test_public_event_stream.py:287-312**: 新增测试覆盖 `limit=0`, `limit=-1`, `limit=max+1` 三种非法 limit 与 missing run 的组合，全部断言 `NOT_FOUND`
- **结论**: ✓ Fixed

### 3. 已有 Run + 非法 limit 仍返回 INVALID_STATE

- **test_public_event_stream.py:262-284**: `test_stream_run_events_rejects_invalid_limits` 先创建有效 Run，再传入 `limit=0` 和 `limit=max+1`，断言 `INVALID_STATE`
- **结论**: ✓ 无回归

### 4. EventLog 扫描仅在 Run 存在且 limit 合法后发生

- **read_api.py:170-174**: `read_events_after(...)` 调用在 `read_run_by_id` (line 163) 和 `_resolve_stream_limit` (line 169) 之后
- **结论**: ✓ 执行顺序正确

### 5. 默认 limit 测试使用实际最大扫描 event_sequence

- **test_public_event_stream.py:335-339**: 使用 `_max_scanned_event_sequence(db_path, cursor, DEFAULT_LIMIT)` 独立计算期望值
- `_max_scanned_event_sequence` (lines 147-180) 通过 SQLite OFFSET 查询直接定位扫描窗口末尾行，不依赖序列连续性
- **结论**: ✓ Fixed

### 6. 无 P4-S4 scope creep

- 修改文件仅限于 `read_api.py` 和 `test_public_event_stream.py`
- 无新增 public API、类型、常量或行为
- `command.py`, `admission.py`, `state.py`, `__init__.py`, `README.md` 均未在本次修复中变更
- **结论**: ✓ 无 scope creep

### 7. 无 P4-S3 cancel 语义修改

- `command.py` cancel_run / cancel_session_runs 未变
- `admission.py` 未变
- `state.py` 未变
- **结论**: ✓ 无 P4-S3 变更

### 8. 编码规范

- `_max_scanned_event_sequence` 有完整中文 docstring (params/returns)
- `_StreamRunEventsOperation.limit` 类型为 `int | None`，严格类型化
- 无 `Any`/`object`/untyped、无 `getattr`/`hasattr`、无 magic string scatter
- **结论**: ✓ 规范合规

## 验证结果

```
source .venv/bin/activate && pytest tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host -q
→ 201 passed in 2.07s  (+1 新增 missing_run_invalid_limit test)

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ passed (no whitespace issues)
```

## Residual

- Finding 3 (Info): `_TERMINAL_RUN_STATUSES` 与 `state.py` `_is_terminal_run_status` 的重复定义仍在。非阻塞，两处当前语义一致。

## Conclusion

**Fixed. No blocking findings.**

上一轮 AgentDS review 的 Finding 1 (Medium, validation order) 和 Finding 2 (Low, test contiguity dependency) 均已正确修复。新增 missing run + invalid limit 组合测试覆盖三种非法 limit 值，默认 limit 测试改为使用独立 DB 查询验证 contract。无回归，无 scope creep，无 P4-S3 语义变更。201 测试通过，pyright 0 errors。
