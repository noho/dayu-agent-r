# P12.6 Plan Re-review — MiMo

## Gate

Plan re-review gate。验证 Codex plan fix 是否正确修复了 P-F1 到 P-F5，且 plan 仍保持 handoff-ready / code-generation-ready，未引入 scope creep、public API drift、Engine/Fins/Service/UI 变更、兼容性 alias、Any/object/extra payload/lazy seam 或弱化测试。

## Reviewed Artifacts

- `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md`（fix 后版本）
- `docs/reviews/p12-6-plan-review-mimo-20260524.md`（首次 review）
- `docs/reviews/p12-6-plan-review-ds-20260524.md`（首次 review）
- `docs/reviews/p12-6-plan-review-controller-adjudication-20260524.md`（controller 裁决）
- `docs/reviews/p12-6-plan-fix-codex-20260524.md`（Codex fix 报告）

## P-F1 到 P-F5 修复验证

### P-F1: §7 主清单与 Slice 3 局部清单不一致

**Controller 要求**: 将 `dayu/host/evidence.py` 和 `tests/host/test_toolruntime_accept_barrier.py` 补入 §7 主清单。

**验证**: plan §7 Host source 列表（行 267）包含 `dayu/host/evidence.py`；§7 测试列表（行 291）包含 `tests/host/test_toolruntime_accept_barrier.py`。两处清单现在一致。

**结论**: 已修复。

### P-F2: Slice 1 未显式覆盖旧 CompactionRequest 测试迁移

**Controller 要求**: 扩展 Slice 1 允许测试列表，覆盖所有直接构造或断言旧 `CompactionRequest` 字段的测试文件；明确要求迁移到新 contract，不保留 deprecated alias。

**验证**: Slice 1 允许修改文件（行 357-366）列出了 10 个测试文件：`test_compaction_contract.py`、`test_llm_compaction.py`、`test_compaction_operation.py`、`test_context_compact_events.py`、`test_compact_artifact_store.py`、`test_dispatch_scheduler.py`、`test_engine_ingest_mapping.py`、`test_memory_projection.py`、`test_run_input_builder.py`、`fake_compaction.py`。行 377 明确要求"不得保留 deprecated alias、compat wrapper、old-field default 或 test-only 兼容路径"。行 378 还要求实施时用 `rg` 扫描旧字段残留，发现 §7 外文件立即停下报告 Controller。

**结论**: 已修复。

### P-F3: Slice 依赖顺序未显式声明

**Controller 要求**: 增加显式依赖图和 per-slice 依赖说明。

**验证**: §8.0（行 322-345）包含完整的 acyclic 依赖图和 7 条 per-slice 依赖说明。每个 Slice 开头都有"依赖"字段（Slice 1 行 351、Slice 2 行 406、Slice 3 行 458、Slice 4 行 505、Slice 5 行 552、Slice 6 行 607、Slice 7 行 654）。

**结论**: 已修复。

### P-F4: `PromptLocalEvidenceMap` 未纳入 §6.1 typed contracts

**Controller 要求**: 在 §6.1 增加 `PromptLocalProvenanceEntry` 和 `PromptLocalEvidenceMap` 的 typed contract 定义，说明与 `CompactMaterialPack.provenance_map` 的关系。

**验证**: §6.1（行 110-112）定义了 `PromptLocalProvenanceEntry`（包含 prompt-local label、section、kind、canonical source refs、source EventLog refs、content digest、accepted evidence id、tool result / tool call event refs、payload / artifact refs、source locator refs、chunk parent label 与 chunk ordinal，非 evidence entry 的 evidence-only 字段必须为空）和 `PromptLocalEvidenceMap`（`dict[PromptLocalMaterialLabel, PromptLocalProvenanceEntry]` 的 evidence-only typed view，从 `CompactMaterialPack.provenance_map` 派生）。`CompactMaterialPack`（行 112）明确说明 `provenance_map` 是完整映射，`PromptLocalEvidenceMap` 是其中 evidence labels 的受限子集。

**结论**: 已修复。

### P-F5: Prompt-local label 生成 owner 和算法未指定

**Controller 要求**: 定义 label 生成 owner 为 `dayu/host/compact_material.py` 模块级私有 helper；定义格式和共享常量。

**验证**: §6.2（行 132）声明"Prompt-local label 生成 owner 固定为 `dayu/host/compact_material.py` 的模块级私有 helper"。行 136-140 定义了完整的生成算法：section prefix 共享常量映射、普通 block label 格式 `{section_prefix}{ordinal}`、evidence chunk label 格式 `{section_prefix}{ordinal}.{chunk_ordinal}`、current input anchor 只能生成 `C1`、parser validation 必须复用同一组模块级共享常量和私有 parse / validate helper。

**结论**: 已修复。

## Scope Creep / API Drift / 约束违反检查

重新通读 fix 后 plan 全文，检查以下维度：

| 检查维度 | 结论 |
|---|---|
| scope creep（新增不在 P-F1-P-F5 范围内的功能或模块） | 未发现。fix 只增加了清单对齐、依赖图、类型定义和 label 算法声明。 |
| public API drift | 未发现。§5 禁止修改清单不变，无新增 public surface。 |
| Engine / Fins / Service / UI 变更 | 未发现。§7 禁止修改清单不变，新增内容全在 Host 内部。 |
| 兼容性 alias / wrapper / re-export | 未发现。Slice 1 行 377 仍明确禁止 deprecated alias 和 compat wrapper。 |
| `Any` / `object` / extra payload / lazy seam | 未发现。§4 编码护栏不变，§6.1 新增类型均为严格 typed dataclass。 |
| 弱化测试 | 未发现。Slice 1 测试迁移范围扩大，要求更严格（行 377-378）。新增 §6.1 类型定义为测试提供了更明确的断言目标。 |
| 设计真源漂移 | 未发现。所有 fix 均与 `docs/host/design.md` §1/§24/§25 和 controller adjudication 一致。 |

## Open Questions

无新增 open questions。Codex fix 报告中提到的三个 residual risks（文件名二选一、Slice 1 测试迁移爆炸半径、`PromptLocalProvenanceEntry` 类型严格性）均为实施阶段 review 关注点，不阻塞 plan handoff。

## Residual Risks

1. **文件名二选一**: plan 仍允许 `compact_material.py` 或 `compaction_material.py`，implementation 必须选一个。风险低，实施时选定即可。
2. **Slice 1 测试迁移爆炸半径**: 10 个测试文件 + `rg` 扫描可能发现更多。这是 fix 的预期效果，不是缺陷。实施 agent 应先跑 `rg` 确认完整范围。
3. **`PromptLocalProvenanceEntry` 类型严格性**: plan 定义了字段，实施时需确保 frozen dataclass + slots，不引入 untyped bag。实施 review gate 已覆盖。

以上均为实施阶段可控风险，不阻塞 plan handoff。

## Conclusion

**PASS**

P-F1 到 P-F5 全部正确修复。fix 后 plan 仍保持 handoff-ready 和 code-generation-ready，未引入 scope creep、public API drift、Engine/Fins/Service/UI 变更、兼容性 alias、Any/object/extra payload/lazy seam 或弱化测试。plan 可交由 implementation agent 按 slice 顺序执行。
