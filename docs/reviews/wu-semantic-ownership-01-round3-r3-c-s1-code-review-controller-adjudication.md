# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S1 Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Slice: `S1 Storage Identity, Commit Point, And Local Durability`
- Gate: code review adjudication
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-ds.md`

## Review Summary

| Reviewer | Status | Findings | Blocking questions |
| --- | --- | ---: | ---: |
| AgentMiMo | `pass-with-risks` | 2 | 0 |
| AgentDS | `pass` | 0 | 0 |

Both reviewers agree S1 stays inside the accepted S1 file scope and does not implement tool-security policy. AgentDS reports no findings. AgentMiMo reports two low-severity findings. Controller accepts both as required fix items because this umbrella WU operates under the current rule that all findings in the batch are fixed before reporting.

## Accepted Findings

### R3-C-S1-CR-F01 — `_replace_directory` should fail closed if target already exists

- Source: AgentMiMo finding 001.
- Severity: low.
- Decision: accepted.
- Reason: `_replace_directory()` is storage-owner infrastructure for commit/recovery physical state. Its docstring states the target is not supposed to exist. Adding a defensive fail-closed check aligns implementation with that contract and prevents a future internal caller from accidentally relying on platform-dependent `os.replace()` behavior for existing files or empty directories.
- Required fix: before `os.replace(source, target)`, reject an existing target path. The check should also reject a symlink target even if broken. Add an owner-level test proving `_replace_directory()` raises and leaves source/target unchanged when target already exists.

### R3-C-S1-CR-F02 — direct `_normalize_object_key` test coverage

- Source: AgentMiMo finding 002.
- Severity: low.
- Decision: accepted.
- Reason: Current object-key behavior is covered through `LocalFileStore`, but the new owner helper is a semantic contract. Direct tests make the owner-level signal precise and reduce the chance that future `LocalFileStore` changes hide owner drift.
- Required fix: import `_normalize_object_key` in `tests/fins/test_fins_storage_atomicity.py` and add direct parameterized tests for valid normalization and invalid values at the owner helper boundary.

## Rejected Findings

None.

## Tool-Security Decision

No tool-security fix is authorized or required. Both reviewers verified S1 did not add upload allowlists, file authority policy, URL/TLS/redirect/SSRF provenance, remote byte budgets, or LLM-facing security schema/prompt/tool schema changes. Storage `local://` containment remains classified as storage identity, not upload security.

## Next Gate

AgentCodex must fix `R3-C-S1-CR-F01` and `R3-C-S1-CR-F02`, update focused tests as needed, rerun:

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Then write `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-fix-codex.md`.
