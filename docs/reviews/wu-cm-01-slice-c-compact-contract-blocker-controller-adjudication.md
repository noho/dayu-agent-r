# WU-CM-01 Slice C Compact Contract Blocker Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C implementation blocker adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| implementation artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`accepted-blocker`。

AgentCodex 的 partial implementation 证明：memory / durable / run-input / config 等生产 direct consumers 可以局部迁到 vNext，但测试与 compact production contract 仍被旧 `CompactionCandidate`、旧 `CompactMaterialPack`、旧 `CompactMaterialBlockKind` 和旧 LLM parser 绑定。继续在当前 Slice C gate 中硬推，会把 Slice A/B 的旧 compact production contract、LLM parser、quality gate 与 tests 一并拉入，超出当前 Slice C 小补丁策略和已接受边界。

## Direct Evidence

- `dayu/host/compaction.py` 仍定义旧 `CompactMaterialPack.stable_input`、`history_input`、`evidence_input` 与旧 `CompactMaterialBlockKind`。
- `dayu/host/compaction.py` 仍定义旧 `CompactionCandidate`、`MinimumPreserveItemCandidate` 和 `pinned_state_patch_candidate`。
- `dayu/host/llm_compaction.py` 的 production `compact()` 仍返回旧 `CompactionCandidate`，并解析 `pinned_state_patch_candidate`。
- `dayu/host/context_governance.py` 的 `check_compaction_candidate()` 仍读取旧 candidate/material shape。
- `tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_compact_material.py`、`tests/runtime/test_config_loader.py`、`tests/service/test_host_assembly.py` 仍大量绑定旧 memory / policy / compact material contract。

## Partial Diff Handling

partial implementation diff 不是完成态，不能提交为 Slice C implementation。Controller 已将代码/config partial diff 保存到 git stash：

```text
stash@{0}: partial WU-CM-01 Slice C typed contract attempt
```

该 stash 只作为后续参考，不作为 accepted implementation。后续若继续推进，应从干净工作区重新计划，不直接套用 partial diff。

## Decision

不接受继续在当前 Slice C implementation gate 内扩大到 `dayu/host/llm_compaction.py` 和完整旧 compact contract tests。更可维护的路径是新增前置 compact contract closure gate：

1. 先让 production `ContextCompactor.compact()`、LLM parser、quality gate、`CompactMaterialPack` 和 event payload 只使用 vNext compact input/output。
2. 同步迁移 `tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_compact_material.py` 到 vNext compact contract，并跑通 pyright。
3. 再重新进入 Slice C memory snapshot / durable projection / RunInputBuilder / dispatch / config-service closure。

## Next Gate

进入 `WU-CM-01 compact contract closure plan gate`。该 gate 应由 AgentCodex 先修正 plan / control doc，只做 code-generation-ready reslice，不直接实现。
