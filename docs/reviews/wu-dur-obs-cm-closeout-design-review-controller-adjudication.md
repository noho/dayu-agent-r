# WU-DUR / WU-OBS / WU-CM Closeout Slice 0 Design Review Controller Adjudication

## Gate

- Work unit: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01
- Gate: Slice 0.5 design review adjudication
- Review target: `docs/host/design.md`
- Slice 0 implementation artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice0-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-dur-obs-cm-closeout-design-review-mimo.md`
  - `docs/reviews/wu-dur-obs-cm-closeout-design-review-ds.md`

## Verdict

Design review result: pass-with-findings.

Controller judgment: Slice 0 design contract writeback is accepted. `docs/host/design.md` is now sufficient as the design truth source for Slice 1-7 implementation. No blocking finding remains.

## Findings Adjudication

| Finding | Source | Ruling | Owner / Destination |
|---|---|---|---|
| `RunnerCallReconstructionDiagnostic` is described narratively rather than as a formal table | MiMo F-01, DS F-001 | deferred-with-owner | Slice 4 implementation/review must ensure the implementation dataclass and focused tests encode the conditional required fields. Current design text is sufficiently explicit for Slice 1 start. |
| `RUNNER_CALL_INPUT_ASSEMBLED` hot payload lacks a separate formal field table | MiMo F-02 | deferred-with-owner | Slice 2 implementation/review must mirror the design row exactly and may add a table if implementation review finds ambiguity. Current event matrix and Section 23.1 list all required fields and validation rules. |
| `ProjectorMetadata.purpose` values are not inline in the table row | MiMo F-03 | rejected-with-reason | The values are listed in the same design section; duplicating them inside the row is optional and not necessary for implementation readiness. |
| Retry/replay/resume to kind mapping lacks examples | DS F-002 | deferred-with-owner | Slice 2 implementation artifact must record the mapping examples used by code/tests. The design's split between kind and trigger reason is sufficient and non-overlapping. |
| Event matrix uses `run_id` in header and `host_run_id` in the new event row | DS F-003 | rejected-with-reason | This is a formatting mismatch, not a contract gap. The row intentionally uses `host_run_id` to distinguish parent Host run from compactor Engine run identity. |
| `projector_id` / `purpose` use "at least covers" wording | DS F-004 | deferred-with-owner | Slice 2 implementation must use closed enums for current values and require design.md updates for new values. This wording does not weaken the current contract. |
| `manifest_schema_version` concrete value is not specified | DS F-005 | deferred-with-owner | Slice 2 implementation must define the concrete version string and keep it aligned with the design-approved current version. |

## Residual Risks

- Provider-specific assistant `tool_calls` / `reasoning_content` remains conditional: if existing typed Engine contracts are insufficient, Slice 2 must emit `provider_specific_atom_deferred` rather than using raw provider bags.
- Manifest field expansion remains a review concern for Slice 1-4; reviewers must reject any hidden messages dump or unbounded prompt/material inline.
- Chunked evidence query text remains a Slice 5 focused test responsibility.

All residual risks have owners and do not block accepting Slice 0.

## Next Gate

Next gate: accepted Slice 0 commit.

After the accepted Slice 0 commit, phaseflow may dispatch Slice 1 durable tool-call request atoms. Slice 1-7 implementation must use `docs/host/design.md` as the stable contract source.
