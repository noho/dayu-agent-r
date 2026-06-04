# WU-CM-01 Compact Contract Closure Plan Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan review gate |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| plan artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| adjudication | `docs/reviews/wu-cm-01-slice-c-compact-contract-blocker-controller-adjudication.md` |
| reviewer | deepreview / AgentController |
| date | 2026-06-04 |
| review scope | 只做 plan review，不修改 production code / tests / docs |
| conclusion | **pass-with-findings** |

## 第一性原理判断

### 动机判断：成立

latest blocker 真实成立，不是 partial implementation 失败被高估。

**直接证据**：

- `dayu/host/compaction.py:2563` — `CompactionCandidate` 类定义仍存在，包含 `pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preservation_evidence` 等旧字段。
- `dayu/host/llm_compaction.py:234` — `LLMContextCompactor.compact()` 仍返回 `CompactionCandidate`，并解析 `pinned_state_patch_candidate`（line 122）、`minimum_preserve_item_candidates`（line 124）、`preservation_evidence`（line 125）。
- `dayu/host/context_governance.py:39` — `check_compaction_candidate()` 旧 production checker 仍接受 `CompactionCandidate` 参数并读取 `candidate.pinned_state_patch_candidate`。
- `dayu/host/compaction.py:1814` — `CompactMaterialPack` 顶层字段仍是 `stable_input`（line 1824）、`history_input`（line 1825）、`evidence_input`（line 1826），JSON 序列化仍输出这些旧 key（lines 1928-1944）。
- `dayu/host/compaction.py:145` — `CompactMaterialBlockKind` 仍包含 `PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY` 等旧枚举值。
- `dayu/host/context_events.py:56-59` — 仍定义 `_FIELD_PINNED_STATE_PATCH_CANDIDATE`、`_FIELD_PRESERVATION_EVIDENCE`、`_FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES` 旧 payload 字段常量。

**严重性评估正确**：旧 `CompactionCandidate`、旧 `CompactMaterialPack` 顶层字段和旧 `CompactMaterialBlockKind` 是 production direct owner — `LLMContextCompactor.compact()` 仍返回旧 candidate，`CompactMaterialPack` 的 JSON/LLM JSON 仍输出旧字段名。若在 Slice C 中删除旧 memory snapshot/policy 后再尝试 pyright-clean，compact material consumer 与 quality gate 仍引用旧 contract，会诱导旧 field alias、旧 wrapper 或旧 snapshot bridge。

### 前置 closure 是否过度切分：否

前置 closure 是正确的最小切分。当前 production compact contract 的真正状态是：

- `compaction_operation.py` 的 production closeout 路径已使用 `compact_request_vnext()` → `check_conversation_compact_output_vnext()`（vNext 路径）。
- 但 `LLMContextCompactor.compact()` 旧方法、`CompactionCandidate` 类型、旧 `CompactMaterialPack` 字段和旧 `CompactMaterialBlockKind` 枚举仍存在。
- 测试文件大量调用 `FakeContextCompactor().compact()`（旧接口，返回 `CompactionCandidate`）。

前置 Slice C 只关闭 compact material / parser / quality checker / operation closeout / payload 的旧 contract，不迁移 memory durable/projection/config-service — 这是正确的 scope 分离。把它合并进 Slice C 会制造跨 Slice A/B/C 的大迁移，违反 no-compat 约束。

## Blocking Findings

### B1: `tests/host/test_compact_artifact_store.py` 未在任何 slice 的 allowed files 中

**直接证据**：

```
tests/host/test_compact_artifact_store.py:26 — from dayu.host.compaction import CompactionCandidate
tests/host/test_compact_artifact_store.py:24 — from dayu.host.compaction import CompactMaterialBlockKind
tests/host/test_compact_artifact_store.py:30 — from dayu.host.context_governance import check_compaction_candidate
tests/host/test_compact_artifact_store.py:283 — candidate = await FakeContextCompactor().compact(request, StubCancellationToken())
tests/host/test_compact_artifact_store.py:284 — quality_result = check_compaction_candidate(request, candidate)
```

**影响**：Pre-Slice C 的退出信号要求 `rg "CompactionCandidate" dayu/host/compaction.py` 不再显示残留。若 `CompactionCandidate` 从 `compaction.py` 中删除（符合退出信号），`test_compact_artifact_store.py` 在第 26 行 import 失败。同理，`check_compaction_candidate` 若从 `context_governance.py` 删除，第 30 行也失败。

该文件不在任何 slice 的 allowed files 中：不在 Slice A、Slice B、Pre-Slice C、Slice C、Slice D。这意味着它成为 orphaned test — 随 Pre-Slice C 实施而断裂。

**修复建议**：

- **方案 A（推荐）**：将 `tests/host/test_compact_artifact_store.py` 加入 Pre-Slice C allowed files，并将其 compact candidate 构造与 quality check 断言同步迁移到 vNext（`compact_request_vnext()` + `ConversationCompactOutputVNext` + `check_conversation_compact_output_vnext()`）。
- **方案 B**：若该文件的 compact artifact store 测试的核心语义（artifact JSON 写入、digest 校验、store 读写）与 compact contract 无关，可将其收缩为只测试 artifact store I/O，改用 vNext `ConversationCompactOutputVNext` 构造输入，不再经过旧 `compact()` / `check_compaction_candidate()`。
- **方案 C**：在退出信号中明确 `CompactionCandidate` 可作为 "明确 unused 删除候选" 保留在 `compaction.py` 中，待 Slice B 补迁移 `test_compact_artifact_store.py` 后再删除。此方案需修改退出信号 grep 范围（排除 class 定义行），有扩散风险，不推荐。

### B2: `dayu/host/compaction_evidence.py` 无明确 slice owner

**直接证据**：

```
dayu/host/compaction_evidence.py:17 — from dayu.host.compaction import CompactMaterialBlockKind
dayu/host/compaction_evidence.py:310 — kind=CompactMaterialBlockKind.RAW_ASSISTANT_TURN
```

该文件在 "Allowed Files / Modules Summary"（plan line 513）中列出，但不在 Slice A、Slice B、Pre-Slice C、Slice C、Slice D 任一具体 slice 的 allowed files 中。

**影响**：Pre-Slice C 要求 `CompactMaterialBlockKind` production enum 删除旧 `PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY`。但 `compaction_evidence.py` 使用的是 `RAW_ASSISTANT_TURN`（非删除目标）。**当前 plan 下，该文件可能不被触碰即通过 pyright**，但存在两个风险：

1. 若 `CompactMaterialBlockKind` 枚举值重构（如从 material block kind 改为 vNext section enum），`RAW_ASSISTANT_TURN` 引用断裂。
2. 因为没有 owner slice，任何 future 修改都没有 gate 控制。

**修复建议**：

- 明确 `compaction_evidence.py` 的 slice owner。按职责（构造 `CompactionRequest` 的 material 输入），它最接近 Slice B（compact operation / event closeout）或 Pre-Slice C（compact contract closure）。建议加入 Slice B 或 Pre-Slice C 的 allowed files。
- 若 `RAW_ASSISTANT_TURN` 在 vNext 中按 plan Slice A 迁移表改为 trace/answer section label，则 `compaction_evidence.py` 的 `CompactMaterialBlockKind.RAW_ASSISTANT_TURN` 需要同 slice 同步迁移；否则 pyright 失败。

### B3: 退出信号 grep 范围与 class 定义删除的张力

**问题**：Pre-Slice C 退出信号要求：

```bash
rg "CompactionCandidate|PinnedStatePatchCandidate|MinimumPreserveItemCandidate|PreservationEvidence|pinned_state_patch_candidate|minimum_preserve_item_candidates|preservation_evidence" dayu/host/compaction.py dayu/host/llm_compaction.py dayu/host/context_governance.py dayu/host/compaction_operation.py dayu/host/context_events.py dayu/host/compact_payload.py
```

不再显示 production closeout 残留。

但 `CompactionCandidate` class 定义在 `dayu/host/compaction.py:2563`，`PinnedStatePatchCandidate` 在 `:2325`，`MinimumPreserveItemCandidate` 在 `:2503`，`PreservationEvidence` 在 `:2381`。上述 grep 会对 class 定义 body 命中。

**张力**：若严格满足退出信号（grep 无命中），必须删除这些 class 定义。但 plan 的实现边界只说 `compact()` 方法必须返回 vNext，并未明说删除 class。退出信号的 caveat "明确 unused 删除候选" 若指 class 定义本身，则 grep 仍会命中（class 定义不是 "unused"，而是 "正被定义"）。

**影响**：若实施者严格按退出信号删除 class 定义，`test_compact_artifact_store.py`（B1）和可能的其他未覆盖文件会断裂。若实施者保留 class 定义但仅注释标记 unused，退出信号 grep 不通过。

**修复建议**：

- 在退出信号中区分两类匹配：
  1. **production closeout 路径中的引用**（compact() 返回值、quality checker 参数、operation result 字段、event payload 构造）— 必须清零。
  2. **class/type 定义**（`class CompactionCandidate:` 等）— 可作为 "明确 unused 删除候选" 保留，implementation report 必须逐项解释为何保留及预期删除 owner。
- 等价做法：将退出信号改为 `rg ... -c` 计数 + 人工逐项 audit，不做盲目的零命中断言。

## Non-blocking Findings

### N1: `LLMContextCompactor` 存在两个 vNext 方法

**直接证据**：

```
dayu/host/llm_compaction.py:269 — async def compact_vnext(...) → ConversationCompactOutputVNext
dayu/host/llm_compaction.py:311 — async def compact_request_vnext(...) → ConversationCompactOutputVNext
dayu/host/llm_compaction.py:331 — return await self.compact_vnext(compact_input, cancellation_token)
```

`compact_request_vnext()` 是 `ContextCompactorVNext` protocol 的实现，内部委托给 `compact_vnext()`。同时旧 `compact()` 方法（line 234）仍存在并返回 `CompactionCandidate`。

**影响**：Pre-Slice C 实施时需决策：是删除 `compact()` + 重命名 `compact_vnext()` 为 `compact()`（变更 public API），还是保留 `compact_vnext()` 作为内部实现 + 让 `compact()` 和 `compact_request_vnext()` 都委派给它。plan 对此未明确。

**建议**：`compact()` 改为返回 `ConversationCompactOutputVNext`（或直接删除，让所有调用方迁移到 `compact_request_vnext()`）。`compact_vnext()` 可保留为内部 shared implementation 或合并入 `compact()`。

### N2: `compaction_operation.py` 类型注解使用旧 Protocol

**直接证据**：

```
dayu/host/compaction_operation.py:95 — compactor: ContextCompactor  # 旧 protocol, compact() → CompactionCandidate
dayu/host/compaction_operation.py:323 — if not isinstance(compactor, ContextCompactorVNext):  # 运行时检查 vNext protocol
```

类型注解声明接受 `ContextCompator`（旧 protocol），但运行时要求 `ContextCompactorVNext`。这是类型不安全的设计 — pyright 允许传入只实现旧 protocol 的对象，但运行时拒绝。

**建议**：将 `run_compaction_operation()` 的 `compactor` 参数类型改为 `ContextCompactorVNext`。这是 Pre-Slice C 的 natural cleanup，与 "production closeout 使用 vNext" 一致。

### N3: `test_llm_compaction.py` 迁移 scope 大

**直接证据**：`tests/host/test_llm_compaction.py` 中 ~30+ 个测试函数调用 `compactor.compact()`（旧方法，返回 `CompactionCandidate`），仅 2 个 vNext 测试（`test_llm_context_compactor_compact_vnext_uses_vnext_material` 等）。

**影响**：这些旧测试覆盖了旧 candidate 的各类解析路径（pinned patch、minimum preserve、preservation evidence、tool content 等）。迁移到 vNext 时，测试必须改写为使用 `compact_request_vnext()` 或 `compact_vnext()` 并断言 `ConversationCompactOutputVNext` 字段。这不是简单的搜索替换，需要理解 vNext candidate schema 并重写断言。plan 当前未估计迁移规模，但 allowed files 已覆盖此文件，所以分类为 non-blocking。

### N4: `context_events.py` 旧字段常量清理范围

**直接证据**：

```
dayu/host/context_events.py:56 — _FIELD_PINNED_STATE_PATCH_CANDIDATE = "pinned_state_patch_candidate"
dayu/host/context_events.py:57 — _FIELD_PRESERVATION_EVIDENCE = "preservation_evidence"
dayu/host/context_events.py:59 — _FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES = "minimum_preserve_item_candidates"
```

这些常量在 `context_events.py` 中定义，plan 将其列为 Pre-Slice C 的 conditionally allowed file（"仅当 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` payload reader / writer 需要同步 vNext closeout"）。若 Pre-Slice C 清理 `CONTEXT_COMPACTED` payload 的旧字段构造逻辑，这些常量应同步删除。

**建议**：在退出信号中显式包含 `context_events.py` 中旧 payload 字段常量的清理检查。

### N5: `test_compaction_contract.py` 仍大量使用旧 contract 断言

**直接证据**：

```
tests/host/test_compaction_contract.py:76 — candidate.pinned_state_patch_candidate.current_goal.operation
tests/host/test_compaction_contract.py:77 — len(candidate.preservation_evidence)
tests/host/test_compaction_contract.py:323 — candidate.preservation_evidence[0]
tests/host/test_compaction_contract.py:344 — candidate.pinned_state_patch_candidate
tests/host/test_compaction_contract.py:682 — candidate.minimum_preserve_item_candidates[0]
tests/host/test_compaction_contract.py:770 — minimum_preserve_items_accepted=True
```

这些测试经过 `FakeContextCompactor().compact()` 返回旧 `CompactionCandidate` 后断言旧字段。同时该文件也有 vNext 测试（从 line 959 起，使用 `ConversationCompactOutputVNext` 直接构造和 `_vnext_input()`）。

**影响**：该文件在 Pre-Slice C allowed files 中，但迁移工作量较大（约 40+ 旧 contract 测试需要重写或替换）。非阻塞因为已纳入 scope。

## Allowed Files Coverage Audit

### 覆盖充分的 compact production owner

| 文件 | Pre-Slice C | 关键旧 contract 残留 |
|---|---|---|
| `dayu/host/compaction.py` | 是 | `CompactionCandidate`, `CompactMaterialPack.stable/history/evidence_input`, `CompactMaterialBlockKind` 旧枚举值, `PinnedStatePatchCandidate` 等 |
| `dayu/host/llm_compaction.py` | 是 | `compact()` 返回 `CompactionCandidate`, `_candidate_from_final_answer()`, `_pinned_state_patch_candidate()` 等 parser |
| `dayu/host/context_governance.py` | 是 | `check_compaction_candidate()` 旧 checker, `CompactionCandidate` 参数类型 |
| `dayu/host/compact_material.py` | 是 | 从旧 `CompactMaterialPack` 字段转换 vNext input |
| `dayu/host/compaction_operation.py` | 是 | 类型注解用旧 `ContextCompactor` protocol |
| `dayu/host/context_events.py` | 条件 | `_FIELD_PINNED_STATE_PATCH_CANDIDATE` 等旧常量 |
| `dayu/host/compact_payload.py` | 条件 | 当前干净（无旧 contract 残留） |

### 覆盖缺口

| 文件 | 缺口类型 | Severity |
|---|---|---|
| `tests/host/test_compact_artifact_store.py` | 未在任何 slice allowed files 中 | **blocking** (B1) |
| `dayu/host/compaction_evidence.py` | 在 summary 但无具体 slice owner | **blocking** (B2) |
| `dayu/host/dispatch.py` | Pre-Slice C allowed（条件），当前已不再 import `CompactionCandidate` | covered |
| `dayu/host/engine_ingest.py` | Pre-Slice C allowed（条件），当前已不再 import `CompactionCandidate` | covered |

### 禁止项有效性检查

Pre-Slice C 禁止项覆盖了所有关键违规模式：

1. **旧 candidate type wrapper** — 禁止 `CompactionCandidate`、`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate` 等的 production wrapper/facade/re-export。**有效**。
2. **旧 material field alias** — 禁止 `stable_input`、`history_input`、`evidence_input` 的 field alias。**有效**。
3. **旧 block kind alias** — 禁止 `CompactMaterialBlockKind` enum alias 或旧到新的运行时桥。**有效**。
4. **旧 snapshot bridge** — 禁止 `ConversationMemorySnapshot` → vNext 和 vNext → 旧 snapshot 的 bridge。**有效**。
5. **Slice C 内容混入** — 禁止迁移 `memory.py`、`durable/memory.py`、`run_input.py`、`host_assembly.py`、`config_loader.py`。**有效**。
6. **类型逃逸** — 禁止 `hasattr`/`getattr`、无类型 dict、`Any`、lazy import、extra payload。**有效**。

**缺失的禁止项**：未显式禁止在 `llm_compaction.py` 中保留双 parser（同时解析旧 `CompactionCandidate` 和新 `ConversationCompactOutputVNext` 的代码路径）。建议补充：`llm_compaction.py` production parser 只保留 vNext 解析路径，旧 parser helper 函数（`_pinned_state_patch_candidate()`、`_minimum_preserve_item_candidates()`、`_preservation_evidence()`、`_candidate_from_final_answer()`）必须删除。

### 后续 Slice C 收窄检查

后续 Slice C（plan lines 304-435）已正确依赖前置 closure：

- "此 slice 不再承担 LLM parser、旧 `CompactionCandidate`、旧 `CompactMaterialPack` production closeout 或 compact event payload closure" — 正确。
- "`Pre-Slice C - Compact Contract Closure` 已保证 production compact material 顶层字段、LLM parser、quality checker、operation payload 和 event closeout 是 vNext；Slice C 只能消费该 vNext contract" — 正确。
- Slice C allowed files 不再包含 `llm_compaction.py`（LLM parser 已在前置 closure 中完成）— 正确。

## Exit Signal Audit

| 退出信号 | 可验证性 | 问题 |
|---|---|---|
| `rg "CompactionCandidate\|..." dayu/host/compaction.py ...` 不再显示残留 | 可直接运行 | B3：grep 命中 class 定义本身，与 "unused 删除候选" 矛盾 |
| `CompactMaterialPack` JSON 不再输出旧字段 | 可通过测试断言 | 无问题 |
| `LLMContextCompactor.compact()` 只返回 `ConversationCompactOutputVNext` | 可通过类型检查 | 无问题，但需决定旧 `compact()` 方法是改签名还是删除 |
| accepted/rejected/repair exhausted/fallback closeout 都用 vNext | 可通过测试断言 | 无问题 |
| 受影响 tests + pyright 全量通过 | 可直接运行 | 无问题，但 `test_compact_artifact_store.py` 不在受影响列表中将静默失败 |

## 测试命令覆盖检查

Pre-Slice C 测试命令：

```bash
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py -q
python -m pyright dayu/ tests/ utils/
```

**覆盖评估**：

- `test_compaction_contract.py` — 覆盖 candidate schema、quality checker、fail-closed 行为。**充分**。
- `test_llm_compaction.py` — 覆盖 LLM parser、strict JSON parse、provenance mapping。**充分**。
- `test_compaction_operation.py` — 覆盖 attempt/repair/closeout。**充分**。
- `test_compact_material.py` — 覆盖 material pack 构造与 section mapping。**充分**。

**缺失**：`test_compact_artifact_store.py` 不在测试命令中（B1）。

**条件追加**：plan 允许在 fake compaction 或 public compact material JSON 行为改变时追加 `test_public_compact_smoke.py`。此条件合理，因为 smoke 测试走 public path 且直接断言 material JSON。

## Residual Risk 完整性

Pre-Slice C 的 residual risks 正确识别了后续 owner：

- ConversationMemorySnapshot / durable / projection → Slice C
- public smoke / README → Slice D
- 完整 eval benchmark → WU-CM-10 / Issue #80

**缺失的 residual risk**：`ContextCompactor`（旧 protocol）删除后，任何外部实现该 protocol 的代码会断裂。当前未知是否有 Service 层或其他模块实现了 `ContextCompactor`。建议在 residual risks 中标注：`ContextCompactor` protocol 删除后，需确认无外部 implementor。

## 总结

| 类别 | 数量 | 关键项 |
|---|---|---|
| blocking | 3 | B1: `test_compact_artifact_store.py` orphaned; B2: `compaction_evidence.py` no slice owner; B3: exit signal grep vs class definition tension |
| non-blocking | 5 | N1: dual vNext methods; N2: old protocol type annotation; N3: test migration scope; N4: event constants cleanup; N5: contract test migration volume |

**结论：pass-with-findings**。

三个 blocking findings 均可在 plan 层面修复（调整 allowed files 列表、明确 slice owner、细化退出信号），不需要重新设计整体 slice 结构。修复后即可转入 implementation gate。

**Controller 裁决后**：根据裁决结果更新 `docs/host/wu-cm-01-conversation-memory-plan.md` 和 `docs/host/issues-implementation-control.md`，然后进入 `WU-CM-01 Pre-Slice C implementation gate`。
