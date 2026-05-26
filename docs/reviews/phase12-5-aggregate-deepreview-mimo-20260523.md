# Code Review

## Scope

- Mode: current changes (aggregate)
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Base: `09481cfe970273f645de26aeb9569092f6427769` (main)
- HEAD: `0dbcc5a`
- Output file: `docs/reviews/phase12-5-aggregate-deepreview-mimo-20260523.md`
- Included scope: Phase 12.5 Slice 1-7 全部 accepted commits，78 files changed，~12K lines added
- Design truth: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Parallel review coverage:
  - Subagent 1: evidence subsystem (`evidence.py`, `compaction_evidence.py`, `durable/schema.py`, `durable/memory.py`, `test_memory_projection.py`) -- 未发现实质性问题
  - Subagent 2: compaction pipeline (`compaction.py`, `compact_artifact.py`, `llm_compaction.py`) -- 3 findings
  - Subagent 3: RunInputBuilder / memory (`run_input.py`, `memory.py`, `test_run_input_builder.py`, `test_memory_projection.py`) -- 1 false positive (order analysis corrected)
  - Subagent 4: context governance / events (`context_governance.py`, `context_events.py`, related tests) -- 2 low-severity observations
  - Subagent 5: tests / config / assembly (all test files, `execution_profiles.json`, `host_assembly.py`, `dispatch.py`, `engine_ingest.py`, `tool_runtime.py`) -- 5 low-severity coverage gaps
- Not-covered areas: `llm_compaction.py` 后半段 JSON helper 函数（~400 行），由 subagent 2 部分覆盖

## Key Success Targets Validation

| 目标 | 状态 | 证据 |
|------|------|------|
| generic evidence_backed_facts | PASS | `EvidenceBackedFactCandidate` 只接受 accepted evidence refs，`evidence_kind` 枚举为 Host-neutral（`observed_value`, `quoted_statement`, `table_value`, `derived_from_evidence`） |
| accepted evidence envelope | PASS | `AcceptedEvidenceEnvelope` 完整定义 evidence_id、producer_event_ref、tool_name、tool_call_id、tool_query、result_ref、source_refs、locator_refs；`__post_init__` 校验所有必填字段和 sha256 digest |
| LLM/compact extraction candidates | PASS | `LLMContextCompactor.compact()` 返回 `CompactionCandidate`，包含 `evidence_backed_fact_candidates` 和 `minimum_preserve_item_candidates` |
| CONTEXT_COMPACTED materialization | PASS | `build_context_compacted_payload()` 写入 episode_summary_candidate、pinned_state_patch_candidate、evidence_backed_fact_candidates、minimum_preserve_item_candidates、preserved_fact_refs、quality_check_result |
| no tool-result-alone facts | PASS | `test_tool_result_accepted_does_not_project_evidence_backed_fact` 验证 TOOL_RESULT_ACCEPTED 只推进 cursor 不生成 fact |
| recent raw continuity | PASS | `_memory_raw_turn_messages()` 保持 RAW_USER_TURN / RAW_ASSISTANT_TURN / ASSISTANT_CONCLUSION 连续性 |
| minimum preserve | PASS | `MinimumPreserveItemCandidate` 只来自 compact accepted output，不产生 evidence_backed_fact |
| RunInputBuilder rendering | PASS | `_memory_evidence_backed_fact_message()` 渲染 `claim_text` + `evidence_refs`；stable blocks 按 pinned_state > evidence_backed_facts > working_assumptions 优先级；budget 超限时产生 diagnostic 而非 crash |

## Findings

### 1-未修复-中-_NeverCancelledToken 阻止 session close 取消进行中的 compaction LLM 调用

- **入口/函数**: `LLMContextCompactor.compact()` -> `_run_agent_request()`
- **文件(行号)**: `dayu/host/llm_compaction.py` (行 112-138, 249-260)
- **输入场景**: Host session 已关闭或 Run 已被取消，但 compaction LLM 调用仍在进行中
- **实际分支**: `_NeverCancelledToken.is_cancelled()` 始终返回 `False`，`asyncio.wait_for` 只受 timeout 约束
- **预期行为**: 设计文档要求 "stale / cancelled / session closed / execution replaced / cursor mismatch 不是可 repair 错误；Host 必须丢弃 stale proposal"
- **实际行为**: Host 在 LLM 调用完成后才检查 stale 状态；进行中的 LLM 调用无法被取消，持续占用 Engine runner 资源直到自然完成或超时
- **直接证据**: `llm_compaction.py:115` `_NeverCancelledToken.is_cancelled()` 返回 `False`；`llm_compaction.py:260` `asyncio.wait_for` 只有 timeout 无 cancellation
- **影响**: 资源浪费；session 关闭后 compaction LLM 调用仍占用 runner slot 直到 timeout
- **建议改法和验证点**: 将 Host 级 `CancellationToken` 透传给 `_run_agent_request`；`_NeverCancelledToken` 仅作为 fallback。验证 session close 时 compaction 调用被正确中断
- **修复风险（低/中/高）**: 中 -- 需要修改 `LLMContextCompactor.__init__` 接收 cancellation token，或在 `compact()` 签名中增加 token 参数
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-JSON 序列化 helper 跨三个模块重复定义

- **入口/函数**: `_string_list_json`, `_range_list_json`, `_fact_candidate_list_json`, `_minimum_preserve_candidate_list_json`, `_evidence_list_json`
- **文件(行号)**: `dayu/host/compaction.py` (行 1410-1477), `dayu/host/compact_artifact.py` (行 314-367), `dayu/host/context_events.py` (行 484-556)
- **输入场景**: 任何调用上述 helper 的路径
- **实际分支**: 每个模块各自定义同名私有函数
- **预期行为**: 架构硬约束要求 "数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"
- **实际行为**: 5 个 JSON 序列化 helper 在 3 个模块中各有一份拷贝，逻辑完全相同
- **直接证据**: `grep` 确认每个函数在 3 个文件中各有定义；函数体相同
- **影响**: 维护成本；修改序列化逻辑需要同步 3 处
- **建议改法和验证点**: 将这些 helper 抽取到 `dayu/host/_compaction_json.py` 或提升为 `compaction.py` 的公共函数，供 `compact_artifact.py` 和 `context_events.py` 导入。验证所有现有测试通过
- **修复风险（低/中/高）**: 低 -- 纯重命名/移动，无行为变更
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-compaction operation diagnostic ref 未脱敏异常消息

- **入口/函数**: `_exception_diagnostic_suffix`
- **文件(行号)**: `dayu/host/compaction_operation.py` (行 263)
- **输入场景**: compaction proposal 抛出包含敏感信息的异常
- **实际分支**: `str(exc)` 原文进入 diagnostic ref，写入 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload
- **预期行为**: 日志和 durable payload 中的异常消息应脱敏
- **实际行为**: `_log_rejected_attempt` 使用 `_safe_exception_message` 脱敏后写日志，但 durable payload 中的 diagnostic ref 保留原始异常消息
- **直接证据**: `compaction_operation.py:263` `_exception_diagnostic_suffix` 使用 `str(exc)`；对比 `_log_rejected_attempt` 使用 `_safe_exception_message`
- **影响**: 低概率泄露 provider 错误中的敏感信息到 durable EventLog
- **建议改法和验证点**: 对 `_exception_diagnostic_suffix` 复用 `_safe_exception_message` 的脱敏+截断逻辑
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

以下为已确认但未阻塞 merge 的剩余风险，按 owner 分配：

| # | 风险 | Owner | 说明 |
|---|------|-------|------|
| R1 | execution_profiles.json 四个 profile 的 memory_projection_policy 完全相同 | config owner | 256k 和 1m 窗口使用相同绝对值 cap，需确认是否符合 design.md ratio-first 自适应意图 |
| R2 | test_config_loader 未验证 compactor_baseline 完整字段 | test owner | 只断言了 `max_evidence_backed_facts == 256`，缺少 `compactor_baseline.model_id` 等字段断言 |
| R3 | test_host_assembly 未验证 compactor runner spec 端到端映射 | test owner | 缺少 `compactor_runner_spec.model` 断言 |
| R4 | test_memory_projection 缺少跨 session isolation 测试 | test owner | 同 consumer 不同 session 的 snapshot 互不污染未验证 |
| R5 | test_compaction_contract 未测试 BudgetEstimate 边界值 | test owner | `hard_threshold_tokens == 0`、`estimated_input_tokens < 0` 等边界未覆盖 |
| R6 | public no-compaction smoke 已存在 | -- | `tests/host/test_public_compact_smoke.py` 已验证 compaction 端到端路径 |
| R7 | start_event_sequence=1 evidence read 已验证正确 | -- | `compaction_evidence.py:65` 正确拒绝 `<=0`，`read_events_after(0)` 正确返回 sequence >= 1 的事件 |
| R8 | durable item-kind query 已验证 | -- | `_validate_snapshot_item_kinds` 在 `durable/memory.py` 中正确校验所有 item kind 合法性 |

## Conclusion

**PASS** -- Phase 12.5 Conversation Memory Optimization 的 Slice 1-7 实现通过聚合深度 review。

核心成功目标全部达成：generic evidence_backed_facts 契约完整、accepted evidence envelope 类型严格、LLM/compact extraction candidates 路径正确、CONTEXT_COMPACTED materialization 字段完整、tool-result-alone facts 已被测试阻止、recent raw continuity 和 minimum preserve 行为正确、RunInputBuilder rendering 包含 claim_text + evidence_refs。

Pyright 0 errors。78 files changed，~12K lines added，类型严格（无 Any、无 object）。

3 个 findings（1 中、2 低）和 5 个 residual risks 均不阻塞 merge，可作为后续改进项跟踪。
