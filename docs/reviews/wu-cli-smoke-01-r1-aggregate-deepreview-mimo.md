# WU-CLI-SMOKE-01-R1 Aggregate Deepreview — AgentMiMo

## Scope

- Mode: current changes（aggregate deepreview）
- Branch: `phaseflow/wu-cli-smoke-01-r1`
- Base: `bd1d3e94`（PR #179 merge commit）
- Output file: `docs/reviews/wu-cli-smoke-01-r1-aggregate-deepreview-mimo.md`
- Included scope: 3 commits（`929691ea` plan, `70ccda60` Slice 1, `d58014cf` Slice 2）+ 未暂存 control doc 更新；覆盖 plan artifacts、Slice 1 生产 contract、Slice 2 测试/README、全部 review/fix/adjudication artifacts
- Excluded scope: `docs/host/issues-implementation-control.md` 的 aggregate 状态更新为 controller 只读，本次 review 不修改
- Parallel review coverage: 4 个 subagent 并行读取 transient_delta.py/engine_ingest.py/open_host.py、测试文件、Service/CLI 代码、review artifacts 与 git diff；主 reviewer 整合、去重并裁决

## 审查维度覆盖

本次 aggregate deepreview 覆盖以下维度：

1. **Adversarial failure pass**：lost wakeup、TOCTOU、resource/task leak、cross-run/session leakage、restart/replay 误承诺、unbounded queue
2. **项目指令检查**：AGENTS docstring/type/no compatibility/no fallback/README/coverage/pyright 约束
3. **过度耦合检查**：Host→Service→CLI 是否只有 public union、是否有 raw EngineEvent 越层
4. **Semantic ownership drift 检查**：三类 delta 的唯一 owner、durable/transient 双真源、error 重写、fake terminal
5. **验证充分性**：测试是否真正证明 3×1000、慢/快 watcher、确定性 barrier、DS-F02、lifecycle 和 durable facts
6. **文档一致性**：README/design/plan/control 语义是否一致，是否遗留旧 HostThinkingView / reasoning durable path

## Findings

### 未发现实质性问题

经过对全部生产代码、测试代码、plan artifacts、review/adjudication artifacts 和 README/design 文档的逐行走读与 adversarial 验证，未发现实质性 correctness、stability、architecture 或 semantic ownership defect。

以下是按维度的详细 evidence-based 结论：

---

## 三类 Delta 的唯一 Owner 验证

**PASS**。三类 delta（`CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA`）在 `engine_ingest.py:_ingest_validated` 中统一由同一 `_is_transient_delta_event` 判断，走同一 `_accepted_no_event_result(_validated_transient_delta_candidate(context, event))` 路径，返回 `events=()`。`_finish_ingest` 在 transaction 成功返回后通过 `_publish_transient_delta` 调用 hub publish。EventLog row 数严格为 0。

- 直接证据：`engine_ingest.py:1041-1042`（ingest 路径）、`engine_ingest.py:871-875`（post-transaction publish）、`engine_ingest.py:7019-7036`（`_accepted_no_event_result` 构造 `events=()`）
- 静态验证：`rg 'EngineEventType\.(CONTENT_DELTA|REASONING_DELTA|TOOL_CALL_DELTA)' dayu/host/engine_ingest.py` 只命中统一 classification/projection，无 reasoning durable append 残留

## Transaction After-Commit Publish 验证

**PASS**。publish 发生在 `_finish_ingest` 中，该方法在 `_ingest_before_reactive_compaction` 的 `run_write` transaction 成功返回后被调用（`engine_ingest.py:794/816`）。transaction rollback/exception 没有 result，因此没有 publish。publisher 异常被 `_publish_transient_delta` 捕获并转为 sanitized operator diagnostic，不改变 accepted result。

- 直接证据：`engine_ingest.py:852-875`（`_finish_ingest` 流程）、`engine_ingest.py:5276-5300`（`_publish_transient_delta` 异常隔离）

## Zero EventLog Row 验证

**PASS**。`_accepted_no_event_result` 构造 `EngineIngestResult(status=ACCEPTED, events=(), ...)`。三类 delta 都不调用 EventLog append。`_is_transient_delta_event` 在 `_ingest_validated` 入口处拦截，不进入后续 durable mapping 分支。

- 测试证据：`test_engine_ingest_mapping.py` 对三类 valid delta 断言 `ACCEPTED`、`events == ()`、publisher once；validation/late/rollback 为 publisher 0
- Stress 证据：`test_transient_delta_stress.py` 每类 1,000 delta 后 EventLog 三类 row 严格为 0

## Public Typed Identity 验证

**PASS**。`HostTransientDelta` 是 frozen dataclass，携带 `runtime_id`、`runtime_sequence`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`worker_event_index`、`observed_at`、`type`、`data`、`dedupe_key`。`__post_init__` 严格校验类型、非空、正整数、UTC 时间与 discriminator/data 一一对应。`HOST_TRANSIENT_DELTA_TYPE_TO_DATA` 使用 `MappingProxyType` 固化映射。

- 直接证据：`api.py` 中 `HostTransientDelta` 定义、`HostTransientDeltaType` enum、`HostContentDelta`/`HostReasoningDelta`/`HostToolCallDelta` payload dataclass
- 不含 `event_id`、`event_sequence`、`event_class`、terminal/activity/thinking 可选字段

## Terminal Fence 验证

**PASS**。`HostTransientDeltaSubscription` 维护 `_terminal_run_ids: set[str]`。`_watch_session_events_after` 在 yield durable terminal 前调用 `subscription.mark_run_terminal(event.run_id)`。`_offer` 和 `drain_nowait` 都检查 `event.run_id in self._terminal_run_ids`，拒绝已终态 Run 的后续 delta。

- 直接证据：`transient_delta.py:296-305`（`mark_run_terminal`）、`transient_delta.py:329`（`_offer` fence check）、`transient_delta.py:255`（`drain_nowait` fence check）、`open_host.py:1019`（terminal yield 前 mark）
- 测试证据：`test_watch_session_events.py` 覆盖 terminal fence、delta 与同 Run terminal 紧邻时的交付顺序

## Multi-Watcher 验证

**PASS**。hub 对 Session 索引的 subscription snapshot 顺序 offer，同一 `HostTransientDelta` 实例 fanout 到所有已 attach watcher。一个 watcher 的 cancel 或 overflow 不修改其它 watcher。

- 直接证据：`transient_delta.py:444-464`（`publish` 对 snapshot 顺序 offer）、`transient_delta.py:329-336`（overflow 只 detach 当前 subscription）
- 测试证据：`test_transient_delta.py` 覆盖多 watcher fanout、detach 隔离；`test_watch_session_events.py` 覆盖 attach race、双域顺序

## Overflow/Close/Detach 验证

**PASS**。容量 256 的 bounded queue 满时 `_offer` 将 subscription 标记为 overflowed 并 detach。iterator 在消费完已接受连续前缀后抛 `HostApiError(UNAVAILABLE, retryable=True, detail=HostUnavailableDetail(component="session_live_stream", reason_code="slow_consumer"))`。Host close 调用 `hub.close()` 唤醒全部 watcher，不取消 Run、不伪造 terminal。显式 `aclose()` 或迭代取消只 detach subscription。

- 直接证据：`transient_delta.py:331-336`（overflow）、`transient_delta.py:96-111`（`_slow_consumer_error`）、`transient_delta.py:477-494`（hub close）、`open_host.py:1046`（handle close 调 hub.close）
- 测试证据：`test_transient_delta.py` 覆盖 overflow、close、detach；`test_transient_delta_stress.py` 覆盖 3×1000 stress；`test_transient_slow_consumer_path.py` 覆盖真实 Host→Service→CLI 慢消费者链

## Host→Service→CLI Public Union 验证

**PASS**。`watch_session_events` 返回 `AsyncIterator[HostSessionEvent]`，其中 `HostSessionEvent = HostEvent | HostTransientDelta`。Service 对 union 做穷举 `isinstance` 分支：`HostEvent` 驱动 activity/terminal/final；`HostTransientDelta` 只把 `HostReasoningDelta` 投影为 `EntrypointThinking`，`HostContentDelta` 和 `HostToolCallDelta` 明确忽略（`assert_never` 兜底）。

- 直接证据：`entrypoint_runtime.py:1189-1212`（`_drain_available_watcher_items` 穷举分支）、`entrypoint_runtime.py:1268-1297`（`_emit_entrypoint_thinking_from_transient_delta`）
- 静态验证：`rg 'EngineEvent|dayu\.engine' dayu/service/entrypoint_runtime.py dayu/cli/thinking.py` 为零命中

## Raw EngineEvent 越层检查

**PASS**。Service 和 CLI 不 import `EngineEvent` 或 `dayu.engine`。Service 只消费 `HostSessionEvent` union。CLI 只消费 `EntrypointThinking` DTO。

- 静态验证：grep 零命中

## Durable/Transient 双真源检查

**PASS**。`HostEvent.event_sequence` 只属于 EventLog，`HostTransientDelta.runtime_sequence` 只属于当前 runtime。两者类型和字段不可互换。`HostEvent` 不含 `runtime_id`/`runtime_sequence`；`HostTransientDelta` 不含 `event_id`/`event_sequence`/`event_class`。

- 直接证据：`api.py` 中两个 dataclass 定义的字段集完全分离
- 静态验证：`rg 'HostThinkingView' dayu/ tests/` 为零命中；`rg 'event_sequence.*thinking' dayu/service dayu/cli tests/service tests/cli` 为零命中

## Error 重写检查

**PASS**。`_WatcherFailure.error` 保存原 `HostApiError` 实例。Service relay 满时 `_drain_host_events` 停在 `await queue.put`，Host subscription overflow 后 iterator 抛原 typed error，`_drain_host_events` 捕获并通过 `_WatcherFailure(error=exc)` 传入 queue。Service 不改写为 generic exception。

- 直接证据：`entrypoint_runtime.py:1053-1054`（`_WatcherFailure(error=exc)`）、`transient_delta.py:96-111`（错误构造）

## Fake Terminal 检查

**PASS**。terminal 只来自 durable `HostEvent`。Host close 只唤醒 watcher 并正常结束，不写 `RUN_CANCELLED`、`RUN_FAILED` 或其它 terminal。watcher detach/overflow 不取消 Run。

- 直接证据：`open_host.py:1022-1050`（close 流程不写 terminal）、`transient_delta.py:307-319`（subscription close 不写 terminal）

## Final 重复检查

**PASS**。final answer 只来自 durable terminal 写 stdout。thinking 只写 stderr。CLI renderer 用 `(runtime_id, runtime_sequence)` 检查单调性并用 `dedupe_key` 等值去重。

- 直接证据：`cli/thinking.py:99-105`（runtime 切换重置 + sequence 单调性 + dedupe_key 去重）

## Lost Wakeup 检查

**PASS**。subscription readiness 使用 level-triggered `asyncio.Event`：queue 非空、overflow 或 closed 时 `_is_ready()` 返回 `True`。`_refresh_readiness()` 在 clear 前后 recheck。`_offer` 在 `put_nowait`/overflow 后 `set()`。`wait_ready` 在 clear 后立即 recheck。

- 直接证据：`transient_delta.py:351-372`（`_is_ready`、`_refresh_readiness`）、`transient_delta.py:273-283`（`wait_ready` clear-recheck）、`transient_delta.py:336`（`_offer` set）
- 测试证据：`test_transient_delta.py` 用 deterministic barrier 覆盖 publish-before-wait、wait-before-publish、drain/clear 与 publish 交界、overflow/close 四类交错

## TOCTOU 检查

**PASS**。`_watch_session_events_after` 的 terminal 分支在 `drain_nowait()` 返回后到 `mark_run_terminal()` 之间没有 `await`；同一 event loop 的 publisher 不能在该同步区间插入。即使外部并发 offer，下一轮 drain 的 fence check 仍会拒绝已终态 Run 的 delta。

- 直接证据：`open_host.py:1010-1020`（terminal 分支同步执行）

## Resource/Task Leak 检查

**PASS**。`_ClosableHostSessionEventIterator` 的 `aclose()` 幂等关闭 subscription 和 generator。never-started `aclose()` 直接关闭 subscription。cursor future 通过 `add_done_callback(_observe_watch_cursor_future)` 吞噬异常。hub 无 per-watcher task。Service `_WatchAndWaitRuntime` 的 drain task 在 `_close_watch_and_wait_runtime` 中 cancel 并 await。

- 直接证据：`open_host.py:1269-1283`（iterator aclose）、`open_host.py:1187-1191`（cursor future callback）、`entrypoint_runtime.py:1057-1076`（runtime close）
- 测试证据：`test_watch_session_events.py` 覆盖 started/never-started aclose、cursor failure、cancel

## Cross-Run/Session Leakage 检查

**PASS**。subscription 按 `session_id` 索引。terminal fence 按 `run_id` 隔离。不同 Session 的 watcher 不共享 subscription。同一 Session 的多个 watcher 各自维护独立 `_terminal_run_ids`。

- 直接证据：`transient_delta.py:402`（Session 索引）、`transient_delta.py:218`（per-subscription terminal set）

## Restart/Replay 误承诺检查

**PASS**。`runtime_id` 是每次 `open_host` 新建的 UUID。`runtime_sequence` 从 1 开始单调。hub 不持久化。watcher 只观察 attach 后的增量。durable cursor 从 attach 时的 EventLog 序号向后轮询。不提供 offline replay。

- 直接证据：`transient_delta.py:400`（UUID 创建）、`open_host.py:980`（cursor 从 attach 点开始）

## Unbounded Queue 检查

**PASS**。subscription queue 容量 256（`_TRANSIENT_WATCH_BUFFER_CAPACITY`）。Service relay queue 容量 256（`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`）。两者都使用 `asyncio.Queue(maxsize=...)`。

- 直接证据：`transient_delta.py:26`（Hub 常量）、`entrypoint_runtime.py:75`（Service 常量）、`entrypoint_runtime.py:1027`（queue 构造）

## AGENTS 约束检查

### Docstring/Type 检查

**PASS**。所有新增/修改模块和类提供中文概览 docstring。函数/方法 docstring 完整列出参数、返回值和异常。签名使用严格具体类型，不引入 `Any`、`object`、无参数类型。

- 直接证据：逐文件走读 `transient_delta.py`、`engine_ingest.py`、`open_host.py`、`api.py`、`entrypoint_runtime.py`、`thinking.py` 的 docstring 与签名

### No Compatibility/No Fallback 检查

**PASS**。`HostThinkingView` 已完全删除。`HostEvent.thinking` 已删除。`read_api._thinking_from_row` 已删除。`HostPreviewEventType.REASONING_DELTA` 已删除。不保留旧 import path、旧 DTO re-export、兼容 wrapper、`getattr`/`hasattr` fallback 或 optional field。

- 静态验证：`rg 'HostThinkingView|_thinking_from_row|HostPreviewEventType\.REASONING_DELTA' dayu/ tests/` 为零命中

### README 触发检查

**PASS**。四份 README 已按触发规则更新：
- `dayu/README.md`：Host→Service 公共 union 变化 → 已更新
- `dayu/host/README.md`：Host public watch、ingest mapping 与 lifecycle 变化 → 已更新
- `dayu/service/README.md`：Service 对 transient delta 的消费方式变化 → 已更新
- `tests/README.md`：新增 Host transient owner/concurrency/CLI 路径测试 → 已更新
- 根 `README.md`：CLI 命令、参数、默认输出通道不变 → 未更新（正确）
- Engine README/design：Engine contract 不变 → 未更新（正确）

### Coverage 检查

**PASS**。`dayu/host/transient_delta.py` 覆盖率 90.96%（>= 80%）。missing lines 主要是验证错误分支（type/value error raises）和边界条件。

### Pyright 检查

**PASS**。`pyright dayu/ tests/ utils/` 报告 `0 errors, 0 warnings, 0 informations`。

## 测试充分性验证

### 3×1000 Stress

**PASS**。`test_transient_delta_stress.py` 对三类 delta 各产生 1,000 个，断言 EventLog row 为 0，terminal final answer 与 durable facts 正常。使用独立 `stress` marker，默认 pytest 排除。

- 直接证据：测试通过（`1 passed`），独立于默认 suite

### 慢/快 Watcher

**PASS**。`test_transient_slow_consumer_path.py` 走真实 Host publisher/subscription → Service `_WatchAndWaitRuntime.queue` → CLI thinking renderer。Service relay 先满并阻塞 `await queue.put`，Host subscription overflow。快 watcher 继续接收完整 mixed stream。恢复消费后保留 typed `UNAVAILABLE/slow_consumer`。terminal/outbox 同 identity 只展示一次。

### 确定性 Barrier

**PASS**。`test_transient_delta.py` 用可控 barrier 在 publish-before-wait、wait-before-publish、drain/clear 与 publish 交界、overflow/close 四类交错下证明无丢唤醒。

### DS-F02（Service prompt/interactive 集成测试注入 transient）

**PASS**。已由 Slice 2 的真实 Host→Service→CLI mixed stream、typed watcher failure、Outbox fallback、thinking/final 单次显示闭环关闭。controller 裁决 `accepted-slice2-review`。

### Lifecycle 测试

**PASS**。`test_watch_session_events.py` 覆盖 attach race、多 watcher、双域顺序、terminal fence、watcher 继续、overflow 隔离、同步 `HostClosedError`、首次 `__anext__` missing/durable typed failure、failure/cancel/started 与 never-started `aclose()` cleanup。

### Durable Facts 测试

**PASS**。`test_transient_delta_stress.py` 证明 3×1000 delta 后 `RUN_SUCCEEDED`/final answer 等 durable row、terminal projection 和 outbox intent 按既有 contract 正常。

## 过度耦合检查

**PASS**。Host→Service→CLI 只通过 `HostSessionEvent` public union 连接。Service 不 import `dayu.engine`。CLI 不 import `dayu.host`。`transient_delta.py` 不放入 `dayu.runtime`（按 plan 设计决策，因为 fanout 必须理解 Host Session/Run/Attempt/execution/terminal fence）。hub 作为 `HostTransientDeltaPublisher` Protocol 端口注入 scheduler/ingestor，测试可用 recording/no-op fixture 替代。

## Semantic Ownership Drift 检查

**PASS**。三类 delta 的语义 owner 清晰：

| 语义 | Owner |
|---|---|
| Engine chunk 与生成器内顺序 | Engine event contract |
| Session/Run/Attempt/execution/dispatch/late-state 接受资格 | Host ingest |
| runtime identity、publication sequence、dedupe、watcher fanout、overflow/detach/close | HostTransientDeltaHub |
| durable facts、terminal identity、offline cursor | EventLog 与 durable HostEvent projection |
| 三类 delta 的公共 envelope/payload | dayu.host.api |
| CLI 是否展示 thinking | Service typed projection 与 CLI renderer |

无 downstream fallback、`hasattr/getattr`、loose parsing、兼容 shim 或测试固化补齐上游 contract 的证据。

## 控制文档一致性

**PASS**。control doc 的当前状态表（gate、active work unit、artifacts、commits、review adjudications）与实际 git history 和 review artifacts 一致。residual risk 表中 `WU-CLI-SMOKE-01-R1` 条目描述的 bug 证据、三类 delta owner 裁决与非目标均与 plan 和实现一致。

## 设计真源一致性

**PASS**。`docs/host/design.md` 已更新：
- §4.1 固定 `HostTransientDelta`、`HostSessionEvent` 术语
- §10 固定 `HostEvent` 删除 `thinking` 字段
- §13 固定三类 delta 均不进入 EventLog
- §16 固定 EventLog/read model/outbox 只拥有 durable member

无遗留旧 `HostThinkingView` / reasoning durable path 描述。

## Open Questions

无。

## Residual Risk

- transient delta 在 overflow、detach、断线、Host close、崩溃或进程重启后不可恢复。这是已接受的 live-only contract，不是数据完整性缺陷。
- 容量 256 是首版内部安全值，缺少真实负载调优数据。未来只能基于观测另开 WU，不在本次暴露 public knob。
- durable progress 与 transient delta 没有可重放总序；只承诺各自内序与同 Run terminal fence。
- E2E 测试不访问真实外部 LLM provider；可控 worker 是测试输入边界，其后的 Host、Service、SQLite/Outbox 与 CLI 路径均为生产实现。

以上均为 accepted plan 已记录边界，无新增未归属 residual risk。

## 结论

**PASS**。0 blocking finding。无需 fix。全 WU 已达到 draft PR 前 residual risk reconciliation 条件。
