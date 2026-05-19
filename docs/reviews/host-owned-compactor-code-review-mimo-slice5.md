# Host-owned compactor Slice 5 code review

## Review metadata

- **Reviewer**: AgentMiMo
- **Review date**: 2026-05-19
- **Gate**: code review for implementation Slice 5
- **Work unit**: Host-owned LLM context compactor public opener contract
- **Review target**: current uncommitted diff after accepted slice commit `7c2e7bd`
- **Approved plan**: `docs/host/host-owned-compactor-plan.md` Slice 5
- **Design source of truth**: `docs/host/design.md`
- **Implementation artifact**: `docs/reviews/host-owned-compactor-implementation-slice5-codex.md`

## Files reviewed

- `utils/smoke_host_public_multiturn.py` (diff: -378/+22 lines)
- `tests/host/test_public_compact_smoke.py` (diff: -407/+88 lines)
- `docs/reviews/host-owned-compactor-implementation-slice5-codex.md`

## Review criteria checklist

### 1. Manual smoke and public compact smoke must not implement or inject ContextCompactor

**PASS** ✅

**Evidence**:
- `utils/smoke_host_public_multiturn.py`: `DeepSeekContextCompactor` class completely removed (was lines ~130-296 in original)
- `tests/host/test_public_compact_smoke.py`: `_RealLLMContextCompactor` class completely removed (was lines ~62-228 in original)
- Both files now use `CompactorRunnerBaseline` which only accepts runner spec/options and artifact configuration
- No `ContextCompactor` import remains in either file

### 2. No DeepSeekContextCompactor / _RealLLMContextCompactor / compactor prompt / candidate mapper / thread wrapper remains as Service-side compactor pattern

**PASS** ✅

**Evidence**:
- All Service-side compactor implementation classes removed:
  - `DeepSeekContextCompactor` (smoke)
  - `_RealLLMContextCompactor` (test)
  - `_NeverCancelledToken` (smoke & test)
  - `_CompactorRejectingToolExecutor` (smoke)
  - `_RejectingToolExecutor` (test)
- All candidate mapper functions removed:
  - `_candidate_from_summary` (smoke & test)
  - `_preservation_evidence` (smoke & test)
  - `_range_for_request` (smoke & test)
  - `_summarized_ranges` (smoke & test)
  - `_confirmed_fact_summaries` (smoke & test)
- All compactor-specific imports removed from both files:
  - `threading`, `datetime` (no longer needed)
  - `BatchToolExecutionRequest`, `BatchToolExecutionOutcome`, `BatchToolExecutionRecord`, `ToolFailedOutcome`, `ToolResultFailure`
  - `run_agent_and_wait`, `AgentRunRequest`, `EngineRunOutcomeFinalAnswer`
  - `AgentMessageRole`, `SystemMessage`, `UserMessage`
  - All `dayu.host.compaction` imports (`CompactInputRange`, `CompactionCandidate`, `CompactionRequest`, `ContextCompactor`, etc.)

### 3. Ordinary DeepSeek runner spec/options helpers remain for normal run execution

**PASS** ✅

**Evidence**:
- `utils/smoke_host_public_multiturn.py:375-401`: `_deepseek_runner_spec(api_key)` function preserved
- Used for both ordinary runner and compactor runner construction in `_open_options()`
- `RunnerCallOptions` construction preserved for normal run execution

### 4. OpenHostOptions uses compactor_runner_baseline=CompactorRunnerBaseline(...) only with runner spec/options/artifact root/create-parent-dir

**PASS** ✅

**Evidence**:
- `utils/smoke_host_public_multiturn.py:339-344`:
  ```python
  compactor_runner_baseline=CompactorRunnerBaseline(
      compactor_runner_spec=compactor_runner_spec,
      compactor_runner_options=runner_options,
      compact_artifact_root=work_dir / "compact-artifacts",
      compact_artifact_create_parent_dirs=True,
  ),
  ```
- `tests/host/test_public_compact_smoke.py:91-96`:
  ```python
  compactor_runner_baseline=CompactorRunnerBaseline(
      compactor_runner_spec=compactor_runner_spec,
      compactor_runner_options=runner_options,
      compact_artifact_root=compact_artifact_root,
      compact_artifact_create_parent_dirs=True,
  ),
  ```
- No `ContextCompactor` instance, no `policy_ref`, no prompt, no candidate builder passed

### 5. Smoke stdout avoids compactor call_count/last_summary and sensitive API key/header/full prompt/provider payload

**PASS** ✅

**Evidence**:
- `utils/smoke_host_public_multiturn.py:661-676`: `_print_compact_summary()` function updated:
  - Removed: `print(f"SMOKE COMPACT_CALL_COUNT {compactor.call_count}")`
  - Removed: `print(f"SMOKE COMPACT_LAST_SUMMARY {compactor.last_summary!r}")`
  - Retained: `SMOKE COMPACT_ARTIFACT_ROOT`, `SMOKE COMPACT_ARTIFACT_FILE_COUNT`, `SMOKE COMPACT_ARTIFACT` (bounded by `_COMPACT_ARTIFACT_PRINT_LIMIT = 10`)
- Function signature changed from `_print_compact_summary(work_dir, compactor)` to `_print_compact_summary(work_dir)`
- No API key, headers, full prompt, or provider payload printed

### 6. Public compact smoke uses public/observable evidence

**PASS** ✅

**Evidence**:
- `tests/host/test_public_compact_smoke.py:131-151`: Assertions updated to use public/observable evidence:
  - Terminal success: `assert first_terminal.kind is HostEventKind.SUCCEEDED`
  - Session alignment: `assert first_terminal.session_id == session.session_id`
  - Run alignment: `assert first_terminal.run_id == compacted.accepted_run_id`
  - Artifact existence: `assert len(new_artifacts) > 0`
  - Artifact content verification:
    ```python
    artifact = _compact_artifact_for_run(new_artifacts, compacted.accepted_run_id)
    input_snapshot = _required_mapping(
        artifact[_INPUT_SNAPSHOT_REFS_FIELD],
        field_name=_INPUT_SNAPSHOT_REFS_FIELD,
    )
    current_user_input_ref = input_snapshot[_CURRENT_USER_INPUT_REF_FIELD]
    assert isinstance(current_user_input_ref, str)
    assert current_user_input_ref.strip() != ""
    ```
  - Continuity: `assert second_terminal.final_answer.content.strip() != ""`
- No internal event checks (e.g., `CONTEXT_COMPACTED`) as primary correctness signal
- Helper functions added for artifact verification:
  - `_compact_artifact_files()`: Lists files in artifact root
  - `_compact_artifact_for_run()`: Finds artifact matching run_id with `llm-compact:{run_id}` candidate id
  - `_read_json()`: Reads JSON artifact
  - `_required_mapping()`: Validates JSON object structure

### 7. Provider skip remains env-gated; no network pytest by default

**PASS** ✅

**Evidence**:
- `tests/host/test_public_compact_smoke.py:55`: `api_key = api_key_or_skip(case)`
- `tests/host/test_public_compact_smoke.py:114`: `skip_if_provider_terminal_failed(case, first_terminal)`
- `tests/host/test_public_compact_smoke.py:127`: `skip_if_provider_exception(case, exc)`
- `tests/host/test_public_compact_smoke.py:130`: `skip_if_provider_terminal_failed(case, second_terminal)`
- All skip logic preserved from `tests/host/public_smoke_support.py`
- No network pytest required by default

### 8. No Host core/README overstep

**PASS** ✅

**Evidence**:
- Only `utils/smoke_host_public_multiturn.py` and `tests/host/test_public_compact_smoke.py` modified
- No changes to Host core files (`dayu/host/`)
- No README changes (deferred to Slice 6 per plan)
- Implementation artifact notes: "README files were not edited. Slice 6 owns README synchronization per the approved plan and this handoff's explicit scope constraint."

## Additional findings

### Finding 1: Smoke function return type change

**File**: `utils/smoke_host_public_multiturn.py:279-281`
**Change**: `_open_options()` return type changed from `tuple[OpenHostOptions, DeepSeekContextCompactor, SmokeFactTool]` to `tuple[OpenHostOptions, SmokeFactTool]`
**Impact**: None - function is module-private
**Status**: PASS ✅

### Finding 2: Policy ref update

**File**: `tests/host/test_public_compact_smoke.py:89`
**Change**: `policy_ref` updated from `"slice6-real-compact-policy"` to `"slice5-real-compact-policy"`
**Impact**: None - test-only policy reference
**Status**: PASS ✅

### Finding 3: Thread name in smoke script

**File**: `utils/smoke_host_public_multiturn.py` (removed)
**Change**: Thread name `"host-public-smoke-compactor"` removed along with `_CompactorRejectingToolExecutor`
**Impact**: None - compactor now owned by Host
**Status**: PASS ✅

### Finding 4: Test docstring update

**File**: `tests/host/test_public_compact_smoke.py:1`
**Change**: Module docstring updated from `"P10.5 Slice 6 public real-compactor smoke"` to `"P10.5 Slice 5 public real-compactor smoke"`
**Impact**: None - documentation only
**Status**: PASS ✅

## Validation results

- **pyright**: `0 errors, 0 warnings, 0 informations` ✅
- **pytest**: `1 passed in 3.70s` ✅
- **git diff --check**: No whitespace errors ✅

## Residual risks

1. **README synchronization pending**: README files may still mention older Service-side compactor injection until Slice 6 updates docs. Owner: Slice 6 docs.

2. **Real provider dependency**: Real provider behavior is still externally dependent when the provider API key is present; existing skip helpers handle unavailable, quota, rate-limit, and provider terminal failure cases. Owner: current provider smoke environment.

3. **Artifact file system dependency**: Test assertions rely on checking artifact files in the file system. This is the correct approach for verifying Host-owned compactor output, but introduces a dependency on file system state. Owner: Host core / already accepted earlier slices.

## Conclusion

**PASS** ✅

All review criteria satisfied. The implementation correctly:
- Removes all Service-side compactor implementations from smoke and test files
- Migrates to `CompactorRunnerBaseline` with only runner spec/options and artifact configuration
- Uses public/observable evidence for correctness assertions
- Maintains env-gated provider skip logic
- Does not overstep into Host core or README changes

The changes are clean, well-structured, and align with the approved Slice 5 plan. No blocking findings identified.
