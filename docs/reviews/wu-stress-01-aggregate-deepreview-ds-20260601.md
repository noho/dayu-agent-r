# WU-STRESS-01 Aggregate Deepreview — AgentDS

## Gate

- **Gate**: aggregate deepreview (WU-STRESS-01 final review before PR)
- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Review role**: AgentDS aggregate deepreview specialist
- **Output file**: `docs/reviews/wu-stress-01-aggregate-deepreview-ds-20260601.md`
- **Review date**: 2026-06-01
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`

## Scope

- **Mode**: current changes (aggregate review of full branch diff against main)
- **Branch**: `test/host-stress-suite`
- **Base**: `main`
- **Included scope**:
  - `pyproject.toml` — stress marker registration + default exclusion
  - `tests/host/stress_support.py` — stress test helpers (~1410 lines, new file)
  - `tests/host/test_host_production_stress.py` — stress tests (~2583 lines, new file)
  - `tests/README.md` — stress marker / command / summary contract documentation
  - `docs/host/wu-stress-01-host-production-stress-suite-plan.md` — planning artifact (read-only for review)
  - `docs/host/host-core-followup-implementation-control.md` — status updates (read-only for review)
  - All 40 WU-STRESS-01 review artifacts under `docs/reviews/wu-stress-01-*.md` (as prior evidence)
- **Excluded scope**: Production code (`dayu/`), review artifacts from other work units, pre-existing tests
- **Parallel review coverage**: 无（单 reviewer 全量走读；所有 5 个 slice 的 prior review artifacts 已在 controller 闭环中完成 separate DS/MiMo review、fix、re-review、controller adjudication）

## Review Pass/Fail

**PASS**

No findings of HIGH or CRITICAL severity. All findings from prior slice-level reviews have been adjudicated and closed by the controller. Two LOW severity findings from prior re-reviews remain as known, non-blocking items. No new findings identified in the aggregate review. Residual risks are well-understood, documented, and within the plan's declared non-goals.

## Cross-Cutting Verification

### 1. No production code / public contract / schema / layering violation

- `git diff main...HEAD --name-only | grep -v 'docs/reviews/'` yields only: `pyproject.toml`, `tests/host/stress_support.py`, `tests/host/test_host_production_stress.py`, `tests/README.md`, `docs/host/wu-stress-01-host-production-stress-suite-plan.md`, `docs/host/host-core-followup-implementation-control.md`
- `grep -rn "stress_support" dayu/` → zero matches
- Zero `dayu/` files modified
- `stress_support.py` imports only from `dayu.host` (Host public API), `dayu.host.durable.codec` (durable decode), `dayu.host.durable.liveness` (liveness enum), `dayu.runtime.lane` (lane public contract), and `tests.host.public_smoke_support` / `tests.host.recovery_support` (existing test helpers)
- No reverse imports; Host public API exports unchanged; durable schema unchanged; EventLog semantics unchanged; recovery state machine unchanged; scheduler production behavior unchanged

### 2. Correctness — stress marker and default exclusion

- `pyproject.toml:138-141`: `addopts = "-m 'not stress'"` with registered `stress` marker — exactly matches plan specification
- `tests/host/test_host_production_stress.py:73`: module-level `pytestmark = pytest.mark.stress`
- All 5 stress test functions carry `@pytest.mark.timeout(...)` with explicit time budgets:
  - `test_stress_marker_summary_contract` → 5s
  - `test_mixed_host_stress_deterministic_fault_injection` → 120s
  - `test_scheduler_liveness_long_run_mixed_flow_stress` → 90s
  - `test_repeated_startup_recovery_crash_stress` → 60s
  - `test_sustained_watch_slow_consumer_reconnect_stress` → 90s

### 3. Correctness — controller validation evidence alignment

The controller's stated validation results align with the code structure:

| Validation claim | Evidence alignment |
|---|---|
| Markers pass | `pytest --markers` shows `stress` + `timeout` from pre-existing `pytest-timeout>=2.1.0` in `pyproject.toml:82` |
| Default 10 passed, 5 deselected | `addopts = "-m 'not stress'"` deselects the 5 `stress`-marked tests; `test_package_exports.py` and non-stress tests pass |
| Explicit stress 5 passed | `-o addopts="" -m stress` overrides default exclusion, runs all 5 stress tests |
| Collect-only default: 0 collected, 5 deselected | Confirmed by `addopts = "-m 'not stress'"` deselecting all tests in the stress file |
| Override collect-only: 5 collected | Confirmed by `-o addopts=""` override |
| Recovery/watch/dispatch/liveness: 75 passed | The 3 `pytest` commands for `test_recovery_multiprocess.py`, `test_watch_session_events.py`, `test_dispatch_scheduler.py`, `test_host_instance_liveness.py` and related files — no stress marker on these files, so default pytest runs them as usual |
| tests/host: 1044 passed, 1 skipped, 5 deselected | Consistent with stress marker excluding 5 tests from 1050 |
| pyright 0 errors | Verified no `Any`/`object`/bare container annotations in the new code |

### 4. Determinism / flakiness assessment

- All stress scenarios use fixed-size loops (`_CRASH_CYCLE_COUNT=3`, `_SLICE3_RUN_COUNT=18`, `_SLICE5_RUN_COUNT=15`, etc.)
- Worker behavior is fully scripted via `DeterministicStressWorkerFactory` with `StressWorkerBehavior` enum — no randomness
- `_NOW = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)` — fixed timestamp for deterministic EngineEvent output
- Process crash uses `multiprocessing.Process` + marker files — deterministic multi-process coordination
- Stale owner fault injection via `force_owner_pid_missing_and_heartbeat_stale()` — same mechanism as existing `recovery_support.py`
- Blocking workers use `asyncio.Event` release gates — no `time.sleep()` for correctness
- Short sleep intervals (`POLL_INTERVAL_SECONDS=0.01`, `delay_seconds=0.02-0.035`) are bounded and have explicit `timeout_seconds` deadlines

**Risk of flakiness: LOW** — the suite is designed for determinism, not random fuzz. The plan explicitly declares this is within scope.

### 5. Type / docstring constraints

- All 22 public module-level functions/classes/dataclasses in `stress_support.py` have complete Chinese docstrings (parameters, returns, raises)
- All 16 private helper functions in `test_host_production_stress.py` have complete Chinese docstrings
- All 5 diagnostic dataclasses have frozen slots, complete Chinese docstrings, and typed properties
- `StressFailureBoundary` is a closed `Literal` type alias — no unrestricted string
- `StressSummaryJsonValue` is a closed `TypeAlias` for JSON-serializable values
- Zero `Any`, `object`, bare `dict`/`list` annotations in the entire diff
- `StressWorkerBehavior` is a `StrEnum` — closed enum, not bare string

### 6. Docs / README sync

- `tests/README.md:29-32`: Documents that default pytest excludes `stress` marker
- `tests/README.md:32`: Documents explicit stress run command `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q`
- `tests/README.md:133-138`: Documents stress suite under `tests/host/` section with marker policy, command, summary JSON field contract, and `failure_boundary` constraints
- Root `README.md`: Not updated (correct — stress marker/exclusion is a test infrastructure detail, not a user-facing entry point)
- Host README: Not updated (correct — Host public contract, durable schema, recovery/scheduler behavior unchanged)
- `docs/host/host-core-followup-implementation-control.md`: Status updated to reflect WU-STRESS-01 implementation completion

### 7. Prior review finding closure verification

All controller-adjudicated findings from slices 1-5 have been verified as closed:

| Slice | Finding | Status |
|---|---|---|
| 1 | All initial review findings adjudicated | CLOSED — marker, summary, helper base established |
| 2 | All review findings adjudicated (recovery/crash/live-owner) | CLOSED |
| 3 | 7/7 controller-accepted findings (race fix, docstrings, magic numbers, gap diagnostics, per-session lag, redundant tuple) | CLOSED — verified in DS re-review |
| 4 | 7/7 controller-accepted findings (RUN_LOST dedupe, dead code, constants dedup, lane_db_path, stale threshold docs, LOST terminal semantics, docstring) | CLOSED — verified in DS re-review |
| 5 | 2/2 controller-accepted findings (PRIMARY_TERMINAL_COUNTS comment, timeout summary consistency) | CLOSED — verified in DS re-review |

## Findings

### DS-AGG-01 · 未修复 · LOW · `consumer_cancel_ok` property docstring 声称"四步验证"但实际检查 2/4 条件

- **入口/函数**: `Slice3WatchDiagnostics.consumer_cancel_ok` property
- **文件(行号)**: `tests/host/test_host_production_stress.py:502-516`
- **输入场景**: 读取 `consumer_cancel_ok` 属性判断 consumer cancel 验证是否通过
- **实际分支**: property 仅检查 `event_log_count_before == event_log_count_after` 且 `worker_cancel_count == 0`
- **预期行为**: docstring 写"consumer cancel 四步验证"（测试主体单独执行四步验证中的 public `get_run` 非终态检查和释放 worker 后正常 terminal 检查），但 property 自身仅检查 2/4
- **实际行为**: 测试主体中 4 步全部覆盖（`assert not _is_terminal_status(...)` + `_wait_run_status(..., SUCCEEDED)`），但 property 的 `failure_boundary` 映射到 `"watch"` 时只依赖 2/4 条件
- **直接证据**: `test_host_production_stress.py:502-516` property body vs `test_host_production_stress.py:1789-1798` test body 中的补充断言
- **影响**: 若未来测试复用 `consumer_cancel_ok` 而不重现测试体的显式断言，会漏检 active run 非终态验证和释放后正常 terminal 验证
- **建议改法和验证点**: 将 docstring 精确化为"consumer cancel 二步验证（EventLog count 不变 + worker 未收到 cancel），另两步由测试主体显式断言完成"；或在 property 中内联完整 4 步（需传入 active run_id 和 host handle）
- **修复风险（低）**: docstring 修改无风险
- **严重程度（低）**: 当前测试体中 4 步全部覆盖，不阻塞合入。此 finding 继承自 Slice 3 DS re-review F-01，尚未修复但已知

### DS-AGG-02 · 未修复 · LOW · primary watcher try/finally 双关路径可掩盖清理不完整

- **入口/函数**: `test_sustained_watch_slow_consumer_reconnect_stress` finally 块
- **文件(行号)**: `tests/host/test_host_production_stress.py:2001-2014`
- **输入场景**: try 块正常路径中已关闭全部 `primary_watchers`（行 1986-1988），finally 块再次遍历关闭
- **实际分支**: finally 块无条件执行 `close_host_event_iterator(watcher)` 并以 `suppress(Exception)` 抑制异常
- **预期行为**: 正常路径关闭已关闭的 generator 时 `aclose()` 是 no-op（PEP 525），行为正确但掩盖 try 块中部分 watcher 因条件跳过或异常中断而未关闭的 bug
- **直接证据**: `test_host_production_stress.py:1986-1988`（try 块关闭）与 `test_host_production_stress.py:2011-2014`（finally 块关闭）
- **影响**: 当前无功能影响；`suppress(Exception)` 在未来 try 块路径新增异常分支时可能静默吞掉真实错误
- **建议改法和验证点**: 用 flag 跟踪哪些 watcher 已在 try 块关闭，finally 中仅关闭未关闭的
- **修复风险（低）**: 重构清理逻辑范围小
- **严重程度（低）**: 不影响当前测试正确性。此 finding 继承自 Slice 3 DS re-review F-02，尚未修复但已知

## Open Questions

1. **`watch_lag_ok` 中 `max(flattened) < _SLICE3_WATCH_LAG_PER_SESSION_LIMIT` 是弱断言**: `_SLICE3_WATCH_LAG_PER_SESSION_LIMIT = _SLICE3_RUNS_PER_SESSION = 6`，而 per-session lag 基于 terminal count watermark，不可能超过 6。实际有效约束来自 `final_watch_lags_by_session` 的 drain-to-0 检查。该上限不提供额外判别力，可作为未来 scale-up 的预留闸门。

2. **`reconnect_ok` 仅检查 terminal 计数，不验证 run_id 归属**: secondary watcher 重连后消费 `expected_count=1` 条 terminal，断言仅验证计数，不验证该事件的 `run_id` 确实是 `expected_reconnect_run_id`。在当前确定性场景下安全（重连后仅提交一个 run），但若未来场景在重连后提交多个 run，计数断言可能漏检错位事件。注：Slice 3 测试体在行 1971 对 `reconnect_run_id` 做了显式断言 `assert reconnect_run_id in _run_ids_from_events(secondary_reconnect_events)`，但 `reconnect_ok` property 未纳入此检查。

## Residual Risk

1. **pytest-timeout SIGTERM 会绕过内部 timeout summary**: `pytest-timeout` 120s 全局超时可在 event loop 全局阻塞时 SIGTERM 整个进程，此时 `_slice5_timeout_summary` 不会执行。这是 pytest-timeout 的固有局限，无法在测试代码内修复，已在 Slice 5 controller adjudication 中接受。

2. **`max(summary_watch_lag_samples)` 在空 tuple 上会抛出 `ValueError`**: 当前所有 5 个 stress tests 都保证 `watch_lag_samples` 非空（Slice 2/4 使用 placeholder `(0,)`，Slice 3/5 有至少 3 个 session 的采样），但若未来新增不采样 watch lag 的 stress test 且错误地使用非空占位，会在 summary 构造时崩溃。已在 Slice 5 DS re-review residual risk 中记录。

3. **`HostEventKind` 无 `LOST` 成员**: `RUN_LOST` 是 durable/public snapshot 终态但不是 `HostEventKind`，因此 `terminal_events_for_runs()` 只能返回 succeeded/failed/cancelled observation。当前通过 `terminal_event_count_for_runs()` 的两层去重证明（含 `RUN_LOST` 的 EventLog 总 terminal 数等于 public terminal snapshot 数）间接覆盖。若未来 `HostEventKind` 新增 `LOST`，需同步更新 `_terminal_kind_for_event_type()`。

4. **`compute_watch_lag` 参数语义偏移**: Slice 3/5 将函数参数名 `latest_sequence` / `last_seen_sequence` 用于 terminal-count watermarks 而非 event sequence numbers。函数体 `max(0, a - b)` 对两者语义等价，但参数名对 count 用法有误导性，未来维护者可能误解意图。已在 Slice 3 DS re-review residual risk 中记录。

5. **Deterministic bounded coverage**: stress suite 是确定性有界场景（3-5 sessions, 15-30 runs, 1-3 crash cycles），不是随机 fuzz 或长时间 soak。极端时序、高并发竞态、资源耗尽等场景不在覆盖范围内。这在 plan 的 non-goals 中已明确声明。

6. **`verify_lane_released` False 分支未测试**: lane 未释放时返回 `False` 的路径当前在 stress 测试中未被触发覆盖。该路径仅在 Host close 失败或 lane claim 泄漏时可达，属于负面路径。

## Review Conclusion

**PASS** — WU-STRESS-01 的完整 diff 满足 correctness、determinism、marker exclusion、docs sync、type/docstring 约束，无 production code / public contract / schema / layering violation。

5 个 stress tests 覆盖 plan 定义的全部 5 个 slice：marker sentinel、repeated crash/recovery E2E、sustained watch with reconnect、scheduler/liveness long-run mixed flow、mixed Host deterministic fault injection。Controller 验证数据（1044 passed, 5 deselected in default; 5 passed in explicit stress; pyright 0 errors）与代码证据一致。

两个 LOW severity findings（consumer_cancel_ok docstring + try/finally 双关）继承自 prior slice re-reviews，已知且非阻塞。Residual risks 在 plan 的 non-goals 内，且 controller 已在各 slice adjudication 中接受。

Ready for PR.
