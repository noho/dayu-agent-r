# WU-SEMANTIC-OWNERSHIP-01 P3-F S4 Controller Validation

## Scope

- Slice: `P3-F S4 - Company metadata freshness semantics`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-f-s4-implementation-codex.md`
- Accepted S3 commit: `edf303a4`

## Motivation Check

S4 motivation remains current. Upload company metadata previously treated the mere existence of repository meta as fresh, which could preserve stale company identity fields produced by older upload resolver semantics. The correct owner is `dayu.fins.pipelines.upload_company_meta`, with `RESOLVER_VERSION` as semantic freshness truth. `updated_at` is audit time, not a TTL.

## Controller Result

Ready for independent code review by AgentMiMo and AgentDS.

## Evidence Checked

- `upsert_company_meta_for_upload(...)` preserves existing meta only when `_existing_company_meta_is_fresh(existing_meta, RESOLVER_VERSION)` is true.
- Stale existing meta goes through the same normalization and required `company_name` validation path as missing meta.
- New helper `_existing_company_meta_is_fresh(...)` compares resolver versions only.
- SEC/CN upload stream tests cover same-version preserve, old-version refresh, and stale-without-company-name fail-closed behavior.
- `FinsReadRuntime._read_company_info(...)` remains a repository read path and does not infer freshness.
- `dayu/fins/README.md` records the owner boundary.

## Commands Run

- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q`
  - Result: `24 passed, 3 warnings in 0.97s`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed with no output.
- Source scans checked `RESOLVER_VERSION`, `_existing_company_meta_is_fresh`, `updated_at`, `upsert_company_meta_for_upload`, and `_read_company_info`.

## Propagation Audit

1. Upload request supplies ticker/company fields.
2. Upload company meta helper determines freshness using resolver version.
3. Fresh meta is preserved; stale/missing meta is validated from current upload fields and persisted with current `RESOLVER_VERSION`.
4. Download producers remain outside upload freshness.
5. Read runtime consumes repository company meta and does not refresh or infer freshness.

## Residual Risk

- No dedicated read-runtime test was added; direct source inspection confirms read runtime still only reads repository meta.
- Download producer freshness remains outside S4 by plan.
