# WU-STRESS-01 Slice 3 Final Focused Re-Review (AgentMiMo)

## Gate

- **Gate**: final focused re-review (controller fix verification gate)
- **Review role**: AgentMiMo final verification
- **Review artifact path**: `docs/reviews/wu-stress-01-code-final-rereview-slice3-mimo-20260601.md`

## Reviewed Target

- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Slice**: Slice 3 — Sustained watch stress with slow consumer and reconnect
- **Base**: `main`
- **Branch**: `test/host-stress-suite`
- **Scope**: Uncommitted changes in `tests/host/stress_support.py` and `tests/host/test_host_production_stress.py`
- **Prior review artifacts**:
  - `docs/reviews/wu-stress-01-code-rereview-slice3-ds-20260601.md` (DS re-review)
  - `docs/reviews/wu-stress-01-fix-slice3-codex-20260601.md` (Codex fix)
- **Excluded scope**: Production code, Slice 1/2/4/5 behavior, `docs/` changes, review artifacts themselves

## Verification Checklist

### 1. `consumer_cancel_ok` docstring exact

**PASS**

- **文件**: `test_host_production_stress.py:467-481`
- **docstring 内容**: "测试主体单独执行四步验证中的 public ``get_run`` 非终态检查和释放 worker 后正常 terminal 检查；本 predicate 只覆盖 diagnostics 中的两个结构化字段：EventLog count 不变、worker 未收到 cancel。"
- **property 体**: 仅检查 `event_log_count_before == event_log_count_after` 且 `worker_cancel_count == 0`
- **测试体补充**: 行 848 `assert not _is_terminal_status(probe_after_consumer_cancel.status)` 和行 852 `await _wait_run_status(host, probe_run_id, RunStatus.SUCCEEDED)` 覆盖剩余两步
- **结论**: docstring 精确描述了 property 自身覆盖的 2/4 条件，并明确说明测试主体单独执行剩余 2 步。无语义膨胀或遗漏。

### 2. `reconnect_ok` proves `expected_reconnect_run_id`

**PASS**

- **文件**: `test_host_production_stress.py:484-497` (property) 和 `test_host_production_stress.py:1017-1025` (test body)
- **property 条件**: `self.expected_reconnect_run_id in _run_ids_from_events(self.secondary_reconnect_events)`
- **显式断言**: 行 1025 `assert reconnect_run_id in _run_ids_from_events(secondary_reconnect_events)`
- **`expected_reconnect_run_id` 字段**: 在 `Slice3WatchDiagnostics` dataclass 中声明（行 416），构造时传入 `reconnect_run_id`（行 1079）
- **结论**: `reconnect_ok` 不仅检查 terminal 计数，还要求 secondary reconnect watcher 观测到的事件包含指定 `expected_reconnect_run_id`。测试体中也有独立显式断言。双重保障。

### 3. Primary watchers are not double-closed on normal path

**PASS**

- **文件**: `test_host_production_stress.py:1040-1042` (normal close) 和 `test_host_production_stress.py:1065-1068` (finally fallback)
- **正常路径**: 行 1040-1042 遍历关闭所有 primary watcher 并设置 `primary_watchers_closed[index] = True`
- **finally 兜底**: 行 1065-1068 检查 `if not primary_watchers_closed[index]`，仅对未关闭的 watcher 执行 `close_host_event_iterator`
- **结论**: `primary_watchers_closed` flag 正确跟踪关闭状态，正常路径关闭后 finally 不再重复关闭。无 double-close 风险。

### 4. Per-session lag limit uses `_SLICE3_WATCH_LAG_PER_SESSION_LIMIT`

**PASS**

- **常量定义**: 行 94 `_SLICE3_WATCH_LAG_PER_SESSION_LIMIT = _SLICE3_RUNS_PER_SESSION`
- **使用位置**: `watch_lag_ok` property 行 515 `max(flattened) < _SLICE3_WATCH_LAG_PER_SESSION_LIMIT`
- **结论**: 替换了先前的硬编码或跨 session 常量，使用 per-session 命名常量。语义清晰。

### 5. No new issues

**PASS**

- DS re-review 的 F-01（`consumer_cancel_ok` docstring 声称"四步验证"但仅检查 2/4）已修复：docstring 现在精确描述为"两个结构化字段"
- DS re-review 的 F-02（primary watcher try/finally 双关）已修复：引入 `primary_watchers_closed` flag
- DS re-review 的 Open Question #2（`reconnect_ok` 仅检查 terminal 计数）已修复：增加 `expected_reconnect_run_id` 检查
- 无新增 BLOCKING/HIGH/MEDIUM findings

### 6. No Slice 4/5

**PASS**

- 无 scheduler long-run cleanup、active task/registry 残留验证
- 无 `InspectableStressWorkerFactory` 或 Slice 4 特有 helper
- 无 Slice 5 terminal dedupe 重设计
- `failure_boundary` 值 `"active_cleanup"` 和 `"scheduler_close"` 在 `StressFailureBoundary` 类型中已定义但 Slice 3 不使用

### 7. No production code

**PASS**

```text
git diff --name-only → tests/host/stress_support.py
                       tests/host/test_host_production_stress.py
```

仅测试文件，无 `dayu/` 生产代码变更。

## Validation Observed

| Command | Result |
|---------|--------|
| `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q` | 1 passed, 2 deselected (0.71s) |
| `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q` | 3 passed (3.82s) |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## Findings

未发现实质性问题。

DS re-review 的 2 个 LOW findings 和 2 个 Open Questions 均已在 Codex fix 中解决：
- F-01 docstring 精确化 → 已修复
- F-02 try/finally 双关 → 已修复
- Open Question #1（`max(lag) < 18` 弱断言）→ 常量已替换为 `_SLICE3_WATCH_LAG_PER_SESSION_LIMIT = _SLICE3_RUNS_PER_SESSION`，语义更清晰
- Open Question #2（`reconnect_ok` 不验证 run_id）→ 已修复

## Open Questions

无。

## Residual Risk

- **Deterministic stress scenario**: Slice 3 是确定性 bounded scenario，验证了 watch/reconnect/cancel/dedupe/lag 的 plan 约定行为。它不是随机 fuzzing，不覆盖极端时序、高并发竞态或资源耗尽场景。
- **Per-session watch lag**: 基于 terminal-count watermarks 的测试诊断，不是生产 replay cursor 或 public watch SLO。
- **`_drain_observed_event_count` 隐式队列合约**: 假设 `observed_events` Queue 中仅包含 terminal HostEvent（由 `consume_terminals` 保证）。当前安全，但队列合约是隐式的。

## Conclusion

**PASS** — 全部 7 项验证检查通过。DS re-review 的 2 个 LOW findings 和 2 个 Open Questions 均已在 Codex fix 中解决，无新增 findings。所有验证命令通过（3 stress tests, pyright 0 errors）。无生产代码变更，无 Slice 4/5 越界行为。
