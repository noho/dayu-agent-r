# WU-STRESS-01 Slice 2 Code Review Controller Adjudication

## Gate

code review

## Reviewed Artifacts

- `docs/reviews/wu-stress-01-implementation-slice2-codex-20260601.md`
- `docs/reviews/wu-stress-01-code-review-slice2-mimo-20260601.md`
- `docs/reviews/wu-stress-01-code-review-slice2-ds-20260601.md`

## Controller Conclusion

Slice 2 code review gate accepted after fix and re-review. AgentDS identified maintainability findings that were valid under AGENTS.md and the control document's slice handoff rules; AgentCodex fixed the accepted findings, and both AgentMiMo and AgentDS re-reviewed the result as PASS with zero remaining findings.

## Finding Decisions

### ADJ-S2-01-accepted-_slice2_failure_boundary 参数过多

来源：AgentDS 001。

裁决：accepted。

原因：15 个 keyword-only 参数已经接近 god function；后续 Slice 3-5 会继续增加诊断维度。基于最佳实践，应先把 Slice 2 的诊断值收束成局部强类型结构或更小的 predicate helper，避免后续扩散。

要求：将 `_slice2_failure_boundary` 改为接收一个 slice-local typed diagnostics dataclass，或拆成更小的 per-boundary helpers；不得引入裸 dict / Any / object。

### ADJ-S2-02-accepted-断言逻辑双真源

来源：AgentDS 002。

裁决：accepted。

原因：failure boundary 与后续 assert 重复同一组条件，后续维护容易分歧。当前 slice 的失败边界和 assertion 应以同一个 diagnostics helper / predicate 真源驱动。

要求：把重复条件集中在 typed diagnostics predicate 或 helper 中，测试断言复用同一结果；不能保留两套分歧判断。

### ADJ-S2-03-accepted-summary 未测量字段需要语义收口

来源：AgentDS 003。

裁决：accepted as clarification。

原因：`HostStressSummary` 是跨 slice 固定摘要，Slice 2 不实际测量 watch lag；但 `scheduler_drained` 应至少来自本 slice 的 terminal/recovery drain 观测，而不是无条件常量。未测量字段需要在局部 helper / 注释 / artifact 中明确为 Slice 2 non-applicable diagnostic，避免误读。

要求：让 `scheduler_drained` 由 Slice 2 diagnostics 推导；对 `watch_lag_max` / `watch_lag_samples` 写明 Slice 2 未测量 watch lag，值仅为 schema placeholder。

### ADJ-S2-04-accepted-terminate 异常路径应保留原始上下文

来源：AgentDS 004、AgentMiMo 01。

裁决：accepted。

原因：虽然概率低，但 cleanup 路径不应覆盖原始异常上下文。测试 helper 也应保持故障可诊断。

要求：调整 `start_and_crash_owner_for_stress` 和 `_run_live_owner_probe` cleanup，避免不必要的重复 terminate；如 cleanup 失败，应保留原异常链。

### ADJ-S2-05-deferred-terminal_duplicate_count 混合场景语义

来源：AgentMiMo 02、AgentDS residual risk。

裁决：deferred-with-owner。

原因：当前 Slice 2 的每 Run 单 terminal 语义下，该 helper 行为正确；Slice 5 mixed Host stress 才会检验更复杂终态组合。当前修改不应预先扩大成新的 dedupe framework。

Owner / Destination：WU-STRESS-01 Slice 5 implementation/review。

## Next Step

Create accepted Slice 2 local commit, then proceed to Slice 3 sustained watch stress handoff.

## Fix / Re-review Artifacts

- `docs/reviews/wu-stress-01-fix-slice2-codex-20260601.md`
- `docs/reviews/wu-stress-01-code-rereview-slice2-mimo-20260601.md`
- `docs/reviews/wu-stress-01-code-rereview-slice2-ds-20260601.md`

## Controller Validation

- `source .venv/bin/activate && pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k repeated_startup_recovery_crash -q`: PASS; `1 passed, 1 deselected`.
- `source .venv/bin/activate && pytest tests/host/test_recovery_multiprocess.py -q`: PASS; `3 passed`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: PASS; `0 errors, 0 warnings, 0 informations`.

## Artifact Path

`docs/reviews/wu-stress-01-code-controller-adjudication-slice2-20260601.md`
