# Phase 10 Aggregate Deepreview Controller Adjudication

日期：2026-05-18

## 结论

Phase 10 Context Governance / Compaction aggregate deepreview 通过。当前可进入 `ready-to-open-draft-PR`。

## Review 输入

- Aggregate review artifacts:
  - `docs/reviews/phase10-aggregate-deepreview-mimo-20260518.md`
  - `docs/reviews/phase10-aggregate-deepreview-ds-20260518.md`
- Commit range: `f131fb8..HEAD`
- Accepted Phase 10 commits:
  - `31615df docs(host): accept phase 10 context governance plan`
  - `d969404 feat(host): add phase 10 context budget policy`
  - `15b2815 feat(host): add context compaction contracts`
  - `6206699 feat(host): add context compact events`
  - `4e5498d feat(host): add proactive context governance`
  - `6b8101f feat(host): add reactive context recovery`
  - `05f2531 feat(host): wire context governance composition`

## 裁决

- AgentMiMo verdict 为 PASS，明确 Phase 10 已可进入 `ready-to-open-draft-PR`。
- AgentDS verdict 为 PASS / Ready for draft PR，提出 3 个 LOW 与若干 INFO / residual。
- Controller 接受 DS AG1 / AG2 / AG3 为 non-blocking residual，不作为当前 PR 前 fix。AG1 不影响 worker stream 停止，因为 scheduler 同时检查 `terminal_closeout or stop_worker_stream`；AG2 是同事务 defensive ordering 改进，正常 CAS 前置校验下不会影响当前 correctness；AG3 是预算压力下的可读性降级，不影响 Host truth。
- 已知 residual 均有 owner / destination，不阻塞 draft PR：真实 compactor adapter、tokenizer / sizing、legacy helper cleanup、reactive recovery method organization、Service composition root caller、higher-fidelity tool verified fact E2E、RECOVERING cancel / startup recovery。

## Phase 10 达成项

- Host-owned `ContextBudgetPolicy` 与 conservative estimator。
- Host-owned typed compactor port、fake compactor、quality check 与 deterministic compact artifact。
- `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED` canonical payload builder / validator。
- P9 Conversation Memory projection 消费 accepted `CONTEXT_COMPACTED`，pinned state patch 使用三态语义，verified facts 仍只来自 `TOOL_RESULT_ACCEPTED`。
- RunInputBuilder 注入 durable memory snapshot 与 compact artifact provider。
- Scheduler pre-start proactive governance：accepted / queued Run 在 Attempt 创建前进行 budget check、compact、failure closeout 或 start。
- EngineEvent reactive overflow recovery：Engine overflow 只是 fallback signal，Host 校验 Attempt / execution identity 后进入 `RECOVERING`，compact accepted 后创建新 Attempt。
- Production composition wiring：`context_window_size` 与 `reserved_output_tokens` 是 `HostCommandHandleOptions` 必填 typed input；budget 字段不进入 per-run request / metadata。
- Multi-turn aggregate integration 覆盖 proactive compact -> memory projection -> subsequent Engine request。

## Controller 验证

S6 后 controller 已复现 Phase 10 focused validation：

- `pytest tests/host/test_public_contracts.py tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py -q`：81 passed。
- `pytest tests/host/test_context_budget.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py -q`：180 passed。
- `pyright`：0 errors / 0 warnings / 0 informations。
- `git diff --check`：clean。

AgentMiMo aggregate review 另行复现 261 passed、pyright 0、diff check clean。

## Remaining Risk Tracking

- LOW AG1: `_close_attempt_for_context_recovery` DUPLICATE branch 缺少显式 `stop_worker_stream=True`，但当前 scheduler 仍通过 `terminal_closeout` 停止 worker stream。Owner: Phase 10 / EngineEvent ingest hardening。
- LOW AG2: reactive `CONTEXT_COMPACTION_REQUESTED` 在 closeout CAS 前追加；当前同一 write transaction 与前置校验使正常路径安全，但可作为 defensive ordering cleanup。Owner: Phase 10 / EngineEvent ingest hardening。
- LOW AG3: budget 压力下 pinned patch text 可能降级为 opaque ref，对 LLM 可读性较弱。Owner: Phase 13 memory diagnostic / retrieval owner。
- INFO: redundant accepted unique index、helper 命名 cleanup 等不影响当前 correctness，归 schema / admission cleanup owner。

上述 tracking items 已写入 `docs/host/implementation-control.md`。
