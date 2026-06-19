# Plan Review: AgentDS

- Gate: plan review
- Work unit: Compact rejected attempt diagnostic artifact
- Reviewed plan: `docs/reviews/wu-cm-compact-rejected-diagnostic-plan-20260619-124435.md`
- Reviewer: AgentDS
- Mode: read-only pane review; reviewer did not edit files
- Artifact writer: controller, from captured pane output
- Timestamp: 20260619-125047
- Conclusion: pass-with-risks

## Findings

### MF-1-已验证-Root Cause Alignment PASS

- **位置**: Goal / First-Principles Judgment
- **结论**: plan 正确识别 `proposal_manifest_ref=null` 的失败路径。generic path 在 manifest 记录前调用 `conversation_compact_input_vnext_from_material_pack()`，`_parse_previous_reference_continuity_text()` 的 `ValueError` 会被 proposal failure catch 分支记录为 rejected attempt。

### MF-2-已验证-Design Alignment PASS

- **位置**: Non-goals / Design Alignment
- **结论**: plan 正确区分 EventLog 小字段和 artifact raw diagnostic 内容，不把 raw text 放入 Conversation Memory、accepted compacted view 或 LLM-facing material。

### MF-3-已验证-Recorder Injection Pattern PASS with note

- **位置**: Implementation Decisions
- **结论**: 新 recorder Protocol 与既有 `CompactorProposalManifestRecorder` 模式一致。两个 recorder 职责正交。

### MF-4-未修复-低-parser diagnostic 逻辑复制存在漂移风险

- **位置**: Offending block detection
- **问题类型**: 维护风险
- **当前写法**: plan 不调用 `compact_material.py` 私有 parser，而是按已知 contract 找 offending line。
- **反例/失败场景**: 若 `_parse_previous_reference_continuity_text()` 后续调整 prefix 或分隔符，diagnostic helper 可能误判 offending block。
- **建议改法和验证点**: 实现中要么直接复用 parser，要么在 diagnostic helper docstring 明确这是 diagnostic mirror，并用测试覆盖当前错误消息和 block 定位。
- **严重程度**: 低

### MF-5-不阻塞-descriptor kind 常量位置需要按实际引用裁决

- **位置**: durable schema boundary
- **问题类型**: 架构边界
- **当前写法**: plan 默认不改 `dayu/host/durable/schema.py`。
- **代码事实**: 既有 `RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND`、`COMPACTOR_INPUT_PROJECTION_DESCRIPTOR_KIND` 在 durable schema 模块集中定义，但本次 descriptor kind 是 metadata 语义，不要求 DDL 变更。
- **建议改法和验证点**: 若新 descriptor kind 只在 `compaction_operation.py` 内部使用，保留私有常量；若跨模块复用再考虑 schema 常量。
- **严重程度**: 低

### MF-6-未修复-低-artifact 内容范围可能过大

- **位置**: Artifact JSON schema v1
- **问题类型**: 过度收集 / 存储风险
- **当前写法**: plan 允许 artifact 包含完整 material pack，包括 trace/evidence/answer material。
- **反例/失败场景**: 长会话 material pack 较大，diagnostic artifact 可能保存过多与 previous reference parse failure 无关的 raw evidence。
- **建议改法和验证点**: 收窄 artifact raw 内容：必须包含 `previous_compacted_view` 和 offending block raw text；其它 sections 只保留 digest、counts 或 locator summary，除非当前失败 stage 需要。
- **严重程度**: 低

### MF-7-已验证-EventLog payload redaction PASS

- **位置**: EventLog payload contract
- **结论**: plan 列出的 EventLog 字段不包含 raw text。需要实现时复用 `_safe_exception_message()`，避免异常消息带入敏感或业务长文本。

## Open Questions

- recorder 写入失败应明确为 best-effort：catch、log warning、返回不带 diagnostic ref 的 rejected attempt。
- `exception_message` 是否进入 EventLog 需要依赖现有 redaction/truncation。
- proactive recovery tier 失败时应记录 recovery request 的 previous view，而不是 initial request 的 previous view。
- 测试需要覆盖 generic path 或 prepared-compactor prepare failure，确保 `proposal_manifest_ref is None`。

## Residual Risks

- parser-diagnostic mirror 可能随 parser 变更漂移；应有测试和 docstring 提醒。
- artifact storage 会随 rejected attempts 累积；归后续 storage lifecycle 维护，不阻塞本 work unit。
- `CompactionAttemptRejected` 若平铺 13 个字段会膨胀；更优方案是只增加 `diagnostic_reference: CompactionRejectedAttemptDiagnosticReference | None`。
- reactive path event sub-index 冲突是既有风险，不在本 work unit 修。

## Final Conclusion

pass-with-risks。计划动机、设计边界和 recorder 模式成立；实施前应收紧 recorder failure semantics、exception redaction、artifact 内容范围、diagnostic reference shape 和 recovery tier ref uniqueness。
