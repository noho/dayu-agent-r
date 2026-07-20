# WU-SEMANTIC-OWNERSHIP-01 / R04-S1 Controller re-validation

## 1. Gate identity and verdict

- Umbrella WU: existing `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation; this is not a new WU or slice.
- Remediation sub-WU: R04 `awaiting provider resolution composition`, unique atomic S1.
- Accepted plan: `983070dd1d56490d23529970960349a3df3e9787`.
- Implementation base and current HEAD: `a4ffd7641c8f114e987972d77572c2c2b4a8202f`; HEAD did not move.
- Original validation: `docs/reviews/wu-semantic-ownership-01-r04-s1-controller-validation.md`.
- Fix handoff: `docs/reviews/wu-semantic-ownership-01-r04-s1-controller-validation-fix-codex.md`.
- Controller verdict: **PASS / READY_FOR_DUAL_CODE_REVIEW**.

`R04-S1-CV-F01` is closed. The Fins awaiting runtime and typed provider metadata are now required construction state, every existing derived discovery consumer preserves that owner-produced state with `dataclasses.replace(...)`, and an owner-level regression proves that replacing the public tool bundle preserves Host wait binding, activation registry, poll registry, and runtime policy composition.

## 2. Finding closure evidence

### R04-S1-CV-F01 — closed

Controller independently inspected the final source and verified:

1. `ServiceDiscoveredTools.fins_awaiting_runtime` and `_fins_awaiting_providers` have no defaults. The discovery owner must explicitly supply `None` / empty tuple for the valid no-provider case, so omission is distinct from an owner-produced empty fact.
2. A repository-wide Python scan finds exactly one direct `ServiceDiscoveredTools(...)` construction, in `dayu/service/host_assembly.py` at the discovery owner.
3. The four authorized derived consumers use `dataclasses.replace(...)` on the owner-produced instance. They do not access the private metadata field/type, reparse `effective_provider_configs`, read raw `awaiting_resolution_mode`, or reconstruct the dataclass.
4. `test_replacing_discovered_bundle_preserves_host_wait_composition` performs real packaged discovery, replaces only the public tool bundle, composes both results, and compares the public Host policy plus all three Fins bindings, activation adapter, and poll adapter through registry resolution. It does not assert a private field.
5. The fix handoff records that, after the required signature was introduced but before the four consumers were corrected, full pyright reported exactly those four constructor omissions. Final full pyright is clean, so future omissions fail at development time.

The root cause was therefore corrected at the Service discovery-result construction contract, not through a downstream fallback, raw-config reparse, compatibility shim, or fixture-only patch.

## 3. Independent validation

### 3.1 Focused regression

Controller reran the new owner regression, combined tool acceptance, and both affected public-smoke assembly suites:

```text
36 passed, 3 warnings in 4.48s
```

The warnings are the existing edgar dependency deprecation warnings.

### 3.2 Accepted-plan affected matrix and coverage

Controller reran the accepted-plan seventeen-target session with the new regression included:

```text
509 passed, 3 warnings in 21.08s
```

Coverage JSON: `workspace/tmp/r04-controller-revalidation-coverage.json`.

| modified production Python file | coverage |
|---|---:|
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 85.54% |
| `dayu/fins/tools/download_provider.py` | 100% |
| `dayu/fins/tools/preprocess_provider.py` | 100% |
| `dayu/fins/tools/upload_provider.py` | 100% |
| `dayu/host/wait_adapter.py` | 90.81% |
| `dayu/runtime/config_loader.py` | 96.31% |
| `dayu/service/entrypoint_runtime.py` | 88.27% |
| `dayu/service/fins_wait_adapter.py` | 94.57% |
| `dayu/service/host_assembly.py` | 95.03% |

Every modified production Python file remains above the required per-file 80% threshold.

### 3.3 Type, lint, whitespace, propagation, and scope

- `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`.
- Ruff `F401,F841` over the NUL-delimited tracked changed Python set: pass.
- `git diff --check`: pass.
- Old entrypoint/scene policy helpers and no-argument Host policy construction: zero production matches.
- Ten former Host deployment-default constants: zero production matches.
- `awaiting_resolution_mode` propagation is limited to packaged config, the Fins owner/parser/direct providers, Service owner routing/presence rejection, and owner tests.
- Prompt assets and `execution_profiles.json` contain neither wait poller policy nor awaiting resolution mode.
- The broad runtime reverse-import scan sees only the existing architecture-prohibition prose in `dayu/runtime/__init__.py`; the anchored Python import-statement scan has zero matches.
- Added-line deferred-scope scan over product/tests/smokes for authorization, permission, process isolation, observation timeout, and lost-outcome implementation: zero matches.
- The four newly authorized consumers have zero added-line matches for private typed metadata, effective provider config reparsing, raw mode parsing, or direct discovery reconstruction.
- Final changed files remain within the accepted S1 allowlist plus the Controller-authorized F01 consumer/artifact/control expansion.

### 3.4 Packaged public Host smoke

Controller ran:

```text
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r04-controller-revalidation-smoke
```

Result: pass. It reproduced typed `poll/manual/callback`, the complete twelve-field runtime snapshot, prompt/interactive equality, manual/no-provider/provider-disabled/runtime-disabled no-poller cases, callback pre-open failure, and the production public Host path `not_ready=1 -> ready=1 -> SUCCEEDED`. It used local deterministic execution/observation boundaries and did not access external LLMs, networks, secrets, or raw credential-bearing config.

## 4. README and deferred boundaries

The existing five README updates remain responsibility-owned and accurate. `tests/README.md` additionally records the derived-discovery composition invariant introduced by F01. Root `README.md` and `dayu/README.md` remain correctly unchanged.

Callback transport, external-network smoke, Host restart recovery, R05 observation timeout/LOST behavior, Issue 175 process isolation, and unified tool authorization remain outside R04-S1. No deferred owner was implemented, and no existing security mechanism was weakened.

## 5. Next gate

R04-S1 is authorized only for concurrent AgentMiMo / AgentDS **complete code review** of the final combined implementation and F01 fix. Reviewers must inspect the full code/test/config/README diff and all implementation/validation evidence, not only the narrow fix. No accepted implementation commit, R04 aggregate gate, R05 work, push, PR, callback transport, Issue 175, Host public API/open_host change, or unified authorization design is yet authorized.
