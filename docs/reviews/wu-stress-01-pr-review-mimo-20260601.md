# WU-STRESS-01 PR Review — AgentMiMo

## Gate

- **Gate**: draft PR review (WU-STRESS-01)
- **Work Unit**: WU-STRESS-01 Host Production Stress Suite
- **PR**: https://github.com/noho/dayu-agent-r/pull/102
- **Branch**: `test/host-stress-suite` -> `main`
- **isDraft**: true
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Review date**: 2026-06-01
- **Reviewer**: AgentMiMo

## Scope

- **Mode**: PR diff against main
- **Included scope**:
  - `pyproject.toml` — stress marker registration + default exclusion (4 lines added)
  - `tests/host/stress_support.py` — stress test helpers (1411 lines, new file)
  - `tests/host/test_host_production_stress.py` — stress tests (2583 lines, new file)
  - `tests/README.md` — stress marker / command / summary contract documentation
  - `docs/host/wu-stress-01-host-production-stress-suite-plan.md` — planning artifact (754 lines, new file)
  - `docs/host/host-core-followup-implementation-control.md` — status updates
  - 45 `docs/reviews/wu-stress-01-*.md` artifacts (aggregate reviews, slice reviews, controller adjudications)
- **Excluded scope**: Production code (`dayu/`), pre-existing tests

## Review Pass/Fail

**PASS**

无 HIGH 或 CRITICAL severity findings。发现 1 个 LOW severity observation，不阻塞 merge。以下逐项给出审查证据。

## Findings

### F-01 [LOW] `StressWorkerBehavior.CLEAN_EOF` 枚举成员已定义但从未被任何测试使用

- **文件/行号**: `tests/host/stress_support.py:231`
- **直接证据**: `CLEAN_EOF = "clean_eof"` 在 `StressWorkerBehavior` 中定义，但 `grep -n CLEAN_EOF tests/host/test_host_production_stress.py` 返回 0 匹配。`DeterministicStressWorkerHandle.events()` 方法（`stress_support.py:281-300`）没有显式处理 `CLEAN_EOF` 分支——它落入最后的 `return` 语句（line 300），产出空 event stream。
- **影响**: Plan Slice 1 Decision 5 明确列出 `clean_eof` 作为 "用于 scheduler failed closeout" 的脚本行为。当前实现支持该行为（空 generator 触发 scheduler timeout closeout），但没有任何测试实际使用它。这是一个测试覆盖缺口，而非功能缺失。scheduler 的 timeout-based closeout 路径已有 `STREAM_EXCEPTION` 间接覆盖（`RUN_LOST` terminal），但 clean EOF（无异常、无 terminal 的正常 stream 结束）这一具体语义路径未被显式测试。
- **建议修复**: 在后续 hardening work unit 中增加一个使用 `StressWorkerBehavior.CLEAN_EOF` 的测试场景，或在本 PR 中为 Slice 4/5 增加一个 clean EOF run。如果决定不覆盖，应在 residual risk 中记录该路径由 scheduler timeout closeout 间接覆盖。
- **Severity**: LOW — 功能路径由 scheduler 生产代码的 timeout 机制保护，不阻塞当前 WU 验收。

### F-02 [INFO] 总控文档 gate 状态与 PR 实际状态存在轻微不一致

- **文件/行号**: `docs/host/host-core-followup-implementation-control.md:119`
- **直接证据**: 总控文档当前状态行显示 `gate | ready-to-open-draft-PR`，但 PR #102 已实际创建（draft PR gate 已开始）。根据 plan 的状态约定，draft PR 打开后 gate 应更新为 `draft-PR-in-progress` 或类似中间态。
- **影响**: 仅文档时效性问题，不影响代码正确性或测试行为。PR merge 后 gate 将更新为 `draft-PR-pass`。
- **建议修复**: PR merge 后在后续状态更新中将 gate 更新为 `draft-PR-pass`。当前不阻塞 merge。
- **Severity**: INFO — 纯文档同步问题，总控文档在 PR merge 后自然收敛。

## Cross-Cutting Verification

### 1. Plan 合约一致性

- **Allowed files 合规**: `git diff main...HEAD --name-only | grep -v 'docs/reviews/'` 输出的非 artifact 文件仅为 `pyproject.toml`、`tests/README.md`、`tests/host/stress_support.py`、`tests/host/test_host_production_stress.py`、`docs/host/wu-stress-01-host-production-stress-suite-plan.md`、`docs/host/host-core-followup-implementation-control.md`，均为 plan 允许修改的文件。
- **Forbidden files 未触碰**: `dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/service/**`、`dayu/ui/**`、`dayu/fins/**`、`dayu/config/**`、`docs/host/design.md` 无任何改动。
- **5 个 slice 全部实现**: Slice 1 (marker/sentinel)、Slice 2 (repeated crash/recovery)、Slice 3 (sustained watch/reconnect)、Slice 4 (scheduler/liveness long-run)、Slice 5 (mixed fault injection) 均有对应测试函数和诊断 dataclass。
- **Stop conditions 未触发**: 无 Host public contract、durable schema、EventLog 语义、recovery 状态机或 scheduler 生产行为修改。

### 2. pyproject.toml marker 与默认排除

- `pyproject.toml:138-141`: `addopts = "-m 'not stress'"` 与 `markers = ["stress: production hardening stress tests; excluded from default pytest runs"]` 正确配置。
- `test_host_production_stress.py:73`: 模块级 `pytestmark = pytest.mark.stress`。
- PR validation 证据: `10 passed, 5 deselected`（默认命令）；`5 passed`（显式 stress 命令）；collect-only 行为可解释。

### 3. 测试 timeout 防护

所有 5 个 stress test 函数均有 `@pytest.mark.timeout(...)` 防护：

| 测试 | timeout |
|---|---|
| `test_stress_marker_summary_contract` | 5s |
| `test_repeated_startup_recovery_crash_stress` | 60s |
| `test_sustained_watch_slow_consumer_reconnect_stress` | 90s |
| `test_scheduler_liveness_long_run_mixed_flow_stress` | 90s |
| `test_mixed_host_stress_deterministic_fault_injection` | 120s |

### 4. 验收信号覆盖

| 总控文档验收信号 | 覆盖情况 |
|---|---|
| repeated startup / recovery / crash E2E 不重复 terminal | Slice 2: `terminal_duplicate_count == 0`, `terminal_dedupe_ok` |
| 不漏 recovery event | Slice 2: `recovery_count == crash_cycle_count` |
| 不错误恢复 live owner | Slice 2: `live_owner.probe_ok` (attempt_lost_delta == 0, recovery_delta == 0) |
| sustained watch cursor 不倒退 | Slice 3: `watch_lag_ok` (max lag < per-session limit, final drain to 0) |
| 不漏关键 terminal | Slice 3: `primary_observed_all_terminals` |
| observer lag 有上界且有诊断输出 | Slice 3: `watch_lag_samples_by_session` + `final_watch_lags_by_session` |
| scheduler 不停摆 | Slice 4: `scheduler_drained` (all terminal, handles closed, no spurious recovery) |
| host instance heartbeat / stale 判断可解释 | Slice 4: `liveness_stale_detected` (stale only in intentional crash, not in clean close) |
| close 后无遗留 active task | Slice 4: `handle_cleanup_ok` (close count == accepted count, cancel >= 1) |
| mixed Host stress 可恢复、可观察、可终止 | Slice 5: `scheduler_drained`, `liveness_stale_detected`, `mixed_statuses_ok`, `cleanup_ok` |
| stress suite 有独立运行入口 | `pyproject.toml` marker + `addopts` 排除 |
| 默认快速 pytest 可以排除它 | `pytest tests/host -q`: 1044 passed, 5 deselected |
| 结构化摘要 | `HostStressSummary` 12 字段 + `summary_to_json` + `record_property` |
| 压测失败能定位到边界 | `StressFailureBoundary` 封闭 Literal 11 值 |

### 5. 类型安全与 docstring 约束

- `stress_support.py` 全部 1411 行通过 pyright 0 errors。
- 所有模块级函数、class、dataclass 均有完整中文 docstring，包含 `:param`、`:returns`、`:raises`。
- 无 `Any`、`object`、无类型参数或无类型返回值。
- `StressFailureBoundary` 使用 `TypeAlias = Literal[...]`，封闭诊断集合。
- `StressWorkerBehavior` 使用 `StrEnum`，封闭行为集合。
- `HostStressSummary`、`StressTerminalObservation`、`StressHostInstanceDiagnostic`、`HostStressScenario` 均为 `frozen=True, slots=True` dataclass。
- 所有 helper docstring 声明"不进入生产代码，不作为 Host durable truth"边界。

### 6. SQL 参数化

- `read_session_terminal_sequences`、`terminal_events_for_runs`、`terminal_event_count_for_runs` 使用 `?` 占位符和 tuple 参数化，无 SQL 注入风险。
- `_TERMINAL_EVENT_TYPES` 与 `_ALL_RUN_TERMINAL_EVENT_TYPES` 使用模块级 tuple 常量，`",".join("?" for ...)` 动态生成占位符，参数数量一致。

### 7. 并发安全与清理

- `asyncio.Queue[HostEvent]` 用于 watcher 事件传递。
- `asyncio.Event` 用于 worker accepted 信号和 blocking final 释放。
- `asyncio.wait_for` 用于所有关键等待操作，有超时保护。
- finally 块正确清理 task 和 watcher iterator，使用 `suppress(asyncio.CancelledError)` 和 `suppress(Exception)` 避免清理异常。
- `close_host_event_iterator` 使用 `cast(AsyncGenerator, iterator).aclose()` 正确关闭 async generator。

### 8. Terminal 去重证明

Slice 4/5 的 terminal 去重证明分两层：
1. `terminal_events_for_runs()` 返回可表达的 succeeded/failed/cancelled terminal observation，`terminal_duplicate_count == 0` 证明无重复。
2. `terminal_event_count_for_runs()` 包含 `RUN_LOST`，`all_terminal_event_count == len(public_snapshots)` 证明 lost closeout 无额外重复 terminal fact。

该证明正确处理了 `RUN_LOST` 没有对应 `HostEventKind` / `HostTerminalStatus` 的边界。

### 9. Watch lag 诊断语义

- `compute_watch_lag()` 每次调用基于 fresh short read transaction 的 point-in-time diagnostic。
- Docstring 明确声明"不表达 watcher replay truth，不替代 EventLog / Run / Attempt canonical facts"。
- Slice 2/4 使用 `(0,)` placeholder，docstring 说明"不表达 watcher replay truth 或 lag 上界"。
- Slice 3/5 有真实 lag 样本和 drain 验证。

### 10. Import 边界

- `stress_support.py` import 路径: `dayu.host` (public API)、`dayu.engine.contracts` (Engine public contracts)、`dayu.host.durable.codec.parse_utc_timestamp` (stable decode)、`dayu.host.durable.liveness.HostInstanceStatus` (stable enum)、`dayu.runtime.lane` (public lane contract)、`tests.host.*` (existing test helpers)。
- 无 import 生产内部实现模块。
- deterministic worker 通过 `LocalEngineWorkerFactory` / `LocalWorkerHandle` 边界产出 `EngineEvent`。

### 11. docs/README 同步

- `tests/README.md` 正确更新：新增默认排除说明、显式 stress 运行命令、production stress 测试描述段落。
- 根 README 未更新（正确 — stress marker 是测试基础设施细节，非用户入口）。
- Host README 未更新（正确 — Host public contract 未变化）。

### 12. Aggregate deepreview 一致性

- MiMo aggregate deepreview: PASS，无 findings。
- DS aggregate deepreview: PASS，2 个 LOW findings 均被 controller 裁决为 stale evidence。
- Controller adjudication: aggregate deepreview accepted。
- 本 PR review 不重复已裁决的 stale findings，除非在当前 diff 中找到新直接证据。

### 13. 确定性与 flakiness 评估

- 所有 stress 场景使用固定规模循环（`_CRASH_CYCLE_COUNT=3`、`_SLICE3_RUN_COUNT=18`、`_SLICE5_RUN_COUNT=15`）。
- Worker 行为完全由 `DeterministicStressWorkerFactory` + `StressWorkerBehavior` enum 脚本化，无随机。
- `_NOW = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)` 固定时间戳。
- Process crash 使用 `multiprocessing.Process` + marker files。
- Stale owner fault injection 复用 `recovery_support` 已有机制。
- Blocking workers 使用 `asyncio.Event` release gates，无 `time.sleep()` 用于 correctness。
- 短 poll interval (`_POLL_INTERVAL_SECONDS=0.01`) 均有 deadline 保护。

**Flakiness 风险: LOW** — suite 为确定性有限预算设计，非随机 fuzz。

## Residual Risks

| 风险 | 状态 | 说明 |
|---|---|---|
| 确定性有限预算，非 fuzz/soak | accepted | RR-STRESS-01 已在总控文档追踪 |
| pytest-timeout 可能先于内部 summary 终止 | accepted | RR-STRESS-02 已在总控文档追踪 |
| `RUN_LOST` 非 live HostEventKind | accepted | RR-STRESS-03 已 closed，通过 RunStatus + EventLog count 证明 |
| Watch lag 为诊断指标非 SLO | accepted | RR-STRESS-04 已 closed |
| `CLEAN_EOF` 行为未被测试覆盖 | NEW / LOW | scheduler timeout closeout 间接覆盖，但 clean EOF 语义路径未显式测试 |

## Final Decision

**PASS**。PR 可以 merge。1 个 LOW severity observation（`CLEAN_EOF` 未使用）不阻塞 merge，可在后续 hardening work unit 中处理或作为 residual risk 记录。
