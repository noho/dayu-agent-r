# WU-CM-01 PR Review — AgentMiMo

**PR**: https://github.com/noho/dayu-agent-r/pull/116
**Branch**: `phaseflow/wu-cm-01` -> `main`
**Review date**: 2026-06-04
**Reviewer**: AgentMiMo
**Scope**: PR diff (160 files, ~36k 行变更)

## Verdict

**PASS**

PR 整体质量良好，无 blocking findings。vNext Conversation Memory 五类 session memory 模型（Trace、Evidence / Fact、Session Summary、Answer Anchor、Forward Intent）已正确落地，与 Host 设计真源 section 24 对齐。所有验证命令通过。

## Findings

### F-1: memory.py 重复常量定义 `_PAYLOAD_FIELD_DISPLAY_TEXT`

- **严重度**: LOW
- **文件**: `dayu/host/memory.py:71` 和 `dayu/host/memory.py:84`
- **证据**: `_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"` 在同一模块内定义两次。第二个定义 shadow 第一个。
- **影响**: 无功能影响（值相同），但违反代码整洁。
- **建议裁决**: 可在后续 fix gate 中清理重复行。

### F-2: memory.py 和 context_fallback.py 缺少 `__all__`

- **严重度**: LOW
- **文件**: `dayu/host/memory.py`、`dayu/host/context_fallback.py`
- **证据**: PR 中 `compaction.py`、`compact_material.py`、`compact_artifact.py`、`compact_payload.py`、`compaction_evidence.py`、`compaction_operation.py`、`context_events.py`、`run_input.py`、`llm_compaction.py`、`context_governance.py` 均有 `__all__`。`memory.py` 有 145 个 public symbols 但无 `__all__`，`context_fallback.py` 有 32 个 public symbols 但无 `__all__`。
- **影响**: 所有 public name 隐式导出，可能意外暴露内部 helper。模块间导出风格不一致。
- **建议裁决**: 非阻塞，可在后续 fix gate 补齐。

### F-3: compact_material.py slice1 诊断常量命名

- **严重度**: INFO
- **文件**: `dayu/host/compact_material.py:57-62`
- **证据**: `_INITIAL_POLICY_DIGEST = "slice1-initial-policy"`、`_INITIAL_REASON_CURRENT = "slice1_current_anchor"` 等常量使用实现切片命名（`slice1`），而非语义命名。这些常量是 module-private，不进入外部接口。
- **影响**: 无功能影响。诊断字符串内含实现切片引用，若未来 slice 概念消失可能产生误导，但不影响运行时行为。
- **建议裁决**: 可忽略或在后续重构中重命名。

## 验证命令与结果

| 命令 | 结果 |
|---|---|
| `pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_durable_concurrency_matrix.py tests/host/test_memory_repair.py -q` | 63 passed |
| `pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_engine_ingest_mapping.py -q` | 168 passed |
| `pytest tests/host/test_admission_queue.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py -q` | 59 passed |
| `pytest tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q` | 67 passed |
| `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q` | 10 passed, 1 skipped |
| `pytest tests/host/test_public_contracts.py tests/host/test_public_tool_wiring_smoke.py -q` | 42 passed |
| `pytest tests/host -q` | 1100 passed, 1 skipped, 5 deselected |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `python -m json.tool dayu/config/execution_profiles.json` | JSON valid |
| `git diff --check` | 无输出（无 whitespace 错误） |

## Design Source Alignment

### Host 设计真源 section 24 (Conversation Memory) 对齐

| 设计要求 | 实现状态 |
|---|---|
| 五类 session memory：Trace、Evidence / Fact、Session Summary、Answer Anchor、Forward Intent | ✅ `ConversationMemorySnapshotVNext` 包含 `trace_memory`、`evidence_fact_memory`、`session_summary_memory`、`answer_anchor_memory`、`forward_intent_memory` |
| Memory 只消费 committed canonical EventLog facts 与 accepted compact projection | ✅ `ConversationMemoryProjectionConsumer` 只消费 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`、`CONTEXT_COMPACTED` |
| vNext Compact I/O Contract: `ConversationCompactInputVNext` / `ConversationCompactOutputVNext` | ✅ schema version、字段、source label 规则均与设计对齐 |
| current_input_anchor readable but not citable | ✅ `check_conversation_compact_output_vnext` 拒绝引用 `CURRENT_INPUT_ANCHOR` 的 label |
| prompt-local label 不携带 durable identity | ✅ label 为确定性短 handle（C1、T1、E1 等），Host 内部维护 provenance map |
| candidate source label 规则：未知 label、跨 section label、stale label、缺 source label 均为 invalid | ✅ `CompactQualityIssueVNext` 枚举覆盖所有拒绝原因 |
| compact 后预算由 Host 估算，不由 LLM 输出 | ✅ `_budget_after_compact_candidate` 在 `compaction_operation.py` 中独立计算 |
| compact 不改写历史 EventLog facts | ✅ compact 只写 `CONTEXT_COMPACTED` canonical event |
| memory projection 是可重建 read model | ✅ `ConversationMemoryProjectionConsumer` 支持 checkpoint、rebuild、catch-up |

### 分层边界

| 检查项 | 结果 |
|---|---|
| `dayu.runtime` 不 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` | ✅ 无违规 |
| Host 不承载财报业务语义 | ✅ |
| Engine 不读取 Host durable store | ✅ |
| Context Governance 不直接写 memory snapshot | ✅ memory projection 由 `ConversationMemoryProjectionConsumer` 独立消费 |
| Dispatch / sink / tool runtime 不直接写 Run / Attempt / EventLog | ✅ |

### README Sync

| README | 触发条件 | 更新状态 |
|---|---|---|
| `README.md` | 项目定位、smoke 脚本变更 | ✅ 已更新（"生产级通用 Agent"、workspace tmp 说明） |
| `dayu/README.md` | 项目定位变更 | ✅ 已更新 |
| `dayu/host/README.md` | Memory Projection、Context Compaction 章节 | ✅ 已更新（vNext 五类 memory、compact I/O contract） |
| `dayu/config/README.md` | memory_projection_policy 字段变更 | ✅ 已更新 |
| `tests/README.md` | 测试覆盖描述 | ✅ 已更新（vNext 术语） |

## Residual Risks

1. **Schema CHECK constraint 变更未 bump version**: `durable/schema.py` 的 `item_kind` CHECK 约束从旧 6 种改为新 6 种，但 `HOST_SCHEMA_VERSION` 仍为 15。SQLite `CREATE TABLE IF NOT EXISTS` 意味着已有数据库保留旧约束，新数据库使用新约束。若已有数据库需要写入新 item_kind，需手动迁移。按设计真源"一律按全新 schema 起库处理"，此行为可接受。

2. **`_COMPACTED_OLD_FIELDS` 仅拒绝旧字段写入，不提供读取兼容**: `context_events.py` 的 `_reject_old_compacted_fields` 只在写入时拒绝旧格式 payload，不提供旧格式读取路径。若 EventLog 中存在旧格式 `CONTEXT_COMPACTED` event，`compaction_evidence.py` 的 `_evidence_backed_fact_refs_from_compacted_event` 会因找不到 `accepted_candidate` 字段而抛出 `HostDurableError`。这是设计意图（全新 schema），但需确认生产环境无旧数据。

3. **compaction_operation.py 多 pass 合并逻辑已移除，改为 last-writer-wins**: 旧实现的 `_merge_pass_candidates` 等合并逻辑被删除，改为迭代 pass 队列、最后一个通过 quality gate 的 candidate 被接受。`test_compaction_operation.py` 中 `test_reactive_multi_pass_commits_single_merged_context_compacted`、`test_reactive_multi_pass_uses_last_whole_vnext_candidate` 等测试显式验证了此语义。这是 vNext 设计的有意简化，已由测试覆盖。
