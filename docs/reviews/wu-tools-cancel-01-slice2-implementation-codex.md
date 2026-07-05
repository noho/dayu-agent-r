# WU-TOOLS-CANCEL-01 Slice S2 implementation report

## 1. Artifact

- Artifact path: `docs/reviews/wu-tools-cancel-01-slice2-implementation-codex.md`
- Gate: implementation
- Slice: `WU-TOOLS-CANCEL-01-S2 production tools interrupt adapters`

## 2. Per-tool-family migration assessment

| Tool family / path | Direct evidence | Chosen classification | Result |
|---|---|---|---|
| Doc tools | `dayu/tools/doc_tools.py` still owns five async tool callables whose synchronous business boundary is a closure passed to `asyncio.to_thread(...)`. S1 process/thread capsule capability exists only as `dayu.host.tool_runtime` internal factory injection; `ToolDefinition` has no typed execution capability field. Importing Host capsule from Doc tools would violate `UI -> Service -> Host -> Engine` layering, while Host-side tool-name branching would be a magic tool-name branch. | design-stop for production-grade non-cooperative cancel | Not migrated in this slice. Requires a typed tool execution capability declaration outside `dayu.contracts`, or a design/contract update if the declaration must live in shared tool contracts. Do not claim Doc production blocking cancel is closed. |
| Fins read tools | `dayu/fins/tools/fins_tools.py` still wraps `FinsReadRuntime` calls in a closure passed to `asyncio.to_thread(...)`. The runtime correctly accesses financial documents through `dayu.fins.storage`, but current tool declarations do not carry a process-backed execution mode or a serializable workspace-root execution descriptor. Capturing `FinsReadRuntime` into a child process is not a reliable process-backed boundary. | design-stop for production-grade non-cooperative cancel | Not migrated in this slice. Any future process-backed migration must pass only a workspace locator and typed request, then rebuild `DefaultFinsRuntime` inside the child process without bypassing `dayu.fins.storage`. |
| Web sync HTTP / search / fetch | `dayu/tools/web/web_tools.py` used `asyncio.to_thread(...)` for search/fetch and passed `timeout_budget=None` into business logic, while `web_http_session.py` already has deadline-aware timeout helpers. | partial migration: deadline bounded; blocking interrupt still design-stop | Changed search/fetch to pass `context.timeout_seconds` into HTTP timeout budgeting. The remaining synchronous `requests` path still depends on `asyncio.to_thread(...)`, so it is not production-grade non-cooperative interrupt until a typed process-backed or abort-capable adapter declaration exists. |
| Async HTTP / httpx | SEC downloader uses `httpx.AsyncClient`, but this S2 handoff allowed only narrowly required Fins helper modules that currently own blocking provider calls. No current touched production tool path routed through async HTTP in the selected files. | not touched | No code change. Cleanup verification remains a future slice/design item if async HTTP paths become part of this production tool boundary. |
| Playwright | `dayu/tools/web/web_playwright_backend.py` already runs picklable workers in a `multiprocessing` child and terminates/kills on cancel or timeout. It previously fell back to same-process execution when the worker was not picklable. | process-backed with fail-closed fallback | Changed unpicklable Playwright worker fallback to fail closed with `reason="playwright_worker_not_picklable"` instead of running same-process blocking work. |

## 3. What changed

- `dayu/tools/web/web_tools.py`
  - `search_web` and `fetch_web_page` now pass `BatchToolExecutionContext.timeout_seconds` as `timeout_budget` into synchronous business logic.
  - Updated internal docstrings so the budget is described as an active HTTP request constraint, not the old `None` behavior.
- `dayu/tools/web/web_playwright_backend.py`
  - Removed same-process fallback for unpicklable Playwright workers.
  - Unpicklable worker now fails closed with an unprocessable Playwright result.
- `tests/tools/web/test_web_tools_provider.py`
  - Added coverage that search/fetch pass the tool timeout budget to business logic.
  - Added coverage that unpicklable Playwright worker does not execute in the parent process.

## 4. Direct evidence used

- S1 internal capsule exists in `dayu/host/tool_runtime.py`, including `ToolExecutionMode.ASYNC_DIRECT`, `THREAD_BACKED`, and `PROCESS_BACKED`, but production dispatch builds `ToolRuntimeBuildRequest(...)` without a production capability-aware factory in `dayu/host/dispatch.py`.
- Shared `ToolDefinition` / `BatchToolExecutionContext` in `dayu.contracts` does not expose typed tool execution capability.
- `dayu/tools/doc_tools.py` and `dayu/fins/tools/fins_tools.py` still use tool-local closures around synchronous business calls, which cannot be safely classified as process-backed via current production declarations.
- `dayu/fins/tools/read_runtime.py` and `dayu/fins/service_runtime.py` show Fins read access goes through `dayu.fins.storage`; any process-backed Fins migration must preserve that by rebuilding `DefaultFinsRuntime` in the child.
- `dayu/tools/web/web_http_session.py` already has `_resolve_timeout_budget(...)`; the missing piece was caller propagation from `web_tools.py`.
- `dayu/tools/web/web_playwright_backend.py` already had process terminate/kill for picklable workers, and the unsafe path was the unpicklable same-process fallback.

## 5. Validation run

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py -q` -> passed, `34 passed`.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q` -> passed, `56 passed`, with existing edgar deprecation warnings.
- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q` -> passed, `23 passed`.
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q` -> passed, `42 passed`.
- `source .venv/bin/activate && pyright` -> passed, `0 errors`.
- `git diff --check` -> passed.

## 6. README decision

- Modified `tests/`, so I read `tests/README.md`.
- No README update needed: the change adds focused assertions to an existing test file and does not introduce a new test layer, command, or testing entrypoint.

## 7. Open questions / residual risks

- Stop condition is active for Doc, Fins read, and Web synchronous blocking production paths: current S1 process-backed capability is not selectable from production tool declarations without either a new typed provider/tool declaration path or a `dayu.contracts` contract change.
- Per handoff instruction, if `dayu.contracts` shared declaration becomes necessary, this slice must return to design/contract update instead of editing contracts.
- The web HTTP budget propagation and Playwright fail-closed change reduce risk but do not close issue #87 for all production blocking tool/provider paths.
