# PR 68 Post-Draft Compactor Scene Prompt Fix Re-Review

**Date:** 2026-05-23
**Reviewer:** Claude Opus 4.7 (deepreview agent)
**Gate:** compactor scene prompt fix re-review
**Verdict: PASS**

---

## Design Intent Verification

### DI-1: Compactor prompt from scene, not hardcoded in Host

**Verdict: PASS**

Evidence chain:
- `CompactorRunnerBaseline` (`dayu/host/api.py:922-978`) now carries `compactor_system_prompt: str` and `compactor_user_prompt_template: str` as typed, validated fields.
- `LLMContextCompactor.__init__` (`dayu/host/llm_compaction.py:134-173`) receives both prompts as constructor parameters, validates non-empty, and validates template contains exactly one `<<compaction_request>>` placeholder.
- `host_assembly.py:514-555` prepares `conversation_compaction` scene via `prepare_scene`, extracts two ordered fragments as `_CompactorScenePrompts(system_prompt, user_prompt_template)`.
- `host_assembly.py:485-511` passes prompts into `CompactorRunnerBaseline`.
- `open_host.py:646-658` wires prompts from `CompactorRunnerBaseline` into `LLMContextCompactor`.
- Manifest `conversation_compaction.json` defines two fragments: `conversation_compaction_system` (order 100, required) → `conversation_compaction.md` and `conversation_compaction_user` (order 200, required) → `conversation_compaction_user.md`.
- No prompt text is hardcoded in any Host module. The only Host-owned prompt logic is `_compaction_request_prompt_block()` which renders typed request data, not task instructions.

### DI-2: Host boundary is typed CompactorRunnerBaseline; Host replaces <<compaction_request>>

**Verdict: PASS**

- `CompactorRunnerBaseline` is a frozen dataclass with full `__post_init__` validation in `dayu/host/api.py:922-978`.
- `_user_prompt()` (`llm_compaction.py:322-333`) does a single `str.replace` of `<<compaction_request>>` with the typed data block from `_compaction_request_prompt_block()` (`llm_compaction.py:336-361`).
- Host validates exactly one placeholder at construction time (`llm_compaction.py:165-169`).
- No Host code parses or interprets the scene prompt content beyond placeholder replacement.

### DI-3: Compactor runner options independent from ordinary Run options

**Verdict: PASS**

- `host_assembly.py:279-285` selects `ordinary_selection` from `execution_profile.run_baseline`.
- `host_assembly.py:286-297` selects `compactor_selection` from `execution_profile.compactor_baseline` using `compactor_baseline.runner_option_hint_id`.
- These are entirely independent `select_runner_option_hint` calls with independent `ExecutionBaselineConfig` inputs and independent `scene_model_hints`/`run_override`.
- `compose_options()` maps each into its respective baseline: `ordinary_run_baseline` vs `compactor_runner_baseline`.
- Test `test_compose_open_host_options_uses_runtime_tuning_from_config` (`tests/service/test_host_assembly.py`) verifies independent compactor runner options (temperature=0.4, top_p=1.0, stream=False).

### DI-4: open_questions_retained=false must fail quality accepted

**Verdict: PASS — this was the critical fix**

Before this diff, `test_quality_marks_open_questions_lost_when_clear_without_summary_questions` (`tests/host/test_compaction_contract.py`) only asserted `result.open_questions_retained is False` but did NOT assert `result.accepted is False`. The quality checker in `context_governance.py:596-608` and line 103 already added `OPEN_QUESTIONS_MISSING` to rejection reasons when `_open_questions_retained()` returned False, but the test was not verifying the full rejection path.

The fix adds two assertions:
```python
assert result.accepted is False
assert CompactQualityIssue.OPEN_QUESTIONS_MISSING in result.rejection_reasons
```

This confirms that `open_questions_retained=False` correctly propagates through `CompactQualityCheckResult.accepted = (len(reasons) == 0)` to cause rejection, closing the gap where a candidate with lost open questions could have theoretically been accepted at quality check and then failed later at canonical compact payload validation.

The `_open_questions_retained()` logic (`context_governance.py:596-608`) is correct:
- Returns True if `episode_summary_candidate.open_questions` is non-empty (line 603-604).
- Returns True if `pinned_state_patch_candidate.open_questions` is REPLACE with non-empty value (lines 605-607).
- Returns False otherwise — which is exactly the case tested.
- When False, `CompactQualityIssue.OPEN_QUESTIONS_MISSING` is added to rejection reasons (line 103), causing `accepted=False`.

### DI-5: No reverse dependency, no dayu.host importing dayu.config, no hidden compatibility seam

**Verdict: PASS**

Verified by grep:
- Zero matches for `from dayu.config` or `import dayu.config` in `dayu/host/`.
- Zero matches for `from dayu.service` or `import dayu.service` in `dayu/host/`.
- Zero matches for `from dayu.host` or `import dayu.host` in `dayu/config/`.
- "compat"/"legacy"/"backward" keyword hits in Host code are only:
  - `_reject_old_preserved_fact_ref_fields` / `_reject_old_quality_result_fields` in `context_events.py`: rejection of old field names, not compatibility support.
  - `_ITEM_KIND_OLD_VERIFIED_FACT` in `durable/memory.py`: migration-aware fact kind handling.
  - "checkpoint cannot move backwards" in `durable/projection.py`: legitimate invariant error message.
  - None constitute a hidden compatibility seam.

---

## Findings

### Finding 1 (INFO): Test coverage gap for scene prompt contract violation

**File:** `dayu/service/host_assembly.py:547-555`
**Severity:** Non-blocking observation

`_compactor_prompts_from_scene_inputs` raises `ValueError` when the compactor scene doesn't provide exactly two prompt fragments. There is no unit test that verifies this error path (e.g., passing scene inputs with 1 or 3+ system messages). The existing tests pass because the real scene manifest happens to have exactly 2 fragments. This is not blocking because the `scene_prepare` contract and manifest config jointly guarantee fragment count at load time, and a mismatch would fail at scene prepare, not at prompt extraction.

### Finding 2 (INFO): conversation_compaction_user.md is untracked

**File:** `dayu/config/prompts/scenes/conversation_compaction_user.md`
**Severity:** Non-blocking observation

This file appears as `??` (untracked) in git status. It is the user prompt template referenced by the manifest and needed by the scene prepare flow. It must be `git add`ed before commit. The manifest references it by path `scenes/conversation_compaction_user.md` and all tests that use scene prepare depend on it being present. This is purely a VCS tracking issue, not a code issue.

### Finding 3 (PASS): Smoke test validates full prompt flow end-to-end

**File:** `tests/host/test_public_compact_smoke.py:181-199`

The smoke test now uses `_compactor_prompts()` which calls `prepare_scene` with the real scene manifest and real prompt files. This validates the full flow from scene asset → Service assembly → Host compactor → LLM for all configured providers. The test also uses `_compactor_runner_options()` to independently resolve compactor runner hints from `conversation_compaction` in `models.json`.

### Finding 4 (PASS): Scene assembly correctly handles compactor prompts via system_messages

**File:** `dayu/service/host_assembly.py:547-555`

The design uses `scene_inputs.system_messages` to extract both the system prompt (fragment 0) and user prompt template (fragment 1). Both fragments are loaded as system-level messages by the scene system (which has no user-message concept), and the Service layer repurposes the second one as the user prompt template for the compactor. This is consistent with the scene contract and does not leak scene internals into Host.

### Finding 5 (PASS): LLMContextCompactor constructor validates non-empty prompts and placeholder

**File:** `dayu/host/llm_compaction.py:153-169`

Constructor validation:
- `system_prompt` must be non-empty string (ValueError if only whitespace).
- `user_prompt_template` must be non-empty string.
- `user_prompt_template` must contain exactly one `<<compaction_request>>` placeholder.
- All validations raise with field-name-specific error messages.

These validations replace the previous hardcoded prompt behavior with explicit contract enforcement.

---

## Smoke Test Readiness

The target smoke test (`test_real_compactor_public_opener_compacts_and_preserves_continuity` in `tests/host/test_public_compact_smoke.py`) **can pass** provided:

1. `conversation_compaction_user.md` is committed (currently untracked).
2. The configured models in `dayu/config/models.json` have a `conversation_compaction` entry under `runtime_hints.runner_option_hints`.
3. The live LLM providers return strict JSON matching the proposal schema defined in `conversation_compaction_user.md`.

The test already validates these paths and uses real provider configurations. No code-level issues blocking smoke test execution were identified.

---

## Residual Risks

None. All five design intent items pass with direct evidence. The two INFO-level findings are non-blocking observations (missing test for unlikely error path, untracked file that needs staging).
