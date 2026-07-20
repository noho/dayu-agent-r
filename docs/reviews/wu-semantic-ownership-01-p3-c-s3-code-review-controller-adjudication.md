# WU-SEMANTIC-OWNERSHIP-01 P3-C S3 Code Review Controller Adjudication

## Verdict

S3 code review entered fix gate for one accepted low-severity finding.

- AgentMiMo artifact: `docs/reviews/wu-semantic-ownership-01-p3-c-s3-code-review-mimo.md`
- AgentDS artifact: `docs/reviews/wu-semantic-ownership-01-p3-c-s3-code-review-ds.md`

## Merged Findings

### P3-C-S3-CR-F01 - accepted - accepted evidence material / renderer import path is not canonical

- Source reviewer: AgentDS `F-01`.
- Severity: Low.
- Direct evidence: `dayu/host/durable/memory.py` imported `AcceptedToolEvidenceLLMMaterial` through `accepted_result_projection`, while other consumers imported the same leaf evidence contract from `dayu.host.evidence`.
- Owner boundary: `dayu.host.evidence` owns the LLM material value object, fallback text, typed mismatch exception, and the single LLM-facing renderer. `accepted_result_projection` owns production of `AcceptedToolResultProjection.llm_material`, not the renderer import surface.
- Controller ruling: accepted as current S3 scope. The inconsistency was not a runtime correctness defect, but it weakened the source-of-truth boundary that S3 explicitly introduced.
- Required fix: remove the evidence material / renderer / fallback text re-export surface from `accepted_result_projection`, import the leaf symbols directly from `dayu.host.evidence` in consumers and tests, and document that consumers render typed material through the evidence contract.
- Required validation: targeted Host tests, S3 affected matrix, pyright, source scan proving no Host/test consumer imports evidence material or renderer from `accepted_result_projection`, and propagation audit.

### P3-C-S3-CR-F02 - rejected as non-defect - `CompactEvidenceBlock.size_units` uses result text length

- Source reviewer: AgentDS `F-02`.
- Severity claimed: Low.
- Direct evidence: `_pack_evidence_blocks()` sets `CompactEvidenceBlock.size_units=len(material.result_text)`.
- Controller ruling: rejected as non-defect. Existing initial evidence packing already used `size_units=len(material.raw_result_text)`, and the accepted P3-C S3 plan requires `CompactEvidenceBlock.raw_result_text` and `EvidenceReadableItemVNext.response_text` to carry the pure result component while `block.text` remains the full four-line renderer. The delta evidence path now matches that existing compact evidence component-size semantics.
- No code change required.

## Residual Scope

- P3-E remains owner for accepted tool status fallback and raw outcome reconstruction.
- P3-J remains owner for global EventLog schema, taxonomy, and DDL closed-set synchronization.
