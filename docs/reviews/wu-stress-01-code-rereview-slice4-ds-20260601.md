# WU-STRESS-01 Slice 4 Re-Review — AgentDS

## Scope

- **Mode**: current changes (unstaged re-review after focused fix)
- **Branch**: `test/host-stress-suite`
- **Base**: `main` (f558eae gateflow: record WU-STRESS-01 slice3 state)
- **Output file**: `docs/reviews/wu-stress-01-code-rereview-slice4-ds-20260601.md`
- **Reviewed artifacts**: `docs/reviews/wu-stress-01-code-controller-adjudication-slice4-20260601.md` (controller adjudication), `docs/reviews/wu-stress-01-fix-slice4-codex-20260601.md` (Codex fix artifact)
- **Included scope**: `tests/host/stress_support.py`, `tests/host/test_host_production_stress.py` — uncommitted diff only
- **Excluded scope**: Slice 1/2/3/5 committed changes; production code; design/control docs
- **Parallel review coverage**: 无（单 reviewer 逐行走读）

## Review Purpose

本 review 是 Slice 4 controller adjudication 后的 focused fix re-review。验证以下 7 项 accepted findings 已正确关闭，检查无新问题、无生产代码改动、无 Slice 5 行为。

## Accepted Finding Closure Verification

### DS-01: RUN_LOST terminal dedupe proof explicit — **已关闭**

- `terminal_event_count_for_runs()` (`stress_support.py:1274-1321`) 的 docstring 明确解释了双层证明："``terminal_events_for_runs()`` 仍只返回 succeeded/failed/cancelled observation，而本 helper 在 count 层显式纳入 ``RUN_LOST``。两者组合形成证明"
- `Slice4SchedulerLivenessDiagnostics.terminal_dedupe_ok` (`test_host_production_stress.py:658-676`) 的 docstring 明确解释了分两层去重："先证明可表达 terminal observation 没有重复，再用包含 ``RUN_LOST`` 的 EventLog terminal 总数等于 public terminal snapshot 数，显式证明 lost closeout 没有额外重复 terminal fact"
- `run_lost_event_count()` (`stress_support.py:1324-1336`) 封装了 `RUN_LOST` 的 event type 计数，避免测试文件复制常量
- **验证**: diff 中直接可见 docstring 文本，证明链完整可追踪

### MiMo-01: unused wait_accepted_run removed or used — **已关闭**

- `grep -rn "wait_accepted_run" tests/` → **零匹配**，方法已被删除
- `InspectableStressWorkerFactory` 当前仅包含三个 aggregate count property
- **验证**: 全量 grep 确认死代码已清理

### MiMo-02 / DS-03: duplicated constants resolved without bad re-export — **已关闭**

- `test_host_production_stress.py` 中不再定义 `_EVENT_TYPE_RUN_*`、`_HOST_DB_FILENAME`
- `grep -n "_EVENT_TYPE_RUN_LOST\|_EVENT_TYPE_RUN_SUCCEEDED\|_HOST_DB_FILENAME" tests/host/test_host_production_stress.py` → **零匹配**
- 所有 durable event type 常量只在 `stress_support.py:100-110` 定义一处
- `terminal_event_count_for_runs()` 和 `run_lost_event_count()` 在 `stress_support.py` 内使用本地常量，无兼容性 re-export
- **验证**: 常量定义已收敛到单一模块

### DS-04: verify_lane_released uses explicit lane_db_path — **已关闭**

- 函数签名 (`stress_support.py:1008`): `verify_lane_released(lane_db_path: pathlib.Path, lane_name: str) -> bool`
- 调用侧 (`test_host_production_stress.py:923`): `verify_lane_released(options.lane_db_path, options.lane_name)`
- 不再硬编码 `root_path / "lane.sqlite3"` 路径，直接从 `OpenHostOptions.lane_db_path` 传递
- **验证**: 路径从 options 参数透明传递，消除了硬编码假阳性风险

### DS-05: stale threshold rationale documented — **已关闭**

- `stress_support.py:113-116` 注释: "该阈值只用于 stress diagnostic 解释已被测试 helper 主动改旧的 heartbeat；Host recovery stale policy 仍以生产 recovery scanner 为准。"
- `read_host_instances()` docstring (`stress_support.py:954-963`): "stale 阈值只解释 ``force_owner_pid_missing_and_heartbeat_stale()`` 已经制造出的测试证据，不替代 Host recovery policy，也不参与生产 orphan 判断"
- **验证**: 注释与 docstring 均明确阈值仅用于解释主动注入的 stale 证据

### DS-02: LOST terminal semantics clear — **已关闭**

- `_is_terminal_status()` docstring (`test_host_production_stress.py:1830-1837`): "这里刻意使用 Host-wide public Run terminal 语义，不等同于 HostEventKind / HostTerminalStatus 可表达的 terminal observation 集合"
- `_is_public_run_terminal()` (`stress_support.py:1373-1386`) 同样包含 LOST 且语义一致
- **验证**: 两处终态判断函数的 docstring 清楚区分了 public Run 终态与 HostEventKind 可表达的 terminal observation 语义

## New Issues

### NEW-01-未修复-极低-InspectableStressWorkerFactory docstring 提及已删除能力

- **入口/函数**: `InspectableStressWorkerFactory` 类 docstring
- **文件(行号)**: `tests/host/stress_support.py:574-586`
- **输入场景**: 代码阅读
- **实际分支**: 不适用（文档问题）
- **预期行为**: docstring 应准确描述类当前提供的诊断入口
- **实际行为**: docstring 写"增加按 Run 等待 accepted、汇总 accepted handle 数、cancel 数和 close 数的诊断入口"，但 `wait_accepted_run` 已删除，"按 Run 等待 accepted" 不再存在于该类的接口中。当前类仅提供 `accepted_handle_count`、`total_cancel_count`、`total_close_count` 三个 aggregate count property
- **直接证据**: `stress_support.py:577-578` docstring 文本 vs 类实际仅含三个 property（`stress_support.py:588-616`）
- **影响**: 极低——仅影响 test helper 类的文档准确性，不影响行为或运行时正确性
- **建议改法和验证点**: 删除 docstring 中"按 Run 等待 accepted、"或更新为当前实际接口描述
- **修复风险（低）**: 仅改 docstring
- **严重程度（极低）**: 测试文档微调

## Validation

### 生产代码改动检查

```
git diff HEAD --diff-filter=M --name-only | grep -v tests/
```

→ **空输出**，无生产代码改动。diff 仅涉及 `tests/host/stress_support.py` 和 `tests/host/test_host_production_stress.py`。

### Slice 5 行为检查

当前 uncommitted diff 中未引入任何 Slice 5 常量（`_SLICE5_*`）、场景（`_SLICE5_SCENARIO_NAME`）、或行为。Slice 5 引用仅存在于已提交的其他测试文件中（`test_public_cancel_smoke.py`、`test_public_retry_replay.py`、`test_recovery_multiprocess.py` 等），不属于本次 review scope。

### 架构边界检查

- `stress_support.py` 新增的 import 均来自 `dayu.host`（Host public API）、`dayu.host.durable.codec`（durable 解码）、`dayu.host.durable.liveness`（liveness 枚举）、`dayu.runtime.lane`（lane 公共契约）以及 `os`（标准库）
- 无反向 import，无生产代码穿透调用
- `read_host_instances` 直接读 SQLite 但这是测试诊断 helper，已明确文档说明不替代 Host durable truth
- `verify_lane_released` 通过独立 `LaneController.open()` 做 lane public acquire/release 验证，不读取 scheduler internals

### 引用完整性检查

- `InspectableStressWorkerFactory` 使用的 `self.accepted_snapshots`、`self.cancel_reasons`、`self.handle_close_count` 均在父类 `DeterministicStressWorkerFactory` 中定义（`stress_support.py:417, 427, 437`）
- `run_lost_event_count()` 委托 `recovery_event_type_count()` → 存在于 `recovery_support.py`
- `verify_lane_released` 使用的 `_LANE_CLAIM_TTL_SECONDS`、`_LANE_HEARTBEAT_INTERVAL_SECONDS` 均来自同模块 `stress_support.py:89-90`

### SQL 注入安全性

`terminal_event_count_for_runs()` 的 SQL 使用 f-string 构造 `IN (?,?,...)` 占位符，其中 `placeholders` 数量来自 `len(run_ids)`（已校验非空），`terminal_type_placeholders` 数量来自 `len(_ALL_RUN_TERMINAL_EVENT_TYPES)`（模块常量 4）。实际值通过参数化 tuple 传入，无注入风险。

## Open Questions

- 无

## Residual Risk

1. **RUN_LOST / HostEventKind.LOST mapping gap**（未变化）: 如果未来 `HostEventKind` 新增 `LOST` 成员，`terminal_events_for_runs()` 的 `_terminal_kind_for_event_type()` 需同步更新。当前通过 `terminal_event_count_for_runs()` 的计数比较间接覆盖，风险可控。

2. **verify_lane_released False 分支未测试**（未变化）: lane 未释放时返回 `False` 的路径当前在 stress 测试中未覆盖。

3. **Stress 测试为确定性有界场景**（未变化）: 非随机 fuzz 或长时间 soak，这在 plan 中已明确声明。

4. **_POLL_INTERVAL_SECONDS=0.01**（新识别）: `wait_all_runs_terminal` 使用 10ms 轮询间隔，属于 stress test helper 的合理设计，不视为 issue。

## Review Conclusion

**PASS** — 所有 7 项 controller adjudication accepted findings 已正确关闭。修复方案严格遵守了 controller 要求：无生产代码改动、无 scheduler internals 暴露、无 Slice 5 行为、无兼容性 re-export。

发现 1 个新的极低严重度问题：`InspectableStressWorkerFactory` docstring 提到已删除的 `wait_accepted_run` 方法，不影响正确性，可在后续 Slice 顺手修正。
