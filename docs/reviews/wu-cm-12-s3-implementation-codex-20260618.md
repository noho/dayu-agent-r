# WU-CM-12 S3 Implementation Artifact

## Gate

- Work unit: WU-CM-12 Conversation Memory Drift Repair
- Slice: S3 Shared Rendering And Selected-Id Provenance Guards
- Agent: Codex
- Date: 2026-06-18
- Status: implemented and locally validated

## Scope

Modified files:

- `dayu/host/run_input.py`
- `dayu/host/compact_material.py`
- `dayu/host/context_fallback.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_dispatch_scheduler.py`

No Engine message dataclasses, EventLog schema, durable schema, public API, tool role, or S4 tier fallback behavior were changed.

## Implementation Summary

`compact_material` now exposes a stable selected material view digest over selected block id, canonical source refs, and content digest. `context_fallback` writes that digest into fallback window payloads, carries selected source refs / floor / selected raw turn count / selected view digest into `ActiveRecentWindowFallback`, and fails closed when the active fallback payload digest or current input ref does not match the failed compact payload.

`run_input` now renders fallback material through a single selected material render view built from `tuple[RunInputMaterialBlock, ...]` plus selected ids. The renderer does not read EventLog and does not reselect material. It validates duplicate selected ids, missing selected ids, current input ref mismatch, selected source refs mismatch, fallback input digest mismatch, selected material digest mismatch, selected raw turn count mismatch, protected turn-group mismatch, and protected group consistency mismatch before producing Engine messages.

Accepted compact artifact rendering no longer emits lossy count summaries such as `evidence_backed_facts=1`. It renders complete semantic lines for session summary, facts, answer anchors, forward intents, and reference continuity. If an accepted compact candidate has no semantic lines, the ordinary compact system material is whole-dropped before rendering.

Control follow-up patch: accepted compact semantic renderer now uses strict optional text handling for `evidence_kind` and `reason`. A missing optional field is omitted, but a present non-string or blank value raises `HostDurableError`.

Review fix patch: `EventLogContextFallbackProvider` now treats `selected_recent_window_turn_floor`, `selected_raw_turn_count`, and `selected_material_view_digest` as required always-present fallback window fields. Missing, malformed, negative integer, or blank text values fail closed with `HostDurableError`. The unreachable `protected_recent_raw_turn=True` marked-group production guard and its synthetic test were removed; protected group consistency remains enforced by requiring all expected protected group block ids to be selected.

Dispatch scheduler tests that intentionally exercise proactive lifecycle behavior had hard-budget fixtures raised to account for full semantic compact rendering instead of old short count summaries.

## Tests Added Or Updated

`tests/host/test_run_input_builder.py` now covers:

- selected ids render all and only selected blocks;
- selected source refs are preserved;
- missing selected id fails closed with `HostDurableError`;
- duplicate selected ids fail closed with `HostDurableError`;
- current input ref mismatch fails closed with `HostDurableError`;
- selected source refs mismatch fails closed with `HostDurableError`;
- fallback input digest mismatch fails closed with `HostDurableError`;
- selected material view digest mismatch fails closed with `HostDurableError`;
- selected raw turn count mismatch fails closed with `HostDurableError`;
- protected group consistency mismatch fails closed with `HostDurableError`;
- EventLog-backed fallback provider payload drift fails closed for missing fallback window, digest mismatch, current input ref mismatch, and missing / invalid always-present provenance fields;
- accepted compact optional semantic text fields fail closed when present but invalid;
- accepted compact semantic material renders full items and no longer renders lossy count summaries.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q
```

Result: `170 passed in 1.79s`

Review fix validation:

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q
```

Result: `181 passed in 1.90s`

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py -q
```

Result: `65 passed in 0.63s`

Passed:

```bash
source .venv/bin/activate && pyright dayu/host/run_input.py dayu/host/compact_material.py dayu/host/context_fallback.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py
```

Result: `0 errors, 0 warnings, 0 informations`

Passed:

```bash
git diff --check
```

Result: no whitespace errors.

## README Decision

Checked `dayu/host/README.md` and `tests/README.md` update constraints before editing. No README update was made:

- Host stable architecture, public contract, and documented module responsibilities did not change.
- Test hierarchy, test running method, and test maintenance rules did not change.

## Residual Risk

- No unclassified residual risk for S3.
- S4 tier fallback remains explicitly out of scope.
- Digest scope is intentionally limited to selected block identity, canonical source refs, and content digest. This avoids false drift between compact selection material and ordinary RunInput material for rendering-irrelevant fields while still proving selected LLM-facing content and provenance are同源.
