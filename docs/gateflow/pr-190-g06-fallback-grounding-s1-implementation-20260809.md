# PR 190 G06 fallback grounding S1 implementation

## Gate state

- Work unit: G06-5 dispatch fallback grounding
- Slice: S1 — Project fallback evidence boundary into ordinary RunInput
- Gate: implementation
- Decision: implementation complete; next gate is code review
- Baseline plan commit: `c7a937e1`

## Scope and owner

The implementation changes only the Host-owned LLM-facing projection of an existing typed `ActiveRecentWindowFallback`. It does not change fallback selection, compaction attempts, Memory, schema, storage, tool availability, provider transport or Run terminal state.

## Changed files

- `dayu/host/run_input.py`
  - adds one module-level fallback grounding guidance;
  - projects it through the existing `Execution guidance:` classifier;
  - injects it in both Attempt-free pre-start and existing `RunInputBuilder` fallback paths;
  - returns no message when the typed fallback fact is absent.
- `tests/host/test_run_input_builder.py`
  - locks the guidance semantics, single occurrence and absence of internal governance terminology in the direct builder path.
- `tests/host/test_dispatch_scheduler.py`
  - locks the production pre-start scheduler path and selected/dropped material behavior;
  - raises only affected synthetic context-window thresholds so the newly required guidance is included in the complete candidate budget instead of causing those tests to exercise fail-closed behavior.
- `docs/host/design.md`
  - freezes the tier 4/5 LLM-facing evidence-boundary behavior and successful insufficient-context final-answer semantics.
- `dayu/host/README.md`
  - records the implemented Host RunInput projection for package developers.

## Data flow and invariants

```text
typed ActiveRecentWindowFallback | None
  -> _fallback_execution_guidance_messages
  -> existing SystemMessage classifier
  -> existing one-system-message envelope
  -> AgentRunRequest
```

- No fallback is inferred from strings, refs, missing Memory or message counts.
- Selected/dropped fallback material and current-input cardinality are unchanged.
- The guidance contains no Host, compaction, fallback tier, artifact, ref, digest, cursor or policy terms.
- The guidance does not direct unconditional tool use; it requires both availability and user permission.
- Normal candidates still render the pre-existing exact Execution Guidance only.
- Final complete candidate sizing remains authoritative. Tests that intentionally require fallback dispatch provide enough synthetic hard-budget headroom for the required guidance; production thresholds are unchanged.

## Validation

- Focused owner paths: `4 passed`.
- Full affected files:
  - `pytest tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q`
  - result: `238 passed`.
- Changed Python Ruff: PASS.
- `python -m compileall -q dayu/host/run_input.py`: PASS.
- Full Pyright `dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: PASS.

## Documentation decision

- Updated `docs/host/design.md` and `dayu/host/README.md` because the change is a stable Host RunInput behavior.
- `tests/README.md` was inspected; no new test layer, command or maintenance convention was introduced, so no update is required.
- Root README and `dayu/README.md` do not change because no CLI workflow, option or layer relationship changed.

## Residual risks

- Real-provider adherence remains probabilistic; post-fix G06 real observation is required after deterministic review gates.
- Repeated generation stability and prompt-quality measurement remain assigned to Issue #193.
- Oracle/scenario acceptance remains owned by the user and is not modified in this slice.

## Completion status

`implementation-complete`
