# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S2 Controller Validation

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-A / S2`
- Gate: controller validation after implementation
- Time: `2026-07-12T15:26:04+0800`
- Branch: `phaseflow/host-issues-control`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s2-implementation-codex.md`

## Validation Result

Controller validation passes. S2 is ready for code review.

## Commands

- Focused S2 pytest:
  - `source .venv/bin/activate && pytest tests/host/test_public_host_admin.py tests/host/test_durable_actor.py tests/host/test_open_host_runtime.py tests/host/test_public_open_host_options.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_submit_followup_public_contract.py tests/host/test_command_handle.py tests/host/test_dispatch_scheduler.py tests/host/test_active_cancel_dispatch.py tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py tests/host/test_purge_session.py tests/host/test_storage_usage_report.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/service/test_host_admin.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/cli/test_session_command.py -q`
  - Result: `417 passed, 3 warnings in 10.62s`
  - Warnings: third-party `edgar` deprecation warnings, unrelated to S2.
- Pyright:
  - `source .venv/bin/activate && python -m pyright dayu/host/ dayu/service/ dayu/cli/commands/session.py tests/host/ tests/service/ tests/cli/test_session_command.py`
  - Result: `0 errors, 0 warnings, 0 informations`
- Whitespace:
  - `git diff --check`
  - Result: pass.

## Source Scans

- `rg -n 'open_host_admin|open_host\(' dayu/cli/commands/session.py`
  - Result: list/purge and resume selector paths use `open_host_admin`; prompt/interactive execution paths still use `open_host`.
- `rg -n 'asyncio\.to_thread\([^)]*(ensure_session|submit_followup|get_run|list_sessions|purge_session)|self\._command_handle' dayu/host/open_host.py`
  - Result: no public-handle direct sync command transport for `ensure_session`, `submit_followup`, `get_run`, `list_sessions`, or `purge_session`.
  - Remaining `_command_handle` matches are wait-poller thread-private resolver/closer paths; they do not carry the public actor connection.
- `rg -n 'ThreadPoolExecutor|max_workers=1|Callable\[\[HostCommandHandle\], T\]|call_soon_threadsafe|Future\[' dayu/host/_durable_actor.py dayu/host/open_host.py`
  - Result: durable actor single-worker executor, typed command callable, typed futures, and opener-loop bridge are present.

## Controller Scope Extension

Controller allowed a narrow S2 test-scope extension for `tests/host/test_public_lifecycle_smoke.py` after AgentCodex found the required pyright command scanned the file and exposed a stale execution `Host.purge_session()` assertion. The accepted fix only removes that obsolete execution-admin closed-handle assertion and its dedicated helper/import. It does not restore admin capability to execution `Host` and does not change the lifecycle smoke behavior otherwise.

## Residual Risk

- S3-S5 health, recovery batching, active-cancel watchdog event, cancel classification, and deferred cancel state work remain out of S2 scope and are owned by later approved slices.
- No unclassified S2 residual risk found by controller validation.
