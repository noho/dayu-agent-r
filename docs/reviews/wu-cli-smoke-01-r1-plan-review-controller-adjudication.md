# WU-CLI-SMOKE-01-R1 Plan Review Controller Adjudication

## Gate 结论

- Work unit：`WU-CLI-SMOKE-01-R1 Engine Delta Transient Live Stream Remediation`
- Review artifacts：
  - `docs/reviews/plan-review-20260720-230213.md`（AgentMiMo）
  - `docs/reviews/plan-review-20260720-230039.md`（AgentDS）
- 两路结论：均为 `pass-with-risks`
- Controller decision：`fix-required`
- 下一 gate：`plan-fix`

问题动机与 root cause 仍成立。两路 review 均确认 transient live delivery 的 semantic owner 应为 Host runtime，Engine 只拥有 typed chunk 与单生成器内顺序，EventLog 只拥有 durable fact/cursor。当前不改变用户已确认的三类 delta 统一 transient、零 EventLog row 目标。

## Findings 裁决

### AgentMiMo F-01：accepted

接受“当前 Slice 1 缺少可直接执行的内部迁移顺序和逐步不变量”，要求在同一 Slice 1 中写明三个 implementation sub-step 及每步验证点：

1. 建立 Host public contract、hub、publisher/subscription、composition 与 watcher union；
2. Service/CLI 切换到 transient reasoning identity，并验证 durable/transient 分支穷举与 bounded relay；
3. 删除 reasoning durable row、`HostEvent.thinking` 及其 projection/export，验证三类 delta 全部 zero-row。

不接受把这些 sub-step 拆成可独立接受/提交的 production slices。建议中的 Step A 会在生产 contract 中同时产生 reasoning durable row 与 transient delivery，Step B 又会保留无人消费的 durable reasoning row；这与本项目“语义单 owner、全新设计、禁止兼容分支”的约束冲突，也增加可被后续代码重新消费的第二真源。三个 sub-step 只用于同一原子 slice 内降低实施和 review 负担，不形成中间 accepted commit。

### AgentDS F-01：accepted

与 AgentMiMo F-01 重叠。接受其方案 B：为 Slice 1 增加明确 sub-step、handoff invariant 和逐步验证点；拒绝方案 A 的独立 production slice 拆分，理由同上。

### AgentDS F-02：accepted

Plan 必须明确 Service backpressure 的唯一受影响 queue 和完整传播链：只把实际承接 live watcher item 的 `_WatchAndWaitRuntime.queue`（以及由同一 factory 创建、语义等价的 watcher relay queue）设为 bounded；不得机械修改 terminal-only、无 watcher 或一次性 drain queue。`await queue.put()` 满时必须自然阻塞 `_drain_host_events`，继而暂停 Host iterator 消费，最终由 Host subscription bounded queue 的 `put_nowait` 触发 typed `UNAVAILABLE/slow_consumer`；Service 不得 `put_nowait` 丢弃、吞掉或改写该错误。Plan 还必须增加 owner-level propagation test，并明确 terminal/outbox fallback 不因 relay 满而丢失或死锁。

### AgentMiMo F-02：accepted

Plan 必须冻结 cursor attach 失败的公共错误与 cleanup 行为。当前直接代码证明 `_session_live_event_start_cursor` 通过 Host read owner 校验 Session，并以 `HostApiError` 表达不存在/不可读；Host 已关闭仍由同步 public lifecycle gate 抛 `HostClosedError`。实现不得泄漏 durable actor/private exception。若 cursor future 在首次 `__anext__` 时以 typed Host error 失败，subscription 必须在同一 iterator cleanup boundary detach；增加 Session not found、durable read failure、consumer never starts iteration/close 等 cleanup 测试。

## Residual Risk 裁决

- 固定容量 256：`accepted` 作为首版内部安全边界；真实负载调优归未来 Host transient observability/capacity WU，不阻塞本 WU。
- 单个 delta 大小沿用 Engine contract、不新增截断：`accepted`，不是本 WU 的新语义。
- 跨进程、Host restart、reconnect replay：`rejected-with-reason` 作为当前缺陷；这是用户已确认的明确非目标，不能据此扩大当前 WU。
- Event/Queue wakeup 竞态与 Service→Host→CLI slow-consumer 链：`accepted` 为当前 implementation/test acceptance criteria，必须在 Slice 2 adversarial validation 覆盖，不留到 closeout 才首次验证。

## Fix Handoff

AgentCodex 只修改 plan 与必要的 Host design 真源文字，并新增 plan-fix artifact；不得进入生产代码、测试、commit、push 或后续 gate。修复后由原 AgentMiMo / AgentDS 对上述 accepted findings 并行 re-review。
