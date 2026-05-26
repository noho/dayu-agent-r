# P12.6 Aggregate Re-review Controller Adjudication

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Base checkpoint: `8749be9`
- Accepted Slice 7 checkpoint: `69ca9ce`
- Aggregate review artifacts:
  - `docs/reviews/p12-6-aggregate-deepreview-mimo-20260524.md`
  - `docs/reviews/p12-6-aggregate-deepreview-ds-20260524.md`
- Aggregate fix artifact: `docs/reviews/p12-6-aggregate-fix-codex-20260524.md`
- Aggregate re-review artifacts:
  - `docs/reviews/p12-6-aggregate-rereview-mimo-20260524.md`
  - `docs/reviews/p12-6-aggregate-rereview-ds-20260524.md`

## Verdict

PASS。Aggregate review、targeted fix 与双路 re-review 均已完成；P12.6 ready-to-open-draft-PR 条件满足。

## Accepted Findings Status

- DS Finding 1: fixed. `open_questions` 与 `working_assumptions` 均按 normalized text 去重，去重发生在 budget limit 前，且输出 deterministic。
- DS Finding 2: fixed. 旧 `collect_compaction_request_evidence_inputs` range collector 定义、`__all__` 导出、生产引用与测试引用均已删除；未保留兼容 wrapper / re-export。
- MiMo INFO `_reject_result_preview()` migration guard: accepted-as-residual。当前 guard 是 fail-closed 防御逻辑，不读取或生成 preview。

## Residual Risks And Owners

- `CompactSegmentSelection.policy_digest` 命名误导: 后续 cleanup owner。
- `build_initial_material_pack()` builder 层 dedupe guard 路径不对称: 后续 cleanup owner。
- Proactive / reactive stale 或状态漂移场景缺 diagnostic: production hardening owner。
- Reactive public smoke 与独立 `CONTEXT_COMPACTED` EventLog 断言: test hardening owner。
- `build_compact_material_pack()` 含 memory snapshot stable input 的显式测试: test hardening owner。
- `EpisodeSummaryCandidate.source_event_refs` ref 策略不一致: Host compaction contract cleanup owner。
- Large session rebuild performance 与 Host-neutral text-overlap relevance strategy: 后续 performance / retrieval owner。

## Validation Evidence

- Controller focused tests: `109 passed`
- Controller compact / memory matrix: `341 passed, 1 skipped`
- Controller pyright: `0 errors, 0 warnings, 0 informations`
- Controller `git diff --check`: pass
- Old range collector residue check: `rg collect_compaction_request_evidence_inputs dayu tests` returned no matches.
