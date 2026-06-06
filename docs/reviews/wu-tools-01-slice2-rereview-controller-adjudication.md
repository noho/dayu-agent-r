# WU-TOOLS-01 Slice S2 Re-Review Controller Adjudication

Gate: re-review  
Work unit: WU-TOOLS-01  
Slice: S2 Tool Adapter And Typed Provider Config  
Controller: phaseflow  
Date: 2026-06-05  
Decision: accepted slice commit

## Inputs

- Implementation artifact: `docs/reviews/wu-tools-01-slice2-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-tools-01-slice2-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-slice2-code-review-ds.md`
- Code review controller adjudication: `docs/reviews/wu-tools-01-slice2-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-tools-01-slice2-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-01-slice2-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-slice2-rereview-ds.md`

## Decision

WU-TOOLS-01 Slice S2 is accepted for local slice commit.

Both re-review agents returned `pass`.

Accepted findings fixed:

- Batch `fetch_more` handling now fails fast in `adapt_collected_tools(...)`, matching `adapt_collected_tool(...)`.
- `SERIAL_PER_PROVIDER` shared-lock behavior and generic exception projection now have direct tests.
- OLD success envelope detection now requires both `ok is True` and a present `value` key, so plain business dicts with an `ok` field are preserved.
- Incomplete `ToolPathValidationPolicy.file_path_params` coverage now fails closed before invoking migrated callables.

## Accepted Scope

S2 establishes the narrow legacy declaration adapter and provider config pass-through:

- Adds `dayu.tools._legacy_adapter`.
- Adds adapter tests under `tests/tools/`.
- Passes provider `config` from config loader through service assembly into `ToolsDiscoveryProviderSpec`.
- Adds disabled Doc / Fins / Web provider config examples without implementing providers.
- Updates `dayu/README.md`, `dayu/config/README.md`, and `tests/README.md` for current package/config/test-layer facts.

S2 does not migrate Doc/Fins/Web business tools, OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, OLD truncate / fetch-more projection, Host runtime behavior, ToolRuntime public contract, or Engine public contract.

## Validation

Controller and reviewers verified:

```bash
source .venv/bin/activate && pytest tests/tools/test_legacy_tool_adapter.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py
```

Result: 93 passed.

```bash
source .venv/bin/activate && pyright
```

Result: 0 errors, 0 warnings, 0 informations.

```bash
git diff --check
```

Result: clean.

## Residual Risks

Existing WU-TOOLS-01 residuals remain tracked:

- Provider-specific typed config parsing remains S3/S4/S5 owner.
- Provider-specific Doc path whitelist behavior remains S3 owner.
- Concrete migrated truncating tools remain S3/S4/S5 owner.
- Combined ToolRuntime accept path remains S6 owner.

No unowned blocking finding remains for S2 acceptance.

## Next Gate

Create accepted Slice S2 local commit, record the commit hash in the control doc, then proceed to WU-TOOLS-01 Slice S3 implementation.
