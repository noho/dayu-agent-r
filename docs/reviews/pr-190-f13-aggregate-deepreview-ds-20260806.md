# PR 190 F13 Aggregate Adversarial Deepreview (DS)

## Scope

- Mode: current changes (aggregate S0+S1+S2 full-slice)
- Branch: `codex/interactive-oracle`
- Base: `2d914beefb7bdee3e762df06f5f1ef0d115da143`
- Output file: `docs/reviews/pr-190-f13-aggregate-deepreview-ds-20260806.md`
- Covered: `dayu/host/compaction.py`, `compact_structure.py`, `compact_payload.py`, `context_governance.py`, `compact_material.py`, `compact_pipeline.py`, `compaction_operation.py`, `memory.py`, `llm_compaction.py`, `durable/tool_trace.py`, `tool_trace_analysis*.py`, 全部改动测试与 README
- Formal replacement scenarios: **仍 unadjudicated**（accepted plan checkpoint 冻结）

## Findings

### F1-ACCEPTED-逐事实provenance防laundering链正确闭合
- **入口/函数**: `derive_compact_accepted_replacement_v4` → `CompactAcceptedEvidenceFactV4`
- **文件(行号)**: `compaction.py:1634-1711`, `compaction.py:1500-1553`
- **输入场景**: 模型 proposal 中 new fact 的 `support_labels` 引用 `EVIDENCE_MATERIAL` source，retain 引用 `PREVIOUS_EVIDENCE_FACT`
- **实际分支**: retained fact：从 boundary entry 原样复制 claim + `canonical_evidence_refs`；new fact：从 `support_labels` 对应的 boundary evidence entries 逐条 union refs
- **直接证据**: `COMPACT_FACT_SOURCE_KINDS_V4 = (CompactSourceKindV4.EVIDENCE_MATERIAL,)`（行117），`COMPACT_RETAIN_SOURCE_KINDS_V4 = (CompactSourceKindV4.PREVIOUS_EVIDENCE_FACT,)`（行119）。`compact_proposal_boundary_binding_issues_v4` 在 proposal 进入 acceptance 前校验 source kind（行1762-1778），非 evidence material 的 label 不能成为 new fact support。`PromptLocalProvenanceEntry.__post_init__`（行323-334）对 evidence kind 强制非空 `canonical_evidence_refs`，非 evidence kind 强制空 refs
- **影响**: 用户/assistant answer/summary 文本无法伪装成 evidence，也无法通过 retained fact 改写 claim 来洗白 refs
- **建议改法**: 无需修改
- **修复风险**: N/A
- **严重程度**: ACCEPTED

### F2-NEEDS_FIX-_aggregate_pass_candidates retained/new 分类依赖不稳定 selection_labels[0] 启发式
- **入口/函数**: `_aggregate_pass_candidates`
- **文件(行号)**: `compaction_operation.py:1256-1277`
- **输入场景**: reactive multi-pass 中某 pass truth 的 accepted evidence fact 带有多个 `selection_labels`（例如两个 evidence label 共同支撑一个 fact）
- **实际分支**: 行1258 `len(fact.selection_labels) == 1` 将多-label fact 排除在 retained 判定之外，强制归入 new_facts；但 accepted replacement 的 fact atom 可能确实代表一个被 retained 的 multi-source previous fact
- **预期行为**: retained 判定应使用 accepted fact 的来源类型而非 selection_labels 数量启发式；或至少文档化此约束
- **直接证据**: 行1260-1262 检查 `fact.selection_labels[0]` 的 source kind 是否为 `PREVIOUS_EVIDENCE_FACT`，但只有单-label fact 能进入此分支。当前 accepted plan 冻结后，new fact support 只允许 `EVIDENCE_MATERIAL`，所以 retained fact 的 `selection_labels` 实际只有一个（行1684 `(entry.source_label,)`），当前逻辑偶然正确
- **影响**: 若未来 accepted fact 构造方式变化（例如 retained fact 允许 context labels），此启发式会产生静默分类错误；当前无实际触发路径
- **建议改法和验证点**: 用 `root_input.source_kind()` 检查所有 selection_labels 是否全部为 `PREVIOUS_EVIDENCE_FACT`，而非只检查 `[0]` 且要求 len==1；增加 multi-label retained fact aggregate 测试
- **修复风险**: 低
- **严重程度**: 低 / NEEDS_FIX

### F3-ACCEPTED-repair feedback 双循环终止保证 fail-closed
- **入口/函数**: `build_compact_repair_feedback_v4`
- **文件(行号)**: `context_governance.py:200-227`
- **输入场景**: 32 条 issue 的 feedback JSON 序列化后超过 8192 字符
- **实际分支**: 第一个 while 循环逐条 drop issue（行201），第二个 while 循环截断最后一条 issue 的 `source_labels`（行211-220），直到全部 labels 耗尽时 `raise RuntimeError`
- **直接证据**: 行213-214 当 `len(only_issue.source_labels) == 0` 时 raise RuntimeError。两个循环都保证严格单调递减（issues 数或 labels 数），必然终止
- **影响**: 极端情况（单条 issue 无 labels 但仍超 8192 chars）会 fail-closed，不会生产 oversized feedback；此路径需手工审查 feedback message 是否合理超长
- **建议改法**: 无需修改；RuntimeError 是预期 fail-closed 行为
- **修复风险**: N/A
- **严重程度**: ACCEPTED

### F4-ACCEPTED-S2 S0 F1 fix applied — accepted_evidence_facts 默认值已删除
- **入口/函数**: `ToolTraceCompactorResponseSummary`
- **文件(行号)**: `tool_trace_analysis_contracts.py`
- **直接证据**: rg 扫描确认 `accepted_evidence_facts` 无 `= ()` 默认值；tests 中所有 attempt-rejected 构造点显式传入 `accepted_evidence_facts=()`；`ResolvedCompactorResponseIdentity.__post_init__`（`tool_trace.py:487-491`）强制 attempt-rejected 时 facts 为空
- **影响**: contract 从隐式默认收紧为 required typed input；不再出现"未提供 provenance 静默改写为空"
- **严重程度**: ACCEPTED

### F5-ACCEPTED-LLM-facing 文本未泄漏内部 provenance 字段
- **入口/函数**: `CompactSourceBoundaryEntryV4.to_json()`, `CompactMaterialBlock.llm_json()`, `compact_output_prompt_rules_v4()`
- **文件(行号)**: `compaction.py:709-718`, `compaction.py:447-458`, `compact_structure.py:224-234`
- **直接证据**: `to_json()` 只输出 `source_label/source_kind/readable_text`，不含 `source_refs/canonical_evidence_refs`；`llm_json()` 不含 `canonical_source_refs/content_digest/canonical_evidence_refs`；`compact_output_prompt_rules_v4()` 使用 "non-empty string"、"array of unique non-empty strings" 等业务可读描述，不暴露内部类型名
- **影响**: 模型无法从 prompt 中读取 canonical refs 来构造伪造引用
- **严重程度**: ACCEPTED

### F6-ACCEPTED-_bind_reactive_pass_to_root_labels identity key 无碰撞风险
- **入口/函数**: `_bind_reactive_pass_to_root_labels`
- **文件(行号)**: `compact_pipeline.py:646-716`
- **输入场景**: 单-block reactive pass 的 boundary entry 绑定回 immutable root labels
- **实际分支**: 行661 使用 `(source_kind, source_refs, readable_text)` 三元组做 identity lookup；`source_refs` 是 canonical 且在 boundary 内唯一保证了无碰撞
- **直接证据**: `CompactSourceBoundaryEntryV4.__post_init__`（行685）要求 `source_refs` 非空唯一；`CompactInputV4.__post_init__`（行1185）要求 source labels 唯一
- **影响**: 无
- **严重程度**: ACCEPTED

### F7-ACCEPTED-aggregate accepted_evidence_mapping_refs 单一真源链完整
- **入口/函数**: `parse_context_compacted_semantic_payload` → `_validate_aggregate_boundary_unique_membership`
- **文件(行号)**: `compact_payload.py:128-131`, `compact_payload.py:501-526`
- **直接证据**: 行128-131 要求 `accepted_evidence_mapping_refs == replacement.canonical_evidence_refs`（replacement-derived ordered unique union）；行511-526 额外校验 aggregate 是 boundary evidence 子集且元素唯一。两处校验互补且无重叠遗漏
- **影响**: durable aggregate 不可能偏离 replacement 真源，也不可能包含 boundary 外 refs
- **严重程度**: ACCEPTED

### F8-ACCEPTED-fallback 路径不污染 durable accepted replacement
- **入口/函数**: `build_fallback_decision_input` → `CompactPipelineFailedPayloadInput`
- **文件(行号)**: `compact_pipeline.py:755-856`
- **直接证据**: fallback 路径构造 `CompactPipelineFailedPayloadInput`，其 `fallback_action` 可为 `FALLBACK_ACTION_DISPATCH` 或 `FALLBACK_ACTION_FAIL_CLOSED`；两种路径均不创建 `CompactAcceptedTruthV4`（需 `_COMPACT_ACCEPTANCE_PERMIT` 私有 token），不写入 `accepted_replacement`
- **影响**: 即使 fallback dispatch 成功，后续 rolling compact 也不会读取到被污染的 fact provenance
- **严重程度**: ACCEPTED

### F9-ACCEPTED-stale/late duplicate terminal 单 terminal 保证未退化
- **入口/函数**: `_resolve_compactor_response_identity`
- **文件(行号)**: `tool_trace.py:680-692`
- **直接证据**: 行681-685 检测到第二个 matching terminal 时 raise `CompactorResponseResolutionError("duplicate canonical terminals")`；完整 keyset exhaustion（行686-687）保证不遗漏尾部 terminal
- **影响**: duplicate terminal 不会静默选择第一个而忽略第二个；fail-closed 保证 observable
- **严重程度**: ACCEPTED

### F10-ACCEPTED-reconnect/raw parser 同源 replacement 单一消费链
- **入口/函数**: `accepted_compact_business_texts` → `RunInput` builder call sites
- **文件(行号)**: `compact_payload.py:226-247`, `memory.py` (changed lines)
- **直接证据**: 所有 consumer（Memory 逐 fact 投影 `memory.py`、RunInput builder `run_input.py`、reconnect `dispatch.py`、engine ingest `engine_ingest.py`）均从 `CompactAcceptedReplacementV4` 读取，不从 proposal 或 raw payload 反推
- **影响**: 不存在 consumer 绕过 replacement 直接解释 proposal 导致 provenance 漂移
- **严重程度**: ACCEPTED

## Open Questions

- `_aggregate_pass_candidates` 的 retained/new 分类启发式（F2）当前因 accepted plan 冻结（retained fact 只有单 selection_label）而偶然安全；若未来 accepted fact 语义扩展，此路径是已知弱点，建议在扩展时同步修复
- formal replacement scenarios 仍 unadjudicated，属于已批准 residual risk

## Residual Risk

- Oracle formal replacement scenarios 尚未裁决，accepted plan checkpoint 明确分类为 "assigned to later Oracle adjudication"
- 真实 provider 行为（repair loop、fallback dispatch）仅在 unit/integration 测试中覆盖，未经过端到端真实 LLM 验证
- S2 `tool_trace.py` 覆盖率 85%，`analysis_contracts.py` 88%，未达 100% 但已超 80% 阈值

## F2 Resolution（Controller adjudication）

- **Finding**: F2 NEEDS_FIX — `_aggregate_pass_candidates` retained/new 分类依赖 `selection_labels[0]` 启发式
- **Controller decision**: **dismissed**
- **直接证据**: `derive_compact_accepted_replacement_v4`（`compaction.py:1681-1688`）对每个 retained previous_evidence_fact boundary atom 唯一构造 `selection_labels=(entry.source_label,)`——单 label，固定不变。retained atom 可有多条 `canonical_evidence_refs`，但 `selection_labels` 始终只有一个元素。new fact 才可多 `selection_labels`，且全部 kind=`EVIDENCE_MATERIAL`，由 `compact_proposal_boundary_binding_issues_v4` 在 acceptance 前校验。pass truth 只能由私有 `_COMPACT_ACCEPTANCE_PERMIT` acceptance 产生，root revalidation 再重验全部 binding
- **为何不采纳**: 不存在合法 multi-label retained atom 路径；改为"检查所有 selection_labels 均为 PREVIOUS_EVIDENCE_FACT"会为不可能状态增加分支，并可能掩盖真正的 contract corruption（例如上游错误地给 retained atom 注入了非 previous label）。当前 `len==1` + `source_kind` 检查精确匹配 construction contract 的不变量，不是启发式
- **处置**: 未来 schema 变更由未来 work unit 处理；当前 finding dismissed，无代码或测试修改

## Final Verdict

**ACCEPTED** — 10 项 adversarial findings 全部 resolved（9 ACCEPTED + 1 dismissed）。无 unresolved NEEDS_FIX。逐事实 provenance 防 laundering 链完整闭合；LLM-facing 文本未泄漏内部 provenance；aggregate 单一真源链、fallback 无污染、stale/late/duplicate terminal fail-closed 均经验证；Tool Trace 展示补偿（S2）通过 strict semantic payload resolver 机械投影 claim/refs，不创建第二 provenance owner。
