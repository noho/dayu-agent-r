# WU-CM-01 Compact Contract Closure Plan Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan review adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md` |
| review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-ds.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`plan-fix-required`。

两路 review 均接受新增 `Pre-Slice C - Compact Contract Closure` 的核心切分：latest blocker 成立，旧 compact production contract 必须在 memory snapshot / durable / config-service Slice C 之前先闭合。Controller 接受该切分，不回退到直接扩大 Slice C implementation。

但 AgentDS 提出的 3 个 blocking findings 都是 plan 层面的 owner / exit-signal 缺口，必须修复后才能进入 implementation。

## Finding Adjudication

| finding | 来源 | 裁决 | 理由 | 修复要求 |
|---|---|---|---|---|
| `tests/host/test_compact_artifact_store.py` 未在任何 slice allowed files 中 | DS B1 | accepted | 该测试直接 import `CompactionCandidate`、`CompactMaterialBlockKind` 与 `check_compaction_candidate()`，Pre-Slice C 删除旧 contract 后会 pyright 失败。 | 加入 Pre-Slice C allowed tests 和测试命令，限定为 artifact store 的 vNext candidate / quality check / material JSON 迁移。 |
| `dayu/host/compaction_evidence.py` 无具体 slice owner | DS B2 | accepted | 该文件使用 `CompactMaterialBlockKind.RAW_ASSISTANT_TURN` 生产 compact evidence material；若 material section enum / field contract 迁移，必须同 gate 有 owner。 | 加入 Pre-Slice C allowed files，限定为 compact evidence material section label / vNext material contract 迁移。 |
| 退出信号 grep 与 class definition 删除存在张力 | DS B3 | accepted | 旧 class definition / `__all__` export 本身就是旧 production contract 残留，不能作为“unused 删除候选”被无条件豁免；但 exit signal 也不能靠盲 grep 误伤历史 artifact 文本。 | 重写 exit signal：旧 candidate/type/helper 在 production closeout files 中不得有 class definition、public export 或 production reference；历史 docs / implementation report 可命中。若保留任何旧 symbol，必须是私有、不可导出、非 production path，并由 report 给直接证据。 |
| exit signals 未显式列出关键测试文件 | MiMo 1 | accepted | 清晰性问题，但有助于 implementation 不漏测。 | 显式列出 `test_compaction_contract.py`、`test_llm_compaction.py`、`test_compaction_operation.py`、`test_compact_material.py`、`test_compact_artifact_store.py`。 |
| exit signals 缺少 vNext positive adoption 验证 | MiMo 2 | accepted | 仅做 negative grep 不足以证明 production 入口已切到 vNext。 | 增加 positive signals：`context_governance.py` production accept barrier 使用 vNext checker；operation closeout / repair / fallback 使用 vNext candidate。 |
| 双 vNext method 决策不明确、old protocol annotation、event constants cleanup、external `ContextCompactor` residual risk | DS N1/N2/N4/residual | accepted | 都是 implementation 容易分叉或遗漏的 contract clarifications。 | 在 plan 中明确 `compact()` / `compact_request_vnext()` 收敛策略、`run_compaction_operation()` compactor 参数类型、旧 payload constants 清理、`ContextCompactor` 外部 implementor residual risk。 |

## Next Gate

进入 `WU-CM-01 compact contract closure plan fix gate`，由 AgentCodex 只修改 plan / control doc / fix artifact，不进入 implementation。
