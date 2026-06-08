# WU-TOOLS-01-F01 PR Review — MiMo

**PR**: noho/dayu-agent-r#126
**Branch**: host-wu-tools-01-f01 → main
**Review date**: 2026-06-08
**Reviewer**: AgentMiMo
**Scope**: Full PR diff (115 files, ~16k additions, ~900 deletions)

---

## Verdict: pass-with-findings

PR is structurally sound, correctly implements the shared Fins ingestion runtime foundation, and passes all focused tests + pyright. Findings are minor and non-blocking.

---

## Findings

### F1. `FinsIngestionRuntime` dataclass exposes `_start_lock` in generated `__init__` / `__eq__`

**Severity**: low
**File**: `dayu/fins/ingestion_runtime.py:947-958`

`@dataclass` without `eq=False` generates `__eq__` comparing all fields including `_start_lock: Lock`. `Lock.__eq__` is identity-based, so two different runtime instances are never equal (correct behavior), but the generated `__repr__` also dumps the lock object (unhelpful noise). More importantly, `_start_lock` is a valid keyword argument of the generated `__init__`, so callers can bypass `create()` and inject arbitrary locks.

**Why it matters**: Minor API hygiene; no current caller exploits this path, but the dataclass contract is wider than intended.

**Suggestion**: Use `@dataclass(eq=False, repr=False)` or move `_start_lock` to `__post_init__` with `field(init=False, repr=False)`.

---

### F2. `FinsIngestionThreadExecutor` daemon threads have no completion tracking

**Severity**: low
**File**: `dayu/fins/ingestion_runtime.py:623-646`

`FinsIngestionThreadExecutor.submit` starts daemon threads but provides no mechanism to join or await completion. If the host process exits while jobs are running, those jobs remain in QUEUED/RUNNING state in the job store. The wait adapter will poll them as "not ready" indefinitely until the host restarts and the poller detects the stale state.

**Why it matters**: S1 scope explicitly accepts this (no real network I/O yet), but it's a known gap for production readiness.

**Suggestion**: Follow-up WU should add a `shutdown(wait=True)` method or track active threads for graceful drain.

---

### F3. `_save_cancelled` uses `save_job` not `save_succeeded_or_cancelled`

**Severity**: low
**File**: `dayu/fins/ingestion_runtime.py:1813-1835`

`_save_cancelled` writes via `save_job` which unconditionally overwrites the record. If a race condition puts the job in a terminal state between the caller's read and this write, the terminal state would be overwritten. In practice this cannot happen because each job has exactly one background thread, and `_save_cancelled` is only called after verifying non-terminal state. But the asymmetry with `_save_succeeded` (which uses `save_succeeded_or_cancelled`) is a code-readability concern.

**Why it matters**: Correctness is fine due to single-thread-per-job invariant; this is a maintainability observation.

---

### F4. `download_provider` and `preprocess_provider` each create a new `DefaultFinsRuntime` per discovery call

**Severity**: low
**File**: `dayu/fins/tools/download_provider.py:36-37`, `dayu/fins/tools/preprocess_provider.py:36-37`

Each provider's `discover_tools` calls `DefaultFinsRuntime.create(workspace_root=...)` which builds all FS repositories fresh. When both providers are enabled in the same assembly, the `host_assembly.py` code correctly detects both via provider config scanning and builds a single wait adapter registry, but the providers themselves each independently instantiate the runtime. This means two `FinsIngestionRuntime` instances exist during discovery (one per provider), each with its own `Lock`.

**Why it matters**: Not a correctness issue because discovery is a one-shot operation and the runtime instances are discarded after tool definitions are built. The actual runtime used at execution time is assembled by `host_assembly.py`. But it's a minor inefficiency.

---

### F5. `_timestamp_or_now` silently swallows parse errors

**Severity**: low
**File**: `dayu/fins/ingestion/wait_adapter.py:338-352`

When a Fins job record has a corrupted timestamp string, `_timestamp_or_now` falls back to `datetime.now(timezone.utc)` without logging. This means the `ToolResultMeta.started_at` / `finished_at` shown to the model could be misleading (current time instead of actual job time).

**Why it matters**: Very unlikely in practice (timestamps are written by `_utc_now` which is deterministic), but silent fallback makes debugging harder if corruption does occur.

---

## Deferred Follow-Up (FileLock)

### D1. Fins private `_StoreFileLock` should converge to `dayu.runtime.filelock`

**Owner/destination**: WU-TOOLS-01-F01-01
**File**: `dayu/fins/ingestion_runtime.py:1945-2013`

`_StoreFileLock` is a private platform-specific (Unix `fcntl.flock`) file lock. Controller direction is to defer this to WU-TOOLS-01-F01-01 which will replace it with `dayu.runtime.filelock`. No blocking action required for this PR.

---

## Accepted Risk

### A1. `fcntl.flock` is Unix-only

`_StoreFileLock` uses `fcntl.flock` which is not available on Windows. The project targets Unix environments (macOS/Linux), so this is accepted.

### A2. No real download adapters in S1

The `download_adapters` mapping defaults to empty `{}`. Without real adapters, all download attempts fail with "不支持的下载来源". This is by design for S1 scope — the follow-up WU for OLD CN/SEC download migration will add real adapters.

### A3. `purge_session` added to Host Protocol

`dayu/host/api.py` adds a `purge_session` method to the `Host` protocol. This is orthogonal to the ingestion runtime work but appears to be a concurrent change included in this branch. No correctness concern.

---

## Validation Performed

| Check | Result |
|-------|--------|
| `pytest tests/fins/test_fins_ingestion_runtime.py` | 27 passed |
| `pytest tests/fins/test_fins_ingestion_tools.py` | 18 passed |
| `pytest tests/service/test_host_assembly.py` | 35 passed |
| `pytest tests/host/ tests/engine/ tests/runtime/ tests/tools/` (all affected) | 116 passed |
| `pyright` on changed production files | 0 errors, 0 warnings |
| `git diff --check` | clean |

**Not run**: Full test suite (out of scope for PR review, but focused tests cover all changed modules).

---

## Summary

The PR correctly implements:
1. **Shared Fins ingestion runtime** (`ingestion_runtime.py`, 2700 lines): typed request/result models, durable job record store with atomic file operations, cooperative cancellation, download + preprocess pipelines.
2. **Host wait adapter** (`wait_adapter.py`): maps Fins job states to Host poll results, supports `abandon_wait` → cooperative cancel.
3. **Awaiting tool providers** (`download_provider.py`, `preprocess_provider.py`): independent ToolsDiscovery providers returning `ToolAwaitingOutcome`.
4. **Service assembly integration** (`host_assembly.py`): auto-detects Fins awaiting providers, builds unified wait adapter registry.
5. **Tool discovery config split** (`tool_discovery.json`): single `financial-tools` → three independent providers.

Code quality is high: comprehensive Chinese docstrings, strict input validation, bounded summaries, and well-structured test coverage including race condition simulation and corrupt evidence handling.
