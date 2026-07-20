# Controller Adjudication — WU-SEMANTIC-OWNERSHIP-01 P3-F Aggregate Deepreview

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-F`
- Topic: Fins source document, blob, provenance, citation, wait timeout, and upload company metadata ownership.
- Reviewed artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-f-aggregate-validation.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-f-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-f-aggregate-deepreview-ds.md`
- Accepted implementation commits:
  - S1 source repository provenance and citation projection: `42ea9c21`
  - S2 blob acknowledgement and explicit staging source contract: `3b2779e4`
  - S3 Fins wait adapter deadline/expiry consumption: `edf303a4`
  - S4 company metadata freshness semantics: `22683a8e`

## Motivation Check

The aggregate review target is valid. P3-F fixed four related semantic ownership chains that can only be accepted after cross-slice propagation is checked:

- source provider/provenance must be produced by Fins producers, validated and persisted by the source repository, then projected into citations by read runtime;
- blob bytes must not be written without an acknowledged source document owner;
- Fins wait transient loss must consume Host-owned wait boundaries instead of inventing adapter-local timeout truth;
- upload company metadata freshness must be resolver-version based, with `updated_at` remaining audit-only.

The correct closeout question is therefore not whether each slice passed locally, but whether the combined state has one source of truth per business fact and no downstream special-case compensation.

## Reviewer Results

| Reviewer | Artifact | Verdict | Material findings |
| --- | --- | --- | --- |
| AgentMiMo | `docs/reviews/wu-semantic-ownership-01-p3-f-aggregate-deepreview-mimo.md` | PASS | 0 |
| AgentDS | `docs/reviews/wu-semantic-ownership-01-p3-f-aggregate-deepreview-ds.md` | PASS | 0 |

Both reviewers explicitly checked cross-slice ownership, source scans, README consistency, validation evidence, and residual risks. Neither review introduced a blocking or current-scope fix finding.

## Controller Decision

Accepted with no fix gate.

- P3-F aggregate validation passed: `256 passed, 3 warnings`, pyright `0 errors`, `git diff --check` passed.
- Both aggregate deepreviews passed with zero material findings.
- All accepted P3-F plan, code-review, and aggregate review findings are closed.
- No new current-scope finding requires AgentCodex implementation or re-review.

## Propagation Audit

### Source Provenance And Citation

Producer paths write `source_provider` into source metadata. `SourceDocumentProvenance.from_meta` validates the durable source metadata. `FinsReadRuntime._build_citation` derives `source_type` and `source_provider` from that provenance and rejects incomplete source metadata. LLM-facing citation output is derived from this repository provenance, not from document id prefixes, `ingest_method`, or consumer-side guesses.

### Blob Acknowledgement

Pipelines stage a source document before blob writes. `DocumentBlobRepositoryProtocol.store_file` accepts a `SourceHandle` and the filesystem implementation checks source metadata before writing bytes. Final source completion preserves staged stable facts and attaches blob membership under the same source document truth.

### Wait Timeout Ownership

Host wait records own `deadline_at` and `expires_at`. The Fins wait adapter consumes those fields in `_wait_boundary_lost`; no local transient-pending timeout remains. No-boundary records stay not-ready, and terminal lifecycle remains Host-owned.

### Company Metadata Freshness

Upload freshness is decided by `upload_company_meta.RESOLVER_VERSION`. Same-version upload metadata is preserved; stale-version metadata is refreshed from current upload fields; stale metadata without required business fields fails closed. `updated_at` is audit-only and read runtime does not become a freshness resolver.

## Residual Risk Disposition

- Multi-process source-meta/blob-write TOCTOU remains an accepted non-blocking residual from the S2 plan; current runtime uses one storage assembly.
- No-boundary transient unavailable staying not-ready is an intentional owner-boundary decision; Host poller cadence, cancel, and close lifecycle own governance.
- `expires_at` support is implemented although the current Host creation path writes `None`.
- Coverage percentage is not measured because local pytest-cov remains blocked by the existing numpy/pandas import issue; behavioral matrix and pyright passed.
- Download-path company metadata freshness outside upload remains owned by the corresponding producer paths and is not a P3-F blocker.

## Final State

P3-F is complete. The next umbrella sub work unit is `WU-SEMANTIC-OWNERSHIP-01 P3-G - Fins form/domain typed rules and processor result contracts`, subject to fresh motivation, owner-boundary, plan, implementation, review, fix, and re-review gates.
