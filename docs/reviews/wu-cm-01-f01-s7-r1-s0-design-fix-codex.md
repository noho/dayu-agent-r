# WU-CM-01-F01-S7-R1-S0 Design Fix

## Scope

- Work unit: `WU-CM-01-F01-S7-R1`
- Gate: S7-R1-S0 design fix
- Review controller adjudication: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-controller-adjudication.md`
- MiMo review: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-mimo.md`
- DS review: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-ds.md`

## Changed Files

- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-fix-codex.md`

No production code, tests, red tests, README, commit, push, or PR action was changed or performed.

## Finding Coverage

| Accepted finding | Fix coverage |
|---|---|
| Section 4 / Section 8 evidence routing ambiguity | Clarified that `Verified Evidence and Facts` only owns verified / accepted memory facts and memory / fact pipeline accepted evidence material. Clarified that `Recent Evidence` owns recent-window fallback, wait-resume, or other evidence-like bounded material not accepted by memory / fact pipeline. Added an explicit no-double-render rule for the same evidence material. |
| `tool` role legality authority | Clarified the current authority: the current Engine message contract does not support ordinary RunInput historical evidence using `tool` role. Such historical evidence defaults into the system envelope until a future Engine contract work unit changes this. |
| Boundedness measurable sanity | Replaced the vague size sanity wording with a measurable assertion: `len(merged_system_content) <= sum(len(candidate_system_content)) + deterministic_header_separator_overhead`, with the overhead limited to fixed headers and separators. |
| Section title single source | Marked the §23 section table as the unique source for section titles, order, and Conversation Memory mapping. Updated §24 to reference §23 instead of repeating the full title list. |

## Validation

- Ran `git branch --show-current`: current branch is `phaseflow/wu-dur-obs-cm-closeout`.
- Ran `git status --short` before edits and confirmed unrelated dirty test files existed; this fix only touched the allowed files.
- Ran `git diff --check`: passed with no whitespace errors.

## README Decision

No README update is required for this gate. The change is a Host design clarification under `docs/host/design.md` and control-doc bookkeeping; it does not change user-facing commands, package-level developer guidance, test running conventions, configuration entry points, or stable README responsibilities.

## Next Gate

`docs/host/issues-implementation-control.md` now points to S7-R1-S0 design re-review before any production `run_input.py` implementation.
