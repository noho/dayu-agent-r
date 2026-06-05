status: implemented

changed files:
- dayu/host/llm_compaction.py
- dayu/host/compaction_operation.py
- dayu/host/dispatch.py
- dayu/host/context_events.py
- dayu/host/durable/schema.py
- tests/host/test_llm_compaction.py
- tests/host/test_compaction_operation.py
- tests/host/test_public_compact_smoke.py
- dayu/host/README.md
- tests/README.md
- docs/reviews/wu-dur-obs-cm-closeout-slice3-implementation-retry-codex.md

implementation summary:
- Added the shared durable descriptor kind constant `COMPACTOR_INPUT_PROJECTION_DESCRIPTOR_KIND = "compactor_input_projection"`.
- Split `LLMContextCompactor` proposal execution into typed prepare/run steps. `prepare_compactor_proposal_run_input(...)` constructs the exact Engine `AgentRunRequest`, message count, role sequence digest, compaction request digest, prompt digests, and compactor input projection digest before the runner call. `compact(...)` still preserves the existing public behavior by preparing then running the prepared request.
- Added typed operation-level contracts: `CompactorProposalRunInput`, `CompactorProposalManifestReference`, `CompactorProposalPreparedCompactor`, and `CompactorProposalManifestRecorder`.
- Extended `run_compaction_operation(...)` so prepared compactor implementations record a proposal manifest before the runner call, then carry accepted proposal manifest ref/digest through `CompactionOperationResult` and rejected proposal manifest ref/digest through `CompactionAttemptRejected`.
- Added a Host durable recorder in dispatch. It writes the compactor input projection artifact/descriptor, writes the `runner_call_input_manifest` artifact/descriptor, and appends the canonical `RUNNER_CALL_INPUT_ASSEMBLED` event before executing the proposal runner call.
- Extended compact event payload builders with typed proposal manifest ref/digest fields. Dispatch passes accepted manifest refs into `CONTEXT_COMPACTED` and rejected attempt manifest refs into `CONTEXT_COMPACTION_ATTEMPT_REJECTED`.
- Added focused tests for prepared input same-source message/role observations, operation accepted/rejected manifest ref propagation, and public proactive compact manifest boundedness.

contract decisions:
- The compactor proposal remains a Host-owned internal runner call, not a Host admitted Run. The manifest uses `runner_call_kind="compactor_proposal"` and a compaction-operation-scoped zero-based `runner_call_index`.
- No `ContextCompactor` public protocol change was made. Production `LLMContextCompactor` exposes an additional typed prepared-input capability; generic compactor fakes keep the old `compact(...)` path.
- The manifest hot payload and manifest body do not inline full prompts, full message text, compact material, provider raw request/response, or provider raw dicts. Full compactor input is stored only as the derived `compactor_input_projection` artifact and referenced by descriptor ref/digest.
- `message_count` and `role_sequence_digest` are computed from the exact `AgentRunRequest.messages` that the compactor runner call receives.
- Dispatch accepted compact path fails closed if an accepted compaction result lacks an accepted proposal manifest ref/digest.

tests / pyright / diff-check:
- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_public_compact_smoke.py`
  - result: 65 passed, 1 skipped
- `source .venv/bin/activate && pyright`
  - result: 0 errors, 0 warnings
- `git diff --check`
  - result: passed

README sync:
- Updated `dayu/host/README.md` to document compactor proposal runner-call manifests and proposal manifest refs in accepted/rejected compact payloads.
- Updated `tests/README.md` to document the new prepared proposal / manifest propagation and bounded public smoke coverage.

remaining risks:
- This retry stayed within the expanded allowed files. `dayu/host/engine_ingest.py` was not edited, so reactive compaction wiring is not expanded here; the implemented durable recorder is connected through the dispatch proactive compaction path covered by the retry validation. If controller expects reactive `CONTEXT_COMPACTED` payloads to carry proposal manifest refs in the same slice, `engine_ingest.py` must be explicitly added to a follow-up allowed-files set.
- Tool Trace analyzer reconstruction for compactor manifests remains out of scope for Slice 3 and is not implemented here.

ready for code review: yes
