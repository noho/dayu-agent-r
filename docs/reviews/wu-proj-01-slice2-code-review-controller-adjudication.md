# WU-PROJ-01 Slice 2 Code Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: Slice 2 code review controller adjudication
- 日期: 2026-06-11
- Implementation artifact: `docs/reviews/wu-proj-01-slice2-implementation-codex.md`
- AgentMiMo review artifact: `docs/reviews/wu-proj-01-slice2-code-review-mimo.md`
- AgentDS review artifact: `docs/reviews/wu-proj-01-slice2-code-review-ds.md`
- Controller verdict: fix required for accepted low findings

## Review Verdicts

| Lane | Verdict | Controller decision |
|---|---|---|
| AgentMiMo | APPROVE | accepted |
| AgentDS | PASS | accepted |

两路 review 均确认 Slice 2 implementation 对齐 accepted plan：proactive budget、segment selection、pack build、CompactionRequest refs 与 fallback 共用冻结 `PreDispatchCompactMaterialView`；旧 dispatch memory snapshot evidence 去重职责已删除；material source failure fail closed；reactive path 只做 previous-view 最小适配。无 blocking finding。

## Accepted Fix Findings

| Finding | 裁决 | 当前 fix 要求 |
|---|---|---|
| DS-S2-L2: `_proactive_fallback_material_blocks` current input 追加逻辑缺少边界场景测试 | accepted | 新增 focused test，直接断言 material view delta 不包含 current input，fallback material blocks 追加 current input 后不产生重复 current block。 |
| MiMo INFO-3: `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 调整 budget 阈值缺少注释 | accepted | 在测试中补简短注释，说明阈值调高是为了让同源 material view 的完整估算超过 soft threshold 但低于 hard threshold，测试目标仍是 proactive compact lifecycle。 |

## Deferred / Rejected Findings

| Finding | 裁决 | 理由 / Owner |
|---|---|---|
| DS-S2-L1: material source failure 异常捕获范围偏宽 | deferred-with-owner | 当前行为 fail closed，符合本 WU 的 source failure 安全目标；细分 `HostDurableError` 与 programming error 属于 diagnostic taxonomy hardening，Owner: Slice 3 diagnostic / later context governance diagnostic cleanup。 |
| DS-S2-L3: reactive material source failure 不写 `CONTEXT_COMPACTION_FAILED` event | deferred-with-owner | Reactive path 本 WU 只做 previous-view 最小适配。是否让 reactive material source failure 写 compact governance event 需统一 reactive diagnostic / EventLog event policy，Owner: reactive deep hardening / context governance event audit。 |
| MiMo INFO-1: reactive budget estimate 仍只用单 fragment | deferred-with-owner | accepted plan 将 reactive budget 同源化留给后续 owner；本 WU 当前 slice 不做 reactive multi-pass / overflow material freeze。 |
| MiMo INFO-2: `_MinimalSummaryCompactor` fixture 假设 trace material 非空 | rejected-with-reason | 当前使用该 fixture 的测试均保证 trace material 非空；若未来新增空 trace 场景，由对应测试补 fixture 防御。 |
| MiMo 其它 PASS / bookkeeping observations | rejected-with-reason | 确认项，无需 fix。 |

## Fix Gate

- Responsible agent: AgentCodex
- Expected fix artifact: `docs/reviews/wu-proj-01-slice2-fix-codex.md`
- Allowed files:
  - `tests/host/test_dispatch_scheduler.py`
  - `docs/reviews/wu-proj-01-slice2-fix-codex.md`
- Required validation:
  - `source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"`
  - `source .venv/bin/activate && pyright`

Fix gate 不得修改 production code、design docs、control doc、README、GitHub issue、commit、push、PR。若 accepted test fix 无法在 allowed files 内完成，应停止并回报。
