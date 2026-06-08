# WU-TOOLS-01-F01 PR Review Controller Adjudication

Date: 2026-06-08
PR: https://github.com/noho/dayu-agent-r/pull/126
Gate: PR review

## Inputs

- AgentMiMo review: `docs/reviews/wu-tools-01-f01-pr-review-mimo.md`
- AgentDS review: `docs/reviews/wu-tools-01-f01-pr-review-ds.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`

## Verdict

Accepted as `pass-with-findings`.

No PR-blocking correctness, stability, contract, layering, wait-resume, or test-coverage finding was accepted. No fix gate is required for PR 126. The PR may proceed to `draft-PR-pass` and final closeout bookkeeping.

## Finding Adjudication

### MiMo F1: `FinsIngestionRuntime` dataclass exposes `_start_lock`

Decision: `rejected-with-reason`.

Reason: This is API hygiene, not a current correctness defect. The production assembly path uses `FinsIngestionRuntime.create(...)`, and no public equality or constructor-injection contract is promised by this work unit. Changing the runtime construction surface now would be a non-essential cleanup after aggregate review and PR review have passed.

### MiMo F2: daemon thread executor has no completion tracking

Decision: `deferred-with-owner`.

Owner / destination: `WU-TOOLS-01-F01-02`.

Reason: This is part of the broader migrated-tool cancellation and graceful stop surface. Current F01 intentionally provides the minimal daemon-thread executor for durable job startup and deterministic wait-resume coverage; production cancellation / drain semantics are now explicitly tracked by `WU-TOOLS-01-F01-02`.

### MiMo F3: `_save_cancelled` uses `save_job`

Decision: `rejected-with-reason`.

Reason: Current code has a single background execution owner per job and terminalization checks around cancellation. The finding is a readability asymmetry, not a demonstrated race in the accepted state machine. No current PR fix is warranted.

### MiMo F4: download and preprocess providers each instantiate `DefaultFinsRuntime`

Decision: `rejected-with-reason`.

Reason: Provider discovery is assembly-time and default-disabled. The current behavior does not create duplicate durable jobs or split Host wait governance. Runtime/service assembly cleanup can be revisited if production assembly proves this cost material.

### MiMo F5 / DS F2: `_timestamp_or_now` silently falls back on parse error

Decision: `rejected-with-reason`.

Reason: Job timestamps are written by the same runtime using `_utc_now()`. Malformed values require corruption or manual editing. The fallback affects display metadata, not Host governance or durable state transitions.

### MiMo D1 / DS FileLock notes: private Fins filelock should converge to `dayu.runtime.filelock`

Decision: `deferred-with-owner`.

Owner / destination: `WU-TOOLS-01-F01-01`.

Reason: User/controller direction is explicit: FileLock work is not fixed in PR 126. `WU-TOOLS-01-F01-01` will evaluate `dayu.runtime.filelock` capability and thoroughly replace Fins private filelock usage. FileLock observations are non-blocking evidence for that WU only.

### DS F1: `_fsync_directory` is POSIX-only

Decision: `rejected-with-reason`.

Reason: The project runtime target is Python 3.11 on macOS/Linux. The current atomic write recipe is correct for the supported POSIX environment.

### DS F3: `FinsIngestionWaitPollAdapter.from_workspace_root()` factory separation

Decision: `rejected-with-reason`.

Reason: Binding registry and runtime adapter instance construction are intentionally separate Host wait-adapter responsibilities. No contract violation was identified.

### DS F4: `download_adapters` key uses `NormalizedTickerMarket`

Decision: `rejected-with-reason`.

Reason: `NormalizedTickerMarket` is a static `Literal` over runtime `str` values. Dict lookup semantics are correct and covered by focused tests.

### MiMo accepted risk A2 / DS follow-up: no real CN/SEC download adapters yet

Decision: `deferred-with-owner`.

Owner / destination: `WU-TOOLS-01-F01-03`.

Reason: PR 126 establishes the shared ingestion runtime, adapter protocol, and awaiting tool path. Real OLD CN/SEC download and upload migration is explicitly tracked by `WU-TOOLS-01-F01-03`.

## Gate Outcome

- PR review gate: passed with non-blocking findings.
- Fix gate: skipped because there are no accepted PR-blocking findings.
- Re-review gate: skipped because no PR fix was performed.
- Next gate: accepted PR review commit / push / draft-PR-pass / final closeout bookkeeping.

## Validation Evidence

- AgentDS reported 91 focused tests passing, pyright 0 errors, and `git diff --check` clean.
- AgentMiMo reported focused Fins, service, Host / Engine / runtime / tools validation passing, pyright 0 errors, and `git diff --check` clean.
- Controller previously verified `git diff --check -- docs/host/issues-implementation-control.md` and pyright after control-doc updates.
