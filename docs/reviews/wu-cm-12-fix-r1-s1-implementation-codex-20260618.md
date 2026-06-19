# WU-CM-12-FIX-R1 Slice 1 Implementation Report

## 结论

Slice 1 已完成。实现只修改 compact input DTO guard 与默认 accepted evidence material chunking；未进入 review gate，未 commit、push 或 open PR。

## 变更文件

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_llm_compaction.py`
- `docs/reviews/wu-cm-12-fix-r1-s1-implementation-codex-20260618.md`

## 关键决策

- `CurrentInputAnchorVNext.text` 从 bounded max-char 校验改为非空文本校验，删除 `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS`。
- `EvidenceReadableItemVNext.response_text` 从 bounded max-char 校验改为非空文本校验，删除 `EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS`。
- 保留 `MAX_VNEXT_*` output candidate / parser safety guard；这些 guard 保护 LLM-generated output accept barrier，不再用于 EventLog-derived input material legality。
- 默认 accepted evidence material 不再按 4096 字符拆分；一个 source evidence block 生成一个 `CompactEvidenceBlock` 和一个 provenance entry。
- 删除无生产调用方的 `_EvidenceChunk`、`_evidence_chunks`、`evidence_chunk_label` 与 `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS`，不保留未接入的显式 budget chunk helper。
- `validate_material_label` 仍保留对 `E1.1` 形式的解析能力，仅作为 label parser，不作为默认 evidence chunking 依据。

## 测试覆盖

- 长 current input 经 `build_compact_material_pack(...)` 后继续进入 `conversation_compact_input_vnext_from_material_pack(...)`，完整落入 `CurrentInputAnchorVNext.text`。
- 长 accepted evidence 经 material pack 与 vNext input 后保持单个 `E1`，`raw_result_text` 与 `response_text` 保持全文，无 `E1.1` / `E1.2`。
- 原大 evidence chunking 测试迁移为 no-default-chunk 断言：单 `E1`、全文 digest、payload / artifact / source locator provenance 保留，`chunk_parent_label` / `chunk_ordinal` 为 `None`。
- `LLMContextCompactor.prepare_compactor_proposal_run_input(...)` 覆盖长 current input 与长 evidence，不因 DTO 私有 cap 在 prepare path 失败。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_llm_compaction.py -q`
  - `79 passed in 0.43s`
- `source .venv/bin/activate && pyright dayu/host/compaction.py dayu/host/compact_material.py tests/host/test_compact_material.py tests/host/test_llm_compaction.py`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## README / Docs 决策

- 已读取 `dayu/host/README.md` 的 Agent 更新约束。当前改动不改变 `dayu.host` public API、开发接口、稳定架构边界或用户可见 Host 行为说明，不更新 Host README。
- 已读取 `tests/README.md` 的 Agent 更新约束。当前只迁移既有 Host compact material / LLM compaction 测试语义，不新增测试层级或运行方式，不更新 tests README。
- 本报告是本 Slice 要求的 docs artifact。

## 常量审计

- `CURRENT_INPUT_ANCHOR_VNEXT_TEXT_MAX_CHARS`：已从 production / tests 删除。
- `EVIDENCE_BLOCK_CHUNK_VNEXT_TEXT_MAX_CHARS`：已从 production / tests 删除。
- `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS`：已从 production / tests 删除。
- `_EvidenceChunk` / `_evidence_chunks` / `evidence_chunk_label`：已从 production 删除。
- `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`：仍保留在 `dayu/host/run_input.py`，这是 Slice 2 范围；Slice 1 未修改 run_input row limit。
- `MAX_VNEXT_*`：保留为 output parser safety guard，不是 EventLog-derived input material budget。

## Residual Risks

- 单条 accepted evidence 不再默认拆分后，极长 evidence 可能让 compactor input 超过上下文预算；这应由 Context Governance selection / fallback / fail-closed 处理，不在 DTO 字段 cap 中处理。
- Slice 2 的 accepted tool evidence row limit 仍未处理，后续必须在 `run_input.py` 范围内移除。
- 未修改 public API、durable schema、EventLog canonical semantics、Engine contract 或 WU-CM-13 reactive recovery。
