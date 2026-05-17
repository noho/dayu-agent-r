# Code Review — P9-S4 Re-review

## Scope

- Mode: current changes (re-review after fix round)
- Branch: feat/host-p9-conversation-memory
- Base: main
- Original review: docs/reviews/p9-s4-code-review-ds-20260517.md
- Output file: docs/reviews/p9-s4-code-rereview-ds-20260517.md
- Included scope: same as original review + fix changes across dayu/host/projection.py, admission.py, dispatch.py, tool_runtime.py, waiting.py, command.py, and corresponding test files
- Pre-review checks: 129 tests passed; pyright 0 errors; git diff --check clean

## Findings from Original Review — Closure Status

### Finding 1 (中): ProjectionCatchupPort 定义在 admission.py 形成跨关注点耦合 → CLOSED

- **原问题**: `ProjectionCatchupPort` Protocol 定义在 `admission.py:175-189`，dispatch 从 admission import projection 层协议
- **修复**: 
  - `ProjectionCatchupPort` Protocol 迁至 `projection.py:251-276`
  - `NoopProjectionCatchupPort` 迁至 `projection.py:268-276`
  - admission 从 `projection.py` import（`admission.py:93-97`）
  - dispatch 从 `projection.py` import（`dispatch.py:71-74`）
  - waiting 从 `projection.py` import（`waiting.py:87-90`）
  - tool_runtime 从 `projection.py` import（`tool_runtime.py:88-91`）
- **直接证据**: 
  - `projection.py:251`：`class ProjectionCatchupPort(Protocol)` — 定义在 projection layer
  - `admission.py`、`dispatch.py` 中原 Definition 已删除（rg 确认 0 matches）
  - 所有消费者统一从 `dayu.host.projection` import
- **裁决**: 已闭合。Projection 层契约现在聚合在 `projection.py`，无跨层反向依赖。

### Finding 2 (中): 工作线程事件消费路径与 resolve_wait 路径 catch-up hook 缺失 → CLOSED

- **原问题**: `_consume_worker_events` → `EngineEventIngestor.ingest()` 添加 `TOOL_RESULT_ACCEPTED` 后不触发 catch-up；`resolve_wait` 路径完全无 catch-up
- **修复**:
  - `DefaultHostToolFactAcceptPort` 增加 `projection_catchup_port` 可选参数（`tool_runtime.py:1840,1860`），`accept_tool_fact()` 返回 `ToolFactAcceptedAck` 后调用 `catch_up_projection_best_effort()`（`tool_runtime.py:1881`）
  - dispatch tool runtime wiring 传入 scheduler projection port（`dispatch.py:733`）：`projection_catchup_port=self._projection_catchup_port`
  - `DefaultHostResolveWaitService` 增加 `projection_catchup_port` 可选参数（`waiting.py:548,568`），`resolve_wait()` write transaction 返回后调用 `catch_up_projection_best_effort()`（`waiting.py:591`）
  - `command.resolve_wait` 从 `host._admission_service.projection_catchup_port` 传入（`command.py:522`）
- **直接证据**:
  - `tool_runtime.py:1881`：`catch_up_projection_best_effort(self._projection_catchup_port)` — 位于 `ToolFactAcceptedAck` 且 `tool_result_event_ref is not None` 分支后
  - `waiting.py:591`：`catch_up_projection_best_effort(self._projection_catchup_port)` — 位于 write transaction 返回后
  - `dispatch.py:733`：`projection_catchup_port=self._projection_catchup_port` — 传入 DefaultHostToolFactAcceptPort
  - `command.py:522`：`projection_catchup_port=host._admission_service.projection_catchup_port` — 传入 DefaultHostResolveWaitService
- **残余 gap**: `_consume_worker_events` 中 `EngineEventIngestor.ingest()` 循环本身不触发 catch-up；但 tool fact accept 路径已通过 tool runtime chain 覆盖；ingestor 写入的其他 EventLog 事件（如 terminal closeout 内的 `EPISODE_SUMMARY_ACCEPTED`）由 admission closeout catch-up 覆盖。Worker 事件消费的周期性 lag 仍在，但这是 S4 设计取舍（best-effort，非实时）。
- **裁决**: 已闭合。TOOL_RESULT_ACCEPTED 和 resolve_wait 两个主要遗漏路径均已覆盖。剩余 worker 事件循环 lag 保持为 residual risk。

### Finding 3 (低): Catch-up 失败信息被完全丢弃，缺乏可观测性 → CLOSED

- **原问题**: `ConversationMemoryProjectionCatchupPort.catch_up_projection()` 丢弃返回值；`_catch_up_projection_best_effort` 静默吞异常
- **修复**: 
  - 统一 shared helper `catch_up_projection_best_effort` 在 `projection.py:278-293`
  - `except Exception` 块调用 `_LOGGER.exception("projection catch-up failed; continuing")`（`projection.py:292`）
  - `_LOGGER = logging.getLogger(__name__)` 使用模块名 `dayu.host.projection`（`projection.py:40`）
- **直接证据**:
  - `projection.py:40`：`_LOGGER = logging.getLogger(__name__)`
  - `projection.py:291-292`：`except Exception: _LOGGER.exception("projection catch-up failed; continuing")`
  - `test_toolruntime_accept_barrier.py:133`：`with caplog.at_level("ERROR", logger="dayu.host.projection")`
  - `test_toolruntime_accept_barrier.py:145`：`assert "projection catch-up failed; continuing" in caplog.text`
- **裁决**: 已闭合。Catch-up 失败现在通过 Python logging 框架以 ERROR 级别记录，包含完整 traceback（`logger.exception`），且测试验证日志输出。

### Finding 4 (低): `_catch_up_projection_best_effort` 在 admission.py 和 dispatch.py 中重复定义 → CLOSED

- **原问题**: 两个模块各自定义 `_catch_up_projection_best_effort`，语义相同但参数签名略有差异
- **修复**: 
  - 统一 shared helper `catch_up_projection_best_effort(projection_catchup_port: ProjectionCatchupPort | None)` 在 `projection.py:278-293`
  - 处理 `None` port（early return，`projection.py:287-288`）
  - admission.py 原 `_catch_up_projection_best_effort` 已删除
  - dispatch.py 原 `_catch_up_projection_best_effort` 已删除
- **直接证据**: rg 确认 admission.py 和 dispatch.py 中无 `_catch_up_projection_best_effort` 定义；所有调用点使用 `dayu.host.projection.catch_up_projection_best_effort`。
- **裁决**: 已闭合。单一 shared helper，统一处理 `None` port 和 logging。

## Re-review of Original Mandatory Check Items

| # | Check Item | Status |
|---|-----------|--------|
| 1 | Rebuild/catch-up 复用 ProjectionRunner | PASS（未变，确认无新增旁路） |
| 2 | Snapshot + checkpoint 原子一致 | PASS（未变，runner 事务模式不变） |
| 3 | Rebuild 不 append EventLog，不改治理状态 | PASS（未变） |
| 4 | Reset 按 consumer 粒度安全清理 | PASS（未变） |
| 5 | Provenance 保留原始 event_id/event_sequence | PASS（未变） |
| 6 | Snapshot digest 稳定 | PASS（未变） |
| 7 | Best-effort catch-up 不影响主命令结果 | PASS（强化：新增 tool fact accept / resolve_wait 失败存活测试） |
| 8 | 无 weak typing / Any / 魔法字符串 / 反向依赖 | PASS（强化：Protocol 迁至 projection.py 消除 admission→projection 语义耦合） |

## New Findings

### 1-未修复-低-tool_runtime catch-up 仅在 `ToolFactAcceptedAck` 且 `tool_result_event_ref is not None` 时触发

- **入口/函数**: `tool_runtime.py:1877-1881` `DefaultHostToolFactAcceptPort.accept_tool_fact()`
- **文件(行号)**: `tool_runtime.py:1877-1881`
- **输入场景**: tool fact accept 返回非 `ToolFactAcceptedAck` 结果（如 rejected、duplicate）或 `tool_result_event_ref` 为 `None` 的 ack
- **实际分支**: 条件 `isinstance(result, ToolFactAcceptedAck) and result.tool_result_event_ref is not None` 不满足时，不触发 catch-up
- **预期行为**: duplicate ack 和某些边缘 ack 场景下不应触发 catch-up（无新 EventLog 行），这是正确行为
- **实际行为**: 只有新写入 TOOL_RESULT_ACCEPTED 的 accepted ack 才触发 catch-up，语义正确
- **直接证据**: `tool_runtime.py:1877-1881` 的条件守卫
- **影响**: 无负面影响。条件准确地守卫了"有新 EventLog entry 写入"的场景。
- **建议改法和验证点**: 无需修改。条件守卫语义正确：rejected/duplicate/timeout 结果不产生新 EventLog 行，无需 catch-up。
- **修复风险（不适用）**:
- **严重程度（低）**: 设计正确，记录为已验证的边界条件。

## Open Questions

- 无。

## Residual Risk

1. **Worker 事件消费循环 projection lag**（延续自原 review Risk 1）：`_consume_worker_events` 中的 `EngineEventIngestor.ingest()` 调用循环不触发 catch-up。tool fact accept 路径已通过 tool runtime chain 覆盖，但 worker 产生的其他 canonical fact（如 `ATTEMPT_RUNNING`，不过该事件不在 memory consumer filter 中）和关闭 edge case 仍依赖 admission/dispatch 层面的 catch-up。lag 窗口已显著缩小，但仍建议 S5 评估 periodic catch-up。**Owner: S5 planning**。

2. **EngineEventIngestor 仍不接受 projection_catchup_port**：`dispatch.py:943-946` 构造 `EngineEventIngestor` 时不传 projection port。当前 design intent 明确 ingestor 不负责 projection catch-up（catch-up 由 tool runtime chain 和 admission hooks 覆盖），这处空白是设计一致的选择，不是遗漏。**Owner: 无需处理，记录澄清**。

## Verdict

**PASS。** 原始 review 中 4 项 findings 全部闭合：

- Finding 1 (中): `ProjectionCatchupPort` / `NoopProjectionCatchupPort` / `catch_up_projection_best_effort` 统一迁至 `projection.py`，所有消费者统一导入
- Finding 2 (中): `TOOL_RESULT_ACCEPTED` 和 `resolve_wait` 路径均已覆盖 catch-up hook
- Finding 3 (低): 统一 shared helper 通过 `logger.exception()` 记录失败，测试验证日志输出
- Finding 4 (低): 重复 helper 已消除，统一为 `projection.py` 中的单一实现

新增测试（`test_tool_fact_accept_survives_projection_catchup_failure` + caplog、`test_resolve_wait_survives_projection_catchup_failure`、`test_scheduler_queue_promotion_survives_projection_catchup_failure`、dispatch tool runtime wiring assertion）正确覆盖修复点。129 tests passed，pyright 0 errors。无 blocking finding。
