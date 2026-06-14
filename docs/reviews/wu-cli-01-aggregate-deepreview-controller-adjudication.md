# WU-CLI-01 aggregate deepreview controller adjudication

## Gate

- gate: aggregate deepreview
- work unit: WU-CLI-01
- aggregate review artifacts:
  - `docs/reviews/wu-cli-01-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-cli-01-aggregate-deepreview-ds.md`

## Controller decision

pass-with-fix。

WU-CLI-01 的整体方向成立：本 WU 迁移的是旧 `dayu-agent` CLI / Fins 命令的业务语义、用户可见行为、
参数面和 cancel 语义，并适配当前 Service boundary、Fins runtime 与 Host public contracts / API；不是搬迁旧代码实现。
Aggregate review 未发现 Host / Engine / Fins storage 越界，也未发现旧 write / host management / provider interactive /
migrations 被错误带回。

## Finding adjudication

### AGG-RV-F01：`_close_watcher` 在 cancellation 穿透 cleanup 时无法保证 drain task 回收

- 来源：DS aggregate deepreview finding 1。
- 裁决：accepted。
- 理由：该 finding 有同一执行链路直接证据。`submit_entrypoint_turn_and_wait(...)` 与
  `cancel_entrypoint_run_and_wait(...)` 的 `finally` 中会 `await _close_watcher(...)`；当前 `_close_watcher`
  先 `await watcher.aclose()`，再 `drain_task.cancel()`。若外层 task cancellation 在 `watcher.aclose()` await 点
  落地，`drain_task.cancel()` 与回收不会执行，影响 prompt / interactive 取消路径的资源确定性清理。
- Fix 要求：
  - 调整 `_close_watcher`，确保无论 `watcher.aclose()` 成功、失败或被 cancellation 中断，`drain_task` 都会被
    cancel 并 await 回收。
  - 不吞掉 `watcher.aclose()` 的非取消异常；cleanup 后仍应按原语义向上暴露 relevant error / cancellation。
  - 补测试：fake watcher `aclose()` 抛 `asyncio.CancelledError` 或一般异常时，drain task 仍被 cancel / awaited。

### AGG-RV-F02：`sigint_monitor.install()` 在 try 块之外

- 来源：DS aggregate deepreview finding 2。
- 裁决：deferred-with-owner。
- Owner / destination：CLI hardening follow-up；可并入现有 `WU-CLI-01-RR-06` 的 cross-platform signal / cancel
  adapter 后续工作。
- 理由：该问题只在 `install()` 成功后、`asyncio.create_task(...)` 或简单赋值抛出极端异常时触发；正常 CLI cancel
  语义和当前业务迁移目标不受影响。本 WU 不为该极端 defensive cleanup 扩大 scope，但需要作为后续 signal
  hardening residual 记录。

### AGG-RV-F03：`cancel_entrypoint_run_and_wait` 初始已终态 + 纯 outbox 路径无超时保护

- 来源：DS aggregate deepreview finding 3。
- 裁决：deferred-with-owner。
- Owner / destination：Service / CLI hardening follow-up；与 caller-owned timeout contract / terminal observation
  hardening 同步处理。
- 理由：S2 review 已裁决 Service helper 不持有内部 timeout，caller 通过 task cancellation、`asyncio.wait_for(...)`
  或显式 cancel 控制等待生命周期。当前 CLI 仍可通过用户再次中断本地退出，且该 finding 需要 outbox projection
  长期 lagged / 故障叠加 cancel 路径才触发，不阻塞当前业务语义迁移。但 caller-owned timeout 在 CLI cancel wait
  上的兑现策略需要后续 hardening 明确。

### AGG-RV-F04：`_optional_stripped_text` 重复实现与空白文本语义不一致

- 来源：DS aggregate deepreview finding 4；MiMo maintainability observation。
- 裁决：rejected-with-reason。
- 理由：该问题已在 S6 review 中按当前 slice 范围 rejected。prompt / interactive 对 execution option 空白值报
  usage error，Fins direct metadata 空白值按 missing optional field 处理，当前属于按命令业务语义区分的输入处理，
  不构成 correctness / boundary defect。抽取公共 helper 属于后续 cleanup，不应在 aggregate deepreview gate 中
  为了统一形式扩大 scope。

### MiMo maintainability observations：SIGINT monitor / workspace helper / CLI usage error class 重复

- 来源：MiMo aggregate deepreview observations。
- 裁决：rejected-with-reason。
- 理由：这些 observation 不指出当前执行路径 correctness、stability 或 architecture boundary defect。当前重复均在
  CLI adapter 层内，没有跨层依赖或 public contract drift；抽象化应以后续真实复用压力和具体 contract 为依据，不能在本
  WU 末尾引入横切 refactor。

## Residual risk classification

- Existing deferred residual risks `WU-CLI-01-RR-01` 至 `WU-CLI-01-RR-08` 均保留 owner / destination。
- 新增 residual risk：
  - AGG-RR-01：signal handler install-to-close 极端异常 cleanup hardening，owner：CLI hardening follow-up / `WU-CLI-01-RR-06` destination。
  - AGG-RR-02：CLI cancel wait caller-owned timeout 兑现策略，owner：Service / CLI hardening follow-up。

## Validation evidence reviewed

- MiMo aggregate artifact：未发现实质性问题，列出低价值 maintainability observations。
- DS aggregate artifact：1 个 accepted 中危 cleanup finding，2 个 deferred low findings，1 个 rejected low helper finding。
- 进入 aggregate 前 controller 复核：工作区 clean；S7 后 `pytest tests/cli -q` 94 passed；`pyright` 0 errors。

## Next gate

AgentCodex aggregate fix gate，修复 AGG-RV-F01，并更新对应测试 / artifact。禁止修 AGG-RV-F02、AGG-RV-F03、
AGG-RV-F04 或做横切 cleanup。
