# WU-CM-08 Compaction Material Readability And Smoke Maintenance Plan

## Goal Confirmation

GitHub Issue #95 is open and #81 is closed, so the work unit is unblocked. The motivation is valid, but the scope must stay narrow. Current code already implements compact material selection, prompt-local labels, evidence chunking, public compact smoke, and vNext compactor input rendering. WU-CM-08 should improve test readability, fixture maintainability, and smoke failure localization; it must not change memory semantics or compactor JSON semantics.

Direct evidence:

- `docs/host/design.md` now defines the current material sections as `previous_compacted_view`, `trace_material`, `evidence_material`, `answer_material`, and `current_input_anchor`. The older Issue #95 wording that mentions `stable_input` / `history_input` is stale and must not be restored.
- `dayu/host/compact_material.py` owns material pack construction, prompt-local labels, evidence chunk labels, and `conversation_compact_input_vnext_from_material_pack(...)`.
- `tests/host/test_compact_material.py` already covers deterministic segment selection, protected current input, vNext material mapping, evidence label provenance, chunking, and EventLog-backed pre-dispatch material.
- `tests/host/test_public_compact_smoke.py` already covers public compact paths with deterministic fake compactor, but some assertions are inline and make boundary failures harder to classify.
- Baseline validation passed: `pytest tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py -q` reported 41 passed, 1 skipped.

## Non-Goals

- Do not change memory snapshot schema.
- Do not introduce new compact material sections, new compactor JSON fields, or new proposal semantics.
- Do not redesign Conversation Memory categories or #81 semantic model.
- Do not change public Host API, `OpenHostOptions`, compactor baseline contracts, EventLog schema, durable schema, or runner-call manifest schema.
- Do not add broad golden snapshots of full compact material JSON.
- Do not move test helpers into production code unless a production duplication defect is directly proven.

## Slice 1: Focused Compact Material Test Readability

Allowed files:

- `tests/host/test_compact_material.py`
- `docs/reviews/wu-cm-08-s1-implementation-report.md`

Exact changes:

- Add small test-only assertion helpers with concrete typed contracts:
  - `_MaterialPackShape` as a `NamedTuple` or frozen test dataclass containing `previous_labels: tuple[str, ...]`, `trace_labels: tuple[str, ...]`, `evidence_labels: tuple[str, ...]`, `answer_labels: tuple[str, ...]`, `current_anchor_label: str`, and `citable_source_labels: tuple[str, ...]`.
  - `_VNextInputShape` as a `NamedTuple` or frozen test dataclass containing `top_level_keys: tuple[str, ...]`, `previous_count: int`, `trace_count: int`, `evidence_count: int`, `answer_count: int`, and `current_anchor_label: str`.
  - Assertion helpers must emit boundary-specific failure messages naming `previous_compacted_view`, `trace_material`, `evidence_material`, `answer_material`, `current_input_anchor`, `instruction`, `prompt-local label`, or `citable_source_labels` as appropriate.
  - Helpers must use typed tuples and concrete dataclasses / `NamedTuple`; do not introduce `Any`, `object`, untyped containers, or full JSON snapshot comparison.
- Strengthen the existing stale-name coverage in `test_conversation_compact_input_vnext_maps_material_without_citable_current_anchor`: it already excludes `stable_input`, `history_input`, and `evidence_input`; add positive assertions that all six current top-level JSON keys are present (`previous_compacted_view`, `trace_material`, `evidence_material`, `answer_material`, `current_input_anchor`, `instruction`).
- Add or strengthen a post-compaction pack-shape assertion through `build_compact_material_pack(...)` -> `conversation_compact_input_vnext_from_material_pack(...)`, proving the current section names and label boundaries hold beyond the initial material-pack path.
- Refactor only the narrow assertions around existing section/label readability where it makes failures identify the boundary: section mapping, current anchor non-citable status, evidence chunk labels, and provenance map.
- Keep assertions semantic and small. Do not snapshot full material JSON.
- Do not modify production files in this slice. If the strengthened tests expose a real production defect in `dayu/host/compact_material.py` or `dayu/host/compaction.py`, stop the slice, record the defect in the implementation report and control doc, and request a separate production-fix scope instead of silently broadening WU-CM-08.

Validation:

- Before edits: `pytest tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py -q` to confirm the 41 passed, 1 skipped baseline has not drifted.
- `pytest tests/host/test_compact_material.py -q`
- `python -m pyright dayu/ tests/ utils/`
- `git diff --name-only` to verify the slice only touched allowed files.

## Slice 2: Public Compact Smoke Failure Localization

Allowed files:

- `tests/host/test_public_compact_smoke.py`
- `tests/host/public_smoke_support.py`, only if avoiding duplication requires extracting a genuinely general public-smoke assertion helper; do not move compact-specific helpers there and do not change existing helper signatures or behavior.
- `docs/reviews/wu-cm-08-s2-implementation-report.md`

Exact changes:

- Extract focused public-smoke assertion helpers for:
  - compactor material instruction contract, by extending or splitting the existing `_assert_compactor_material_instruction_contract(...)` rather than adding a parallel overlapping helper;
  - current material section shape and stale legacy section exclusion;
  - forbidden internal terms in LLM-facing material;
  - evidence material presence and marker retention;
  - fake compactor proposal using prompt-local labels only.
- Use helper names and assertion messages that identify the failing boundary: input construction, material pack / labels, compactor request / proposal, memory projection, or RunInput rendering.
- Add positive and negative tests for each newly extracted non-trivial helper. Negative cases must assert the boundary-specific failure message, for example material section shape, stale legacy section, forbidden internal term, missing evidence marker, or canonical ref leakage in a fake proposal.
- Keep fake compactor behavior deterministic and label-only. Do not call real providers or require `DAYU_RUN_REAL_COMPACTOR_SMOKE`.
- Do not change the default skip behavior of optional real compactor smoke.
- If new assertions interact with `tests/host/fake_compaction.py` and encounter the pre-existing `cast(...)` residual from WU-CM-05, document it in the implementation report and do not fix it in WU-CM-08 unless it causes a direct test or pyright failure inside the approved slice.

Validation:

- Before edits: `pytest tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py -q` to confirm the 41 passed, 1 skipped baseline has not drifted.
- `pytest tests/host/test_public_compact_smoke.py -q`
- `python -m pyright dayu/ tests/ utils/`
- `git diff --name-only` to verify the slice only touched allowed files.

## Artifacts And State Transitions

- After plan acceptance, update `docs/host/issues-implementation-control.md` to `implementation` / `WU-CM-08-S1 implementation gate`.
- Slice 1 must write `docs/reviews/wu-cm-08-s1-implementation-report.md`, run the S1 validation, then enter code review / re-review as needed before an accepted slice commit.
- Slice 2 must write `docs/reviews/wu-cm-08-s2-implementation-report.md`, run the S2 validation, then enter code review / re-review as needed before an accepted slice commit.
- Aggregate deepreview must cover both slices, baseline drift, README decisions, and any residual risks. Accepted nonblocking residual risks must be recorded in this control doc with an owner or an explicit non-actionable rationale.
- After WU-CM-08 aggregate acceptance, the next work unit is WU-CM-09.

## README Decision

Check but likely do not update:

- `tests/README.md`: update only if WU-CM-08 adds a new test layer, command, or maintenance rule. Focused helper extraction and small assertions inside existing `tests/host/` files should not change README.
- If a new shared helper module is introduced, or if `tests/host/public_smoke_support.py` gains a new reusable helper that future tests are expected to use, update `tests/README.md` to document the maintenance pattern.
- `dayu/host/README.md`: not triggered unless production Host code or stable developer-facing compact behavior changes. This plan should avoid production changes.

## Acceptance

- Compact material section naming and prompt-local label boundaries are easier to read and fail locally in tests.
- Public compact smoke failures identify whether the boundary is material construction, labels/chunking, compactor request/proposal, memory projection, or RunInput rendering.
- Existing public compact smoke remains meaningful without full-material golden snapshots.
- No production behavior, schema, public API, or memory semantic model changes are introduced.
