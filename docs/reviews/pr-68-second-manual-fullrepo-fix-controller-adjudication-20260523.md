# PR 68 second manual full-repo review repair controller adjudication

## Scope

- Review inputs:
  - `docs/reviews/repo-review-20260523-211835.md`
  - `docs/reviews/repo-review-20260523-211917.md`
- Fix artifact:
  - `docs/reviews/pr-68-second-manual-fullrepo-fix-codex-20260523.md`
- Re-review artifacts:
  - `docs/reviews/pr-68-second-manual-fullrepo-fix-rereview-mimo-20260523.md`
  - `docs/reviews/pr-68-second-manual-fullrepo-fix-rereview-ds-20260523.md`

## Controller Decision

Verdict: PASS.

The second manual full-repo review repair closes the accepted PR 68 findings and both independent re-review agents returned PASS.

## Accepted Findings

- Public tool wiring smoke failure: accepted because the test suite had one reproducible failure. Controller verified the failure directly and accepted the worker's root-cause judgment that the old assertion was stale under the P12.5 contract: `TOOL_RESULT_ACCEPTED` does not directly materialize an `evidence_backed_fact`, so later Run input must not require raw tool-result event ids.
- Service assembly secret / path / tool discovery boundary tests: accepted because these are security-sensitive and configuration-sensitive fail-fast paths with low implementation risk.
- Compactor scene AgentPolicy required-field tests: accepted because compactor policy is production configuration, and missing required fields must fail before Host construction.
- Runtime `ToolsDiscovery._validate_provider_output` provider identity self-contained validation: accepted because a validation helper should not depend on an undocumented upstream precondition for the identity it uses in diagnostics and reports.

## Deferred Findings

- Dispatch owner / recovery missing-owner blind spot, promotion result semantics and startup timeout diagnostics: deferred to Host dispatch / recovery hardening because they require ownership contract review across admission, scheduler and recovery.
- `working_assumptions`, fact-candidate partial projection, raw assistant continuity, compaction retry defaults and budget estimation: deferred to Conversation Memory / Context Governance hardening because they affect memory semantics and compaction acceptance policy.
- `ensure_session` idempotency, projection checkpoint CAS and memory snapshot CAS: deferred to durable contract hardening because they affect durable API semantics and projection ownership.
- Helper deduplication, secret-redaction deduplication, JSON helper consolidation, token estimator consolidation, filelock warning and module decomposition findings: deferred to cleanup / production hardening owners because they are maintainability improvements rather than current PR correctness blockers.
- The previously reported steer replay failure was rejected as current blocker because controller reran `tests/host/test_public_steer.py::test_steer_replays_same_client_request_id_idempotently` and it passed.

## Validation

Controller reran:

```bash
source .venv/bin/activate && pytest tests/host/test_public_tool_wiring_smoke.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py -q
```

Result: 36 passed.

```bash
source .venv/bin/activate && pyright dayu tests
```

Result: 0 errors, 0 warnings, 0 informations.

```bash
git diff --check
```

Result: passed.

## Residual Risk

- The public smoke test name changed; external scripts that target the old node id need to use `test_mock_tool_result_feeds_same_run_and_later_run_continuity`.
- Only the affected tests were rerun in this repair loop. The two independent re-reviews accepted this as sufficient for the scoped changes.
- Deferred dispatch / recovery, memory semantics and durable hardening items remain tracked in `docs/host/implementation-control.md`.
