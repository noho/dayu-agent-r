# WU-SEMANTIC-OWNERSHIP-01 / R12 fixed-plan re-review Controller adjudication

## 1. Immutable target and corrected review artifacts

- Fixed plan target: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`, 558 lines / 56,459 bytes /
  SHA-256 `37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b`.
- AgentMiMo corrected complete re-review:
  `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-rereview-mimo.md`, 249 lines / 17,394 bytes /
  SHA-256 `a1812b6f7539ee252de27d01ad4a40382163dd7c5955cafe029720370f2aaac5`, verdict
  `PASS_WITH_OBSERVATIONS`, one LOW candidate.
- AgentDS corrected complete re-review:
  `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-rereview-ds.md`, 469 lines / 35,432 bytes /
  SHA-256 `f08584c337d910663003ab8be39c42371b8b1cd27e02b19d3f1a9640711e9381`, verdict
  `PASS_WITH_FINDINGS`, two MEDIUM and three LOW candidates.

Both reviewers completely read and matched the same 558-line target, and both independently close `R12-PF-01..12`. MiMo's
initial global-Ruff observation was factually wrong because it did not activate `.venv`; the same-task correction removes it and
records the specified environment as Ruff `0.15.11`, 144 findings and raw stdout SHA
`051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`. Both reviewers also corrected their metrics for the
114-line plan-fix Controller validation. Only their final hashes above enter this adjudication.

## 2. Controller evidence and decision principles

Controller accepts plan changes where current typed contracts leave more than one materially different implementation path. It
does not accept timing-luck tests, synthetic production tool truth, deferring an accepted coverage gate, or treating README
triggers as an exclusive prohibition on updating an in-scope manual.

Direct evidence used for the new candidates:

- `ScenePrepareRequest.available_tools` is required and `SceneToolCatalog` has no implicit provider discovery.
- Thirteen package runtime manifests use real `none`/tag-select tool semantics; three exact
  `smoke_host_public_*` manifests select the test-only `manual-smoke` tag. Required context slots across the package set are
  exactly `current_time` and `fins_default_subject`.
- Current Service assembly obtains the real catalog only through
  `discover_service_tools(assemble_effective_tool_provider_configs(...))` and
  `SceneToolCatalog.from_tool_bundle(...)`.
- `EntrypointRuntimeRequest.env` is required and Host assembly consumes it only to resolve selected ordinary/compactor model
  `api_key_ref` placeholders. Passing all of `os.environ` is unnecessary for prewarm.
- `dayu/config/README.md` explicitly owns package defaults, workspace config overlay and current `dayu-cli init` behavior; R12
  changes exactly that documented behavior.
- AGENTS.md requires affected code to meet per-file coverage target `>=80%` after modification; an absent S3 smoke file cannot
  be part of an S2 command.

No design contradiction or user/product question exists. All accepted changes remain in the R12 plan owner and do not authorize
implementation.

## 3. Accepted plan-fix groups

### `R12-RR-PF-01` — resolved model records are the static-validation truth

Accept AgentMiMo `FINDING-01`. The plan must say that each of the 13 ordinary/thinking IDs is loaded through the current
`ModelsConfig` extends resolver and that `provider`/`api_key_ref` are compared on the resolved records. Tests must include a
thinking child that inherits those fields and a mismatch after resolution. Do not raw-check inherited fields or create another
extends resolver.

### `R12-RR-PF-02` — pre-publish scene validation needs an exact real/test catalog boundary

Accept AgentDS `R12-RR-01`, extended to the equally required context-slot input. The plan must distinguish:

1. the thirteen non-`smoke_host_public_*` package runtime manifests, which pre-publish validation prepares using the real
   staging `RuntimeConfig`, existing Service effective-provider assembly/discovery, a
   `SceneToolCatalog.from_tool_bundle(...)` projection, and explicit empty-string values for the only two locked required slots
   `current_time` / `fins_default_subject`; and
2. the three exact `smoke_host_public_*` test manifests, whose `manual-smoke` selection is validated by test-owned explicit
   catalog fixtures and must not be injected into production discovery or treated as a real product tool.

All 16 model projections remain validated. Production code must not use an empty catalog, duplicate the manifest parser, invent
a synthetic product provider, skip real tag selection, or loosen `allow_empty`. If the locked package manifest/slot/tag set
drifts before implementation, stop for Controller re-adjudication.

### `R12-RR-PF-03` — real lock-contention smoke uses observable coordination, not timing luck

Accept AgentDS `R12-RR-02` narrowly. The parent test harness acquires the real workspace lock first, starts one or two real
`dayu-cli init` subprocesses with complete deterministic input, waits for each process's already-required user-visible
"waiting for this workspace lock" notification, asserts that config has not published, and only then releases the parent lock.
The harness uses a bounded subprocess/read timeout only to fail a hung test; production `file_lock(..., timeout_seconds=None)`
remains unchanged. Both queued publishers must exit successfully in serialized order and the final state must load through the
real `ConfigLoader`.

Reject DS's alternatives of a finite production lock timeout, `pytest.mark.flaky`, success ratios/retries, sleeps, process kill,
or new production-only sentinel/test shim. The public waiting notification is already an accepted CLI behavior, not a test-only
protocol.

### `R12-RR-PF-04` — prewarm env projection has one bounded source

Accept AgentDS `R12-RR-03`. After successful POSIX or Windows persistence, newly stored entries must also be available to the
current init process; partial persistence failure still prevents injection and publish. For prewarm, `commands/init.py` builds a
new private mapping containing only the selected model pair's catalog-owned required env name when non-null, reading the
non-empty value from the current process environment. Ollama receives an empty mapping. The five optional integrations are not
Host model-header inputs and are not forwarded merely because they exist. Never pass the entire environment, a secret typed
entry object, or a value in output/artifacts. Tests inspect mapping keys and invocation behavior without recording values.

If the resolved ordinary/compactor models require a different env ref from the selected pair at implementation entry, that is a
source-contract drift and must stop rather than trigger env-name inference or fallback.

### `R12-RR-PF-05` — coverage is executable at every cumulative slice

Accept AgentDS `R12-RR-05` narrowly. Add exact S1, S2 and S3 per-file coverage commands using only tests present in that slice.
Every production file first changed or added in S1/S2 must already meet `>=80%` before its slice review; S3 reruns the cumulative
final profile and may add smoke coverage but cannot repair or defer a failed earlier gate. In particular, the S2
`commands/init.py` command cannot name the not-yet-created `test_init_smoke.py`.

Reject the suggested option to record an S2 coverage gap and close it in S3. That conflicts with the user's per-change gate and
AGENTS.md.

## 4. Rejected/no-fix candidate

Reject AgentDS `R12-RR-04`. README update triggers state when a code-path change requires checking a manual; they are not an
exclusive authorization list. The existing `dayu/config/README.md` already documents package defaults, workspace overlay and
the old `init` failure/overwrite workflow. R12 directly replaces that user-visible config lifecycle, and plan S3 already limits
the update to current owner/state semantics. Keeping the README in scope is correct and needs no additional product decision.

## 5. Finding ledger and next gate

| Category | Count | Status |
|---|---:|---|
| original `R12-PF-01..12` | 12 | closed by both complete re-reviews |
| accepted new plan-fix groups | 5 | open pending AgentCodex plan-only fix |
| rejected/no-fix new candidate | 1 | closed with reason |
| blocker/design contradiction | 0 | none |
| unclassified residual | 0 | none |

AgentCodex must update only the fixed plan and add
`docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-rereview-fix-codex.md`. The artifact must show exact before/after
evidence for all five groups and retained rejection boundaries. No production, test, README, design, control, earlier artifact,
stage or commit change is authorized.

After Controller validates the new immutable plan, AgentMiMo and AgentDS must again perform concurrent complete re-review. A
single PASS or the reviewers' claim that implementation could proceed does not bypass this mandatory fix/re-review loop.

## 6. Verdict

`PLAN_FIX_REQUIRED / 5 ACCEPTED GROUPS / ZERO BLOCKER`
