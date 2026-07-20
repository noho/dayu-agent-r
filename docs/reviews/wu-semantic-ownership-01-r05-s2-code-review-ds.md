# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Code Review（AgentDS 第二路）

日期：2026-07-16
Reviewer：AgentDS（独立第二路 adversarial review）
Controller validation artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-controller-validation.md`
Codex implementation artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-implementation-codex.md`

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- HEAD: `e077c70878bc47a2f1724d30f3ef22b8eb88e56f`
- Base: accepted S1 commit `c5af5613`（本 slice 相对 accepted S1 的四路径 diff）
- Output file: `docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-ds.md`
- Included scope（changed paths）:
  1. `tests/engine/test_agent_phase3_tool_call.py` — 新增 `_AwaitingExternalOperationExecutor` fake executor 与 `test_accepted_awaiting_external_operation_outlives_handshake_timeout`（+136 行）
  2. `utils/smoke_host_public_awaiting_entrypoint.py` — 重构为 phase-driven state machine（+1094/-97 行）
  3. `dayu/host/README.md` — 补充 observation timeout 语义段落（+2 行）
  4. `tests/README.md` — 纠正旧测试描述并登记新覆盖（+3/-2 行）
- Excluded scope（verified no-diff）:
  - `dayu/engine/agent.py` — 三重 no-diff（fixed base / accepted S1 / transition HEAD）
  - `dayu/engine/README.md` — no diff
  - `dayu/host/_wait_observation.py` — no diff
  - `dayu/host/waiting.py` — no diff
  - `dayu/host/durable/schema.py` — no diff
  - `dayu/host/dispatch.py` — no diff
  - `dayu/host/engine_ingest.py` — no diff
  - `docs/host/issues-implementation-control.md` — control doc 非 review 对象
  - 根 `README.md` / `dayu/README.md` — no diff
- Parallel review coverage: 无（单 reviewer 逐路径走读）

## Evidence baseline

本 review 直接阅读了以下真源文件作为判断依据：

| 文件 | 阅读范围 | 目的 |
|---|---|---|
| `dayu/engine/agent.py:1960-2100` | 工具批式执行、awaiting 分发、suspended 路径 | 验证 Engine 握手 timeout 边界 |
| `dayu/engine/agent.py:2164-2198` | `_execute_batch`、`await_or_cancel_or_timeout` | 验证 timeout 仅在 executor handshake 使用 |
| `dayu/engine/README.md:475-482` | 工具握手 timeout 章节 | 验证 Engine 公开契约与实现一致 |
| `dayu/host/wait_adapter.py:1-80` | 模块契约、error code 常量 | 验证 observation timeout error code 真源 |
| `dayu/host/wait_adapter.py:1552-1730` | `WaitPollerSupervisor`、`observation_diagnostics_snapshot` | 验证 smoke 访问的 public method |
| `dayu/host/_wait_observation.py:1-270` | token lifecycle、invalidation、timeout、diagnostics | 验证发布权撤销与迟到丢弃机制 |
| `dayu/host/open_host.py:660-710` | `_HostHandle.__slots__`、`_wait_poller` 字段 | 验证 `_wait_poller` 是私有字段 |
| `dayu/host/open_host.py:990-1010` | `_HostHandle.close` 的 wait poller close 路径 | 验证 close cleanup |
| `dayu/host/api.py:1126-1175` | `OpenHostOptions` 字段定义 | 验证 `_durable_options` 字段映射 |
| `dayu/host/durable/options.py:1-60` | `HostDurableStoreOptions`、`HostSQLiteStoragePolicy` | 验证独立 store options 构造 |
| `dayu/host/durable/state.py:2373-2440` | `read_wait_record_by_id`、`read_active_wait_records_for_run` | 验证 smoke 使用的 durable read 函数 |
| 四路径完整 diff（83.9KB） | 逐行走读 | 直接 review 对象 |

---

## Findings

### DS-01-未修复-中-`_WaitPollerDiagnosticsHost` Protocol 通过私有字段 `_wait_poller` 访问 poller diagnostics

- **入口/函数**: `_capture_smoke_state` → `cast(_WaitPollerDiagnosticsHost, host)._wait_poller`
- **文件(行号)**: `utils/smoke_host_public_awaiting_entrypoint.py:1162`
- **输入场景**: smoke 在 phase 等待循环中每次调用 `_capture_smoke_state` 读取 runner dropped count
- **实际分支**: `cast(_WaitPollerDiagnosticsHost, host)._wait_poller` 穿透 `Host` Protocol 直接访问 `_HostHandle` 的 `__slots__` 私有字段
- **预期行为**: Host 应在 `Host` Protocol 或等价的 public contract 上暴露 poller diagnostics 读取入口，smoke 通过 public API 获取 dropped count，不依赖私有字段名和实现类结构
- **实际行为**: smoke 定义了一个只包含 `_wait_poller: WaitPollerSupervisor | None` 的局部 Protocol，然后用 `cast()` 把 `Host` Protocol 强制转型为该局部 Protocol 来读取私有字段
- **直接证据**:
  - `open_host.py:668`：`"_wait_poller"` 在 `_HostHandle.__slots__` 中，命名以下划线开头，属于实现私有
  - `open_host.py:700`：`self._wait_poller = wait_poller` 在 `_HostHandle.__init__` 中赋值
  - `Host` Protocol（`api.py:3630`）不包含 `_wait_poller` 或任何 poller diagnostics 入口
  - `WaitPollerSupervisor.observation_diagnostics_snapshot()`（`wait_adapter.py:1713`）是 public method，但到达它的路径 `_wait_poller` 是私有的
  - smoke 中的 `_WaitPollerDiagnosticsHost` Protocol（smoke:230-232）只声明 `_wait_poller` 字段，不经过任何 Host public API
- **影响**: 若 `_HostHandle` 重命名 `_wait_poller` 字段、改为 property、或变更 poller 存储方式，smoke 会在运行时因 `AttributeError` 失败。这是 semantic ownership 的轻微漂移：smoke 把 `_HostHandle` 的私有字段名当作 de facto public contract。不过 smoke 是 `utils/` 下的脚本（非生产代码），且 `observation_diagnostics_snapshot()` 本身是 `WaitPollerSupervisor` 的 public method，所以实际风险限于 smoke 自身维护成本
- **建议改法和验证点**:
  1. 在 `Host` Protocol 或 `open_host` 模块中增加一个 public 入口（如 `read_poller_diagnostics() -> WaitObservationDiagnosticsSnapshot | None`），返回 `None` 表示 poller 未装配
  2. smoke 改为调用该 public 入口，不再使用 `cast` 穿透私有字段
  3. 若判定 smoke 场景不需要 poller diagnostics 成为 Host public contract，则至少在本 review 中标记为 deferred，并在 smoke 中加注释说明这是刻意允许的测试穿透
- **修复风险（低）**: 新增一个只读 public API 入口，不改变任何现有行为
- **严重程度（中）**: 虽然影响面限于 smoke 脚本，但这是在 R05（semantic ownership remediation）context 下新增的私有字段穿透，与 WU 目标方向不一致

---

### DS-02-未修复-低-`_durable_options` 独立投影 `OpenHostOptions` 到 `HostDurableStoreOptions` 与 Host 内部 store 构造逻辑重复

- **入口/函数**: `_durable_options` → `_read_wait_record` → `open_host_durable_store`
- **文件(行号)**: `utils/smoke_host_public_awaiting_entrypoint.py:1194-1225`
- **输入场景**: smoke 在 `_capture_smoke_state` 中通过独立只读 durable transaction 读取 wait record state
- **实际分支**: `_durable_options(options)` 从 `OpenHostOptions` 逐字段构造 `HostDurableStoreOptions`，然后 `open_host_durable_store` 打开第二个 SQLite connection
- **预期行为**: smoke 应复用 Host 已有的 durable read path，或至少与 Host 内部 store 构造共享同一个 options projection helper
- **实际行为**: smoke 用 30 行代码逐字段投影 `OpenHostOptions` → `HostDurableStoreOptions`（含 `PayloadStoragePolicy` 与 `HostSQLiteStoragePolicy` 子对象），逻辑与 Host 内部 `open_host` 中构建 durable store 的路径平行但不共享
- **直接证据**:
  - `_durable_options` 显式映射了 `db_path`、`artifact_root`、`payload_inline_threshold_bytes`、`create_parent_dirs` 和 5 个 `sqlite_*` 字段
  - 该映射与 `open_host.py` 中构造 `HostDurableStore` 的路径使用同一组 `OpenHostOptions` 字段
  - 若 `OpenHostOptions` 新增 mandatory 字段，`_durable_options` 需要同步更新，否则 smoke 在 `open_host_durable_store` 时会因 typed options 校验失败而抛出（fail closed，不会静默成功）
- **影响**: 维护成本——两处需要同步的 options projection。但由于 typed options 校验 fail closed，不会产生静默数据损坏。smoke 是 `utils/` 脚本，不受测试覆盖率要求约束
- **建议改法和验证点**:
  1. 若 Host 内部已有 `OpenHostOptions` → `HostDurableStoreOptions` 的公共投影 helper，smoke 应复用
  2. 若不存在该 helper，可接受当前实现并在 smoke 注释中标注同步风险
  3. 最低限度：在 `_durable_options` 的 docstring 中补充注释，说明字段映射需与 `OpenHostOptions` 中的 durable store 相关字段保持同步
- **修复风险（低）**: 仅影响 smoke 脚本
- **严重程度（低）**: fail closed，影响面仅 smoke 维护

---

### DS-03-未修复-低-Engine regression test 的"独立 operation"实为同 event loop 的 `asyncio.sleep`，未完全模拟真实跨线程/跨进程独立 operation

- **入口/函数**: `_AwaitingExternalOperationExecutor._run_external_operation`
- **文件(行号)**: `tests/engine/test_agent_phase3_tool_call.py:407-414`
- **输入场景**: `test_accepted_awaiting_external_operation_outlives_handshake_timeout` 以 0.1s 握手预算和 0.25s operation 时长运行
- **实际分支**: `_run_external_operation` 用 `asyncio.sleep(self.operation_duration_seconds)` 模拟独立 operation，该 task 运行在 Engine Agent 所在的同一 event loop 中
- **预期行为**: test 目标是证明"Engine 握手 timer 不拥有 accepted awaiting 后的独立 operation"。当前实现通过 `asyncio.create_task` 创建 operation task 并在握手返回后不 await 它，确实证明了 Engine 不会取消或等待它
- **实际行为**: operation task 与 Engine Agent 共享同一个 event loop。在极端情况下（如 event loop 被阻塞），operation task 也会被延迟。但 Engine 的 `await_or_cancel_or_timeout` 同样依赖 event loop 调度，因此 handshake timeout 和 operation 受同样的底层调度影响。在当前实现下，这不会导致 false positive（因为 handshake timeout 先于 operation 完成触发）
- **直接证据**:
  - `agent.py:2180-2184`：`await_or_cancel_or_timeout` 只包裹 `_call_tool_executor` 的 await
  - `agent.py:2017-2018`：接到 `ToolAwaitingOutcome` 后直接进入 suspended path，不再读 timeout
  - test 断言 `operation_finished_at - operation_started_at > _AWAITING_HANDSHAKE_TIMEOUT_SECONDS`（实测时长大于握手预算）
  - test 断言 `not executor.operation_cancelled`（operation 未被取消）
- **影响**: test 提供的证据强度略低于真正的跨线程 operation（如 `asyncio.to_thread` 中的 `time.sleep`），但已充分证明 Engine 不拥有 accepted operation 的生命周期。不影响 test 的有效性
- **建议改法和验证点**: 无需修改。当前实现在同 event loop 约束下提供了最大证据强度。若需要更强证据，可将 `_run_external_operation` 改为 `asyncio.to_thread(time.sleep, ...)` 但会引入额外线程管理复杂度，且不会实质性增强证据
- **修复风险（低）**: 无需修复
- **严重程度（低）**: test 证据充分，此发现属于 adversarial completeness note，不构成 defect

---

### DS-04-未修复-低-smoke timing margin（0.03s / 5×0.005s quantum）在极端慢 CI 上可能产生 false negative

- **入口/函数**: `_assert_static_timing_contract` → margin vs quantum 校验
- **文件(行号)**: `utils/smoke_host_public_awaiting_entrypoint.py:939-943`
- **输入场景**: CI worker 在 `_wait_for_state` 的 0.005s quantum 循环中因 OS 调度延迟导致连续多次循环实际耗时远超 quantum
- **实际分支**: `_wait_for_state` 使用 `asyncio.sleep(min(0.005, remaining))` 做 state polling，每次 sleep 后重新读取 owner state 并检查谓词。如果 OS 调度导致单次 sleep 实际耗时显著大于 0.005s（例如 GC pause），可能错过短暂的 state 窗口
- **预期行为**: margin = 0.03s >= 5 × 0.005s，按照最坏情况 5 个 quantum 内应能捕获 state 变化
- **实际行为**: 静态校验通过（0.03 >= 0.025），但在极端负载下 5 个 quantum 可能不够。然而：
  - 所有关键 state transition 由 `threading.Event` / `asyncio.Event` 驱动，不依赖 polling 发现
  - `_wait_for_state` 仅用于等待 durable state 落盘（如 `_is_durable_waiting`、`_is_first_timeout_release`、`_is_late_publication_dropped`）
  - durable write 是持久化操作，state 一旦写入就不会短暂出现后消失
  - overall deadline 15.0s 提供充足 headroom
- **影响**: 在极端慢 CI 上，state polling 可能因 quantum 不足而延迟发现已成立的 state，但在 15s overall deadline 内极大概率能发现。false negative 概率极低
- **建议改法和验证点**: 当前 margin 足够。若 CI 历史中出现 `_wait_for_state` timeout，可将 `_TEST_RELATIVE_MARGIN_SECONDS` 调至 0.05s 或增大 `_TEST_STATE_POLL_QUANTUM_SECONDS` 到 0.01s
- **修复风险（低）**: 仅 smoke 调参
- **严重程度（低）**: 实际风险极低，属于 adversarial completeness 记录

---

### DS-05-未修复-低-`_TimedLateReadyPollAdapter.poll_wait` 首轮 observation 中 `operation_finished.wait()` 无限阻塞依赖 observation runner timeout 释放

- **入口/函数**: `_TimedLateReadyPollAdapter.poll_wait`
- **文件(行号)**: `utils/smoke_host_public_awaiting_entrypoint.py:1456-1458`
- **输入场景**: 首轮 observation（`observation_index == 1`）时，poller 线程调用 `self._operation.operation_finished.wait()` 无限期阻塞
- **实际分支**: `poll_wait` 在首轮 observation 中调用 `threading.Event.wait()` 无 timeout 参数，线程阻塞直到 operation 完成（0.30s）
- **预期行为**: 该阻塞是被设计的行为——observation runner 的 timeout（0.15s）会先触发并 invalidate token，随后迟到结果被丢弃。线程在 operation 完成后返回的结果不会进入 `resolve_wait`
- **直接证据**:
  - `_wait_observation.py:208-210`：`result_queue.get(timeout=timeout_seconds)` 超时后调用 `_invalidate_token`
  - `_wait_observation.py:124-138`：`invalidate()` 将 token state 从 ACTIVE 改为 INVALIDATED，迟到结果无法通过 lifecycle gate 发布
  - smoke 中的 `_is_late_publication_dropped` 谓词断言 `runner_dropped_count >= 1`，验证迟到结果确实被丢弃
- **影响**: 如果 `operation_finished` 永远不触发（例如 `_ExternalOperationController._run_external_operation` 因未捕获异常崩溃），首轮 observation 线程将永久阻塞。但由于：
  - `_run_external_operation` 只有 `asyncio.sleep` 和 event.set，不会抛异常
  - smoke 的 `finally` 块中 `operation.abort()` 会 set `operation_finished` 和 `late_result_release`
  - observation 线程是 daemon thread，进程退出时自动终止
  实际风险极低
- **建议改法和验证点**: 可考虑给 `operation_finished.wait()` 加 timeout（如 `_TEST_OVERALL_DEADLINE_SECONDS`），超时后抛出 `RuntimeError` 使 failure 更可诊断。当前实现可接受
- **修复风险（低）**: 仅在 smoke 适配器中增加 timeout 参数
- **严重程度（低）**: 依赖外部 guarantee 的无限阻塞，但 smoke cleanup 提供 safety net

---

## Adversarial Challenge 逐项回应

### 1. Engine no-diff owner 与新增 regression 是否真实证明 accepted awaiting external operation 不受 handshake timer 拥有

**真实**。三条证据链独立且互相印证：

- `agent.py:1974` 仅将 `tool_execution_timeout_seconds` 投影到 `BatchToolExecutionContext.timeout_seconds`
- `agent.py:2180-2184` 仅在 `_execute_batch` 的 `await_or_cancel_or_timeout(...)` 中使用该值包裹 `_call_tool_executor` 的 await
- `agent.py:2017-2018` 接到 `ToolAwaitingOutcome` 后走 `if awaiting_records:` 分支（line 2055），调用 `_make_suspended_terminal_with_close`（line 2083），该路径不再读取任何 timeout

Engine README:480-482 明确声明："该 timeout 只表示 Engine 不再等待 batch handshake outcome；不证明工具内部线程、子进程、HTTP 请求或远端 job 已停止"。

test 的 fake executor 不是 self-proving：它记录 `handshake_started_at`/`handshake_returned_at` 证明握手在预算内返回（`< 0.1s`），记录 `operation_started_at`/`operation_finished_at` 证明 operation 实测越过预算（`> 0.1s`），并断言 `not operation_cancelled` 证明未被 Engine timer 取消。cleanup 路径在 `finally` 块中取消并 await operation task，无 task leak。

### 2. Public smoke 是否保留 packaged ConfigLoader/provider discovery/Service composition/open_host/durable poller/public terminal/outbox 主链

**保留**。逐段验证：

- `_prepare_packaged_entrypoint_runtime` 仍通过 `ConfigLoader` + provider discovery + Service composition 产出 `_CompositionSmokeMatrix`
- `open_host(options)` 仍使用从 composition 派生的 deterministic options
- `submit_entrypoint_turn_and_wait` 仍走 public submit/wait path
- `host.get_run()`、`host.read_outbox_terminal_items()` 仍通过 public Host API
- `_TimedLateReadyPollAdapter` 替换外部依赖（真实 Fins poll adapter），`_AwaitingThenAnswerWorkerFactory` 替换外部依赖（真实 process-backed worker）
- 无 self-implemented Host timeout/backoff/terminal 语义

### 3. 首轮 timeout、claim release/backoff、diagnostic、late Ready dropped、真实 due、second Ready、Run/outbox terminal 是否从真实 owner 读取并同源

**是**。逐项验证：

- **首轮 timeout**: `_is_first_timeout_release` 谓词从 `WaitRecordRow`（durable owner）读取 `poll_claim_id is None`（claim released）、`poll_backoff_attempt == 1`、`poll_last_outcome is ADAPTER_ERROR`、`poll_last_error_code == "wait_observation_timeout"`
- **claim release/backoff**: `_assert_timeout_release_state` 断言 claim 四字段全部为 None，并从 `poll_next_observe_at - updated_at` 计算 backoff delay，与 `_TEST_INITIAL_BACKOFF_SECONDS` 比较（tolerance 0.01s）
- **diagnostic**: `poll_last_error_code == "wait_observation_timeout"` 与 `wait_adapter.py:73` 的 `_POLL_ERROR_CODE_OBSERVATION_TIMEOUT` 常量为同一真源
- **late Ready dropped**: `_is_late_publication_dropped` 通过 public `observation_diagnostics_snapshot().dropped_count >= 1`（`WaitPollerSupervisor` public method）和 public `RunSnapshot.status is WAITING` + durable `WaitRecordStatus.WAITING` 交叉验证
- **真实 due**: `_wait_for_state` 轮询 owner state，不做 fixed sleep
- **second Ready**: `_TimedLateReadyPollAdapter` 的 `observation_index == 2` 分支断言 `operation_finished.is_set()`，然后返回 authoritative `WaitPollReady`
- **Run/outbox terminal**: `host.get_run()` 返回 public `RunSnapshot.status is SUCCEEDED`，`host.read_outbox_terminal_items()` 返回 terminal outbox，且 terminal event id 与 outbox item 精确一致

### 4. 约 `+1094/-97` smoke 增量是否是 plan 十项 contract 的最小可维护实现

**是**。逐模块评估：

| 模块 | 行数估算 | 职责 | 是否可合并/删除 |
|---|---|---|---|
| Timing constants | ~15 | 十项常量定义 | 不可合并，每项独立语义 |
| `_SmokePhaseContext` | ~40 | phase ledger + deadline 管理 | 单一职责，不可删除 |
| `_ExternalOperationController` | ~85 | 独立 operation + thread event 协调 | 单一职责 |
| `_WaitPollerDiagnosticsHost` Protocol | ~5 | 私有字段访问类型标注 | 见 DS-01 |
| Phase wait helpers（4个） | ~80 | 统一 deadline 管理的 event/state wait | 四个函数共享 deadline 模式但不重复逻辑 |
| `_capture_smoke_state` + `_read_wait_record` + `_durable_options` | ~90 | 跨 public/durable/poller 状态快照 | `_durable_options` 见 DS-02 |
| State predicates（3个） | ~50 | 三个不同 phase 的状态判断 | 每个谓词断言不同 phase 的不同字段组合，不可合并 |
| Assertion helpers（5个） | ~90 | 静态/动态 timing、handshake、timeout release、packaged policy | 每个断言不同 contract |
| `_phase_failure` | ~55 | deadline 失败诊断 | 单一职责 |
| `_TimedLateReadyPollAdapter` | ~50 | 替换旧 `_GatedReadyPollAdapter` | 新语义需要新 adapter |
| `_AwaitingThenAnswerWorkerFactory` 改造 | ~30 | 增加 handshake timing | 必要扩展 |
| Main flow 重构 | ~200 | condition-driven phase 序列 | plan 核心要求 |

无 God script/helper、无重复 typed option projection、无测试夹具职责混合。每个 helper 有单一清晰职责，模块级私有函数结构合理。

### 5. Private `_wait_poller` diagnostics cast 与独立 durable read `_durable_options` 是否必要且边界正确

**`_wait_poller` cast**：必要（smoke 需要读取 dropped count 验证迟到丢弃），但边界不正确（见 DS-01）。

**`_durable_options` 独立 read**：必要（smoke 需要通过 durable owner 读取 wait record state 做交叉验证），边界基本正确（显式 typed 字段映射，fail closed），但与 Host 内部 store 构造有逻辑重复（见 DS-02）。

两者都不是"不当私有耦合/第二 source of truth"：
- wait record 的 source of truth 是 SQLite durable store，smoke 通过 durable owner 的 public read functions（`read_wait_record_by_id`、`read_active_wait_records_for_run`）读取，不绕过 owner
- dropped count 的 source of truth 是 `WaitObservationRunner.diagnostics_snapshot().dropped_count`（public method），smoke 只是通过私有路径到达它

### 6. Timing constants、四条 inequality、event/condition/state 驱动、单一 deadline、慢 CI 边界、false pass/fail、thread/task/Host close 与失败 cleanup

**Timing constants**：十条常量均在模块级定义，命名以 `_TEST_` 前缀区分测试意图。

**四条 inequality**：静态校验（`_assert_static_timing_contract`）+ 动态校验（`_assert_measured_timing_contract`）。全为 strict inequality（`<`），margin 条件为 `>=`。逻辑正确。

**Event/condition/state 驱动**：11 个 phase 中 6 个由 `threading.Event`/`asyncio.Event` 驱动，4 个由 owner state predicate 驱动，1 个由 public terminal task 驱动。无 business-logic fixed sleep。

**单一 deadline**：`_remaining_seconds` 从 `started_at + _TEST_OVERALL_DEADLINE_SECONDS`（15.0s）单调递减，所有 wait helper 共用。

**慢 CI 边界**：见 DS-04。

**False pass 风险**：低。关键断言使用精确 state predicate（如 `_is_first_timeout_release` 断言 9 个字段），不依赖宽松匹配。`_assert_packaged_policy_snapshot` 精确断言 12 字段 tuple 完全相等。

**False fail 风险**：低。timing 使用 `time.monotonic()`（不受系统时钟调整影响），backoff delay 有 0.01s tolerance。

**Thread/task cleanup**：
- smoke `finally` 块：`operation.abort()` → cancel task + await + set events，`submit_task.cancel()` + await
- test `finally` 块：cancel operation task + await + catch `CancelledError`
- Host close：`_HostHandle.close()` 先 close `_wait_poller`（`asyncio.to_thread`），再 stop scheduler、drain actor、close stores

**失败诊断**：`_phase_failure` 输出 completed/pending phases、monotonic elapsed、Run status、9 个 wait record 字段、dropped count、terminal outbox。充分覆盖排障所需信息。

### 7. `agent.py` no diff、Engine branch-aware 78% / statement 80.458% 解释、Host 83%/86%、Ruff registry 165、pyright 与验证证据是否可信

**`agent.py` no diff**：可验证。`git diff c5af5613..e077c708 -- dayu/engine/agent.py` 在当前分支上应为 exit 0。Controller validation 已独立确认。

**Engine coverage 解释**：`agent.py` statement coverage 597/742 = 80.458%，branch-aware combined = 77.626%（显示 78%）。计划中"agent.py=80%"指 statement coverage。两数如实保留，78 未伪装成 80。且 `agent.py` 不是 S2 的 changed production file，无新增 coverage debt。

**Host coverage**：`durable/state.py=83%`、`wait_adapter.py=86%`，两者均通过 `--fail-under=80`。这是 S1 changed-owner 文件的 coverage，S2 未新增 production Python diff。

**Ruff registry**：fixed base 167 → accepted S1 165 → current S2 165。machine-readable JSON 比对确认 current == accepted S1。两条 removal 已登记为 S1 changed-file F401。

**pyright**：Controller 独立确认 0 errors, 0 warnings, 0 informations。

**验证证据可信**。所有数值有独立复核记录。

### 8. README 是否只写 current contract 并遵守各自更新约束

**Host README**（`dayu/host/README.md`）：
- 新增段落只描述当前实现：observation timeout 是本地诊断、late Ready 不进入 resolve、cancelled abandon 不写 `poll_abandoned_at`、typed outcome 拥有终态
- 未写实施过程、未来 policy、内部治理术语
- 符合 Host README 的 Waiting 章节职责

**Tests README**（`tests/README.md`）：
- 纠正了两处旧描述：`stuck poll→LOST` → `observation timeout 后 WAITING retry`、`abandon timeout marker` → `cancelled abandon timeout retry`
- 新增一行登记 public awaiting entrypoint smoke 覆盖边界
- 新增 Engine regression 描述（"accepted awaiting 握手返回后独立 operation 可越过工具握手预算且不被 Engine timer 取消"）
- 符合 Tests README 更新约束

**未修改的 README**：Engine README 已有 handshake timeout 边界描述（line 480-482），无需补充；根 README / `dayu/README.md` 无用户入口或分层变化，保持 no diff。

### 9. Retained safety、scheduler residual、Issue 175/callback/unified authorization/R06+ deferred boundary 是否保持

**Retained safety**：
- `_wait_observation.py` token invalidation、generation、lock 未修改
- `wait_adapter.py` claim CAS、release/backoff 均保持原 owner
- cancellation、capacity、close-drain、typed LOST 测试全部保持

**Scheduler residual**：Controller 独立 `test_r05_scheduler_close_probe.py` 仍为 `1 passed`（以 `HostApiError` 为通过条件）。未修、未隐藏、未 waive。

**Deferred**：production added-lines 对 `authorization|permission|callback transport|process isolation|process_backed|subprocess|Issue 175` 零命中。Issue 175、callback、unified authorization、R06+ 均保持 deferred。

### 10. Allowlist/no-diff owners 与没有 hidden production behavior

**Allowlist**：五条 changed paths 均在 implementation evidence 声明的 allowlist 内：
1. `tests/engine/test_agent_phase3_tool_call.py`
2. `utils/smoke_host_public_awaiting_entrypoint.py`
3. `dayu/host/README.md`
4. `tests/README.md`
5. `docs/reviews/wu-semantic-ownership-01-r05-s2-implementation-codex.md`（untracked artifact）

**No-diff owners**：Engine `agent.py`/README、S1 七路径、control doc、scheduler owners、根/dayu README 均 no diff。

**No hidden production behavior**：changed test/smoke 中无 `hasattr`/`getattr`、monkeypatch、`.resolve_wait(...)` shortcut、无参 `WaitPollerRuntimePolicy()`、`poll_next_observe_at` mutation 或 `with_entrypoint_wait_poller_policy`。`mark_wait_record_poll_abandon_timeout` 与 `_MarkWaitRecordAbandonTimeoutOperation` 零定义、零调用。

---

## Verdict

**PASS — 可以进入 Controller 裁决。**

本 slice 的 Engine no-diff regression、public smoke contract、README 更新和 timing/phase 驱动验证均正确。四路径改动忠实执行了 accepted R05-S2 plan。四项 findings（DS-01 中、DS-02 低、DS-03 低、DS-04 低、DS-05 低）均不构成 merge blocker：

- **DS-01（中）**：私有字段穿透与 WU semantic ownership 目标方向不一致，建议修复但可在 Controller 裁决为 deferred
- **DS-02～DS-05（低）**：均为 smoke/test 脚本级别的 maintainability/robustness 注意事项，不阻塞 merge

## Open Questions

1. Host 是否计划在 `Host` Protocol 中暴露 poller diagnostics public API？若有计划，DS-01 可在该 API 落地后自然修复
2. `OpenHostOptions` → `HostDurableStoreOptions` 投影在 Host 内部是否有可复用的公共 helper？若有，DS-02 可简化

## Residual Risk

1. **Scheduler residual**（已知，未引入）：scheduler close / terminal promotion coordination race 仍可复现，本 slice 未修未隐藏
2. **Cancelled wait 的 abandon observation 无限重试**（已知，deferred）：若 provider 从不返回 explicit lifecycle terminal outcome，可能按 capped backoff 长期重试。R05 已保证 claim CAS、bounded capacity、finite observation timeout 与 late-publication fencing，不发明 terminal evidence
3. **`_durable_options` 字段同步**（低）：若 `OpenHostOptions` 新增 mandatory durable store 字段，smoke 需同步更新 `_durable_options`
4. **Slow CI timing margin**（低）：参见 DS-04
5. **Engine coverage**：`agent.py` statement 80.458%、branch-aware 78% 不是 S2 新增 debt，但 Engine 整体 coverage 仍有提升空间

---

## Reviewed Evidence Inventory

| 证据类型 | 路径 | 状态 |
|---|---|---|
| S2 四路径 diff | `tests/engine/test_agent_phase3_tool_call.py`、`utils/smoke_host_public_awaiting_entrypoint.py`、`dayu/host/README.md`、`tests/README.md` | 逐行走读完成 |
| Engine timeout owner | `dayu/engine/agent.py:1960-2100,2164-2198` | 三重 no-diff 确认 |
| Engine README contract | `dayu/engine/README.md:475-482` | 与实现一致 |
| Host observation token fence | `dayu/host/_wait_observation.py:1-270` | 未修改，机制正确 |
| Host poller diagnostics API | `dayu/host/wait_adapter.py:1713-1721` | public method 确认 |
| Host `_wait_poller` 字段 | `dayu/host/open_host.py:660-710` | 私有字段确认 |
| Host close cleanup | `dayu/host/open_host.py:990-1010` | wait poller close 路径确认 |
| Durable read functions | `dayu/host/durable/state.py:2373-2440` | public read API 确认 |
| OpenHostOptions fields | `dayu/host/api.py:1126-1175` | 字段映射验证 |
| Durable store options | `dayu/host/durable/options.py:1-60` | typed options 构造验证 |
| Implementation evidence | `docs/reviews/wu-semantic-ownership-01-r05-s2-implementation-codex.md` | 全文阅读，逐项复核 |
| Controller validation | `docs/reviews/wu-semantic-ownership-01-r05-s2-controller-validation.md` | 全文阅读，独立复核 |
| Control doc | `docs/host/issues-implementation-control.md` | 确认非 review 对象 |
| Project instructions | `AGENTS.md`、`CLAUDE.md` | 全文阅读，约束检查 |
