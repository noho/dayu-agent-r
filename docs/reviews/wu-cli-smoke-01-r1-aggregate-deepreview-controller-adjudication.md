# WU-CLI-SMOKE-01-R1 Aggregate Deepreview Controller Adjudication

## Scope

- Gate: 全 WU aggregate deepreview。
- Base: prerequisite merge commit `bd1d3e94`。
- Accepted commits:
  - plan `929691ea`。
  - Slice 1 `70ccda60`。
  - Slice 2 `d58014cf`。
- Review artifacts:
  - `docs/reviews/wu-cli-smoke-01-r1-aggregate-deepreview-mimo.md`（AgentMiMo，PASS，0 blocking，no fix）。
  - `docs/reviews/wu-cli-smoke-01-r1-aggregate-deepreview-ds.md`（AgentDS，PASS，0 blocking；7 个低严重度测试项）。

## Motivation / Owner Check

本 WU 的根因是三类 per-chunk delta 的实时展示语义被错误地部分寄存在 EventLog；正确 owner 是 Host 当前 runtime 的 typed transient fanout，而 durable terminal、activity、final、Outbox 与恢复仍由 EventLog 拥有。aggregate diff 已把 producer、Host validation/publish、public projection、Service relay、CLI display、durable facts、测试与设计文档统一到这两个互斥 owner。

两路 reviewer 均完成 adversarial failure、项目约束、过度耦合、semantic ownership drift 与 residual risk 检查，未给出生产 correctness、stability、resource leak、TOCTOU、lost wakeup、反向依赖、durable/transient 双真源或 LLM-facing 语义漂移的反例。MiMo 还独立复跑 Host/Service/CLI 全量 suite、owner coverage、pyright 与静态边界检查；结论与 implementation gate 一致。

## Decisions

### MiMo aggregate verdict

- `accepted`。
- 0 blocking finding，0 current-fix finding。三类 delta owner、after-commit publish、zero-row、terminal fence、multi-watcher、bounded queue、Host→Service→CLI public union、cleanup、restart/no-replay 与 README/design 一致性均通过。

### DS Finding 01：subscription count 通过 private Host owner probe

- `rejected-with-reason`。
- subscription count 是 `HostTransientDeltaHub` 的内部生命周期观测，不是上层调用需要的业务事实。把它加入 `Host` public protocol 会把治理实现细节泄漏给 Service/UI 并扩大公共契约，直接违反分层与最小接口原则。
- public behavior 已由 overflow、detach、close、Run/terminal 不变性覆盖；private probe 只在 owner-level lifecycle test 中精确证明资源回收，并用 `_PublicHostHandle` 类型 guard fail closed，边界合理。

### DS Finding 02：Service 单元测试导入 private runtime helpers

- `rejected-with-reason`。
- `_WatchAndWaitRuntime`、relay factory、drain 与 close helper 正是 Service relay/cleanup 的实现 owner；owner-level unit test 直接断言容量、原异常 identity 与 task cleanup 是必要的白盒测试。跨层 E2E 另行证明 public behavior，两者不是重复真源。
- 删除这些测试只保留 E2E 会降低错误定位能力，且无法精确证明 close helper 的 cancellation/exception 分支。

### DS Finding 03：deterministic barrier 替换 private `_ready`

- `rejected-with-reason`。
- 该项与 Slice 2 review 已裁决项相同。subscription 使用 `__slots__`；字段删除/重命名会在赋值时直接失败，readiness 实现不再消费该 Event 时 barrier 会 timeout，不会静默通过。
- lost-wakeup 的 owner 线性化点就在 `_ready` clear/set 与 owner-state recheck，白盒可控 Event 是比 sleep 更严格的测试 seam；无需把 private primitive 提升为 production docstring 公共承诺。

### DS Finding 04：既有 `_FakeHost` 顺序索引

- `rejected-with-reason`（out of current change and no demonstrated failure）。
- aggregate diff 只把 `_FakeHost` 的事件类型从 `HostEvent` 扩展为 `HostSessionEvent`；`_run_status_index`、`_outbox_index` 与 `_session_snapshot_index` 的状态推进机制来自基线，review 未提供本 WU 修改导致静默通过的反例。
- 增加全局 strict 模式会改变大量既有 Service 测试语义，必须由独立、直接失败证据驱动，不能作为当前 transient WU 的顺带 cleanup。

### DS Finding 05：`cast(Host, probe)`

- `rejected-with-reason`。
- 该项与 Slice 2 review 已裁决项相同。当前执行路径所需四个方法全部显式实现并透明转发到真实 Host；未来调用面扩大时运行时显式失败是测试应提供的 contract-change signal。
- 建议的 `__getattr__` 泛化委托违反本仓库禁止用动态属性逃避类型与边界设计的约束；补齐约十五个未使用方法则制造测试 God facade。当前窄 probe 更小且更严格。

### DS Finding 06：close 与 publish 并发测试

- `rejected-with-reason`。
- hub `publish()`、subscription `close()` 与 hub close 的状态迁移都是同一 event loop 内无 `await` 的同步方法，不存在 reviewer 假设的函数内部协程交错。`asyncio.gather` 只能把两个调用整段串行化，不能增加新的可达 schedule。
- 现有 wait-entered→close wakeup、publish-before/wait-before、drain-clear-publish 与 overflow/close owner-state barrier 已覆盖真实可达交界。

### DS Finding 07：直接 SQLite payload corruption

- `rejected-with-reason`。
- 测试目标是 EventLog row payload 在读取时损坏后的 public error mapping 与 detach；通过正常 append writer 无法构造该输入，直接 SQL 注入是 owner read-path 的必要 failure seam，并限定在 `tmp_path` 且恢复原 payload。
- 截断整个 SQLite 文件属于不同的 storage-open/page-corruption failure domain，会破坏数据库级别而非精确命中 row codec，并增加不可恢复与平台差异风险，不能替代当前测试。

## Aggregate Evidence Accepted

- 三类 delta 统一走 Host transient classification/projection，transaction commit 后 publish，EventLog row 为 0。
- typed runtime identity 与 durable EventLog identity 字段互斥；terminal fence 同时在 offer 与 drain 生效。
- watcher queue 与 Service relay 均有界为 256；慢 watcher错误为原 typed `UNAVAILABLE/retryable/slow_consumer`，不取消 Run、不阻塞快 watcher或 terminal append。
- Service/CLI 不导入 raw EngineEvent；reasoning 只投影为 `EntrypointThinking`，content/tool-call 当前显式忽略，final 只来自 durable terminal/Outbox。
- lifecycle、deterministic readiness、3×1000 stress、真实 Host→Service→CLI E2E、zero-row 与 durable facts 均有测试证据。
- `dayu/host/transient_delta.py` coverage 90.96%；最终 Host/Service/CLI suite 2816 passed / 8 skipped / 6 deselected；pyright 0 errors；静态边界 grep 与 `git diff --check` pass。

## Residual Risk Reconciliation

- accepted live-only boundary：overflow、detach、断线、Host close、崩溃与进程重启后不恢复 transient delta。
- accepted internal bound：容量 256 暂无真实负载调优数据，但不暴露为 public knob。
- accepted ordering boundary：durable 与 transient 不承诺跨域可重放总序，只承诺各自内序与同 Run terminal fence。
- accepted test boundary：外部 LLM provider 由可控 worker 替代；其后的 Host、Service、SQLite/Outbox 与 CLI 均为生产路径。
- `WU-CLI-SMOKE-01-R2` 继续独立拥有可展开 thinking panel UI enhancement。

以上均已有明确 owner 或属于冻结 non-goal；无新增未归属 residual risk。主 control doc 中本 WU 的陈旧 active residual row 与 work-unit 状态由 controller 在本 gate 同步收口，不构成实现 fix。

## Decision

`accepted-aggregate-deepreview`。两路均 PASS，0 blocking finding，0 accepted current-fix finding；无需 aggregate fix / re-review，也无需新增 supplemental finding-fix batch。下一步创建 accepted aggregate commit，然后进入 draft PR gate。
