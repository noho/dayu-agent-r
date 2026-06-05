# WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01 Slice 0.5 Design Review

## Review Context

- review gate: Slice 0.5 design review sub-gate
- review target: `docs/host/design.md` diff from Slice 0 implementation
- implementation artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice0-implementation-codex.md`
- accepted plan: `docs/host/wu-dur-obs-cm-closeout-plan.md` (commit `c1e9de3f`)
- control doc: `docs/host/issues-implementation-control.md`
- reviewer: AgentMiMo
- stance: adversarial design review

## Verdict

**pass-with-findings**

## Summary

Slice 0 写回覆盖了 accepted plan appendix 的全部 contract shape。核心数据结构（`RunnerCallInputAssemblyManifest`、`RunnerCallMessageEntry`、`ProjectorMetadata`、`ToolCallArgumentsAtom`、`CompactorRunnerCallIdentity`）均以正式字段表写入 design.md，包含字段名、类型、必填性、语义、digest/ref boundary 与 validation rule。`RunnerCallReconstructionDiagnostic` 与 Tool Trace signal 的语义、状态枚举、reason 枚举、consumer boundary 均已写入，但 diagnostic 字段未以正式类型表呈现。inline/ref boundary 正确复用 `payload_inline_threshold_bytes`，descriptor kinds 明确。无 blocking finding。design.md 可作为 Slice 1-7 的设计真源。

## Blocking Findings

无。

## Non-blocking Findings

### F-01: RunnerCallReconstructionDiagnostic 缺少正式字段类型表

- location: design.md 14.1 节，RunnerCallReconstructionDiagnostic 描述段落
- evidence: design.md 叙述列出了 diagnostic 字段名（`status`、`reason`、`missing_atom_kind`、`missing_ref_kind`、`missing_ref`、`observed_count`、`expected_count`、`observed_digest`、`expected_digest`、`consumer_boundary`）和各字段语义/必填规则，但没有像 `RunnerCallInputAssemblyManifest`、`ToolCallArgumentsAtom` 等结构一样提供正式字段表（field / type / required / semantics / validation rule）。plan appendix 有完整类型表。
- severity: non-blocking。语义已足够清晰，implementation 可从 plan appendix 获取类型；但若 Slice 1-7 implementation 只读 design.md 而不回查 plan，可能产生类型推断偏差。
- recommendation: 在 design.md 14.1 节为 `RunnerCallReconstructionDiagnostic` 增加正式字段表，与 plan appendix 对齐。

### F-02: RUNNER_CALL_INPUT_ASSEMBLED hot payload 无正式字段表

- location: design.md 13.3 节 canonical event matrix 行 + 23.1 节首段
- evidence: hot payload 字段以叙述形式列出（`session_id`、`host_run_id`、`attempt_id`、`execution_id`、`runner_call_index`、`runner_call_kind`、`runner_call_trigger_reason`、`manifest_payload_ref`、`manifest_digest`、`manifest_schema_version`、`validation_status`），并给出 validation rule（`manifest_digest` 必须等于 manifest body canonical JSON digest；scope fields 必须与 manifest identity fields 一致）。plan appendix 有明确类型表。
- severity: non-blocking。字段列表完整，validation rule 清晰，canonical event matrix 中其它事件也采用叙述风格。但 hot payload 是 `RUNNER_CALL_INPUT_ASSEMBLED` 的关键 contract，正式表可减少 implementation 歧义。
- recommendation: 在 design.md 23.1 节或 13.3 节为 `RUNNER_CALL_INPUT_ASSEMBLED` hot payload 增加正式字段表。

### F-03: ProjectorMetadata purpose 枚举未列出完整允许值

- location: design.md 23.1 节 ProjectorMetadata 表格 `purpose` 字段
- evidence: `purpose` 字段描述为 "closed string enum"，validation rule 为 "must be one of design-approved purposes"。同节后文列出了第一版 `purpose` 值：`ordinary_run_input`、`tool_continuation_input`、`post_compaction_input`、`compactor_proposal_input`、`retry_replay_resume_input`、`forced_answer_input`、`length_continuation_input`。但表格 validation rule 列本身未内联这些值。
- severity: non-blocking。值在同节后文可找到，且 plan appendix 同样用 "allowed values defined in design writeback" 表述。但表格与枚举定义分离可能增加查找成本。
- recommendation: 考虑在 ProjectorMetadata 表格 `purpose` 行的 validation rule 中引用枚举值列表的位置，或直接内联。

## Acceptance Criteria Checklist

| # | criterion | status | evidence |
|---|---|---|---|
| 1 | `RunnerCallInputAssemblyManifest` 字段名、类型、必填性、语义、digest/ref boundary、validation rule | PASS | design.md 23.1 节完整字段表，23 个字段全部覆盖 |
| 2 | `RunnerCallMessageEntry` 字段名、类型、必填性、语义、digest/ref boundary、validation rule | PASS | design.md 23.1 节完整字段表，10 个字段全部覆盖 |
| 3 | `ProjectorMetadata` 字段名、类型、必填性、语义、digest/ref boundary、validation rule | PASS | design.md 23.1 节完整字段表，6 个字段全部覆盖 |
| 4 | `ToolCallArgumentsAtom` 字段名、类型、必填性、语义、digest/ref boundary、validation rule | PASS | design.md 13.3 节完整字段表，13 个字段全部覆盖 |
| 5 | Tool Trace signal 字段 | PASS | design.md 14.1 节完整字段表，11 个字段全部覆盖，含 ProjectorMetadataSummary 字段 |
| 6 | `RunnerCallReconstructionDiagnostic` 字段 | PASS-with-F-01 | 字段名、语义、必填性、枚举值均覆盖；缺正式类型表 |
| 7 | `CompactorRunnerCallIdentity` 字段名、类型、必填性、语义、digest/ref boundary、validation rule | PASS | design.md 25 节完整字段表，9 个字段全部覆盖 |
| 8 | inline/ref boundary 复用 `payload_inline_threshold_bytes` | PASS | design.md 13.1 节明确四种 descriptor kind 与 inline/ref 判定规则 |
| 9 | descriptor kinds 明确 | PASS | `runner_call_input_manifest`、`runner_call_projection_artifact`、`tool_call_arguments_json`、`tool_call_semantic_query_text`、`compactor_input_projection` 均在 13.1 节明确 |
| 10 | `RUNNER_CALL_INPUT_ASSEMBLED` 无 Run/Attempt state side effect | PASS | 13.3 节矩阵行 + 23.1 节首段双重声明：不参与 terminal decision、recovery scan、memory projection、dispatch decision 或 lifecycle transition |
| 11 | `RunnerCallKind` / `RunnerCallTriggerReason` 无重叠并覆盖 required paths | PASS | 23.1 节两个完整枚举表 + "forced answer、length continuation、retry/replay/resume 只作为 trigger reason，不挤入 kind" 显式声明 |
| 12 | Engine vs Host ownership 清楚 | PASS | 23.1 节明确 "Engine 只产出 execution-local observations；Host 产出 runner_call_index、manifest refs/digests、source refs 和 EventLog / payload descriptor" |
| 13 | Compactor parent/self identity 清楚，complement CONTEXT_COMPACTED | PASS | 25 节 "CompRunnerCallIdentity 补充 CONTEXT_COMPACTED，不替代 compact truth" + 详细引用关系说明 |
| 14 | Tool Trace 是 read model | PASS | 14.1 节 "read-only signal" + "不得读取旧 provider request、EngineRunner 内存、当前 prompt builder 代码或重新运行 compact material selection" |
| 15 | LLM-facing boundary 自解释且不暴露内部标识 | PASS | 24.2 节明确禁止暴露 tool_call_id、EventLog id、payload ref、artifact ref、digest、cursor、projection checkpoint、policy 名称、Attempt/execution ledger、Projector metadata |
| 16 | 无 hidden messages dump 风险 | PASS | 23.1 节 "manifest 不内联 full messages、完整 prompt、完整 compact material"；RunnerCallMessageEntry 只有 content_digest + content_size_bytes |
| 17 | 无 untyped bag/extra payload 风险 | PASS | 23.1 节 "provider-specific assistant tool_calls / reasoning_content 不得以 raw provider dict、untyped payload bag 或 Python object 进入 Host manifest"；provider state deferred 用 `provider_specific_atom_deferred` limited-signal |
| 18 | 无兼容旧 schema 风险 | PASS | plan 要求 fresh schema only；design.md 写回未引入兼容读取路径 |

## Residual Risks / Open Questions

1. **Provider-specific atom deferred scope**: `provider_specific_atom_deferred` 覆盖了 raw provider state 的场景，但具体 typed provider atom 何时纳入取决于后续 WU-ENG provider contract work。Slice 2 实现时若 Engine provider contract 仍无 typed 字段，manifest 中 `provider_tool_calls_digest` / `reasoning_content_digest` 将始终为 null，此时 trace 必须稳定输出 `provider_specific_atom_deferred`。这不是 blocking risk，但 Slice 2 plan 需明确该 fallback 行为。

2. **ProjectorMetadata 第一版枚举稳定性**: `projector_id` 和 `purpose` 的第一版枚举值在 design.md 中列出，但后续 projector 新增时需要同步更新枚举表。Slice 2-3 实现时应确保枚举定义与 design.md 对齐，不自行扩展。

3. **Diagnostic field type alignment**: 非阻塞 finding F-01 若在 Slice 1 前修复，可消除 implementation 只读 design.md 时的类型推断偏差。若不修复，implementation agent 需同时参考 plan appendix。

## Completion Report

```text
artifact path: docs/reviews/wu-dur-obs-cm-closeout-design-review-mimo.md
verdict: pass-with-findings
blocking findings: 0
non-blocking findings: 3
residual risks: 3 (provider atom deferred scope, projector enum stability, diagnostic field type alignment)
next gate readiness: ready for Slice 1-7 implementation dispatch
```
