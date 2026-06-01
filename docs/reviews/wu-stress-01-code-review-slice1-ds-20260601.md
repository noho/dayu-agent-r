# WU-STRESS-01 Slice 1 Code Review Artifact

## Gate

- **Gate**: implementation review (AgentDS code review specialist)
- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Slice**: Slice 1 — Stress marker、默认排除、summary/helper 基础
- **Review role**: AgentDS；不修改文件，不 commit/push/PR
- **Review date**: 2026-06-01

## Reviewed Target

- **Accepted plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- **Implementation artifact**: `docs/reviews/wu-stress-01-implementation-slice1-codex-20260601.md`
- **Changed files (4 + artifact)**:
  - `pyproject.toml` — 新增 `stress` marker 与 `addopts = "-m 'not stress'"`
  - `tests/host/stress_support.py` — 新增（348 行）
  - `tests/host/test_host_production_stress.py` — 新增（90 行）
  - `tests/README.md` — 新增 stress 命令与摘要约定说明
  - `docs/reviews/wu-stress-01-implementation-slice1-codex-20260601.md` — 实现报告
- **Review scope**: 仅上述文件；不审查 `docs/reviews/wu-stress-01-code-review-slice1-mimo-20260601.md`（非本 review 产物）

## Review Methodology

逐项检查以下维度：

1. Correctness：默认 addopts 是否正确排除 stress 且不破坏普通测试；显式 stress 命令是否可靠
2. Type safety：summary helper 是否强类型、无 `Any`/`object`/裸 `dict`
3. Docstring：中文 docstring 是否完整（参数、返回值、异常）
4. Host boundary：deterministic worker 是否通过 `LocalEngineWorkerFactory` / `LocalWorkerHandle` / `LocalEngineWorker` Protocol 边界，不绕过状态机
5. Scope discipline: 是否偷偷实现了 Slice 2-5
6. Test validity: sentinel test 是否可信
7. Stability: 是否有 flaky、不可控 sleep、外部服务依赖
8. Docs: `tests/README.md` 是否只同步当前事实
9. Plan compliance: 逐条对照 plan Slice 1 的 Exact changes 与 Expected assertions

## Findings

无 finding。

逐项验证结果：

### 1. Correctness — 默认排除与显式运行

- `pyproject.toml` 新增 `addopts = "-m 'not stress'"` 与 `markers = ["stress: ..."]` — 符合 plan Section "pyproject.toml 具体策略"。
- 显式命令 `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q` — 符合 plan 固定命令格式。
- 实现报告记录：
  - 默认 `pytest tests/host/test_package_exports.py tests/host/test_host_production_stress.py -q` → `10 passed, 1 deselected` — 证明默认排除生效，普通测试不受影响。
  - `pytest -o addopts="" -m stress ...` → `1 passed` — 显式命令可靠。
  - `pytest --collect-only tests/host/test_host_production_stress.py -q` → `no tests collected (1 deselected)`，exit code 5 — 符合 pytest 对全量 deselect 的标准行为。
  - `pytest -o addopts="" --collect-only ...` → `1 test collected` — 覆盖 addopts 后收集正常。
- CI 配置检查：无 `.github/`、`.gitlab-ci.yml`、`tox.ini`、`noxfile.py`、`Makefile`，实现报告如实记录"未发现对应 CI pytest 配置"。
- `pytest --markers` 输出含 `stress` 与 `timeout` — 实现报告确认通过。

### 2. Type Safety — 零 Any/object/裸 dict

逐类型审查：

| 符号 | 类型注解 | 判定 |
|---|---|---|
| `StressFailureBoundary` | `TypeAlias = Literal["durable", ..., "unknown"]` | 封闭，符合 plan |
| `HostStressSummary.failure_boundary` | `StressFailureBoundary \| None` | 封闭枚举或 None，符合 plan 要求 |
| `HostStressSummary` 全部字段 | `str`, `int`, `bool`, `tuple[int, ...]`, `StressFailureBoundary \| None` | 无 `Any`/`object`/裸 `dict` |
| `StressTerminalObservation` 全部字段 | `str`, `int`, `HostEventKind`, `HostTerminalStatus` | 全部强类型 |
| `summary_to_json` | `(HostStressSummary) -> str` | 返回值强类型 |
| `terminal_duplicate_count` | `(Sequence[StressTerminalObservation]) -> int` | 强类型 |
| `terminal_dedupe_ok` | `(Sequence[StressTerminalObservation]) -> bool` | 强类型 |
| `compute_watch_lag` | `(int, int) -> int` | 强类型 |
| `build_stress_open_host_options` | 完整参数类型 + `-> OpenHostOptions` | 强类型 |
| `DeterministicStressWorkerFactory` | 全部方法与属性有类型注解 | 无 `Any`/`object` |
| `StressSummaryJsonValue` | `TypeAlias = str \| int \| bool \| tuple[int, ...] \| None` | 仅供 `summary_to_json` 内部使用，非公共导出 |

`assert_summary_ok` 内部 `summary_json` 变量虽无显式类型注解，但其值来自 `summary_to_json()` 返回的 `str`，pyright 可推断；函数签名 `-> None` 完整。不构成弱类型扩散。

### 3. Docstring — 中文完整

- 模块级 docstring ✓
- `HostStressSummary` — 含 `:param scenario_name:` 到 `:param failure_boundary:` 全部字段、`:returns:`、`:raises:` ✓
- `StressTerminalObservation` — 全部 5 字段 + `:returns:` + `:raises:` ✓
- `StressWorkerBehavior` — 枚举成员 + `:param value:` + `:returns:` + `:raises:` ✓
- `DeterministicStressWorkerHandle` — class 级 docstring、`__init__`、`local_worker_id`、`events`、`close`、`on_cancel`、`_final_answer_event`、`_failed_event` 全部含中文 docstring ✓
- `DeterministicStressWorker` — class + `__init__` + `accept` ✓
- `DeterministicStressWorkerFactory` — class + `__init__` + 全部 property + 全部 method ✓
- `summary_to_json` — 含 `:param:`、`:returns:`、`:raises:` ✓
- `assert_summary_ok` — 含 `:param:`、`:returns:`、`:raises:` ✓
- `terminal_duplicate_count` — 含去重逻辑说明、`:param:`、`:returns:`、`:raises:` ✓
- `terminal_dedupe_ok` — ✓
- `compute_watch_lag` — 含 fresh short read transaction / point-in-time diagnostic 语义边界声明，符合 plan Section "实现决策 4" 精确要求 ✓
- `build_stress_open_host_options` — 全部参数 + `:returns:` + `:raises:` ✓

### 4. Host Public Boundary — Protocol 兼容

- `DeterministicStressWorkerFactory.create_worker` 返回 `LocalEngineWorker` — `DeterministicStressWorker` 结构满足 `LocalEngineWorker` Protocol（`accept` 方法签名匹配）✓
- `DeterministicStressWorker.accept` 返回 `LocalWorkerHandle` — `DeterministicStressWorkerHandle` 结构满足 `LocalWorkerHandle` Protocol（`local_worker_id`、`events`、`close`、`on_cancel`）✓
- `DeterministicStressWorkerHandle.events` 仅产出 `EngineEvent`，通过 `FinalAnswerData` / `RunFailedData` 构造，不绕过状态机 ✓
- `build_stress_open_host_options` 复用 `open_host_options()` + `deterministic_runner_spec()`，通过 `dataclasses.replace` 覆盖 lane 字段 — 不构造 `OpenHostOptions` 裸字段，符合 plan ✓
- 未 import `dayu.host` 的私有模块（如 `dispatch`、`recovery`、`durable`）✓
- `AttemptDispatchSnapshot`、`HostEventKind`、`HostTerminalStatus` 均在 `dayu.host.__all__` 中 ✓

### 5. Scope Discipline — 仅 Slice 1

对照 plan Slice 2-5 Exact changes 检查：

- Slice 2 的 `run_blocking_stress_owner_process`、`start_and_crash_owner_for_stress`、`count_event_type` 等 — 未实现 ✓
- Slice 3 的 `consume_terminals`、`close_host_event_iterator`、`read_latest_event_sequence` 等 — 未实现 ✓
- Slice 4 的 `InspectableStressWorkerFactory`、`wait_all_runs_terminal`、`read_host_instances`、`verify_lane_released` — 未实现 ✓
- Slice 5 的 `HostStressScenario` — 未实现 ✓

`DeterministicStressWorkerFactory` 已具备 `handle_close_count`、`cancel_reasons`、`accepted_snapshots` 等基础诊断属性，这些是 Slice 1 的 "基础 deterministic worker / option builder" 合理组成部分，不是 Slice 4 的 `InspectableStressWorkerFactory`。

`StressWorkerBehavior` 枚举包含 `BLOCKING_FINAL`、`STREAM_EXCEPTION`、`CLEAN_EOF` — 这三个行为在 plan Slice 1 的 worker script 列表中明确列出（"final answer、failed engine event、blocking final answer、stream exception、clean EOF"），属于 Slice 1 范围。

### 6. Test Validity — Sentinel 可信

`test_stress_marker_summary_contract`:
- 构造两个同 `run_id` 的 `StressTerminalObservation`，验证 `terminal_duplicate_count() == 1` 且 `terminal_dedupe_ok() is False` — 正确测试去重逻辑 ✓
- 构造干净 `HostStressSummary`，验证 `summary_to_json` 输出包含全部 12 个字段 — 正确测试 JSON 字段完整性 ✓
- 调用 `assert_summary_ok` 确认干净 summary 不触发断言 — 正确 ✓
- 使用 `record_property` 写入 summary JSON — 符合 plan "record_property" 约定 ✓
- `@pytest.mark.timeout(5)` — 5 秒超时，符合 plan 超时预算 ✓
- 模块级 `pytestmark = pytest.mark.stress` — 所有测试自动标记 ✓

未覆盖项（非 Slice 1 范围）：
- `compute_watch_lag` 未在 sentinel 中测试。该函数逻辑简单（`max(0, latest - last_seen)`），且其消费场景在 Slice 3，当前不作为 finding。

### 7. Stability — 无 flaky 模式

- 无 `asyncio.sleep` / `time.sleep` 调用 ✓
- 无外部服务依赖 ✓
- 无随机 fuzz ✓
- `asyncio.Event` 用于 blocking worker 释放 — 确定性同步原语 ✓
- 模块级常量（`_LANE_CLAIM_TTL_SECONDS`、`_WORKER_STARTUP_TIMEOUT_SECONDS` 等）均为小固定值，无魔法数字 ✓

### 8. Docs — tests/README 只同步当前事实

- 新增"默认 pytest 配置会排除 `stress` marker"说明 ✓
- 新增显式 stress 命令 ✓
- 新增 stress summary 字段约定与 `failure_boundary` 封闭语义 ✓
- 在"当前测试分层"的 `tests/host/` 节新增 production stress 条目 ✓
- 未写未来计划、Slice 2-5 场景或未实现功能 ✓
- 未修改根 `README.md`、`dayu/README.md`、`dayu/host/README.md` — 符合 plan Docs decision ✓

### 9. Plan Compliance — 逐条对照

| Plan Slice 1 Exact Change | 状态 |
|---|---|
| `pyproject.toml` 注册 `stress` marker，`addopts = "-m 'not stress'"` | ✓ |
| 模块中文概览 docstring | ✓ |
| `HostStressSummary` dataclass | ✓ |
| `StressTerminalObservation` dataclass | ✓ |
| `DeterministicStressWorkerFactory`、worker、handle，支持 final / fail / blocking / stream exception / clean EOF | ✓ |
| `summary_to_json`、`assert_summary_ok`、`terminal_duplicate_count`、`terminal_dedupe_ok` | ✓ |
| `compute_watch_lag` | ✓ |
| `build_stress_open_host_options` 复用 `public_smoke_support` | ✓ |
| 哨兵 test `test_stress_marker_summary_contract` | ✓ |
| 模块级 `pytestmark = pytest.mark.stress` | ✓ |
| `tests/README.md` 更新 | ✓ |

## Open Questions / Residual Risk

1. **`pytest --collect-only` exit code 5**：当 stress 文件全部被 deselect 时，pytest 返回 exit code 5（no tests collected）。这在 CI 中如果有严格的 exit code 检查可能被视为失败。但当前仓库无 CI 配置，且该行为是 pytest 标准语义。风险等级：低，仅当未来引入 CI 时需要关注。

2. **`DeterministicStressWorkerFactory._accepted_event` 不可重置**：`asyncio.Event` 一旦 set 便无法 clear，导致 `wait_accepted` 在首次 accept 后永远立即返回。实现 artifact 已记录此限制。后续 slice 若需"等待第 N 次 accept"，需要扩展 factory。风险等级：低，当前 Slice 1 不依赖此行为。

3. **`compute_watch_lag` 未经 sentinel 测试**：该函数逻辑简单，但 sentinel test 未覆盖其 `ValueError` 错误路径。建议 Slice 3 使用前补齐基本 smoke。风险等级：低，不影响 Slice 1 交付。

4. **`_NOW` 固定时间戳**：所有 EngineEvent 使用同一 `datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)`。Host 使用 EventLog `event_sequence` 排序而非 `occurred_at`，因此不影响正确性。风险等级：极低。

## Controller Decision Status

[ ] 待 controller 裁决
[ ] Blocking — 需修复后重新 review
[ ] Approved — 可进入 Slice 2

## Conclusion

**PASS** — 0 finding。

Slice 1 实现严格遵循 plan，四条变更文件均为 allowed files，未触及 forbidden files。默认 addopts 排除策略正确生效，显式 stress 命令可靠。所有新增类型强类型、零 `Any`/`object`/裸 `dict`，中文 docstring 完整。Deterministic worker 通过 Host public Protocol 边界接入，不绕过状态机。未实现 Slice 2-5 内容。Sentinel 测试可信。`tests/README.md` 只同步当前事实。无 flaky 模式、无外部依赖。

**建议：Approved，可直接进入 Slice 2。**

## Artifact Path

`docs/reviews/wu-stress-01-code-review-slice1-ds-20260601.md`
