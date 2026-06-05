# WU-CM-01 Slice C Plan Boundary Follow-up Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C plan boundary follow-up adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| follow-up artifact | `docs/reviews/wu-cm-01-slice-c-plan-boundary-followup-codex.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`accepted`。

动机成立。Slice C plan 已要求迁移 `CompactMaterialPack` 顶层字段与 `CompactMaterialBlockKind` 全量枚举；直接代码证据显示 owner 是 `dayu/host/compaction.py`，直接测试证据显示 `tests/host/test_llm_compaction.py`、`tests/host/test_compaction_contract.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_public_compact_smoke.py` 与 `tests/host/fake_compaction.py` 仍消费旧 material contract。若 Slice C 专属 allowed files 不显式列这些 owner，会复现 allowed-files blocker。

## Accepted Updates

- Slice C allowed files/modules 显式加入 `dayu/host/compaction.py`，范围限定为 `CompactMaterialPack`、`CompactMaterialBlockKind`、material JSON / LLM JSON 与 vNext material section contract 迁移。
- Slice C allowed tests 显式加入 `tests/host/test_llm_compaction.py`、`tests/host/test_compaction_contract.py`、`tests/host/test_compaction_operation.py`。
- `tests/host/fake_compaction.py` 被限定为 public smoke / compaction tests 的 material JSON 字段迁移 helper，不改变生产 compactor 行为。
- Slice C 测试命令补充 compact contract / LLM / operation 三个直接 consumer 测试。

## Re-review Decision

不需要重新完整 plan re-review。本次没有改变 vNext contract、schema 取舍、分层边界或 Slice C 目标，只把既有 plan 中已经要求迁移的 compact material owner 和测试 owner 明确写入专属 allowed boundary。

## Next Gate

进入 `WU-CM-01 Slice C implementation gate`。implementation handoff 必须包含 `dayu/host/compaction.py` 与上述直接 consumer tests，避免实现过程中再次因 owner 漏列停下。
