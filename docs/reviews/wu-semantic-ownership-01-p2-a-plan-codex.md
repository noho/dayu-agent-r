# WU-SEMANTIC-OWNERSHIP-01 P2-A Plan Delivery - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-A CLI/service boundary consistency`
- Gate: plan generation only
- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-a-plan.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Source adjudication: `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`
- Non-goals preserved:
  - No production code changes.
  - No tests changed.
  - No commit.
  - Did not enter P2-B memory/test hardening.
  - Did not enter P2-C fallback prompt source-of-truth.
  - Did not alter P1-A / P1-B / P1-C accepted contracts.

## Preflight

- Branch: `phaseflow/host-issues-control`
- Existing dirty file before this task: `docs/host/issues-implementation-control.md`
- I only read the dirty control doc as current controller truth and did not modify it.

## Direct-evidence Root-cause Confirmation

| Finding | Current judgment | Evidence |
|---|---|---|
| DS 03 `session resume` imports private prompt/interactive helpers | accepted | `dayu/cli/commands/session.py:36-45` imports `_execute_*` / `_prepare_*` private helpers; `session.py:251-267` and `:275-289` call them. |
| DS 10 CLI duplicates Service missing RESULT fallback | partially accepted / updated | Service owns normal fallback through `dayu/service/fins_direct.py:477-510`, covered by `tests/service/test_fins_direct.py:499-515`. CLI still has downstream `_missing_result_event()` at `dayu/cli/commands/fins.py:899-923` and calls it from `:703-731`; this should become hard contract violation rather than CLI business fallback. |
| DS 11 HostApiError formatting / exit-code inconsistency | accepted | `session.py:150-154`, `:268-295`, `:331-336`, `:621-647` have session-local HostApiError mapping; `prompt.py:150-162` and `interactive.py:194-210` fall through generic Exception handling. |

## First-principles Judgment

P2-A motivation is valid and severity is correctly P2. The current issue is not durable truth corruption, but it does break command boundary ownership: CLI modules depend on each other's private implementation, Service RESULT guarantees can be masked by downstream CLI fallback, and Host structured errors have inconsistent user-visible projection.

The plan rejects a mechanical implementation that simply wraps old private functions or preserves CLI missing-result fallback for test compatibility. The owner boundary is:

- Service owns Host entrypoint protocol and Fins direct stream RESULT contract.
- CLI owns user-facing command execution composition, stderr formatting, signal/display behavior, and process exit code.
- Host owns `HostApiError` facts but not CLI presentation.

## Plan Summary

The plan defines three implementation slices:

- S1: create a real public CLI existing-session execution helper and migrate prompt / interactive / session to it.
- S2: delete CLI Fins missing-result business fallback and treat missing terminal result after Service stream exhaustion as contract violation.
- S3: centralize CLI HostApiError formatting and exit-code mapping across prompt / interactive / session.

This keeps the work within the control doc's 1-3 slice guideline for small cross-module cleanup.

## README Decision

No README update was made for this plan-only gate. The plan explicitly records future README triggers:

- root `README.md` if CLI user-visible output / exit code / workflow changes need documentation.
- `dayu/service/README.md` if Service public contract changes.
- `tests/README.md` if test responsibility descriptions change.
- `dayu/README.md` if layering relationship documentation changes.

## Validation

No production tests or pyright were run because this gate only creates planning artifacts and does not modify code or tests.

Required implementation validation is recorded in the plan:

```bash
source .venv/bin/activate && pytest tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py
source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_fins_direct.py
source .venv/bin/activate && pyright
git diff --check
```

Plan artifact whitespace validation was run after writing artifacts:

```bash
git diff --check
git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-p2-a-plan.md
git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-p2-a-plan-codex.md
```

Result: `git diff --check` passed with no output. The two `--no-index --check` commands exited `1` because `/dev/null` differs from each new artifact, but produced no whitespace diagnostics.

## Residual Risks

- The exact shape of the CLI public session execution helper should be reviewed carefully in plan review to avoid creating a facade that only forwards to old private functions.
- HostApiError exit-code policy should remain conservative: only explicit user selector `NOT_FOUND` maps to usage error; operation/runtime conflicts remain failure unless evidence proves they are input validation.
- Fins CLI contract violation text is user-visible. If root README currently promises a specific Fins failure message for missing RESULT, implementation must update docs or preserve only documented behavior that remains true.
