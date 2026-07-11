# WU-SEMANTIC-OWNERSHIP-01 Full Repository Round 2 Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01` umbrella follow-up.
- Gate: full-repository deepreview merge / controller adjudication.
- Review artifacts:
  - `docs/reviews/repo-review-20260711-143516.md`
  - `docs/reviews/repo-review-20260711-143658.md`
  - `docs/reviews/repo-review-20260711-144159.md`
  - `docs/reviews/repo-review-20260711-144330.md`
  - `docs/reviews/repo-review-20260711-145711.md`
  - `docs/reviews/repo-review-20260711-150304.md`
- Design sources:
  - `AGENTS.md`
  - `docs/host/design.md`
  - `docs/engine/design.md`
  - `docs/host/issues-implementation-control.md`
  - `docs/phaseflow-umbrella-optimization-control.md`

## Optimization Decision

Per `docs/phaseflow-umbrella-optimization-control.md`, raw findings are merged by semantic owner, failure mode, and validation matrix. The controller rejects or defers broad structural observations that do not show a current material failure path. The accepted findings below are grouped into implementation batches rather than one sub-WU per raw finding.

## Accepted Fix Batches

### Batch A - Web/Doc/FMP Boundary Safety

Status: accepted.

Raw findings:
- `145711-01` Web private-network policy bypass by redirects, meta refresh, and browser navigation.
- `145711-09` `search_files` symlink containment bypass.
- `145711-10` FMP resolver injects first fuzzy result as company identity.
- `145711-11` `fetch_web_page` lacks wire/decompressed body limits.

Rationale: material user/security/correctness failures with direct entry points and bounded owner surfaces.

Owner correction:
- Web fetch transport safety owner must validate every network hop and final target.
- Doc file access owner must validate every derived file path before read.
- FMP identity resolver must require exact identity proof; Service should fall back to ticker-only context when no exact match.
- Web fetch owner must enforce pre-conversion byte limits.

### Batch B - Fins Storage/Data-Loss Ownership

Status: accepted.

Raw findings:
- `145711-02` concurrent same-ticker tasks share an ownerless batch.
- `145711-03` download overwrite clears all ticker filings.
- `145711-04` upload overwrite deletes old document before conversion/cancel checks.
- `145711-05` `document_id` is not constrained to a single path component.
- `145711-15` HKEX fixed 100-row discovery without pagination/truncation.
- `145711-16` production download adapter ignores `rebuild_processed`.
- `150304-09` `_write_json` uses non-portable replacement semantics.

Rationale: data loss, path containment, and stale processed output are material Fins storage owner failures.

Owner correction:
- Fins storage must own path-component validation and same-ticker batch ownership.
- Download/upload overwrite must become scoped and staging-based enough to avoid deleting unrelated/current-good documents before success.
- HKEX downloader must prove completeness or return a typed truncated/failure result.
- Production download adapters must consume `rebuild_processed` or remove the public option.

### Batch C - Host Wait/Dispatch/Cancellation State Machines

Status: accepted.

Raw findings:
- `144159-01` / `145711-12` wait deadline is adjudicated separately by callback, poll adapter, and provider branches.
- `150304-01` WaitPollerSupervisor fails permanently after one transient exception.
- `150304-02` `_resolve_claimed_wait` error-recovery second failure crashes the supervisor.
- `143658-01`, `143658-02`, `143658-04`, `143658-05` scheduler close / recovery / cancelled worker paths leave or mishandle `CANCELLING` runs.
- `145711-06` dispatch first durable write retry exhaustion can lose the current record.
- `145711-07` promotion transient exception can drop the only session wakeup.
- `144330-03` cancel predispatch race.
- `144159-03` cancellation requested time is overwritten by propagation-token time.
- `150304-04` duplicate accepted record path can throw after durable accept.
- `144330-19` tool accept transaction and in-memory duplicate index can diverge under cancellation.
- `150304-05` OpenAI retry off-by-one.
- `150304-11`, `150304-12`, `150304-13`, `150304-22`, `150304-23` CAS/DI/claim-release state ownership gaps.

Rationale: all are Host/Engine lifecycle ownership issues. They share admission, dispatch, wait, and tool-runtime validation surfaces and should be fixed in a small number of state-machine slices.

Owner correction:
- Wait expiry/eligibility must move to the Host wait resolve owner.
- Scheduler/promotion/dispatch must use ack/requeue/terminal-closeout semantics for current work items.
- Cancellation terminal payload must derive requested time from committed `CANCEL_REQUESTED`.
- Tool accept durable fact is authoritative; post-commit duplicate indexes must not change the accepted outcome.
- Retry semantics must honor `max_retries` as an actual retry count.

### Batch D - Engine/Host Public Contract Ownership

Status: accepted.

Raw findings:
- `143516-01` final answer blankness uses different Engine and Host predicates.
- `144159-02` / `145711-13` `RunnerEvent.type` and `RunnerEvent.data` pairing is not enforced in the public contract.
- `144159-04` compactor repair/retry trigger is inferred from ordinal.
- `144159-05` cancelled tool outcome has ordinary/wait-specific canonical shapes.
- `144159-06` Service rebuilds Host terminal status.
- `144159-07` `RUN_STARTED.start_reason` consumers use raw strings.
- `144159-08` Agent fallback mode has multiple owners.
- `144159-09` Host public construction annotations cannot be resolved at runtime.
- `144330-20` compaction evidence kind is hard-coded by Host.
- `143516-02` Engine Agent test imports OpenAI runner private parser.
- `144330-21`, `144330-22`, `144330-23`, `144330-24`, `144330-25` continuation/fallback/compaction/memory ownership gaps.

Rationale: cross-layer contract drift with clear owner candidates. Most fixes are medium risk and should be handled after state-machine high-risk fixes unless they are prerequisite for tests.

Owner correction:
- Engine contracts must enforce discriminated unions and AgentPolicy fields at construction.
- Host public API must expose owner-level terminal/start/fallback predicates and runtime-resolvable schemas.
- Tool outcome codec and compaction trigger/evidence semantics must have one Host owner.

### Batch E - Fins Typing / Runtime Hygiene With Direct Failure Evidence

Status: accepted where directly evidenced; otherwise deferred.

Accepted raw findings:
- `144330-02` / `150304-07` / `150304-27` typed Fins read/runtime capability and object/Any leaks.
- `150304-08` unbounded `_meta_cache`.
- `150304-10` direct Fins wait adapter dependency on Host, only as a follow-up if Batch C changes wait adapter public boundary.
- `150304-28`, `150304-30` import-boundary weak-typing guard tests, as validation hardening for the above.

Deferred raw findings:
- `150304-06` ingestion runtime God module.
- `144330-11` ToolRuntime monolith.
- `150304-29` broad Fins processor coverage.

Rationale: weak typing with direct locations is accepted. Broad file-size or test-coverage findings are not material enough for this optimized fix pass unless they block accepted fixes.

## Rejected Or Deferred With Reason

- Broad module size findings (`144330-11`, `150304-06`) are deferred. They are real maintainability concerns but not a bounded semantic ownership failure and would explode the WU.
- General broad `except Exception` audits without a concrete wrong state transition (`144330-12`, `144330-13`) are deferred. Specific wrong closeout paths are accepted in Batches C/D.
- README/doc wording, config secret syntax, and English diagnostic text findings (`144330-14`, `144330-15`, `144330-26`) are deferred unless touched by accepted code changes.
- Queue starvation telemetry (`150304-14`) is deferred; it requires product policy, not a local semantic owner correction.
- Async DB actor replacement (`145711-08`) is deferred as an architectural migration; accepted dispatch/promotion orphan fixes must not depend on a full DB actor.
- Memory projection nuance findings (`150304-17`, `150304-18`, `150304-19`) are accepted only if Batch D compaction/memory tests show direct current contract failure; otherwise defer with memory owner.
- Tool Trace O(N) and cold projection catch-up findings (`150304-20`, `150304-21`) are deferred as performance/resilience follow-up unless touched by accepted tool outcome codec changes.

## Implementation Plan

Use optimized batch gates:

1. Batch A and low-risk single-line Engine retry fix can be implemented together if touched files do not conflict.
2. Batch B Fins storage/data-loss fixes should be a separate high-risk slice.
3. Batch C Host wait/dispatch/cancel fixes should be split into at most two slices:
   - wait expiry/supervisor/claim release;
   - dispatch/promotion/cancel/tool accept/retry.
4. Batch D Engine/Host public contract fixes should follow Batch C because several tests depend on stabilized lifecycle behavior.
5. Batch E Fins typing/import hardening should be batched with Batch B when file ownership overlaps; otherwise run as a final cleanup slice.

Every accepted finding must end in one of: fixed, rejected-with-direct-evidence, or deferred-with-owner. No raw finding is to become a separate sub-WU only because it came from a separate review artifact.

## Validation Profiles

- Batch A: targeted Web/Doc/FMP tests, new SSRF/symlink/body-limit/FMP exact-match tests, pyright, `git diff --check`.
- Batch B/E: Fins storage/download/upload/read focused tests, path traversal and overwrite regression tests, pyright, `git diff --check`.
- Batch C: Host wait/dispatch/cancel/tool-runtime focused matrices, OpenAI retry tests, pyright, `git diff --check`.
- Batch D: Engine contract tests, Host public API/Service/compaction/tool outcome tests, pyright, `git diff --check`.

