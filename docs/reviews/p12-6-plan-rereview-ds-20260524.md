# P12.6 Plan Re-Review — DS Adversarial Re-Review

## Review Metadata

- **Reviewer**: DS (Design Reviewer, role-scoped plan re-review)
- **Target**: `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` (post-fix, Codex patch applied)
- **Gate**: Plan re-review, NOT implementation
- **Timestamp**: 2026-05-24T20:00:45+08:00
- **Truth sources**: `docs/host/design.md` §1, §24, §25; `docs/host/implementation-control.md` Phase 12.6
- **Prior review artifacts**:
  - `docs/reviews/p12-6-plan-review-mimo-20260524.md` (PASS, findings F1, F2)
  - `docs/reviews/p12-6-plan-review-ds-20260524.md` (PASS conditionally, findings F1, F2, F3)
  - `docs/reviews/p12-6-plan-review-controller-adjudication-20260524.md` (accepted P-F1 through P-F5)
  - `docs/reviews/p12-6-plan-fix-codex-20260524.md` (fix artifact, P-F1 through P-F5)
- **Instruction**: Re-review only accepted findings fixes. Do NOT modify source code, tests, README, control_doc, design_doc, or plan.

## Scope

Verify that:

1. P-F1 through P-F5 are fixed in the plan artifact.
2. Plan remains handoff-ready / code-generation-ready.
3. No new scope creep, public API drift, Engine/Fins/Service/UI changes introduced by the fixes.
4. No compatibility aliases, Any/object/extra payload/lazy seam introduced.
5. Tests are not weakened; test coverage requirements not reduced.

## P-F1 Fix Verification — §7 Master Allowlist vs. Slice 3 Local Allowlist

**Claim**: Added `dayu/host/evidence.py` and `tests/host/test_toolruntime_accept_barrier.py` to §7 master lists.

**Evidence**:
- Plan §7 line 267: `dayu/host/evidence.py` present in Host source list.
- Plan §7 line 291: `tests/host/test_toolruntime_accept_barrier.py` present in tests list.
- Slice 3 allowlist (lines 462, 467) entries now match §7 entries.
- Cross-check: all 7 slices' local allowlists are subsets of §7 master lists. No remaining inconsistencies.

**Verdict**: FIXED. §7 is now the canonical exhaustive allowlist; all slice-local allowlists are consistent subsets.

## P-F2 Fix Verification — Slice 1 Old CompactionRequest Test Migration Scope

**Claim**: Expanded Slice 1 allowed tests to cover all existing files that directly construct or assert old `CompactionRequest` fields; explicit migration requirement with no deprecated aliases.

**Evidence**:
- Slice 1 allowed test files (lines 357-366) now include all 10 test files + `fake_compaction.py` that reference old `CompactionRequest` fields.
- Slice 1 具体修改 (lines 377-378): "Slice 1 必须同步迁移所有现有直接构造或断言旧 `CompactionRequest` 字段的测试引用...不得保留 deprecated alias、compat wrapper、old-field default 或 test-only 兼容路径。"
- Slice 1 具体修改 (lines 378-379): "已知需要在 Slice 1 一并迁移的现有测试边界包括 contract、LLM prompt/parser、compaction operation、dispatch scheduler、engine ingest mapping、compact artifact store、context compact event、memory projection、run input builder 与 fake compactor。"
- Slice 1 具体修改 (line 379): "若实施时 `rg` 发现同一旧字段还存在于 §7 主清单内其他测试文件，必须在 Slice 1 同步迁移；若出现在 §7 外文件，立即停下报告 Controller。"
- Slice 1 verification commands (lines 389-394) cover all listed test files.
- No deprecated alias, compat wrapper, old-field default, or test-only compatibility path is permitted anywhere in the plan.

**Verdict**: FIXED. Slice 1 now has explicit, exhaustive test migration scope and a fail-safe discovery instruction for implementation agent.

## P-F3 Fix Verification — Slice Dependency Graph

**Claim**: Added explicit acyclic dependency graph before slice details, with per-slice dependency notes.

**Evidence**:
- Plan §8.0 (lines 322-344) contains an explicit dependency graph:
  ```
  Slice 1 -> Slice 2 -> Slice 3 -> Slice 4 -> Slice 5
  Slice 1 -> Slice 2 -> Slice 6
  Slice 1-6 -> Slice 7
  ```
- Dependency notes explain WHY each edge exists (e.g., Slice 4 depends on Slice 1-3 for material pack, provenance map, evidence map, and label parse/validate helpers).
- Slice 6 dependency on only Slice 1+2 is explicitly noted, enabling parallel implementation with Slices 3-5.

**Verdict**: FIXED. Dependency graph is acyclic, explicit, and actionable.

## P-F4 Fix Verification — PromptLocalEvidenceMap Typed Contract

**Claim**: Added `PromptLocalProvenanceEntry` and `PromptLocalEvidenceMap` to §6.1 typed contracts, with stated relationship to `CompactMaterialPack.provenance_map`.

**Evidence**:
- Plan §6.1 line 110-111: `PromptLocalProvenanceEntry` defined with complete field list — prompt-local label, section, kind, canonical source refs, source EventLog refs, content digest, accepted evidence id (only for evidence entries), tool result/tool call event refs (only for evidence entries), payload/artifact refs, source locator refs, chunk parent label, chunk ordinal. Non-evidence entries must have empty evidence-only fields; no untyped bag.
- Plan §6.1 line 112: `PromptLocalEvidenceMap` defined as `dict[PromptLocalMaterialLabel, PromptLocalProvenanceEntry]` evidence-only typed view. Key constraint: only `E` section labels or evidence chunk labels. Each entry must have accepted evidence id, tool result event ref, tool call event ref, and digest-checked payload/artifact ref. Explicitly stated as NOT a second source of truth — must be derived from or share immutable values with `CompactMaterialPack.provenance_map`.
- Slice 3 具体修改 (line 477): "建立 `PromptLocalEvidenceMap`：LLM label 到 canonical accepted evidence id、tool result event、tool call event、payload / artifact refs" — consistent with §6.1 definition.

**Verdict**: FIXED. Cross-slice contract for evidence provenance mapping is now typed and owned.

## P-F5 Fix Verification — Prompt-Local Label Generation Owner and Algorithm

**Claim**: Defined label generation owner, algorithm, shared constants, and parser validation reuse.

**Evidence**:
- Plan §6.2 lines 132-133: "Prompt-local label 生成 owner 固定为 `dayu/host/compact_material.py` 的模块级私有 helper，不得在 parser、prompt renderer 或 tests 中重复手写规则。若最终文件名选择 `dayu/host/compaction_material.py`，同一 owner 规则随文件名迁移。"
- Plan §6.2 lines 136-137: Section prefix shared constants — `CURRENT_INPUT_ANCHOR -> C`, `HISTORY_INPUT -> H`, `EVIDENCE_INPUT -> E`, `STABLE_INPUT -> S`.
- Plan §6.2 lines 137-138: Label format — `{section_prefix}{ordinal}` for normal blocks (ordinal starts at 1, per-section increment); `{section_prefix}{ordinal}.{chunk_ordinal}` for evidence chunks (chunk_ordinal starts at 1, all chunks share same canonical evidence id).
- Plan §6.2 line 139: "current input anchor V1 只能生成 `C1`；若实现需要第二个 current anchor，必须停下报告 Controller。"
- Plan §6.2 line 140: "parser validation 必须复用同一组模块级共享常量和私有 parse / validate helper 校验 label 格式、section membership、chunk parent 与 ordinal，不得另写不一致的 regex / magic string。"

**Verdict**: FIXED. Label generation is owned, deterministic, and parser-verifiable.

## Boundary Integrity Re-Check (Post-Fix)

### Public API Drift

§5 unchanged. All stop conditions reference public API checks. No new files in allowed-modification lists that touch `api.py`, `open_host.py`, or public surface. **Clean.**

### Engine/Fins/Service/UI Changes

§3.2 不做列表 unchanged. §7 禁止修改列表 unchanged. No new files cross these boundaries. **Clean.**

### Compatibility Aliases

§3.2 explicitly rejects compat wrappers/re-exports. Slice 1 explicitly rejects deprecated aliases, compat wrappers, old-field defaults, and test-only compatibility paths. Fix P-F2 strengthened this position. **Clean.**

### Any/Object/Extra Payload/Lazy Seam

§4 unchanged. New typed contracts in §6.1 use strict types (`dict[PromptLocalMaterialLabel, PromptLocalProvenanceEntry]`, typed dataclass fields, enum-based section/kind). No untyped bags, no `Any`, no `object`, no `hasattr`/`getattr` escape hatches. **Clean.**

### Test Strength

Slice 1 test requirements were EXPANDED (P-F2), not reduced — 10 test files now explicitly required to migrate in Slice 1. Test assertions remain contract-level (assert on JSON keys, section mapping, label format, canonical mapping, fail-closed). No test was removed or weakened. **Clean.**

### Scope Creep Check

Fixes P-F1 through P-F5 are all within the plan's original §3.1 范围内 scope:
- P-F1: file list consistency (documentation fix)
- P-F2: test migration explicitness (documentation fix)
- P-F3: dependency graph (documentation fix)
- P-F4: typed contract gap fill (already implied by §6.5 usage)
- P-F5: label algorithm specification (already implied by §6.2 examples)

No new features, no new abstractions, no new slices, no new file ownership, no new public contracts. **Clean.**

## Slice Allowlist Cross-Check (Post-Fix)

All 7 slice local allowlists verified as subsets of §7 master lists:

| Slice | Source files in §7? | Test files in §7? | New files justified? |
|-------|---------------------|-------------------|---------------------|
| Slice 1 | Yes (3 of 15) | Yes (10 of 13 + fake) | N/A |
| Slice 2 | Yes (5 of 15) | Yes (2 of 13 + 1 new) | `test_compact_material.py` (new, listed in §7) |
| Slice 3 | Yes (4 of 15) | Yes (3 of 13) | N/A |
| Slice 4 | Yes (3 of 15) | Yes (2 of 13) | N/A |
| Slice 5 | Yes (6 of 15) | Yes (4 of 13) | N/A |
| Slice 6 | Yes (3 of 15) | Yes (2 of 13) | N/A |
| Slice 7 | Yes (0 source) | Yes (2 of 13) | N/A |

No slice-local allowlist exceeds §7. **Clean.**

## Open Questions

无阻塞 open question。以下为确认项：

1. **OQ1** (carried from DS original review): Slice 4 的 prompt asset 修改是否涉及 JSON schema 结构变更？plan 仍未明确 schema 变更的具体文件位置（嵌入 prompt markdown 还是代码中定义），但 implementation agent 可从现有 prompt asset 和 Slice 4 的 `_compaction_request_prompt_block` 修改指南推断。不阻塞。

2. **OQ2** (new): Slice 1 now explicitly requires migration of ALL existing test files that reference old `CompactionRequest` fields. The `rg` discovery clause ("若实施时 `rg` 发现同一旧字段还存在于 §7 主清单内其他测试文件") is a sensible safety net, but the blast radius is intentionally large. Implementation agent should budget for this.

## Residual Risks

1. **大 session rebuild performance** (unchanged): plan §11 标记为后续 hardening。**追踪**: implementation-control.md Phase 12.6 退出后 Open Questions 区。

2. **V1 relevance strategy Host-neutral** (unchanged): plan §11 标记为设计限制。**追踪**: 后续 Fins / retrieval owner phase。

3. **Reactive multi-pass budget 耗尽 fail closed** (unchanged): Slice 5 测试已覆盖。**追踪**: Slice 5 review gate。

4. **Label-to-provenance mapping 扩大 artifact 面** (unchanged): Slice 1 测试 `test_context_compacted_payload_records_mapping_refs_not_raw_prompt` 已覆盖。**追踪**: Slice 1 + Slice 4 review gate。

5. **Filename ambiguity** (`compact_material.py` vs `compaction_material.py`): Codex fix artifact 标记为 residual risk。Plan §6.2 已说明 "同一 owner 规则随文件名迁移"。实现时需选定一个并保持一致。低风险，不阻塞。

## Conclusion

**PASS**

All five controller-accepted findings (P-F1 through P-F5) are verified fixed in the plan artifact. The plan remains handoff-ready and code-generation-ready.

No new scope creep, public API drift, Engine/Fins/Service/UI changes, compatibility aliases, Any/object/extra payload/lazy seam, or weakened tests were introduced by the fixes. The fixes are documentation-only clarifications that strengthen the plan's implementability without altering its design decisions.

The plan can proceed to implementation.
