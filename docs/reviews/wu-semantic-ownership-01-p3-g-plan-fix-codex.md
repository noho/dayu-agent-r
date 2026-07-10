# Plan Fix — WU-SEMANTIC-OWNERSHIP-01 P3-G

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G`
- Plan artifact updated: `docs/host/wu-semantic-ownership-01-p3-g-fins-domain-contracts-plan.md`
- Input adjudication: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-review-controller-adjudication.md`
- Implementation status: plan-only fix; no production code or tests were implemented in this gate.

## Fix Status

### P3-G-PF-01 — S4 XBRL `total` Contract Boundary

Fixed.

- S4 now states that raw processor result validation happens before read-runtime fact normalization and deduplication.
- Raw `total` must exist, be `int`, and equal the raw `facts` list length.
- Post-dedup shrink is explicitly valid and must not cause failure.
- Read runtime must preserve processor-owned `total`; any deduped count must be a distinct derived field or summary term.
- Test matrix now covers missing `total`, non-int `total`, raw mismatch, valid raw result, and valid post-dedup shrink.

### P3-G-PF-02 — S1 Form Normalizer Disposition And Source Scans

Fixed.

- S1 now explicitly deletes `dayu/fins/processors/form_type_utils.py`.
- Plan forbids compatibility wrappers, compatibility re-exports, or keeping the old module as a pass-through delegate.
- Plan lists current import/call sites that must move to the domain helper.
- Source scans now cover definitions, imports, aliases, and call sites, including `_normalize_report_form_type`, `_normalize_form_type`, `_normalize_form`, and `_normalize_form_for_fiscal`.

### P3-G-PF-03 — S2 CN/HK Adapter Versus Pipeline Boundary

Fixed.

- S2 now classifies downloader-owned raw HTTP/provider parsing versus pipeline/domain-owned business filtering.
- Product-level title blocking, language filtering, report-kind classification, fiscal period/year inference, dedupe/grouping, and `CnReportCandidate` construction are assigned to pipeline/domain helpers.
- Test migration is explicit: raw adapter tests keep HTTP/raw parsing assertions, pipeline helper tests receive business filtering/inference assertions, and workflow tests remain integration coverage.

### P3-G-PF-04 — S3 Rejection Registry Consumer Scope

Fixed.

- S3 scope now includes `dayu/fins/pipelines/sec_sc13_filtering.py`.
- S3 validation, source scans, and propagation audit now include SC13 filtering as a typed registry consumer.
- The plan forbids typed-registry-to-dict compatibility shims for SC13 call paths.

## Validation

- `git diff --check`: passed.
- Targeted source checks confirmed the updated plan contains the PF-01 through PF-04 requirements.

## Blocking Questions

None. The plan is ready for independent re-review.
