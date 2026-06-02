# WU-STRESS-01 Host Production Stress Suite Plan

## Gate / Role

- **Gate**: planning
- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Planning role**: AgentCodex planning specialist；不启动完整 gateflow，不实现代码，不提交，不 push，不创建 PR。
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Inspection artifact**: `docs/reviews/wu-stress-01-discussion-code-inspection-20260601.md`
- **Planning output**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`

## Goal / Motivation

WU-STRESS-01 的目标是建立一组默认排除、可显式运行、可重复诊断的 Host production hardening stress suite，用测试层 deterministic worker / process crash / durable inspection helper 组合验证 Host 在 crash / recovery / watch / scheduler / liveness 混合压力下仍然满足以下事实：

- repeated startup / recovery / crash E2E 不重复 terminal、不漏 recovery event、不错误恢复 live owner。
- sustained watch 在慢消费、断开重连和长时间事件压力下，关键 terminal 事实不丢，watch lag 有结构化诊断。
- scheduler / liveness long-run 在 queued / active / terminal / cancel / recovery 混合流转下不停止推进，close 后没有 active task / lane / registry 残留。
- mixed Host stress 可以通过 deterministic fault injection 复现，并输出足够定位 durable、watch、scheduler、liveness 或 recovery 边界的摘要。

动机成立。设计真源要求 Host 是 Session / Run / Attempt / EventLog / admission / cancel / recovery / watch / scheduler / liveness 的治理真源；总控文档明确当前缺口不是单点状态机测试，而是组合压力入口与结构化诊断缺失。已有测试覆盖大量短路径与单点 invariant，但没有独立 marker / 命令 / 默认排除策略，也没有覆盖这些行为同时发生时的可恢复性。

## Non-goals / Scope

- 不修改 Host public contract、`OpenHostOptions`、`Host.watch_session_events()` signature、public request / response dataclass 或 `dayu.host` exports。
- 不修改 durable schema、EventLog append / sequence / idempotency 语义、recovery 状态机、scheduler 生产行为、lane 生产语义或 liveness production policy。
- 不把 stress suite 放入默认快速 pytest 入口。
- 不依赖真实 provider、外部服务、不可控长 sleep、Docker Linux、慢盘或高延迟文件系统。
- 不重复已有 SQLite 多进程压力测试的高规格环境版。
- 不创建通用 stress framework、平台化 runner、生产诊断 API 或新的 Host replay cursor 功能。
- 不为旧接口保留兼容逻辑；测试跟随当前 public / durable 边界。

## Direct Evidence

- `pyproject.toml:136-137` 当前 pytest 配置只有 `minversion = "7.4"`，没有 `stress` marker、`addopts` 或默认排除策略。
- `tests/README.md` 当前记录常规 Host / Runtime / Service / Engine 命令，没有 stress suite marker、运行命令、超时预算或结构化摘要约定。
- `dayu/host/open_host.py:633-645` 打开 Host 时注册 `HostDispatchScheduler` 并执行 `StartupRecoveryScanner(...).scan()`，可用真实 public opener 做 startup recovery E2E。
- `dayu/host/open_host.py:476-521` `watch_session_events(session_id)` 只从 attach 时的 live cursor 后读取；当前 public contract 没有 caller-specified replay cursor。因此 stress suite 不能要求断开后 watcher 回放断开窗口内已发生的 live event，只能用持续 watcher、后续 reconnect watcher、public snapshot / outbox / durable diagnostic 组合证明 terminal fact 不丢。
- `dayu/host/dispatch.py:384-457` `ActiveWorkerRegistry` 支持 register / unregister / cancel / cancel_all，scheduler close 清理可以通过测试层注入 registry 或 handle 计数验证。
- `dayu/host/dispatch.py:1921-1941` scheduler dispatch 先进入 lane waiting，再处理 lane timeout closeout；long-run stress 可以覆盖 lane waiting / timeout / dispatch 推进。
- `dayu/host/dispatch.py:2273-2291` worker accept 后注册 active worker 并创建 `_consume_worker_events` task；close 后 active task / handle / lane 释放是 scheduler stress 的核心断言。
- `dayu/host/dispatch.py:2862-2875` terminal / stop_worker_stream 会驱动 run terminal closeout 与 duplicate governance registry 清理；terminal 去重和 active cleanup 可在 stress 摘要中验证。
- `dayu/host/recovery.py:139-151` `StartupRecoveryScanResult` 已提供 actions / pending dispatches / queue promotion sessions，可在直接 scanner stress 或 durable diagnostic 中辅助定位 recovery 分支。
- `tests/host/test_recovery_multiprocess.py:49-180` 已有 live owner 不误杀、crashed owner reopen、projection lag 不阻塞 durable recovery 的短路径 E2E，可复用其多进程支撑思想。
- `tests/host/test_watch_session_events.py:347-423` 已有双 watcher、terminal event、consumer cancel 不取消 Run 的短路径测试；缺少 sustained lag / reconnect stress。
- `tests/host/test_dispatch_scheduler.py` 已覆盖 scheduler drain、lane、worker startup、close、active task cleanup 等单点窗口；缺少 queued / active / terminal / cancel / recovery 混合 long-run stress。

## Affected Files / Modules

Planning specialist 本轮只允许编辑本 plan 文档。Implementation gate 允许的文件如下。

### Allowed Implementation Files

- `pyproject.toml`
  - 注册 `stress` marker。
  - 增加默认排除策略。
- `tests/host/stress_support.py`
  - 新增 Host stress 专用测试 helper、deterministic worker / handle、summary dataclass、durable diagnostic helper、process target。
- `tests/host/test_host_production_stress.py`
  - 新增 WU-STRESS-01 stress tests。
- `tests/README.md`
  - 只同步 stress marker / 命令 / 默认排除 / 摘要约定；不写未来计划。

### Read-only Reference Files

- `docs/host/design.md`
- `docs/host/host-core-followup-implementation-control.md`
- `docs/reviews/wu-stress-01-discussion-code-inspection-20260601.md`
- `tests/host/recovery_support.py`
- `tests/host/public_smoke_support.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_host_instance_liveness.py`
- `dayu/host/open_host.py`
- `dayu/host/dispatch.py`
- `dayu/host/recovery.py`

### Forbidden Implementation Files Unless Stop Condition Triggers

- `dayu/host/**`
- `dayu/engine/**`
- `dayu/runtime/**`
- `dayu/service/**`
- `dayu/ui/**`
- `dayu/fins/**`
- `dayu/config/**`
- `docs/host/design.md`
- `docs/host/host-core-followup-implementation-control.md`
- 根目录 `README.md`

如果 implementation agent 认为必须修改 forbidden files 才能实现 stress suite，应停止，不得自行扩大 scope。

## Contract / Schema / State-machine / Public-interface Changes

- **Host public contract**: 不变。
- **Durable schema**: 不变。
- **EventLog semantics**: 不变。
- **Recovery state machine**: 不变。
- **Scheduler production behavior**: 不变。
- **Public test interface**: 新增 `pytest` marker `stress` 与显式 stress 运行命令。
- **Default test behavior**: 默认 pytest 排除 `stress` marker。
- **Documentation**: 仅 `tests/README.md` 需要同步测试运行事实；Host README / design / 总控文档不因本 WU 修改。

`pyproject.toml` 具体策略：

```toml
[tool.pytest.ini_options]
minversion = "7.4"
addopts = "-m 'not stress'"
markers = [
    "stress: production hardening stress tests; excluded from default pytest runs",
]
```

显式运行 stress 时必须覆盖默认 `addopts`，避免 `-m stress` 与默认 `-m 'not stress'` 组合歧义：

```bash
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
```

`pytest-timeout>=2.1.0` 已在 `pyproject.toml` test optional dependency 中存在；implementation 不应新增依赖，只需验证 `pytest --markers` 中存在 `timeout` marker。

## Implementation Decisions

### 1. Stress suite 使用 public opener，测试 helper 只做 fault injection / diagnostic

主要路径通过 `open_host(options)`、`ensure_session`、`submit_followup`、`cancel_run`、`cancel_session_runs`、`get_run`、`watch_session_events`、`read_outbox_terminal_items` 等 public API 触发。Durable SQL helper 只允许用于：

- 制造已有测试也使用的 deterministic fault，例如 owner pid missing / heartbeat stale。
- 统计 EventLog / run / attempt / dispatch / host instance diagnostic。
- 计算 watch lag、terminal 去重和 recovery event 计数。

测试断言的行为真源仍应优先是 public snapshot / HostEvent；durable helper 不能成为新的 production truth，也不能绕过状态机直接构造成功路径。

### 2. Watch reconnect 不新增 replay cursor

当前 public `watch_session_events` 从 attach cursor 后开始读取，不能按调用方传入旧 cursor 回放断开期间事件。Stress suite 的 reconnect 语义定义为：

- primary watcher 在高压期间持续附着，用于证明 live stream 不漏关键 terminal。
- secondary watcher 可以断开并重新 attach，用于证明重新订阅后能继续观察后续 terminal，且 consumer 取消不会写 EventLog / 不取消 Run。
- 断开窗口内已经 terminal 的 Run，通过 primary watcher、public `get_run`、outbox terminal read / durable diagnostic 验证 terminal fact 不丢。

如果 controller 要求“同一个 public watcher reconnect 后回放断开窗口内 terminal event”，这需要 public cursor/replay contract，超出本 WU，应停止并写入 Blocking Questions For Controller。

### 3. 结构化摘要是测试诊断，不是生产 API

新增封闭诊断类型，放在 `tests/host/stress_support.py`，不得使用裸字符串扩散：

```python
StressFailureBoundary = Literal[
    "durable",
    "scheduler",
    "watch",
    "watch_reconnect",
    "liveness",
    "recovery",
    "projection",
    "active_cleanup",
    "scheduler_close",
    "worker_accept",
    "unknown",
]
```

该类型别名必须使用 Python 3.11 可用语法。若实现选择 `StrEnum` 加 dataclass 字段枚举类型，也可接受，但必须保持封闭诊断集合。无论采用哪种写法，`failure_boundary` 必须是 `StressFailureBoundary | None` 或等价封闭枚举类型，不得是 `str | None`。

新增 `HostStressSummary` dataclass，放在 `tests/host/stress_support.py`。它必须有完整中文 docstring，字段固定覆盖：

- `scenario_name: str`
- `session_count: int`
- `run_count: int`
- `crash_count: int`
- `recovery_count: int`
- `watch_lag_max: int`
- `watch_lag_samples: tuple[int, ...]`
- `scheduler_drained: bool`
- `liveness_stale_detected: bool`
- `terminal_duplicate_count: int`
- `terminal_dedupe_ok: bool`
- `failure_boundary: StressFailureBoundary | None`

helper 提供 `summary_to_json(summary: HostStressSummary) -> str`，只返回排序后的 JSON 文本，用于 assertion message / `record_property` / `tmp_path` diagnostic file。不得引入 `Any`、`object`、裸 `dict` 或无类型签名。

`StressTerminalObservation` 只能在实现需要 terminal 去重或 watch lag 计算时创建。它的消费路径必须明确为：

- `terminal_duplicate_count(observations: Sequence[StressTerminalObservation]) -> int`
- `terminal_dedupe_ok(observations: Sequence[StressTerminalObservation]) -> bool`
- `watch_lag_samples(...)` 或等价 lag helper 读取 observation 中的 `event_sequence` / `run_id`

如果实现最终直接用局部 tuple / dict-free typed helper 完成去重和 lag 计算，而没有上述消费路径，则不得创建 `StressTerminalObservation`，避免死设计或 god bag。

### 4. 新增 helper 的 docstring、类型和 diagnostic 语义

`tests/host/stress_support.py` 中所有新增模块级函数、class、dataclass 都必须有完整中文 docstring，至少包含：

- 参数含义。
- 返回值。
- 可能抛出的异常；如果函数不主动抛出异常，也要写明异常由底层调用透传或“不主动抛出”。
- 对测试 helper 的边界说明：它只服务 WU-STRESS-01，不进入生产代码，不作为 Host durable truth。

所有新增函数必须有完整参数类型和返回值类型；禁止 `Any`、`object`、裸 `dict` / `list` 注解和无类型签名。JSON-like 结构必须使用本仓已有强类型或局部封闭 dataclass / typed tuple，不得用 extra payload 袋。

lag diagnostic helper 必须在 docstring 中明确：

- 每次读取 latest sequence、session terminal sequence 或 EventLog count 时，都通过 fresh short read transaction 获取 point-in-time diagnostic。
- 该读取只用于测试诊断和 lag 估算，不表达 watcher replay truth，不替代 EventLog / Run / Attempt canonical facts。
- 不得复用长事务快照计算“最终 lag”，避免把旧 snapshot 误判为 watcher 落后。

### 5. Deterministic fault injection 只放测试层

新增 stress worker factory 的职责必须相对既有 `tests.host.recovery_support` helper 保持增量化：优先复用 `run_blocking_owner_process`、`AsyncControlledFinalAnswerWorkerFactory`、accepted marker、process terminate、owner stale fault injection、event type count、attempt count 等既有能力；只有在现有 helper 不能覆盖 stress 诊断时才新增类型。

`stress_support.py` 可以提供确定性 worker script，但新增职责只限于：

- final answer。
- failed engine event。
- blocking final answer，直到测试释放。
- stream exception，用于 worker lost / recovery。
- clean EOF，用于 scheduler failed closeout。
- handle close count / cancel count / accepted snapshot count 等 close cleanup 诊断。
- per-run scripted worker 行为选择，用于 mixed stress 的 deterministic fault injection。

worker script 通过 `LocalEngineWorkerFactory` / `LocalWorkerHandle` 边界产出 Engine public `EngineEvent`，不导入或修改生产状态机。process crash 使用 `multiprocessing.Process` + marker file；stale owner 使用测试 helper 更新 liveness row，与现有 `tests/host/recovery_support.py` 思路一致。

不得复制 `recovery_support.py` 中已有多进程 owner / marker / stale liveness 逻辑的大段实现。若只需要语义微调，应写薄 wrapper，并在 wrapper docstring 中说明复用关系和增量职责。

### 6. 超时预算显式、短而稳定

所有 stress tests 必须 `@pytest.mark.stress`，并使用 `pytest-timeout` 的 `@pytest.mark.timeout(...)` 或内部 `asyncio.wait_for`。`pytest-timeout>=2.1.0` 已在 `pyproject.toml` 的 test optional dependency 中存在；Slice 1 必须通过 `pytest --markers` 验证 timeout marker 与 stress marker 均可见，避免 stress 测试失去超时防线。建议预算：

- 单个 stress test 30-90 秒。
- 整个 `tests/host/test_host_production_stress.py` 在普通本地机器上目标 < 3 分钟。
- 循环规模固定小数值，例如 sessions 3-5、runs 12-30、crash cycles 3-6；不做随机 fuzz。

不得使用不可控 `sleep` 表示 correctness。允许短 poll interval helper，但必须有 deadline 和失败时 summary。

## Implementation Slices

### Slice 1: Stress marker、默认排除、summary/helper 基础

**Objective**: 建立独立 stress 入口和可复用诊断基础，不新增生产行为。

**Prerequisites**:

- 已完成 plan review fix，并确认 ADJ-01 到 ADJ-09 的约束进入本 plan。
- 当前仓库 test optional dependency 已包含 `pytest-timeout>=2.1.0`；implementation 只验证 marker 可用，不新增依赖。

**Allowed files**:

- `pyproject.toml`
- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`
- `tests/README.md`

**Exact changes**:

- 在 `pyproject.toml` 注册 `stress` marker，并设置默认 `addopts = "-m 'not stress'"`。
- 新建 `tests/host/stress_support.py`：
  - 模块中文概览 docstring。
  - `HostStressSummary` dataclass。
  - `StressTerminalObservation` dataclass：记录 `run_id`、`event_id`、`event_sequence`、terminal kind/status。
  - `DeterministicStressWorkerFactory`、worker、handle，支持 final / fail / blocking / stream exception / clean EOF。
  - `summary_to_json`、`assert_summary_ok`、`terminal_duplicate_count`、`watch_lag` 等私有 helper。
  - `build_stress_open_host_options(root_path, worker_factory, *, lane_capacity, lane_timeout_seconds)`，复用 `tests.host.public_smoke_support.open_host_options` 与 deterministic runner spec。
  - process target 与 marker helper 可复用 `tests.host.recovery_support`，不要复制大段逻辑；如必须新增，保持顶层函数以支持 multiprocessing。
- 新建 `tests/host/test_host_production_stress.py`：
  - 模块级 `pytestmark = pytest.mark.stress`。
  - 先加入一个轻量 sentinel test，例如 `test_stress_marker_summary_contract`，验证 summary JSON 字段完整、terminal duplicate helper 可用。
- 更新 `tests/README.md`：
  - 在命令区说明默认 pytest 排除 stress。
  - 增加显式运行命令：`pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q`。
  - 增加 stress 摘要字段约定。

**Tests / validation**:

```bash
source .venv/bin/activate
pytest --markers
pytest tests/host/test_package_exports.py tests/host/test_host_production_stress.py -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest --collect-only tests/host/test_host_production_stress.py -q
pytest -o addopts="" --collect-only tests/host/test_host_production_stress.py -q
python -m pyright dayu/ tests/ utils/
```

**Expected assertions**:

- `pytest --markers` 输出包含 `stress` marker 和 `timeout` marker；`timeout` marker 来自已存在的 `pytest-timeout` dependency，不需要新增依赖。
- CI / 常规 pytest 命令检查必须覆盖 `.github/**`、`pyproject.toml`、`tox.ini`、`noxfile.py`、`Makefile` 中实际存在的 pytest 调用；建议用 `rg -n "pytest|python -m pytest|uv run pytest" <existing paths>` 检查。implementation report 必须记录发现的 pytest 调用及其是否会受默认 `addopts` 正确排除 stress；如果没有 CI 文件或无匹配，记录“未发现对应 CI pytest 配置”，不得因为无 CI 文件而改动其它配置。
- 默认命令中 stress tests 被 deselect，`test_package_exports.py` 正常通过，命令 exit 0。
- 显式 stress 命令运行 sentinel stress test。
- 默认 `pytest --collect-only tests/host/test_host_production_stress.py -q` 必须体现 stress tests 被默认 marker expression 过滤或 deselect；`pytest -o addopts="" --collect-only ...` 必须能看到完整 stress tests。implementation report 必须记录两条命令的 collected / deselected / selected 摘要。
- 检查仓库 CI / 常规 pytest 调用文档或配置中是否直接运行 `pytest` / `pytest tests/...`；若存在，确认新的 `addopts = "-m 'not stress'"` 不会让 CI 误跑 stress。当前若无 CI 配置，也要在 report 中写明“未发现 CI pytest 配置”。
- pyright 无新增或扩散报错。

**Failure paths**:

- unknown marker warning：说明 `pyproject.toml` marker 未注册。
- `pytest --markers` 缺少 `timeout`：说明测试环境没有安装已声明的 `pytest-timeout`，必须停止修复环境，不得提交无 timeout 防线的 stress。
- 默认命令运行了 stress test：说明默认排除策略失效。
- `-m stress` 显式命令 0 selected：说明 addopts 覆盖命令缺失或 marker 未生效。
- 覆盖 `addopts` 的 collect-only 无法收集完整 stress tests：说明 test module import 或 marker 配置破坏了基础收集。

**Stable output for next slices**:

- `stress` marker 和默认排除策略稳定生效。
- `tests/host/stress_support.py` 提供 `HostStressSummary`、封闭 `StressFailureBoundary`、summary JSON helper、基础 deterministic worker / option builder。
- `tests/host/test_host_production_stress.py` 存在 marker sentinel，后续 slice 只追加 stress cases。
- `tests/README.md` 记录显式 stress 命令和默认排除行为。

**Docs decision**:

- `tests/README.md` 必须更新。
- 根 README 不更新，因为用户手册入口未变化。
- `dayu/host/README.md` 不更新，因为 Host 接口、状态机、生产机制未变化。

**Stop conditions**:

- 如果默认排除无法通过 pytest 配置可靠实现，停止并向 controller 提供替代方案，不要引入自定义 plugin。

### Slice 2: Repeated startup / recovery / crash E2E stress

**Objective**: 反复启动 Host、提交 Run、制造 worker accepted / running 附近 owner crash，再 reopen recovery，验证 terminal 去重、recovery event 和 live owner 防误杀。

**Prerequisites**:

- Slice 1 已完成并通过验证。
- `stress_support.py` 已提供 summary、封闭 failure boundary、option builder、基础 worker/handle。
- `tests.host.recovery_support` 中可复用的 process / accepted marker / stale owner helper 已确认优先复用。

**Allowed files**:

- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`
- `tests/README.md`，仅当命令或摘要说明需要补充。

**Exact changes**:

- 在 `stress_support.py` 增加：
  - `run_blocking_stress_owner_process(...)` 或复用 `run_blocking_owner_process(...)` 的 wrapper。
  - `start_and_crash_owner_for_stress(...)`：启动子进程，等待 accepted marker，terminate，等待 lane TTL，强制 owner pid missing / heartbeat stale。
  - `count_event_type(root_path, event_type)`、`attempt_count_for_run(root_path, run_id)`、`terminal_events_for_runs(root_path, run_ids)` 等 diagnostic helper；可复用 `recovery_support` 已有函数。
- 在 `test_host_production_stress.py` 增加 `test_repeated_startup_recovery_crash_stress`：
  - 循环 3-6 次，每次创建独立 session 或同 session sequential run。
  - 每轮启动 owner process，等 worker accepted 后 crash。
  - reopen `open_host`，使用 recovery worker 释放 final。
  - 通过 watcher 或 `get_run` 等待 terminal。
  - 同时增加一次 live owner probe：另一个 process 打开同 DB 不应产生 `ATTEMPT_LOST` / `RUN_RECOVERING`。
  - 最后构造 summary。

**Expected assertions**:

- `summary.session_count >= 1`。
- `summary.run_count == crash_cycle_count + live_probe_count` 或与实际提交数一致。
- `summary.crash_count == crash_cycle_count`。
- `summary.recovery_count == crash_cycle_count`，通过 `RUN_RECOVERING` event count 或 recovery worker accepted count 验证。
- 每个 crashed run 最终 `RunStatus.SUCCEEDED`。
- 每个 crashed run `attempt_count == 2`，live owner run `attempt_count == 1`。
- terminal event 每个 run 至多一个 public terminal；`terminal_duplicate_count == 0`、`terminal_dedupe_ok is True`。
- live owner probe 不增加 `ATTEMPT_LOST` / `RUN_RECOVERING`。

**Stable output for next slices**:

- `start_and_crash_owner_for_stress(...)` 或等价 wrapper 可被 Slice 4 / Slice 5 复用。
- recovery event count、attempt count、terminal dedupe diagnostic helper 可复用。
- repeated crash/reopen scenario 已证明不会要求修改 recovery production behavior。

**Validation command**:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k repeated_startup_recovery_crash -q
pytest tests/host/test_recovery_multiprocess.py -q
python -m pyright dayu/ tests/ utils/
```

**Failure paths / diagnostics**:

- timeout waiting accepted marker：summary `failure_boundary="scheduler"` 或 `"worker_accept"`。
- recovery worker never accepted：`failure_boundary="recovery"`，附 run_id、attempt_count、event counts。
- duplicated terminal：`failure_boundary="durable"` 或 `"watch"`，附 duplicate run ids / event ids。
- live owner 被误 recover：`failure_boundary="liveness"`。

**Stop conditions**:

- 如果必须改变 recovery stale threshold、recovery policy 或 `open_host` startup scan signature，停止。

### Slice 3: Sustained watch stress with slow consumer and reconnect

**Objective**: 多 session / run 持续产生 terminal events，验证慢消费、consumer cancel、secondary reconnect 后 watch 仍可观察后续 terminal，primary watcher 不漏关键 terminal，lag 有上界和诊断。

**Prerequisites**:

- Slice 1 已完成并通过验证。
- Slice 2 的 terminal dedupe helper 可用；如果 Slice 3 不依赖 crash helper，可不运行 Slice 2 stress case作为前置，但不得复制其 helper。
- lag diagnostic helper docstring 已按本 plan 声明 fresh short read transaction 与 point-in-time diagnostic 语义。

**Allowed files**:

- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`
- `tests/README.md`，仅当 stress 命令说明变化。

**Exact changes**:

- 在 `stress_support.py` 增加：
  - `consume_terminals(iterator, expected_run_ids, *, per_event_delay_seconds, timeout_seconds)`。
  - `close_host_event_iterator(iterator)`，可复用已有 helper 但不要跨文件 import 私有嵌套函数。
  - `read_latest_event_sequence(root_path)` 和 `read_session_terminal_sequences(root_path, session_id)` diagnostic。
  - `compute_watch_lag(latest_sequence, last_seen_sequence) -> int`。
- 在 `test_host_production_stress.py` 增加 `test_sustained_watch_slow_consumer_reconnect_stress`：
  - 打开 Host，创建 3 个 session。
  - 每个 session attach primary watcher。
  - 提交 12-24 个 deterministic final / failed / cancelled mixed runs；同 session active 时允许 queued，释放 worker 使 queue promotion 继续。
  - primary watcher 用小延迟消费 terminal，制造 backlog。
  - secondary watcher 在中途 attach，消费若干 terminal 后主动 cancel / close，再重新 attach，验证 reconnect 后提交的新 run terminal 可被观察。
  - 对断开窗口内 terminal，不要求 secondary replay；使用 primary watcher + public run snapshot / outbox terminal read / durable diagnostic 验证 terminal fact 不丢。
  - 记录每个 session `watch_lag_samples`，最大 lag 不应无限增长；在所有 runs terminal 后 lag 应 drain 到 0 或可解释的小值。

**Expected assertions**:

- 所有提交 run 最终进入 `SUCCEEDED` / `FAILED` / `CANCELLED` 中的预期终态。
- primary watchers 观察到所有 expected terminal run ids。
- secondary reconnect watcher 至少观察到 reconnect 后提交的 terminal run ids。
- consumer cancel 必须通过具体机制验证：
  - cancel consumer 前用 fresh short read transaction 读取 EventLog count，记为 `before_cancel_event_count`。
  - cancel consumer 后立即用 `await host.get_run(active_run_id)` 验证 active run 仍为 `RUNNING` 或原预期非终态，且 worker handle 未收到 cancel。
  - 再用 fresh short read transaction 读取 EventLog count，断言 `after_cancel_event_count == before_cancel_event_count`。
  - 释放对应 worker 后，再通过 public `get_run` 或 watcher 验证 run 正常 terminal。
- `terminal_duplicate_count == 0`。
- `watch_lag_max` 小于本测试提交 event 总量，且最终 lag 为 0；如果由于 attach cursor 语义导致 secondary 不看历史，不计为失败，但 summary 需记录 reconnect observed count。

**Stable output for next slices**:

- sustained watch slow-consumer helper、consumer cancel verification helper、lag diagnostic helper 可被 Slice 5 复用。
- reconnect 语义固定为“重新 attach 后观察后续 terminal”，不要求 replay disconnect gap。
- lag samples 可进入 `HostStressSummary.watch_lag_samples`。

**Validation command**:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q
pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q
python -m pyright dayu/ tests/ utils/
```

**Failure paths / diagnostics**:

- primary watcher 缺 terminal：`failure_boundary="watch"`，附 missing run ids、last_seen_sequence、latest_sequence。
- run terminal 但 outbox/read model 缺 terminal：`failure_boundary="projection"`。
- duplicate terminal event id / run id：`failure_boundary="durable"`。
- reconnect 后新 terminal 不可观察：`failure_boundary="watch_reconnect"`。

**Stop conditions**:

- 如果需求被解释为 public watcher 必须 replay disconnect gap，停止并写 Blocking Questions For Controller，因为当前 public contract 不支持 caller cursor。

### Slice 4: Scheduler / liveness long-run stress

**Objective**: 在 queued / active / terminal / cancel / recovery 混合流转下验证 scheduler 持续 drain，host instance liveness stale 判断可解释，close 后 active task / handle / lane 清理完成。

**Prerequisites**:

- Slice 1 已完成并通过验证。
- Slice 2 的 crash/recovery helper 可复用。
- Slice 3 的 terminal dedupe / lag diagnostic helper 可复用；如果本 slice 不消费 watch lag，也不得另写重复 helper。
- `InspectableStressWorkerFactory` 的增量职责已确认不能由 `recovery_support` 现有 helper满足。

**Allowed files**:

- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`
- `tests/README.md`，仅当 stress 说明变化。

**Exact changes**:

- 在 `stress_support.py` 增加：
  - `InspectableStressWorkerFactory`，记录 accepted snapshots、handle close count、cancel count、release gates。
  - `wait_all_runs_terminal(host, run_ids, timeout_seconds)`。
  - `read_host_instances(root_path)` diagnostic，判断 running / stopping / stopped / stale heartbeat。
  - `verify_lane_released(root_path, lane_name)` diagnostic，可通过 runtime lane acquire `timeout_seconds=0` 验证 capacity 可用，不读取 lane 作为 Host truth。
- 在 `test_host_production_stress.py` 增加 `test_scheduler_liveness_long_run_mixed_flow_stress`：
  - 使用 lane capacity 1 或 2，提交多个 session 的 active + queued runs。
  - 混合执行：
    - active blocking run 后释放为 success。
    - queued run cancel。
    - active run cancel。
    - worker stream exception 导致 lost / failed closeout。
    - 一轮 owner crash + reopen recovery 可复用 Slice 2 helper。
  - 等待 queue promotion drain。
  - close Host，断言 handles close、cancel token、lane capacity、active registry diagnostic 均收口。
  - reopen Host，确认没有因前一个 clean close 产生错误 recovery；对 crash case recovery 仍按预期出现。

**Expected assertions**:

- 所有 run 最终处于 terminal 或 recovery 后 terminal。
- queued cancel 不阻塞同 session 后续 promotion。
- active cancel 至少传播到 worker cancellation token / handle。
- close 后 no active task diagnostic：如直接使用 public opener无法访问 private scheduler，则通过 handle close count、lane reacquire、reopen no spurious recovery、EventLog terminal counts 间接证明；如使用直接 `HostDispatchScheduler` 单元式 stress，则可断言 `_active_tasks` 为空，但该断言只能放在 scheduler-internal stress test 分支。
- `scheduler_drained is True`。
- `liveness_stale_detected is True` 至少在 crash/recovery 子流中成立，clean close 子流不应被误判 stale orphan。
- `terminal_duplicate_count == 0`。

**Close cleanup indirect proof chain**:

不得为了测试暴露 scheduler internals。public opener 路径的 close cleanup 必须按以下伪代码级步骤间接证明：

```python
factory = InspectableStressWorkerFactory(...)
options = build_stress_open_host_options(tmp_path, factory, lane_capacity=1, ...)
async with open_host(options) as host:
    session = await host.ensure_session(...)
    active = await host.submit_followup(session.session_id, blocking_request)
    await factory.wait_accepted(active.accepted_run_id)
    queued = await host.submit_followup(session.session_id, queued_request)
    before_terminal_counts = read_terminal_event_counts(tmp_path, (active.accepted_run_id, queued.accepted_run_id))
    await host.cancel_run(queued.accepted_run_id, ...)
    await wait_expected_cancelled(host, queued.accepted_run_id)

# context manager exit 已 close Host
assert factory.total_cancel_count >= 1
assert factory.total_close_count == factory.accepted_handle_count
assert verify_lane_immediate_acquire(options.lane_db_path, options.lane_name) is True

async with open_host(options_with_final_worker) as reopened:
    active_after_reopen = await reopened.get_run(active.accepted_run_id)
    assert active_after_reopen.status in {RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.SUCCEEDED}

after_terminal_counts = read_terminal_event_counts(tmp_path, (active.accepted_run_id, queued.accepted_run_id))
assert after_terminal_counts == expected_no_duplicate_increment(before_terminal_counts, after_close_expected_counts)
assert count_event_type(tmp_path, "RUN_RECOVERING") == expected_recovery_count_from_intentional_crash_only
```

证明链含义：

- handle cancel / close count 证明 scheduler close 已向 active worker 传播取消并让 handle finally close。
- reopen 后没有额外 `RUN_RECOVERING` / `ATTEMPT_LOST`，证明 clean close 未被误判为 stale orphan；只有测试脚本中故意 crash 的 run 可以贡献 recovery count。
- lane immediate acquire 成功证明 close 后没有遗留 lane claim 阻塞 capacity。
- terminal / EventLog counts 不重复证明 close / reopen 没有重复 terminal closeout。

**Stable output for next slices**:

- close cleanup proof helper、lane immediate acquire diagnostic、host instance stale diagnostic 可被 Slice 5 复用。
- mixed queued / active / cancel / recovery script 的稳定 building blocks 可复用。

**Validation command**:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k scheduler_liveness -q
pytest tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py tests/host/test_public_cancel_session_runs.py -q
python -m pyright dayu/ tests/ utils/
```

**Failure paths / diagnostics**:

- queue stuck：`failure_boundary="scheduler"`，附 queued / active run ids。
- stale live owner misclassified：`failure_boundary="liveness"`。
- lane not released after close：`failure_boundary="scheduler_close"`。
- active handle not closed：`failure_boundary="active_cleanup"`。

**Stop conditions**:

- 如果 close cleanup 只能通过新增 production accessor 证明，停止；不要为测试暴露 scheduler internals。

### Slice 5: Mixed Host stress with deterministic fault injection

**Objective**: 把 crash / recovery / watch / scheduler / liveness 混合在一个 deterministic scenario 中，形成最终 WU 验收信号。

**Prerequisites**:

- Slice 1 到 Slice 4 均已完成并通过各自验证。
- Summary、failure boundary、terminal dedupe、watch lag、crash/recovery、close cleanup proof helper 均可复用。
- 所有 helper 已有中文 docstring 和强类型签名，pyright green。

**Allowed files**:

- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`
- `tests/README.md`，仅当最终命令或摘要说明调整。

**Exact changes**:

- 在 `stress_support.py` 增加 `HostStressScenario` dataclass，字段包括 session_count、runs_per_session、crash_cycles、watch_delay、lane_capacity。
- 在 `test_host_production_stress.py` 增加 `test_mixed_host_stress_deterministic_fault_injection`：
  - 固定 scenario，不用 random；如需多样性，用显式 tuple script。
  - sessions: 3。
  - runs: 15-30。
  - fault script 覆盖 final、failed、queued cancel、active cancel、stream exception、owner crash/recovery、watch reconnect。
  - primary watchers 全程消费；secondary watcher 中途断开重连。
  - 每个阶段更新 `HostStressSummary`。
  - 最终 assert summary 全部关键字段满足验收。
- 输出 summary：
  - `record_property("host_stress_summary", summary_to_json(summary))`。
  - 在失败 assertion message 中包含 `summary_to_json(summary)`。
  - 可写入 `tmp_path / "host-stress-summary.json"`，但不得写 workspace 固定路径。

**Expected assertions**:

- `session_count == 3`。
- `run_count >= 15`。
- `crash_count >= 1`。
- `recovery_count == crash_count`。
- `watch_lag_max >= 0` 且最终 drain。
- `scheduler_drained is True`。
- `liveness_stale_detected is True`。
- `terminal_duplicate_count == 0`。
- `terminal_dedupe_ok is True`。
- 所有 expected terminal run ids 都可通过 public snapshot、primary watcher terminal set 或 outbox terminal projection 解释。

**Stable output for WU completion**:

- `tests/host/test_host_production_stress.py` 覆盖 repeated crash/recovery、sustained watch、scheduler/liveness long-run、mixed deterministic fault injection。
- `HostStressSummary` 在每类 stress 中输出结构化摘要字段。
- 默认 pytest 排除 stress，显式 stress 命令可运行完整 suite。
- 无 Host public contract、durable schema、EventLog、recovery 或 scheduler production behavior 修改。

**Validation command**:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k mixed_host_stress -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
python -m pyright dayu/ tests/ utils/
```

**Failure paths / diagnostics**:

- summary 的 `failure_boundary` 必须使用 `StressFailureBoundary` 封闭类型，只能设置为 `durable`、`scheduler`、`watch`、`watch_reconnect`、`liveness`、`recovery`、`projection`、`active_cleanup`、`scheduler_close`、`worker_accept` 或 `unknown` 之一。
- AssertionError message 必须包含 summary JSON。
- 不允许只报 timeout without context。

**Stop conditions**:

- 如果 mixed scenario 需要不可控 sleep 才稳定，通过减小规模或改为更确定的 release gate 修正；仍无法稳定则停止，不要提交 flaky stress。

## Validation Matrix

Implementation 完成后必须运行：

```bash
source .venv/bin/activate
pytest --markers
pytest tests/host/test_package_exports.py tests/host/test_host_production_stress.py -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest --collect-only tests/host/test_host_production_stress.py -q
pytest -o addopts="" --collect-only tests/host/test_host_production_stress.py -q
pytest tests/host/test_recovery_multiprocess.py tests/host/test_watch_session_events.py tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py -q
python -m pyright dayu/ tests/ utils/
```

推荐补充：

```bash
source .venv/bin/activate
pytest tests/host -q
```

预期：

- 默认 pytest 不运行 stress tests。
- 显式 stress 命令运行所有 WU-STRESS-01 tests。
- `pytest --markers` 同时展示 `stress` 与 `timeout` marker。
- 默认 collect-only 与覆盖 addopts collect-only 的 selected / deselected 行为可解释。
- 受影响 Host regression tests 通过。
- pyright 0 errors。
- 无新增弱类型、无 `Any` / `object` 注解、无无类型参数 / 返回值。

## Review Gates

- **Plan review gate**:
  - 确认没有要求修改 Host public contract / durable schema / EventLog / recovery / scheduler production behavior。
  - 确认 watch reconnect 语义没有偷偷要求 replay cursor。
  - 确认 slices 都能独立 pyright-green，不制造中间红态。
- **Implementation review gate**:
  - 检查只改 allowed files。
  - 检查新增 helper 中文 docstring 完整，参数 / 返回值 / 异常齐全。
  - 检查 stress tests 都有 marker、timeout、deterministic release gate 和 summary failure message。
  - 检查 durable helper 只用于 fault injection / diagnostic，不绕过状态机制造成功。
  - 检查默认 pytest 排除策略实际有效。
- **Re-review gate**:
  - 针对 reviewer findings 修复后重新运行 stress 命令、受影响 Host tests 和 pyright。

## Stop Conditions

Implementation agent 必须停止并写 Blocking Questions For Controller，如果出现任一情况：

- 需要新增或修改 Host public API、public dataclass、`open_host` option、watch cursor / replay contract。
- 需要修改 durable schema、EventLog semantics、run / attempt transition helper 或 recovery 状态机。
- 需要修改 scheduler production close / drain / liveness 行为才能让 stress 通过。
- 需要依赖外部服务、真实 provider、随机 fuzz、不可控 sleep 或环境特定慢盘行为。
- stress tests 在本地重复运行不稳定，且无法通过 deterministic gate / 更小规模修复。
- pyright 报错需要扩大到 source 层修复。

## Risks / Open Questions

- **Watch reconnect 语义风险**: 当前 public watch 不支持 caller cursor。计划已把 reconnect 限定为“重新 attach 后观察后续 terminal”，断开窗口内 terminal 通过 primary watcher / public snapshot / outbox / durable diagnostic 证明不丢。若 controller 需要 replay gap，这是 blocking question。
- **Stress 耗时风险**: 新 suite 默认排除，显式命令运行。实现时要控制规模，避免把 hardening suite 变成不可用的长测。
- **Private diagnostic 风险**: 直接读取 durable rows 容易被误用为 truth。实现必须在 helper docstring 中声明 diagnostic / fault injection 边界，行为断言优先 public API。
- **Pytest addopts 覆盖风险**: 默认 `addopts` 排除 stress 后，显式 stress 命令必须使用 `-o addopts=""`。README 和 plan 已固定该命令。

## Blocking Questions For Controller

当前没有 blocking questions。设计真源、总控文档与代码证据足以按本 plan 进入 implementation gate。

若 controller 要求 watcher reconnect replay disconnect gap，请先裁决是否允许新增 public watch cursor/replay contract；在裁决前不得实现该语义。

## Completion Report Format

Implementation agent 完成后，最终报告必须使用以下格式：

```text
WU-STRESS-01 implementation report

Changed:
- ...

Stress slices completed:
- Slice 1 ...
- Slice 2 ...
- Slice 3 ...
- Slice 4 ...
- Slice 5 ...

Validation:
- `pytest tests/host/test_package_exports.py tests/host/test_host_production_stress.py -q`: ...
- `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q`: ...
- `pytest tests/host/test_recovery_multiprocess.py tests/host/test_watch_session_events.py tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py -q`: ...
- `python -m pyright dayu/ tests/ utils/`: ...

Structured summary:
- session_count: ...
- run_count: ...
- crash_count: ...
- recovery_count: ...
- watch_lag_max: ...
- scheduler_drained: ...
- liveness_stale_detected: ...
- terminal_duplicate_count: ...
- terminal_dedupe_ok: ...

Docs:
- tests/README.md updated / not updated because ...

Risks / uncovered:
- ...

Blocking questions:
- none / ...
```
