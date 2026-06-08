# WU-TOOLS-01-F01 PR Review (AgentDS)

**Review target:** PR [#126](https://github.com/noho/dayu-agent-r/pull/126)
**Branch:** `host-wu-tools-01-f01`
**Date:** 2026-06-08
**Review type:** PR review gate (final deepreview before merge)

---

## Verdict: pass-with-findings

PR is merge-ready. No correctness, stability, or layering blocks found. All 91
tests pass, pyright reports 0 errors. Four findings below are either
accepted-risk design notes or follow-up refinements that do not need to block
merge.

---

## Scope summary

This PR builds the shared Fins ingestion runtime foundation (download +
preprocess) and wires it into the Host/ToolRuntime wait-resume contract via
independent `ToolsDiscovery` providers and a Fins-specific `WaitAdapterRegistry`.

Key additions (~16K lines, ~15K net new):

| Layer | Files | What |
|---|---|---|
| Fins domain | `dayu/fins/ingestion_runtime.py` (2700L) | Typed request/result dataclasses, job record + status machine, filesystem job store with `fcntl` locking, `FinsIngestionRuntime` orchestrator, bounded validation helpers |
| Fins tools | `dayu/fins/tools/download_tools.py`, `preprocess_tools.py` | `ToolDefinition` callables that start durable jobs and return `ToolAwaitingOutcome` |
| Fins tools | `dayu/fins/tools/download_provider.py`, `preprocess_provider.py` | Independent `ToolsDiscovery` providers that each demand an explicit absolute `workspace_root` |
| Fins ingestion | `dayu/fins/ingestion/wait_adapter.py` (380L) | `FinsIngestionWaitPollAdapter` mapping Fins job status → Host `WaitPollResult` |
| Fins assembly | `dayu/fins/service_runtime.py` | `get_ingestion_runtime()` lazy singleton on `DefaultFinsRuntime` |
| Service assembly | `dayu/service/host_assembly.py` | `_fins_wait_adapter_registry_from_provider_configs()` auto-builds registry from enabled providers |
| Host public API | `dayu/host/api.py` | `purge_session` added to `Host` protocol (unrelated infrastructure enablement) |
| Config | `dayu/config/tool_discovery.json` | Split single `financial-tools` into three independent providers (`financial-read-tools`, `financial-download-tools`, `financial-preprocess-tools`), all default-disabled |
| Docs | 5 READMEs + design docs | Updated to reflect split provider architecture and ingestion runtime |

---

## Findings

### F1 — `_fsync_directory` is POSIX-only (accepted risk)

**File:** `dayu/fins/ingestion_runtime.py:2662-2679`
**Severity:** low

```python
def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
```

`os.fsync` on a directory fd is a POSIX guarantee (Linux/macOS). On Windows,
`os.fsync` on a directory handle will raise `OSError`. The project targets
Python 3.11 on macOS/Linux, so this is acceptable. The `FsFinsIngestionJobStore`
is not the only persistence path — the rest of the system already uses SQLite
which handles fsync internally — so this is a localized ingestion concern.

**Why not blocking:** Project runtime environment is POSIX-only. The atomic
write pattern (`tmp → fsync → os.replace → fsync dir`) is the correct POSIX
recipe for durable job records.

---

### F2 — `_timestamp_or_now` silently swallows malformed timestamps (design note)

**File:** `dayu/fins/ingestion/wait_adapter.py:338-352`
**Severity:** low

```python
def _timestamp_or_now(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
```

If a Fins job record contains a corrupted timestamp, the adapter silently
substitutes `datetime.now(timezone.utc)`. This means a corrupted `started_at`
or `finished_at` in a job record will produce a `ToolResultMeta` with a
`finished_at` that may precede `started_at` (the `max(started_at, finished_at)`
guard at line 329-330 partially mitigates this). The produced `ToolResultMeta`
is not used for governance decisions — only for LLM display — so the blast
radius is low.

**Why not blocking:** The timestamps come from Fins job records that were
written by `_utc_now()` in the same codebase, so malformation requires
filesystem corruption or manual editing. The fallback is defensive and the
impact is cosmetic.

---

### F3 — No `FinsIngestionWaitPollAdapter` factory is used at assembly time (design note)

**File:** `dayu/fins/ingestion/wait_adapter.py:86-99`
**Severity:** note

`FinsIngestionWaitPollAdapter.from_workspace_root()` exists but
`build_fins_wait_adapter_registry()` does not call it. The registry only
produces `WaitAdapterBinding` entries (tool → adapter_key → resume_policy
mappings). The actual poll adapter instance must be constructed and registered
separately by the Host at `open_host` time.

This separation is intentional — the registry is a static binding map consumed
by `HostToolingOptions`, while the adapter instance is a runtime object that
the Host constructs on demand via the binding's `adapter_key`. The
`from_workspace_root` factory exists for the Host to use when it encounters
`FINS_INGESTION_WAIT_ADAPTER_KEY`.

**Why not blocking:** Follows the existing Host wait-adapter architecture where
bindings and adapter instances are separately managed. The factory method is
tested indirectly via the `FinsIngestionWaitPollAdapter` constructor in the
poll adapter tests.

---

### F4 — `download_adapters` mapping uses `NormalizedTickerMarket` (Literal type) as key (correctness note)

**File:** `dayu/fins/ingestion_runtime.py:957`

```python
download_adapters: Mapping[tuple[str, NormalizedTickerMarket], FinsSourceDownloadAdapter]
```

`NormalizedTickerMarket` is `Literal["US", "HK", "CN"]`. In tests, the mapping
key `("fake", "US")` works because `"US"` is a valid literal value. At runtime,
`normalized.market` is the string literal `"US"` and matches the dict key. This
is correct because Python dict lookup by `Literal` string values works
transitively — the Literal type constrains the set of valid keys but the
runtime value is a plain `str`.

**Why not blocking:** The type is sound. The adapter selection at
`ingestion_runtime.py:1440` does `self.download_adapters.get((source, market))`
with `source: str` and `market: NormalizedTickerMarket` — both are `str` at
runtime so the lookup works.

---

## Layering verification

Checked and confirmed:

- **No reverse dependencies:** `dayu/fins/` does not import from
  `dayu.host`, `dayu.engine`, `dayu.service`, or `dayu.ui` (verified by
  `test_fins_import_boundaries_do_not_reverse_depend`).
  `dayu/fins/ingestion/wait_adapter.py` is granted a narrow exception to import
  from `dayu.host.api` and `dayu.host.wait_adapter` — this is by design as it
  is the Fins→Host adapter boundary, and is explicitly tested
  (`test_fins_import_boundaries_do_not_reverse_depend` in
  `test_fins_storage_provider.py` allows this specific file to import Host).

- **Engine/runtime do not import Fins:** Verified by
  `test_runtime_and_engine_do_not_import_fins`.

- **Fins storage protocol boundary:** All ingestion data access goes through
  `SourceDocumentRepositoryProtocol`, `DocumentBlobRepositoryProtocol`,
  `FilingMaintenanceRepositoryProtocol`, and
  `ProcessedDocumentRepositoryProtocol` — no direct filesystem access outside
  the job store.

- **Host/Engine public contract:** The wait adapter produces
  `ResolveWaitCompletedOutcome`, `ResolveWaitFailedOutcome`,
  `ResolveWaitCancelledOutcome`, and `ResolveWaitLostOutcome` — all from
  `dayu.host.api` public exports. No internal Host types leak into Fins.

---

## Cancellation / wait-resume governance

The cancellation flow is well-designed with explicit race windows covered:

1. **Queued → cancel → claim_running:** `claim_running_or_cancelled` checks
   `cancellation_requested` under lock before transitioning to RUNNING. Tested
   by `test_claim_running_preserves_cancel_between_read_and_running_write`.

2. **Running → cancel → save_succeeded:** `_run_download_job` and
   `_run_preprocess_job` re-read the job record before calling
   `save_succeeded_or_cancelled`, which atomically checks cancellation state
   under lock. Tested by
   `test_start_download_cancel_immediately_before_success_terminalization_writes_cancelled`.

3. **Already-terminal jobs:** `request_cancel`, `save_succeeded_or_cancelled`,
   and `claim_running_or_cancelled` all short-circuit for terminal-status
   records. Tested by
   `test_request_cancel_marks_active_job_and_keeps_terminal_job_terminal` and
   `test_runners_return_for_preterminalized_jobs_without_executing`.

4. **Preprocess per-document cancellation check:** `_execute_preprocess_request`
   polls `read_job` before each document. Download also polls before each
   document and each rejected artifact.

5. **Host abandon_wait → Fins cancel:** `FinsIngestionWaitPollAdapter.abandon_wait`
   calls `runtime.request_cancel(job_id)`. Idempotent for missing/corrupt
   evidence.

---

## Test coverage

| Test file | Tests | Focus |
|---|---|---|
| `tests/fins/test_fins_ingestion_runtime.py` | 27 | Job lifecycle, download/preprocess execution, cancellation races, job store atomicity, file lock cleanup |
| `tests/fins/test_fins_ingestion_tools.py` | 18 | Tool discovery, provider independence, tool outcome mapping, wait adapter registry, poll adapter state mapping, abandon semantics |
| `tests/fins/test_fins_storage_provider.py` | 11 | Storage read path, provider discovery, import boundaries, truncate specs |
| `tests/service/test_host_assembly.py` | 35 | Host assembly with Fins wait adapter registry, workspace root validation, duplicate binding detection |
| **Total** | **91** | All passing |

Coverage of key risk areas:
- Job state machine transitions: covered
- Cancellation race between queued→running: covered
- Cancellation race between running→success: covered
- Job store atomic write with tmp+fsync+replace: covered
- File lock cleanup on flock failure: covered
- Corrupt job evidence → WaitPollLost: covered
- Adapter abandon with missing/corrupt evidence: covered
- Tool argument error before job creation: covered
- Tool OSError/unexpected exception during start: covered
- Import boundary enforcement: covered

---

## Validation performed

| Check | Result |
|---|---|
| `pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_storage_provider.py tests/service/test_host_assembly.py -v` | 91 passed, 0 failed |
| `pyright` on all new/modified production modules | 0 errors, 0 warnings |
| `git diff --check` | clean |
| Manual diff review of all production code paths | No correctness issues found |
| Import boundary verification (`test_fins_import_boundaries_do_not_reverse_depend`, `test_runtime_and_engine_do_not_import_fins`) | Passing |

---

## Follow-up items (not blocking)

These are recorded in the control doc as post-merge WUs and are correctly
scoped out of this PR:

1. **Fins filelock convergence** — `FsFinsIngestionJobStore` uses `fcntl.flock`
   (POSIX-only). Future work may converge this with the Host's SQLite-based
   locking or add a Windows-compatible fallback.

2. **Migrated tool cancellation response** — Current read tools use the legacy
   adapter path. Future work may align their cancellation semantics with the
   new ingestion job model.

3. **OLD CN/SEC download/upload migration** — Existing download/upload paths
   (if any) should be migrated to use the new `FinsSourceDownloadAdapter`
   protocol.

---

## Control doc consistency

The control doc at `docs/host/issues-implementation-control.md` correctly
reflects:
- Active WU: WU-TOOLS-01-F01
- Gate: ready-to-open-draft-PR → advancing to PR review
- Follow-up WUs recorded for filelock convergence, tool cancellation, and
  OLD download/upload migration
- Residual risk WU-TOOLS-01-S4-R1 marked as resolved (transferred to
  WU-TOOLS-01-F01)

No inconsistencies found between the control doc and the PR contents.
