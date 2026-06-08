# WU-TOOLS-01-F01 Slice S6 Code Review Controller Adjudication

## Gate Metadata

- Work unit: `WU-TOOLS-01-F01`
- Slice: S6, config, docs and regression closeout
- Gate: code review adjudication
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s6-implementation-codex.md`
  - `docs/reviews/wu-tools-01-f01-s6-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s6-code-review-ds.md`

## Verdict

fix-required

Both reviewers validated that S6 closes the functional config/docs/test target shape: default config now has disabled read/download/preprocess provider entries, workspace overlay tests no longer depend on `include_ingestion_tools`, README sync is scoped, and the full requested validation passed.

However, both reviewers found that the read provider still reports the old mixed provider id. Controller also verified the read provider source id is still the old package-level source id. Because S6 is specifically closing the old mixed provider shape, this naming residue should be fixed before accepting the slice.

## Accepted Findings

| ID | Source | Severity | Controller decision |
|---|---|---|---|
| F01-S6-001 | MiMo F1 / DS F2 / Controller verification | medium | Accept. Change read provider output identity from old mixed names to the split read provider identity: `_PROVIDER_ID = "financial-read-tools"` and `_SOURCE_ID = "dayu.fins.tools.provider"`. Update tests and docs/artifacts as needed so provider report, spec id and source refs all align with the S6 target shape. This is a narrow production change needed to remove the old mixed provider identity; it does not change Host/Engine contracts. |
| F01-S6-002 | MiMo F2 | low | Accept. Make the Fins import boundary exception for `dayu/fins/ingestion/wait_adapter.py` robust against path representation differences. Keep the exception limited to that exact file and do not broaden the allowlist. |

## Rejected Or Deferred Findings

| Source | Controller decision |
|---|---|
| Real SEC/CN/HK network adapters, upload provider, CI/smoke and future CLI wrappers | Deferred to existing later owners. These are outside S6 and do not block closing `WU-TOOLS-01-S4-R1`. |

## WU-TOOLS-01-S4-R1 Closure Decision

Tentatively approve closure after F01-S6-001 and F01-S6-002 are fixed and re-reviewed. The residual asked for shared Fins ingestion service/runtime plus separate download/preprocess awaiting adapters. S1-S5 implemented the runtime, pipelines, providers and wait adapter wiring; S6 closes config/docs/test target shape. The only current blocker is the old read provider identity residue.

## Required Fix Validation

- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`
