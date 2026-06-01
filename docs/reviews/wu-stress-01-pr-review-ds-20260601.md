# WU-STRESS-01 Draft PR Review — AgentDS

## Gate

- **Gate**: draft PR review
- **Work Unit**: WU-STRESS-01 Host Production Stress Suite
- **Review role**: AgentDS PR review specialist
- **Review target**: Pull Request 102 (https://github.com/noho/dayu-agent-r/pull/102)
- **Branch**: `test/host-stress-suite` → `main`
- **PR state**: draft
- **Output file**: `docs/reviews/wu-stress-01-pr-review-ds-20260601.md`
- **Review date**: 2026-06-01
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- **Prior aggregate DS deepreview**: `docs/reviews/wu-stress-01-aggregate-deepreview-ds-20260601.md`
- **Aggregate controller adjudication**: `docs/reviews/wu-stress-01-aggregate-controller-adjudication-20260601.md`

## Scope

- **Included**:
  - `pyproject.toml` — stress marker registration + default exclusion
  - `tests/host/stress_support.py` — stress test helpers (~1410 lines)
  - `tests/host/test_host_production_stress.py` — stress tests (~2583 lines)
  - `tests/README.md` — stress marker / command documentation
  - `docs/host/wu-stress-01-host-production-stress-suite-plan.md` — planning artifact (read-only)
  - `docs/host/host-core-followup-implementation-control.md` — status updates (read-only)
  - All 40 WU-STRESS-01 review artifacts (as prior evidence)
- **Excluded**: Production code (`dayu/`), review artifacts from other work units, pre-existing tests

## Conclusion: PASS

WU-STRESS-01 draft PR 满足 correctness、determinism、marker exclusion、docs sync、type/docstring 约束。无 production code / public contract / schema / layering violation。5 个 stress tests 覆盖 plan 定义的全部 5 个 slice 验收信号。Controller 验证数据与代码证据一致。

两个 LOW severity finding 继承自 aggregate deepreview，已由 Slice 3 final focused fix 和 controller adjudication 关闭——当前代码中均已修复（见下方"Stale Finding Closure Verification"）。未发现新 finding。

Residual risks 在 plan 的 non-goals 内，controller 已在本 WU 各 slice adjudication 和 aggregate adjudication 中逐一接受。

## Cross-Cutting Evidence

### 1. No production code / public contract / schema / layering violation

- `git diff main...HEAD --name-only` 的非 artifact 文件仅为 `pyproject.toml`、`tests/host/stress_support.py`、`tests/host/test_host_production_stress.py`、`tests/README.md`、`docs/host/host-core-followup-implementation-control.md`、`docs/host/wu-stress-01-host-production-stress-suite-plan.md`。
- 零 `dayu/` 文件修改。
- `stress_support.py` 的 import 路径均来自 `dayu.host` public API、`dayu.engine.contracts`、`dayu.host.durable.codec`（decode helper）、`dayu.host.durable.liveness`（enum）、`dayu.runtime.lane`（public contract）、`tests.host.public_smoke_support` 与 `tests.host.recovery_support`（现有 test helper）。
- 无 import `dayu.host.dispatch`、`dayu.host.recovery` 等内部实现。
- 无反向 import。Host public API exports 未变；durable schema 未变；EventLog 语义未变；recovery 状态机未变；scheduler 生产行为未变。

### 2. Correctness — stress marker and default exclusion

- `pyproject.toml:138-141`: `addopts = "-m 'not stress'"` + registered `stress` marker — 与 plan 规范完全一致。
- `tests/host/test_host_production_stress.py:73`: 模块级 `pytestmark = pytest.mark.stress`。
- 全部 5 个 stress test 有显式 `@pytest.mark.timeout(...)` 预算：5s / 60s / 90s / 90s / 120s。
- 默认 pytest 正确 deselect stress tests（10 passed, 5 deselected）。
- 显式 stress 命令正确运行全部 5 个 tests。

### 3. Control doc verification signal coverage

对照 control doc 中 WU-STRESS-01 的验收信号：

| Control doc 信号 | 对应测试 | 覆盖状态 |
|---|---|---|
| repeated startup/recovery/crash E2E，terminal 去重，recovery event，live owner 防误恢复 | `test_repeated_startup_recovery_crash_stress` (Slice 2) | 已覆盖 |
| sustained watch，慢消费，reconnect，terminal fact 不丢，watch lag 诊断 | `test_sustained_watch_slow_consumer_reconnect_stress` (Slice 3) | 已覆盖 |
| scheduler/liveness long-run，queued/active/terminal/cancel/recovery 混合，close cleanup 间接证明 | `test_scheduler_liveness_long_run_mixed_flow_stress` (Slice 4) | 已覆盖 |
| mixed deterministic fault injection，全部验收信号组合 | `test_mixed_host_stress_deterministic_fault_injection` (Slice 5) | 已覆盖 |

每个 stress test 均产出结构化 `HostStressSummary`，包含 plan 要求的全部 12 个字段，`failure_boundary` 使用封闭 `StressFailureBoundary` Literal 类型。

### 4. Determinism / flakiness assessment

- 所有 stress 场景使用固定规模循环（`_CRASH_CYCLE_COUNT=3`、`_SLICE3_RUN_COUNT=18`、`_SLICE5_RUN_COUNT=15` 等）。
- Worker 行为通过 `DeterministicStressWorkerFactory` + `StressWorkerBehavior` 枚举完全脚本化，无随机性。
- `_NOW = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)` — 固定时间戳。
- Process crash 使用 `multiprocessing.Process` + marker files — 确定性 multi-process 协调。
- Blocking worker 使用 `asyncio.Event` release gate — 无 `time.sleep()` 表达 correctness。
- 短 sleep interval（`POLL_INTERVAL_SECONDS=0.01`，`delay_seconds=0.02-0.035`）有显式 deadline。
- **Flaky 风险: LOW** — suite 专为确定性设计，非 random fuzz。Plan 已明确声明此边界。

### 5. Type / docstring compliance

- 全部模块级 public 函数/class/dataclass 有完整中文 docstring（参数、返回值、异常）。
- 全部参数和返回值有类型注解。
- `StressFailureBoundary` 为封闭 `Literal` TypeAlias — 非裸 string。
- `StressSummaryJsonValue` 为封闭 `TypeAlias`。
- `StressWorkerBehavior` 为 `StrEnum`。
- 零 `Any`、`object`、裸 `dict`/`list` 注解。
- 各 slice diagnostics dataclass 为 `frozen=True, slots=True`。
- Helper docstring 均声明"不进入生产代码，不作为 Host durable truth"边界。

### 6. Docs / README sync

- `tests/README.md:29-32`: 正确记录默认 pytest 排除 `stress` marker。
- `tests/README.md:32`: 正确记录显式 stress 运行命令。
- `tests/README.md:133-138`: 正确记录 stress suite 的 marker policy、summary JSON 字段约定和 `failure_boundary` 约束。
- 根 `README.md` 未更新（正确——stress marker/exclusion 是测试基础设施细节，非用户入口）。
- Host README 未更新（正确——Host public contract 未变）。

### 7. Design source compliance

- Design source 确认 `watch_session_events` 不接收 caller cursor，不做离线补读（`docs/host/design.md` 与 `dayu/host/README.md:206`）。
- PR 的 watch reconnect 语义正确限定为"reconnect 后只能观察到 reconnect 后提交的 Run terminal；disconnect 窗口内 terminal 通过 primary watcher + public snapshot + outbox + durable diagnostic 证明不丢"。这符合 design source 的 public contract 边界，没有偷偷要求 replay cursor。
- Succinct 分层边界: `UI -> Service -> Host -> Engine`，stress tests 只通过 Host public API 操作，durable diagnostic helper 只读不写且不绕过状态机。

### 8. No flaky/uncontrolled sleep/无限等待/misproven drain

- `consume_terminals` 使用 `asyncio.wait_for(anext(iterator), timeout=remaining)` 带 deadline，非无界等待。
- `wait_all_runs_terminal` 使用轮询 + `asyncio.sleep(0.01)` + 显式 deadline，无限等待由 `TimeoutError` 兜底。
- Scheduler drain proof 通过 `scheduler_drained` 属性间接证明（public snapshot terminal counts + handle close count + clean reopen recovery delta），不暴露 scheduler internals。
- Lane release 通过独立的 `LaneController.open` + `acquire(timeout_seconds=0)` 路径验证，不读 scheduler private state。
- Terminal 去重通过 `terminal_duplicate_count` + `terminal_dedupe_ok` 双重证明，对 `RUN_LOST` 的证明缺口（`HostEventKind` 不建模 `LOST`）使用 `terminal_event_count_for_runs()` 的 count 层显式补足。

## Stale Finding Closure Verification

### DS-AGG-01: `consumer_cancel_ok` docstring → CLOSED

- **Aggregate DS 描述**: property docstring 声称"四步验证"但仅检查 2/4 条件。
- **Controller 裁决**: rejected as stale evidence（Slice 3 final focused fix 已修复）。
- **当前代码验证** (`tests/host/test_host_production_stress.py:502-510`): docstring 精确描述为"本 predicate 只覆盖 diagnostics 中的两个结构化字段：EventLog count 不变、worker 未收到 cancel。"property 体仅检查 2 条件，docstring 与代码一致。剩余 2 步由测试主体显式断言完成。**已修复，无新证据。**

### DS-AGG-02: primary watcher try/finally double close → CLOSED

- **Aggregate DS 描述**: finally 块无条件双关已关闭的 watcher，掩盖清理不完整。
- **Controller 裁决**: rejected as stale evidence（Slice 3 final focused fix 已引入 `primary_watchers_closed` flag）。
- **当前代码验证**:
  - Slice 3 (`test_host_production_stress.py:1750`): `primary_watchers_closed = [False for _index in range(_SLICE3_SESSION_COUNT)]`
  - 正常路径关闭 (`:1988`): `primary_watchers_closed[index] = True`
  - finally 兜底 (`:2012`): `if not primary_watchers_closed[index]:` 仅关闭未关闭的 watcher
  - Slice 5 (`:1097`, `:1310`, `:1334`): 同模式
- **已修复，无新证据。**

## Open Questions

1. **`verify_lane_released` False 分支无测试覆盖**: lane 未释放时返回 `False` 的路径当前未被任何 stress test 触发。该路径仅在 Host close 失败或 lane claim 泄漏时可达，属于负面路径。对当前 deterministic happy-path stress 不构成缺口，但若未来需要 lane leak diagnostic，需补充对应场景。

2. **`read_latest_event_sequence` 未被使用**: 该 helper 在 `stress_support.py:714` 定义但当前未被任何测试导入。它是 per-session lag 计算引入前的全局 lag helper，被 `read_session_terminal_sequences` 取代。不影响正确性，可考虑在后续清理中移除。

## Residual Risk

1. **Deterministic bounded coverage**: stress suite 是确定性有界场景（3-5 sessions, 15-30 runs, 1-3 crash cycles），不是随机 fuzz 或长时间 soak。极端时序、高并发竞态、资源耗尽等场景不在覆盖范围内。已在 plan non-goals 和 aggregate controller adjudication 中接受。

2. **pytest-timeout SIGTERM 绕过内部 summary**: event loop 全局卡死时 pytest-timeout 可 SIGTERM 整个进程，此时 `_slice5_timeout_summary` 不会执行。这是 pytest-timeout 的固有局限，已在 Slice 5 controller adjudication 中接受。

3. **`RUN_LOST` / `HostEventKind` mapping gap**: `RUN_LOST` 当前不是 live `HostEventKind`，因此 `terminal_events_for_runs()` 不返回 `RUN_LOST` observation。stress suite 通过 `terminal_event_count_for_runs()` 的 count 层补足证明。若未来 `HostEventKind` 新增 `LOST`，需同步更新 `_terminal_kind_for_event_type()`。已在 aggregate controller adjudication 中接受。

4. **`compute_watch_lag` 参数语义偏移**: Slice 3/5 将参数名 `latest_sequence` / `last_seen_sequence` 用于 terminal-count watermarks 而非 event sequence numbers。函数体 `max(0, a - b)` 对两者语义等价，但参数名对 count 用法有误导性。已在 Slice 3 DS re-review 中记录。

5. **Host instance stale 阈值为测试专用**: `_HOST_INSTANCE_STALE_AFTER_SECONDS=1.0` 只解释 `force_owner_pid_missing_and_heartbeat_stale()` 注入的测试证据。已在 helper docstring 和注释中声明不替代 Host recovery policy。

## Review Artifact Path

`docs/reviews/wu-stress-01-pr-review-ds-20260601.md`
