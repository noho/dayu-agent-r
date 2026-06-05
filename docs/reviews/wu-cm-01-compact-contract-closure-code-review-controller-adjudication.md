# WU-CM-01 Compact Contract Closure Code Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure code review adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| implementation artifact | `docs/reviews/wu-cm-01-compact-contract-closure-implementation-retry-codex.md` |
| review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-code-review-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-code-review-ds.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`fix-required`。

Production compact contract closure 方向通过 review，但存在两项必须在本 slice 合并前修复的问题：

- prompt 示例允许 parser 不接受的 forward intent enum 值，属于 compact runtime correctness issue。
- `tests/host/test_dispatch_scheduler.py` 全文件运行出现测试隔离回归，属于受影响测试未闭合。

## Finding Adjudication

| finding | 来源 | 裁决 | 理由 | 修复要求 |
|---|---|---|---|---|
| LLM prompt 中 `forward_intents[*].intent_type/status` 枚举值与 parser 不一致 | DS 1 | accepted-blocking | `conversation_compaction_user.md` 允许 `user_constraint`、`working_assumption`、`resolved`，但 `ForwardIntentTypeVNext` / `ForwardIntentStatusVNext` 不接受这些值；LLM 按 prompt 输出会触发 parser fail closed，浪费 repair attempt。 | 修正 prompt 枚举候选值为 parser 真源；新增或更新测试，断言 prompt 中列出的 forward intent enum 值均能被 parser enum 接受。 |
| `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 全文件运行 attempt count 3 vs 2 | MiMo 001 | accepted-blocking | 该实现修改了 `tests/host/test_dispatch_scheduler.py` 与 fake compactor，单测单独通过但全文件失败，说明受影响测试隔离不闭合；这违反“修改后优先验证通过”。 | 定位并修复 fake compactor / test factory 状态泄漏或断言边界，必须运行 `pytest tests/host/test_dispatch_scheduler.py -q` 并通过。 |
| Pre-Slice C 范围外修改 prompt assets 与 `context_fallback.py` | DS 2 | accepted-non-blocking | prompt assets 与 fallback enum 替换是 vNext parser / enum 删除的必要 fallout，review 判断 correctness 通过；但 plan allowed files 没有显式记录 prompt files，存在 plan-to-implementation 记录缺口。 | 在 fix artifact 或 plan 中补记这些文件作为 Pre-Slice C necessary dependency fallout，scope 限定为 vNext prompt schema 与 enum member replacement，不扩大 config-service 或 fallback behavior。 |
| memory-owned legacy projection parser path | DS 3 | deferred-with-owner | 该 path 不从 `dayu.host.compaction` 导入，也不导出 compact compatibility contract；属于后续 memory projection closure 的 residual risk。 | 记录 owner 为后续 Slice C；本 fix 不要求删除。 |
| `compaction.py.__all__` 缺少 7 个 `MAX_VNEXT_*` 字符/label limit 常量 | MiMo 002 | rejected-with-reason | 当前这些常量仅由同包 parser 内部消费，不是本 slice 需要扩大的 public compact contract。保持较小 public surface 更符合项目边界；未来若外部 contract 需要再显式导出。 | 无需修复。 |

## Required Validation

Fix gate 完成后至少运行：

```bash
source .venv/bin/activate
pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py -q
pytest tests/host/test_dispatch_scheduler.py -q
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_compact_artifact_store.py -q
pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q
pytest tests/host/test_package_exports.py tests/host/test_public_compact_smoke.py -q
python -m pyright dayu/ tests/ utils/
```

## Next Gate

进入 `WU-CM-01 compact contract closure fix gate`，由 AgentCodex 修复 accepted findings。AgentCodex 不得 commit、push、PR 或进入 re-review。
