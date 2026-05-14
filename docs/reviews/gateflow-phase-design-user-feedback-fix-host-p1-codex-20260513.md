# Host Phase 1 User Feedback Design Fix

## Work Gate

phase design fix after user feedback

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

## Source User Feedback

1. “我没看到 lane 和 FileLock 的设计”。Controller 裁决：成立，是阻塞 Phase 1 plan 的 design gap。
2. “ScenePrepare 和 ToolsDiscovery 推迟到 P12”。Controller 裁决：用户指定 deferred destination，但当前 P12 标题是 Audit / Tool Trace / Outbox Projections，职责明显不同，必须显式处理。

## Fix Status

### Feedback 1: 已修复

- `docs/host/design.md` §3 已新增 `### 3.1 dayu.runtime.lane`。
- lane 设计已覆盖：
  - 第一版对象 / 协议命名：`LaneConfig`、`LaneToken`、`LaneAcquired`、`LaneAcquireCancelled`、`LaneAcquireTimedOut`、`LaneAcquireOutcome`、`LaneController`。
  - public API shape：`LaneController.from_configs(...)`、`LaneController.acquire(...)`、`LaneController.close(...)`。
  - named lane capacity 配置：非空 name、正整数 capacity、重复 name / 未知 name / 非正 capacity 为配置错误。
  - acquire / release 生命周期：token 模型为必需 primitive，`LaneToken.release()` 幂等，可选 async context helper 不得引入第二套生命周期。
  - cancellation / shutdown：等待 acquire 支持 `CancellationToken`、外层 `asyncio.Task.cancel()` 透传、timeout、`LaneController.close()` 取消 pending acquire；持有 token 时由 owner task 在 `finally` / context helper 中 release。
  - fairness / ordering / timeout / non-goals：不承诺 FIFO、公平性、优先级、跨进程全局容量、lease / fencing、dead owner takeover 或 capacity recovery。
  - import boundary：只能依赖标准库、`dayu.contracts.cancellation.CancellationToken` 和同包层中立 helper。
  - 明确 lane token 不是 Host truth、不是 lease / fencing、不是 Attempt owner、不是 dispatch record。
  - Phase 1 只实现 runtime primitive，不实现 Host dispatch usage、LLM provider policy 或 Host durable state machine。

- `docs/host/design.md` §3 已新增 `### 3.2 dayu.runtime.filelock`。
- filelock 设计已覆盖：
  - wrapper API shape：`RuntimeFileLockOptions`、`RuntimeFileLockToken`、`RuntimeFileLock`、`file_lock(...)`。
  - sync / async 边界：Phase 1 只提供同步 wrapper，不提供 async file lock context manager，也不隐藏线程池阻塞。
  - timeout / path / directory / error semantics：显式 lock path、parent directory creation、`timeout_seconds=None/0/>0` 语义、第三方 timeout 包装为 runtime timeout error、路径和 acquire failure 归一为 runtime file lock error。
  - stale lock / reentrancy / release：不实现 stale lock takeover / break lock，不承诺 reentrant lock，token release 幂等，context manager 异常路径 release。
  - 第三方依赖边界：只有 `dayu.runtime.filelock` 可以直接 import `filelock.FileLock`。
  - 明确 filelock 不能用于 SQLite transaction、EventLog ordering、Host durable truth、Run / Attempt owner、lease / fencing 或 recovery 判断。

- `docs/host/implementation-control.md` Phase 1 已同步 lane / filelock 的进入条件、关键设计问题、Slice 2A / 2B、验证要求和退出条件。
- `dayu/README.md` 已同步 lane 为 process-local async named semaphore、filelock 为 sync wrapper。

### Feedback 2: 已处理但存在 Blocking Question For Controller

- `docs/host/implementation-control.md` Phase 1 后续依赖已明确：ToolsDiscovery / ScenePrepare 具体 adapter 与 manifest / provider typed contract 按用户要求 deferred destination 标记为 P12。
- `docs/host/implementation-control.md` Phase 12 已新增 Scope guard：当前 Phase 12 既有职责仍是 Audit / Tool Trace / Outbox Projections；ToolsDiscovery / ScenePrepare 属于 external assembly / scene-tool preparation，不得静默夹带进现有 P12 projection implementation。
- 因职责冲突无法由 fix agent低风险改写为“现有 P12 直接承载”。需要 controller / user 在 P12A、重排 P12 或扩展 P12 文案之间决策。

## Blocking Questions For Controller

### BQ1: ToolsDiscovery / ScenePrepare 的 P12 destination 应如何落地？

- **为什么阻塞**：用户指定 deferred destination 为 P12，但当前 P12 的目标、范围、设计章节、slice 和验证要求全部是 Audit / Tool Trace / Outbox projection。ToolsDiscovery / ScenePrepare 是 external assembly / scene-tool preparation，直接塞入现有 P12 会破坏 phase ownership，并让 P12 implementation agent 同时处理 projection sinks 与工具 / 场景装配设计。
- **推荐决策**：创建 `P12A. External Assembly / ToolsDiscovery / ScenePrepare` 独立 work unit，排在现有 P12 之后或由 controller 按依赖重新排序。这样满足用户的 P12 destination 意图，同时不污染现有 P12 projection 职责。
- **备选 1**：重排现有 Phase 12，把原 P12 projection 后移为 P13 或 P12B，空出 P12 给 ToolsDiscovery / ScenePrepare。风险是影响后续 Phase 13 RemoteProxy / RemoteStub 与 Phase 14 Retention 编号和引用。
- **备选 2**：扩展现有 P12 文案，把 ToolsDiscovery / ScenePrepare 与 Audit / Tool Trace / Outbox 合并。风险最高，会形成职责不相干的大 phase，降低 plan review 和 implementation slice 可审查性。
- **不决策风险**：后续 controller / agent 可能把 “P12” 解读为现有 projection phase，导致 external assembly work 被夹带进 projection implementation，或在 Phase 1 closeout 中留下未分类 residual risk。

## Changed Files

- `dayu/README.md`
- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `docs/reviews/gateflow-phase-design-user-feedback-fix-host-p1-codex-20260513.md`

## Validation

- `git diff --check`
  - Result: passed, no whitespace errors.

未运行 pyright；当前 gate 是文档级 phase design fix，且未修改生产代码。

## Residual Risks

- 当前 gate 已修复：lane / filelock design gap。
- 需要 controller 决策：ToolsDiscovery / ScenePrepare 的 P12 destination 与现有 P12 projection scope 冲突。
- 后续 phase plan 覆盖：lane 的具体实现细节、filelock wrapper error class naming、runtime import boundary test file placement。

## Ready For Re-Review

是，但 Phase 1 进入 phase plan 前仍需要 controller / user 回答 BQ1。

## Artifact Path

`docs/reviews/gateflow-phase-design-user-feedback-fix-host-p1-codex-20260513.md`
