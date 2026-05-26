# Code Review

## Verdict: FAIL

存在 blocking findings（见 Finding B1、B2）。以下 3 条 blocking findings 及 10 条 non-blocking findings 均基于直接代码路径证据。

---

## Blocking Findings

### Finding B1 - [严重] - 标准 dispatch 路径创建的 dispatch record 初始 owner=NULL，进程崩溃导致 Run 永久卡死且阻塞整个 Session

- **入口/函数**: `HostDispatchScheduler._start_governed_in_transaction`
- **文件(行号)**: `dayu/host/dispatch.py:1230-1291`，具体 `owner_host_instance_id=None` 传入 line 1260
- **输入场景**: accepted/queued Run 进入 pre-start governance 并触发 `_start_governed_in_transaction`，在 `allow_without_budget` 或 `ALLOW_DISPATCH` 决策下创建 dispatch record
- **实际分支**: `start_governed_run_with_starting_attempt_in_transaction(..., owner_host_instance_id=None)` — dispatch record 初始无 owner
- **预期行为**: dispatch record 创建时即应携带当前 scheduler 的 owner host instance id，确保 crash 后 recovery scan 可通过 owner 追溯并执行 orphan proof
- **实际行为**: owner 仅在后续 `_mark_waiting_for_lane`（`dispatch.py:2114`）中设置。若进程在 dispatch record 创建事务提交后、`_mark_waiting_for_lane` 执行前崩溃：
  1. Run 状态: `RUNNING` + `STARTING` Attempt
  2. Dispatch record 状态: `PENDING` + `owner_host_instance_id=NULL`
  3. Recovery scan 调用 `_classify_owner` → `dispatch_record.owner_host_instance_id is None` → 返回 `OrphanProofInconclusive(reason="missing_owner_host_instance_id")`（`recovery_process.py:192-199`）
  4. **不做任何 closeout** — Run 永久卡在当前状态
  5. `_read_startable_run` 检测到 active Run 存在 → 返回 `None` → **阻塞整个 Session 的所有新输入**（`dispatch.py:3155-3157`）
- **直接证据**:
  - `dispatch.py:1260` — `owner_host_instance_id=None` 传入 `StartGovernedRunInput`
  - `recovery.py:289-293` — `_classify_owner` 中 None owner 分支
  - `recovery_process.py:192-199` — `owner_host_instance_id is None` → `OrphanProofInconclusive`
  - `dispatch.py:3094` — `_is_dispatchable_recheck` 也检查 `owner_host_instance_id is not None`
  - 对照：recovery dispatch 路径在创建 dispatch record 时就设置 owner（`recovery.py:434`），不受此问题影响
- **影响**: 崩溃后 Run 永久卡死，阻塞整个 Session，必须手动介入才能解锁。这是生产级阻断缺陷
- **建议改法和验证点**: 在 `_start_governed_in_transaction` 中将 `owner_host_instance_id=None` 改为 `owner_host_instance_id=self._host_instance_identity.host_instance_id`。补充崩溃恢复集成测试：commit 后立即 kill 进程，验证 restart 后 recovery scan 能正确 close orphan
- **修复风险**: 低 — `StartGovernedRunInput.owner_host_instance_id` 已支持非 None 值，recovery 路径已使用非 None 值，纯属调用方传参错误

### Finding B2 - [严重] - dispatch record owner 字段使用 `self._host_handle_id` 而非 `self._host_instance_identity.host_instance_id`

- **入口/函数**: `HostDispatchScheduler._mark_waiting_for_lane` / `_mark_dispatching_after_recheck`
- **文件(行号)**: `dayu/host/dispatch.py:2114`, `dispatch.py:2171`
- **输入场景**: 任何 dispatch drain 路径将 dispatch record 升级为 WAITING_FOR_LANE 或 DISPATCHING
- **实际分支**: `owner_host_instance_id=self._host_handle_id`
- **预期行为**: `owner_host_instance_id=self._host_instance_identity.host_instance_id`
- **实际行为**: 使用 `host_handle_id`（如 `"open-host-abc123"`）写入 `owner_host_instance_id`；`host_instances` 表中注册的 `host_instance_id` 也恰好来自 `host_handle_id`（`dispatch.py:3571`），两者当前巧合相等
- **直接证据**: `dispatch.py:2114` — `mark_dispatch_waiting_for_lane_row(..., owner_host_instance_id=self._host_handle_id, ...)`；`dispatch.py:3571` — `host_instance_id=host_handle_id`
- **影响**: 当前因为巧合相等暂不发生 FK 约束冲突。但若 `host_instance_id` 改为不同值（如 UUID），`owner_host_instance_id` 将指向 `host_instances` 表中不存在的值，recovery scan 所有 ongoing dispatch 均变为不可恢复
- **建议改法和验证点**: 将 `self._host_handle_id` 替换为 `self._host_instance_identity.host_instance_id`
- **修复风险**: 低 — 两者当前值相同，纯属引用纠正

### Finding B3 - [高] - Governance 拒绝的 Run 标记为 FAILED，与真实执行失败不可区分

- **入口/函数**: `HostDispatchScheduler._fail_unstarted_in_transaction` → `fail_unstarted_run_in_transaction`
- **文件(行号)**: `dayu/host/dispatch.py:920-933`, `dispatch.py:980-1009`, `dispatch.py:1029-1038`, `dispatch.py:1059-1068`
- **输入场景**: Context governance 检测到 `BLOCK_HARD_THRESHOLD`、compact 失败或 compact count 不可读
- **实际分支**: 多处调用 `self._fail_unstarted_in_transaction(transaction, run, reason=_GOVERNANCE_FAILURE_REASON, ...)` → `fail_unstarted_run_in_transaction` → 写入 `RUN_FAILED` EventLog + Run 状态 FAILED
- **预期行为**: 从未创建 Attempt 的 accepted/queued Run 被 governance 拒绝应有独立的终态或至少可区分的 event payload 标记
- **实际行为**: governance 拒绝与真实 worker 执行失败在 durable 层面不可区分。上层重试逻辑无法区分两者，可能错误触发自动 retry 绕过治理
- **直接证据**: `dispatch.py:920-933` — input_event_missing → FAILED；`dispatch.py:980-1009` — BLOCK_HARD_THRESHOLD → FAILED
- **影响**: 治理失效风险 — 被治理拒绝的 Run 可能被上层当作可重试的执行失败自动重试
- **建议改法和验证点**: 考虑新增 `RunStatus.REJECTED` 或在 `RUN_FAILED` event payload 中标记 `rejected_by_governance=True`
- **修复风险**: 中 — 涉及 RunStatus 枚举变更，需更新所有 match/case 分支

---

## Scope

- **Mode**: all repository (post draft-PR-pass full repo review)
- **Branch**: feat/phase-12-5-conversation-memory-optimize
- **PR**: https://github.com/noho/dayu-agent-r/pull/68
- **Review date**: 2026-05-26
- **Output file**: docs/reviews/pr-68-postdraft-fullrepo-review-ds-20260526.md
- **Included scope**: 全部 `dayu/` 生产代码、`tests/` 测试代码、`utils/` smoke 脚本、README 文档
- **Excluded scope**: `.venv/` (virtualenv), `workspace/` (临时脚本目录), `docs/reviews/` (历史 review artifacts)
- **Parallel review coverage**: 5 个 subagent 并行覆盖 Host lifecycle/recovery、Memory/compaction、Engine runner/protocol、Service/runtime assembly、Tests/docs consistency；主 reviewer 复核关键交叉链路。其中 tests/docs subagent 产出 18 项 findings（2 HIGH / 3 MEDIUM / 8 LOW / 5 PASS），已去重整合至本 artifact

### Repository Map

```
dayu/
├── contracts/          # 层中立公共契约 (tool_call, tool_result, tool_schema, cancellation, etc.)
├── runtime/            # 公共运行时基础设施 (config_loader, lane, cancellation, tools_discovery, etc.)
├── engine/             # LLM runner 与 Agent 状态机
│   ├── contracts/      # Engine 层契约 (runner, agent_run, messages, engine_events, etc.)
│   └── runners/openai/ # OpenAI 兼容 runner (SSE parser, tool_call_aggregator, payload, etc.)
├── host/               # Host governance 层 (admission, dispatch, recovery, compaction, memory, etc.)
│   └── durable/        # Durable store (state, event_log, transaction, schema, etc.)
├── service/            # Service assembly 层 (host_assembly)
├── config/             # 配置说明
└── fins/               # 财报能力 (本 review scope 内未深度走读)
```

### Reviewed Entry Points & Critical Chains

| Priority Area | Entry Points | Status |
|---|---|---|
| Host lifecycle | `open_host()`, `_PublicHostHandle.close()`, `HostDispatchScheduler.open()/close()`, heartbeat loop, drain loop | 完整走读 |
| Dispatch & admission | `drain_once()`, `_dispatch_one()`, `_run_pre_start_governance()`, `run_queue_promotion()`, `ActiveWorkerRegistry` | 完整走读 |
| Recovery | `StartupRecoveryScanner.scan()`, `classify_orphan_candidate()`, `StdlibPidLivenessProbe` | 完整走读 |
| Compaction contracts | `CompactionRequest`, `CompactionCandidate`, `CompactMaterialPack`, `CompactQualityCheckResult` 及全部 dataclass 校验 | 完整走读 |
| Compaction operation | `run_compaction_operation()`, `_merge_pass_candidates()`, `_merge_text_field_patch()` | 完整走读 |
| LLM compaction | `LLMContextCompactor.compact()`, proposal parsing, `_RejectingToolExecutor` | 部分走读 |
| Context governance | `check_compaction_candidate()`, quality issues, pinned patch validation | 完整走读 |
| Memory projection | `MemoryProjectionPolicy`, `ConversationMemorySnapshot`, `MemoryRepairReason`, `catch_up_conversation_memory_projection()` | 部分走读 |
| Engine runner | `AsyncOpenAIRunner.call()`, `SSEParser`, `ToolCallAggregator`, `await_or_cancel()` | 部分走读 |
| Engine agent | `_AsyncAgent`, `run_agent_and_wait()`, tool call loop | 部分走读 |
| Engine ingest | `EngineEventIngestor`, event type mapping, reactive compaction trigger | 部分走读 |
| Tool runtime | `DefaultToolRuntimeFactory`, accept barrier, duplicate governance, truncation | 部分走读 |
| Service assembly | `open_host()` composition root, `host_assembly.py` | 部分走读 |
| Layer boundaries | import 方向检查 (runtime → engine/host/service, engine → host, host → service) | 完整走读 |
| Durable state | `RunRow`, `AttemptRow`, `DispatchRecordRow`, `SessionRow`, state transitions | 完整走读 |
| Durable transitions | `run_transition.py` primitives, CAS mutation results | 部分走读 |
| Context events | `CONTEXT_COMPACTION_REQUESTED/COMPACTED/FAILED/ATTEMPT_REJECTED` payload builders | 完整走读 |

---

## Non-blocking Findings

### Finding N1 - [高] - LLM Compaction proposal JSON 响应缺少大小上限

- **入口/函数**: `LLMContextCompactor.compact()` → `_parse_proposal()`
- **文件(行号)**: `dayu/host/llm_compaction.py:483-487`
- **输入场景**: LLM 返回超大 JSON proposal（如幻觉导致无限增长的 evidence array）
- **实际分支**: `_parse_proposal` 调用 `json.loads(raw)` 前仅检查 `len(raw) >= _MIN_PROPOSAL_LENGTH`（下限=1），无上限检查。`MAX_EVIDENCE_BACKED_FACT_CANDIDATES` 等上限仅在 `json.loads()` 完成后的 post-init validation 生效
- **预期行为**: proposal 文本应有合理上限（如 128KB），超限时提前拒绝并作为可修复异常进入 retry loop
- **实际行为**: `json.loads(raw)` 完整解析任意大小 JSON，大输入可导致 Host OOM
- **直接证据**: `llm_compaction.py:483-487` — `raw = final_answer.strip()` 后仅 `len(raw) < _MIN_PROPOSAL_LENGTH` 检查；`json.loads(raw)` 无大小限制
- **影响**: LLM in the loop 的关键安全边界缺失；finish_reason=LENGTH 作为间接保护但不可靠
- **建议改法和验证点**: 在 `_parse_proposal` 入口增加 `if len(raw) > MAX_PROPOSAL_CHARS`（建议 128*1024）提前检查
- **修复风险**: 低
- **严重程度**: 高

### Finding N2 - [高] - budget_after_compact 估算使用启发式近似，proactive path 可能错误允许 dispatch

- **入口/函数**: `LLMContextCompactor._candidate_from_final_answer()` → `_budget_after_compact()` → `_estimate_preserved_context_tokens()`
- **文件(行号)**: `dayu/host/llm_compaction.py:1270-1445`
- **输入场景**: Compactor 返回大 episode summary + 大量 preserved refs，但 dropped 部分被估算为已删除
- **实际分支**: `_estimate_preserved_share_from_budget` 使用 `estimated_input_tokens * retained_count / len(source_refs)` 按比例估算保留大小。但 LLM 返回的 `preserved_material_labels` 对应的 canonical ref set 与 `request.material_source_refs` 非 1:1 映射，比例估算可能偏低
- **预期行为**: `budget_after_compact` 应不低於 compact 后实际上下文大小
- **实际行为**: 若估算偏低，`budget_after_compact < hard_threshold` 可能为真但实际上下文仍超限。虽 `_requires_budget_acceptance` 仅对 proactive path 生效（reactive 不以此作闸门），但 proactive path 可能错误允许 dispatch
- **直接证据**: `llm_compaction.py:1372-1401` — `_estimate_preserved_context_tokens`；`llm_compaction.py:1414-1434` — `_estimate_preserved_share_from_budget` 按 ref 数量比例估算；`compaction_operation.py:640-651` — `_requires_budget_acceptance` 仅针对 proactive
- **影响**: proactive compaction budget 闸门可靠性下降；不影响 reactive path
- **建议改法和验证点**: 在 `_estimate_preserved_context_tokens` 中基于 candidate 实际保留 refs 数量修正估算
- **修复风险**: 中
- **严重程度**: 高

### Finding N3 - [低] - SSE parser 未知 finish_reason 默认 fallback 为 STOP

- **入口/函数**: `SSEParser._ingest_line` → `_emit_completion`
- **文件(行号)**: `dayu/engine/runners/openai/sse_parser.py:489-498`, `sse_parser.py:664-670`
- **输入场景**: Provider 返回当前 `_FINISH_REASON_MAP` 中未列出的新 finish_reason 字符串（如未来新增的 `"function_call"` 或 provider 特定值）
- **实际分支**: `_FINISH_REASON_MAP.get(finish_reason)` 返回 `None` → `self._finish_reason` 保持 `None` → 终态 fallback 为 `FinishReason.STOP`
- **预期行为**: 未知 finish_reason 应至少记录 diagnostic 并考虑是否映射为 `ERROR`，避免将 provider 语义变更静默掩盖为正常终止
- **实际行为**: 日志 warning 记录 `unknown_finish_reason`，但流仍以 `STOP` 正常完成，Engine/Host 层无法区分
- **直接证据**: `sse_parser.py:490-492` — `mapped = _FINISH_REASON_MAP.get(finish_reason)` 为 `None` 时只记 log；`sse_parser.py:664` — `self._finish_reason or FinishReason.STOP` 将 None 覆盖为 STOP
- **影响**: 若 provider 新增 finish_reason 语义与 STOP 不同（如表示工具调用被 provider 端拒绝但流正常结束），Host 将无从检测。目前 `tool_calls` 的检测同时依赖 `self._tool_calls_seen` flag（line 667-670），缓解了部分风险
- **建议改法和验证点**: 在 `_emit_completion` 中区分"解析到的已知 finish_reason"与"未解析到的 fallback"；对 fallback 情况考虑产出 `RunnerProtocolErrorData` 或至少确保 `RunnerDoneData` 携带原始 finish_reason 字符串
- **修复风险**: 低 — 改动仅影响未知 finish_reason 的终态映射，不改变已知路径
- **严重程度**: 低

### Finding N4 - [低] - Drain loop 在队列为空时仍调用 drain_once()

- **入口/函数**: `HostDispatchScheduler._drain_loop`
- **文件(行号)**: `dayu/host/dispatch.py:1929`
- **输入场景**: 队列为空时的正常 idle 轮询
- **实际分支**: `if self._queue.empty()` 为 True → sleep → 无条件调用 `drain_once()`（line 1929）
- **预期行为**: sleep 后应回到 while 循环开头重新检查 `self._closed`，`drain_once()` 调用是多余的
- **实际行为**: `drain_once()` 在 `self._queue.empty()` 为 True 时立即返回零结果 `DispatchDrainResult(0,0,0,0)`，无功能错误但产生一次不必要的 async 调用和 lock 操作
- **直接证据**: `dispatch.py:1913-1929` — 条件体 sleep 后不 `continue`，而是穿透到 `result = await self.drain_once()`
- **影响**: 极轻微的性能开销（每个 poll 周期多一次 async 函数调用），不影响正确性
- **建议改法和验证点**: 在 sleep 后添加 `continue` 跳过 `drain_once()`，或重构为 if/else 结构
- **修复风险**: 低 — 纯控制流整理
- **严重程度**: 低

### Finding N5 - [低] - Memory projection policy ratio 字段缺乏总和 ≤ 1.0 校验

- **入口/函数**: `MemoryProjectionPolicy.__post_init__`
- **文件(行号)**: `dayu/host/memory.py:652-682` (class definition), 未见 ratio 总和校验
- **输入场景**: 调用方传入 `raw_turn_context_ratio=0.5`, `history_pool_context_ratio=0.5`, `stable_layer_context_ratio=0.5`（总和 1.5）
- **实际分支**: 三个 ratio 分别通过各自的 floor/cap clamp，但总和未校验
- **预期行为**: 应在构造期校验 ratio 总和合理性（至少 warning），防止三项尺寸之和超过 context window 导致 memory snapshot 构造时出现意外的 budget 溢出
- **实际行为**: 当前默认值总和为 0.875（0.125 + 0.5 + 0.25），在正常范围内；但调用方可传入超过 1.0 的组合
- **直接证据**: `memory.py:652-682` — 三个 ratio 字段无交叉校验逻辑
- **影响**: 若调用方传入不合理 ratio 组合，memory snapshot 构造时 raw turn + history pool + stable layer 尺寸之和可能超过 context window，导致 budget enforcement 行为不可预测
- **建议改法和验证点**: 在 `__post_init__` 中添加 `raw_turn_context_ratio + history_pool_context_ratio + stable_layer_context_ratio <= 1.0` 的校验（或至少 warning 日志）
- **修复风险**: 低 — 当前默认值在合法范围内，只需添加防御性校验
- **严重程度**: 低

### Finding N6 - [信息] - `_DurableRunCancellationToken.is_cancelled()` 每次调用执行 durable read transaction

- **入口/函数**: `_DurableRunCancellationToken.is_cancelled()` → `cancel_reason()`
- **文件(行号)**: `dayu/host/dispatch.py:606-633`
- **输入场景**: Proactive compaction loop 中每次 attempt 迭代检查取消状态
- **实际分支**: `cancel_reason()` 调用 `self._transaction_runner.run_read(_ReadCompactionCancelReasonOperation(...))`，执行完整 durable read transaction
- **预期行为**: 这是有意设计 — proactive compaction 发生在 worker 启动前，没有 active worker registry，必须直接读取 durable Run 真源判断状态是否变更
- **实际行为**: 每次 `is_cancelled()` 调用产生一次 SQLite read transaction。在 `run_compaction_operation()` 的 attempt loop 中，这发生在每次 proposal attempt 开始时（`compaction_operation.py:130`）
- **直接证据**: `dispatch.py:622-633` — 每次调用执行 `run_read()`
- **影响**: 对 correctness 无影响（fail-closed 设计），但在高 attempt 数场景下会有可测量的 durable read 开销。当前 `max_compaction_attempts_per_operation` 默认值较小，实际影响有限
- **建议改法和验证点**: 已知设计权衡，无需修改。记录为 residual observation
- **修复风险**: N/A（有意设计）
- **严重程度**: 信息

---

## Architecture & Layer Boundary Validation

### Import Direction Check

| From | To | Allowed? | Evidence |
|---|---|---|---|
| `dayu.runtime` | `dayu.engine/host/service/fins/ui` | No (forbidden) | Grep 确认 zero matches |
| `dayu.engine` | `dayu.host/service/fins/ui` | No (forbidden) | Grep 确认 zero matches |
| `dayu.host` | `dayu.service/fins/ui` | No (forbidden) | Grep 确认 zero matches |
| `dayu.contracts` | `dayu.engine/host/runtime/service` | No (forbidden) | 已验证 contracts 只依赖 stdlib |
| `dayu.service` | `dayu.host/engine/runtime/contracts` | Yes | 正常装配方向 |

结论：**无反向 import，分层边界干净。**

### Protocol / Interface Coupling Check

- `ContextCompactor` Protocol 定义在 `dayu/host/compaction.py`，`LLMContextCompactor` 实现在 `dayu/host/llm_compaction.py` — 接口与实现分离，正确
- `ToolExecutor` Protocol 定义在 `dayu/contracts/tool_executor.py`，Engine 和 Host 各自依赖 Protocol 而非具体实现 — 正确
- `CancellationToken` Protocol 定义在 `dayu/contracts/cancellation.py`，`_HostCancellationToken` 和 `_DurableRunCancellationToken` 为 Host 内部实现 — 正确
- `ProcessLivenessProbe` Protocol 定义在 `dayu/host/recovery_process.py`，`StdlibPidLivenessProbe` 为默认实现 — 正确

### State Machine Validation

| State Machine | Source of Truth | Validated Paths |
|---|---|---|
| Run lifecycle (QUEUED→RUNNING→terminal) | `dayu/host/durable/state.py` RunRow.status + `run_transition.py` CAS mutations | 正常路径、cancel 路径、recovery 路径、compaction fail 路径 |
| Attempt lifecycle (STARTING→RUNNING→terminal) | `dayu/host/durable/state.py` AttemptRow.status | CAS guard 防止重复推进 |
| Dispatch record (PENDING→DISPATCHING→CANCELLED) | `dayu/host/durable/state.py` DispatchRecordRow.status | lane acquire 前后的 durable recheck |
| Compaction operation | `compaction_operation.py` attempt loop | proposal fail → retry → quality reject → retry → hard threshold → retry → max attempts exhausted |
| Session lifecycle (OPEN→CLOSED) | `dayu/host/durable/state.py` SessionRow.status | 完整 |

**关键状态机检查结果**:
- Terminal 状态不可回退：`_TERMINAL_RUN_STATUSES = frozenset((SUCCEEDED, FAILED, CANCELLED, LOST))` 在 `state.py:56-58` 定义，所有 transition helper 使用 CAS mutation 防止终态再推进
- 取消传播路径完整：`cancel_run` → command handle → `ActiveWorkerRegistry.cancel()` → `_HostCancellationToken.request_cancel()` + `LocalWorkerHandle.on_cancel()`
- Recovery 不重复派发：`StartupRecoveryScanner` 基于 `OrphanClassificationPolicy` 的 stale 阈值（30s）和 `ProcessLivenessProbe` 的 OS 级 pid 检查，避免误判 live worker 为 orphan

---

## Adversarial Failure Pass

| Attack Surface | Assessment |
|---|---|
| Auth / tenant isolation | N/A — 本项目是本地 Agent，无多租户 |
| Data loss / corruption | 低风险 — 所有状态变更通过 durable write transaction + CAS mutation；EventLog append 后写 state row；compaction 失败时 Run 被 fail_unstarted 而非静默丢失 |
| Rollback safety | 事务内 append EventLog + update state row 为原子操作；事务外操作（compaction proposal、worker execution）失败时通过 durable recheck 检测 stale state |
| Race conditions | Lane controller (SQLite-based) 提供 cross-process 互斥；dispatch record 通过 `mark_dispatching_after_recheck` 做 durable CAS；duplicate governance 通过 in-memory registry + idempotency store 双重防护 |
| Empty-state / null | Compaction request 构造时验证 `current_input_ref in material_source_refs`（compaction.py:880）；空 material pack 在 `CompactMaterialPack.__post_init__` 被拒绝 |
| Missing required params | 所有 dataclass 在 `__post_init__` 中执行 `_require_non_empty` / `_require_non_negative_int` 等校验 |
| Duplicate requests | Idempotency store (`dayu/host/durable/idempotency.py`) 用于 tool accept；`InMemoryRunScopedDuplicateGovernanceRegistry` 用于 run-scoped 去重 |
| Version skew / schema drift | Schema 在 `dayu/host/durable/schema.py` 集中定义，无 migration 文件 — residual risk |
| Observability gaps | 所有关键路径有结构化日志（`_LOGGER.warning` / `_LOGGER.error` / `_LOGGER.debug`），包含 `session_id`/`run_id`/`attempt_id` 等关联字段；compaction operation 有完整的 rejected attempt 诊断信息 |
| External protocol | Engine ↔ Provider 通过 `SSEParser` / `non_stream_parser` 归一化；未知 finish_reason 有 warning 日志（见 Finding 1） |
| Overcoupling | 层间通过 Protocol/ABC 解耦；Host 不依赖具体 Runner 实现；Engine 不依赖 Host state |
| Performance (static) | `_DurableRunCancellationToken` 每次 `is_cancelled()` 读 durable store（见 Finding 4）；drain loop idle 时多余的 `drain_once()` 调用（见 Finding 2） |

---

## Test Coverage Assessment

基于测试文件阅读（未逐行执行覆盖率工具），关键测试覆盖情况：

| Area | Test Files | Coverage Assessment |
|---|---|---|
| Compaction smoke | `test_public_compact_smoke.py` | 覆盖 public compact API |
| Compaction contract | `test_compaction_contract.py` | 覆盖 typed contract 校验 |
| Compaction operation | `test_compaction_operation.py` | 覆盖 attempt loop / quality check / merge |
| LLM compaction | `test_llm_compaction.py` | 覆盖 proposal parsing / error handling |
| Compact material | `test_compact_material.py` | 覆盖 material pack 构造 |
| Memory projection | `test_memory_projection.py` | 覆盖 memory snapshot 构造 |
| Memory repair | `test_memory_repair.py` | 覆盖 repair / catch-up 流程 |
| Recovery dispatch | `test_recovery_dispatch.py` | 覆盖 startup recovery scan |
| Recovery orphan | `test_recovery_orphan_classifier.py` | **新增 63 行** — 覆盖 orphan 分类 |
| Run attempt transitions | `test_run_attempt_transitions.py` | **新增 107 行** — 覆盖 transition CAS |
| Run input builder | `test_run_input_builder.py` | **大幅扩展 +725 行** — 覆盖 run input 构造 |
| Tool runtime | `test_toolruntime_accept_barrier.py` 等 | 覆盖 accept barrier / duplicate governance / truncation |
| Dispatch scheduler | `test_dispatch_scheduler.py` | 覆盖 dispatch drain / lane acquire |
| Lifecycle smoke | `test_public_lifecycle_smoke.py`, `test_public_open_host_multiturn_smoke.py` | 覆盖端到端 lifecycle |
| Conversation memory smoke | `utils/smoke_host_public_conversation_memory.py` | **新增 1537 行** — 端到端 smoke |
| Import boundaries | `test_import_boundary.py` (4 层) | 覆盖所有层的 import 方向 |
| Package exports | `test_package_exports.py` (3 层) | 覆盖 `__all__` 导出 |

### Uncovered / Under-covered Production Risks

1. **Proactive compaction + recovery interaction**: 若 proactive compaction 执行期间 Host crash，compaction request event 已写入但 compacted event 未写入，restart 后该 Run 的 input cursor 未变但 compaction request fact 存在 — recovery scan 如何处理此中间状态？未见专门测试覆盖此场景。

2. **SSE parser 畸形输入 fuzzing**: `SSEParser` 有 protocol error 处理，但未见针对畸形 SSE chunk（如跨 chunk 的 multi-byte UTF-8 截断、超长 data line、空 data field）的专门测试。

3. **Lane controller cross-process 竞争**: lane acquire 的 cross-process 安全性依赖 SQLite 文件锁，未见多进程并发 lane acquire 的专门测试。

4. **Compaction merge 边界**: `_merge_text_field_patch` 的 last-writer-wins 语义在 CLEAR 后 REPLACE 场景下证据链完整性，未见专门测试。

---

## README / Docs Consistency

- `README.md`: 作为用户手册，未检查（非此次 review focus）
- `dayu/host/README.md`: 描述 Host 架构、接口、状态机、事件流，与代码一致
- `dayu/engine/README.md`: 未单独存在（engine contracts 通过 docstring 自文档化）
- `dayu/config/README.md`: 描述配置结构，与 `config_loader.py` 一致
- `tests/README.md`: 描述测试分层与运行方式，与当前测试结构一致

---

### Finding N7 - [高] - test_memory_repair.py 仅 4 条测试，rebuild/catch-up 非空 batch 路径未覆盖

- **入口/函数**: `rebuild_conversation_memory_projection()` / `catch_up_conversation_memory_projection()`
- **文件(行号)**: `tests/host/test_memory_repair.py`（349 行，仅 4 条测试）
- **输入场景**: 生产环境中 memory projection rebuild 或 catch-up 遇到非空 EventLog batch
- **实际分支**: `test_rebuild_resets_projection_and_finishes_empty_batch` 强行注入空 batch（`scanned=0`）；`FakeProjectionRunner.queued_results` 在 rebuild 测试中硬编码为空 batch。**从未测试批内有实际事件可投影**
- **直接证据**: `test_memory_repair.py` — `FakeProjectionRunner.queued_results` 在 rebuild 测试中被设为 `[FakeProjectionRunResult(scanned=0, ...)]`；catch-up 测试的 `test_catchup_port_delegates_to_catch_up_function` 使用 `del max_event_sequence` 显式不验证参数传递
- **影响**: 若 rebuild/catch-up 在生产中遇到有事件可投影的场景，行为未经单元测试验证；projection 数据丢失风险
- **建议改法和验证点**: 补充 (1) rebuild 首 batch 非空聚合 (2) catch-up cursor 已追平 (3) catch-up failure 传播 (4) batch 恰好等于 batch_size
- **修复风险**: 低（纯测试补充）
- **严重程度**: 高

### Finding N8 - [高] - test_recovery_dispatch.py 仅 3 条测试，关键 recovery 状态分支缺失

- **入口/函数**: `StartupRecoveryScanner.scan()`
- **文件(行号)**: `tests/host/test_recovery_dispatch.py`（700 行，仅 3 条测试）
- **输入场景**: 正常运行的 dispatch（不应误杀）、STOPPING owner 仍 alive、STOPPED owner graceful close、recovery limit 超限
- **实际分支**: 当前 3 条测试全部使用 `_PidMissingProbe`（总是返回 pid missing），从未构造 pid alive 场景；缺失 NO_ACTION 正常路径、recovery limit 超限→LOST、STOPPING+alive→不接管 等关键分支
- **直接证据**: `test_recovery_dispatch.py` — 所有 seed 数据通过 `_PidMissingProbe` 注入；仅 `test_recovering_scan_creates_new_attempt_dispatch_and_wakes_scheduler`、`test_closes_and_loses_attempt_when_event_received_after_run_lost`、`test_orphan_closeout_reports_invalid_state_as_recovering_ready` 三条测试
- **影响**: recovery scanner 的误杀（false positive orphan）或漏诊（false negative）未被测试覆盖，生产事故风险
- **建议改法和验证点**: 至少补充 (1) NO_ACTION 正常路径 (2) recovery limit 超限→LOST (3) STOPPING+pid alive→不接管 (4) STOPPED owner→graceful close
- **修复风险**: 中（需构造不同 liveness 状态的数据）
- **严重程度**: 高

### Finding N9 - [高] - `HostRuntimeProfileConfig.store_root` 为死字段

- **入口/函数**: `HostRuntimeProfileConfig` → `_compose_options()`
- **文件(行号)**: `dayu/runtime/config_loader.py`
- **输入场景**: 用户在 `scene.toml` 中配置 `store_root` 字段
- **实际分支**: `store_root` 在 `HostRuntimeProfileConfig` 中被 parse 和 validate（`_validate_store_root` 检查路径合法性），但在 `_compose_options` 中从未被读取或映射到任何 `OpenHostOptions` 字段
- **预期行为**: 配置字段要么被消费，要么不应该存在
- **实际行为**: `store_root` 的值被静默忽略。同时 `scene.toml` 中 `sqlite.path` 与 `store_root` 存在路径前缀重复——两者都表达"存储根路径"语义，但只有 `sqlite.path` 实际生效
- **直接证据**: `config_loader.py` — `_validate_store_root` 执行校验但 `_compose_options` 不消费；Grep `store_root` 在 assembly 路径中无消费点
- **影响**: 用户可能配置了 `store_root` 但发现它不影响任何行为；配置界面存在误导
- **建议改法和验证点**: 要么让 `store_root` 映射到实际 `OpenHostOptions` 字段（如 `db_path` 的父目录），要么移除该字段。如果 `store_root` 是未来设计，应标注为 reserved
- **修复风险**: 低（移除死字段或连线到正确消费点）
- **严重程度**: 高

### Finding N10 - [高] - 工具发现 provider 无法接收任何配置

- **入口/函数**: `_tool_discovery_specs()` → `ToolsDiscoveryProviderSpec`
- **文件(行号)**: `dayu/runtime/tools_discovery.py`
- **输入场景**: 工具发现 provider 需要配置参数（如 API endpoint、认证信息）
- **实际分支**: `_tool_discovery_specs` 对所有 provider 都硬编码 `config={}`；`ToolDiscoveryProviderConfig` 数据类不接受 config 字段
- **预期行为**: 工具发现 provider 应能通过配置接收必要的初始化参数
- **实际行为**: 无论用户配置什么，工具发现 provider 的 config 始终为空 dict
- **直接证据**: `tools_discovery.py` — `_tool_discovery_specs` 中每个 spec 的 config 字段被硬编码为 `{}`
- **影响**: 需要配置的工具发现 provider（如远程工具注册中心）无法在当前框架下正常工作
- **建议改法和验证点**: 扩展 `ToolDiscoveryProviderConfig` 以支持 config 字段，并连线配置加载路径
- **修复风险**: 中（涉及配置 schema 变更）
- **严重程度**: 高

## Open Questions

1. Schema migration 策略：`dayu/host/durable/schema.py` 定义当前 schema，无 migration 文件。若未来 schema 变更，如何确保向前兼容？当前无 migration framework。

2. Compaction 与 memory projection 的 durability 边界：`CONTEXT_COMPACTED` event 写入后 memory projection catch-up 是 best-effort（通过 `catch_up_projection_best_effort`），若 catch-up 失败，下次 rebuild 可恢复 — 但 rebuild 的成本（全量 EventLog 扫描）在大 session 下可能显著。

---

## Residual Risk

1. **无 schema migration framework** — 若 durable schema 变更，需要手动 migration 或全量重建
2. **Proactive compaction crash recovery** — 中间状态（request written, compacted not written）的恢复路径未被测试覆盖
3. **大 session memory rebuild 成本** — `rebuild_conversation_memory_projection` 全量扫描 EventLog，在长会话（数千 events）下可能慢
4. **SSE parser 对未知 finish_reason 的 fallback 行为** — 当前以 STOP 兜底，但未来 provider 行为变更可能需同步更新映射表

---

## Areas Not Covered

- `dayu/fins/` 财报能力模块（未深度走读）
- `dayu/config/prompts/` prompt 模板目录
- `utils/` 下除 `smoke_host_public_conversation_memory.py` 外的辅助脚本
- Provider 认证/密钥管理
- 性能 profiling / benchmark
