# P12.6 Slice 7 Cleanup Re-review Controller Adjudication

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 7 Public Compact Smoke、README 同步与最终验证
- Base checkpoint: `a2114a2 gateflow: accept P12.6 slice 6`
- Implementation artifact: `docs/reviews/p12-6-slice7-implementation-codex-20260524.md`
- Targeted production fix artifact: `docs/reviews/p12-6-slice7-fix-codex-20260524.md`
- Cleanup artifact: `docs/reviews/p12-6-slice7-cleanup-codex-20260524.md`
- Review artifacts:
  - `docs/reviews/p12-6-slice7-code-review-mimo-20260524.md`
  - `docs/reviews/p12-6-slice7-code-review-ds-20260524.md`
- Cleanup re-review artifacts:
  - `docs/reviews/p12-6-slice7-cleanup-rereview-mimo-20260524.md`
  - `docs/reviews/p12-6-slice7-cleanup-rereview-ds-20260524.md`

## Verdict

PASS。两路 cleanup re-review 均确认 accepted cleanup findings fixed，未发现 blocking / high / medium 新问题。

## Accepted Findings Status

- MiMo F1 / F2: fixed. Compact payload text-list 与 preserved canonical evidence refs 解析已抽入 `dayu.host.compact_payload`，`dispatch.py` 与 `run_input.py` 不再保留重复解析路径。
- DS Finding 1 / MiMo F4: fixed. `_latest_session_compacted_event_before_input` 改为使用调用方传入的 `EventLogStore`。
- MiMo F3: accepted-as-non-blocking. `tests/host/fake_compaction.py` 继续复用生产 parser，后续若生产 parser 重构再同步测试。
- DS Finding 2 / 3 / 4 与 DS NF1: recorded as non-blocking residuals，不阻塞 Slice 7 acceptance。

## Validation Evidence

- Controller public smoke: `5 passed, 1 skipped`
- Controller specified host suite: `292 passed, 1 skipped`
- Controller pyright: `0 errors, 0 warnings, 0 informations`
- Controller `git diff --check`: pass

## Residual Risks

- Proactive budget estimator 仍按当前输入估算触发条件；本 slice 只补齐 compactor material evidence 输入。
- Accepted evidence 读取上限固定为 8；若后续需要按 token budget / evidence priority 调整，应另走 Host policy 设计。
- Evidence id 跨模块链路仍依赖 `accepted_evidence_id` / `fact.evidence_refs` / `preserved_fact_refs.canonical_evidence_refs` 同源语义；当前 tests 与 review 均未发现不一致。
- Real provider compactor smoke 默认 skip，需设置 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 才运行。
