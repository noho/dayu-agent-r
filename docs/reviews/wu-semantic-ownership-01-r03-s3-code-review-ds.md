# WU-SEMANTIC-OWNERSHIP-01 R03-S3 Code Review (AgentDS)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `44e68550ed226a3a207a73bd257478ab1bbbdce4`
- Output file: `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-ds.md`
- Review timestamp: 2026-07-15 14:08 CST
- Included scope: `44e68550..worktree` 全部 S3 改动（含 untracked 新文件）
- Excluded scope: 无（所有 allowlist 内/外文件均已审查）
- Parallel review coverage: 无（单 reviewer 全文走读）

### 审查输入

按任务要求已完整读取：

1. `AGENTS.md`（根项目指令）
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`（Topic 3/4/9 裁决）
3. `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` §11（S3 plan）、§12（smoke contract）
4. `docs/reviews/wu-semantic-ownership-01-r03-s3-implementation-codex.md`（Codex implementation handoff）
5. `docs/reviews/wu-semantic-ownership-01-r03-s3-controller-validation.md`（Controller validation，含 R03-S3-CV-F01..F05）

### 审查的生产文件（all diffed）

- `dayu/host/accepted_result_projection.py`
- `dayu/host/evidence.py`
- `dayu/host/run_input.py`
- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/tool_trace.py`

### 审查的测试/smoke 文件

- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py`（新增）
- `utils/smoke_host_public_r03_semantic_ownership.py`（新增）

### 审查的文档文件

- `dayu/host/README.md`
- `tests/README.md`

### no-diff owner 验证

以下四个文件相对 baseline 零差异（`git diff --exit-code 44e68550 -- ...` 均 exit 0）：

- `dayu/host/compaction.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/domain/tool_models.py`

### 静态验证结果

- pyright（修改的八个 production files）：`0 errors, 0 warnings, 0 informations`
- git diff --check：`PASS`（无 whitespace error）
- allowlist 外零 diff
- 旧符号传播扫描（`_INTERNAL_SOURCE_REF_KINDS`、`_READABLE_SOURCE_SEPARATOR`、`_readable_ref_text`、`ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`、`ACCEPTED_EVIDENCE_MATERIAL_UNAVAILABLE_TEXT`）：五个 consumer production files 零命中
- `OpaqueEvidenceRef` 在五个 consumer production files 零命中
- `hasattr`/`getattr` 在八个 production files 零命中
- `FALLBACK_ACTION_NOT_APPLICABLE` 在 `compact_pipeline.py` 已移除 unused import

---

## Findings

### 未发现实质性问题

经过对全部 S3 diff 的逐文件走读，包括：

1. **语义 owner 审查**：`_explicit_citation` 的 exact JSONPath（`kind=completed → result.ok=true → value.citation`）正确识别 producer-owned citation object；Host 不枚举 citation key、不猜测 ref kind/id、不新增 `BusinessSource` abstraction。旧 blacklist `_INTERNAL_SOURCE_REF_KINDS` 和 `_readable_ref_text` 已完全删除。

2. **opaque refs internal-only 审查**：`OpaqueEvidenceRef` 已从 `AcceptedToolResultProjection`、`RunInputMaterialBlock`、`InitialEvidenceMaterial`、`run_input_material_block` 等公共 contract 中移除。`AcceptedEvidenceEnvelope` 仍保留 `source_refs`/`locator_refs` 用于 EventLog/audit/internal provenance round-trip。`_evidence_provenance` 和 `_provenance_from_evidence_blocks` 对 `source_locator_refs` 固定传空 tuple `()`。

3. **explicit citation 唯一 readable business source 审查**：新的 `_source_projection(raw_outcome, diagnostics)` 直接消费 digest-checked raw outcome，不依赖 envelope。四个消费者（RunInput、Memory、Compact、Tool Trace）的 source 文本均从 shared projection 的 `source.text` 字段派生。citation 缺失、`citaiton` 拼错、非 object citation 均收敛为唯一中性文案 `"该工具结果未提供业务来源。"`，不退回 ref guessing。

4. **四消费者 strict typed material/no fallback 审查**：
   - RunInput (`run_input.py`): `_memory_projection_event_from_row` 检查 `projection.llm_material is None` → `HostDurableError`；`_fallback_message_from_material_block` 检查 `block.accepted_tool_evidence is None` → `HostDurableError`
   - Memory (`memory.py`): `_selected_evidence_text` 检查 `material is None` → `HostDurableError`；`durable/memory.py`: `_tool_result_memory_payload_view` 检查 `projection.llm_material is None` → `HostDurableError`
   - Compact (`compact_material.py`): `_pack_evidence_blocks` 检查 `block.accepted_tool_evidence is None` → `HostDurableError`；`compact_pipeline.py`: `_message_from_material_block` 检查 `block.accepted_tool_evidence is None` → `HostDurableError`
   - Tool Trace (`tool_trace.py`): `_canonical_trace_summary_signals` 检查 `projection.llm_material is None` → `HostDurableError`；`_tool_result_summary_from_projection` 检查 `projection.llm_material is None or projection.raw_outcome is None or projection.result_text is None` → `HostDurableError`
   所有四个消费者在 material 缺失时均 fail closed，无 skip、fallback、limited signal 或 consumer-specific recovery。

5. **Tool Trace strict canonical request atom 审查**：`_tool_request_summary_from_row` 通过 `read_event_by_id` + strict `EventClass.CANONICAL_FACT` 检查 + `tool_call_request_atoms` 恢复 bounded exact args/query。旧 `_tool_request_summary_from_payload`（raw payload/redaction/placeholder）和 `_inline_arguments_json` 已删除。`_projection_arguments_object` 和 `_arguments_object` 在参数缺失或类型错误时 fail closed 为 `HostDurableError`。readable result 通过 `business_source_text` 和 `business_source_state` 映射 shared projection，不再暴露 `raw_outcome_digest`、`outcome_digest`、`payload_ref`、`payload_digest` 或 `limited_signal` 状态。

6. **R03-S3-CV-F01..F05 关闭验证**：
   - F01: `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 已从 `evidence.py` 定义和 `__all__` 删除；active production/tests/smoke 源码扫描零命中。
   - F02: smoke 使用 `list_documents` → `get_document_sections` 顺序；`get_document_sections` 是唯一 explicit citation producer；Fins owner files no-diff。
   - F03: `_validate_required_request_atoms` 校验五个 required calls 的 exactly-once、exact arguments equality、normalized/payload digest 同源；`_validate_tool_awaiting_payload_contract` 通过 `event_payload_object` 读取 digest-checked payload，校验 strict request link，拒绝所有 arguments/digest 副本。
   - F04: `_workspace_retention_summary` 恒定输出 `WORKSPACE_KEPT true ... cleanup=never`；flag 仅记录 `caller_requested=true/false`。
   - F05: `fins-list` round 只传 `{"ticker": fins_ticker}`；`fins-read` prompt 自足携带前置验证条件（"只有当上一轮同 ticker...确实包含...才执行"）和 stop/no-guess 规则。Fins/config owner 均 no-diff。

7. **真实 public-run smoke 合约审查**：
   - 执行链：`ConfigLoader → ToolsDiscovery → ScenePrepare/Service assembly → open_host → ensure_session → submit_followup`
   - 五个 exact calls：`read_file`、`search_web`、selected Fins awaiting tool、`list_documents`、`get_document_sections`
   - `TOOL_AWAITING` no-copy/link：`_forbidden_awaiting_duplicate_fields` 拒绝所有含 `"arguments"` 子串或 `normalized_arguments_digest` 的字段
   - Fins grounding → citation read 顺序：`fins-list` 只传 exact ticker，`fins-read` prompt 条件化于上轮同 ticker 结果
   - internal diagnostic read 与 public execution 分离，明确标注为 internal
   - stdout 脱敏、有界、不输出 secret/header/完整 prompt/opaque refs

8. **allowlist/no-diff 验证**：所有 production diff 均在 allowlist 八文件内；四个 no-diff owner 文件零差异。

9. **安全机制保留验证**：Doc `allowed_paths`、Web 网络防御、path containment、symlink 防护、DNS/peer/resource budget、atomic write、process fencing、Host durable integrity checks 均未被本 slice 修改。

10. **禁止偷带验证**：Issue 177/178、`BusinessSource` abstraction、统一 tool authorization、aggregate PASS 均不在本 slice diff 中。

---

## Open Questions

无。

---

## Residual Risk

1. **Aggregate 外部 public-run smoke 未执行**：`utils/smoke_host_public_r03_semantic_ownership.py` 脚本和 assembly guard tests 已交付，但 §12 要求的真实 Web/provider/Fins 外部环境 smoke 尚未运行。Controller validation 已明确记录此 gate 留给后续 aggregate validation。这不是 S3 implementation 缺陷，但 R03 整体 closure 仍依赖此 gate。

2. **单文件 coverage 有未覆盖行**：八个 production files 的 coverage 在 85%–96% 之间（全部 >=80% gate），evidence.py branch coverage 91%（>=90% gate）。未覆盖行涉及部分异常恢复路径和诊断分支，不影响 S3 核心 semantic ownership contract。这些未覆盖行属于既有模块的 residual area，不是本 slice 新增的未测试路径。

3. **`AcceptedToolEvidenceLLMMaterial` non-empty text constraint**：`evidence.py` 中 `AcceptedToolEvidenceLLMMaterial.__post_init__` 要求四个字段均为非空文本。如果 producer citation 产生空 JSON object `{}`，`canonical_json_dumps({})` 返回 `"{}"`（非空字符串），会通过校验。这是正确的 mechanical rendering（Host 不解释 citation 内容），但下游 LLM 会看到空 source text。这不是本 slice 引入的缺陷，而是 explicit citation contract 的自然边界——空 citation 是 producer 的决策，Host 不应补充语义。

---

## Verdict

**PASS — 未发现实质性问题。**

R03-S3 implementation 正确实现了 accepted plan §11 的全部八项符号级改动和 §12 的 smoke contract。语义 owner 边界清晰：opaque refs 回归 internal provenance/audit；explicit citation 是唯一 producer-owned readable business source；四个消费者一致使用 strict typed material，缺失时 fail closed；Tool Trace 使用 strict canonical request atom。五个 controller validation findings（R03-S3-CV-F01..F05）均有直接代码证据支持已关闭。allowlist/no-diff/安全机制/deferred scope 均验证通过。无 `hasattr`/`getattr`、无 compatibility shim、无 downstream repair、无 speculative abstraction。
