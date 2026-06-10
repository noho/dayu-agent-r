# WU-TOOLS-01-F03 Final Closeout

## Status

- Work unit: `WU-TOOLS-01-F03 Web CI smoke generation`
- Final gate: draft-PR-pass / final closeout
- Draft PR: `https://github.com/noho/dayu-agent-r/pull/134`
- Date: 2026-06-10
- Branch: `wu-tools-01-f03-web-ci-smoke`
- Final accepted commit: `3c70949d Align tool discovery defaults and effective specs`
- GitHub checks: no checks reported on the branch

## Completed Scope

WU-TOOLS-01-F03 is complete for its defined scope:

- generated direct `utils/smoke_web_ci.py` smoke coverage for local HTML, local PDF Docling conversion, browser fallback, local Web config assembly, external URL diagnostic-only cases, and `auto` / `tavily` / `serper` / `duckduckgo` search provider diagnostic cases;
- added Web smoke UI summary lines and default debug logging aligned with Dayu logging and observability conventions;
- migrated Web tool config defaults into `dayu/config/tool_discovery.json` and proved the effective config reaches `search_web` / `fetch_web_page`;
- aligned default Tools Discovery provider `enabled=true` semantics with scene manifest and Host per-run tool selection boundaries;
- split effective provider config assembly from discovery: callers run `assemble_effective_tool_provider_configs(...)`, and `discover_service_tools(...)` only consumes effective provider configs;
- ensured upload empty allowlist returns an empty tool set and does not bind `start_fins_upload` wait adapter.

## Validation

Final validation:

- `pytest tests/runtime/test_config_loader.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py tests/tools/web/test_web_tools_provider.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`
  - Result: `212 passed, 3 warnings`
- `pyright dayu tests utils`
  - Result: `0 errors, 0 warnings, 0 informations`
- `python utils/smoke_web_ci.py`
  - Result: `passed`, `local_cases=4`, `external_cases=2`, `search_cases=4`, `diagnostic_only=6`
  - Output: `workspace/output/web_smoke/web-smoke-20260610T085513Z`
- `git diff --check`
  - Result: passed
- `gh pr checks 134`
  - Result: no checks reported on the branch

The final pytest run emitted background Fins ingestion logging errors after test completion, but the pytest process exited 0 with all selected tests passed. This is not treated as a WU-TOOLS-01-F03 functional failure.

## Review And Reconciliation

- R3 code review / fix / re-review passed.
- R3 effective spec follow-up review / fix / re-review passed.
- Default enabled / effective discovery re-review:
  - AgentDS artifact: `docs/reviews/wu-tools-01-f03-default-enabled-effective-discovery-rereview-ds.md`, verdict `pass`.
  - AgentMiMo short re-review verdict: `pass-with-findings`, no blocking findings.

## Residual Risk Reconciliation

| Risk | Final status | Owner / Destination |
|---|---|---|
| Tavily / Serper key, auth, quota, rate limit, and external provider availability are environment-dependent. | diagnostic-only by design | Web smoke summary; not a local hard gate |
| Tools Discovery spec semantics need follow-up evaluation: remove `allow_empty`, remove `include_read_tools`, set `workspace_root` to `"workspace/"`, migrate Fins read / Doc OLD limits, and remove upload `allowed_upload_roots`. | transferred-to-issue | GitHub Issue #133 |
| SEC/Fins and CN/HK Docling CI coverage remain outside Web smoke scope. | deferred-with-owner | WU-TOOLS-01-F04/F05 and WU-TOOLS-01-F06/F07 |

No active WU-TOOLS-01-F03 residual risk remains without an owner.

## Non-Goals Preserved

- Did not make external provider availability a local hard gate.
- Did not close GitHub Issue #120 before draft PR merge.
- Did not implement the Tools Discovery spec semantic cleanup tracked by GitHub Issue #133.
- Did not migrate SEC/Fins or CN/HK Docling CI pipelines.

## Next Entry Point

After the user merges draft PR 134, enter `WU-TOOLS-01-F04` goal confirmation unless the user asks to address a PR comment or CI result first.
