# WU-CM-01 Compact Contract Closure Fix Re-Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure fix re-review adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-fix-codex.md` |
| re-review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-fix-rereview-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-fix-rereview-ds.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`accepted-slice`。

AgentMiMo 与 AgentDS 均裁决 `pass`。Controller accepted findings 已完整处理，Pre-Slice C - Compact Contract Closure 可以进入 accepted slice commit。

## Finding Adjudication

| finding | 裁决 | 理由 |
|---|---|---|
| forward intent prompt enum 与 parser enum 不一致 | accepted-as-fixed | Prompt 已改为 `next_step_note/open_question/pending_clarification/pending_user_visible_task` 与 `open/blocked/superseded`，并新增从 prompt 读取候选值后构造 parser enum 的测试。 |
| dispatch scheduler repeated overflow 全文件测试回归 | accepted-as-fixed | 测试改为等待最终 `CONTEXT_COMPACTION_FAILED`，断言 2 次成功 compact + 1 次 `reactive_compact_limit_reached` fail-closed attempt；`pytest tests/host/test_dispatch_scheduler.py -q` 通过。 |
| prompt assets 与 `context_fallback.py` necessary dependency fallout 记录 | accepted-as-fixed | Plan 已补记 prompt files 仅限 vNext prompt schema / enum replacement，`context_fallback.py` 仅限 vNext material enum replacement，不扩大 config-service、runtime prompt loading、fallback behavior 或 durable/projection 语义。 |
| memory-owned legacy projection parser path | deferred-with-owner | 仍为后续 Slice C owner；本 slice 不删除且不作为 compact public compatibility contract 导出。 |
| `MAX_VNEXT_*` char/label 常量未导出 | rejected-with-reason | 保持内部 parser 实现细节，不扩大 public compact contract。 |
| prompt 中 `evidence_kind` / `reason` 枚举值未被自动化测试覆盖 | deferred-with-owner | 当前值经 DS 人工验证与 parser enum 一致；该 finding 是低风险 non-blocking。若后续继续扩展 prompt/schema consistency tests，owner 为后续 compact prompt maintenance 或 Slice C/D 测试完善。 |

## Validation

Review artifacts 记录以下验证已通过：

- `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q`：28 passed。
- `pytest tests/host/test_dispatch_scheduler.py -q`：60 passed。
- `pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_compact_artifact_store.py -q`：88 passed。
- `pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`：99 passed。
- `pytest tests/host/test_package_exports.py tests/host/test_public_compact_smoke.py -q`：15 passed, 1 skipped。
- `python -m pyright dayu/ tests/ utils/`：0 errors。
- MiMo 额外全量 `pytest tests/host/ -q`：1144 passed, 1 skipped, 5 deselected。

## Next Gate

进入 accepted slice commit。提交后 `next entry point` 为 `WU-CM-01 Slice C implementation gate`。
