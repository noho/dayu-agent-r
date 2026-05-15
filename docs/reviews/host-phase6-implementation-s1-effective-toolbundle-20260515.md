# Host Phase 6 P6-S1 Implementation Artifact

- gate: Phase 6 implementation
- slice: P6-S1 - Effective ToolBundle And RunInputBuilder Wiring
- approved plan: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`
- design source: `docs/host/design.md`
- control doc: `docs/host/implementation-control.md`
- branch: `feat/host-phase-6-toolruntime`
- accepted plan commits: `04517f5` / `a5863ce`
- status: completed

## Allowed Files

Production:

- `dayu/host/tool_runtime.py`
- `dayu/host/tooling.py`
- `dayu/host/run_input.py`
- `dayu/host/command.py`
- `dayu/host/api.py`
- `dayu/host/__init__.py`

Tests:

- `tests/host/test_toolruntime_effective_bundle.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_tooling_options.py`
- `tests/host/test_package_exports.py`

Artifact:

- `docs/reviews/host-phase6-implementation-s1-effective-toolbundle-20260515.md`

## Changed Files

- `dayu/host/tool_runtime.py`
- `dayu/host/run_input.py`
- `dayu/host/README.md`
- `tests/host/test_toolruntime_effective_bundle.py`
- `tests/host/test_run_input_builder.py`
- `docs/reviews/host-phase6-implementation-s1-effective-toolbundle-20260515.md`

## Implemented Plan Items

- Added Host-local ToolRuntime typed ports and runtime objects:
  `EffectiveToolBundle`, `EffectiveToolBundleBuilder`, `ToolRuntimeHandle`,
  `ToolRuntimeFactory`, `ToolRuntimeBuildRequest`, policy / truncation /
  duplicate / accept / diagnostic port shapes.
- Implemented reserved framework tool name validation in
  `EffectiveToolBundleBuilder`; business `fetch_more` remains rejected.
- Implemented deterministic diagnostic digest derivation for business bundle
  and effective schema projection.
- Implemented effective schema projection from the same effective bundle that
  retains callable bindings in `definitions_by_name`.
- Added optional framework injection hook. Disabled framework tools do not
  inject `fetch_more`. P6-S1 does not implement a real `fetch_more` callable.
- Added explicit `ToolExecutionMode` with `TOOL_ENABLED`,
  `NO_TOOL_REPLAY`, and `NO_TOOL_DISABLED`.
- Split `PolicySnapshot.__post_init__` from no-tool enforcement:
  `allow_tool_calls=True` can construct, while RunInputBuilder validates it
  only in `TOOL_ENABLED` mode.
- Split RunInputBuilder validation by mode:
  no-tool / replay require disabled tools, empty schemas, no handle, and
  `allow_tool_calls=False`; tool-enabled requires enabled tools,
  `allow_tool_calls=True`, and schema / executor from the same
  `ToolRuntimeHandle`.
- Added ToolRuntime handle-backed schema and executor providers.
- Updated default scene parameter rendering so `TOOL_ENABLED` does not emit
  `tools=disabled`; replay / no-tool still emit `tools=disabled`.
- Kept no-tool / replay returning empty schemas and `NoToolExecutor`.
- Used an explicit `ToolRuntimeUnsupportedExecutor` stub for P6-S1; it does
  not execute business callables.

## Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_effective_bundle.py tests/host/test_run_input_builder.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q
```

Result:

```text
29 passed in 0.22s
```

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

```bash
git diff --check
```

Result: passed with no output.

## Docs Decision

`dayu/host/README.md` was updated because the Host developer manual previously
described ToolRuntime as entirely unimplemented. P6-S1 now implements the
ToolRuntime typed boundary, `EffectiveToolBundle`, `ToolRuntimeHandle`, and
tool-enabled RunInputBuilder validation. The README now states the current
implemented boundary and keeps real execution, accept barrier, truncation,
`fetch_more`, duplicate governance, policy resolution, and durable cursor /
snapshot work explicitly out of scope.

## Explicit Non-Changes

Confirmed no change was introduced to:

- wait record / `WAITING` / `resolve_wait`
- durable cursor descriptor
- Remote wire protocol
- business tool scanning
- `dayu.fins` imports
- Engine contracts or Engine governance
- durable EventLog accept path
- fetch_more callable implementation
- duplicate governance beyond typed P6-S1 stubs

## Residual Risks

- Deferred capability: `ToolRuntimeUnsupportedExecutor` intentionally does not
  call business tools, apply accept barrier, truncate results, or enforce
  duplicate governance. These are owned by later Phase 6 slices.
- Integration risk: Host dispatch still constructs the existing no-tool builder
  path. Tool-enabled dispatch construction is available through
  `create_tool_enabled_run_input_builder`, but full dispatch policy selection
  is deferred until the ToolRuntime execution path is connected.
- Docs risk: README now reflects the S1 ToolRuntime boundary; later slices must
  update it again when real execution, accept barrier, truncation, or
  `fetch_more` becomes connected behavior.

## Completion Signal

RunInputBuilder can now produce a tool-enabled request whose schemas and
executor originate from one `ToolRuntimeHandle`, while no-tool / replay remains
no-tool with empty schemas, `NoToolExecutor`, and `allow_tool_calls=False`.
