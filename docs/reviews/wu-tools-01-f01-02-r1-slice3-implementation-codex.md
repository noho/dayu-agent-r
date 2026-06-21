# WU-TOOLS-01-F01-02-R1 Slice 3 Implementation Artifact

## Scope

Slice: Service wiring, docs, and final focused validation.

Implementation judgment: Slice 3 motivation is valid. The remaining production risk was not just a missing option field; Fins awaiting tool callables and accepted-wait activation must observe the same process-local ingestion runtime, otherwise the activation adapter cannot see the prepared observation registered by the tool callable.

## Changed Files

- `dayu/host/tooling.py`
  - Extended `HostToolingOptions` with `wait_activation_registry`.
- `dayu/host/dispatch.py`
  - Passed `tooling_options.wait_activation_registry` into `ToolRuntimeBuildRequest`.
- `dayu/service/host_assembly.py`
  - Added Service-side shared Fins awaiting runtime assembly for enabled Fins awaiting provider configs.
  - Fins awaiting provider discovery now emits the same tool definitions as the provider modules, but binds download / preprocess / upload awaiting tools to one shared `FinsIngestionRuntime` for the single absolute workspace root.
  - Built `WaitActivationRegistry` from the same enabled Fins awaiting provider configs and same workspace root, using the same runtime observed by the awaiting tool callables.
  - Disabled providers remain non-imported during discovery.
- `tests/service/test_host_assembly.py`
  - Added focused production-like wiring coverage for Service discovery -> `HostToolingOptions` -> accepted activation path.
  - Verified the Fins awaiting callable and activation adapter share the same runtime, and activation moves a prepared observation out of `PENDING`.
- `docs/host/design.md`
  - Documented ToolRuntime internal activation after accepted awaiting ack and Engine non-ownership.
- `dayu/host/README.md`
  - Documented current Host ToolRuntime activation boundary.
- `dayu/fins/README.md`
  - Documented current Fins awaiting prepare / activation behavior and shared Service assembly runtime requirement.

## Validation

- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py -q`
  - Result: `52 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: `159 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

Warnings were existing third-party `edgar` deprecation warnings from test imports.

## README / Docs Decision

- `docs/host/design.md`: updated. Host design now records the accepted-wait activation hook and Engine non-ownership.
- `dayu/host/README.md`: updated under its Agent update constraints because `dayu.host` ToolRuntime construction-time behavior changed.
- `dayu/fins/README.md`: updated under its Agent update constraints because current Fins awaiting behavior is prepare-then-activate.
- `tests/README.md`: intentionally not updated. The test organization, test running model, and maintenance rules did not change; only a focused Service assembly test was added.
- Root `README.md`: intentionally not updated. No user-visible install, CLI/Web/WeChat workflow, command argument, output channel, log location, workspace file location, or troubleshooting behavior changed.
- `dayu/README.md`: intentionally not updated. No UI / Service / Host / Engine boundary change beyond the existing Host-owned awaiting governance was introduced.

## Contract / Schema Confirmation

- No Engine public awaiting model change.
- No `ToolAwaitingOutcome` shape change.
- No LLM-facing tool schema, prompt, memory projection text, evidence material format, or tool description change.
- No durable prepared status, lifecycle supervisor, public await contract, callback endpoint, production poller loop, or external physical cancel / revoke implementation added.
- No control doc modification.

## Residual Risks

- Production poller scheduling, backoff, fencing and retry remain outside this slice. Owner: GitHub Issue #90.
- External provider physical cancel / revoke / abandon remains outside this slice. Owner: GitHub Issue #92.
- Callback endpoint / auth / replay remains outside this slice. Owner: GitHub Issue #89.
- Process-local Fins observation registry still does not survive Host process loss as a durable external job ledger. Owner: #90 / #92 as applicable.
- Future non-Fins providers that need accepted-wait activation must provide their own adapter keyed by an existing `WaitAdapterKey`; this slice deliberately does not create a cross-provider lifecycle platform.
