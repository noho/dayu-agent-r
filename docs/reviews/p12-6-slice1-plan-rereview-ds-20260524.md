# P12.6 Slice 1 Plan Re-review

## Gate

P12.6 Slice 1 plan-fix re-review. This artifact does not authorize implementation.

## Reviewed Target

- `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` (plan-fix revision, status: `PLAN_FIX_READY`)
- Plan-fix truth: `docs/reviews/p12-6-slice1-stop-controller-adjudication-20260524.md` accepted finding S1-PF1

## Review Scope

Verify that the plan-fix resolves S1-PF1 by establishing a coherent compile-safe ownership boundary for Slice 1 that:
- Deletes old `CompactionRequest` fields without deprecated aliases, compat wrappers, old-field defaults, or test-only compatibility
- Includes all direct production consumers in the same slice or reshapes slices coherently
- Maintains adequate tests and validation
- Has no scope creep beyond Host internals, no public API drift, no Engine/Fins/Service/UI changes, no weakened design goals

## Assumptions Tested

1. **A1**: The revised Slice 1 allowed files include all current direct production consumers of old `CompactionRequest` fields.
2. **A2**: The revised Slice 1 explicitly forbids compatibility paths (deprecated alias, compat wrapper, old-field default, test-only compatibility).
3. **A3**: The revised Slice 1 provides adequate test coverage for the migration boundary.
4. **A4**: The revised plan preserves design goals from `docs/host/design.md` §24 and §25.
5. **A5**: The revised slice dependency graph is coherent after reshuffling Slice 1 content.
6. **A6**: The revised plan does not expand scope beyond Host internals.

## Evidence

### E1: Direct Consumer Coverage

The stop-controller adjudication identified five direct production consumers outside the original Slice 1 scope:
- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_evidence.py`

The revised plan's Slice 1 "允许修改文件" list includes all five, plus `compaction_operation.py` (scoped to compile-break cleanup only). Code grep confirms these files currently reference the old fields (`accepted_evidence_envelopes`, `compact_raw_context_items`, `current_message_summary`, `CompactRawContextItem`, `input_event_refs`).

**Finding**: A1 holds. All five direct consumers are now in Slice 1 scope.

### E2: Compatibility Path Prohibition

The revised plan states:
- Slice 1 目标: "删除旧 LLM-facing ledger / envelope prompt 契约及其所有当前直接生产构造 / 消费点" (line 350)
- 停止条件: "需要兼容旧 request shape" (line 425)
- "不得通过 deprecated alias、compat wrapper、old-field default、test-only compatibility 或派生旧属性继续推进" (line 353)
- Slice 1 测试: `test_no_old_compaction_request_fields_remain_in_slice1_boundary` 断言 "防止旧字段通过 alias / default / derived property 回流" (line 408)
- `rg` no-match check explicitly searches for old field names in all production and prompt files (line 417)

**Finding**: A2 holds. The plan explicitly and repeatedly forbids all compatibility paths, with both test and `rg` verification.

### E3: Test Coverage

The revised Slice 1 defines 8 focused tests:
1. `test_compaction_request_llm_material_excludes_host_provenance_keys`
2. `test_compaction_request_material_pack_has_one_section_per_block`
3. `test_slice1_direct_consumers_construct_only_material_pack_request`
4. `test_context_governance_validates_prompt_local_labels_not_input_event_refs`
5. `test_llm_prompt_asset_uses_material_labels_not_input_event_refs`
6. `test_context_compacted_payload_records_mapping_refs_not_raw_prompt`
7. `test_old_result_preview_or_old_tool_fact_keys_fail_closed`
8. `test_no_old_compaction_request_fields_remain_in_slice1_boundary`

These cover: LLM material exfiltration prevention (1), section dedup (2), direct consumer construction (3), governance migration (4), prompt asset wording (5), payload hygiene (6), old-key fail-closed (7), and alias/default regression (8). The plan also requires migrating all existing test references to old fields.

Verification commands include pytest over all Slice 1 test files, pyright over all Slice 1 production and test files, and `rg` no-match check.

**Finding**: A3 holds. Test coverage is comprehensive for the Slice 1 boundary.

### E4: Design Goal Preservation

The plan-fix document states the preserved design goals explicitly (line 48-54):
- No EventLog ledger dump into compactor prompt
- No `result_preview` read, generation, fallback or prompt use
- No Host provenance keys as LLM semantic input
- No public API drift
- No deprecated aliases, compatibility wrappers, old-field defaults or test-only compatibility

The plan's "不做" section (line 60-71) and "Public Surface 禁止修改清单" (line 84-96) are unchanged from the original plan and continue to protect all external boundaries.

The Slice 1 `rg` check explicitly verifies old ledger/envelope terms don't persist in production/prompt files.

**Finding**: A4 holds. Design goals from §24 and §25 are preserved and enforced in Slice 1 verification.

### E5: Dependency Graph Coherence

The revised dependency graph:
```
Slice 1 -> Slice 2 -> Slice 3 -> Slice 4 -> Slice 5
Slice 1 -> Slice 6 (depends on Slice 1-2)
```

Slice 2 dependency declaration: "Slice 2 依赖 Slice 1 的 CompactMaterialPack、CompactSegmentSelection、PromptLocalProvenanceEntry、prompt-local label helper 与 compile-safe direct consumer migration" — all of these are produced by Slice 1's typed contract definitions.

Slice 1 explicitly defers full deterministic implementation to Slice 2: "完整 deterministic segment selection、already-represented 判断和 snapshot cursor repair 在 Slice 2 落地" — this is properly scoped.

Slice 6 depends on Slice 1-2 for contracts/material block view, consistent with its consolidation scope.

**Finding**: A5 holds. The dependency graph is coherent. The Slice 1 initial construction is properly labeled as non-deterministic scaffolding, with behavior refinement in Slice 2.

### E6: Scope Containment

The plan's "禁止修改" list (line 312-319) explicitly excludes:
- `dayu/engine/**`
- `dayu/fins/**`
- `dayu/runtime/config_loader.py`
- ScenePrepare owner files
- `dayu/host/api.py` public request/handle fields
- `dayu/host/open_host.py` public options fields
- `dayu/service/**`

Slice 1 stop conditions (line 422-428) include: "需要修改 Host public API / OpenHostOptions / SubmitFollowupRequest", "发现 §7 外生产文件仍直接构造 / 消费旧 CompactionRequest 字段", "需要新增 public API".

All Slice 1 allowed files are within `dayu/host/`, `tests/host/`, or `dayu/config/prompts/scenes/` (prompt asset only, not ConfigLoader schema).

**Finding**: A6 holds. No scope creep beyond Host internals.

## Findings

### S1-PF1-Verified: Slice 1 now has a coherent compile-safe ownership boundary

**Status**: VERIFIED-FIXED. The original finding S1-PF1 identified that Slice 1's file ownership did not form a compile-safe migration boundary because five direct production consumers of old `CompactionRequest` fields were excluded. The plan-fix resolves this by:

1. Expanding Slice 1 allowed files to include all five direct consumers (`llm_compaction.py`, `context_governance.py`, `dispatch.py`, `engine_ingest.py`, `compaction_evidence.py`)
2. Adding explicit per-file migration requirements for each consumer
3. Adding prompt asset migration to Slice 1
4. Adding 8 focused tests covering the migration boundary
5. Adding `rg` no-match verification for old field names
6. Explicitly forbidding all compatibility paths with both stop conditions and test assertions

**Evidence**: Plan lines 349-428; plan-fix document lines 26-44; code grep confirming old fields exist in all five files.

No new material findings identified.

## Residual Risks

### RR1: Slice 1 initial material construction is deliberately incomplete

Slice 1 creates typed contracts and initial material construction but defers deterministic segment selection, already-represented pruning, snapshot cursor repair, and evidence chunking to later slices. The intermediate state between Slice 1 and Slice 2 will have correct types but non-deterministic behavior. This is explicitly documented as a tradeoff: "Slice 1 is now intentionally larger. This is the cost of a compile-safe contract deletion boundary."

**Severity**: Low. The plan acknowledges this and Slice 2 immediately follows to converge behavior.

### RR2: `compact_artifact.py` is an additional old-field consumer beyond the five named in the stop-controller

Code grep shows `dayu/host/compact_artifact.py` also references old fields (`accepted_evidence_envelopes`, `compact_raw_context_items`, `input_event_refs`, `current_message_summary`). This file is in Slice 1's allowed list but was not explicitly named in the stop-controller adjudication.

**Severity**: Low. The file is covered by Slice 1 scope and the `rg` verification. The requirement "删除旧 old-key validator 分支中仅服务兼容的字段接受逻辑" implicitly covers artifact write path cleanup.

### RR3: `CompactSegmentSelection` is defined as a Slice 1 type but its construction in `dispatch.py`/`engine_ingest.py` uses initial (non-deterministic) logic

In Slice 1, `dispatch.py` and `engine_ingest.py` must construct `CompactionRequest(material_pack=..., segment_selection=...)`, but the full deterministic segment selection logic doesn't exist until Slice 2. The Slice 1 construction will be an initial/placeholder selection. This is acceptable for a compile-safe migration but represents a behavior gap between slices.

**Severity**: Low. Documented in the plan and Slice 2 immediately follows.

## Open Questions

None.

## Conclusion

**PASS**

The plan-fix resolves accepted finding S1-PF1. Slice 1 now has a coherent compile-safe ownership boundary that:
- Includes all five direct production consumers identified by the stop-controller
- Explicitly forbids deprecated aliases, compat wrappers, old-field defaults, and test-only compatibility
- Provides comprehensive test coverage (8 new tests + existing test migration)
- Preserves all design goals from `docs/host/design.md` §24 and §25
- Contains no scope creep beyond Host internals
- Maintains the public API boundary and layered architecture

The plan is ready for Slice 1 implementation re-review.
