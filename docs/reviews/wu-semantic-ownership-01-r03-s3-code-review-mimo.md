# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `44e68550`
- Review date: 2026-07-15
- Output file: `docs/reviews/wu-semantic-ownership-01-r03-s3-code-review-mimo.md`
- Included scope: `44e68550..worktree` 全部 S3 改动（8 production files、6 modified tests、2 new files、3 docs）
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对关键设计决策的逐项 evidence-based 确认：

### 语义 owner 收束确认

`accepted_result_projection.py:_source_projection`（L549-576）只从 digest-checked `raw_outcome` 的精确 JSONPath `kind==completed -> result.ok==True -> value.citation` 读取 producer-owned 显式 citation object。`_explicit_citation`（L579-598）严格按 shape 校验，不枚举 key、不猜测 ref_kind、不 fallback。旧 `_INTERNAL_SOURCE_REF_KINDS`、`_READABLE_SOURCE_SEPARATOR`、`_readable_ref_text` 在五个 production consumer 文件中零命中。

### Opaque refs internal-only 确认

`evidence.py` 的 `OpaqueEvidenceRef`（L70-93）仍由 `AcceptedEvidenceEnvelope` 产生、校验并在 EventLog/audit round-trip 中保留。`AcceptedToolResultProjection`（L112-148）不再携带 `source_locator_refs`。注入 `fliing-typo`、`opaque-should-never-reach-llm`、`event-typo-should-never-reach-llm` sentinel 的 owner tests 证明 envelope 中实际存在的 opaque refs 在 RunInput、Memory、Compact、Tool Trace 四消费者 LLM-facing 文本中均不可见。

### Explicit citation 唯一 readable business source 确认

无 explicit citation 时唯一文案为 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT = "该工具结果未提供业务来源。"`（`evidence.py` L38）。misspelled `citaiton`、citation 非 object、unknown citation member 均走同一路径。四消费者 canonical source text 完全同源。

### 四消费者 strict typed material / no fallback 确认

- **RunInput**（`run_input.py`）：`_selected_evidence_text` 在 `accepted_tool_evidence is None` 时抛 `HostDurableError`；`_message_from_material_block` 在 `accepted_tool_evidence is None` 时抛 `HostDurableError`。
- **Memory**（`durable/memory.py`）：`_tool_result_memory_payload_view` 在 `projection.llm_material is None` 时抛 `HostDurableError`。
- **Compact**（`compact_material.py`）：`RunInputMaterialBlock.__post_init__` 在 evidence block 缺 typed material 时抛 `ValueError`；`compact_pipeline.py` 的 `_message_from_material_block` 在 `accepted_tool_evidence is None` 时抛 `HostDurableError`。
- **Tool Trace**（`tool_trace.py`）：`_canonical_trace_summary_signals` 在 `projection.llm_material is None` 时抛 `HostDurableError`；`_tool_result_summary_from_projection` 在 `llm_material/raw_outcome/result_text` 任一为 `None` 时抛 `HostDurableError`。

四路径均无 skip、limited signal、consumer-specific recovery 或局部 catch。

### Tool Trace strict canonical request atom 确认

`_canonical_trace_summary_signals`（`tool_trace.py` L1088-1125）对 `TOOL_CALL_REQUESTED` 事件调用 `read_event_by_id` 获取真实 EventLog row，再通过 `tool_call_request_atoms` strict resolver 获取 bounded exact args/query。missing row、wrong type/class、storage conflict、descriptor/digest corruption 在 summary 发布前 fail closed。arguments descriptor ref/digest 只留在 internal row，不进入 readable summary。

### R03-S3-CV-F01..F05 关闭确认

| ID | 直接 evidence | 状态 |
|---|---|---|
| F01 | `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 从 `evidence.py` 删除，active source scan 零命中 | CLOSED |
| F02 | `list_documents` 无 citation，`get_document_sections` 作为 citation producer，Fins owner files no-diff | CLOSED |
| F03 | 五个 typed expected calls、exactly-once、exact arguments、normalized/payload digest 同源；`TOOL_AWAITING` strict link/no-copy | CLOSED |
| F04 | `_workspace_retention_summary` 恒定 `WORKSPACE_KEPT true ... cleanup=never` | CLOSED |
| F05 | `fins-list` → `fins-read` grounding 顺序、同 ticker 条件、exact tool sets、Fins/config owner no-diff | CLOSED |

### 真实 public-run smoke 链确认

`utils/smoke_host_public_r03_semantic_ownership.py` 使用 `ConfigLoader -> ToolsDiscovery -> ScenePrepare/Service assembly -> open_host -> ensure_session -> submit_followup`，配置真实 runner、Doc/Web/Fins ToolDefinition 与 production wait poller。五个 required calls 为 `read_file`、`search_web`、selected Fins awaiting tool、`list_documents`、`get_document_sections`，加 no-tool observation 轮。internal diagnostic read 只在 public runs 完成后用于验证，不参与执行链。

### Allowlist / no-diff 确认

实际 diff 的 8 production files、6 modified tests、2 new files、3 docs 全部在 implementation codex §2 allowlist 内。`compaction.py`、`durable/tool_trace.py`、`fins/tools/read_runtime.py`、`fins/domain/tool_models.py` 经 `git diff --exit-code 44e68550` 验证为零差异。

### 安全机制保留确认

Doc `allowed_paths`、Web 网络防御、path containment、symlink 防护、DNS/peer/resource budget、atomic write、process fencing 与 Host durable integrity checks 均保留。stdout 脱敏覆盖 `api_key/authorization/bearer/token/secret/cookie`，摘要限制 240 chars。未实现 Issue 177/178、BusinessSource abstraction、统一 tool authorization 或 aggregate PASS。

## Open Questions

无。

## Residual Risk

- §12 aggregate 真实外部 public-run smoke（Web/provider/Fins 环境 gate）未运行、未标 PASS，由后续 Controller aggregate validation 负责。
- `run_input.py` 单文件 coverage 89%（141 miss），部分 provider edge case 和 fallback path 未覆盖，但本 slice 新增/修改的 evidence material 路径已覆盖。
- `compact_material.py` 单文件 coverage 85%（140 miss），部分 recovery/selection edge case 未覆盖，但本 slice 新增的 `accepted_tool_evidence` 类型守卫已覆盖。

## Verdict

**ACCEPT — 未发现实质性问题。**

S3 实现正确地将业务来源语义从 opaque envelope ref guessing 收束到 producer-owned explicit citation 的唯一 owner boundary。四消费者在 typed material 缺失时统一 fail closed，Tool Trace request 通过 strict canonical atom resolver 恢复 exact arguments/query。CV-F01..F05 全部有直接 evidence 证明关闭。allowlist、no-diff、安全机制保留均通过。实现与 accepted plan §11/§12 一致，无偷带。
