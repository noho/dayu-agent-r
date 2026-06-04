# WU-CM-01 Compact Contract Closure Implementation Blocker

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure implementation |
| agent | AgentCodex |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-plan-rereview-controller-adjudication.md` |
| artifact path | `docs/reviews/wu-cm-01-compact-contract-closure-implementation-codex.md` |
| status | blocked |

## Scope Judgment

本 gate 动机成立。设计真源第 24.3 / 25 章要求 compactor input/output 与 Context Governance accept barrier 收敛到 `ConversationCompactInputVNext` / `ConversationCompactOutputVNext`，当前代码也直接证明旧 production compact contract 仍未闭合。

但当前 implementation allowed files 不足以同时满足两个硬约束：

- 删除旧 production compact contract public symbols、旧 material fields 与双 public compactor method。
- 保持 `python -m pyright dayu/ tests/ utils/` 通过。

若继续在 allowed files 内实现，只能走两条坏路径之一：

- 保留旧 `CompactionCandidate` / `PinnedStatePatchCandidate` / `MinimumPreserveItemCandidate` 等 public symbols，违反本 gate 退出信号与禁止 compatibility wrapper / alias 的约束。
- 删除旧 public symbols，导致未授权文件 `dayu/host/memory.py`、`dayu/host/run_input.py`、`dayu/host/compact_artifact.py` 立刻失去 import/type 真源，无法 pyright-clean。

因此本次没有修改 production / tests / README，也没有应用或恢复 git stash。

## Direct Evidence

production closeout 文件内仍存在旧 public class definition / public export：

- `dayu/host/compaction.py:101` 定义 `PinnedPatchOperation`。
- `dayu/host/compaction.py:109` 定义旧 `CompactQualityIssue`。
- `dayu/host/compaction.py:292` 定义 `MinimumPreserveReason`。
- `dayu/host/compaction.py:2116` 定义 `EpisodeSummaryCandidate`。
- `dayu/host/compaction.py:2325` 定义 `PinnedStatePatchCandidate`。
- `dayu/host/compaction.py:2381` 定义 `PreservationEvidence`。
- `dayu/host/compaction.py:2503` 定义 `MinimumPreserveItemCandidate`。
- `dayu/host/compaction.py:2563` 定义 `CompactionCandidate`。
- `dayu/host/compaction.py:2677` 定义旧 `CompactQualityCheckResult`。
- `dayu/host/compaction.py:2799` 的 `ContextCompactor.compact()` 仍声明返回 `CompactionCandidate`。
- `dayu/host/compaction.py:3836` 起的 `__all__` 仍导出旧 `CompactQualityCheckResult`、`CompactQualityIssue`、`CompactionCandidate`、`EpisodeSummaryCandidate`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`、`PinnedPatchOperation`、`PinnedStatePatchCandidate`、`PreservationEvidence`。

production closeout 文件内仍存在旧 parser / checker production reference：

- `dayu/host/llm_compaction.py:234` 的 `LLMContextCompactor.compact()` 仍返回 `CompactionCandidate`。
- `dayu/host/llm_compaction.py:883` 起保留旧 strict parser `_candidate_from_final_answer()`，解析 `episode_summary_candidate`、`pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preservation_evidence`、`preserved_*` 字段。
- `dayu/host/llm_compaction.py:271` 与 `dayu/host/llm_compaction.py:315` 又提供 vNext `compact_vnext()` / `compact_request_vnext()`，形成 plan 明确禁止的双 public method closeout。
- `dayu/host/context_governance.py:40` 起仍有旧 `check_compaction_candidate()`，并导入/使用旧 `CompactionCandidate`、`CompactQualityIssue`、`PinnedPatchOperation`、`PreservationEvidence`。

allowed scope 外仍直接依赖旧 symbols：

- `dayu/host/memory.py:16` 起从 `dayu.host.compaction` import `EvidenceBackedFactCandidate`、`EvidenceBackedFactKind`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`；后续在 projection 中直接构造 minimum preserve candidate。
- `dayu/host/run_input.py:63` 起仍导入 `CompactMaterialBlockKind` / `CompactMaterialSection`，并在 memory section material rendering 中使用旧 block kind。
- `dayu/host/compact_artifact.py:15` 起从 `dayu.host.compaction` import `CompactQualityCheckResult`、`CompactionCandidate`、`EvidenceBackedFactCandidate`、`MinimumPreserveItemCandidate`；`CompactArtifactWriteRequest` 仍要求旧 accepted candidate 与旧 quality result。

`dayu/host/compact_artifact.py` 不在本 gate allowed production files 内，但 `tests/host/test_compact_artifact_store.py` 是必跑测试。若不迁移该 production artifact writer，artifact store 测试无法真正收敛到 vNext；若迁移它，则越过用户给定 allowed files。

## Changed Files

### Production

无。

### Tests

无。

### README

无。由于没有修改 `dayu/host/` production 或 `tests/` 行为，`dayu/host/README.md` 与 `tests/README.md` 未触发实际同步；本次只记录 blocker。

### Artifacts

- 新增 `docs/reviews/wu-cm-01-compact-contract-closure-implementation-codex.md`。

## Old Symbols Status

旧 symbols 仍存在，且不是私有、不可导出、非 production path：

- `CompactionCandidate`：public class；owner 需要扩展到 `dayu/host/compact_artifact.py`、`dayu/host/memory.py` 后才能删除。
- `EpisodeSummaryCandidate`：public class；owner 同上。
- `PinnedStatePatchCandidate` / `PinnedPatchOperation` / `PinnedStringTupleFieldPatch` / `PinnedTextFieldPatch`：public class / enum；owner 需要扩展到旧 parser、旧 quality checker、memory projection 后才能删除。
- `MinimumPreserveItemCandidate` / `MinimumPreserveReason`：public class / enum；owner 需要扩展到 `dayu/host/memory.py` 后才能删除。
- `PreservationEvidence`：public class；owner 需要扩展到旧 parser、旧 quality checker 和 old artifact writer 后才能删除。
- `CompactQualityCheckResult` / `CompactQualityIssue`：public class / enum；owner 需要扩展到 `dayu/host/compact_artifact.py` 和旧 checker 删除后才能删除。
- `ContextCompactorVNext.compact_request_vnext()`：public protocol method；owner 是本 gate，但删除前必须先把 `ContextCompactor.compact()` 改为 vNext input/output 并同步所有 implementor/callers。

## Validation

未运行指定 pytest / pyright。

原因：本 gate 在代码修改前已被 allowed files 不足阻断。继续修改会产生不完整迁移或兼容桥，违反用户明确的停止条件：“若发现 allowed files 不足以 pyright-clean，先写 blocker artifact 并停止，不要用兼容桥绕过。”

## README Check

已检查 README 触发规则。由于没有实施 production/tests 行为变更，`dayu/host/README.md` 与 `tests/README.md` 不需要同步。

## Residual Risks

| 风险 | 分类 | Owner / Destination |
|---|---|---|
| 旧 compact contract public symbols 仍在 production closeout files 中存在 | requiring new issue or explicit user decision | Controller 需要扩大本 gate allowed files，或把 compact artifact / memory projection / RunInputBuilder 依赖迁入同一 closure slice |
| `dayu/host/compact_artifact.py` 仍是旧 `CompactionCandidate` artifact writer，但 artifact store 测试在本 gate 必跑 | requiring new issue or explicit user decision | Controller 需要把该文件加入 allowed production files，或从本 gate 测试矩阵移除 artifact store closure |
| `memory.py` / `run_input.py` 对旧 symbols 的 import 使删除旧 public symbols无法 pyright-clean | covered by later approved slice, but blocking current closeout as written | 后续 Slice C 原 owner；若当前 gate 必须删除旧 symbols，则必须提前纳入本 gate |
| 外部 `ContextCompactor` implementor 会因 protocol 改为 vNext input/output 发生 public contract breakage | assigned to later work unit | Controller / public contract owner 需要在 closeout report 与后续 release notes 中明确 |

## Completion Status

blocked。未进入 code review、commit、push、PR 或其它 gate。
