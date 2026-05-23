# PR 68 Post-Draft Compactor Scene Prompt Fix Re-Review

- **Gate**: compactor scene prompt fix re-review
- **Reviewer**: mimo
- **Date**: 2026-05-23
- **Scope**: current uncommitted diff (20 files, +333/-125)

## Verdict: PASS

## Design Intent Verification

### 1. Compactor prompts come from scene, not hardcoded in Host

**PASS.** `_SYSTEM_PROMPT` hardcoded string removed from `dayu/host/llm_compaction.py:77-87`. `LLMContextCompactor.__init__` now requires `system_prompt` and `user_prompt_template` parameters (`llm_compaction.py:139-140`). Service assembly (`host_assembly.py:514-555`) calls `prepare_scene()` on `conversation_compaction` scene and unpacks the two ordered fragments into `CompactorRunnerBaseline.compactor_system_prompt` / `compactor_user_prompt_template`. Host never reads prompt config or scene assets.

### 2. Host public boundary remains typed CompactorRunnerBaseline

**PASS.** `CompactorRunnerBaseline` (`api.py:922-978`) gains two typed `str` fields: `compactor_system_prompt` and `compactor_user_prompt_template`. Both validated non-empty in `__post_init__`. No `dict`, `Any`, or extra payload used. Host only replaces `<<compaction_request>>` placeholder with typed request data block (`llm_compaction.py:330-333`).

### 3. Compactor runner options independent from ordinary Run options

**PASS.** `host_assembly.py:286-297` selects compactor runner hint from `execution_profile.compactor_baseline` (not `run_baseline`). Smoke test `_compactor_runner_options` (`test_public_compact_smoke.py:181-197`) reads hint from `config.models.models[model_id].runtime_hints.runner_option_hints["conversation_compaction"]`. Test asserts `temperature=0.4`, `top_p=1.0`, `stream=False`, `max_tokens=None` (`test_host_assembly.py:107-110`).

### 4. open_questions_retained=false blocks at quality gate

**PASS.** `context_governance.py:60,102-103`: `_open_questions_retained()` result now feeds `CompactQualityIssue.OPEN_QUESTIONS_MISSING` into `issue_collector`, making `CompactQualityCheckResult.accepted=False`. `compaction.py:85`: `OPEN_QUESTIONS_MISSING` added to `CompactQualityIssue` enum. Test `test_compaction_contract.py:282-285`: asserts `result.accepted is False` and `OPEN_QUESTIONS_MISSING in result.rejection_reasons`. Previously this path returned `accepted=True` with `open_questions_retained=False` on the result, deferring failure to canonical payload validation.

### 5. No reverse dependency, no hidden compatibility seam

**PASS.** `grep 'from dayu.config' dayu/host/` returns zero matches. `dayu/host/` imports only from `dayu.contracts`, `dayu.engine`, and own package. Scene asset loading happens exclusively in `dayu/service/host_assembly.py`. No compatibility re-export, wrapper, or facade introduced.

## Findings

No blocking findings.

## Detailed Review

### Prompt Source Architecture

| Concern | Status | Evidence |
|---------|--------|----------|
| System prompt from scene | OK | `conversation_compaction.md` → fragment order 100 → `system_messages[0]` |
| User template from scene | OK | `conversation_compaction_user.md` → fragment order 200 → `system_messages[1]` |
| Placeholder not consumed by ScenePrepare | OK | `<<compaction_request>>` uses `<<>>` delimiters; ScenePrepare only processes `{{...}}` context slots |
| Template placeholder count validated | OK | `llm_compaction.py:165`: `count() != 1` raises ValueError |
| Manifest declares exactly 2 fragments | OK | `conversation_compaction.json` has 2 fragment entries with order 100, 200 |
| Fragment ordering deterministic | OK | `scene_prepare.py:612`: fragments sorted by `order` field |

### Quality Gate Hardening

| Concern | Status | Evidence |
|---------|--------|----------|
| OPEN_QUESTIONS_MISSING enum member | OK | `compaction.py:85` |
| Rejection wired into quality check | OK | `context_governance.py:102-103` |
| Test coverage | OK | `test_compaction_contract.py:282-285` |
| No regression on existing passing paths | OK | `open_questions_retained=True` path unchanged |

### Smoke Test Path

| Concern | Status | Evidence |
|---------|--------|----------|
| Smoke loads real scene prompts | OK | `test_public_compact_smoke.py:64-77`: `prepare_scene()` on actual config root |
| Smoke reads compactor hint from config | OK | `test_public_compact_smoke.py:181-197`: `ConfigLoader` → `runner_option_hints["conversation_compaction"]` |
| Smoke passes prompts to `CompactorRunnerBaseline` | OK | `test_public_compact_smoke.py:109-114` |
| Provider skip precision maintained | OK | Existing skip logic unchanged |

### Documentation Consistency

| Doc | Status | Note |
|-----|--------|------|
| `dayu/README.md` | Updated | Compactor prompt source documented in architecture and extension points |
| `dayu/host/README.md` | Updated | Compactor baseline description updated with scene prompt assembly |
| `dayu/config/README.md` | Updated | `conversation_compaction` scene description added |
| `docs/host/design.md` | Updated | Design intent sections updated for scene prompt flow |
| `docs/host/implementation-control.md` | Updated | Gate conclusion and residual risk updated |
| `tests/README.md` | Updated | Public smoke description updated for scene prompt |

### Import Boundary

| Check | Result |
|-------|--------|
| `dayu.host` → `dayu.config` | 0 matches |
| `dayu.host` → `dayu.runtime` | Not in diff; existing boundary preserved |
| `dayu.service` → `dayu.runtime.scene_prepare` | OK; Service is allowed to depend on runtime |

## Target Smoke Assessment

`test_public_compact_smoke.py` can pass. The test:
1. Loads real `conversation_compaction` scene from package config via `prepare_scene()`
2. Reads compactor runner options from `models.json` via `ConfigLoader`
3. Passes both to `CompactorRunnerBaseline`
4. The smoke requires actual provider credentials to run the LLM compactor; skip logic for missing secrets is unchanged

## Residual Risks (Non-Blocking)

1. **Raw evidence aggregate prompt budget**: Large session compact raw context items combined with scene prompt + request envelope may exceed provider context window. Listed in `implementation-control.md` under Phase 15 hardening. Low risk for soft-threshold proactive compaction; higher risk for Engine overflow reactive compaction.

2. **Scene prompt content drift**: The system prompt (`conversation_compaction.md`) and user template (`conversation_compaction_user.md`) are now config assets outside Host. If they drift from `CompactionCandidate` schema expectations, `LLMCompactionProposalError` will catch it at runtime, but there is no static compile-time guard. Acceptable for v1.

3. **Fragment count coupling**: `_compactor_prompts_from_scene_inputs` hardcodes `_COMPACTOR_PROMPT_FRAGMENT_COUNT = 2`. If scene manifest adds a third fragment, assembly will fail fast with a clear ValueError. Acceptable coupling given the scene's documented two-fragment contract.
