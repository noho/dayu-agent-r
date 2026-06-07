# WU-TOOLS-01-F01 Shared Fins Ingestion Runtime And Download / Preprocess Awaiting Tools Plan

## Gate Metadata

- Gate: plan only.
- Work unit: `WU-TOOLS-01-F01 Shared Fins Ingestion Runtime And Download / Preprocess Awaiting Tools`.
- Branch: `host-wu-tools-01-f01`.
- Dirty state at preflight: clean (`git status --short` produced no rows).
- Artifact path: `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`.
- Scope guard: this artifact is the only file written in this gate. Do not enter implementation, review, fix, commit, push or PR gates from this plan gate.

## Goal / Motivation / Success Signal

Goal: establish one shared `dayu.fins` service/runtime foundation for read, download and preprocess/process. Read tools, download tools, preprocess tools, future CLI and CI runners must call this same Fins business runtime instead of duplicating ticker normalization, storage writes, form/date/overwrite semantics, pipeline selection or result normalization.

Motivation: `WU-TOOLS-01` S4 only migrated Fins read tools. The residual `WU-TOOLS-01-S4-R1` exists because download and preprocess/process still lack a NEW shared runtime and current awaiting adapter, not because Host or Engine lacks suspension mechanics.

Success signals:

- `ToolDiscovery` can discover three independent Fins provider groups: read, download and preprocess. The target shape does not rely on `include_ingestion_tools=true`.
- Download and preprocess tool calls return `ToolAwaitingOutcome` during long transactions and are resolved through the current Host wait-resume contract.
- Read, download and preprocess share `DefaultFinsRuntime` / Fins ingestion runtime ownership for storage repositories, ticker normalization, processing and result projection.
- All ticker / market normalization calls go through `dayu.fins.ticker_normalization` public API.
- All financial document access and writes go through `dayu.fins.storage` repository protocols and implementations.
- Current absence of a NEW `dayu/cli` package is treated as a boundary: F01 does not restore CLI/UI; it only makes future CLI a thin adapter over the shared runtime.
- `WU-TOOLS-01-S4-R1` can be closed after implementation if the runtime, providers, waiting adapter path, tests and docs are complete.

## Non-goals / Scope Boundary

- Do not redesign Host / Engine awaiting contracts.
- Do not change `ToolAwaitSpec`, `ToolAwaitingOutcome`, `ResolveWaitRequest`, Host wait record schema or Engine suspend/resume semantics.
- Do not migrate upload. Upload remains `WU-TOOLS-01-F09`.
- Do not migrate old UI / FastAPI / Streamlit ingestion entrypoints.
- Do not restore the whole CLI/UI publishing surface in this work unit. `pyproject.toml` currently declares `dayu-cli = "dayu.cli.main:main"`, but direct code evidence shows no `dayu/cli` package.
- Do not let CI runner, smoke runner or future CLI bypass the shared runtime.
- Do not modify migrated OLD ingestion business function signatures or internals if such functions are reintroduced from OLD code. Adapt them from outer runtime/provider/assembly code.
- Do not build a general platform job system. Build only the Fins-specific runtime, durable job state, background execution and Host wait adapter needed by download/preprocess.
- Do not add ticker parsing, suffix stripping, market inference or company id generation outside `dayu.fins.ticker_normalization`.

## Design Document Alignment

Host design alignment:

- `docs/host/design.md` defines `UI -> Service -> Host -> Engine`. Fins business logic must stay outside Host; Service/composition root maps ToolsDiscovery and wait adapters into `HostToolingOptions`.
- Host design states `dayu.runtime` is layer-neutral and must not import `dayu.fins`. Therefore this work must not put Fins business runtime into `dayu.runtime`; the shared runtime belongs under `dayu.fins`.
- Host design states `ToolsDiscovery` only loads explicit provider callables and returns `ToolBundle`; Host does not discover tools. F01 must expose independent provider callables and update config/tests accordingly.
- Host design states `ToolRuntime / TruncationManager` owns tool execution governance, waiting and duplicate governance. F01 tool providers must return normal `ToolDefinition` callables; awaiting acceptance remains Host-owned.

Engine design alignment:

- `docs/engine/design.md` states Engine only sees tool schemas, tool call requests and tool outcomes; financial document storage is outside Engine and must use `dayu.fins.storage`.
- Engine design states `ToolAwaitingOutcome(await_spec, snapshot)` is the only suspension path, and waiting semantics cannot be hidden in `ToolResult.meta`.
- Engine handshake timeout only bounds `ToolExecutor.execute`; long-running download/preprocess must return `ToolAwaitingOutcome` quickly after durable job creation, before expensive work blocks the Engine handshake.
- Resume is not recovery of an old Engine instance. F01 must map Fins job terminal state into Host `ResolveWaitCompletedOutcome` / `ResolveWaitFailedOutcome` / `ResolveWaitCancelledOutcome` / `ResolveWaitLostOutcome`.

## First-principles Judgment And Direct Code Evidence

Judgment:

The work unit is real and correctly scoped around a missing Fins business runtime. The problem is not a missing tool name list. A production Agent cannot have read tools use one storage/ticker path while download, preprocess, CLI or CI each own separate business rules. That would create divergent document identity, overwrite, market routing and result semantics. The root fix is a shared `dayu.fins` runtime with provider and future CLI adapters around it.

Direct evidence:

- `docs/host/issues-implementation-control.md` marks `WU-TOOLS-01-S4-R1` owner as `WU-TOOLS-01-F01` and states F01 must establish shared Fins ingestion service/runtime before exposing download/preprocess providers.
- `dayu/fins/service_runtime.py` docstring and `DefaultFinsRuntime` currently assemble only read tool repositories, processor registry and `FinsToolService`; it explicitly says download/preprocess ingestion job semantics are not exposed.
- `dayu/fins/tools/provider.py` has `_CONFIG_INCLUDE_INGESTION_TOOLS_FIELD = "include_ingestion_tools"` and raises `ValueError` when enabled, with the message that ingestion requires `ToolAwaitingOutcome` or wait-adapter semantics.
- `dayu/fins/tools/fins_tools.py` only registers the read tool factories: `list_documents`, `get_document_sections`, `read_section`, `search_document`, `list_tables`, `get_table`, `get_page_content`, `get_financial_statement`, `query_xbrl_facts`.
- `dayu/fins/tools/service.py` uses `try_normalize_ticker` in `_resolve_canonical_ticker`, and storage `_fs_storage_utils.py` also routes `_normalize_ticker` through `try_normalize_ticker`; this is the current ticker normalization pattern to preserve and extend.
- `dayu/fins/ticker_normalization.py` declares itself the only ticker normalization truth and exposes `normalize_ticker`, `try_normalize_ticker`, `ticker_to_company_id`.
- `dayu/fins/storage/repository_protocols.py` already defines repository protocols for company metadata, source documents, processed documents, blob files, batching and filing maintenance. F01 must build on these, not file-tree ad hoc access.
- `dayu/contracts/tool_await.py` defines only `ToolAwaitKind.EXTERNAL_JOB`, `ToolAwaitSpec(deadline, resume_token)` and `ToolAwaitSnapshot`; it has no arbitrary payload bag.
- `dayu/contracts/tool_outcome.py` defines `ToolAwaitingOutcome`; waiting semantics are separate from completed/failed tool results.
- `dayu/host/wait_adapter.py` already has `WaitAdapterBinding`, `WaitAdapterRegistry`, `WaitPollAdapter`, `WaitPollAdapterRegistry` and `WaitPoller`.
- `dayu/host/tool_runtime.py` accepts awaiting only when `awaiting_accept_port` and `wait_adapter_registry` are configured; otherwise it returns governed failure `awaiting_adapter_not_configured`.
- `dayu/service/host_assembly.py` currently maps discovered tools to `HostToolingOptions(..., wait_adapter_registry=None)`. F01 must add minimal composition-root wiring for Fins wait adapters; otherwise tools returning `ToolAwaitingOutcome` will fail before Host wait acceptance.
- `tests/fins/test_fins_storage_provider.py` covers read provider discovery, fail-closed `include_ingestion_tools`, ToolRuntime execution for read tools, storage boundaries and import boundaries.
- `dayu/fins/README.md` currently states provider does not expose download/preprocess ingestion tools and that migration is pending F01.
- `pyproject.toml` declares `dayu-cli = "dayu.cli.main:main"`, but `find dayu -maxdepth 2 -type d` shows no `dayu/cli` directory. Therefore F01 must not claim current CLI implementation; future CLI owner must wrap shared runtime.

## Affected Files / Modules

Expected production modules:

- `dayu/fins/service_runtime.py`
- `dayu/fins/ingestion_runtime.py` or split modules under `dayu/fins/ingestion/`
- `dayu/fins/tools/provider.py`
- `dayu/fins/tools/download_provider.py`
- `dayu/fins/tools/preprocess_provider.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/tools/__init__.py`
- `dayu/service/host_assembly.py`
- `dayu/config/tool_discovery.json`

Expected tests:

- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/service/test_host_assembly.py`
- focused Host waiting integration tests only if existing `tests/host` coverage cannot prove Fins adapter wiring through public Host path.

Expected docs after implementation:

- `dayu/fins/README.md`
- `tests/README.md`
- `dayu/config/README.md` if default tool discovery config names or provider examples change.
- Root `README.md` only if this work changes real user-facing CLI commands or published usage. F01 should not update root README to claim CLI download/process because current `dayu/cli` is absent.

## Contract / Schema / State-machine / Public-interface Changes

No changes:

- No Host durable schema change.
- No Engine public contract change.
- No `ToolAwaitSpec`, `ToolAwaitingOutcome`, `ResolveWaitRequest`, `WaitRecordStatus` or `WaitResumePolicy` change.
- No `ToolsDiscoveryProviderSpec` / `ToolsDiscoveryProviderOutput` shape change.
- No CLI command contract change in this work unit.

Added Fins-owned typed shapes:

- Fins runtime request/result dataclasses for read/runtime access, download and preprocess.
- Fins ingestion job status enum: `queued`, `running`, `cancelling`, `succeeded`, `failed`, `cancelled`. `lost` is not normal job terminal state; the Host poll adapter maps missing/corrupt/stale job evidence to `ResolveWaitLostOutcome`.
- Fins durable job record shape stored under Fins runtime ownership, not Host durable store. It must include job id, operation kind, normalized ticker, market, optional form/date filters, overwrite/rebuild flags, status, created/updated/started/finished timestamps, result summary or failure summary, and cancellation flag.
- Fins wait adapter factory returning `WaitAdapterRegistry` bindings for download/preprocess tool names with `ToolAwaitKind.EXTERNAL_JOB`, `WaitResumePolicy.POLL`, `WaitExternalJobRefSource.RESUME_TOKEN`.
- Fins `WaitPollAdapter` implementation that maps Fins job state to `WaitPollNotReady`, `WaitPollReady` or `WaitPollLost`.

Provider public interface target:

- Keep read provider callable for read tools.
- Add independent download provider callable.
- Add independent preprocess provider callable.
- Update `dayu.fins.tools` exports without keeping compatibility re-export solely for old names if the old name becomes misleading. If `discover_tools` remains, it must mean read provider only or be clearly named; do not keep a mixed provider facade for compatibility.

## Implementation Decisions

Shared runtime ownership:

- `dayu.fins.service_runtime.DefaultFinsRuntime` becomes the common assembly root for Fins repositories, processor registry, read service and ingestion service.
- Fins ingestion service/runtime lives under `dayu.fins`, not `dayu.runtime`, `dayu.host` or tool provider modules.
- "Shared runtime" means shared Fins business code plus workspace-scoped durable state. It does not require one Python object instance shared by every provider.
- Do not introduce a module-level singleton or hidden memoized global runtime factory. Runtime lifecycle must remain explicit in providers or Service assembly.
- Tool providers may each call `DefaultFinsRuntime.create(workspace_root=...)`, but every runtime instance for the same `workspace_root` must derive the same Fins job store path and use cross-instance-safe writes.
- Tool providers receive only provider config, construct/get a Fins runtime for the configured workspace, then adapt runtime operations into `ToolDefinition` callables.
- Future CLI and CI runners must instantiate the same `DefaultFinsRuntime` / ingestion service and call the same methods. They may parse CLI args or print output, but must not implement download/process rules.

Download/preprocess long transaction model:

- Tool callable validates lightweight arguments, calls `FinsIngestionRuntime.start_download(...)` or `start_preprocess(...)`, persists a durable job record, launches/queues the Fins-specific background job and returns `ToolAwaitingOutcome`.
- `await_spec.await_kind = ToolAwaitKind.EXTERNAL_JOB`.
- `await_spec.resume_token = job_id`. It is an opaque Host-owned/external-job reference for resume, not business data or authorization.
- `snapshot` may contain a Fins job snapshot id and captured time. It must not carry raw business payload.
- Job state transitions:
  - start creates `queued`;
  - executor claims to `running`;
  - cancellation request moves active job to `cancelling`;
  - successful pipeline writes source/processed data through storage and transitions to `succeeded`;
  - known business/validation/runtime failure transitions to `failed` with bounded diagnostic;
  - cooperative cancellation transitions to `cancelled`;
  - missing/corrupt/stale job evidence is mapped by adapter as Host wait `lost`.
- Poll adapter mapping:
  - `queued` / `running` / `cancelling` -> `WaitPollNotReady`;
  - `succeeded` -> `WaitPollReady(ResolveWaitCompletedOutcome)`;
  - `failed` -> `WaitPollReady(ResolveWaitFailedOutcome)`;
  - `cancelled` -> `WaitPollReady(ResolveWaitCancelledOutcome)`;
  - missing/corrupt/stale -> `WaitPollLost(ResolveWaitLostOutcome)`.
- `abandon_wait` marks the Fins job cancellation requested; it must not delete source documents or Host wait records.

Ticker normalization:

- Download routing must call `normalize_ticker(...)` when market selection is required.
- Read path may keep `try_normalize_ticker(...)` plus company alias fallback because current read behavior intentionally supports workspace aliases.
- Preprocess/process must normalize ticker through `normalize_ticker(...)` or `try_normalize_ticker(...)` depending on whether it only touches already stored workspace documents; it must not infer market by suffix parsing.
- Company id generation must call `ticker_to_company_id(...)` if needed.

Storage boundary:

- Source documents, blob files, processed documents, rejected filing artifacts and batching must use `dayu.fins.storage` repository protocols/implementations.
- No direct `Path(".../filings")`, `Path(".../processed")`, glob or raw JSON writes outside storage repository internals for financial document data.
- The Fins job store may use runtime-owned files because job governance state is not financial document content; it must not store source document payloads or processed payloads.
- The Fins job store path must be deterministic from `workspace_root`, such as `<workspace_root>/.dayu/fins_ingestion/jobs` or an equivalent explicit Fins runtime directory.
- The Fins job store must save only job governance records and must use atomic replacement plus a lock, or an equivalent transactional filesystem-safe mechanism, so separate runtime instances for the same workspace cannot corrupt job state.

Download adapter scope:

- F01 implements the typed download runtime, the source adapter protocol, deterministic no-network fake adapter test path, storage write path and explicit unsupported-source failure.
- F01 does not implement real SEC/CN/HK network download adapters. Real adapter breadth is deferred to a later Fins source-adapter owner or requires explicit user-approved F01 scope expansion.
- The download runtime may route to an adapter selected from normalized ticker/market/source fields, but absent real adapters must produce a bounded unsupported-source failure instead of fake success.

Provider split:

- Read provider remains read-only and must remove `include_ingestion_tools` parsing from the target implementation after download/preprocess providers exist.
- `include_ingestion_tools` is not a supported target config. Workspace overlays must enable download/preprocess capability through independent download and preprocess providers.
- Download provider exposes only download start tool(s), tagged `fins` and `fins-download`, with LLM-facing schema that explains ticker, forms/date filters and overwrite/rebuild semantics without internal ids.
- Preprocess provider exposes preprocess/process start tool(s), tagged `fins` and `fins-preprocess`, with schema that explains stored-document processing.
- Avoid start/status/cancel polling tools as the target shape. Host wait-resume owns status/resume; explicit cancel remains Host/user wait cancellation unless a later approved design adds user-facing cancellation tools.

Service/composition-root adapter:

- Because `HostToolingOptions.wait_adapter_registry` currently defaults to `None`, implementation must add minimal Service assembly wiring that builds a Fins wait adapter registry when Fins download/preprocess providers are enabled.
- This wiring belongs in Service/composition root or a Fins-provided assembly helper called by Service. It must not change Host or Engine contracts.
- Service assembly detects Fins awaiting providers from explicit configured provider ids, import paths and binding specs already visible in `tool_discovery.json` / provider config. It must not inspect diagnostic strings.
- Service assembly must validate that enabled Fins awaiting providers for one Host assembly use a matching absolute `workspace_root`, then build the Fins wait adapter registry once for that workspace.
- Do not change `ToolsDiscoveryProviderOutput` shape to carry Fins wait adapter objects or awaiting-provider metadata.
- If multiple Fins providers are enabled, their wait adapter bindings must be combined deterministically and fail on duplicate tool binding.

CLI boundary:

- Current repo has no `dayu/cli` package. F01 must not restore CLI commands.
- Plan residual/owner: future NEW CLI download/process must be a thin adapter over `DefaultFinsRuntime` / `FinsIngestionRuntime`; it must not reimplement download/process logic.

## Small Implementation Slices

### S1 - Shared Fins Runtime Foundation

Objective: make `DefaultFinsRuntime` the shared read/download/preprocess assembly root and add Fins-owned typed job/request/result shapes.

Allowed files/modules:

- `dayu/fins/service_runtime.py`
- new `dayu/fins/ingestion_runtime.py` or `dayu/fins/ingestion/*.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- no Host/Engine changes

Prerequisites:

- Existing read provider tests pass before changes.
- Confirm no production `dayu/cli` package exists; do not add CLI.

Exact allowed changes:

- Add Fins ingestion request/result dataclasses for download and preprocess with strict typed fields. No `Any`, `object`, untyped params or untyped returns.
- Add `FinsIngestionJobStatus` enum and durable Fins job record dataclass.
- Add Fins job store interface and filesystem implementation for job records only.
- Derive the job store path from `workspace_root`, for example `<workspace_root>/.dayu/fins_ingestion/jobs`, or from an equivalent explicit Fins runtime directory under the workspace.
- Implement job record writes with atomic/locked semantics so multiple runtime instances in the same workspace are safe without a module-level singleton.
- Extend `DefaultFinsRuntime.create(...)` to instantiate shared storage repositories already used by read tools plus ingestion runtime.
- Add `get_ingestion_service()` / `get_ingestion_runtime()` with locking pattern analogous to `get_tool_service()`.
- Keep read `get_tool_service()` behavior stable.

Functions/classes/types/call paths:

- `DefaultFinsRuntime.create(workspace_root=...)`
  -> `build_fs_repository_set(...)`
  -> storage repository implementations
  -> `FinsToolService`
  -> `FinsIngestionRuntime`
- `FinsIngestionRuntime.start_download(request) -> FinsIngestionJobStart`
- `FinsIngestionRuntime.start_preprocess(request) -> FinsIngestionJobStart`
- `FinsIngestionRuntime.read_job(job_id) -> FinsIngestionJobRecord`
- `FinsIngestionRuntime.request_cancel(job_id) -> FinsIngestionJobRecord`

Data flow/state transitions/error handling/invariants:

- `start_*` normalizes ticker through `dayu.fins.ticker_normalization`.
- `start_*` persists `queued` before launching any expensive work.
- Job id is stable, ASCII and opaque.
- Job store records contain governance state only: job id, operation kind, normalized request summary, status/timestamps, bounded result summary, bounded failure summary and cancellation flag. They must not contain source document正文, processed payloads, provider raw payloads or raw filesystem document paths exposed to tools.
- Validation errors before job creation raise typed argument/business errors and must become regular failed tool outcomes in providers.
- Once a job reaches `succeeded`, `failed` or `cancelled`, runtime must not transition it back to active.
- Job result summary must be JSON-compatible and bounded; no full documents or raw provider payloads in job records.

Non-goals:

- No provider registration.
- No Host wait adapter.
- No real CLI.
- No upload.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- Read runtime still returns `FinsToolService`.
- Ingestion runtime uses storage repository protocols, not raw document paths.
- Ticker normalization calls are through `dayu.fins.ticker_normalization`.
- Job start creates durable `queued` record before execution.
- Two `DefaultFinsRuntime.create(workspace_root=same_root)` instances read/write the same workspace-derived job store safely without sharing a Python object singleton.

Completion signal:

- Runtime foundation can start deterministic fake download/preprocess jobs in tests and read terminal job records.

Stop condition:

- Stop if implementing durable Fins job state requires Host durable schema changes.

### S2 - Preprocess / Process Runtime Pipeline

Objective: implement preprocess/process as a Fins runtime business operation over existing source documents and processed storage.

Allowed files/modules:

- `dayu/fins/ingestion_runtime.py` or `dayu/fins/ingestion/*.py`
- `dayu/fins/service_runtime.py`
- existing `dayu/fins/storage` protocols only if a missing repository method is directly required
- `tests/fins/test_fins_ingestion_runtime.py`

Prerequisites:

- S1 complete.
- Existing storage protocols can read source documents and write processed documents.

Exact allowed changes:

- Implement `start_preprocess` background job execution.
- Resolve ticker/document selection through storage repositories.
- Use existing `dayu.fins.processors` / `dayu.documents.processors` processor registry to produce processed outputs.
- Write processed metadata/sections/tables/financials through `ProcessedDocumentRepositoryProtocol`.
- Support explicit document ids and whole-ticker processing with bounded selection.
- Support overwrite/reprocess flags through runtime semantics, not tool provider-specific logic.

Functions/classes/types/call paths:

- `FinsIngestionRuntime.start_preprocess(request)`
  -> `FinsIngestionJobStore.create_queued(...)`
  -> `FinsIngestionExecutor.submit(...)`
  -> source repository list/read
  -> processor registry
  -> processed repository create/update
  -> job store terminal update

State transitions:

- `queued -> running -> succeeded`
- `queued/running -> cancelling -> cancelled`
- `queued/running -> failed`

Error handling/invariants:

- Missing ticker/document produces `failed` terminal result with bounded message, not an unobserved thread exception.
- Processor unsupported document produces per-document skipped/not_supported summary; whole job fails only when no requested document can be processed and policy says fail.
- Storage writes must be batch-safe where existing repositories provide batching.
- No direct writes to `processed/` outside repository implementation.

Non-goals:

- No upload.
- No CI runner.
- No source download.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- Existing source fixture can be preprocessed to processed repository.
- Overwrite false skips existing processed document.
- Overwrite true updates processed document.
- Cancellation request before execution leads to `cancelled`.
- Runtime job summary contains business-readable counts and document ids, not internal Host refs.

Completion signal:

- Preprocess runtime is usable by both future CLI adapter and tool adapter without duplicating process logic.

Stop condition:

- Stop if existing processor/storage boundaries cannot express required processed output without direct file-tree writes; do not bypass `dayu.fins.storage`.

### S3 - Download Runtime Pipeline

Objective: implement download as a Fins runtime business operation that writes source documents through storage and shares job semantics with preprocess.

Allowed files/modules:

- `dayu/fins/ingestion_runtime.py` or `dayu/fins/ingestion/*.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/storage` protocols/implementations only if current protocols cannot express required source/blob/rejected filing writes
- `tests/fins/test_fins_ingestion_runtime.py`

Prerequisites:

- S1 complete.
- Direct code search confirms current repo does not contain NEW `FinsIngestionService` or CLI download implementation. If OLD source-specific download functions are reintroduced during implementation, wrap them; do not change their signatures.

Exact allowed changes:

- Implement `start_download` using the same job store/executor as preprocess.
- Add a typed source download adapter protocol whose request/response shapes are owned by `dayu.fins` and contain business-readable fields only.
- Add a deterministic no-network fake download adapter for runtime tests.
- Normalize ticker and market via `normalize_ticker(...)`.
- Route request to source-specific download adapter only after normalization.
- Persist downloaded source documents through `SourceDocumentRepositoryProtocol`, blob repository and filing maintenance repository as needed.
- Persist rejected filing artifacts through `FilingMaintenanceRepositoryProtocol` where applicable.
- Return explicit unsupported-source failure when no adapter is available for the normalized source/market.
- Normalize result summary into counts: discovered, downloaded, skipped, rejected, failed, written document ids.

Functions/classes/types/call paths:

- `FinsIngestionRuntime.start_download(request)`
  -> `normalize_ticker(...)`
  -> market/source adapter selection
  -> source repository/blob/maintenance repositories
  -> job terminal result

Data flow/state transitions/error handling/invariants:

- Same job transitions as S2.
- Download adapters must not infer market by ticker suffix. They receive `NormalizedTicker`.
- If source-specific implementation is unavailable for a market/source, fail with explicit unsupported-source result; do not silently fabricate success.
- Network/provider raw payloads must not be stored in job records or LLM-facing tool results.
- `rebuild` or `overwrite` semantics belong in runtime request handling, not provider schema code.

Non-goals:

- No real SEC/CN/HK network download adapter implementation in F01.
- No broad real-network smoke in this slice unless explicitly opt-in by a later approved scope expansion.
- No CI pipeline migration.
- No CLI command.
- No upload.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- Deterministic fake/download adapter writes source document through storage protocols.
- Unsupported market/source produces failed job with clear business error.
- Repeated start with same semantic request either reuses/skips according to runtime policy or creates a new job with deterministic storage skip result; provider must not invent separate duplicate semantics.
- Ticker normalization is called through `normalize_ticker(...)`.

Completion signal:

- Download runtime has a production-owned typed entry point, adapter protocol, deterministic no-network fake adapter test path, storage write path and explicit unsupported-source failure. Real SEC/CN/HK network adapter breadth is deferred to a later owner or explicit user-approved scope expansion.

Stop condition:

- Stop and request user decision before adding real SEC/CN/HK network download adapters or rebuilding full downloader parity inside F01. Current repo evidence does not contain those NEW source-specific download implementations.

### S4 - Download / Preprocess Awaiting Tool Providers

Objective: expose independent Fins download and preprocess providers that adapt shared runtime starts into `ToolAwaitingOutcome`.

Allowed files/modules:

- `dayu/fins/tools/provider.py`
- `dayu/fins/tools/download_provider.py`
- `dayu/fins/tools/preprocess_provider.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/tools/__init__.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_storage_provider.py`

Prerequisites:

- S1 complete.
- S2/S3 runtime start methods available.

Exact allowed changes:

- Keep read provider focused on read tools.
- Remove read-provider `include_ingestion_tools` parsing after split providers exist; after implementation, the old fail-closed test must be replaced with independent provider discovery tests.
- Add download provider callable with provider id/version/source ref distinct from read provider.
- Add preprocess provider callable with provider id/version/source ref distinct from read provider.
- Register download/preprocess tool callables that call shared runtime and return `ToolAwaitingOutcome`.
- Tool schemas must be self-explanatory for LLMs and not expose Host internals, digest, cursor, raw job record paths or tool_call_id.

Functions/classes/types/call paths:

- `download_provider.discover_tools(spec)`
  -> parse explicit absolute `workspace_root`
  -> `DefaultFinsRuntime.create(...)`
  -> `runtime.get_ingestion_runtime()`
  -> register download tool definitions
- `preprocess_provider.discover_tools(spec)`
  -> same runtime path
  -> register preprocess tool definitions
- Tool callable:
  -> runtime `start_*`
  -> `_awaiting_outcome_from_job_start(...)`

State transitions:

- Provider itself creates no state except through shared runtime job start.
- Tool returns awaiting only after job is durable.
- Separate provider-created runtime instances for the same workspace must converge on the same workspace-derived job store through `DefaultFinsRuntime.create(workspace_root=...)`.

Error handling/invariants:

- Config parsing remains fail-fast for non-absolute `workspace_root`.
- `include_ingestion_tools` is not accepted as a target enablement switch; download/preprocess enablement must come from independent providers in workspace overlay config.
- Tool argument errors before durable job creation become `ToolFailedOutcome`.
- Once runtime returns job start, callable must not block until job completion.
- Tool names must not collide with read tools or framework reserved names.

Non-goals:

- No status/cancel polling tools.
- No CLI.
- No old mixed provider facade as target architecture.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_storage_provider.py tests/runtime/test_config_loader.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- ToolsDiscovery can discover read, download and preprocess providers independently.
- Provider reports list separate provider ids/spec ids/tool names.
- Download/preprocess tool call returns `ToolAwaitingOutcome` with `EXTERNAL_JOB`.
- `include_ingestion_tools=true` is no longer the target path, no longer parsed by the read provider for ingestion enablement, and no longer required for discovery.

Completion signal:

- ToolDiscovery target shape is split by provider group and all Fins ingestion tool callables adapt only to shared runtime.

Stop condition:

- Stop if ToolDiscovery shape must change to carry provider-specific wait adapter objects. Use Service composition-root wiring instead.

### S5 - Fins Wait Adapter And Service Assembly Wiring

Objective: wire Fins awaiting tools into current Host wait-resume contract without changing Host/Engine contracts.

Allowed files/modules:

- `dayu/fins/ingestion_runtime.py` or `dayu/fins/ingestion/*.py`
- `dayu/service/host_assembly.py`
- `tests/service/test_host_assembly.py`
- `tests/fins/test_fins_ingestion_tools.py`
- focused `tests/host` waiting integration only if needed

Prerequisites:

- S1 complete.
- S4 tool names stable.
- Existing Host waiting tests remain unchanged unless Fins-specific integration coverage is needed.

Exact allowed changes:

- Add Fins poll adapter that implements `WaitPollAdapter`.
- Add Fins wait adapter binding factory for download/preprocess tool names.
- Update Service host assembly to pass `wait_adapter_registry` into `HostToolingOptions` when Fins awaiting providers are enabled.
- Detect Fins awaiting providers from explicit configured provider ids, import paths and binding specs already visible to Service assembly.
- Validate that all enabled Fins awaiting provider configs participating in one assembly have the same absolute `workspace_root`; fail before `open_host` on mismatch.
- Build one Fins wait adapter registry for the validated workspace and bind it to the stable download/preprocess tool names.
- Combine Fins wait bindings deterministically with no duplicate binding.
- Keep `ToolsDiscovery` layer-neutral; do not add Fins imports to `dayu.runtime`.
- Do not change `ToolsDiscoveryProviderOutput` shape and do not depend on provider diagnostics strings.

Functions/classes/types/call paths:

- `FinsIngestionWaitPollAdapter.poll_wait(wait_record)`
  -> runtime/job store read by `wait_record.external_job_id`
  -> map state to `WaitPollResult`
- `FinsIngestionWaitPollAdapter.abandon_wait(wait_record)`
  -> runtime `request_cancel(job_id)`
- `build_fins_wait_adapter_registry(...)`
  -> `WaitAdapterRegistry((WaitAdapterBinding(...), ...))`
- `dayu.service.host_assembly`
  -> inspect explicit configured provider ids/import paths/binding specs
  -> detect enabled Fins download/preprocess provider config
  -> validate matching absolute `workspace_root`
  -> build registry
  -> `HostToolingOptions(wait_adapter_registry=registry)`

State transitions:

- Host wait record remains Host-owned.
- Fins job remains Fins-owned.
- Poll adapter is the only bridge from Fins terminal job state to Host `resolve_wait`.

Error handling/invariants:

- Missing job id maps to `ResolveWaitLostOutcome`, not an uncaught exception.
- Corrupt job record maps to lost with bounded diagnostic.
- Adapter exceptions are allowed to be caught by existing `WaitPoller` and counted as adapter errors.
- Service assembly fails before `open_host` if Fins awaiting provider config cannot construct a wait adapter registry.
- Service assembly fails before `open_host` if enabled Fins awaiting providers have different workspace roots.

Non-goals:

- No Host public API change.
- No Engine change.
- No callback endpoint.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/fins/test_fins_ingestion_tools.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- Service assembly with enabled Fins download/preprocess providers produces `HostToolingOptions.wait_adapter_registry is not None`.
- Service assembly detects Fins awaiting providers from configured ids/import paths/binding specs, not diagnostic strings.
- Workspace root mismatch across Fins awaiting providers fails before `open_host`.
- A Fins awaiting tool call is accepted by ToolRuntime when registry is present.
- Poll adapter maps succeeded/failed/cancelled/missing jobs to the expected Host resolve outcome envelopes.
- When registry is absent, existing Host governed failure behavior remains covered by current Host tests.

Completion signal:

- Representative Fins download/preprocess path can suspend and resolve through current Host wait-resume contract.

Stop condition:

- Stop if implementation requires adding fields to `HostToolingOptions`, changing `WaitAdapterBinding`, or changing Host durable wait schema.

### S6 - Config, Docs And Regression Closeout

Objective: align default config, package docs and tests with the new provider split and close F01 residuals.

Allowed files/modules:

- `dayu/config/tool_discovery.json`
- `dayu/config/README.md` if config examples change
- `dayu/fins/README.md`
- `tests/README.md`
- affected tests from S1-S5

Prerequisites:

- S1-S5 complete.

Exact allowed changes:

- Replace default mixed Fins provider config with separate disabled provider entries for Fins read, Fins download and Fins preprocess if implementation uses separate import paths.
- Delete or rewrite tests that assert read-provider `include_ingestion_tools` fail-closed behavior; target coverage must prove independent download/preprocess provider enablement through workspace overlay config.
- Update `dayu/fins/README.md` to describe implemented read/download/preprocess runtime and provider split.
- Update `tests/README.md` if new Fins ingestion tests introduce new fixture or opt-in network/heavy-test convention.
- Update `dayu/config/README.md` only if provider config shape examples change.
- Do not update root README to advertise `dayu-cli download/process`; current CLI package is absent.

Tests/validation commands:

- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- Default config keeps providers disabled unless workspace overlay explicitly enables them.
- Workspace overlay can enable read/download/preprocess independently.
- Workspace overlay does not use `include_ingestion_tools` as a supported target config.
- README statements match current code.

Completion signal:

- Docs and config no longer describe `include_ingestion_tools` as the target shape, and no README claims future CLI behavior as implemented.

Stop condition:

- Stop if root README cleanup expands into broad CLI documentation correction unrelated to F01; that belongs to a separate CLI/package surface work unit.

## Tests / Validation Commands And Expected Assertions

Plan gate validation already run:

- `git branch --show-current` -> `host-wu-tools-01-f01`
- Original plan gate recorded `git status --short` as clean. Fix-gate validation must report current dirty state separately and must confirm only this plan artifact was edited in the fix pass.

Implementation validation required after code changes:

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py`
  - read provider still works;
  - storage boundary still enforced;
  - import boundary still enforced.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py`
  - shared runtime creates durable jobs;
  - preprocess writes through processed repository;
  - download writes through source/blob repositories;
  - cancellation and failure states are deterministic.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py`
  - download/preprocess providers discover independently;
  - tool callables return `ToolAwaitingOutcome`;
  - schemas are self-contained and do not expose Host internals.
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py`
  - Service maps enabled Fins awaiting providers to `HostToolingOptions.wait_adapter_registry`;
  - non-Fins tool assembly remains unchanged.
- `source .venv/bin/activate && pytest tests/host/test_phase7_waiting_integration.py tests/host/test_public_resolve_wait_resume.py`
  - existing Host wait-resume behavior remains valid with Fins-style bindings.
- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py`
  - config and combined discovery still load.
- `source .venv/bin/activate && pyright`
  - no new or expanded type errors.

## Docs Decision

README sync decision after tests:

- Update `dayu/fins/README.md`: yes, implementation changes Fins provider/runtime behavior.
- Update `tests/README.md`: yes if new Fins ingestion fixture, fake source adapter, heavy/network skip convention, or coverage boundary is introduced.
- Update `dayu/config/README.md`: yes if default `tool_discovery.json` provider entries or example config change.
- Update root `README.md`: no for this work unit unless a real CLI package/command is implemented, which is explicitly non-goal.
- Update `dayu/README.md`: only if implementation changes stable package/layer boundaries; the intended plan should not require it.

## Risks / Open Questions

Fixed in current slices:

- `WU-TOOLS-01-S4-R1`: covered by S1-S6 if shared runtime, split providers and wait adapter integration complete.
- Current `include_ingestion_tools` fail-closed transition: covered by S4/S6.
- Host awaiting adapter missing for Fins tools: covered by S5.

Covered by later approved slice:

- README/config synchronization: S6.
- Deterministic no-network runtime/tool tests before broader smoke: S1-S5.

Assigned to later work unit:

- Real SEC/CN/HK network download adapter breadth is deferred to later Fins source-adapter work or explicit user-approved F01 scope expansion; F01 only provides typed runtime, adapter protocol, deterministic no-network fake path, storage write path and unsupported-source failure.
- Upload migration and upload ingestion tool: `WU-TOOLS-01-F09`.
- SEC/Fins CI process runner and scoring pipeline must call shared runtime: `WU-TOOLS-01-F04/F05`.
- CN/HK Docling CI process runner must call shared runtime: `WU-TOOLS-01-F06/F07`.
- Future NEW CLI download/process must wrap shared runtime only. Current code has no `dayu/cli`; owner must be a future CLI/package work unit or a user-approved F01 extension, not an incidental side effect.

Tracked by existing issue:

- `WU-TOOLS-01-S1-R1` remains with F04-F07 owners for CI coverage.
- `WU-TOOLS-01-S1-R2` remains with F08 owner for documents processor registry naming cleanup.

Requiring user decision:

- Adding real SEC/CN/HK network download adapters to F01 requires explicit user approval because current repo evidence shows those NEW source-specific implementations are absent.
- Whether to remove stale root README CLI references is outside F01 unless the user opens a CLI/package documentation work unit.

No blocking open question for this plan gate:

- The design sources are sufficient to keep Host/Engine contracts unchanged.
- Current code evidence is sufficient to decide CLI boundary.
- The implementation slices are reviewable if S3 stays within typed runtime, adapter protocol, deterministic no-network fake path, storage write path and unsupported-source failure.

## Why This Is Not Over-designed

- It does not introduce a generic job platform; job state, executor and poll adapter are Fins-specific and only support download/preprocess long transactions.
- It reuses current Host wait-resume contracts instead of adding status/cancel tools or new Host state.
- It keeps `ToolsDiscovery` layer-neutral and uses Service/composition root for wait adapter wiring, matching Host design.
- It keeps storage and ticker normalization true sources instead of adding provider/CLI helper duplicates.
- It splits provider groups only because discovery, selection and awaiting semantics differ; it does not create unnecessary abstraction for unrelated tool families.
- It defers CLI/UI restoration and upload instead of expanding the work unit across publishing surfaces.

## Completion Report Format

Implementation closeout for this work unit must report:

- Artifact path: implementation/review artifacts and this plan path.
- First-principles judgment: whether F01 remained a shared runtime fix rather than tool-name migration.
- Proposed/completed slices: completed slice ids and any approved deviations.
- Validation run: exact pytest and pyright commands with results.
- Docs decision: README files updated or explicitly not updated, with reason.
- Open questions / residual risks: every residual classified as fixed in current slice, covered by later approved slice, assigned to later work unit, tracked by existing issue, or requiring user decision.
