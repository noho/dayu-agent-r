# WU-SEMANTIC-OWNERSHIP-01 P3-C S2 Controller Validation

## Gate 与结论

- Gate：P3-C S2 implementation controller validation。
- Agent artifact：`docs/reviews/wu-semantic-ownership-01-p3-c-s2-implementation-codex.md`。
- Controller 结论：PASS，ready for code review。
- Blocking questions：0。

## Scope 审计

S2 实际修改落在 accepted plan 的 allowed production/test/docs 范围：

- Production：`compaction.py`、`compact_payload.py`、`compact_material.py`、`compact_pipeline.py`、`run_input.py`、`context_budget.py`、`compaction_operation.py`、`llm_compaction.py`。
- Tests/docs：`test_compact_material.py`、`test_compact_pipeline.py`、`test_compaction_operation.py`、`test_context_budget.py`、`test_llm_compaction.py`、`test_run_input_builder.py`、`dayu/host/README.md`、`tests/README.md`。

未进入 S3：accepted evidence typed LLM material、唯一 evidence renderer、typed mismatch exception 旧路径仍存在，作为已批准 S3 scope 处理。

## Controller 独立验证

- `source .venv/bin/activate && python -m pytest tests/host/test_run_input_builder.py tests/host/test_llm_compaction.py -q`
  - `136 passed in 1.04s`
- `source .venv/bin/activate && python -m pytest tests/host/test_compaction_contract.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_run_input_builder.py tests/host/test_public_compact_smoke.py tests/host/test_llm_compaction.py -q`
  - `285 passed, 1 skipped in 1.93s`
- `source .venv/bin/activate && python -m pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - `25 passed in 2.19s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `0 errors, 0 warnings, 0 informations`
- import smoke：
  - `dayu.host`
  - `dayu.host.memory`
  - `dayu.host.compact_material`
  - `dayu.host.run_input`
  - result：`import smoke ok`
- `git diff --check`
  - pass。
- `git diff -- dayu/host/tool_trace.py`
  - empty。

## Coverage

命令：

```bash
source .venv/bin/activate && python -m pytest \
  tests/host/test_compaction_contract.py \
  tests/host/test_context_budget.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_compact_material.py \
  tests/host/test_compact_pipeline.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_public_compact_smoke.py \
  tests/host/test_llm_compaction.py \
  --cov=dayu.host.compact_material \
  --cov=dayu.host.compact_payload \
  --cov=dayu.host.compact_pipeline \
  --cov=dayu.host.compaction \
  --cov=dayu.host.compaction_operation \
  --cov=dayu.host.context_budget \
  --cov=dayu.host.llm_compaction \
  --cov=dayu.host.run_input \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

结果：

| 文件 | 覆盖率 |
|---|---:|
| `dayu/host/compact_material.py` | 86% |
| `dayu/host/compact_payload.py` | 87% |
| `dayu/host/compact_pipeline.py` | 94% |
| `dayu/host/compaction.py` | 88% |
| `dayu/host/compaction_operation.py` | 94% |
| `dayu/host/context_budget.py` | 93% |
| `dayu/host/llm_compaction.py` | 90% |
| `dayu/host/run_input.py` | 88% |

总覆盖率 `88.86%`，`285 passed, 1 skipped`，`--cov-fail-under=80` pass。

## Source scans

Hard-delete scans were zero-match for S2-owned removals:

- `_compact_material_source_ref`
- `_parse_previous_forward_intent_text`
- `_parse_previous_reference_continuity_text`
- `_previous_blocks_from_snapshot`
- `_compact_artifact_message_content`
- `_vnext_compact_candidate_semantic_lines`
- `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`
- `_POST_COMPACT_BASE_MESSAGE_COUNT`
- `_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT`
- `def _previous_compacted_(view|session_summary|fact_material|answer_anchors|forward_intents|references)_vnext`
- `_snapshot_(summary_text|fact_texts|answer_anchor_texts|forward_intent_texts|reference_continuity_texts)`
- `_candidate_(session_summary_text|facts_texts|answer_anchor_texts|forward_intent_texts|reference_continuity_texts)`

Protocol scans:

- `CompactPipelineCompactArtifactView` has zero `messages` / `represented_evidence_refs` protocol properties.
- `CompactPipelineCompactArtifactView` keeps only `compact_artifact_ref` and `compact_artifact_digest` provenance properties for raw-tail selection.

Budget owner scans:

- `compaction_operation.py` no longer defines `_POST_COMPACT_BASE_MESSAGE_COUNT`.
- `llm_compaction.py` no longer defines the three dead `_POST_COMPACT_*` constants.
- `context_budget.py` owns `POST_COMPACT_BASE_MESSAGE_COUNT` and `estimate_post_compact_budget(...)`; `compaction_operation.py` only imports/calls the estimator with `accepted_compact_business_texts(candidate)`.

S3-deferred scans still have matches for accepted evidence renderer / mismatch paths. Controller accepts these as unchanged S3 scope because S2 was explicitly forbidden from entering S3.

## README decision

- `dayu/host/README.md` update is in scope: it documents that compact material and RunInputBuilder no longer re-interpret nested candidate JSON, ordinary RunInput no longer renders accepted compact artifact as a second system message, and post-compact budget belongs to context budget.
- `tests/README.md` update is in scope: it documents typed previous view pair invariant, compact event ref / memory latest compaction ref matrix, and budget diagnostics exclusion tests.
- Root README and `dayu/README.md` not triggered by this S2 slice.

## Propagation audit

```text
CONTEXT_COMPACTED.accepted_candidate
  -> compact_payload.parse_context_compacted_semantic_payload()
  -> compact_material typed projector
     -> previous compact blocks + CompactReadableViewVNext pair
     -> CompactMaterialPack / source snapshot exact invariant validation
     -> compact pipeline tier2/tier3 pair transform
     -> next ConversationCompactInputVNext.previous_compacted_view
  -> accepted_compact_business_texts()
     -> context_budget.estimate_post_compact_budget()
     -> compaction_operation budget gate

Conversation Memory snapshot latest_compaction_event_ref
  + CompactArtifactView.compaction_event_ref
  -> RunInputBuilder equality / repair matrix
  -> ordinary input uses memory sections once
```

Consistency conclusion:

- previous compact semantics no longer round-trip through private strings.
- ordinary RunInput no longer renders `compact.messages` or `Accepted compacted conversation view`.
- budget counts business texts and current input with context-budget-owned fixed overhead; diagnostics do not count.
- compact provenance remains available for raw-tail selection, represented evidence de-dup, manifest and audit, but no longer becomes LLM-facing compact material.

## Remaining risks

- S3 remains open for accepted evidence typed LLM material, unique renderer, and typed mismatch exception.
- S2 code review by AgentMiMo and AgentDS is still required before accepted slice commit.
