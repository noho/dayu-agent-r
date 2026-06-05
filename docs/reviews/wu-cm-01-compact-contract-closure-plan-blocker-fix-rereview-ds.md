# WU-CM-01 Compact Contract Closure Plan Blocker Fix Re-Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan blocker fix re-review |
| reviewer | AgentDS |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| implementation blocker artifact | `docs/reviews/wu-cm-01-compact-contract-closure-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-blocker-controller-adjudication.md` |
| plan blocker fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-codex.md` |
| artifact path | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-ds.md` |
| conclusion | pass-with-findings |

## Scope Judgment

本次 re-review 只判断 AgentCodex 的 plan blocker fix 是否完整处理了 Controller accepted findings，并判断新的 Pre-Slice C 是否可进入 implementation。不修改 production code、tests、README、plan 或 control doc。

## Controller Accepted Findings 处理完整性

### Finding 1: `compact_artifact.py` owner 缺失

**裁决**: accepted-fixed，处理完整。

直接代码证据：

- `dayu/host/compact_artifact.py:15-22` 仍从 `dayu.host.compaction` import `CompactQualityCheckResult`、`CompactionCandidate`、`EvidenceBackedFactCandidate`、`MinimumPreserveItemCandidate`，`CompactArtifactWriteRequest` 仍以旧 candidate / 旧 quality result 为 production 类型。
- `tests/host/test_compact_artifact_store.py` 存在 5 个测试函数，已纳入 Pre-Slice C 必跑测试。
- Plan fix 已将 `dayu/host/compact_artifact.py` 加入 Pre-Slice C allowed production files，并要求 `CompactArtifactWriteRequest`、artifact canonical JSON 和 descriptor metadata 从旧 candidate / quality result 迁移到 vNext output / vNext quality result。
- 实现边界明确禁止 "不得把 vNext output 先转换成旧 candidate 再写 artifact"。

该 finding 已完整闭合，无 residual gap。

### Finding 2: 删除旧 public compact symbols 牵连 `memory.py` / `run_input.py`

**裁决**: accepted-fixed，处理完整。

直接代码证据：

- `dayu/host/memory.py:16-22` 从 `dayu.host.compaction` import `EvidenceBackedFactCandidate`、`EvidenceBackedFactKind`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`，并在 projection 中直接构造 minimum preserve candidate。
- `dayu/host/run_input.py:63-66` 从 `dayu.host.compaction` import `CompactMaterialBlockKind`、`CompactMaterialSection`，并在 material rendering 中使用 `PINNED_STATE`、`WORKING_ASSUMPTION`、`EPISODE_SUMMARY` 等旧 enum。
- Plan fix 已将这两个文件加入 allowed files，但仅限 "断开对旧 compact public symbols 的直接 import / annotation / construction 依赖"。
- 退出信号要求二者 "不再从 `dayu.host.compaction` 导入或引用旧 compact public symbols"。
- 实现边界明确："若当前仍需表达局部承接原因或历史 item shape，必须改为 memory-owned typed shape"；"若当前仍需构造 selected recent window / current input material 时，必须使用 vNext material section typed API 或本模块私有分类 helper"。

该 finding 已完整闭合。scope 限制严格：dependency severance only，不迁 durable/projection、prompt assembly、config-service。边界清晰，不会诱导 Slice C 提前迁移。

### Finding 3: `ContextCompactor` 双 public method closeout 受旧 callers 牵制

**裁决**: accepted-fixed，处理完整但有 residual finding（见下方 non-blocking findings）。

直接代码证据：

- `dayu/host/compaction.py:2792` 定义 `ContextCompactor(Protocol)` 含 `compact()` 返回 `CompactionCandidate`。
- `dayu/host/compaction.py:2812` 定义 `ContextCompactorVNext(Protocol)` 含 `compact_request_vnext()` 返回 `ConversationCompactOutputVNext`。
- `dayu/host/compaction_operation.py:323-324` 仍做 `isinstance(compactor, ContextCompactorVNext)` 检查并调用 `compactor.compact_request_vnext()`。
- Plan fix 已列出仓库内 production implementor / caller owner 清单，并要求同 gate 收敛到单一 public `compact()` vNext contract。
- `compact_request_vnext()` / `compact_vnext()` 不得作为 public protocol / production method 保留。

该 finding 已完整闭合。

## 额外检查项

### 1. `compact_artifact.py` 与 `test_compact_artifact_store.py` 闭合

**结果**: 通过。

- production writer `dayu/host/compact_artifact.py` 已纳入 allowed files，要求迁移到 vNext。
- 对应测试 `tests/host/test_compact_artifact_store.py` 在 Pre-Slice C 必跑测试矩阵中。
- 实现边界明确禁止 vNext -> old candidate adapter；artifact JSON 必须从 vNext output / vNext quality result 直接写入。
- 闭合条件成立。

### 2. `memory.py` / `run_input.py` 新增范围是否足够且不越界

**结果**: 通过。

- `memory.py` 只允许断开旧 compact symbol import/annotation/construction；不得迁移 snapshot shape、durable item kind、projection algorithm、policy schema 或 repair path。
- `run_input.py` 只允许断开旧 compact material public enum/section 的 import/annotation/construction；不得迁移 vNext memory section 渲染、prompt assembly 顺序或 fallback 语义。
- 新增测试 `test_memory_projection.py` 与 `test_run_input_builder.py` 仅限 fixture/assertion 迁移，"不得把 full vNext memory prompt assembly 提前纳入本 gate"。
- 上述 scope 足够支撑旧 public symbol 删除后 pyright-clean，且不越界到 Slice C 的 durable/projection/config-service 内容。

### 3. `ContextCompactor` owner 清单与 allowed files 一致性

**结果**: 通过，有 non-blocking finding。

Plan 第 276 行列出的 ContextCompactor owner 清单包括 `open_host.py`（production construction owner）和 `api.py`（typed option owner），以及 `test_dispatch_scheduler.py` 和 `test_engine_ingest_mapping.py`（test implementor/caller owner），但这些文件均不在 Pre-Slice C allowed files 或必跑测试中。

经代码核对：
- `open_host.py:75` import `LLMContextCompactor`，`open_host.py:847` 构造 `LLMContextCompactor(...)`。
- `api.py:34` import `ContextCompactor`，`api.py:750` 声明 `context_compactor: ContextCompactor | None = None`。

若 `ContextCompactor.compact()` 只改返回值类型而不改参数签名，且 `LLMContextCompactor.__init__` 不需要新增 vNext 构造参数，则这两个文件**不需要 code change**——Protocol 是 structural type，类型变更由 `compaction.py` 表达，`api.py` 的类型注解自动跟随。`open_host.py` 的构造调用的参数不变则无需修改。

同理，`dispatch.py` 和 `engine_ingest.py` 的修改条件是 "仅当 proactive / reactive compact closeout 仍受旧 contract 影响时同步迁移"；若 compact event/artifact closeout 在修改 `compaction_operation.py` 与 `compact_artifact.py` 后已闭合，可能不需要改动 `dispatch.py` / `engine_ingest.py`，其对应测试自然也不需要进入必跑矩阵。

但 plan 把 `open_host.py`、`api.py` 列为 owner 而未纳入 allowed files，会造成 implementation agent 的二义性：如果实现中发现需要修改这些文件，会再次触发 blocker。见下方 non-blocking finding F-1。

### 4. 旧 public symbol 删除 exit signal 可执行性

**结果**: 通过。

Plan Pre-Slice C 退出信号要求：
- 旧 candidate / type / helper 在 production closeout files 中不得再有 class definition、public export 或 production reference。
- production closeout files 明确定义为 `compaction.py`、`llm_compaction.py`、`context_governance.py`、`compaction_operation.py`、`context_events.py`、`compact_payload.py`、`compact_artifact.py`、`compact_material.py`、`compaction_evidence.py`。
- `memory.py` 与 `run_input.py` 不得再 import 或引用旧 compact public symbols。

当前 `__all__`（`compaction.py:3814-3892`）仍导出旧符号：`CompactionCandidate`、`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`、`PinnedPatchOperation`、`PinnedStringTupleFieldPatch`、`PinnedTextFieldPatch`、`PreservationEvidence`、`CompactQualityCheckResult`、`CompactQualityIssue`，以及旧常量 `MAX_MINIMUM_PRESERVE_*`、`MAX_EVIDENCE_BACKED_FACT_*`。

扩展 owner 后，这些旧符号的 import/annotation/construction 依赖 graph 已全部被 allowed files 覆盖。exit signal 可执行。Plan 未使用 wrapper、alias、re-export 或旧 snapshot bridge 绕过。

注意 `EvidenceBackedFactCandidate` 在 plan 中同时出现在旧符号列表（via `compaction.py __all__` 导出）和 vNext 语境中（design 24.3 定义了 `EvidenceBackedFactCandidate`）。若当前 `EvidenceBackedFactCandidate` 的定义与 vNext schema 一致，则可以保留并重定向；若不一致，必须迁移到 vNext shape 并删除旧定义。Plan 未单独裁决此符号的迁移策略——它属于 `compaction.py` allowed scope 内的实现决策，但 implementation agent 必须在 slince closeout 时给出明确裁决。

### 5. 新 tests 充分性且不越界

**结果**: 通过。

| 新增/变更测试 | scope | 越界风险 |
|---|---|---|
| `test_compact_artifact_store.py` | vNext candidate / quality check / material JSON 迁移 | 无——artifact writer closure 属于 compact governance 闭环 |
| `test_memory_projection.py` | 仅限旧 compact symbol dependency severance 所需 fixture/assertion 迁移 | 无——明确禁止迁移 vNext snapshot durable behavior |
| `test_run_input_builder.py` | 仅限旧 compact material symbol dependency severance 所需 fixture/assertion 迁移 | 无——明确禁止把 full vNext memory prompt assembly 提前纳入 |
| `test_package_exports.py` | 条件触发：仅当 compact public exports 变化 | 无 |

所有新增测试 scope 均有明确上限，不越界到 Slice C 的 memory durable/projection、prompt assembly 或 config-service。

### 6. Slice C 边界缩小

**结果**: 通过。

Plan fix 已更新 Slice C 目标：
- Slice C "不再承担 LLM parser、旧 `CompactionCandidate`、旧 `CompactMaterialPack` production closeout、compact artifact writer、compact event payload closure 或旧 compact public symbol deletion"。
- Slice C 只消费 Pre-Slice C 已闭合的 vNext compact event / artifact。
- `compact_artifact.py` 在 Allowed Files Summary 中标注 "仅限 Pre-Slice C compact artifact writer vNext 迁移；后续 Slice C 不得重新打开 artifact writer 旧 candidate 兼容读取"。

不会重复打开 compact artifact writer 或旧 compact symbol deletion。

### 7. 与 `docs/host/design.md` 第 24 / 25 章一致性

**结果**: 通过。

- 第 24.3 章定义 `ConversationCompactInputVNext` / `ConversationCompactOutputVNext` contract：plan Pre-Slice C 的 vNext compact I/O 对齐。
- 第 24.4 章定义 `ConversationMemorySnapshotVNext` typed schema：plan 将此归入 Slice C，Pre-Slice C 不迁移。
- 第 24.6 章 prompt assembly 固定顺序：plan 将此归入 Slice C RunInputBuilder，Pre-Slice C 不迁移。
- 第 25 章 Context Governance accept barrier、whole-candidate repair、fallback 不生成高阶语义：plan Pre-Slice C 的 quality checker vNext migration 对齐第 25 章 compactor 输出 accept barrier。
- 第 25 章 `CONTEXT_COMPACTED` payload 字段对齐：plan Pre-Slice C 的 `context_events.py` / `compact_payload.py` 迁移对齐。

无矛盾。

## Non-Blocking Findings

### F-1: ContextCompactor owner 清单与 allowed files 不完全一致

**严重性**: 低。**分类**: non-blocking。

**证据**:
- Plan Pre-Slice C 第 276 行列 `open_host.py`（production construction owner）、`api.py`（typed option owner）为 ContextCompactor 同 gate owner。
- Plan Pre-Slice C 第 276 行列 `tests/host/test_dispatch_scheduler.py`、`tests/host/test_engine_ingest_mapping.py` 为 test implementor/caller owner。
- 上述 4 个文件均不在 Pre-Slice C allowed files 或必跑测试命令中。

**分析**: 若 `LLMContextCompactor.__init__` 不需要新增 vNext 构造参数，且 `dispatch.py`/`engine_ingest.py` 的 compact closeout 路径不受影响，则这些文件确实不需要 code change。但 plan 将它们列为 owner 而未说明是否需要变更，会造成 implementation agent 的二义性——若实现中发现需要改，会再次触发 allowed files 不足的 blocker。

**建议**: 在进入 implementation gate 前，plan 应明确说明：
- `open_host.py` / `api.py` 在什么条件下需要修改、什么条件下不需要。
- `test_dispatch_scheduler.py` / `test_engine_ingest_mapping.py` 在什么条件下需要进入必跑测试矩阵。
- 或者在 allowed files 中预留这两个文件（仅当 ContextCompactor constructor / protocol signature 需要变更时），以防止二次 blocker。

### F-2: `EvidenceBackedFactCandidate` 符号迁移策略未单独裁决

**严重性**: 低。**分类**: non-blocking。

**证据**:
- `EvidenceBackedFactCandidate` 当前在 `compaction.py` 中定义并从 `__all__` 导出。
- Design 24.3 也定义了 `EvidenceBackedFactCandidate` 作为 vNext output candidate 的一部分。
- Plan 的旧符号删除列表列出了 `CompactionCandidate`、`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate` 等，但对 `EvidenceBackedFactCandidate` 的处置未单独裁决——它是否与 vNext schema 一致、应该保留还是删除重建。

**分析**: 这是 `compaction.py` allowed scope 内的实现决策，plan 不需要穷举每个符号的处置。但 implementation agent 必须在 closeout 时给出明确裁决，不能让新旧 `EvidenceBackedFactCandidate` 定义并存或通过 alias 过渡。

## 结论

**pass-with-findings**。

AgentCodex 的 plan blocker fix 完整处理了 Controller 的三项 accepted findings：

1. `compact_artifact.py` owner 缺失 → 已纳入 allowed files，production writer 与 test 闭合。
2. `memory.py` / `run_input.py` 旧 symbol 依赖 → 已纳入 allowed files，dependency severance 范围严格。
3. `ContextCompactor` 双 public method closeout → 已列出 owner 清单，要求单 `compact()` vNext contract 收敛。

两项 non-blocking findings（F-1, F-2）不阻塞进入 implementation gate，但建议在 implementation 启动前澄清 F-1，避免二次 blocker。

新的 Pre-Slice C 可以进入 implementation，前提是 implementation agent 遵守 allowed files 边界、禁止项和退出信号。
