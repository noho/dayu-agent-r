# WU-SEMANTIC-OWNERSHIP-01 P3-C Aggregate Deepreview Controller Adjudication

## Verdict

PASS. P3-C plan, S1, S2, S3, code-review fixes, and re-reviews are aggregate-accepted with no current-scope fix gate.

- AgentMiMo aggregate artifact: `docs/reviews/wu-semantic-ownership-01-p3-c-aggregate-deepreview-mimo.md`
- AgentDS aggregate artifact: `docs/reviews/wu-semantic-ownership-01-p3-c-aggregate-deepreview-ds.md`

## Merged Findings

### AGG-F01 - rejected as stale evidence - `_parse_fact` duplicate label path validation

- Source reviewer: AgentDS aggregate finding 1.
- Controller ruling: rejected as stale evidence.
- Direct current-code evidence:
  - `dayu/host/compact_payload.py` `_parse_fact()` calls `_required_unique_text_list(..., path=f"{path}.evidence_labels")` and `_required_unique_text_list(..., path=f"{path}.source_labels", allow_empty=True)`.
  - `_required_unique_text_list()` raises `ValueError(f"{path}[{index}] must be unique")`.
  - `tests/host/test_context_compact_events.py::test_compacted_semantic_parser_rejects_duplicate_fact_labels_with_indexed_path` covers both duplicate `evidence_labels` and duplicate `source_labels` with indexed JSON path assertions.
- Root cause of review mismatch: the aggregate review text quoted the earlier S1 finding evidence, not the current post-S1-fix implementation.
- No code fix required.

### AGG-F02 - rejected as non-defect - `CompactEvidenceBlock.size_units` result-text component size

- Source reviewer: AgentDS aggregate finding 2; also observed during S3 code review.
- Controller ruling: rejected as non-defect.
- Direct current-code evidence:
  - `_pack_evidence_blocks()` sets `CompactEvidenceBlock.raw_result_text=material.result_text`, `size_units=len(material.result_text)`, and `content_digest=_text_digest(material.result_text)`.
  - The initial evidence path already uses `size_units=len(material.raw_result_text)`.
  - P3-C S3 plan explicitly fixes no-rename component mapping: `CompactEvidenceBlock.raw_result_text` and `EvidenceReadableItemVNext.response_text` carry the pure result component, while rendered four-line text remains `RunInputMaterialBlock.text`.
- No code fix required.

### AGG-F03 - fixed as artifact hygiene - trailing whitespace in old S1 review artifact

- Source reviewer: AgentMiMo residual observation.
- Controller ruling: not a production or semantic finding, but fixed in-place to keep `git diff --check` clean for the aggregate commit.
- Changed file: `docs/reviews/wu-semantic-ownership-01-p3-c-s1-code-review-ds.md`.

## Closed Scope

- P3-C accepted plan findings: all closed.
- P3-C plan re-review fixes: all closed.
- S1 review accepted findings: all closed; stale parser-path finding is disproved by current code and tests.
- S2 review: no material findings.
- S3 review accepted finding: closed.
- No new material P3-C regression.

## Residuals

- P3-E remains owner for accepted tool status fallback and raw outcome reconstruction.
- P3-J remains owner for global EventLog schema, taxonomy, and DDL closed-set synchronization.
- Non-P3-C full-repository issues remain outside this aggregate gate and will be handled by subsequent umbrella deepreview rounds.
