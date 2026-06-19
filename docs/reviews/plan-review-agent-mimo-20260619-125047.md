# Plan Review: AgentMiMo

- Gate: plan review
- Work unit: Compact rejected attempt diagnostic artifact
- Reviewed plan: `docs/reviews/wu-cm-compact-rejected-diagnostic-plan-20260619-124435.md`
- Reviewer: AgentMiMo
- Mode: read-only pane review; reviewer did not edit files
- Artifact writer: controller, from captured pane output
- Timestamp: 20260619-125047
- Conclusion: pass-with-risks

## Findings

### F-1-未修复-中-_attempt_rejected 调用点需要明确注入诊断产出

- **位置**: Implementation Decisions / Slice 1
- **问题类型**: 不可直接实施
- **当前写法**: plan 说 `run_compaction_operation()` 接受 `rejected_attempt_diagnostic_recorder` 并在 proposal failure branches 调用。
- **反例/失败场景**: `CompactionAttemptRejected` 是 frozen dataclass。若 implementation agent 不知道诊断是在 `_attempt_rejected()` 参数中注入，还是 `_attempt_rejected()` 后重新构造对象，容易写出重复构造或遗漏字段。
- **直接证据**: `compaction_operation.py` 的两个 proposal failure catch 分支都调用 `_attempt_rejected()`；当前 `_attempt_rejected()` 只接收 `diagnostic_suffix` 和 manifest ref。
- **建议改法和验证点**: plan 明确 `_attempt_rejected()` 接受 `diagnostic_reference: CompactionRejectedAttemptDiagnosticReference | None`，并由 rejected summary 持有该 reference。
- **严重程度**: 中

### F-2-未修复-低-failure_stage 稳定值未定义

- **位置**: Contract / Schema / State-Machine Changes
- **问题类型**: 契约缺失
- **当前写法**: plan 引入 `failure_stage` 字段，但未定义允许值。
- **反例/失败场景**: 实施者可自由写 `material_projection`、`prepare_or_material_projection`、`previous_compacted_view_parse` 等字符串，后续 smoke/log/SQL 查询无法稳定匹配。
- **直接证据**: follow-up doc 曾使用 `prepare_or_material_projection`；用户本轮要求示例包含 `material_pack_to_compact_input / previous_compacted_view_parse`。
- **建议改法和验证点**: plan 至少定义当前 work unit 使用的固定值：`material_pack_to_compact_input`、`previous_compacted_view_parse`、`proposal_execution`。
- **严重程度**: 低

### F-3-不阻塞-CONTEXT_COMPACTION_FAILED 不直接传播 diagnostic artifact ref 是设计权衡

- **位置**: Slice 2 / traceability
- **问题类型**: observability path clarification
- **当前写法**: plan 把 diagnostic artifact ref 放在 per-attempt `CONTEXT_COMPACTION_ATTEMPT_REJECTED`。
- **风险**: operator 只查 `CONTEXT_COMPACTION_FAILED` 时不会直接看到 artifact ref，必须通过同一 `operation_id` join 到 rejected attempts。
- **建议改法和验证点**: 在 plan 和 docs 中明确追踪路径：failed event `operation_id` -> same operation rejected attempt rows -> `diagnostic_artifact_ref` -> `payload_descriptors` -> artifact JSON。
- **严重程度**: 低

### F-4-未修复-低-recorder 写入失败语义不够精确

- **位置**: State-machine invariant
- **问题类型**: 状态机漏洞
- **当前写法**: "fail closed only if existing durable write semantics require it"。
- **反例/失败场景**: diagnostic artifact 写入失败后如果异常向上传播，可能改变 compact failure/fallback 行为；如果吞掉异常但不记录，可能隐藏观测失败。
- **建议改法和验证点**: 明确 diagnostic recorder 失败是 best-effort：catch、log warning、返回不带 diagnostic reference 的 rejected attempt；不得改变 accept/reject/fallback/tier。
- **严重程度**: 低

### F-5-不阻塞-diagnostic_suffix 冗余但可接受

- **位置**: Artifact JSON schema
- **问题类型**: 过度设计
- **当前写法**: artifact JSON 存 `diagnostic_suffix`，而该值可由 exception class/message 推导。
- **建议改法和验证点**: 若保留，说明它用于 artifact 自包含阅读和与 EventLog `diagnostic_refs` 对齐。
- **严重程度**: 低

## Open Questions

- `run_compaction_operation()` 新参数需要确认 initial、proactive recovery tier、reactive 三类调用都传入 recorder。
- `CompactMaterialPack.to_json()` 是否包含 previous compacted view 原始 block text；实现测试需要直接断言。

## Residual Risks

- Parser root cause 未修复，long25 仍可能失败；归后续 production memory compact failure work unit。
- 多次 rejected attempt 会产生多条 descriptor；content-addressed artifact bytes 可去重，但 descriptor 行仍线性增长。
- artifact 大小随 material pack 增长；当前作为 diagnostic artifact 可接受，但应限制 raw 内容到必要 material。

## Final Conclusion

pass-with-risks。计划方向正确，scope 边界合规；实施前需要修正 F-1、F-2、F-4，并补充 F-3 的追踪路径说明。
