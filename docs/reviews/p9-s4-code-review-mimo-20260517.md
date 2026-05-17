# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-p9-conversation-memory
- Base: main
- Output file: docs/reviews/p9-s4-code-review-mimo-20260517.md
- Included scope: dayu/host/memory_repair.py (new), dayu/host/durable/memory.py (reset + imports), dayu/host/admission.py (ProjectionCatchupPort + best-effort hook), dayu/host/dispatch.py (ProjectionCatchupPort pass-through + scheduler best-effort hook), tests/host/test_memory_projection.py (rebuild / reset / catch-up tests), tests/host/test_admission_queue.py (catch-up failure resilience tests), tests/host/test_dispatch_scheduler.py (scheduler catch-up failure resilience test)
- Excluded scope: committed S1-S3 changes; dayu/host/memory.py, dayu/host/run_input.py, dayu/host/durable/schema.py (all S1-S3 committed)
- Parallel review coverage: 无

## Findings

### 1-未修复-中-resolve_wait 路径缺失 projection catch-up hook

- **入口/函数**: `dayu/host/command.py:505` `resolve_wait()`
- **文件(行号)**: `dayu/host/command.py:505-528`
- **输入场景**: 外部通过 `resolve_wait` 提交 wait result，wait service 内部 append `TOOL_RESULT_ACCEPTED` canonical fact
- **实际分支**: `resolve_wait` 只调用 `wake_dispatch`（L525），不调用 projection catch-up
- **预期行为**: `TOOL_RESULT_ACCEPTED` 是 memory projection 的核心事件来源（plan S4 要求 catch-up 覆盖 TOOL_RESULT_ACCEPTED）。`resolve_wait` 是该事件的两大产生路径之一（另一路径是 `engine_ingest`），应在 EventLog commit 后触发 best-effort catch-up
- **实际行为**: catch-up hook 只接入 `HostAdmissionService` 的 `start_run` / `submit_followup_queue` / `closeout_attempt_terminal` 三条路径（`admission.py:472,506,617`）和 `HostDispatchScheduler.wake_queue_promotion`（`dispatch.py:410`）。`resolve_wait` 通过 `DefaultHostResolveWaitService` 直接操作 transaction runner 和 event log store，绕过了 `HostAdmissionService`，因此 catch-up hook 被完全跳过
- **直接证据**: `command.py:517-528` — `resolve_wait` 构造 `DefaultHostResolveWaitService` 并调用 `service.resolve_wait()`，随后只调用 `wake_dispatch`。`waiting.py:824` — `append_event` 写入 `TOOL_RESULT_ACCEPTED`。无任何 `projection_catchup` 引用
- **影响**: `TOOL_RESULT_ACCEPTED` 事件（工具验证事实，memory verified_facts 的唯一来源）在 wait resolution 路径不会触发 memory projection catch-up。memory snapshot 会滞后于 EventLog，直到下一次通过其它路径触发的 catch-up 才能追平。对于依赖 wait resolution 的财报工具调用场景，verified facts 在同一会话内可能有明显延迟进入 memory context
- **建议改法和验证点**: 在 `command.py:resolve_wait` 的 `service.resolve_wait()` 之后、`wake_dispatch` 之前，增加 `_catch_up_projection_best_effort(host._admission_service.projection_catchup_port)` 调用。需新增 import 或直接通过 host handle 访问。验证：补测试确认 `resolve_wait` commit 后 catch-up 被调用，且 catch-up failure 不影响 resolve_wait 返回值
- **修复风险（低/中/高）**: 低 — 只增加一行 hook 调用，不改变 transaction 边界
- **严重程度（低/中/高/严重）**: 中 — 不会导致数据损坏或状态不一致，但会延迟 verified facts 进入 memory context，对用户体验有可感知影响

### 2-未修复-中-catch-up hook 静默吞异常导致 projection failure 不可观测

- **入口/函数**: `dayu/host/admission.py:2469` `_catch_up_projection_best_effort()` 和 `dayu/host/dispatch.py:1032` `_catch_up_projection_best_effort()`
- **文件(行号)**: `admission.py:2478-2480`, `dispatch.py:1043-1045`
- **输入场景**: projection catch-up 抛出任何异常（HostDurableError、ProjectionConsumer 异常、SQLite 错误等）
- **实际分支**: `except Exception: pass` — 所有异常被静默丢弃
- **预期行为**: plan S4 明确要求 "projection-local failure 可观测"。best-effort 不影响命令返回是正确的，但 failure 必须有观测手段（日志、metric 或 diagnostic），否则生产环境 memory projection 持续失败时无人知晓
- **实际行为**: 两个 `_catch_up_projection_best_effort` 函数均使用 `except Exception: pass`，不记录日志、不写 diagnostic、不更新 metric。注意：projection runner 内部的 consumer apply failure 会被 runner 记录到 `host_projection_failures` table，但 runner 初始化失败、transaction runner 错误、或 runner 外层异常会被此处完全吞掉
- **直接证据**: `admission.py:2478-2480` — `try: projection_catchup_port.catch_up_projection() except Exception: pass`。`dispatch.py:1043-1045` — 同样模式
- **影响**: 生产环境中 memory projection 持续失败时完全不可观测。runner-level failure 有 projection failure row 可查，但 runner 外层异常（transaction runner 故障、consumer 初始化错误等）会完全丢失
- **建议改法和验证点**: 在 `except Exception` 分支中增加 `logging.getLogger(__name__).debug("projection catch-up failed", exc_info=True)` 或等价日志。不改变 best-effort 语义，但使 failure 可被日志系统捕获。验证：确认日志输出存在
- **修复风险（低/中/高）**: 低 — 只增加一行日志
- **严重程度（低/中/高/严重）**: 中 — 当前功能正确，但运维可观测性缺失会在生产环境放大问题发现时间

### 3-未修复-低-ProjectionCatchupPort 放在 admission.py 形成跨层 contract 依赖

- **入口/函数**: `dayu/host/admission.py:175` `ProjectionCatchupPort` Protocol
- **文件(行号)**: `admission.py:175-189`, `dispatch.py:18` import
- **输入场景**: `dispatch.py` 需要使用 `ProjectionCatchupPort` 类型注解
- **实际分支**: `dispatch.py` 从 `admission.py` import `ProjectionCatchupPort`
- **预期行为**: plan S4 说 "若必须新增，只能新增最小通用 extension"。`ProjectionCatchupPort` 是一个通用 projection catch-up 端口协议，语义上属于 projection 层通用 contract，不是 admission 专用
- **实际行为**: Protocol 定义在 `admission.py`，导致 `dispatch.py` 必须从 `admission.py` import 一个与 admission 业务无关的通用 projection contract。`dispatch.py` 已依赖 `admission.py` 的 `PendingDispatchRecord` 和 `create_host_admission_service`，但 `ProjectionCatchupPort` 不属于 admission 语义
- **直接证据**: `dispatch.py:18-21` — `from dayu.host.admission import (PendingDispatchRecord, ProjectionCatchupPort, create_host_admission_service,)`
- **影响**: 低 — 当前只有两个消费方，依赖方向也不违反分层（dispatch 本就依赖 admission）。但如果未来 `engine_ingest.py` 或 `waiting.py` 也需要注入 catch-up port，从 `admission.py` import projection contract 会越来越不合理
- **建议改法和验证点**: 将 `ProjectionCatchupPort` 和 `NoopProjectionCatchupPort` 移到 `dayu/host/projection.py` 作为通用 projection contract。admission.py 和 dispatch.py 改为从 projection.py import。当前阶段可接受维持现状，标记为后续 cleanup
- **修复风险（低/中/高）**: 低 — 纯符号搬迁，无行为变化
- **严重程度（低/中/高/严重）**: 低 — 架构洁癖问题，不影响功能

### 4-未修复-低-wake_queue_promotion 重复触发 catch-up

- **入口/函数**: `dayu/host/dispatch.py:400` `wake_queue_promotion()`
- **文件(行号)**: `dispatch.py:410-415`
- **输入场景**: scheduler 的 `wake_queue_promotion` 被调用
- **实际分支**: L410 调用 `_catch_up_projection_best_effort`，L411-415 构造 admission service 并调用 `promote_next_queued_run`，而 `promote_next_queued_run` 内部的 `HostAdmissionService` 也注入了 `projection_catchup_port`
- **预期行为**: catch-up 应在 promotion 前触发一次
- **实际行为**: catch-up 在 `wake_queue_promotion` 中触发一次（L410），然后 `promote_next_queued_run` 内部通过 `HostAdmissionService.promote_next_queued_run` 的 `_wake_dispatch_if_needed` 路径不触发 catch-up（`promote_next_queued_run` 不调用 `_catch_up_projection_best_effort`）。但 `create_host_admission_service` 传入了 `projection_catchup_port`（L414），如果未来 `promote_next_queued_run` 增加 catch-up 调用，会出现重复。当前实际只触发一次
- **直接证据**: `dispatch.py:410` — `_catch_up_projection_best_effort(self._projection_catchup_port)`。`admission.py:638-652` — `promote_next_queued_run` 不调用 `_catch_up_projection_best_effort`
- **影响**: 低 — 当前实际只触发一次 catch-up。但如果未来 `promote_next_queued_run` 增加 catch-up hook，会出现重复调用。catch-up 是幂等的，重复调用不会导致错误
- **建议改法和验证点**: 当前无需修改。如果未来 `promote_next_queued_run` 增加 catch-up hook，应移除 `wake_queue_promotion` 中的显式调用
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低 — 当前无实际重复，仅为潜在维护风险

## Open Questions

- 无

## Residual Risk

1. **resolve_wait 路径 catch-up 缺失**（Finding 1）是 S4 最显著的覆盖面缺口。`TOOL_RESULT_ACCEPTED` 的两大产生路径中，admission 路径（start_run / submit_followup / terminal closeout）已覆盖，但 wait resolution 路径未覆盖。建议 S4 闭环前修复，或将此作为明确 residual risk 指派给 Phase 10。
2. **engine_ingest 路径**（`dayu/host/engine_ingest.py`）也产生 `TOOL_RESULT_ACCEPTED`，但 engine ingest 是 scheduler dispatch loop 的一部分，当前 scheduler 没有在 ingest 后触发 catch-up。这与 resolve_wait 是同类问题，但 engine ingest 事件会在下一次 admission 命令触发时被 catch-up 追平，延迟相对可控。
3. **silent exception swallowing**（Finding 2）在生产环境中可能导致 memory projection 问题长期不可发现。建议至少增加 debug 日志。
4. **submit_followup_queue 的 catch-up failure 测试**缺失。现有测试覆盖 start_run、terminal_closeout、scheduler promotion 三条路径的 catch-up failure resilience，但 submit_followup_queue 路径（`admission.py:506`）虽有相同模式未被测试覆盖。作为代码模式完全一致的路径，风险低。

## 验证确认

- rebuild 复用 `ProjectionRunner` + `ConversationMemoryProjectionConsumer`（`memory_repair.py:191-198`），无 memory 专用 runner 旁路 ✓
- rebuild 写 snapshot 与 checkpoint 原子一致（通过 `ProjectionRunner.run_once` → `write_memory_snapshot_with_checkpoint`），不 append EventLog，不改 Run / Attempt / wait / dispatch 状态 ✓
- `reset_conversation_memory_projection` 按 consumer 粒度清理 snapshot / item / diagnostic / failure / checkpoint（`durable/memory.py:443-476`），保留其它 consumer ✓
- provenance 保留原始 event_id / event_sequence / payload_ref / digest_ref（`memory_repair.py:191-198` → `ConversationMemoryProjectionConsumer.apply_event` → `_memory_projection_event_from_view`）✓
- snapshot digest 不含 built_at（`memory.py:737-750` docstring 明确排除）✓
- catch-up hook 是 best-effort：failure 不影响 start_run / submit_followup / terminal closeout / scheduler promotion / dispatch wakeup ✓
- `ProjectionCatchupPort` 是通用 Protocol，`ConversationMemoryProjectionCatchupPort` 是 memory 专用实现，无旁路 ✓

## Verdict

No blocking findings。1 条中等严重度 finding（resolve_wait catch-up 缺失）建议在 S4 闭环前修复或明确标记为 residual risk；1 条中等严重度 finding（silent exception）建议增加日志；2 条低严重度 finding 为架构优化建议。
