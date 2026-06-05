# WU-CM-01 Slice C Engine Ingest / Context Governance Boundary Follow-up Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C engine ingest / context governance boundary follow-up adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| follow-up artifact | `docs/reviews/wu-cm-01-slice-c-engine-ingest-context-governance-boundary-followup-codex.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`accepted`。

AgentCodex 准确落实了 `docs/reviews/wu-cm-01-slice-c-implementation-blocker-controller-adjudication.md` 的 accepted blocker 裁决，只补充 allowed files/tests 与测试命令，没有进入 production implementation。

## Accepted Boundary Updates

- `dayu/host/engine_ingest.py` 纳入 Slice C，范围限定为 reactive compaction pending request 的 recent-window floor 字段迁移，不允许旧 `recent_raw_turns_floor` alias。
- `dayu/host/context_governance.py` 纳入 Slice C，范围限定为 compact quality checker 对 vNext `CompactMaterialPack` sections 和删除旧 `CompactMaterialBlockKind` 后的读取迁移。
- `tests/host/test_engine_ingest_mapping.py` 纳入 Slice C，范围限定为 reactive compaction pending policy field 迁移。
- 计划明确没有独立 `tests/host/test_context_governance.py` 必跑文件，context governance / compact material contract 由 `test_compaction_contract.py`、`test_compaction_operation.py`、`test_llm_compaction.py` 覆盖。

## Re-review Decision

不需要重新完整 plan re-review。本次没有改变 vNext contract、schema 取舍、分层边界或 Slice C 目标；它只把 Controller 已接受的两个 direct consumer 和测试 owner 写入 Slice C 专属 implementation boundary。

## Next Gate

进入 `WU-CM-01 Slice C implementation gate`。
