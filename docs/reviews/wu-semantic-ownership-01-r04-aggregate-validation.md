# WU-SEMANTIC-OWNERSHIP-01 / R04 aggregate Controller validation

## 1. Identity and verdict

- Active work unit: existing umbrella `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation.
- Internal remediation sub-WU: R04 `awaiting provider resolution composition`.
- Accepted plan commit: `983070dd1d56490d23529970960349a3df3e9787`.
- Accepted R04-S1 implementation commit: `9e349ac4`.
- Validation HEAD: `c2a40929b0221fa3cbbe394ce5c25d1d49a766cb` (control-only aggregate transition after the accepted implementation).
- Controller verdict: **PASS / READY_FOR_DUAL_AGGREGATE_DEEPREVIEW**.

R04 has one deliberately atomic implementation slice, but its aggregate boundary spans packaged provider config, Fins parser/direct providers, layer-neutral runtime config, Service typed discovery/composition, Host policy execution, public CLI entrypoint assembly, derived discovery consumers, tests, README, and real public Host behavior. This validation re-ran that combined contract from the accepted commit state; it did not merely reuse the pre-commit slice result.

## 2. Combined contract validation

Controller verified the following single-source chain as a whole:

1. Packaged Fins awaiting providers explicitly own strict `poll/manual/callback` mode input; the shared Fins parser is the only parser and all three direct providers validate before runtime creation.
2. Packaged `host_runtime.json` owns the exact required twelve-field wait-poller deployment snapshot; ConfigLoader performs exact-shape, strict finite-positive typed parsing without Host/Fins knowledge.
3. Host policy/value/runtime constructors have no deployment defaults, no no-argument construction, and no `None` fallback.
4. Service uses the typed provider collection plus typed runtime snapshot to compose binding, activation registry, poll registry, and `OpenHostOptions`; scene selection and entrypoint type do not own poller policy.
5. Any active callback fails before Host open because the authenticated callback transport owner is absent; manual remains resumable without a background poller; poll starts only with the explicit enabled policy and registry.
6. `ServiceDiscoveredTools` requires both Fins awaiting state fields. The discovery owner is the unique direct constructor, and all derived consumers preserve the owner fact through `dataclasses.replace(...)`.
7. Public packaged composition reaches the production Host poller and durable wait path, observes one not-ready and one ready result, and terminates `SUCCEEDED` with matching outbox truth.

`R04-S1-CV-F01` remains closed at the aggregate boundary. No downstream fallback, raw mode reparse, second LLM-safe normalization, compatibility shim, or scene/execution-profile bridge exists.

## 3. Tests and per-file coverage

At the accepted commit state Controller reran the accepted-plan complete seventeen-target matrix:

```text
509 passed, 3 warnings in 23.10s
```

The three warnings are existing edgar dependency deprecation warnings. Coverage artifact: `workspace/tmp/r04-aggregate-validation-coverage.json`.

| modified production Python file | coverage |
|---|---:|
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 85.54% |
| `dayu/fins/tools/download_provider.py` | 100% |
| `dayu/fins/tools/preprocess_provider.py` | 100% |
| `dayu/fins/tools/upload_provider.py` | 100% |
| `dayu/host/wait_adapter.py` | 90.41% |
| `dayu/runtime/config_loader.py` | 96.31% |
| `dayu/service/entrypoint_runtime.py` | 88.27% |
| `dayu/service/fins_wait_adapter.py` | 94.57% |
| `dayu/service/host_assembly.py` | 95.03% |

Every modified production Python file satisfies the per-file `>=80%` gate.

## 4. Type, lint, source, security, and scope gates

- Full `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`.
- Ruff `F401,F841` over every Python path changed by `f7006a80..9e349ac4`: pass.
- `git diff --check`: pass; worktree was clean before creating this artifact.
- Repository Python constructor scan finds one direct `ServiceDiscoveredTools(...)`, at the Service discovery owner.
- Old scene/entrypoint policy helpers and no-argument `WaitPollerRuntimePolicy()` construction: zero production matches.
- Ten removed Host deployment-default constants: zero production matches.
- Prompt assets and `execution_profiles.json` contain neither wait poller policy nor awaiting resolution mode.
- Anchored runtime reverse-import scan: zero matches.
- Added-line scan across `f7006a80..9e349ac4` for authorization, permission, process isolation, observation timeout, and lost-outcome implementation: zero matches.

The implementation does not modify Engine, Host public API/open_host, callback transport, R05 state machine, Issue 175 process isolation, Issue 142/151/177/178, permission schema, or unified tool authorization. Existing identity, allowed paths, Web defenses, containment/symlink protections, DNS/peer proof, resource budgets, atomic write, cancellation, durable wait, and process fencing remain intact.

## 5. Packaged public Host smoke

Controller ran:

```text
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r04-aggregate-validation-smoke
```

Result: pass. The smoke reported typed modes `poll/manual/callback`, all twelve runtime-policy fields, prompt/interactive equality, callback pre-open failure, no poller for manual/no-provider/provider-disabled/runtime-disabled cases, and the public Host terminal path:

```text
observed_waiting=true
not_ready=1
ready=1
terminal=SUCCEEDED
outbox_terminal_match=true
```

The smoke used local deterministic execution/observation boundaries and did not access external LLMs, networks, secrets, or raw credential-bearing config.

## 6. Review ledger and residual ownership

- `R04-S1-CV-F01`: closed.
- Current accepted R04 finding: zero.
- DS observation-timeout/LOST evidence: real but explicitly deferred to mandatory R05; it is not accepted as correct umbrella-final behavior.
- DS hypothetical provider-fragment collision: rejected-with-reason because it lacks current evidence and would replace the accepted existing identity contract with speculative framework design.
- Callback transport: existing WU-WAIT-01 / Issue 89 owner; current fail-closed behavior is correct.
- Issue 175 process isolation and all other named deferred Issues: unchanged and outside R04.

There is no unowned current R04 residual and no blocking question.

## 7. Next gate

Next gate is concurrent AgentMiMo / AgentDS **aggregate deepreview** of the complete R04 accepted implementation, evidence chain, configuration-to-public-Host behavior, security/deferred boundaries, and review adjudication. Any new accepted aggregate finding must return to AgentCodex fix, Controller validation, and concurrent aggregate re-review. R04 completion, R05 entry, push, and PR remain unauthorized until aggregate deepreview is finally accepted.
