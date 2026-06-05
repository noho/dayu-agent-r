# WU-CM-01 Compact Contract Closure Plan

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan gate |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| blocker adjudication | `docs/reviews/wu-cm-01-slice-c-compact-contract-blocker-controller-adjudication.md` |
| current status commit | `5fd75844` |
| result | plan/reslice complete; waiting for plan review |

## 动机判断

latest blocker 成立，严重性评估正确。

第一性原理判断：Host design 第 24.3 / 25 章把 compact I/O 固定为 `ConversationCompactInputVNext` / `ConversationCompactOutputVNext`，Context Governance 只能接受 vNext compact candidate 并写 compact-related canonical facts。Conversation Memory Slice C 要删除旧 memory snapshot / policy；如果 production compact parser、material pack、quality checker 和 operation closeout 仍使用旧 contract，Slice C 无法 pyright-clean，也会诱导旧 field alias、旧 compat wrapper 或旧 snapshot bridge。

因此当前问题不是测试 fixture 落后，也不是可以在 Slice C 内局部止血的类型错误，而是 compact production owner 尚未闭合。继续把 compact parser / operation closure 混进 memory durable / projection / RunInputBuilder / config-service，会扩大 Slice C scope 并削弱 review 可承载性。

## 直接证据

直接证据来自当前代码读取，而不是 issue body 或间接推断：

- `dayu/host/compaction.py` 仍定义旧 `CompactMaterialPack.stable_input`、`history_input`、`evidence_input`。
- `dayu/host/compaction.py` 仍定义旧 `CompactMaterialBlockKind`，包括 `PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY`。
- `dayu/host/compaction.py` 仍定义旧 `CompactionCandidate`、`MinimumPreserveItemCandidate`、`PinnedStatePatchCandidate`、`PreservationEvidence` 等旧 candidate 类型。
- `dayu/host/llm_compaction.py` 的 production `LLMContextCompactor.compact()` 仍返回旧 `CompactionCandidate`，并解析 `pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preservation_evidence`。
- `dayu/host/context_governance.py` 仍保留旧 `check_compaction_candidate()` production checker，读取 `candidate.pinned_state_patch_candidate` 与旧 material sections。
- `dayu/host/compact_material.py` 仍从旧 `CompactMaterialPack` 字段转换 vNext input，说明 vNext 仍是 adapter 后产物，不是 production material 真源。
- `tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_compact_material.py` 仍有旧 candidate、旧 material JSON 或旧 block kind 断言。

## 计划如何重切

已更新 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- 在当前 Slice C 之前新增 `Pre-Slice C - Compact Contract Closure`。
- 该前置 slice 的目标是先关闭 production compact material、LLM parser、quality checker、operation closeout、compact payload / event closeout 与直接 tests 的旧 contract 残留。
- 前置 slice 明确 allowed production owners：`dayu/host/compaction.py`、`dayu/host/llm_compaction.py`、`dayu/host/context_governance.py`、`dayu/host/compact_material.py`、`dayu/host/compaction_operation.py`，以及 payload reader / writer 需要时的 `dayu/host/context_events.py`、`dayu/host/compact_payload.py`，compact event closeout 受影响时的 `dayu/host/dispatch.py` / `dayu/host/engine_ingest.py`。
- 前置 slice 明确 tests：`tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_compact_material.py`，以及 material JSON 行为改变时的 `tests/host/fake_compaction.py` / `tests/host/test_public_compact_smoke.py`。
- 前置 slice 明确禁止旧 compat wrapper、旧 field alias、旧 block kind alias、旧 snapshot bridge、`hasattr` / `getattr` 式类型逃逸、无类型 dict / `Any`、lazy import 和 extra payload。
- 前置 slice 明确禁止混入后续 Slice C 内容：不迁移 memory durable/projection、RunInputBuilder memory section、Runtime config loader、Service assembly、config JSON 或 README。
- 后续 Slice C 已改为依赖前置 closure 完成后再迁移 memory snapshot、durable/projection、RunInputBuilder、dispatch memory precondition、config-service。
- 后续 Slice C 的 allowed files、测试命令、退出信号和 residual risks 已收窄，不再承担 LLM parser、旧 `CompactionCandidate`、旧 `CompactMaterialPack` production closeout 或 compact event payload closure。

已更新 `docs/host/issues-implementation-control.md`：

- `implementation status` 改为 `compact-contract-closure-plan-complete`。
- `next entry point` 改为 `WU-CM-01 compact contract closure plan review gate`。
- 记录本 artifact：`docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md`。
- 未声明任何新的 implementation commit。

## 未触碰范围

本 gate 是 code-generation-ready plan/reslice，只更新计划、总控与本 artifact。

未修改：

- production code。
- tests。
- schema。
- config JSON。
- README。
- git stash。
- git commit / push / PR。

本 gate 未运行 pytest 或 pyright，因为未修改代码，且停止条件要求完成文档更新后等待 Controller。

## 后续需要 Plan Review

下一步应进入 `WU-CM-01 compact contract closure plan review gate`。

plan review 应重点审查：

- 前置 closure slice 是否足够关闭 current production compact contract。
- allowed files 是否覆盖全部 production owner，且没有越界到 memory durable/projection/config-service。
- 禁止项是否足以防止旧 compat wrapper、旧 field alias、旧 snapshot bridge。
- 测试命令与退出信号是否能证明 compact contract closure pyright-clean。
- 后续 Slice C 是否已经正确依赖前置 closure，而不是重复承担 compact parser / operation 迁移。
