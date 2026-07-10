# Controller Adjudication — WU-SEMANTIC-OWNERSHIP-01 P3-G Plan Review

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G`
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-g-fins-domain-contracts-plan.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-g-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-g-plan-review-ds.md`

## Verdict

Plan review passed with required plan fixes. The plan motivation and owner boundaries are accepted, but implementation must not start until the fixes below are reflected in the plan and re-reviewed.

## Merged Findings

### P3-G-PF-01 — S4 XBRL `total` Contract Boundary

Accepted.

Merged from:
- MiMo 001, high
- DS `P3-G-PLAN-F02`, medium

Required fix:
- Clarify that `XbrlFactsResult.total` is processor-owned and must be validated against the processor's raw `facts` list before read-runtime dedup/projection.
- Read runtime must not fail a valid processor result merely because its post-dedup projected fact count differs from processor `total`.
- Read runtime must not overwrite `total`; if projected/deduped count is needed, it must use a distinct derived field or summary term.
- Tests must distinguish:
  - missing `total` fails closed;
  - non-int `total` fails closed;
  - raw processor `total != len(raw facts)` fails closed;
  - valid raw total with post-dedup shrink remains valid and preserves processor `total`.

### P3-G-PF-02 — S1 Form Normalizer Disposition And Source Scans

Accepted.

Merged from:
- MiMo 002, medium
- DS `P3-G-PLAN-F03`, medium

Required fix:
- Choose an explicit disposition for `dayu/fins/processors/form_type_utils.py`: delete it and update imports, or move the true helper to domain and make this file non-public only if it adds real semantics. A compatibility wrapper/re-export is not acceptable.
- Plan must name the current import/call sites that S1 will update.
- Strengthen source scans so they catch both definitions and call/import usage of old normalizers, including aliases such as `_normalize_report_form_type`, `_normalize_form_type`, `_normalize_form`, and `_normalize_form_for_fiscal`.

### P3-G-PF-03 — S2 CN/HK Adapter Versus Pipeline Boundary

Accepted.

Merged from:
- MiMo 003, medium
- DS `P3-G-PLAN-F01`, medium

Required fix:
- Classify CNInfo/HKEXNews helper responsibilities one by one:
  - provider raw field parsing / HTTP JSON normalization may remain in downloader;
  - product-level title blocking, language filtering, report-kind classification, fiscal period/year inference, dedupe/grouping, and `CnReportCandidate` construction must move to pipeline/domain helper.
- Plan must describe the test migration path:
  - preserve existing downloader assertions for HTTP and raw provider parsing;
  - move business filtering/inference assertions to pipeline helper tests;
  - keep workflow tests as integration coverage.

### P3-G-PF-04 — S3 Rejection Registry Consumer Scope

Accepted.

Merged from:
- MiMo 004, low

Required fix:
- Add `dayu/fins/pipelines/sec_sc13_filtering.py` to S3 allowed files and propagation audit because it currently consumes `dict[str, dict[str, str]]` rejection registry signatures.
- S3 source scan and validation must cover `sec_sc13_filtering.py`, not only `sec_download_state.py`, `sec_pipeline.py`, diagnostics, and storage.

## Rejected / Deferred Findings

None. All review findings are accepted as plan-fix work.

## Next Gate

AgentCodex must update only the P3-G plan artifact and report the fixes. Then AgentMiMo and AgentDS must re-review the plan before the controller can accept the plan commit and enter S1 implementation.
