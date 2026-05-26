# Aggregate Deepreview: Conversation Memory Optimize

## Scope

- **Mode**: Current Changes (aggregate after all accepted local slices)
- **Branch**: feat/phase-12-5-conversation-memory-optimize
- **Base**: main
- **Output file**: docs/reviews/gateflow-aggregate-deepreview-conversation-memory-optimize-mimo-20260526.md
- **Included scope**: Full branch diff (main...HEAD), 277 files, ~44870 additions
- **Excluded scope**: None
- **Parallel review coverage**:
  - Dispatch/scheduler/close/cancel: dispatch.py, recovery_process.py, run_transition.py, api.py (subagent completed)
  - Memory projection/context: memory.py, llm_compaction.py, context_events.py, durable/memory.py, durable/schema.py (subagent completed)
  - ToolRuntime/engine ingest: tool_runtime.py, engine_ingest.py, evidence.py, opaque_ref.py, payload_resolution.py (subagent completed)
  - Tests adequacy: all test files and smoke (subagent completed)
  - Compaction/material pipeline: compaction.py, compact_material.py, compaction_operation.py, compaction_evidence.py, compact_payload.py, context_governance.py, compact_artifact.py (subagent did not complete in time)
  - Service layer: host_assembly.py (main reviewer direct analysis)
  - Architecture boundaries: import direction checks across all changed files (main reviewer)

## Verdict

**PASS**

未发现阻塞性缺陷。所有已完成的专项 review 均未发现 critical 或 high severity 问题。

## Blocking Findings

未发现。

## Non-blocking Findings

### N1-低-OpaqueEvidenceRef 校验未强制 Host-neutral kind allowlist

- **入口/函数**: `OpaqueEvidenceRef.__post_init__`
- **文件(行号)**: `dayu/host/evidence.py:78-87`
- **输入场景**: 任意非空 `ref_kind` 字符串
- **实际分支**: `_require_non_empty_text` 校验通过
- **预期行为**: `OpaqueEvidenceRef` 作为 Host 不解析语义的 evidence ref，`ref_kind` 应受 `opaque_ref.py` 的 `_HOST_NEUTRAL_OPAQUE_REF_KINDS` 约束
- **实际行为**: `__post_init__` 只校验非空文本，不调用 `validate_host_neutral_opaque_ref_kind`
- **直接证据**: `evidence.py:85` 使用 `_require_non_empty_text`，`opaque_ref.py:10-21` 定义了 allowlist 但未被 `OpaqueEvidenceRef` 引用
- **影响**: 结构性弱校验。当前所有调用方构造有效 kind，不会触发运行时错误；但未来新调用方可能传入非法 kind 而不被拒
- **建议改法和验证点**: 在 `OpaqueEvidenceRef.__post_init__` 中增加 `validate_host_neutral_opaque_ref_kind(self.ref_kind)` 调用；或确认 evidence envelope 层有意放宽校验并在 docstring 说明
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### N2-低-_propagate_active_worker_cancel 日志缺少异常详情

- **入口/函数**: `_propagate_active_worker_cancel`
- **文件(行号)**: `dayu/host/dispatch.py:478-489`
- **输入场景**: `on_cancel` 抛出异常
- **实际分支**: `except Exception` 捕获后 `_LOGGER.warning`
- **预期行为**: 生产环境取消失败需要足够上下文调试
- **实际行为**: warning 日志只记录 `exc.__class__.__name__`，不包含 `str(exc)` 或 `exc_info`
- **直接证据**: `dispatch.py:486` 格式串只有 `error_type=%s`，无 `exc_info=True`
- **影响**: 生产调试取消失败时信息不足
- **建议改法和验证点**: 添加 `exc_info=True` 或在格式串中包含 `str(exc)`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### N3-低-cancel_all 快照-迭代窗口

- **入口/函数**: `ActiveWorkerRegistry.cancel_all`
- **文件(行号)**: `dayu/host/dispatch.py:446-461`
- **输入场景**: `cancel_all` 执行期间新 worker 注册
- **实际分支**: 快照在锁内完成，传播在锁外执行
- **预期行为**: 所有 active worker 收到取消
- **实际行为**: 快照后注册的 worker 可能错过 cancel_all 的传播
- **直接证据**: `dispatch.py:447-458` 锁内快照，`dispatch.py:459-460` 锁外传播
- **影响**: 已被 `HostDispatchScheduler.close()` 的 per-task cancel 兜底（`dispatch.py:1771-1773`），不会导致 worker 泄漏
- **建议改法和验证点**: 当前设计已通过 defense-in-depth 兜底，无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Residual Risks / Deferred Tracking

### R1-DB schema 不兼容升级

`durable/schema.py` 的 `TABLE_HOST_MEMORY_ITEMS` CHECK 约束从 `verified_fact` 改为 `evidence_backed_fact`，从 `tool_verified` 改为 `evidence_backed`。旧数据库中的行违反新 CHECK 约束。`durable/memory.py:941-972` 在读取时有 defense-in-depth 拒绝旧值。这符合项目"全新 schema 起库"策略，但用户需知旧库不可直接使用。

### R2-Stale doc reference

`docs/host/runtime-assembly-followup-discussion.md` 第 200、215 行仍引用 `max_verified_facts`。这是讨论文档，不在 README 同步触发规则范围内，属于 cosmetic。

### R3-compact_material.py 模块体量

`dayu/host/compact_material.py` 新增 1904 行。虽然当前 review 未发现阻塞性问题（数据类 + builder 模式），但该模块体量较大，后续维护需关注职责收敛。

## Validation Reviewed

1. **架构边界**: 所有 host 内部模块未反向 import service/ui 层。`AgentRunRequest` 从 `dayu.engine.contracts.agent_run` 导入，遵循已有的 `dayu.engine.contracts.engine_events` 模式（contracts 层可被 host 引用）。`ToolBundleSourceRef` 从 `dayu.host` 移至 `dayu.contracts`，旧 re-export 正确移除。
2. **状态机安全**: `_DurableRunCancellationToken` 每次调用独立读事务，fail-closed 处理 durable 不可用。Run terminal/STOPPING/recovery 路径完整。`close()` 顺序正确：mark stopping → cancel background tasks → cancel_all → cancel active tasks → close lane → mark stopped。
3. **取消传播**: `cancel` → `on_cancel` 重命名完整覆盖 Protocol、实现、调用方。语义从"主动取消"变为"Host 已发出取消信号后通知"，cancellation token 是主取消通道。
4. **Memory 正确性**: `EvidenceBackedFactView` 强制 `HOST_PROJECTION` producer、非空 evidence_refs、claim_text 长度限制。DB schema CHECK 约束和读取时 defense-in-depth 双重拒绝旧值。旧 payload 字段（`proposed_verified_fact_refs`、`tool_fact_refs` 等）在 `context_events.py` 被显式拒绝。
5. **Compaction pipeline**: 多 pass compaction 正确传播 cancellation token。Quality check 新增 evidence-backed fact、minimum preserve item、open questions 校验。Context governance 完整校验 candidate 的 evidence refs、fact candidates、pinned patch。
6. **ToolRuntime hot/cold payload**: 小 payload inline，大 payload 写 SQLite + EventLog 引用。`_candidate_payload_descriptor_exists` 新校验不破坏 REUSE kind。`raw_tool_outcome` 对 COMPLETED/FAILED/CANCELLED/GOVERNED_ERROR 必填。
7. **Engine ingest**: `run.current_attempt_id != envelope.attempt_id` 校验正确拒绝旧 attempt 事件。Reactive compaction 冻结 material blocks 在 closeout 前捕获。
8. **Service 层**: Compactor scene 通过 `prepare_scene` 装配，system prompt 要求恰好一个 fragment，Agent policy 所有字段必填。Prompt asset 路径有逃逸根目录防护。
9. **Schema 变更**: 全新 schema，无兼容读取。Config loader 使用 `_require_exact_fields` 拒绝旧 key `max_verified_facts`（测试 `test_config_loader.py:585` 验证）。
10. **测试覆盖**: dispatch/scheduler close/cancel/recovery 测试完整。Multi-pass compaction、cancellation token、quality check、material pack builder、memory projection 均有测试。

## Areas Not Fully Covered

1. **Compaction/material pipeline 专项深挖未完成**: `compaction.py`、`compact_material.py`（1904 行）、`compaction_operation.py`、`compaction_evidence.py`、`compact_payload.py`、`context_governance.py`、`compact_artifact.py` 的专项 subagent 未在时限内返回。这些文件已被主 reviewer 通过 diff 和关键路径走读部分覆盖（quality check 逻辑、multi-pass 机制、material pack builder 验证），但未做完整的逐行走读。

2. **测试边界条件**: 以下测试间隙由测试 subagent 识别但未验证是否为真实回归风险：
   - 空 material blocks 输入的 segment selection 边界
   - 多个 stable_input block 的 compactor prompt 渲染
   - Memory repair 异常传播（rebuild/catch-up 当 projection runner 抛出异常）
   - 多个 simultaneous quality rejection reasons
   - `FinishReason.CONTENT_FILTER` 在 LLM compactor 中的处理
