# WU-CM-01 Compact Contract Closure Plan Fix

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan fix gate |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| plan artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md` |
| review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-ds.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-controller-adjudication.md` |
| result | plan fix complete; waiting for re-review |

## 动机判断

Controller accepted findings 成立，严重性评估正确。

Pre-Slice C 的目的不是扩大实现范围，而是在 memory snapshot / durable / RunInputBuilder / config-service 迁移前关闭 production compact contract。review 指出的缺口都属于 plan owner、测试矩阵或退出信号不完整：如果不在 plan 中明确，implementation agent 仍可能漏掉 artifact store、compact evidence material、旧 public symbol 清理、operation compactor 类型收敛和 vNext positive adoption 证据，进而把风险推迟到 Slice C。

## Accepted Findings 处理

- 接受 DS B1：已把 `tests/host/test_compact_artifact_store.py` 加入 Pre-Slice C allowed tests、测试命令和退出信号，范围限定为 artifact store 的 vNext candidate / quality check / material JSON 迁移。
- 接受 DS B2：已把 `dayu/host/compaction_evidence.py` 加入 Pre-Slice C allowed files，范围限定为 compact evidence material section label / vNext material contract 迁移。
- 接受 DS B3：已重写退出信号，不再使用盲 grep 作为唯一标准；要求旧 candidate / type / helper 在 production closeout files 中不得有 class definition、public export 或 production reference。历史 docs / review artifact / implementation report 可命中；若保留旧 symbol，必须是私有、不可导出、非 production path，并由 implementation report 给直接代码证据。
- 接受 MiMo 1：已显式列出必须通过的 tests：`tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_compact_material.py`、`tests/host/test_compact_artifact_store.py`。fake/public smoke 的追加条件也已写明。
- 接受 MiMo 2：已增加 vNext positive adoption exit signals：`context_governance.py` production accept barrier 使用 vNext checker；operation accepted / rejected / repair exhausted / fallback closeout、whole-candidate repair 和 failed fallback 使用 vNext candidate。
- 接受 DS N1/N2/N4/residual：已明确 `compact()` / `compact_request_vnext()` 收敛策略、`run_compaction_operation()` 的 compactor 参数类型、`context_events.py` 旧 payload constants / allowlist / helper 清理，以及外部 `ContextCompactor` implementor residual risk。

## 文档改动

已更新 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- 补齐 Pre-Slice C allowed files / tests owner：`dayu/host/compaction_evidence.py` 与 `tests/host/test_compact_artifact_store.py`。
- 收紧 Pre-Slice C 实现边界：production `ContextCompactor`、`LLMContextCompactor.compact()`、operation 调用路径和 `run_compaction_operation()` compactor 参数类型必须统一收敛到 `ConversationCompactOutputVNext`。
- 明确 `compact_request_vnext()` 只能作为未导出的内部拆分 helper，不能形成与旧 `compact()` 并存的双 public contract。
- 明确 `context_events.py` / `compact_payload.py` 中旧 compact payload constants、旧 field allowlist、旧 payload reader / writer helper 需要同步清理。
- 更新 Pre-Slice C 测试命令、fake/public smoke 追加条件、退出信号和 residual risk。
- 更新 Test Matrix 与最终验证命令，加入 `tests/host/test_compact_artifact_store.py`。

已更新 `docs/host/issues-implementation-control.md`：

- `implementation status` 改为 `compact-contract-closure-plan-fix-complete`。
- `next entry point` 改为 `WU-CM-01 compact contract closure plan re-review gate`。
- 记录本 fix artifact：`docs/reviews/wu-cm-01-compact-contract-closure-plan-fix-codex.md`。

## 未触碰范围

本 gate 只修文档，未修改：

- production code。
- tests。
- schema。
- config JSON。
- README。
- git stash。
- git commit / push / PR。

本 gate 未运行 pytest 或 pyright，因为没有修改代码，且停止条件要求完成文档更新后等待 Controller。

## 后续

下一步需要进入 `WU-CM-01 compact contract closure plan re-review gate`，由 re-review 审查本 fix 是否完整处理 Controller accepted findings，并确认 Pre-Slice C 是否可以进入 implementation。
