# WU-STRESS-01 Slice 3 Final Focused Re-Review (AgentDS)

## Gate

- **Gate**: final focused re-review (controller fix verification gate, post Codex final fix)
- **Review role**: AgentDS independent code re-review specialist
- **Review artifact path**: `docs/reviews/wu-stress-01-code-final-rereview-slice3-ds-20260601.md`

## Reviewed Target

- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Slice**: Slice 3 — Sustained watch stress with slow consumer and reconnect
- **Base**: `main`
- **Branch**: `test/host-stress-suite`
- **Scope**: Uncommitted changes in `tests/host/stress_support.py` and `tests/host/test_host_production_stress.py`，仅审查 `docs/reviews/wu-stress-01-code-rereview-slice3-ds-20260601.md` 和 `docs/reviews/wu-stress-01-fix-slice3-codex-20260601.md` 之后的变更
- **Prior review artifacts**:
  - `docs/reviews/wu-stress-01-code-rereview-slice3-ds-20260601.md` (前次 DS re-review，含 F-01/F-02 两个 LOW finding 和两个 Open Question)
  - `docs/reviews/wu-stress-01-fix-slice3-codex-20260601.md` (Codex final fix artifact)
- **Excluded scope**: 生产代码、Slice 1/2/4/5、`docs/` 变更、review artifacts 自身

## Focused Verification Items

### V-01: `consumer_cancel_ok` docstring 不再声称"四步验证"

- **位置**: `tests/host/test_host_production_stress.py:468-477`
- **验证**: docstring 关键句——"本 predicate 只覆盖 diagnostics 中的两个结构化字段：EventLog count 不变、worker 未收到 cancel。"明确注明测试主体单独执行另外两步（public `get_run` 非终态检查 + 释放 worker 后 terminal 检查）。
- **结果**: **PASS**。docstring 与 property 体（仅 2 条件）完全一致，无虚报。

### V-02: `reconnect_ok` 验证 `expected_reconnect_run_id`

- **位置**: 
  - property: `tests/host/test_host_production_stress.py:485-497`
  - 测试体内显式断言: `tests/host/test_host_production_stress.py:1025`
  - diagnostics 构造传参: `tests/host/test_host_production_stress.py:1079`
- **验证**:
  1. `Slice3WatchDiagnostics` 新增 `expected_reconnect_run_id: str` 字段（行 416）
  2. `reconnect_ok` property 检查 `self.expected_reconnect_run_id in _run_ids_from_events(self.secondary_reconnect_events)`（行 496）
  3. 测试体内 `secondary_reconnect_events` 收集后立即 `assert reconnect_run_id in _run_ids_from_events(secondary_reconnect_events)`（行 1025）
  4. diagnostics 构造时 `expected_reconnect_run_id=reconnect_run_id`（行 1079）
- **结果**: **PASS**。三层验证（property 内、测试体断言、参数传递链）均闭合。

### V-03: primary watcher 正常路径不双关

- **位置**: 
  - flag 初始化: `tests/host/test_host_production_stress.py:804`
  - 正常路径关闭+标记: `tests/host/test_host_production_stress.py:1039-1042`
  - finally 兜底: `tests/host/test_host_production_stress.py:1065-1068`
- **验证**:
  1. `primary_watchers_closed = [False for _index in range(_SLICE3_SESSION_COUNT)]` 初始化全为 False
  2. 正常路径中 `close_host_event_iterator(watcher)` 后立即 `primary_watchers_closed[index] = True`
  3. finally 块中仅 `if not primary_watchers_closed[index]` 才执行兜底关闭，并用 `suppress(Exception)` 抑制
- **结果**: **PASS**。正常路径关闭一次并标记；异常路径由 finally 兜底关闭未标记的 watcher；无正常路径双关。

### V-04: per-session lag limit 使用 `_SLICE3_WATCH_LAG_PER_SESSION_LIMIT`

- **位置**:
  - 常量定义: `tests/host/test_host_production_stress.py:94`
  - 使用点: `tests/host/test_host_production_stress.py:515`
- **验证**:
  1. `_SLICE3_WATCH_LAG_PER_SESSION_LIMIT = _SLICE3_RUNS_PER_SESSION`（即 6）
  2. `watch_lag_ok` 中 `max(flattened) < _SLICE3_WATCH_LAG_PER_SESSION_LIMIT`
  3. 旧常量 `_SLICE3_WATCH_LAG_EVENT_TOTAL_LIMIT` 已从 `tests/` 目录完全移除（rg 确认 0 匹配）
- **结果**: **PASS**。per-session 上限 6 对每个 session 最多 6 个 terminal 的场景是紧约束，有实际判别力。

### V-05: 无新问题、无 Slice 4/5、无生产代码

- **验证**:
  1. `git diff --name-only` 仅 `tests/host/stress_support.py` 和 `tests/host/test_host_production_stress.py`
  2. 无生产代码变更
  3. `StressFailureBoundary` 类型定义了 `"active_cleanup"` 和 `"scheduler_close"` 但 Slice 3 的 `failure_boundary` property 仅返回 `"watch"`, `"watch_reconnect"`, `"scheduler"`, `"durable"`, `"projection"`，未使用 Slice 4/5 边界值
  4. 无 Slice 4 scheduler long-run cleanup、无 Slice 5 terminal dedupe 重设计
- **结果**: **PASS**。

## Prior Finding Closure Verification

### 前次 Re-Review F-01: `consumer_cancel_ok` docstring → CLOSED

docstring 已更新为准确描述 2-condition predicate，测试体覆盖完整 4 步验证，不再声称"四步验证"。

### 前次 Re-Review F-02: primary watcher try/finally 双关 → CLOSED

引入 `primary_watchers_closed` flag 列表跟踪关闭状态，正常路径关闭并标记，finally 仅兜底未关闭的 watcher。

### 前次 Re-Review OQ1: `watch_lag_ok` 弱上限 → CLOSED

`_SLICE3_WATCH_LAG_PER_SESSION_LIMIT = _SLICE3_RUNS_PER_SESSION = 6` 替代了旧的 `_SLICE3_WATCH_LAG_EVENT_TOTAL_LIMIT = 18`，上限在每个 session 仅 6 terminal 的场景下是紧约束。

### 前次 Re-Review OQ2: `reconnect_ok` 不验证 run_id → CLOSED

property 内联 `expected_reconnect_run_id in _run_ids_from_events(...)` 检查，测试体另有显式断言。

## Validation Observed

| Command | Result |
|---------|--------|
| `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q` | 1 passed, 2 deselected (0.72s) |
| `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q` | 3 passed (3.85s) |
| `pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q` | 20 passed (0.67s) |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## Findings

未发现实质性问题。

前次 Re-Review 的 2 个 LOW finding 和 2 个 Open Question 全部 CLOSED。5 项 focused verification 全部 PASS。

## Open Questions

无。

## Residual Risk

- 测试场景为确定性 stress，非随机 fuzzing，不覆盖极端时序或高并发竞态。
- `compute_watch_lag` 参数名 `latest_sequence` / `last_seen_sequence` 在 Slice 3 terminal-count watermark 用法下仍有一定误导性，但不影响正确行为。

## Conclusion

**PASS** — 5/5 focused verification items PASS。前次 Re-Review 全部 finding 和 Open Question CLOSED。无新 finding。验证命令全部通过，无生产代码变更，无 Slice 4/5 越界。
