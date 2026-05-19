# Host-owned compactor Slice 5 implementation artifact

## Gate / work unit

- Gate: implementation Slice 5
- Work unit: Host-owned LLM context compactor public opener contract
- Slice: Slice 5 smoke migration
- Approved plan: `docs/host/host-owned-compactor-plan.md`
- Design source of truth: `docs/host/design.md`
- Current accepted slice commit before this work: `7c2e7bd`
- Role: implementation worker only; did not start Gateflow controller flow.

## Changed files

- `utils/smoke_host_public_multiturn.py`
- `tests/host/test_public_compact_smoke.py`
- `docs/reviews/host-owned-compactor-implementation-slice5-codex.md`

`tests/host/public_smoke_support.py` was inspected but not modified.

## Implemented plan items

- Removed manual smoke caller-owned `DeepSeekContextCompactor`, compactor-only rejecting executor, thread wrapper, prompt construction, and candidate mapper.
- Removed public compact smoke caller-owned `_RealLLMContextCompactor`, compactor-only rejecting executor, thread wrapper, prompt construction, and candidate mapper.
- Preserved ordinary DeepSeek `RunnerSpec` / `RunnerCallOptions` construction used by normal run execution.
- Migrated manual smoke `OpenHostOptions` construction to `compactor_runner_baseline=CompactorRunnerBaseline(...)`, passing only runner spec, runner options, artifact root, and create-parent-dir flag.
- Kept public compact smoke on `CompactorRunnerBaseline(...)` and strengthened assertions toward public / observable evidence:
  - first run terminal succeeded;
  - second run terminal succeeded;
  - terminal events align with the public session and accepted run ids;
  - compact artifact root gains a new artifact after the run window;
  - artifact content has Host-owned `llm-compact:{run_id}` candidate id for the compacted run;
  - artifact input snapshot retains a non-empty current user input ref;
  - second run continuity remains non-empty.
- Manual smoke stdout no longer prints compactor call count or last summary. It prints compact artifact root, file count, and bounded artifact paths only.
- Provider skip logic remains env-gated through existing public smoke helpers; no network pytest is required by default.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q -rs`
  - Result: passed, `1 passed in 5.77s`
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
  - Result: passed, argparse help printed successfully.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed, no whitespace errors.

## Docs decision

README files were not edited. Slice 6 owns README synchronization per the approved plan and this handoff's explicit scope constraint.

## Residual risks / uncovered areas

- Owner / destination: Slice 6 docs.
  - README and developer manual text may still mention older Service-side compactor injection until Slice 6 updates docs.
- Owner / destination: current provider smoke environment.
  - Real provider behavior is still externally dependent when the provider API key is present; existing skip helpers handle unavailable, quota, rate-limit, and provider terminal failure cases.
- Owner / destination: Host core / already accepted earlier slices.
  - This slice did not change Host core construction or compaction operation behavior. If future smoke failures point to Host-owned compactor internals, that belongs to a Host core fix gate, not this smoke-only slice.

## Stop status

Slice 5 implementation is complete within the assigned allowed files. No Host core compile/runtime blocker was encountered. No README, commit, push, PR, review, or next gate action was performed.
