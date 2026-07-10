# WU-SEMANTIC-OWNERSHIP-01 P3-C S3 Fix - AgentCodex

## Scope

Fix gate for controller-accepted code review finding `P3-C-S3-CR-F01`.

## Fixed

### P3-C-S3-CR-F01

Accepted evidence material and renderer now have a single canonical import owner:

- `dayu.host.evidence` remains the leaf contract for `AcceptedToolEvidenceLLMMaterial`, accepted evidence fallback texts, typed mismatch exception, and `render_accepted_tool_evidence_for_llm`.
- `dayu.host.accepted_result_projection` still produces `AcceptedToolResultProjection.llm_material`, but no longer exposes material / renderer / fallback symbols through its public `__all__`.
- `dayu.host.durable.memory` imports `AcceptedToolEvidenceLLMMaterial` from `dayu.host.evidence` and only imports `project_accepted_tool_result` from `accepted_result_projection`.
- Tests that need material / renderer / fallback texts import them from `dayu.host.evidence`.
- `dayu/host/README.md` now states that consumers use accepted-result projection material and call the unique renderer from `dayu.host.evidence`.

## Rejected Observation

`P3-C-S3-CR-F02` was not changed. `CompactEvidenceBlock.size_units` using `material.result_text` is consistent with the existing initial evidence path and the S3 plan's no-rename component mapping.

## Validation

- `python -m pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py -q` -> `227 passed`
- S3 affected matrix -> `449 passed, 1 skipped`
- import / weak typing guards -> `25 passed`
- targeted pyright -> `0 errors`
- full pyright -> `0 errors`
- coverage gate -> total `89.39%`; every touched production file remained >= 80%
- canonical import scan for evidence symbols from `accepted_result_projection` -> zero matches
- old string / `str(exc)` / private renderer / envelope re-parse scans -> zero matches
- `git diff -- dayu/host/tool_trace.py` -> empty
- `git diff --check` -> pass

## Propagation Audit

Accepted evidence facts still originate in ToolRuntime / accept barrier durable payloads, are projected by `accepted_result_projection` into `AcceptedToolResultProjection.llm_material`, and are rendered only by `dayu.host.evidence.render_accepted_tool_evidence_for_llm`. Durable memory, Conversation Memory, compact material, compact pipeline, and RunInput consume the same typed material or renderer result. No downstream consumer reconstructs the evidence material from payload refs, event ids, or rendered text.
