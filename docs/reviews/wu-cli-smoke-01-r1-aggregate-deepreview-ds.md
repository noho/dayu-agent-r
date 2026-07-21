# WU-CLI-SMOKE-01-R1 Aggregate Deepreview — AgentDS

## Scope

- **Mode**: current changes
- **Branch**: `phaseflow/wu-cli-smoke-01-r1`
- **Base**: `bd1d3e94` (PR #179 merge commit, prerequisite)
- **Output file**: `docs/reviews/wu-cli-smoke-01-r1-aggregate-deepreview-ds.md`
- **Included scope**:
  - Accepted plan: `docs/host/wu-cli-smoke-01-r1-engine-delta-transient-live-stream-plan.md`
  - All plan review/fix/re-review/adjudication artifacts (8 files)
  - Slice 1 production contract: `dayu/host/transient_delta.py`, `dayu/host/api.py`, `dayu/host/engine_ingest.py`, `dayu/host/open_host.py`, `dayu/host/dispatch.py`, `dayu/host/read_api.py`, `dayu/host/lifecycle_events.py`, `dayu/host/__init__.py`, `dayu/service/entrypoint_runtime.py`, `dayu/cli/thinking.py`
  - Slice 2 tests/README: all test files (12 new/modified), support modules, CLI E2E
  - All review/fix/adjudication artifacts for Slice 1 and Slice 2 (20 files)
  - Design doc: `docs/host/design.md`
  - Control doc: `docs/host/issues-implementation-control.md` (read-only)
  - READMEs: `dayu/README.md`, `dayu/host/README.md`, `dayu/service/README.md`, `tests/README.md`
- **Excluded scope**: Engine code, runtime code (not modified by this WU), plan-fix gate artifacts superseded by accepted plan, obsolete/resolved review discussion threads
- **Parallel review coverage**:
  - Subagent 1: `transient_delta.py` hub/subscription — level-triggered wakeup, fanout snapshot, terminal fence, close semantics, overflow, bounded queue backpressure
  - Subagent 2: `engine_ingest.py` → `dispatch.py` → `transient_delta.py` publish chain — three-delta unified path, reasoning durable removal, transaction-after-commit timing, validation/publish gating, publisher wiring
  - Subagent 3: `entrypoint_runtime.py` → `thinking.py` → `__init__.py` consumer chain — union branching, bounded relay, backpressure propagation, CLI identity migration, old export cleanup
  - Subagent 4: all test files — 3×1000 stress, slow/fast watcher, deterministic barrier, DS-F02 E2E, terminal fence, private API coupling, fake/mock risk
  - Controller (AgentDS): static grep boundary checks, README consistency, design doc alignment, adversarial failure pass, semantic ownership drift, overcoupling
- **Review date/time**: 2026-07-21

## Findings

### 01-未修复-低-test_subscription_count_穿透私有类访问内部属性

- **入口/函数**: `_subscription_count` helper
- **文件(行号)**: `tests/host/test_watch_session_events.py:1211-1222`
- **输入场景**: 任意需要断言 subscription 数量的测试
- **实际分支**: `isinstance(host, _PublicHostHandle)` 后访问 `host._transient_delta_hub.subscription_count(session_id)`
- **预期行为**: subscription count 应通过 `Host` public protocol 暴露，或通过 public observable behavior 间接验证（如 watcher detach 后的行为差异）
- **实际行为**: 绕过 public protocol，直接依赖私有类 `_PublicHostHandle` 和其私有属性 `_transient_delta_hub`
- **直接证据**: L1211 `from dayu.host.open_host import _PublicHostHandle`；L1216-1218 `isinstance(host, _PublicHostHandle)` + `host._transient_delta_hub.subscription_count(session_id)`
- **影响**: 若 `_PublicHostHandle` 重命名其内部 hub 属性，该测试崩溃而 public contract 未变 — 测试与实现细节过度耦合
- **建议改法和验证点**: 在 `Host` public protocol 新增 `subscription_count(session_id)` 方法，或删除该 helper 改用 public behavior 间接验证
- **修复风险（低）**: 只改测试，不动生产代码
- **严重程度（低）**: 非 blocking，测试耦合问题，不影响生产正确性

### 02-未修复-低-Service测试直接导入私有模块级类型和函数

- **入口/函数**: 多个 Service 测试函数
- **文件(行号)**: `tests/service/test_entrypoint_runtime.py:82-85`
- **输入场景**: Service 层 relay queue 容量断言测试
- **实际分支**: 测试直接 import `_WatchAndWaitRuntime`, `_WatcherFailure`, `_close_watch_and_wait_runtime`, `_create_watch_and_wait_runtime`, `_drain_host_events`
- **预期行为**: relay queue 容量应通过 public API 的 slow-consumer 集成测试（`test_transient_slow_consumer_path.py`）间接验证，不依赖私有符号
- **实际行为**: 测试直接构造 `_WatchAndWaitRuntime` 实例并访问 `runtime.queue.maxsize`，将测试耦合到模块内部实现细节
- **直接证据**: L82-85 从 `dayu.service.entrypoint_runtime` 导入五个 `_` 前缀的私有符号
- **影响**: 若 `_WatchAndWaitRuntime` 内部结构变化，测试编译/运行失败而 Service public behavior 未变
- **建议改法和验证点**: 队列容量行为已由 `test_transient_slow_consumer_path.py` 的 E2E 集成测试覆盖（通过 `_wait_for_yielded_count` 隐式验证容量），可将这些单元测试中的私有符号访问改为 public API 驱动的行为断言，或删除重复断言
- **修复风险（低）**: 只改测试，不动生产代码
- **严重程度（低）**: 非 blocking，测试耦合问题，不影响生产正确性

### 03-未修复-低-deterministic_barrier测试替换私有_ready_Event

- **入口/函数**: `test_subscription_publish_before_wait_is_level_triggered`, `test_subscription_wait_before_publish_wakes_at_barrier`, `test_subscription_drain_clear_publish_intersection_rechecks_owner_state`
- **文件(行号)**: `tests/host/test_transient_delta.py:246, 272, 303`
- **输入场景**: deterministic barrier 并发交错测试
- **实际分支**: 测试直接执行 `subscription._ready = controlled_event` 替换内部 `asyncio.Event`
- **预期行为**: barrier 测试是最小侵入性的验证方式，当前实现合理；但应显式化该依赖
- **实际行为**: 直接操作私有 `_ready` 属性 — 若 readiness 机制从单一 Event 演进为更复杂状态机，这些测试全部失效
- **直接证据**: L246 `subscription._ready = _WaitEnteredEvent()`；L272 `subscription._ready = _PublishOnClearEvent(...)`；L303 同上
- **影响**: 测试对 `_ready` 的实现细节（单一 asyncio.Event）形成隐式契约
- **建议改法和验证点**: 当前可接受；建议在 `HostTransientDeltaSubscription` 的类 docstring 中标注 `_ready` 字段的语义合约为 level-triggered wakeup primitive，使测试依赖显式化
- **修复风险（低）**: 只改文档注释，或保持现状
- **严重程度（低）**: 非 blocking

### 04-未修复-低-_FakeHost顺序索引状态机存在静默调用次数漂移风险

- **入口/函数**: `_FakeHost` 类的 `get_run`, `read_outbox_terminal_items`, `get_session` 方法
- **文件(行号)**: `tests/service/test_entrypoint_runtime.py:333-550`
- **输入场景**: Service 层对 Host 的调用次数或顺序发生合理变化
- **实际分支**: `_FakeHost` 使用 `_run_status_index`, `_outbox_index`, `_session_snapshot_index` 等顺序计数器，每次调用自动推进索引
- **预期行为**: 测试应能检测到 Host 调用次数的意外变化
- **实际行为**: 若生产代码中 polling 逻辑增加一次额外 `get_run` 调用，`_FakeHost` 静默返回下一个预设值，测试通过但语义已偏离
- **直接证据**: L333-550 `status_index = min(self._run_status_index, len(self._run_statuses) - 1)` + `self._run_status_index += 1`
- **影响**: 测试对 Service→Host 调用次数的断言不精确，无法检测调用次数漂移
- **建议改法和验证点**: 为 `_FakeHost` 增加 `strict` 模式或在测试 tearDown 中断言所有预设值恰好消耗完毕
- **修复风险（低）**: 只改测试工具类
- **严重程度（低）**: 非 blocking，测试工具改进

### 05-未修复-低-_SlowConsumerHostProbe使用cast绕过类型检查

- **入口/函数**: `test_slow_consumer_path` 的 service task 创建
- **文件(行号)**: `tests/cli/test_transient_slow_consumer_path.py:289`
- **输入场景**: `submit_entrypoint_turn_and_wait` 接收 `_SlowConsumerHostProbe` 实例
- **实际分支**: `cast(Host, probe)` 将不完整实现强制转为 `Host` 类型
- **预期行为**: 若 Service 新增对其他 `Host` 方法的调用，应获得编译时类型错误而非运行时 `AttributeError`
- **实际行为**: `cast()` 绕过静态类型检查，`_SlowConsumerHostProbe` 只实现所需方法子集
- **直接证据**: L289 `cast(Host, probe)`
- **影响**: 未来 Service 代码变更将得到运行时崩溃而非编译时保护
- **建议改法和验证点**: 为 `_SlowConsumerHostProbe` 增加 `__getattr__` 委托给真实 Host，未拦截的方法自动透传
- **修复风险（低）**: 只改测试 probe 类
- **严重程度（低）**: 非 blocking，测试工具改进

### 06-未修复-低-缺少close与publish并发竞争场景测试

- **入口/函数**: `HostTransientDeltaHub.publish` + `HostTransientDeltaSubscription.close` / `_close_from_hub`
- **文件(行号)**: 覆盖缺失，`tests/host/test_transient_delta.py` 中无对应测试
- **输入场景**: 一个协程执行 `publish()` 同时另一个协程执行 `close()`，且第三个协程在 `wait_ready()` 等待
- **实际分支**: 现有四个 barrier 测试覆盖 publish-before-wait、wait-before-publish、drain/clear+publish、overflow/close — 但全部是串行序列
- **预期行为**: close 和 publish 并发时，waiter 被唤醒后状态一致（subscription count = 0，waiter 不丢 item 也不死锁）
- **实际行为**: 缺少并发交错测试
- **直接证据**: `test_transient_delta.py` 中所有 barrier 测试使用受控 event 序列而非 `asyncio.gather` 并发
- **影响**: asyncio 单线程模型下 publish/close 不会真正并发执行，风险极低；但测试未覆盖"close 与 publish 在同一事件循环迭代中交错"的更细微场景
- **建议改法和验证点**: 新增一个使用 `asyncio.gather` 的并发测试，在 waiter 已进入 `wait_ready` 时同时 publish 和 close
- **修复风险（低）**: 只新增测试
- **严重程度（低）**: 非 blocking，incremental coverage improvement

### 07-未修复-低-_replace_event_payload绕过写入路径校验做故障注入

- **入口/函数**: `_replace_event_payload` helper
- **文件(行号)**: `tests/host/test_watch_session_events.py:1225-1254`
- **输入场景**: `test_watch_first_and_subsequent_durable_failures_are_public_and_detach`
- **实际分支**: 直接 `UPDATE event_log SET payload_json = ?` 写入畸形 JSON
- **预期行为**: 故障注入是合理的测试技术，但当前方式只能模拟 payload 字段损坏，无法覆盖磁盘级损坏（如 page 损坏、整行损坏）
- **实际行为**: 直接 SQL UPDATE 绕过 EventLog append 写入路径的全部校验（codec、digest、schema 验证）
- **直接证据**: L1225-1254 `connection.execute(f"UPDATE {TABLE_EVENT_LOG} SET payload_json = ? WHERE event_id = ?", ...)`
- **影响**: 注入的故障模式在真实系统中不会自然出现（所有写入都经过 codec），可能与真实 corruption 模式不同
- **建议改法和验证点**: 当前可接受；建议补充文件系统级损坏测试（截断 SQLite db 文件）
- **修复风险（低）**: 只新增可选测试
- **严重程度（低）**: 非 blocking，incremental coverage improvement

## Adversarial Failure Pass

以下 adversarial 审查维度均通过，未发现生产级缺陷：

### 三类 delta 唯一 owner、transaction after-commit publish、zero EventLog row

- **通过**。`_is_transient_delta_event` 闭集正确覆盖三类 delta；`_ingest_validated` 在最前进入 transient 分支；`_accepted_no_event_result` 返回 `events=()`。
- **通过**。`REASONING_DELTA -> PREVIEW` 旧分支完全删除；三类 delta 的 EventLog row 数严格为 0。
- **通过**。`_finish_ingest` 在 `_with_terminal_promotion_retry` 返回后（即 durable transaction 已提交）才调用 `_publish_transient_delta`。
- **通过**。validation 失败（stale/late/wrong identity/rollback）的 candidate 的 `transient_delta` 均为 `None`，publish 不被调用。

### public typed identity、terminal fence、multi-watcher、overflow/close/detach

- **通过**。`HostTransientDeltaHub.publish` 对同一 candidate 分配一次 `runtime_sequence`，构造一次 immutable envelope，所有 watcher 收到相同 `runtime_id`/`runtime_sequence`/`dedupe_key`。
- **通过**。terminal fence 在 subscription 自身的 `_offer` 中检查（L329），同 Run delta 在 terminal 后入队被拒绝。
- **通过**。fanout 使用 eager `tuple()` snapshot，一个 watcher 的 overflow/detach 不影响其他 watcher。
- **通过**。overflow 后已接受前缀被完整 drain 后才抛 typed `HostApiError(UNAVAILABLE/slow_consumer)`，无 silent-drop。
- **通过**。`close()` 与 `_close_from_hub()` 各有幂等保护和正确职责分离；hub close 通过 snapshot + `_ready.set()` 安全唤醒所有 watcher。

### Host→Service→CLI 只有 public union，无 raw EngineEvent 越层

- **通过**。Service 对 `HostSessionEvent` 做穷举 `isinstance` 分支，`assert_never` 收口。
- **通过**。Service 零处使用 `hasattr`/`getattr`，零处字符串猜类型，零处 optional field 猜 payload。
- **通过**。`grep EngineEvent|dayu\.engine dayu/service/entrypoint_runtime.py dayu/cli/thinking.py`：零命中。
- **通过**。`dayu/host/__init__.py` 已移除 `HostThinkingView` 和 `HostEvent.thinking` export。

### durable/transient 双真源、error 重写、fake terminal、final 重复

- **通过**。durable facts 唯一来源于 committed EventLog row；transient delta 唯一来源于当前 runtime hub。
- **通过**。`HostEvent` 不含 `thinking`/`runtime_id`/`runtime_sequence` 字段；`HostTransientDelta` 不含 `event_id`/`event_sequence`/terminal 字段。
- **通过**。`_WatcherFailure.error` 保留原 `HostApiError` 完整类型，诊断摘要只是安全投影，不重写错误。
- **通过**。Host close 不写 Run cancel/failed terminal fact；terminal 只来自 durable EventLog。
- **通过**。thinking/final answer/activity 三条输出路径语义来源互斥（transient reasoning / durable terminal / durable activity），各用独立 dedupe key，无重复输出。

### lost wakeup、TOCTOU、resource/task leak、cross-run/session leakage、restart/replay 误承诺、unbounded queue

- **通过**。`wait_ready` 使用 clear-recheck 三段式 level-triggered 模式，无丢唤醒窗口。`drain_nowait` 同步执行，drain/clear 与 publish 之间无 `await` 点。
- **通过**。publish 在 durable transaction 提交后执行，不存在 TOCTOU 窗口（transaction 内状态与 publish 时状态一致）。
- **通过**。`HostTransientDeltaSubscription` 和 `HostTransientDeltaHub` 均不创建 asyncio Task（`grep create_task\|ensure_future` 零命中）。
- **通过**。`runtime_id` 是 `uuid.uuid4()`，`runtime_sequence` 从 1 开始，均不持久化（`grep runtime_id.*durable\|runtime_sequence.*EventLog` 零命中）。
- **通过**。plan §3.2 明确非目标"不提供 durable delta replay"、"不提供跨进程 broker"，实现与设计一致。
- **通过**。容量 256 + `put_nowait` overflow 语义确保 publish 路径零 backpressure。

### 测试证明 3×1000、慢/快 watcher、确定性 barrier、DS-F02、lifecycle 和 durable facts

- **通过**。`test_transient_delta_stress.py`：三类 delta 各 1000 条，`observed_counts == expected_counts` 断言正确；terminal durable facts（RUN_SUCCEEDED、final answer）正常。
- **通过**。慢 watcher 258 条 delta（> 256）触发 overflow，保留 256 条前缀后抛 typed `UNAVAILABLE/slow_consumer`；fast watcher 接收全部 258 条。
- **通过**。publish-before-wait、wait-before-publish、drain/clear+publish、overflow/close 四种交错均有覆盖。
- **通过**。`test_transient_slow_consumer_path.py` 走真实 `open_host` + `submit_entrypoint_turn_and_wait` + `render_prompt_terminal_result` 全链路，非 fake 绕过。
- **通过**。terminal fence、attach race、HostClosedError、NOT_FOUND、aclose before iteration、cancel during iteration 均有测试覆盖。

### README/design/plan/control 语义一致

- **通过**。`docs/host/design.md` 已按 plan §11 更新：§4.1 固定 durable/transient 术语、三类 delta owner、envelope 字段、runtime identity/sequence/dedupe、validation-success 后 publish、terminal fence、容量 256 overflow、detach/Host close；§10 固定类型分离，删除 durable thinking projection；§13 固定三类 delta 不进入 EventLog；§16 固定 EventLog/read model/outbox 只拥有 durable member。
- **通过**。`dayu/host/README.md` L248 列出 `HostTransientDelta`/`HostTransientDeltaType`/`HostContentDelta`/`HostReasoningDelta`/`HostToolCallDelta`/`HostSessionEvent` 类型；L86 描述 `watch_session_events` 的新语义。
- **通过**。`dayu/README.md` L100 描述 Service 通过有界 relay 消费 `HostTransientDelta`；L134 描述三类 delta 零 EventLog row，不进入 memory/outbox/audit。
- **通过**。`dayu/service/README.md` L27 描述容量 256 有界 relay、`HostSessionEvent` 联合类型、reasoning delta → EntrypointThinking 投影、content/tool-call 忽略。
- **通过**。plan §4.1 的 frozen contract 与当前生产代码一致；plan §5.2 的 call path 与实现一致。

### 旧 HostThinkingView / reasoning durable path 遗留

- **通过**。`grep HostPreviewEventType.REASONING_DELTA`：零命中。
- **通过**。`grep _EVENT_TYPE_REASONING_DELTA`：零命中。
- **通过**。`grep HostThinkingView`：零命中（仅在 README 中作为历史术语出现，不在代码中）。
- **通过**。`grep thinking=_thinking_from_row`：零命中。
- **通过**。`grep event_sequence.*thinking|EntrypointThinking.*event_sequence`：零命中。

### AGENTS docstring/type/no compatibility/no fallback/README/coverage/pyright 约束

- **通过**。所有新增模块和类有中文概览 docstring；函数/方法 docstring 完整列出参数、返回值、异常。
- **通过**。所有签名使用严格具体类型，无 `Any`、`object`、无参数类型。
- **通过**。无兼容性代码：无 re-export、无 wrapper/facade 透传、无 `hasattr`/`getattr` 作为类型绕过手段（grep 零命中）。
- **通过**。无兼容 shim：旧 `HostThinkingView`、`HostEvent.thinking`、`_thinking_from_row` 全部删除而非保留为可选字段。
- **通过**。受影响 README 已按触发规则更新。
- **通过**。Slice 1 implementation report: `dayu/host/transient_delta.py` coverage 89.36%；Slice 2 report: coverage 90.96%，both ≥ 80% 阈值。
- **通过**。两个 slice 的 validation report 均报告 pyright 0 errors。

### 全 WU 是否达到 draft PR 前 residual risk reconciliation 条件

- **通过**。control doc 当前 residual risk 表中 `WU-CLI-SMOKE-01-R1` 已在 Slice 1 和 Slice 2 的 accepted commits (`70ccda60`, `d58014cf`) 后更新状态。
- **通过**。本 aggregate deepreview 对生产代码 0 个 blocking finding。
- **通过**。测试侧 7 个 findings 均为低严重度、非 blocking、只涉及测试实现细节。

## Open Questions

无。所有权、public API、跨 durable/transient ordering、同-runtime 边界、三类 delta 契约均已由 plan freeze + 两个 accepted slice 收敛。Slice 2 code review 中的 DS/MiMo 全部 finding 已由 controller adjudication 裁决完毕（0 个 accepted current-fix finding）。

## Residual Risk

- `WU-CLI-SMOKE-01-R2`：`CliThinkingRenderer` 当前保留 160 字符单行运行态展示；可展开 thinking panel 已 deferred 给未来 CLI UI enhancement。不阻塞 draft PR。
- 容量 256 是首版内部安全值，缺少真实负载调优数据；未来基于观测另开 WU。不阻塞 draft PR。
- 跨进程/跨 Host instance 多 watcher 不可见；已明确为非目标，不阻塞 draft PR。
- 测试侧 Findings 01–07（本 artifact）：全部低严重度、测试实现细节层面，不影响生产正确性。建议在 draft PR 后 incremental improvement 中处理，不阻塞 draft PR。
- `_FakeHost` 顺序索引状态机（Finding 04）和 `_SlowConsumerHostProbe` cast（Finding 05）属于测试工具 debt，建议在后续 Service 层变更前优先修复以防静默漂移。

## 结论

**PASS。0 blocking finding。**

经过四个并行 subagent 专项 deepreview + controller 静态边界检查 + adversarial failure pass + semantic ownership drift 检查 + overcoupling 检查 + README/design/plan/control 一致性核对：

- 生产代码在所有指定审查维度上正确：三类 delta 统一 owner、transaction after-commit publish、zero EventLog row、public typed identity、terminal fence、multi-watcher、overflow/close/detach、Host→Service→CLI public union only、无 raw EngineEvent 越层、无 durable/transient 双真源、无 error 重写、无 fake terminal、无 final 重复、无 lost wakeup、无 TOCTOU、无 resource/task leak、无 cross-run/session leakage、无 restart/replay 误承诺、无 unbounded queue。
- 测试覆盖充分：3×1000 stress、慢/快 watcher、四类受控交错、DS-F02 E2E 全链路、lifecycle 和 durable facts。
- README/design/plan/control 语义一致，无旧 HostThinkingView / reasoning durable path 遗留。
- AGENTS 约束（docstring、type、no compatibility、no fallback、README、coverage、pyright）全部通过。

**全 WU 已达到 draft PR 前 residual risk reconciliation 条件。** 无需 fix、无需 code re-review、无需新增 supplemental batch。
