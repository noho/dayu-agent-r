# WU-SEMANTIC-OWNERSHIP-01 / R12 plan re-review fix follow-up Controller validation

## 1. Gate identity

- Umbrella work unit: existing `WU-SEMANTIC-OWNERSHIP-01` remediation continuation.
- Internal remediation sub-WU: R12, `dayu-cli init` workflow.
- Gate: Controller validation after the accepted fixed-plan re-review findings and the
  Controller CURRENT-code contradiction follow-up.
- This is not a new WU and does not authorize implementation, staging, commit, push or PR.

## 2. Immutable validated inputs

| Input | Lines / bytes | SHA-256 |
|---|---:|---|
| final R12 plan | 608 / 71,044 | `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2` |
| AgentCodex rereview-fix/follow-up artifact | 211 / 19,852 | `861cedef54452173bfd5c05cf5cf5fb918fda030a271e66e51c49fb3fbc89ef3` |
| corrected AgentMiMo re-review | 249 / 17,394 | `a1812b6f7539ee252de27d01ad4a40382163dd7c5955cafe029720370f2aaac5` |
| corrected AgentDS re-review | 469 / 35,432 | `f08584c337d910663003ab8be39c42371b8b1cd27e02b19d3f1a9640711e9381` |
| Controller re-review adjudication | 133 / 9,055 | `1f5142be9a4e5468625719be760e90e93e48d9093c633901849b65ff76bcadc9` |

The Controller fully read the 596-line first follow-up result, found one direct
CURRENT-code contradiction, sent a same-task bounded correction, then read the final
608-line plan and 211-line AgentCodex artifact. Protected reviewer/adjudication inputs
did not change.

## 3. Direct contradiction and root-cause decision

The earlier prewarm plan was not executable under CURRENT owners:

- `dayu/service/host_assembly.py` SHA-256 is
  `54559d2ea0446316b4ff82bf66594dfaa5d7b75067d495f5d3558d2ea94bbe52`.
- Ordinary selection may consume scene model hints or the ordinary override.
- Compactor selection instead consumes only
  `execution_profile.compactor_baseline.model_id`, with no scene/run override.
- `ServiceAssemblyOverrides` has no compactor override.
- `dayu/config/execution_profiles.json` SHA-256 is
  `ca827749876c29be8dc1808219a4082cfe06ebf7930939f30d2d6cf2a9340a31`;
  all four profiles use `deepseek-v4-flash` for both run and compactor baselines.

Therefore a selected-pair-only secret mapping cannot satisfy full runtime assembly for
most non-DeepSeek choices. Adding the compactor secret, passing all environment values,
changing execution profiles, or adding a Service/Host override would cross the R12
owner boundary and contradict the adjudicated minimal-design goal.

The OLD SHA-locked `_run_init_prewarm` directly performs import-only warming. The
correct CURRENT projection is consequently the OLD tuple filtered to the two surviving
real user entry roots, in the original relative order:

```text
dayu.cli.commands.interactive
dayu.cli.commands.prompt
```

Their modules own the transitive import graph through `dayu.cli.session_execution` to
`dayu.service.entrypoint_runtime`. Init must not copy that graph into another list or
call its runtime functions.

## 4. Accepted finding closure

| Finding group | Final status | Controller evidence |
|---|---|---|
| `R12-RR-PF-01` resolved `ModelsConfig` truth | closed | plan requires current resolver output and success/failure inheritance tests; no duplicate resolver |
| `R12-RR-PF-02` real/test Scene catalog boundary | closed | exact 13 production manifests use existing Service discovery and one real catalog; exact three manual-smoke manifests remain test-owned |
| `R12-RR-PF-03` deterministic lock smoke | closed | parent-held real lock, public waiting notification, one/two real `Popen`, zero publish before release; no sleep/retry/test sentinel |
| `R12-RR-PF-04` POSIX/Windows current-process visibility | closed | injection occurs only after whole persistence batch succeeds; partial failure cannot inject or publish |
| prior `R12-RR-PF-04` runtime-assembly prewarm part | superseded and closed | direct CURRENT contradiction removed; exact-two-root import-only prewarm has no env/secret/runtime assembly contract |
| `R12-RR-PF-05` per-slice coverage | closed | S1/S2/S3 each has executable per-production-file `>=80%` commands using tests present in that slice |
| AgentDS `R12-RR-04` README scope candidate | rejected/no-fix retained | `dayu/config/README.md` already owns package defaults, overlay and init lifecycle |

Accepted/open before final re-review: `0`. Blocking product question: `0`.

## 5. Independent import-only smoke

Controller executed the CURRENT roots in an isolated process with
`PYTHONDONTWRITEBYTECODE=1`, a socket/connect fail-fast guard, a temporary workspace,
and environment/file snapshots. It verified:

- both exact roots import twice with stable module identity;
- `dayu.cli.session_execution` and `dayu.service.entrypoint_runtime` are loaded only
  through their normal transitive graph;
- deleted `dependency_setup`, `interactive_ui` and `commands.write` roots are absent;
- no network attempt occurred;
- the environment and temporary workspace tree remained byte-for-byte unchanged.

Result:

```text
PASS roots=interactive,prompt transitive=session_execution,entrypoint_runtime
env_unchanged workspace_unchanged network_guarded
```

This validates plan feasibility only; implementation tests remain mandatory in S3.

## 6. Scope and mechanical validation

- Plan and AgentCodex artifact no-index whitespace checks: expected exit `1` for new
  files, zero diagnostic bytes.
- `git diff --check`: exit `0`.
- Staged tree: empty.
- No production, tests, README, design or workflow file was changed by this plan gate.
- No Issue 142/151/175/177/178 implementation, Web/WeChat/render work, Topic 8 change,
  Topic 9 authorization framework, compatibility branch, fallback or test shim entered
  the plan.

## 7. Verdict and next gate

Verdict:

```text
PASS / READY_FOR_FINAL_DUAL_COMPLETE_PLAN_REREVIEW
```

The final immutable review target is the 608-line plan with SHA-256
`69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`.
AgentMiMo and AgentDS must each perform a new complete independent plan re-review,
including the corrected import-only prewarm boundary. A single PASS does not authorize
implementation. Any new accepted finding returns to AgentCodex plan fix and complete
dual re-review.
