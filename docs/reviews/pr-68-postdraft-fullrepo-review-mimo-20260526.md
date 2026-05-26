# Code Review -- PR 68 Post-Draft Full Repository

## Scope

- Mode: All Repository (post draft-PR-pass)
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- PR URL: https://github.com/noho/dayu-agent-r/pull/68
- Review date: 2026-05-26
- Output file: `docs/reviews/pr-68-postdraft-fullrepo-review-mimo-20260526.md`
- Included scope: Entire repository at HEAD (283 files changed, +45645/-2143 lines)
- Excluded scope: `.venv/`, `__pycache__/`, generated files
- Parallel review coverage: 5 subagents covering Host lifecycle/recovery, Conversation memory/compaction, Engine runner/SSE, Service/runtime/import boundaries, Tests/docs consistency

## Verdict: FAIL

发现 1 个 blocking finding：`test_scene_assets_migration` 测试因 PR 68 新增 smoke scenes 未更新 allowlist 而 consistently failing。生产代码 review 未发现 blocking defects。

## Findings

### B1 - [MEDIUM] - test_scene_assets_migration 测试失败：smoke scene agent_policy allowlist 未更新

- **入口/函数**: `test_scene_manifest_agent_policy_carries_old_max_iterations_only`
- **文件(行号)**: `tests/runtime/test_scene_assets_migration.py:271`
- **输入场景**: 测试遍历所有 scene manifests，校验非 compactor 场景的 `agent_policy` 配置。
- **实际分支**: PR 68 新增的 `smoke_host_public_conversation_memory` 和 `smoke_host_public_multiturn` scenes 声明了 `agent_policy`（`allow_tool_calls: True, max_iterations: 20`），但测试 allowlist 未包含这些 scenes。
- **预期行为**: 测试 allowlist 应包含所有非 compactor 且带 agent_policy 的 scenes，或 smoke scenes 不应声明 agent_policy（因为 `allow_tool_calls: True` 是默认行为）。
- **实际行为**: `assert agent_policy is None` 失败，因为 smoke scenes 的 `agent_policy` 不为 None。
- **直接证据**: `tests/runtime/test_scene_assets_migration.py:271` (`assert agent_policy is None`), scene manifests 在 `workspace/scenes/smoke_host_public_conversation_memory/` 和 `workspace/scenes/smoke_host_public_multiturn/` 中声明了 `agent_policy`。
- **影响**: 测试 consistently failing，阻塞 CI。
- **建议改法**: 在测试中将 smoke scenes 加入 `_EXPECTED_AGENT_POLICY_SCENES` allowlist，或从 smoke scene manifests 中移除 `agent_policy`（因为 `allow_tool_calls: True` 是默认值）。
- **修复风险**: 低。纯测试维护。
- **严重程度**: MEDIUM（blocking CI，但不影响生产代码正确性）

以下为 non-blocking residuals，按严重程度排序：

### R1 - [LOW] - Scheduler close 不 drain 剩余 dispatch queue

- **入口/函数**: `HostDispatchScheduler.close()`
- **文件(行号)**: `dispatch.py:1741-1780`
- **输入场景**: Service 调用 `host.close()`，dispatch queue 中仍有待处理的 `PendingDispatchRecord`。
- **实际分支**: `self._closed = True` 后 drain task 被 cancel，queue 中剩余记录被丢弃。
- **预期行为**: close 时应 drain 剩余 queue 或标记 dispatch record CANCELLED。
- **实际行为**: 对应 Run 停留在 RUNNING + STARTING Attempt + PENDING 状态，restart 后由 recovery scan 处理。
- **直接证据**: `dispatch.py:1749` (`self._closed = True`), `dispatch.py:1762-1765` (drain task cancel), `dispatch.py:1902-1951` (`while not self._closed` 退出条件)
- **影响**: 正常 shutdown 后产生临时僵尸 Run，restart 后 recovery 将其转为 LOST/RECOVERING。
- **建议改法**: close 时在 cancel tasks 前先 drain queue（设置 close 超时）。
- **修复风险**: 低
- **严重程度**: LOW

### R2 - [LOW] - dispatch record 初始 owner_host_instance_id=NULL 的脆弱窗口

- **入口/函数**: `HostDispatchScheduler._start_governed_in_transaction`
- **文件(行号)**: `dispatch.py:1260`
- **输入场景**: accepted/queued Run 进入 pre-start governance 后创建 dispatch record。
- **实际分支**: `owner_host_instance_id=None` 传入 `StartGovernedRunInput`。
- **预期行为**: dispatch record 创建时即携带 owner Host instance id。
- **实际行为**: `owner_host_instance_id=None` 导致若进程在事务提交后、drain loop 拾取前崩溃，recovery scan 返回 `OrphanProofInconclusive`，不做 closeout。
- **直接证据**: `dispatch.py:1260`, `recovery.py:289-293`, `recovery_process.py:192-199`
- **影响**: 极窄窗口（事务提交到 drain loop 拾取之间）内的 crash 会导致 Run 永久卡住。recovery 路径已正确设置 owner（`recovery.py:434`），此问题仅影响标准 dispatch 路径。
- **建议改法**: 将 `owner_host_instance_id=None` 改为 `owner_host_instance_id=self._host_instance_identity.host_instance_id`。
- **修复风险**: 低。两者当前值相同（`dispatch.py:3571`），纯属 redirect。
- **严重程度**: LOW

### R3 - [LOW] - owner_host_instance_id 使用 host_handle_id 而非 host_instance_id

- **入口/函数**: `HostDispatchScheduler._mark_waiting_for_lane` / `_mark_dispatching_after_recheck`
- **文件(行号)**: `dispatch.py:2114`, `dispatch.py:2171`
- **输入场景**: dispatch drain 路径将 PENDING dispatch record 升级为 WAITING_FOR_LANE 或 DISPATCHING。
- **实际分支**: `owner_host_instance_id=self._host_handle_id`
- **预期行为**: `owner_host_instance_id=self._host_instance_identity.host_instance_id`
- **实际行为**: 当前因为 `_new_dispatch_host_instance_identity` 用 `host_handle_id` 作为 `host_instance_id`（`dispatch.py:3571`），两者恰好相等，不产生 FK 冲突。
- **直接证据**: `dispatch.py:2114`, `dispatch.py:2171`, `dispatch.py:3571`
- **影响**: fragile 间接耦合。一旦 `host_instance_id` 改为不同值，recovery scan 将无法找到 owner。
- **建议改法**: 替换为 `self._host_instance_identity.host_instance_id`。
- **修复风险**: 低
- **严重程度**: LOW

### R4 - [LOW] - WAITING 状态 Run 在 startup recovery 中仅做 diagnostic

- **入口/函数**: `StartupRecoveryScanner._classify_run`
- **文件(行号)**: `recovery.py:188-195`
- **输入场景**: 启动时存在 WAITING 状态的 Run。
- **实际分支**: 返回 `WAITING_DIAGNOSTIC_ONLY`，不进行 closeout/recovery/cancel。
- **预期行为**: 若 wait record 已超时/过期，应标记为 LOST 或 FAILED。
- **实际行为**: 不做任何处理，依赖外部 `resolve_wait`。
- **直接证据**: `recovery.py:188-195`
- **影响**: 超时的 WAITING Run 可能永久卡住。
- **建议改法**: 检查 wait record 的 `deadline_at` / `expires_at`，对已过期记录做 LOST 收口。
- **修复风险**: 低
- **严重程度**: LOW

### R5 - [LOW] - _ChunkAggregationKind 未使用枚举

- **文件(行号)**: `_types.py:195-202`
- **直接证据**: grep 全仓无引用。
- **影响**: 死代码。
- **建议改法**: 删除。
- **修复风险**: 无
- **严重程度**: LOW

### R6 - [LOW] - test_memory_repair.py 仅 4 条测试，覆盖不足

- **文件(行号)**: `tests/host/test_memory_repair.py`（349 行，4 条测试）
- **缺失路径**: rebuild 首 batch 非空聚合、catch-up cursor 已追平、batch 恰好等于 batch_size、rebuild failure 传播。
- **影响**: memory projection rebuild/catch-up 的关键路径在测试中未验证。
- **建议改法**: 补充至少 4 条测试覆盖上述路径。
- **修复风险**: 低
- **严重程度**: LOW

### R7 - [LOW] - test_recovery_dispatch.py 仅 3 条测试

注：subagent 报告 `test_lane_multiprocess.py` 3 个测试失败，但主 reviewer 验证时 3 个全部通过（macOS Darwin 24.6.0）。该 finding 不成立。

### R8 - [LOW] - compaction_evidence.py 无 dedicated 测试

- **文件(行号)**: `dayu/host/compaction_evidence.py`（528 行，~15 个函数）
- **直接证据**: 无 `tests/host/test_compaction_evidence.py`。公共函数由 `test_compaction_operation.py` 和 `test_run_input_builder.py` 间接覆盖，但内部 validation helpers（`_reject_result_preview`, `_readable_query_text`, `_deduplicate_evidence_materials` 等）缺 direct unit coverage。
- **影响**: 形态异常的 EventLog row 到达这些 helpers 时可能产生静默错误结果。
- **建议改法**: 补充 dedicated 测试覆盖 validation/canonicalization 路径。
- **修复风险**: 低
- **严重程度**: LOW

- **文件(行号)**: `tests/host/test_recovery_dispatch.py`（700 行，3 条测试）
- **缺失路径**: NO_ACTION 正常路径、recovery limit 超限 -> LOST、STOPPING + pid alive -> 不接管、STOPPED owner -> graceful close。
- **影响**: recovery scanner 的误杀/漏诊路径未被大量测试覆盖。
- **建议改法**: 补充至少 4 条测试。
- **修复风险**: 低
- **严重程度**: LOW

## Open Questions

无。

## Residual Risk

### 已覆盖区域

以下区域由并行 subagents 完整走读，未发现 blocking findings：

1. **Host lifecycle & recovery**（subagent 1）：scheduler close/cancel、recovery scan、orphan proof、event/outbox atomicity、CAS-based state transitions、cancel propagation 路径。确认所有状态迁移使用 CAS 保护，事件写入与状态变更在同一事务内原子完成。

2. **Conversation memory & compaction**（subagent 2）：compaction state machine（bounded by max_attempts）、material/evidence consistency（quality check 强制）、LLM compaction failure handling（timeout/empty/非 JSON/schema invalid/truncated 全覆盖）、memory projection（checkpoint-guaranteed rebuild）、ToolRuntime hot/cold payloads（transactionally consistent）、context budget enforcement（proactive hard threshold gate, reactive path intentionally skipped）。

3. **Engine runner & SSE**（subagent 3）：SSE parsing（UTF-8 incremental decoder, cross-chunk boundary tested）、tool call aggregation（synthetic index isolation, defensive finalization）、cancellation propagation（4 blocking boundaries covered, resource cleanup guaranteed）、error classification（exhaustive with assert_never）、retry policy（no mid-stream retry, cancellation-aware sleep）。

4. **Service/runtime & import boundaries**（subagent 4）：import boundaries 正确执行（dayu.runtime 不 import 上层）、config loading fail-fast（严格类型校验）、assembly order dependency-correct、package exports 锁定。

5. **Tests & docs**（subagent 5）：README 一致性检查、包导出锁定、import 边界测试、smoke 脚本覆盖。

### 主 reviewer 直接审查区域

- `dayu/contracts/`：CancellationToken、ToolCallRequest、BatchToolExecutionContext、ToolExecutor、ToolExecutionOutcome 等公共契约，Protocol 边界清晰，类型校验完备。
- `dayu/engine/agent.py`：Agent 状态机主循环，iteration/cancellation/tool-execution/continuation 路径，终态收口正确。
- `dayu/host/open_host.py`：Host opener 生命周期，close 序列（scheduler -> projection flush -> durable store），HostClosedError gate。
- `dayu/host/dispatch.py`：dispatch scheduler drain loop、active worker registry、HostCancellationToken、DurableRunCancellationToken。
- `dayu/host/llm_compaction.py`：LLM compactor 完整路径（prompt 构造 -> Engine run -> JSON 解析 -> candidate 构建 -> budget 估算）。
- `dayu/host/compaction_operation.py`：multi-pass compaction operation 循环、quality check、merge logic、budget gate。

### 未覆盖区域

- `dayu/host/durable/` 内部实现（schema.py, state.py, transaction.py, connection.py）：仅通过 subagent 间接审查，未逐行走读。
- `dayu/ui/` 和 `dayu/fins/`：不在本 PR 范围内，未审查。
- `workspace/` 和 `utils/`：辅助脚本，无覆盖率要求。

### 验证状态

- **pyright**: 0 errors, 0 warnings, 0 informations
- **tests**: 1089 passed, 2 failed:
  - `test_scene_manifest_agent_policy_carries_old_max_iterations_only` — PR 68 新增 smoke scenes 未更新测试 allowlist（blocking）
  - `test_gemini_public_real_runner_two_turn_path` — 外部网络依赖 `generativelanguage.googleapis.com` 不可达（非代码缺陷）
- **git status**: clean（无未提交变更）
