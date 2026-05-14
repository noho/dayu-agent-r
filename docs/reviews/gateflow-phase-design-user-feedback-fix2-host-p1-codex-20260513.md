# Host Phase 1 User Feedback Design Fix Round 2

## Work Gate

phase design fix after user feedback round 2

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

## Source User Feedback

1. lane 必须是跨进程的。用户要求读取 `dayu/README.md` 项目目标；README / Host design 目标明确支持单机多客户端 / 多进程。Controller 裁决：上一轮 process-local lane 设计不成立，必须改为 cross-process runtime lane design。
2. Phase 重排：把现有 P12 后移，P12 专门给 ToolsDiscovery / ScenePrepare。

## Fix Status

### Feedback 1: 已修复

- `dayu/README.md` 已删除 lane 的 process-local / 不提供跨进程容量旧表述，改为 cross-process named semaphore / capacity guard。
- `docs/host/design.md` §3 / §3.1 已改为 cross-process lane 设计。
- lane 第一版 coordinator 选型为独立 runtime SQLite lane DB：
  - 通过短事务实现跨进程 capacity compare-and-claim。
  - 显式注入 `SQLiteLaneCoordinatorConfig(db_path=...)`。
  - 不复用 Host durable store / EventLog / state index DB。
  - 只保存 runtime capacity coordination rows，不保存 Session / Run / Attempt / EventLog / Tool / 财报业务字段。
- public API shape 已补齐：
  - `LaneConfig`
  - `LaneOwner`
  - `SQLiteLaneCoordinatorConfig`
  - `LaneClaimToken`
  - `LaneAcquired`
  - `LaneAcquireCancelled`
  - `LaneAcquireTimedOut`
  - `LaneAcquireOutcome`
  - `LaneController.open(...)`
  - `LaneController.acquire(...)`
  - `LaneController.close(...)`
- capacity claim / release 生命周期已补齐：
  - `claim_id` 为不可猜测随机 id。
  - `owner` 只用于 runtime cleanup / diagnostics，不是 Host owner。
  - `LaneClaimToken.release()` 异步且幂等。
  - token 持有期间通过 heartbeat / refresh 延长 `expires_at`。
  - expired claims 由后续 acquire 在短事务内清理。
- cancellation / shutdown / timeout 已补齐：
  - 等待 acquire 可被 `CancellationToken` 取消。
  - 外层 `asyncio.Task.cancel()` 必须透传。
  - `timeout_seconds=None/0/>0` 语义明确。
  - `LaneController.close()` 停止新 acquire、唤醒 pending acquire，并 best-effort release 当前 controller tokens。
- 边界保留：
  - lane 只表达 runtime resource capacity。
  - lane token / claim 不是 Host truth、不是 lease / fencing token、不是 Attempt owner、不是 dispatch record、不是 recovery proof。
  - stale cleanup 只释放 runtime capacity，不能证明 Host Attempt orphan，不能写 EventLog，不能授权 takeover。
- multi-process tests 已写入 Phase 1 验证要求与退出条件：
  - 多个独立 Python 进程共享同一 lane DB 时 successful claims 总数不超过 capacity。
  - capacity 满时另一个进程 non-blocking acquire timed out。
  - 正常 release 后其它进程可 acquire。
  - owner 崩溃或停止 heartbeat 后，TTL 过期并清理 stale claim 后其它进程可 acquire。

### Feedback 2: 已修复

- `docs/host/implementation-control.md` Phase Map 已重排：
  - Phase 12: ToolsDiscovery / ScenePrepare。
  - Phase 13: Audit / Tool Trace / Outbox Projections（原 Phase 12 后移）。
  - Phase 14: RemoteProxy / RemoteStub（原 Phase 13 后移）。
  - Phase 15: Retention / Purge / Production Hardening（原 Phase 14 后移）。
- Phase 12 已专门写 external assembly / scene-tool preparation scope：
  - 目标、对应设计章节、前置条件、进入条件、范围、non-goals、关键设计问题、slice、验证要求、退出条件、后续依赖均已改写。
  - 明确不混入 Audit / Tool Trace / Outbox projection；projection scope 已移至 Phase 13。
- 相关引用已同步：
  - `purge_session` destructive cleanup 指向 Phase 15。
  - tool trace / audit / outbox projection 指向 Phase 13。
  - RemoteProxy / RemoteStub 指向 Phase 14。
  - Retention / Purge / Production Hardening 指向 Phase 15。

## Changed Files

- `dayu/README.md`
- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `docs/reviews/gateflow-phase-design-user-feedback-fix2-host-p1-codex-20260513.md`

## Validation

- `git diff --check`
  - Result: passed; no whitespace errors reported.
- Residual text scan:
  - `process-local` / “不提供跨进程” / “跨进程全局容量” no longer appear in `dayu/README.md`、`docs/host/design.md`、`docs/host/implementation-control.md`.
  - Old Phase Map headings `Phase 12. Audit...`、`Phase 13. RemoteProxy...`、`Phase 14. Retention...` no longer appear in `docs/host/implementation-control.md`.

未运行 pyright；当前 gate 是文档级 phase design fix，且未修改生产代码。

## Blocking Questions

0.

## Residual Risks

- Phase 1 implementation-ready plan 仍需选择具体 error class naming、SQLite schema detail、heartbeat task ownership 实现细节和 test file placement，但 design 已足够支撑 handoff-ready plan。
- Cross-process lane 使用 runtime SQLite coordinator，会引入一个 workspace-level runtime DB 文件；后续 plan 必须明确默认路径注入、cleanup 策略和 busy timeout 测试。
- ToolsDiscovery / ScenePrepare 的具体业务 provider 与财报 prompt 内容仍属于 Service / Fins / 配置 work unit，不属于 Phase 12 runtime assembly 本体。

## Ready For Re-Review

是。

## Artifact Path

`docs/reviews/gateflow-phase-design-user-feedback-fix2-host-p1-codex-20260513.md`
