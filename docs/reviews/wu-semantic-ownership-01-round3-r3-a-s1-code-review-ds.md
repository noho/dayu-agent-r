# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S1

## Scope

- Mode: current changes (workspace, base: plan acceptance commits 4a282850 / 41bd6ca9)
- Branch: phaseflow/host-issues-control
- Output file: docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-ds.md
- Review date: 2026-07-12
- Included scope:
  - New: `dayu/host/_runner_call_manifest.py`, `dayu/host/durable/payload_resolution.py`
  - Modified: `dayu/host/run_input.py`, `dayu/host/engine_ingest.py`, `dayu/host/compaction_operation.py`, `dayu/host/tool_trace.py`, `dayu/host/durable/tool_trace.py`, `dayu/host/payload_resolution.py`, `dayu/host/_execution_config_projection.py`, `dayu/host/compact_material.py`
  - New tests: `tests/host/test_runner_call_hot_payload_contract.py`, `tests/host/test_durable_payload_integrity.py`
  - Modified tests: `tests/host/test_payload_store.py`, `tests/host/test_effective_execution_config.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_compaction_operation.py`, `tests/host/test_tool_trace_projection.py`, `tests/host/test_tool_trace_queries.py`, `tests/host/test_compact_material.py`, `tests/host/test_terminal_payload.py`, `tests/host/test_host_production_stress.py`
  - Docs: `docs/host/design.md`, `dayu/host/README.md`, `tests/README.md`
- Excluded scope: S2-S8 implementation, `dayu/config/`, CLI, Fins, Engine provider, schema DDL/migration, control docs
- Parallel review coverage: 无（全部文件由主 reviewer 直接走读）
- Independent re-verification:
  - Focused S1 matrix: `392 passed` (不含 test_outbox_projection.py 的 14 个，合计 406)
  - Stress: `4 passed, 1 failed`; 失败为 `test_scheduler_liveness_long_run_mixed_flow_stress`（S3 范围 DR-009 retry exhaustion → scheduler close，非 S1 回归）；runner-call stress 通过且 accepted count 断言为 12
  - pyright: `0 errors, 0 warnings, 0 informations`
  - Source scans 与 git diff --check 复核通过

## Findings

### 1-未修复-低-run_input.py 中 iteration_index 硬编码为 None 丢失（未来） manifest 内值时无诊断

- **入口/函数**: `run_input._runner_call_manifest_hot_payload()`
- **文件(行号)**: `dayu/host/run_input.py:4255`（`iteration_index=None`）
- **输入场景**: 未来如有 code path 在普通 RunInput manifest 中写入非 None 的 `iteration_index`（例如某些 tool-continuation 场景被错误路由到普通 RunInputBuilder），旧代码会把 manifest 中的 `iteration_index` 透传进 hot payload，新代码会静默替换为 `None`。
- **实际分支**: `RunnerCallHotAtoms(iteration_index=None, ...)` 无条件提交 `None`。
- **预期行为**: 如果 S1 的语义是“普通 RunInput 绝不应有 iteration_index”，则应在 owner 层校验 manifest 中的 `iteration_index` 为 None 并 fail closed，而不是静默丢弃。
- **实际行为**: `_validate_hot_atoms` 允许 `iteration_index=None`（可选非负整数检查放行），不会因为 manifest 中误带了 `iteration_index` 而报错。
- **直接证据**: `dayu/host/_runner_call_manifest.py:290-293` 对 `iteration_index` 使用 `_require_optional_non_negative_int`，允许 None；`run_input.py` 传给 atoms 的值为 `iteration_index=None`，未读取 manifest 中的对应字段。
- **影响**: 极低。当前所有已知 code path 下普通 RunInput manifest 的 `iteration_index` 必定为 None；只有在未来代码错误路由时才会触发隐式数据丢失。
- **建议改法和验证点**: 在 `run_input._runner_call_manifest_hot_payload()` 中增加一行 `_require_optional_non_negative_int(manifest.get("iteration_index"), field_name="manifest.iteration_index")` 并将该值传给 `RunnerCallHotAtoms`，或直接断言 `manifest.get("iteration_index") is None`（fail closed）；或接受当前行为并在设计文档中明确“普通 RunInput manifest 禁止携带 iteration_index，owner 不负责二次校验 manifest 字段冗余度”。无论哪种，需要显式决策而不是静默覆盖。
- **修复风险（低）**:
- **严重程度（低）**:

### 2-未修复-低-compact_material.py 中 previous_answer_anchor_block_text / validate_previous_compacted_view_pair / ConversationCompactOutputVNext 等新增使用不在 S1 contract 中明确列出

- **入口/函数**: `compact_material.py` 中多处新增的 `validate_previous_compacted_view_pair(...)` 调用与 `previous_answer_anchor_block_text(...)` 调用
- **文件(行号)**: `dayu/host/compact_material.py:407, 996, 1005, 1035, 1196, 2047, 2068, 2082, 2125, 2162, 2169, 2199`
- **输入场景**: S1 accepted scope 明确说 "compact_material wrong tool_call_event_ref fallback" 且 "No S2-S8 behavior changes"。但当前 workspace 对 compact_material.py 的修改不仅包含 `_accepted_tool_evidence_delta_blocks` 的 fail-closed 改动，还新增了 `validate_previous_compacted_view_pair`、`previous_answer_anchor_block_text`、`parse_context_compacted_semantic_payload`、`ConversationCompactOutputVNext` 的使用，这些调用分布在多个 compact material 构建路径中。
- **实际分支**: 在 `_accepted_tool_evidence_delta_blocks` 之外，`validate_previous_compacted_view_pair` 被用于 pre-dispatch、readable view 构造等多条路径。
- **预期行为**: S1 的 compact_material 改动应只限定于 `_accepted_tool_evidence_delta_blocks` 的 fail-closed 重构；其他 compact material 逻辑变更应属于独立 slice。
- **实际行为**: compact_material.py 中同时包含了若干与 evidence provenance 不直接相关的 validation 调用新增。
- **直接证据**: `grep -n "validate_previous_compacted_view_pair\|previous_answer_anchor_block_text\|parse_context_compacted\|ConversationCompactOutputVNext" dayu/host/compact_material.py` 命中 13 行，分布在 `_accepted_tool_evidence_delta_blocks` 之外的多条 code path。
- **影响**: 低——这些改动不太可能引入回归（均由已有 typed helper 和 typed contract 支撑），但它们是未在 S1 contract 中声明的行为变更，controller 和 reviewer 对 S1 的 scope 判定存在信息不对称。
- **建议改法和验证点**: 核实这些 compact material 调用是否为 S1 工作时必要的依赖（例如 R3-F 提交已引入这些 import 而 S1 只是调整了 import 组织），或是否属于独立 slice 应拆分。如果确实属于 S1 范围，在 implementation report 中补充说明这些变更的动机和影响范围。
- **修复风险（低）**:
- **严重程度（低）**:

## Open Questions

1. compact_material.py 中 `validate_previous_compacted_view_pair`、`previous_answer_anchor_block_text` 等新增调用是否属于 R3-F baseline 已存在的代码路径，当前 workspace diff 只是 import 重组？如果是，则 finding 2 不成立；如果不是，需要明确这些变更的 S1 scope 归属。

## Residual Risk

- **Stress test flakiness**: `test_scheduler_liveness_long_run_mixed_flow_stress` 在独立验证中失败（S3 范围 DR-009 retry exhaustion → scheduler close），与 S1 无关。完整 stress suite 在 controller 验证中 serially 通过。风险：该 stress 在 CI 中可能间歇失败，建议在 S3 修复前标记为 known-flaky。
- **旧数据兼容性**: 按 S1 设计，不提供旧 descriptor/row 兼容性 fallback。如果部署前已有损坏的 descriptor、row 或 artifact，会在首次读取时 fail closed。风险：运维侧需要部署前坏数据审计，S1 不覆盖。
- **Tool Trace cold query 成本**: 300 条 metadata 的完整解析发生在显式 read-only query 路径，成本已被 owner test 覆盖。当前不引入分页 metadata 子协议，超大量（>1000）metadata 场景下 query 延迟未测试。
- **文档与代码一致性**: `dayu/host/README.md` 和 `docs/host/design.md` 的更新描述了 S1 contract，但未提及 compact_material.py 中 `_accepted_tool_evidence_delta_blocks` 之外的 validation 变更。如果这些变更确属 S1，文档需要补充。

## Conclusion

**PASS** — 未发现阻塞级（中/高/严重）finding。

S1 实现正确完成了三项核心任务：
1. runner-call hot payload 的统一 owner 边界（`_runner_call_manifest.py`），三个 producer 共享同一 bounded contract，hot payload 不再包含 `projector_metadata_summary` 数组；
2. durable JSON descriptor 完整性 owner（`durable/payload_resolution.py`），所有 consumer 委托同一 resolver，覆盖 caller/descriptor/row/artifact 的完整 digest/size/format/canonicality 校验链；
3. compact material 的 tool_call_event_ref 从 fallback 改为 fail-closed，通过 `project_accepted_tool_result` 验证 request atom identity。

类型系统干净（0 pyright errors），392+14=406 focused tests 全部通过，runner-call stress 证明 12 个 accepted calls，tamper matrix 覆盖所有已知篡改维度。

两个低严重度 finding 均不影响 merge 判断：一个关于 `iteration_index` 静默覆盖的防御性校验缺失，另一个关于 compact_material.py 中超出声明的 validation 调用。建议 controller 裁决时确认 finding 2 的 scope 归属。
