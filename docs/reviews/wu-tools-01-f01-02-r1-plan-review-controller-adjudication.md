# WU-TOOLS-01-F01-02-R1 Plan Review Controller Adjudication

## Metadata

- Work unit: `WU-TOOLS-01-F01-02-R1`
- Gate: plan review
- Timestamp: `2026-06-21T18:15:05+0800`
- Plan artifact: `docs/host/wu-tools-01-f01-02-r1-plan.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260621-180827.md` by AgentDS
  - `docs/reviews/plan-review-20260621-181350.md` by AgentMiMo

## Review Summary

Both reviewers concluded `pass-with-risks`. The plan correctly identifies the submit-before-accept root cause and keeps activation inside Host / ToolRuntime and Fins runtime boundaries without changing Engine or LLM-facing schemas. Both reviewers found the same material gap: activation failure handling must guarantee that an accepted wait cannot remain permanently stuck in `WAITING` because the prepared observation stayed `PENDING`.

## Findings Adjudication

### C-F01 accepted

- Source findings:
  - AgentMiMo F01, high severity: activation exception guarantee gap.
  - AgentDS F1, medium severity: `activate_observation` and `cancel_observation` lock order not explicit.
- Decision: `accepted`
- Rationale: This is the core correctness risk after accepted wait. Host wait truth is already durable by the time activation runs; if the activation adapter throws before marking the Fins observation terminal, the poller can continue seeing `PENDING` and return `WaitPollNotReady` forever. The plan must explicitly require activation to use the same observation lock as cancellation and to guarantee terminal `FAILED` or `LOST` state before surfacing unexpected exceptions.
- Required plan fix:
  - Specify that `activate_observation(handle)` and `cancel_observation(handle)` coordinate through the same observation lock.
  - Specify that activation checks cancellation / terminal / submitted state and marks submitted under that lock before submit.
  - Specify that any activation failure path after accepted wait must ensure the observation reaches terminal `FAILED` or `LOST`; ToolRuntime catch is only a safety net, not the primary failure recording path.
  - Add validation for unexpected activation exception and cancel/activate race or equivalent deterministic test coverage.

### C-F02 accepted

- Source finding:
  - AgentDS F3, low severity: Slice 1 test harness extension not explicit.
- Decision: `accepted`
- Rationale: The implementation agent must update Host test fixtures to inject an activation registry / spy adapter; otherwise Slice 1 cannot prove activation call count or non-activation paths without guessing scope. This is a small plan clarity fix.
- Required plan fix:
  - In Slice 1 exact allowed changes, explicitly allow test fixture extension to inject `wait_activation_registry` and spy/stub activation adapters.

### C-F03 accepted

- Source findings:
  - AgentMiMo F03, low severity: prepared observation after accept rejection needs explicit behavior.
  - AgentDS F2, low severity: prepared observation cleanup gap on accept reject.
- Decision: `accepted`
- Rationale: The plan must be explicit so implementation does not invent a broad cleanup mechanism or leave an ambiguous obligation. Because the observation is process-local, has no wait record, and has not been activated, explicit best-effort cleanup or documented orphan semantics are both acceptable if scoped narrowly. The best current plan choice is to require no activation and either best-effort abandon via the prepared handle when available or a documented harmless process-local orphan if no safe cleanup path exists.
- Required plan fix:
  - Add accept rejected / timeout / stale execution behavior for prepared-but-unaccepted observations.
  - Avoid adding a durable cleanup ledger or public contract.
  - Keep cleanup best-effort and process-local, or explicitly document harmless orphan semantics with owner/destination if implementation cannot safely call abandon.

### C-F04 rejected-with-reason

- Source finding:
  - AgentMiMo F02, medium in heading but low in conclusion: unified activation registry alternative.
- Decision: `rejected-with-reason`
- Rationale: Extending `WaitAdapterBinding` with activation callback would broaden an existing Host binding contract and risks mixing wait selection metadata with executable provider behavior. The accepted plan's separate construction-time `WaitActivationRegistry` keyed by existing `WaitAdapterKey` keeps executable activation wiring internal and avoids changing Engine, LLM-facing schemas, or public wait contracts. This is the better minimal design for this WU.
- Required plan fix: none, except optionally note that the separate activation registry is an intentional boundary choice.

## Required Next Gate

Plan review does not pass directly to accepted plan commit. The next gate is plan fix by AgentCodex.

Expected fix artifact:

- `docs/reviews/wu-tools-01-f01-02-r1-plan-fix-codex.md`

The fix must edit only the plan artifact and add the fix artifact. It must not modify production code, tests, design docs, README, commit, push, PR, or enter implementation.

## Residual Risks

- Production poller scheduling / backoff / fencing / retry remains owned by GitHub Issue 90.
- External job physical cancel / revoke / abandon remains owned by GitHub Issue 92.
- Callback endpoint / auth / replay remains owned by GitHub Issue 89.
- Process-local observation loss on Host restart remains consistent with the current lightweight observation design and is owned by later wait hardening work where applicable.
