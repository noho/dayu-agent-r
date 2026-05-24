# PR 68 Post-Draft Full-Repo Review Controller Adjudication

## Gate

- Gate: post `draft-PR-pass` appended full-repo review
- PR: https://github.com/noho/dayu-agent-r/pull/68
- Head: `feat/phase-12-5-conversation-memory-optimize` @ `53a6d13`
- Review artifacts:
  - `docs/reviews/pr-68-post-draft-fullrepo-review-mimo-20260524.md`
  - `docs/reviews/pr-68-post-draft-fullrepo-review-ds-20260524.md`

## Verdict

Controller verdict: post-draft full-repo fix gate required.

Both reviewers returned `PASS_WITH_FINDINGS`. The review did not identify a broad correctness failure in the branch,
but it did identify one blocking test-coverage gap in a production-critical memory repair path and one direct
AGENTS.md re-export violation. Several compact-quality findings are low-risk and directly affect P12.6 compaction
correctness, so they are accepted into the fix gate.

## Accepted For Fix

### A1: `memory_repair.py` has no direct tests

- Source: MiMo Finding 13.
- Decision: accepted, blocking for this appended review loop.
- Reason: memory projection rebuild/catch-up is a Host startup recovery and admission critical path; a zero-test module
  leaves batch loop termination, cursor tracking, and failure handling unprotected.
- Required fix: add `tests/host/test_memory_repair.py` covering empty rebuild, cursor catch-up, batch termination,
  failure counting, and port delegation.

### A2: `ToolBundleSourceKind` / `ToolBundleSourceRef` compatibility re-export

- Source: DS Finding 2.
- Decision: accepted.
- Reason: the project explicitly forbids compatibility re-exports; the contracts module is the true owner for tool
  source refs.
- Required fix: remove the Host re-export and update callers/tests to import from `dayu.contracts.tool_source`.

### A3: compaction semantic repair disabled by default

- Source: MiMo Finding 2.
- Decision: accepted for minimal fix.
- Reason: `max_compaction_attempts_per_operation=1` means quality-check rejection cannot use the existing repair loop.
  P12.6 compaction quality guardrails are intentionally strict; without at least one repair pass, recoverable LLM
  omissions become hard failures.
- Required fix: raise the default to allow one repair attempt, or document and test a stronger design reason if not.

### A4: open-question quality check rejects legitimate empty / clear outcomes

- Source: MiMo Finding 3 and DS Finding 7.
- Decision: accepted.
- Reason: compaction should not force LLMs to fabricate open questions when no original open questions remain, and an
  evidence-supported `CLEAR` patch is a legitimate way to resolve them.
- Required fix: make the quality check distinguish original open-question presence from candidate retention, and allow
  evidence-supported clear semantics. Add focused tests.

### A5: multi-pass compaction merge overstates preserved refs

- Source: DS Finding 8.
- Decision: accepted.
- Reason: merged candidates should report refs actually preserved by passes, not all refs in the request.
- Required fix: merge preserved canonical evidence refs and evidence-backed fact refs from pass candidates, with tests.

### A6: `_summary_pretends_evidence_backed_fact` missing test coverage

- Source: MiMo Finding 15.
- Decision: accepted.
- Reason: the branch just hardened evidence-backed fact guardrails; the untested preserved-ref-subset rejection path
  should be covered.
- Required fix: add direct quality-check test.

### A7: `tool_runtime_schema_projection.py` has no functional tests

- Source: MiMo Finding 16.
- Decision: accepted.
- Reason: reserved-name and duplicate-tool-name rejection protects ToolRuntime schema correctness and is cheap to test.
- Required fix: add direct tests for valid projection, duplicate definitions, and reserved-name conflicts.

### A8: `tool_truncation.py` has no direct tests

- Source: MiMo Finding 17.
- Decision: accepted.
- Reason: runtime tool truncation is a shared safety mechanism; boundary tests reduce regression risk.
- Required fix: add direct runtime tests for no truncation, exact threshold, truncation, empty input, and multibyte text.

### A9: after-commit callback secondary errors are not logged

- Source: MiMo Finding 1.
- Decision: accepted if the fix is local and low risk.
- Reason: preserving the first exception while logging later callback failures improves diagnostics without changing
  transaction semantics.
- Required fix: log secondary callback failures and add a focused test, or document direct evidence that existing
  behavior is intentionally silent.

## Deferred / Residual

- DS Finding 1 test private-symbol coupling: real maintainability concern, but broad test architecture work. Owner:
  tests maintainers; destination: test-boundary hardening.
- DS Finding 3 God object file sizes: real structural debt, not suitable for a post-draft bugfix loop. Owner: Host
  architecture; destination: module decomposition phase.
- DS Finding 4 durable `HostApiError` dependency: real layering smell within Host, defer to durable error taxonomy work.
- DS Finding 5 ToolRuntime cancellation cleanup / fast path: production hardening, defer unless later evidence shows a
  concrete leak in current workflow.
- DS Finding 6 duplicate governance / cursor persistence across Attempt: design-level state ownership work, defer to
  ToolRuntime run-local state phase.
- DS Finding 9 cancellation vs Engine event race: production hardening, defer with owner Host lifecycle.
- MiMo Finding 4 Host close terminal facts: rejected as blocking because current docs intentionally rely on recovery
  scanner after close; keep as lifecycle residual.
- MiMo Finding 5 `WAITING_FOR_LANE` external cancellation orphan: defer to scheduler cancellation hardening.
- Low findings from both reviews: defer as performance / diagnostics / cleanup residuals unless touched by accepted
  fixes.

## Next Step

Route AgentCodex for a post-draft full-repo fix gate covering A1-A9. The worker must write
`docs/reviews/pr-68-post-draft-fullrepo-fix-codex-20260524.md`, update tests/docs as triggered, run focused tests,
full tests if feasible, pyright, and diff check, then stop without commit or push.
