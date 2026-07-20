# WU-CLI-SMOKE-01-R1 Slice 2 Implementation（Codex）

## Gate 结论

- 基线：accepted Slice 1 commit `70ccda606a7d256cb1a9ef47f5b84652ed82b810`。
- 范围：仅执行 Slice 2 implementation gate；未重新设计 Slice 1 contract。
- 状态：**PASS / STOP**。
- 生产代码：**无修改**。adversarial barrier、真实跨层 E2E 与全量回归没有证明 production correctness defect，因此没有越过测试/README 边界做补偿性修复。
- 外部动作：未 commit、未 push、未创建 PR、未执行 review、未进入 aggregate gate。
- controller-owned 文件：`docs/host/issues-implementation-control.md` 与 `docs/phaseflow-umbrella-optimization-control.md` 在开始时已存在未提交修改；本 gate 只读，未修改。

## 动机复核

问题真实存在，但性质是 accepted Slice 1 之后的生产级证据缺口，不是已证明的协议设计错误：三类 delta 已迁移到 Host-owned transient live stream，但只有 adversarial lifecycle、慢消费者、放大量和真实 Host→Service→CLI 反压路径才能证明“EventLog 零放大、单 watcher 隔离、terminal durable truth 不受阻、错误不被改写”。若缺少这些证明，常规少量 happy-path 测试无法排除 lost wakeup、lazy attach 丢窗、unbounded relay、terminal 伪造或 cleanup 泄漏。

Slice 2 的严重性评估成立；用户指定的实现路径也与 accepted plan 的语义 owner 一致。没有理由重开 Slice 1 public contract，也没有证据支持引入 broker、replay cursor、兼容 shim 或下游 fallback。

## Semantic owner 判断

| 语义 | 唯一 owner | 本 gate 的处理 |
| --- | --- | --- |
| transient readiness、容量 256、fanout、overflow、terminal fence、detach | `dayu.host.transient_delta` | 用 deterministic barrier、双 watcher和 stress 从 owner/public path 验证；未改生产代码 |
| attach-before-return、durable/transient merge、public typed failure、Host close cleanup | `dayu.host.open_host` | 用真实 `open_host` 生命周期与 SQLite failure injection 验证；未在 Service/CLI 补偿 |
| 有界 live relay、watcher failure 诊断、Outbox terminal fallback、reasoning thinking 投影 | `dayu.service.entrypoint_runtime` | 通过真实容量 256 relay 反压链验证原 `HostApiError` identity 与 fallback |
| thinking 去重、runtime sequence、stderr display、terminal 前 display cleanup | `dayu.cli.thinking` 及 CLI entrypoint adapter | 用真实 mixed stream callback 和既有 prompt/interactive/Ctrl+C suites 验证 |
| Run / Attempt / terminal / final answer / Outbox durable facts | Host EventLog、状态索引及既有 projection owner | stress 与 overflow E2E 只读取并断言，不从 transient 重算或持久化 |

直接证据没有指向上述生产 owner 的 correctness defect。实施期间两类失败均来自测试控制边界：一是可控 worker 未让出 event loop，导致“快 watcher”也无法消费；二是 durable failure 用例错误要求 transient 后的下一项立刻是损坏 terminal，忽略了合法 durable progress prefix。前者在测试 worker 每条 delta 后显式调度让出，后者改为消费合法 prefix 直到 owner 读取损坏 row；两者都没有引入生产 fallback。

## 实现内容与 changed files

### 测试

- `tests/host/transient_stream_support.py`（新增）：集中提供严格 typed 的可控 LocalEngineWorker、三类 mixed delta 计数、真实 `OpenHostOptions`、EventLog row 计数与 Run/Attempt/terminal durable snapshot。测试经 worker public boundary 产出 Engine events，不绕过 Host ingest。
- `tests/host/test_transient_delta_stress.py`（新增）：独立 `stress` marker；真实 `open_host` 路径各发布 content/reasoning/tool-call 1,000 条，fast watcher 精确观察 3,000 条，三类 EventLog row 均为 0，并核对 terminal、final answer、Run、Attempt 与 Outbox identity。
- `tests/host/test_transient_delta.py`：加入 publish-before-wait、wait-before-publish、drain/clear 与 publish 最不利交界、overflow/close wakeup 的 deterministic barriers；继续验证 queue prefix、closed/overflow owner state 和快慢 watcher 隔离。
- `tests/host/test_watch_session_events.py`：加入容量 256 慢 watcher overflow、快 watcher与 terminal/Run 隔离、精确 typed detail、attach 前不 replay/attach 后首 delta、首次与后续 durable failure、首次/后续 iteration cancellation、started/never-started `aclose()`、missing、Host close、closed handle 与 subscription count cleanup；既有双 watcher用例继续证明 terminal 后下一 Run 可观察。
- `tests/cli/test_transient_slow_consumer_path.py`（新增）：真实 Host publisher/subscription → Service bounded relay → CLI renderer。受控阻塞 Service 首次 `get_run`，证明 relay 先满并停在第 257 个 `await queue.put`，随后 Host subscription overflow；恢复后原 `UNAVAILABLE/retryable/HostUnavailableDetail(session_live_stream, slow_consumer)` 可见，Run 保持成功，Outbox 与 terminal/result 同 identity，thinking 与 final 各只展示一次并在 30 秒 timeout 内结束。

### 文档

- `dayu/host/README.md`：记录 durable `HostEvent` / live-only `HostTransientDelta` 分离、`HostSessionEvent` 联合、三类 zero-row、attach/live-only、容量 256、typed slow-consumer、terminal fence 与 detach/close 语义。
- `dayu/README.md`：记录 Host→Service 跨层 union 与 durable/transient source-of-truth 边界；Service 不读取 raw EngineEvent，只把 reasoning delta 投影为 entrypoint thinking。
- `dayu/service/README.md`：记录 `_WatchAndWaitRuntime` 容量 256 relay、`await queue.put` 背压、原 typed watcher failure、Outbox fallback 以及 content/tool-call 不进入 thinking。
- `tests/README.md`：记录 deterministic barrier、lifecycle/overflow、真实 Host→Service→CLI regression 与独立 transient stress 的运行方法和覆盖范围。
- `docs/reviews/wu-cli-smoke-01-r1-slice2-implementation-codex.md`（本文件）：implementation gate 证据与 stop artifact。

未修改：根 `README.md`、`dayu/engine/README.md`、`docs/engine/design.md`、accepted design/plan、Slice 1 artifacts、既有 reviews、两份 controller-owned control docs。

## 测试矩阵证明

### Scale 与 durable zero-row

- 三类 delta 各 1,000，fast watcher 观察值严格等于 `(1000, 1000, 1000)`。
- EventLog 中 `content_delta`、`reasoning_delta`、`tool_call_delta` row 严格分别为 0。
- `RUN_SUCCEEDED`、public terminal、final answer、Run/Attempt terminal 状态、terminal event id/sequence 与 Outbox terminal item 保持同源一致。
- 文件使用 `pytest.mark.stress`；仓库默认 `addopts=-m 'not stress'` 不运行它，只能用显式 stress 命令执行。

### Overflow、ordering 与 lifecycle

- 不消费的 watcher 在精确 256 条连续前缀后以 `HostApiError(code=UNAVAILABLE, retryable=True, detail=HostUnavailableDetail(component="session_live_stream", reason_code="slow_consumer"))` 结束。
- 同一 publish 的快 watcher持续收到全部 258 条 mixed delta 和真实 success terminal；worker cancel reason 为空，Run/Attempt 为 succeeded，三类 delta row 为 0，terminal append 不受慢 watcher 阻塞。
- readiness barrier 覆盖 publish-before-wait、wait-before-publish、drain-last/clear/publish 丢 `set` 的最不利交界，以及 overflow/close wakeup；全部在 timeout 内按 owner state 收口。
- attach 返回前 subscription 已注册；attach 前第一 Run 的 transient 不 replay，attach 后第二 Run 的首个 transient 不丢。
- never-started immediate `aclose()`、started terminal 后 `aclose()`、首次 `__anext__` cancel、transient 后 pending iteration cancel、missing cursor failure、首次及 transient 后 durable read failure、Host close 均把 subscription count 恢复到 attach 前；iterator cleanup 本身不取消 Run、不写伪 terminal。
- 既有双 watcher测试继续证明 terminal 不结束 Session watcher，下一 Run 的不同 terminal identity 仍可观察；focused CLI suites 覆盖 Ctrl+C 显式调用 Host cancel、renderer cleanup 与 terminal 输出去重。

### DS-F02 收口

DS-F02 已通过本 Slice 的真实 mixed stream / thinking callback / terminal / fallback 路径收口：

1. LocalEngineWorker 经真实 Host ingest 发布 content、reasoning、tool-call mixed stream。
2. Host public subscription 交付 `HostSessionEvent`，不生成三类 durable row。
3. Service bounded relay 真实填满并反压 Host iterator；Host slow-consumer error 保留原 typed detail进入 Service watcher failure diagnostic。
4. Service 只把 reasoning delta 交给 `EntrypointThinking` callback，content/tool-call 不触发 thinking/activity/final callback。
5. overflow 后 terminal 由 real Outbox fallback 收口；terminal/outbox/result 使用同一 identity。
6. `CliThinkingRenderer` 输出一次 thinking，terminal renderer 向 stdout 输出一次 final；30 秒 timeout 内结束，无 fake terminal 或重复显示。

## Validation 命令与结果

所有命令均在仓库根目录执行，并先 `source .venv/bin/activate`。

### 定向实施验证

- `pytest tests/host/test_transient_delta.py tests/host/test_watch_session_events.py tests/cli/test_transient_slow_consumer_path.py -q`
  - `21 passed, 3 warnings in 2.16s`。
- `pyright tests/host/transient_stream_support.py tests/host/test_transient_delta.py tests/host/test_transient_delta_stress.py tests/host/test_watch_session_events.py tests/cli/test_transient_slow_consumer_path.py`
  - `0 errors, 0 warnings, 0 informations`。
- 首次全量 `pytest tests/host tests/service tests/cli -q`
  - `1 failed, 2815 passed, 8 skipped, 6 deselected, 3 warnings in 93.56s`。
  - 唯一失败为新增 durable failure 测试把合法 durable progress prefix 误判为“下一项必须立刻抛错”；直接堆栈确认生产 iterator 未泄漏 private error，也未交付伪 terminal。修正测试消费边界后，单例 `1 passed in 0.37s`，随后完整命令通过。
- 最终 lifecycle 定向复核：
  - `pytest tests/host/test_watch_session_events.py::test_watch_never_started_first_cancel_missing_and_host_close_cleanup tests/host/test_watch_session_events.py::test_watch_first_and_subsequent_durable_failures_are_public_and_detach -q`
  - `2 passed in 0.54s`。

### Accepted plan §9 Required validation

- `pytest tests/host/test_transient_delta.py --cov=dayu.host.transient_delta --cov-report=term-missing --cov-fail-under=80 -q`
  - `9 passed in 0.37s`；owner module coverage `91%`（188 statements，17 missing，total 90.96%），超过 80% hard gate。
- `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py tests/host/test_host_activity_event_projection.py tests/host/test_public_event_stream.py tests/host/test_lifecycle_events.py tests/host/test_audit_sink.py tests/host/test_public_host_event.py tests/host/test_package_exports.py tests/host/test_dispatch_scheduler.py -q`
  - `295 passed in 4.33s`。
- `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q`
  - `51 passed, 3 warnings in 1.70s`。
- `pytest tests/cli/test_thinking_renderer.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_runtime_display.py tests/cli/test_transient_slow_consumer_path.py -q`
  - `109 passed, 3 warnings in 3.69s`。
- 最终 `pytest tests/host tests/service tests/cli -q`
  - `2816 passed, 8 skipped, 6 deselected, 3 warnings in 92.85s`。
- `pytest -o addopts="" -m stress tests/host/test_transient_delta_stress.py -q`
  - `1 passed in 0.60s`。
- 最终 `pyright`
  - `0 errors, 0 warnings, 0 informations`。

warnings 均来自 `.venv` 内 `edgar` 的三条既有 deprecation warning，不是本 Slice 代码或测试失败。

### 单文件 coverage 核对

Slice 2 没有修改 production Python 文件，因此不存在新增 production file coverage 缺口。accepted plan 指定的 owner module `dayu/host/transient_delta.py` 已由 focused coverage 独立核对为 **91%**，不是用总体平均值掩盖。三个新增/修改测试文件和测试 support 由最终全量 pytest 与全仓 pyright 覆盖其执行/类型边界。

### 静态一致性与工作树

- `rg -n 'HostPreviewEventType\.REASONING_DELTA|_EVENT_TYPE_REASONING_DELTA|HostThinkingView|thinking=_thinking_from_row' dayu/host tests/host`
  - 零命中（`rg` exit 1，符合预期）。
- `rg -n 'EngineEventType\.(CONTENT_DELTA|REASONING_DELTA|TOOL_CALL_DELTA)' dayu/host/engine_ingest.py`
  - 仅命中统一三类 classification 与 typed projection：244–246、5221–5223、5240、5246、5252；无 reasoning durable append。
- `rg -n 'event_sequence.*thinking|EntrypointThinking.*event_sequence|thinking\.event_sequence' dayu/service dayu/cli tests/service tests/cli`
  - 零命中（`rg` exit 1，符合预期）。
- `rg -n 'EngineEvent|dayu\.engine' dayu/service/entrypoint_runtime.py dayu/cli/thinking.py`
  - 零命中（`rg` exit 1，符合预期）。
- `git diff --check`
  - exit 0，无 whitespace error。
- `git diff --stat`
  - tracked diff 包含四份 README、两个测试文件，以及开始时已存在的两份 controller-owned control doc 修改；新增的三份测试/support 与本 artifact 因 untracked 不出现在该命令 stat 中。
- `git status --short`
  - 本 gate 文件为四份 README、两个既有测试文件、三个新增测试/support 与本 artifact；另有两份 pre-existing controller-owned control doc 修改。本 gate 未写入后两者。

## README decision

- 更新 `dayu/host/README.md`：命中 Host public watch、ingest/live stream 与生命周期边界。
- 更新 `dayu/README.md`：命中 Host→Service 联合事件和 durable/transient 跨层关系。
- 更新 `dayu/service/README.md`：命中 entrypoint relay、watcher failure、thinking/fallback 投影。
- 更新 `tests/README.md`：命中新增测试层级、stress 入口和覆盖说明。
- 不更新根 `README.md`：CLI 参数、`--thinking/--no-thinking`、默认输出通道、Ctrl+C、安装/初始化和最终用户工作流均未变化。
- 不更新 Engine README/design：Engine contract、三类 EngineEvent payload 与 provider 行为未变化；transient fanout/lifecycle 属于 Host owner。

## Propagation audit

- Producer：Engine 三类 delta 仍只通过既有 typed `EngineEvent` 产生；本 Slice 没有修改 Engine。
- Validation/publish owner：Host ingest 的统一 classification/projection 是唯一入口，validation 成功后交给 current-runtime hub；静态 grep 没有第二条 reasoning durable path。
- Persistence：三类 delta 在普通 owner tests 与 3×1,000 stress 中都保持 EventLog 零 row；Run/Attempt/terminal/final/outbox 继续从 canonical Host facts 派生。
- Public projection：`HostEvent` 只承载 durable event；`HostTransientDelta` 只承载 current-runtime delta；`HostSessionEvent` 是 watch union，两个 identity domain 未混用。
- Service：只消费 Host public union，不导入 `EngineEvent` / `dayu.engine`；reasoning 由唯一 helper 投影成 `EntrypointThinking`，content/tool-call 明确忽略。
- CLI：只消费 `EntrypointThinking`，按 runtime sequence/dedupe 去重；不读取 Host/Engine internals。terminal final 继续从 Service terminal result/Outbox 同源 identity 渲染一次。
- Error：Host hub 生成的原 `HostApiError` 通过 Service `_WatcherFailure.error` 保留 code/retryable/detail；Service 只生成诊断并走既有 public Outbox fallback，不吞掉、重分类或伪造 terminal。
- Cleanup：watch iterator 的 never-started/started/cancel/error/Host-close 路径都回到 Host subscription owner detach；CLI Ctrl+C 仍通过显式 Host cancel command，renderer/watch cleanup 不反推 Run cancellation。

未发现 semantic ownership drift、反向依赖、raw EngineEvent 越层、durable/transient 双 owner、兼容 shim、fake-only E2E 或显示正确但 durable facts 错误的传播分叉。

## Residual risk

- transient delta 在 overflow、detach、断线、Host close、崩溃和进程重启后永久丢失；这是已冻结的 live-only contract，不是 durable data loss defect。
- 容量 256 是内部固定安全值，尚无真实生产负载调优数据；本 gate 只证明 boundedness 和隔离，不把它提升为 public knob。
- durable event 与 transient delta 没有跨域总序，只承诺各自内序及同 Run terminal fence。
- E2E 使用可控 LocalEngineWorker 产生确定性 mixed stream，没有调用真实外部 LLM provider；Host publisher/subscription、Service relay/fallback、SQLite durable store/Outbox 和 CLI renderer 均为 production path。这是避免网络/供应商不确定性所需的测试边界。
- 全量测试出现的三条 `edgar` deprecation warning 仍存在，属于外部依赖现状，不影响本 Slice correctness。

## Stop status

Slice 2 implementation gate 已完成并 **PASS**。本 artifact 写入后停止；等待 controller 读取结果并决定后续 gate。不得由本 agent commit、push、开 PR、执行 review 或进入 aggregate gate。
