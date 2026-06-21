# WU-TOOLS-01-F01-02-R1 Slice 3 Code Review Fix Artifact

## Scope

- Fix gate: Slice 3 code-review fix.
- Input artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-implementation-codex.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-ds.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-controller-adjudication.md`
- Modified files in this fix:
  - `dayu/service/host_assembly.py`
  - `tests/service/test_host_assembly.py`
  - `dayu/fins/ingestion/wait_adapter.py`
- Not modified by this fix:
  - plan / control docs.
  - README files.

## Motivation Judgment

The accepted findings are maintainability and guardrail issues, not production correctness blockers. The root evidence is direct: the activation registry path discarded a constructed wait adapter registry, the disabled provider callable was skipped before invocation by runtime discovery, the two Fins registry builders duplicated the same provider filtering and workspace collection, and the local Service assembly contract allowed callers to omit a runtime that is required whenever Fins awaiting tools are present.

The requested path is appropriately narrow. A broader lifecycle platform, generic builder, durable job ledger, or public API expansion would be over-design for these findings and was not introduced.

## Fixes

### S3-CR-F01

Removed the discarded `build_fins_wait_adapter_registry(...)` call from `_fins_wait_activation_registry_from_provider_configs(...)`.

Equivalent direct validation is preserved by:

- reusing the same provider config collection helper for enabled Fins awaiting tool names and single workspace root;
- keeping workspace root validation through `_fins_workspace_root_from_provider_config(...)` and `_single_fins_workspace_root(...)`;
- adding direct duplicate tool-name validation before constructing the activation registry.

Activation registry behavior is unchanged: it still registers one `FinsIngestionWaitActivationAdapter` under `FINS_INGESTION_WAIT_ADAPTER_KEY` using the shared runtime.

### S3-CR-F02

Changed `_DisabledProviderCallable.__call__` into an explicit unreachable fail-fast sentinel.

It now raises `RuntimeError` if invoked, instead of constructing a `ToolsDiscoveryProviderOutput` that normal discovery never consumes. Disabled provider reporting and ordinary discovery behavior are unchanged because `ToolsDiscovery.discover_from_bindings(...)` still skips disabled specs before invoking provider callables.

### S3-CR-F03

Added `_FinsAwaitingRegistryInputs` and `_fins_awaiting_registry_inputs_from_provider_configs(...)` as a small private helper.

The helper centralizes only the Slice 3 duplicated logic:

- enabled provider filtering;
- Fins awaiting tool recognition;
- available ToolBundle name filtering;
- workspace root collection and single-root validation.

Both the wait adapter registry path and activation registry path now consume this helper. No broad platform abstraction was added.

### S3-CR-F04

Tightened `_tooling_options_from_discovery(...)` by removing the default value from `fins_awaiting_runtime`.

Callers must now explicitly pass either the shared Fins awaiting runtime or `None`. No-Fins-awaiting behavior is unchanged: explicit `None` still yields no wait adapter registry and no activation registry when no Fins awaiting tool is available.

Focused tests were updated to pass `fins_awaiting_runtime=None` in no-Fins or filtered-out Fins cases.

### S3-CR-F05

Added a concise guardrail in `build_fins_wait_activation_registry(...)` documenting that production Service assembly must make the awaiting tool callable, poll adapter, and activation adapter share the same `FinsIngestionRuntime` instance.

Also kept a local Service assembly comment at the production activation adapter construction point. No lifecycle platform or broad builder API was introduced.

## Validation

- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py -q`
  - Result: `52 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `159 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

The warnings are existing third-party `edgar` deprecation warnings observed in the same focused suites.

## README / Docs Decision

- `dayu/fins/README.md`: checked because this fix touched `dayu/fins/ingestion/wait_adapter.py`. No update needed; the existing README already documents Fins awaiting providers, observation handles, Service assembly shared runtime behavior, and wait adapter integration. The code docstring guardrail does not change a recorded fact.
- `tests/README.md`: checked because focused tests were adjusted. No update needed; test layering, commands, and responsibilities did not change.
- Root `README.md`: no update needed; no user-visible install, CLI / Web / WeChat entry, command argument, output channel, log location, workspace file location, final-user workflow, or troubleshooting behavior changed.
- `dayu/README.md`: no update needed; no layer boundary or assembly relationship changed.
- Plan / control docs: intentionally not modified.

## Residual Risk

- Full open-host dispatch worker activation path remains outside this fix; the existing focused Service test verifies Service discovery, `HostToolingOptions`, shared runtime identity, and activation adapter behavior.
- Production poller scheduling, backoff, fencing, retry, and external provider physical cancel / revoke remain outside this fix and were not expanded here.
- The standalone activation registry builder still constructs its own runtime; it is now explicitly documented as unsuitable for production Service assembly unless the caller guarantees runtime consistency.
