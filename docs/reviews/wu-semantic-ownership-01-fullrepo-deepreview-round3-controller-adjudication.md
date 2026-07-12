# WU-SEMANTIC-OWNERSHIP-01 Round3 Full-Repository Deepreview Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Gate: aggregate full-repository deepreview adjudication after P3-K
- Controller inputs:
  - `docs/reviews/repo-review-20260712-085921.md`
  - `docs/reviews/repo-review-20260712-085930.md`
  - `docs/reviews/repo-review-20260712-090033.md`
  - `docs/reviews/repo-review-20260712-091126.md`
  - `docs/reviews/repo-review-20260712-093647.md`
- Design truth:
  - `docs/host/design.md`
  - `docs/engine/design.md`
- Control truth:
  - `docs/host/issues-implementation-control.md`
  - `docs/phaseflow-umbrella-optimization-control.md`

## Controller Position

The five review artifacts reported 165 raw findings. The controller treats `repo-review-20260712-093647.md` as the primary ledger because it contains a complete 795-file coverage account, explicit minimal counterexamples, full validation records, and a numbered DR ledger. MiMo and DS findings are merged into that ledger when they either confirm the same owner drift or provide additional direct evidence not covered by the Codex ledger.

The current WU is not "fix every reviewer sentence". Findings are accepted only when direct evidence shows an existing semantic-owner, state-machine, storage, public-contract, security, or LLM-facing failure. Findings based only on file size, style, generic cleanup, speculative future extensibility, or broad governance without a bounded owner path are rejected or deferred with an owner.

## Raw Finding Count

| Artifact | Raw findings | Controller use |
| --- | ---: | --- |
| `repo-review-20260712-085921.md` | 28 | merge confirmations and additional Host/Fins evidence |
| `repo-review-20260712-085930.md` | 16 | merge confirmations and governance-only rejection/defer evidence |
| `repo-review-20260712-090033.md` | 38 | merge additional Fins/Web findings |
| `repo-review-20260712-091126.md` | 45 | merge additional Host/Fins/Engine findings |
| `repo-review-20260712-093647.md` | 38 | canonical DR ledger |
| Total raw | 165 | deduplicated below |

## Accepted Sub WU Queue

### R3-A - Host Lifecycle, Wait, Admin, Durable Integrity, And Scheduler Health

Decision: accepted.

Owner boundary: Host lifecycle/admission/dispatch/wait/durable state owners. Host remains the truth for Run/Attempt lifecycle, waiting closeout, scheduler health, durable descriptor integrity, admin-vs-execution opener separation, and shutdown semantics.

Merged source findings:

- DR-006 runner-call hot payload unbounded.
- DR-007 session list/purge starts full execution Host.
- DR-008 wait deadline leaves Run WAITING forever.
- DR-009 scheduler fatal fail-stop not propagated to public Host admission.
- DR-010 durable descriptor content/digest split.
- DR-011 async Host API blocks event loop on sync SQLite retry.
- DR-012 sync wait adapter can hang Host close forever.
- DR-017 interruptible process lifecycle commits before side effect completion.
- DR-025 reactive compactor timeout contaminates parent cancellation token.
- DR-029 LaneController.close commits completed after partial release failure.
- MiMo/DS confirmations: dispatch retry exhaustion self-closes scheduler; watchdog wakeup drop; proactive compaction TOCTOU; recovery single huge transaction; cancel_run deferred race; compact_material wrong tool_call_event_ref fallback; wait adapter reverse dependency is handled under R3-D/R3-A boundary split.

Required correction:

- Use bounded hot EventLog atoms and descriptor references for runner-call manifests.
- Split execution Host opening from read/purge/admin durable access.
- Make wait expiry a Host-owned terminal closeout path.
- Expose scheduler fatal state through admission or supervised recovery.
- Validate durable descriptor bytes/digest/ref at owner boundaries.
- Move blocking durable calls behind an explicit owner boundary or otherwise prove no event-loop freeze.
- Bound wait adapter observation and Host close.
- Preserve first-committed terminal/lifecycle result.
- Make lane close retryable after partial release failure.

Validation profile: production-high; must include focused Host lifecycle/wait/durable tests, runner payload stress, event-loop lock contention probe, pyright, `git diff --check`, and source scans for old unbounded hot payload patterns.

### R3-B - Engine Provider Protocol And Tool-Call Contract

Decision: accepted.

Owner boundary: Engine contracts, provider parser/aggregator, and message/event discriminators. Engine owns provider protocol normalization before Host sees semantic events.

Merged source findings:

- DR-013 late cancellation after RunnerDone overwrites completion.
- DR-014 ToolCallAggregator can merge provider tool calls.
- DR-031 EngineEvent and Message discriminator/role invariants lack owner validation.
- DR-034 non-stream parser retains OLD compatibility protocol.
- DR-035 tool argument JSON Schema uses Python equality and accepts negative bounds.
- DS/MiMo confirmations: non-stream finish_reason forcing; finish_reason missing policy mismatch; agent failure_candidate overwrite; runner identity delimiter contract weakness; OpenAI error classifier hardcoded markers.

Required correction:

- Treat RunnerDone as the Engine commit boundary.
- Fail closed on native/synthetic tool-call identity conflicts.
- Validate event discriminator/data and message role invariants at construction/projection boundary.
- Remove generic OLD non-stream dict-arguments compatibility.
- Enforce JSON typed equality and non-negative JSON Schema bounds.
- Align finish_reason and failure diagnostic ownership without caller-side repair.

Validation profile: production-high; must include OpenAI parser/aggregator negative matrix, Engine agent cancellation ordering tests, JSON Schema validation tests, pyright, `git diff --check`, and compatibility-branch deletion scans.

### R3-C - Fins Storage, Upload, Download Provenance, And Mutation Atomicity

Decision: accepted.

Owner boundary: `dayu.fins.storage`, Fins upload/download pipeline owners, and Service/Host adapter assembly. Fins storage owns ticker/document/file identity and repository atomicity; Service/Host owns Host-facing wait adapter assembly so Fins must not import Host.

Merged source findings:

- DR-001 Fins storage path identity escapes ticker/document root.
- DR-002 default LLM upload tool can persist arbitrary process-readable local files.
- DR-003 CN/HK download lacks trusted URL/TLS provenance boundary.
- DR-020 completed Fins document mutation paths are not atomic.
- DR-023 Fins upload/download lacks byte budgets.
- DR-024 Docling converter builder failure bypasses fallback.
- DR-036 CN/HK temp PDFs can leak after cancellation.
- MiMo/DS additions: Fins wait_adapter imports Host; `_store_downloaded_document` rollback cannot restore physical/blob/processed side effects; `docling_upload_service` commit failure leaks batch token; `LocalFileStore.put_object` lacks fsync; `store_file` misses filename component validation; `ProcessedHandle` existence is not validated; SEC/CN/HK cache and temp file cleanup gaps; CN/HK cancellation asymmetry.

Required correction:

- Introduce owner-level single-component identity validation for ticker, document id, entry name, URI, and filename before any FS key construction.
- Constrain LLM-facing upload to explicit user file authority or a symlink-safe allowlist.
- Enforce trusted provider URL/TLS/redirect provenance and byte budgets for CN/HK downloads.
- Make completed document mutation all-or-nothing across source/blob/processed side effects or avoid cross-repo partial commits.
- Roll back upload/download batches correctly on commit failure.
- Clean temp assets on all cancel/exception/generator-close paths.
- Remove Fins -> Host imports by moving Host wait adapter glue to Service/Host assembly.

Validation profile: production-high; must include Fins storage path traversal tests, upload authority tests, CN/HK byte/provenance tests, batch rollback tests, temp cleanup tests, Fins import-boundary scan, pyright, and `git diff --check`.

### R3-D - Fins Financial Semantics, XBRL Projection, Processor Freshness, And Read Contracts

Decision: accepted.

Owner boundary: Fins financial result/domain contracts and read runtime projection. Financial scale, period, quality, failure reason, and source freshness must be produced once and preserved through LLM-facing output.

Merged source findings:

- DR-021 financial results lose periods/scale/data_quality/reason in LLM projection.
- DR-022 XBRL query.execute exceptions become successful empty sets.
- DS additions: BS XBRL scale always None; fiscal period sort constants diverge; `_infer_fiscal_year` is a no-op; 10-Q virtual section postprocess misses ref rebuild/table reassignment; processor cache has no invalidation after reprocess; `_load_text(errors="ignore")` silently drops bytes; 6-K only has BS route/no fallback; `sec_download_filing_workflow` not_modified skip misses `download_version`; ticker alias upload normalization bypasses `try_normalize_ticker`; duplicated `_normalize_optional_string`.
- MiMo additions: `search_document` swallows non-cancel exceptions; `DocumentMeta`/result types carry broad dynamic signatures where they cross durable/LLM contracts.

Required correction:

- Preserve owner-level financial semantics in result types and LLM projection.
- Convert XBRL/query failures into typed degradation or failure signals, not empty success.
- Infer or explicitly reject absent scale/year semantics at the processor owner.
- Consolidate fiscal period and optional string normalization truth.
- Rebuild 10-Q virtual section indexes and table assignments after expansion.
- Invalidate processor cache on reprocess or validate freshness before reuse.
- Stop silently ignoring non-UTF-8 and search/index failures.
- Align skip/version and ticker alias normalization with existing owner helpers.

Validation profile: production-high; must include Fins result projection tests, XBRL exception tests, BS scale tests, 10-Q virtual section/table tests, processor cache invalidation tests, read-runtime degradation tests, pyright, and `git diff --check`.

### R3-E - Web And Document Tool Egress, Resource Caps, Diagnostics, And Oracles

Decision: accepted.

Owner boundary: production Web/Documents tool egress policy, resource budget, diagnostic redaction, and smoke oracle owners.

Merged source findings:

- DR-004 Web URL security has DNS TOCTOU/reserved-network bypass.
- DR-015 Web resource caps happen after full decompression and warmup bypasses caps.
- DR-016 diagnostic path saves full page and reversible secret text.
- DR-019 document read/search/list load entire file/tree before business caps.
- DR-032 smoke/diagnostic oracle can self-certify PASS.
- DR-033 web diagnostic utility uses weak URL policy and plaintext login state.
- DS additions: web redirect response leak on cancel/security reject; challenge detection false positives; challenge detected but status mismatch skips Playwright fallback; DuckDuckGo parser silently returns empty on shape drift.

Required correction:

- Use a shared egress policy for production and diagnostic paths, including redirect/subrequest peer checks or explicit safe profiles.
- Enforce wire and decoded byte caps before allocating full bodies; give warmup and browser DOM budgets.
- Redact or avoid writing full secrets/login state by default; require explicit opt-in, restricted permissions, and cleanup.
- Stream or pre-budget document reads/search/list before materialization.
- Make smoke/diagnostic pass/fail/skipped states come from independent, non-self-certifying oracles.
- Close responses on all redirect reject/cancel paths and tune challenge fallback policy.

Validation profile: production-high; must include Web SSRF/resource/challenge tests, document cap tests, diagnostic redaction tests, oracle negative-control tests, pyright, and `git diff --check`.

### R3-F - CLI, Config, Packaging, Public Documentation, And Numeric Contracts

Decision: accepted.

Owner boundary: CLI public contract, config loader/runtime numeric validators, packaging metadata, README public documentation, and release validation gates.

Merged source findings:

- DR-005 `dayu-cli init` follows config symlink out of workspace.
- DR-018 Python 3.11 installability conflicts with Docling runtime dependency.
- DR-026 interactive `--ticker` does not enter LLM-facing scene context.
- DR-027 `upload_filings_from` renders POSIX quoting unsafe for Windows cmd.
- DR-028 root README drifts from actual CLI public contract.
- DR-030 NaN/Infinity pass through config/timeouts/backoff/lane/filelock.
- DR-037 default pytest/stress/pyright release gate is red.
- MiMo/DS additions: config overlay silently replaces non-map fields; CLI SIGINT monitor duplication; CLI temp log cleanup; public parser/doc mismatch.

Required correction:

- Make init destination writes symlink-safe across normal and reset paths.
- Align package Python requirement with actual Docling dependency or gate Docling install/runtime clearly.
- Route interactive ticker through the shared scene context slot owner.
- Define and implement a platform-specific command renderer or avoid shell scripts for upload batches.
- Update README to current CLI behavior only.
- Reject non-finite numbers at JSON/config/runtime public boundaries.
- Fix current default test and pyright failures as release-gate work, not by compatibility shims.

Validation profile: production-high; must include CLI init symlink tests, interactive scene tests, command-renderer tests, config finite-number tests, focused README contract smoke, pyright, default pytest, stress test after R3-A runner payload fix, and `git diff --check`.

## Deferred With Owner

| Raw findings | Decision | Owner / destination | Reason |
| --- | --- | --- | --- |
| God files/classes/modules: `tool_runtime.py`, `engine_ingest.py`, `ingestion_runtime.py`, `durable/state.py`, `run_transition.py`, `web_tools.py`, Fins facade bloat | deferred-with-owner | Future architecture debt WU under `WU-SEMANTIC-OWNERSHIP-01` only if user opens a structure/refactor WU | They violate maintainability constraints but the reports mostly provide size/coupling evidence, not a bounded semantic failure path. Folding them into this round would create high-risk churn unrelated to the accepted correctness/security fixes. |
| Broad "24 nested functions" / broad `except Exception` scans | deferred-with-owner | Same future structure/governance WU | Current evidence is pattern-based and not always a semantic-owner failure. Specific broad exceptions with direct semantic loss are accepted in R3-D/R3-E. |
| Broad `Any` / docstring governance including DR-038 | deferred-with-owner | Future typed-contract hardening WU after R3-D narrows financial/read contracts | Direct financial/LLM projection loss is accepted in R3-D. The global 30+ file typing/docstring cleanup is too broad for this correctness round and lacks a single owner boundary. |
| Host importing `dayu.engine.contracts` | needs-more-evidence | Architecture/design discussion | The current package may be acting as a public contract namespace. No direct reverse behavior dependency was proven. Requires design-truth decision before code movement. |
| Engine `__init__.py` re-export concern | rejected-with-reason | None | The finding is compatibility-shape suspicion without a proven failing call path in this review round. |
| Low style-only findings: `Optional[X]` style, `__all__` list vs tuple, docstring style inconsistency, unused local variables | rejected-with-reason | None | Outside semantic ownership drift and not evidence-backed as correctness risk. |
| Low current-non-triggering future risks without owner failure: `ProcessorLRUCache.get()` None sentinel, Playwright post-exit terminate race, `_resolve_response_text_encoding` call-order fragility | deferred-with-owner | Future defensive-hardening WU if surfaced by tests or production evidence | Not accepted for current round because the artifacts explicitly say current runtime does not trigger them. |

## Needs More Evidence

| Raw finding | Reason |
| --- | --- |
| 6-K edgartools fallback completeness | Accepted only to the extent R3-D must either document/validate current BS-only owner contract or add fallback. Whether a second engine is required needs code-level plan evidence. |
| `build_bs_experiment_registry()` no-op | Needs code-level usage check. If unused public surface, delete or document in R3-D; if internal test helper, reject. |
| `service_runtime.py` one-shot assembly cost | No direct semantic failure beyond performance/cost. Do not fix unless R3-C/D changes touch the same owner and expose a bounded resource leak. |

## Sequencing

The six accepted sub WUs are ordered by blast radius and dependency:

1. R3-F release gate baseline and public CLI/config fixes that unblock reliable verification, except the stress failure that depends on R3-A.
2. R3-A Host lifecycle/durable/wait fixes because multiple later validations depend on a trustworthy Host baseline.
3. R3-B Engine provider protocol fixes because Host terminal semantics consume Engine events.
4. R3-C Fins storage/upload/download atomicity and boundary fixes.
5. R3-D Fins financial/read semantics after storage contracts stabilize.
6. R3-E Web/Documents tool egress and diagnostic cap fixes.

The controller may reorder within a batch if code evidence shows a lower-level owner must move first, but must not split by raw finding count. Every accepted sub WU requires AgentCodex plan/implementation/fix, MiMo/DS review or aggregate review per risk, controller validation, and accepted commit before final closeout.

## Stop Status

Round3 adjudication is complete. No code has been modified by this artifact. Next gate: dispatch AgentCodex to produce and implement R3-F first, with the stress subpart explicitly dependent on R3-A runner payload closure.
