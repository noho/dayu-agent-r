# WU-DUR / WU-OBS / WU-CM Closeout Plan Fix Re-review

## Gate

- Work unit group: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01
- Gate: plan fix re-review
- Fixed plan artifact: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- Plan fix artifact: `docs/reviews/wu-dur-obs-cm-closeout-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-dur-obs-cm-closeout-plan-review-controller-adjudication.md`
- Original review artifact: `docs/reviews/wu-dur-obs-cm-closeout-plan-review-mimo.md`
- Design source: `docs/host/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Re-reviewer: AgentMiMo
- Date: 2026-06-05

---

## Accepted Findings Fix Status

### A1. Slice 0 contract shape too abstract — 已修复

Controller 要求：补充 consolidated contract appendix，定义 RunnerCallInputAssemblyManifest、message entry、projector metadata、tool-call arguments atom、Tool Trace signal，每字段含 name、type、requiredness、semantics、digest/ref boundary、validation rule。

验证：fixed plan L226-377 包含完整的 "Consolidated Contract Appendix"，共 7 张 typed 表：

| 表 | 行数 | 字段数 | 6 列完整性 |
|---|---|---|---|
| RunnerCallInputAssemblyManifest | L248-273 | 22 | field/type/required/semantics/digest-ref boundary/validation rule ✅ |
| RunnerCallMessageEntry | L280-292 | 11 | 同上 ✅ |
| ProjectorMetadata | L297-305 | 6 | 同上 ✅ |
| ToolCallArgumentsAtom | L309-323 | 13 | 同上 ✅ |
| Tool Trace signal | L329-341 | 12 | 同上 ✅ |
| RunnerCallReconstructionDiagnostic | L346-360 | 10 | field/type/required/semantics/validation rule ✅ |
| CompactorRunnerCallIdentity | L364-376 | 9 | field/type/required/semantics/validation rule ✅ |

具体度等价于 design.md L1501-1523 的 canonical event contract matrix 格式。Slice 0 writeback 要求（L388-394）明确指向本 appendix。

### A2. Inline-vs-ref and storage-form unresolved — 已修复

Controller 要求：决定 arguments inline/payload ref/both；复用 design.md payload_inline_threshold_bytes；定义 payload descriptor kind；决定 manifest 存储形态。

验证：

- L160：mixed storage strategy，`arguments_json_size_bytes <= payload_inline_threshold_bytes` 走 inline，否则走 `tool_call_arguments_json` descriptor kind。
- L166：5 个 descriptor kinds 明确枚举：`tool_call_arguments_json`、`tool_call_semantic_query_text`、`runner_call_input_manifest`、`runner_call_projection_artifact`、`compactor_input_projection`。
- L238-242：manifest 存储为 canonical event `RUNNER_CALL_INPUT_ASSEMBLED` + payload descriptor/artifact body 组合形态。
- L315：`arguments_storage_kind` 含 validation rule "inline iff size <= payload_inline_threshold_bytes"。
- L320：`semantic_query_storage_kind` 含 "absent" | "inline_text" | "payload_descriptor" 三值。
- L173：manifest body 超过阈值写 artifact root 并通过 payload descriptor 引用；不成为 Run state truth。

阈值、descriptor kind、存储形态、判定规则全部明确，无实现歧义。

### A3. limited-signal / mismatch diagnostic shape undefined — 已修复

Controller 要求：定义 diagnostic contract 含 status enum、reason enum、missing atom/ref fields、observed/expected counts/digests、consumer boundary。

验证：

- L346-360：`RunnerCallReconstructionDiagnostic` 完整 typed shape。
- L349：`status` 三值枚举 `"complete" | "limited_signal" | "mismatch"`。
- L350：`reason` 类型为 `DiagnosticReason` 闭合枚举。
- L360：`DiagnosticReason` 13 值，覆盖 missing atom（6 种）、mismatch（4 种）、unresolvable_ref、provider_specific_atom_deferred。
- L351-352：`missing_atom_kind`、`missing_ref_kind` 均为 closed string enum | null。
- L354-357：`observed_count`、`expected_count`、`observed_digest`、`expected_digest` 用于 mismatch 诊断。
- L358：`consumer_boundary` 四值枚举 `"tool_trace_query" | "analyzer_fixture" | "compact_evidence_projection" | "public_smoke"`，明确 compact LLM-facing text 只能接收 business-neutral wording。

5 个消费该 shape 的 slice（L218/L379/L474/L528/L557）全部引用同一 typed shape。

### A4. runner_call_kind incomplete and overlapping — 已修复

Controller 要求：闭合枚举或分类模型，不重叠；若需多维则 kind 与 trigger/reason 分离。

验证：

- L274：`RunnerCallKind` 5 值闭合枚举：`initial_user_dispatch`、`followup_user_dispatch`、`tool_result_continuation`、`post_compaction_dispatch`、`compactor_proposal`。
- L276：`RunnerCallTriggerReason` 11 值独立枚举：`initial_user_input`、`followup_user_input`、`tool_results_available`、`force_answer_after_tool_limit`、`finish_reason_length_continuation`、`host_retry`、`host_replay`、`host_resume`、`context_compaction_completed`、`context_compaction_repair_attempt`、`context_compaction_retry_attempt`。
- L276 validation rule："forced answer、length continuation、retry/replay/resume 是 trigger reason，不再挤入 runner_call_kind"。

两维分离，覆盖 ordinary initial/follow-up、tool loop continuation、forced answer、length continuation、retry/replay/resume、context compaction，无语义重叠。

### A5. Compactor internal runner-call identity ambiguous — 已修复

Controller 要求：定义 parent/self fields（parent Host run id、compaction operation id、compactor Engine run id），明确与 CONTEXT_COMPACTED 和 rejected attempt diagnostics 的关系。

验证：

- L364-376：`CompactorRunnerCallIdentity` 9 个字段。
- L366-367：`parent_host_run_id`、`parent_session_id` 明确为 parent。
- L368：`compaction_operation_id` 为 operation 级 identity。
- L369：`compactor_engine_run_id` 含 validation rule "must not be treated as Host admitted user Run id"。
- L373-374：`accepted_context_compacted_event_ref`、`rejected_attempt_diagnostic_ref` 分别指向 accepted/rejected。
- L376：明确关系说明——"CONTEXT_COMPACTED continues to own accepted compact artifact refs...The compactor runner-call manifest complements it by recording the LLM proposal call input identity. Accepted compact events reference the accepted proposal manifest; rejected attempts reference their manifest through typed diagnostics. Neither path turns rejected proposal content into memory or compact truth."

parent/self 分离明确，引用关系可实现。

### A6. WU-CM-01-F02 motivation overstated — 已修复

Controller 要求：收窄动机，表明 tool_name 已有设计位置，真实缺口是 arguments/semantic query in query_text。

验证：

- L19 Goal："EvidenceReadableItem.tool_name 在设计中已存在；真实缺口是 query_text 缺少 durable arguments / semantic query 的业务可读表达，不能把问题表述成完全缺失 tool identity。"
- L37 Success Signal F02："evidence_material[*].tool_name 继续承担工具身份；query_text 不再退化为裸 tool_call_id=...，而是来自 durable arguments 或 optional semantic query"
- L556 Slice 5："tool_name 已由 EvidenceReadableItem.tool_name 承担身份，query_text 的职责是补足 arguments / semantic query"

动机准确收窄，不再夸大 tool identity 缺失。

### A7. Slice 0 needs a design review sub-gate before code slices — 已修复

Controller 要求：增加 design-review sub-gate，含 artifact path、acceptance criteria、stop condition。

验证：

- L408-424：完整的 "Slice 0.5: Design Review Sub-gate" 章节。
- L411：artifact path `docs/reviews/wu-dur-obs-cm-closeout-design-review.md`。
- L413：review owner 定义（phaseflow 总控派发的 design reviewer）。
- L416-421：6 条 acceptance criteria 覆盖 manifest/inline-ref/kinds/compactor identity/Engine vs Host ownership/LLM-facing text boundary。
- L424：stop condition "该 artifact 未给出 pass / accepted verdict 前，Slice 1-7 不得派发"。

sub-gate 完整，可阻止未经 review 的 code slices。

---

## Consolidated Contract Appendix 必检项验证

| 检查项 | 状态 | 证据 |
|---|---|---|
| 字段名 | ✅ | 7 张表全部有 field name 列 |
| 类型 | ✅ | 7 张表全部有 type 列，含 str/int/Digest/HostInternalRef/closed enum/list/nullable |
| 必填性 | ✅ | 7 张表全部有 required 列（yes/conditional/no） |
| 语义 | ✅ | 7 张表全部有 business/Host semantics 列 |
| digest/ref boundary | ✅ | 7 张表全部有 digest/ref boundary 列 |
| validation rule | ✅ | 7 张表全部有 validation rule 列 |
| inline/ref threshold | ✅ | 复用 design.md §13.1 `payload_inline_threshold_bytes`，L160/L241/L315 明确引用 |
| payload descriptor kind | ✅ | L166 枚举 5 个 kind |
| manifest storage form | ✅ | L238-242 canonical event + payload descriptor/artifact 组合形态 |
| diagnostic shape typed | ✅ | L346-360 RunnerCallReconstructionDiagnostic 完整定义 |
| runner call classification | ✅ | L274-276 RunnerCallKind + RunnerCallTriggerReason 两维分离无重叠 |
| compactor parent/self identity | ✅ | L364-376 CompactorRunnerCallIdentity 完整定义 |
| F02 motivation | ✅ | L19/L37/L556 准确收窄为 arguments/semantic query gap |
| Slice 0.5 sub-gate | ✅ | L408-424 完整定义，可阻止未 review 的 code slices |

---

## New Blocking Findings

无。fix 为纯文档修改，不引入新的 blocking risk。

---

## Residual Risks

1. **Manifest 字段膨胀**：RunnerCallInputAssemblyManifest 有 22 个字段。Slice 0.5 review gate 有 size-boundary 检查（L420），需在 design writeback 时严格压缩。
2. **Provider-specific tool_calls/reasoning_content**：已正确 deferred（L292-293），Slice 0 design review 必须选择纳入或显式 deferred。不是 blocking，但需要明确 owner。
3. **Prompt rewrite 保持 Slice 6**：L696 解释理由充分——public smoke 最终验收需要 durable manifest/trace/compact query signals 先落地。

---

## Completion Report

- **artifact path**: `docs/reviews/wu-dur-obs-cm-closeout-plan-rereview-mimo.md`
- **verdict**: pass
- **unfixed/partial findings count**: 0
- **new blocking findings count**: 0
- **residual risks / open questions**: 3（均 non-blocking）

### Verdict Rationale

7 个 accepted blocking findings 全部已修复。consolidated contract appendix 包含完整的 typed shape 定义（字段名、类型、必填性、语义、digest/ref boundary、validation rule），inline/ref threshold 复用 design.md 已有策略，payload descriptor kind 明确枚举，manifest 存储形态决策清晰，diagnostic shape 有闭合枚举和完整字段，runner call 分类两维分离无重叠，compactor parent/self identity 明确，F02 动机准确收窄，Slice 0.5 design review sub-gate 可阻止未 review 的 code slices。fix 未引入新 blocking risk。fixed plan 现在 code-generation-ready。
