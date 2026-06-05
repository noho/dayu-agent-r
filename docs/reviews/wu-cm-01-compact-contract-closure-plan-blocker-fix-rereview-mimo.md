# WU-CM-01 Compact Contract Closure Plan Blocker Fix Re-Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan blocker fix re-review |
| reviewer | AgentMiMo |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-blocker-controller-adjudication.md` |
| date | 2026-06-04 |

## Verdict

`fail`。

AgentCodex 的 plan blocker fix 正确处理了 Controller accepted findings 的诊断部分，但 fix 本身引入了一个新的可直接验证的 allowed files 缺口，使 Pre-Slice C 退出信号在当前 plan 下不可执行。

## Direct Evidence

### Finding 1 — `open_host.py` 与 `api.py` 缺失于 allowed files（blocker）

Controller accepted finding #3 要求 `ContextCompactor` 仓库内 production implementor / caller 全部收敛到单一 public `compact()` vNext contract。Fix artifact 列出了 owner 清单：

> `ContextCompactor` production owner 清单：`dayu/host/compaction.py`、`dayu/host/llm_compaction.py`、`dayu/host/open_host.py`、`dayu/host/api.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/compaction_operation.py`。

但 Pre-Slice C allowed production files 只包含：

> `dayu/host/compaction.py`、`dayu/host/llm_compaction.py`、`dayu/host/context_governance.py`、`dayu/host/compact_material.py`、`dayu/host/compaction_evidence.py`、`dayu/host/compaction_operation.py`、`dayu/host/context_events.py`、`dayu/host/compact_payload.py`、`dayu/host/compact_artifact.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/memory.py`、`dayu/host/run_input.py`。

代码直接证据：

- `dayu/host/api.py:34` — `from dayu.host.compaction import ContextCompactor`。该文件使用 `ContextCompactor` 作为 typed option field 类型。
- `dayu/host/open_host.py:75` — `from dayu.host.llm_compaction import LLMContextCompactor`。该文件在 `_local_execution_options_from_open_host_options` 中构造 `LLMContextCompactor` 实例并传入 `HostLocalExecutionOptions`。

若 `ContextCompactor.compact()` 签名从 `-> CompactionCandidate` 改为 `-> ConversationCompactOutputVNext`（Pre-Slice C 退出信号要求），`api.py` 的 typed field annotation 和 `open_host.py` 的构造代码都会因旧 `CompactionCandidate` 返回值类型删除而无法 pyright-clean。这两个文件不在 allowed files 内，implementation agent 无法修改它们。

后果：implementation agent 只能走两条不合格路径之一：

1. 不改 `ContextCompactor` protocol，保留 `compact() -> CompactionCandidate`，违反退出信号。
2. 改了 protocol 但不改 `api.py` / `open_host.py`，pyright 失败，违反验证要求。

### Finding 2 — `CompactMaterialBlockKind` 旧 enum member 删除与 `run_input.py` dependency severance 边界模糊（non-blocking）

`run_input.py:63-66` 导入 `CompactMaterialBlockKind` 和 `CompactMaterialSection`。Pre-Slice C 实现边界要求 `run_input.py` "不得继续引用旧 `CompactMaterialBlockKind.PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY` 等旧 mental model"。

但 fix artifact 的 dependency severance 描述只说"不得继续从 `dayu.host.compaction` 导入或引用旧 compact public symbols"。`CompactMaterialBlockKind` 和 `CompactMaterialSection` 是 material contract enum，不是 compact candidate 类型。它们是否属于"旧 compact public symbols"有歧义。

若属于：`run_input.py` 必须停止导入它们，但 material rendering 依赖这些 enum，severance 实际上等同于 RunInputBuilder vNext memory section 渲染迁移，超出 dependency severance 范围。

若不属于：`run_input.py` 可以继续导入它们，但 plan 禁止项要求删除 `PINNED_STATE`、`WORKING_ASSUMPTION` 等旧 enum members，`run_input.py` 仍引用这些 members 时会因 enum member 删除而 pyright 失败。

两种解释都会在 implementation 中产生问题，但严重性低于 Finding 1，因为 implementation agent 可以在实现时自行裁决将 `run_input.py` 中对旧 enum members 的引用替换为 vNext section 分类 helper。

### Finding 3 — `test_package_exports.py` 条件触发确认（non-blocking）

Fix artifact 正确列出 `tests/host/test_package_exports.py` 为条件测试："仅当 compact public exports 变化"。Pre-Slice C 会从 `compaction.py` 的 `__all__` 删除旧 symbols，这必然触发 public exports 变化。Plan 的测试命令和退出信号已覆盖此条件。Implementation agent 只需记住在删除旧 `__all__` entries 时运行该测试。

## Accepted Findings Handling 逐项验证

### Controller Finding #1 — `compact_artifact.py` owner 缺失

Fix: Pre-Slice C allowed production files 明确加入 `compact_artifact.py`。

代码验证：`compact_artifact.py:15-22` 确实导入 `CompactQualityCheckResult`、`CompactionCandidate`、`EvidenceBackedFactCandidate`、`MinimumPreserveItemCandidate`。`CompactArtifactWriteRequest` 的 `accepted_candidate: CompactionCandidate` 和 `quality_result: CompactQualityCheckResult` 必须迁移到 vNext output / vNext quality result。

结论：accepted-fixed，诊断正确，处理方案合理。

### Controller Finding #2 — 删除旧 public compact symbols 牵连 `memory.py` / `run_input.py`

Fix: Pre-Slice C allowed files 明确加入 `memory.py` 和 `run_input.py`，只允许 dependency severance。

代码验证：
- `memory.py:16-22` 导入 `EvidenceBackedFactCandidate`、`EvidenceBackedFactKind`、`MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`。
- `run_input.py:63-66` 导入 `CompactMaterialBlockKind`、`CompactMaterialSection`。

其中 `MinimumPreserveItemCandidate` 和 `MinimumPreserveReason` 是明确的旧 compact candidate 类型，severance 方案（memory-owned typed shape 替代）可行。`EvidenceBackedFactCandidate` / `EvidenceBackedFactKind` 是 vNext schema 类型，不需在 Pre-Slice C severance。

`run_input.py` 的 `CompactMaterialBlockKind` / `CompactMaterialSection` 边界见 Finding 2。

结论：accepted-fixed，诊断正确，memory.py severance 方案合理。run_input.py 边界有轻微歧义但 non-blocking。

### Controller Finding #3 — `ContextCompactor` 双 public method closeout 受旧 callers 牵制

Fix: Pre-Slice C 新增 production implementor / caller owner 清单，要求收敛到单一 public `compact()` vNext contract。

代码验证：owner 清单本身完整准确。`LLMContextCompactor` 确实有 `compact()`、`compact_vnext()`、`compact_request_vnext()` 三个 public method。`compaction_operation.py`、`engine_ingest.py`、`api.py`、`open_host.py` 确实是 production caller / construction owner。

但 allowed files 缺少 `open_host.py` 和 `api.py`（见 Finding 1），使该 fix 在 implementation 中不可执行。

结论：诊断正确，fix 方案不完整。必须把 `open_host.py` 和 `api.py` 纳入 Pre-Slice C allowed production files。

## Design Source 24/25 章一致性

Fix artifact 的处理方向与 design source 一致：

- 第 24.3 章要求 `ConversationCompactOutputVNext` 作为 compactor 唯一输出 schema，与 fix 要求收敛到 vNext contract 一致。
- 第 25 章要求 Context Governance 只接受 vNext candidate，与 fix 要求 `check_conversation_compact_output_vnext()` 替代 `check_compaction_candidate()` 一致。
- Fix 不引入 compatibility wrapper / alias / re-export，与 design 禁止兼容性代码一致。

## Slice C 边界同步

Fix artifact 正确缩小了 Slice C 边界：

- Slice C 不再承担 compact artifact writer、compact event payload closure 或旧 compact public symbol deletion。
- Slice C 只消费 Pre-Slice C 已闭合的 vNext compact event / artifact。
- Deferred owner list 与 Slice C 目标一致。

## 退出信号可执行性

| 退出信号 | 可执行 | 说明 |
|---|---|---|
| 旧 candidate/type/helper 在 production closeout files 中不得有 class definition、public export 或 production reference | 受阻 | `open_host.py` 和 `api.py` 未纳入 allowed files，删除 `CompactionCandidate` 后这些文件无法 pyright-clean |
| `memory.py` 与 `run_input.py` 不再从 `dayu.host.compaction` 导入旧 compact public symbols | 部分可执行 | `memory.py` 的 `MinimumPreserveItemCandidate` / `MinimumPreserveReason` severance 可执行；`run_input.py` 的 `CompactMaterialBlockKind` 边界有歧义 |
| `ContextCompactor` 收敛到单一 public `compact()` vNext contract | 受阻 | 同 Finding 1 |
| `CompactMaterialPack` JSON 不再输出旧字段 | 可执行 | 只涉及 `compaction.py` 和 `compact_material.py`，均在 allowed files 内 |
| `LLMContextCompactor.compact()` 只返回 vNext output | 受阻 | 同 Finding 1，protocol 改动牵连 `api.py` / `open_host.py` |
| `context_governance.py` 使用 vNext checker | 可执行 | `check_conversation_compact_output_vnext()` 已存在 |
| `compact_artifact.py` 写 vNext output / quality result | 可执行 | 已纳入 allowed files |
| Tests 通过 | 部分可执行 | `fake_compaction.py` 的 `CompactionCandidate` import 必须同步迁移 |

## Conclusion

`fail`。

- **Blocker**: `open_host.py` 和 `api.py` 缺失于 Pre-Slice C allowed production files。这两个文件直接 import `ContextCompactor`，protocol 改动后无法 pyright-clean。Fix artifact 的 owner 清单已正确列出这两个文件，但 allowed files 未同步更新。
- **Non-blocking**: `run_input.py` 对 `CompactMaterialBlockKind` 的 dependency severance 边界有轻微歧义，implementation agent 可在实现时裁决。
- **Non-blocking**: `test_package_exports.py` 条件触发已正确覆盖，implementation agent 只需在删除旧 `__all__` entries 时运行。

Fix 要求：Pre-Slice C allowed production files 必须增补 `dayu/host/open_host.py`（仅限 `ContextCompactor` / `LLMContextCompactor` construction 迁移）和 `dayu/host/api.py`（仅限 `ContextCompactor` typed option field 迁移）。同时应明确 `run_input.py` 的 `CompactMaterialBlockKind` 旧 enum members 引用在 enum members 删除前必须替换为 vNext section 分类 helper 或本模块私有分类。
