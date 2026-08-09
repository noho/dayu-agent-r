# PR 190 G06 fallback grounding Gateflow plan

## Gate state

- Work unit: G06-5 dispatch fallback grounding
- Goal confirmation: accepted from the user's explicit adjudication and instruction to fix
- Current gate: plan
- Next gate: plan review
- Target branch: `codex/interactive-oracle`
- Target baseline: `23097230861fe4acad730054e0ba9818ca42bd4f`
- Existing PR: #190

## Goal and motivation

When a real compaction operation exhausts bounded repair and Host continues through a tier 4/5 dispatch fallback, the ordinary Runner sees only the selected fallback material. The model must understand that material outside the current request is unavailable and must not reconstruct missing facts from user references, prior assistant claims, or general knowledge.

The motivation is established by the real `interactive.interactive.g06.cap-constrained-memory-replacement@1` observation: Host correctly rejected five invalid proposals and dispatched a bounded recent-window fallback, but the ordinary model then emitted several risk claims that were absent from the actual Runner input.

## Success signals

1. A fallback-backed ordinary RunInput contains explicit business-readable Execution Guidance stating that earlier conversation material may be unavailable.
2. The guidance requires the model to use only directly supporting material visible in the current request, and not treat user references, prior assistant claims, or general knowledge as evidence for missing facts.
3. When required facts are absent, the guidance tells the model to use available tools only when the user's instruction permits; otherwise it must state that the available material is insufficient and ask to retrieve or provide evidence.
4. The guidance is derived only from the typed active fallback fact and appears only in fallback-backed RunInput.
5. Normal ordinary, accepted-compaction and reconnect paths remain byte-for-byte unchanged unless they also carry an active dispatch fallback.
6. The LLM-facing message does not expose Host, compaction, fallback tier, operation id, event id, artifact, digest, cursor, policy or other governance terminology.
7. Existing parser, repair, fallback selection, Memory, durable state, tool availability and Run terminal semantics are unchanged.

## Non-goals and scope boundary

- Do not change the compaction schema, prompts, attempt budget or acceptance barrier.
- Do not retry compaction beyond the existing bounded operation.
- Do not use rejected proposals or rematerialize historical Memory.
- Do not add a natural-language answer verifier, citation parser or post-generation heuristic.
- Do not change tool schemas, provider adapters or Issue #193's stability-measurement scope.
- Do not modify Oracle/scenario/readiness registries before the user adjudicates the post-fix real observation.
- Do not modify the unrelated untracked `docs/reviews/plan-review-20260808-095346.md`.

## First-principles judgment and direct evidence

- Host owns the active fallback decision and exact selected material in `dayu.host.context_fallback` and `dayu.host.run_input`.
- `dayu/host/run_input.py::_fallback_context_messages` currently renders only selected material blocks; it does not project the fact that earlier material may be unavailable.
- `dayu/host/run_input.py::_default_scene_messages` supplies generic Execution Guidance, and `_normalize_ordinary_run_messages` already merges all guidance into the single `## Execution Guidance` system-envelope section.
- `dayu/config/prompts/base/fact_rules.md` already forbids unsupported facts globally, but the G06 real observation proves that generic wording alone did not communicate the fallback input boundary reliably.
- `docs/host/design.md` permits business-readable execution guidance while forbidding internal fallback diagnostics in LLM-facing text. Therefore the correct owner fix is a minimal Host projection from the active fallback fact, not a generic prompt change or downstream answer checker.

## Design decisions

1. Add one module-level LLM-facing fallback guidance constant/helper in `dayu/host/run_input.py`.
2. The helper accepts the typed `ActiveRecentWindowFallback` presence rather than inferring fallback from refs, trigger strings, message count or missing Memory.
3. Insert the guidance as a `SystemMessage` prefixed with the existing `Execution guidance:` classifier before fallback material is normalized.
4. Reuse `_normalize_ordinary_run_messages`; do not introduce a second envelope renderer or public contract.
5. Keep tool handling declarative: the fallback guidance says to use tools only when both available and permitted by the user's instruction. Existing default scene guidance remains the truth for enabled/disabled tool availability.
6. A final answer that honestly reports insufficient available material is a successful ordinary Run; no lifecycle or exit-code change is required.

## Contract and state-machine impact

- Public API/schema/storage changes: none.
- Host state-machine changes: none.
- Durable event or manifest schema changes: none.
- LLM-facing behavioral contract: fallback-backed ordinary RunInput gains one deterministic Execution Guidance item.
- Semantic owner: Host RunInput fallback projection, directly downstream of the typed active fallback decision.

## Implementation slice

### S1 — Project fallback evidence boundary into ordinary RunInput

- Objective: make the bounded fallback evidence boundary actionable to the ordinary model without exposing internal governance state.
- Allowed production files:
  - `dayu/host/run_input.py`
- Allowed tests:
  - `tests/host/test_run_input_builder.py`
  - existing focused Host public/integration tests only if a direct assertion must be updated
- Allowed documentation:
  - `docs/host/design.md`
  - `dayu/host/README.md` if its update constraints classify the behavior as Host-reader relevant
  - `tests/README.md` only if its update constraints require documenting a new testing convention
- Exact changes:
  1. Define the minimal fallback guidance text at module scope.
  2. Add a private helper returning the guidance message for a typed active fallback.
  3. Include that message in both fresh pre-start and recovery fallback RunInput construction paths.
  4. Add owner-level assertions for presence, absence on normal paths, material selection preservation, tool-permission wording and forbidden internal terms.
  5. Freeze the behavior in Host design truth.
- Invariants:
  - selected fallback material, source refs, caps, manifest refs and digest logic do not change;
  - current user input remains present exactly once;
  - one-system-message normalization remains true;
  - no internal identifier is rendered to the model.
- Stop condition: any implementation need to alter compaction lifecycle, schema, Memory, provider transport or final-answer validation requires a new goal confirmation.

## Validation

1. Focused owner tests for fallback and system-envelope behavior.
2. Affected Host RunInput test file.
3. Full Pyright, because production Python changes.
4. Changed-file Ruff/compileall and `git diff --check`.
5. Post-fix real `interactive.interactive.g06.cap-constrained-memory-replacement@1` run using production CLI, real provider and real AAPL corpus; report the observed final answer for user adjudication rather than asserting semantic correctness in code.

Expected assertions:

- fallback input has the new guidance exactly once;
- normal input lacks it;
- tools may be used only when available and user-permitted;
- otherwise the model must state insufficiency and request retrieval/provision;
- no forbidden governance fragments appear;
- selected/dropped material assertions remain unchanged.

## Documentation decision

- Update `docs/host/design.md` because it owns RunInput/fallback behavior and the LLM-facing projection boundary.
- Read `dayu/host/README.md` update constraints before deciding whether to update it.
- Read `tests/README.md` update constraints before deciding whether test changes require it.
- Root README and `dayu/README.md` are not expected to change because no CLI option, user workflow or layer relationship changes.

## Risks and residual ownership

- Prompt adherence remains probabilistic. This work only makes the fallback boundary explicit; repeated generation stability remains tracked by Issue #193.
- A model may still violate the instruction. The Host must continue to reject invalid compactor output and must not add a natural-language final-answer checker in this work unit.
- Post-fix semantic behavior remains subject to user Oracle adjudication.

## Completion report

Report changed production/docs/test files, exact validations, post-fix real observation, user-visible behavior, remaining probabilistic provider risk, PR 190 head/status and the next Oracle adjudication entry point.
