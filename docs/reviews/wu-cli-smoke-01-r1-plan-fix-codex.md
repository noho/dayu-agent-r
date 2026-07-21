# WU-CLI-SMOKE-01-R1 Plan Fix — AgentCodex

## Gate 结果

- Work unit：`WU-CLI-SMOKE-01-R1 Engine Delta Transient Live Stream Remediation`
- Gate：`plan-fix`
- 执行者：AgentCodex
- 日期：2026-07-20
- Controller decision source：`docs/reviews/wu-cli-smoke-01-r1-plan-review-controller-adjudication.md`
- Status：`completed`
- 下一步：只允许 controller 派发原 AgentMiMo / AgentDS re-review；本 gate 不进入 re-review、implementation、commit、push 或 PR。

## 第一性原理判断

accepted findings 的动机成立，且严重性没有被高估：

1. 当前代码确实把 `REASONING_DELTA` 单独写为 durable `PREVIEW`，而 content/tool-call delta 不写 row；这使 live 可见性错误拥有 durable owner。
2. 当前 public watch 在同步调用时只完成 lifecycle gate 与 cursor future submit，Session missing/durable failure在首次 `__anext__` await future 时出现；未来 attach-before-return subscription 若仍只依赖 async generator body 的 `finally`，never-started iterator 会泄漏 subscription。因此错误 timing 与 cleanup 必须在 Host public iterator owner 冻结。
3. Service 当前四个 `asyncio.Queue()` 创建点语义不同：三个实际承接 watcher live items，一个是已终态、无 watcher 的 Outbox fallback queue。机械全部 bounded 会误伤 terminal-only path，只改一个调用点又会产生多处 capacity owner；应由单一 `_WatchAndWaitRuntime` factory 按 watcher 语义收口。
4. Host subscription 若用 edge-trigger Event 驱动 bounded Queue，drain/clear 与 publish 交界可能丢 wakeup；Service relay 若不验证完整 backpressure 链，也可能丢 error 或在 terminal/outbox fallback 上死锁。这两项属于当前正确性 acceptance，不是 closeout 才处理的观测性优化。

正确修复边界仍是：Engine 只拥有 typed chunk 与单生成器内顺序；Host ingest/runtime 拥有 validation、transient identity、fanout、overflow 与 lifecycle；EventLog 只拥有 durable fact/cursor；Service/CLI 只消费 Host public union。没有采用独立 accepted migration slices、Service fallback、raw EngineEvent 旁路或兼容 shim。

## Accepted findings 逐项映射

### A / AgentMiMo F-01 / AgentDS F-01：Slice 1 内部迁移顺序

状态：`已修复`

Plan 修改：

- 在原 Slice 1 内增加 S1-A / S1-B / S1-C 三个 implementation sub-step：
  - S1-A：Host public contract、hub、publisher/subscription、composition、watcher union 与 cursor cleanup；
  - S1-B：Service/CLI transient reasoning identity、union 穷举与唯一 bounded relay；
  - S1-C：删除 reasoning durable row、`HostEvent.thinking`、projection/export，完成三类 zero-row。
- 每个 sub-step 都写明实施动作、handoff invariant 与逐步验证点。
- 明确三步只属于同一次 implementation / review boundary；任何中间状态都不得 accepted commit、交付或部署。S1-A/S1-B 中可能暂存的 durable/transient reasoning 双路径仅是未接受 worktree 迁移状态，不得增加 consumer、feature flag、fallback 或 compatibility branch；只有 S1-C 完成后才允许进入 Slice 1 code review。

### B / AgentDS F-02：Service bounded relay 唯一 owner 与传播链

状态：`已修复`

Plan 修改：

- 冻结 `_WatchAndWaitRuntime` 及其 factory 为 Service live relay capacity 的唯一 owner；只对实际承接 `HostSessionEvent | _WatcherFailure` 的 queue 使用 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY = 256`。
- submit、非终态 cancel、startup reconnect 的 watcher relay 必须复用该 factory；已终态/无 watcher/一次性 Outbox drain queue 不机械修改。
- 写清完整链：Service `await queue.put` 阻塞 → 停止 Host iterator `__anext__` → Host merge iterator 暂停 → Host subscription bounded queue 被 hub `put_nowait` 填满 → subscription owner detach/overflow → iterator 在连续前缀后抛 typed `UNAVAILABLE/slow_consumer` → `_WatcherFailure` 保存原 `HostApiError` → typed diagnostic / Outbox terminal fallback 收口。
- 禁止 Service `put_nowait`、QueueFull 丢弃、替换 item、旁路槽、generic exception 改写或只记日志后继续。
- 增加 owner-level propagation assertions 与真实 Host → Service → CLI 慢消费者 integration acceptance；断言 terminal/outbox identity 不丢、Run 不 cancel/fail、final 一次且 timeout 内无死锁。

### C / AgentMiMo F-02：attach cursor public failure 与 cleanup

状态：`已修复`

Plan 与设计真源修改：

- 同步 `watch_session_events` 先执行 lifecycle gate；closed handle 当场抛 `HostClosedError`，不注册 subscription。
- 打开 handle 在返回 iterator 前注册 subscription 并 submit durable cursor future；首次 `__anext__` await future。
- missing/purged Session 固定为 `HostApiError(NOT_FOUND, retryable=False)`；其它 durable read failure沿 `HostCommandHandle._run_read` 既有 mapping 保持 public `HostApiError`，不泄漏 `HostDurableError`、actor future/private operation exception。
- Host 内部 closable iterator共同拥有 cursor future 与 subscription；同步 attach 中途失败、cursor failure、首次/后续 `__anext__` cancel、iterator error、started `aclose()`、never-started immediate `aclose()` 都幂等 detach，并观察/收口 cursor future。
- 测试矩阵逐项冻结上述 error timing、code/retryable、subscription count、pending task 与 unhandled-future warning。

### D / Controller residual-risk decision：当前 Slice 2 adversarial acceptance

状态：`已修复`

Plan 修改：

- Event/Queue readiness 明确为 level-triggered owner state；Slice 2 用 deterministic barrier 覆盖 publish-before-wait、wait-before-publish、drain-last-item/clear 与 publish 交界、overflow/close wakeup。
- 新增 `tests/cli/test_transient_slow_consumer_path.py` 计划项，在 Slice 2 当前 acceptance 走真实 Host publisher/subscription → Service bounded relay → CLI renderer 链。
- 明确两项不得等到 aggregate deepreview 或 closeout 才首次验证，也不得用 fake-only 分层测试替代端到端 slow-consumer chain。

### E / 必须保留的既有 contract 与非目标

状态：`已保留`

- 两个 sequence/semantic owner 不变：Host runtime 的 `runtime_id/runtime_sequence` 与 EventLog 的 `event_id/event_sequence` 不可互换。
- `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA` 最终都为 transient，三类 durable EventLog row 严格为 0。
- 同一 `open_host` runtime 多 watcher 收到相同 immutable envelope identity；单 watcher overflow/detach 不影响其它 watcher。
- 跨进程、Host restart、reconnect replay、统一 durable/transient cursor、public capacity tuning、delta 截断仍是非目标；没有扩展 Engine、`dayu.runtime`、broker、schema migration 或兼容读取。

## 直接代码证据

- `dayu/host/engine_ingest.py:1022`–`1028`：reasoning 当前单独 `_append_preview_event`，content/tool-call 经 `_is_transient_delta_event` 返回 no-event；`5261`–`5275` 证明 transient closed set 当前缺 reasoning。
- `dayu/host/dispatch.py:3922`、`4035`–`4044`：同一 execution 的 `worker_event_index` 顺序递增，并逐个 await `ingest_async`，可作为 Host publication source order。
- `dayu/host/open_host.py:895`–`924`：同步 lifecycle gate 后 submit cursor future，首次 `__anext__` 才 await；`1127`–`1140` 只观察未开始 future 异常，当前没有 transient subscription cleanup owner。
- `dayu/host/read_api.py:182`–`194`、`454`–`468`：cursor read 由 Host read owner 校验 Session 并读取最新 EventLog sequence；missing 由 public `HostApiError` 表达。
- `dayu/host/command.py:313`–`324`、`1247`–`1288`：durable read failure 统一映射为 public `HostApiError`；busy/retry-exhausted 与通用 durable failure 已有稳定 code/retryable 规则。
- `dayu/service/entrypoint_runtime.py:646`–`720`、`769`–`771`：实际存在多个无界 queue；`707` 是已终态、无 watcher queue，不能与 live relay 机械同改。
- `dayu/service/entrypoint_runtime.py:967`–`997`：watcher drain 当前使用 `await queue.put`，异常由 `_WatcherFailure` 保存；`1101`–`1131` 是 typed failure 的现有消费/diagnostic boundary。
- `dayu/cli/thinking.py:53`、`83`、`95`–`103`：CLI 当前用 durable `event_sequence` 排序去重，必须迁移到 runtime identity。
- `docs/host/design.md` 的 Stream/P10.5 public contract 已确认 Host transient hub 与 EventLog 的双 owner边界；本 fix 只补 level-triggered readiness 和 cursor public failure/cleanup，没有改变既有 owner 裁决。

## Changed files

- `docs/host/wu-cli-smoke-01-r1-engine-delta-transient-live-stream-plan.md`：修复全部 accepted plan findings，更新 gate handoff 为 re-review。
- `docs/host/design.md`：为保持 Host 唯一设计真源一致，补充 readiness 无丢唤醒不变量与 attach cursor public failure/cleanup；未修改其它设计职责。
- `docs/reviews/wu-cli-smoke-01-r1-plan-fix-codex.md`：本 plan-fix artifact。

未修改 `docs/host/issues-implementation-control.md`、生产代码、测试、其它 review artifacts 或 README。工作区初始状态已包含 controller 拥有的 control doc 变更和既有 untracked review artifacts；本 gate 未接管或改写它们。

## Validation

- 已完整阅读：`AGENTS.md`、controller adjudication、AgentMiMo/AgentDS 两份 plan review、目标 plan、与 fix 相关的 `docs/host/design.md` 段落及上述直接代码证据。
- 分支：`phaseflow/wu-cli-smoke-01-r1`，不是 protected trunk。
- accepted-finding 内容核验：`rg` 已逐项命中 S1-A/B/C、handoff invariant、唯一 relay owner、terminal-only 排除、typed slow-consumer、never-started cleanup、Event/Queue 与 Slice 2 end-to-end acceptance。
- `git diff --check`：pass，无输出。目标 plan 与本 artifact 当前为 untracked，另用 `git diff --no-index --check /dev/null <path>` 检查，两者均无 whitespace diagnostic；命令 exit 1 仅表示 no-index 内容存在差异。
- scope 核验：本 gate 只写 plan、必要 design 真源与本 artifact；没有运行 commit、push、PR、implementation 或 re-review。
- 测试 / pyright：未运行。本 gate 只有文档变更，且 controller 明确禁止进入 implementation/测试修改；未来实现测试与 pyright 命令已保留在 plan 的 required validation 中。

## Residual risks

- fixed in current plan-fix：两个 review artifacts 的全部 accepted findings、cursor cleanup、Service propagation、Event/Queue 与 end-to-end slow-consumer acceptance 均已进入 code-generation-ready plan。
- covered by later approved Slice 2：真实调度交错、高量 3 × 1,000 delta、slow/fast watcher 隔离、Host close/Ctrl+C 与无 task leak 由当前批准的 adversarial slice 验证，不再推迟到 closeout。
- assigned to later work unit：capacity 256 的真实负载调优与 transient observability 归未来 Host capacity/observability WU。
- accepted existing boundary：单个 delta 大小沿用 Engine contract，本 WU 不新增截断。
- rejected-with-reason as current defect：跨进程、Host restart/reconnect replay 是明确非目标，不扩大本 WU。
- Unclassified residual risk：无。

## Stop confirmation

Status：`completed`。

Artifact path：`docs/reviews/wu-cli-smoke-01-r1-plan-fix-codex.md`。

本 plan-fix 已停止在 controller 指定边界：未修改总控、生产代码、测试或其它 review artifact；未 commit、push、建 PR、implementation 或 re-review。下一入口只能是 controller 派发原 reviewers re-review。
