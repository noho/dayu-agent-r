# WU-CM-01 Compact Contract Closure Plan Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan review |
| design source | `docs/host/design.md` 第 24 / 25 章 |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| plan artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-c-compact-contract-blocker-controller-adjudication.md` |
| reviewer | mimo |
| date | 2026-06-04 |
| result | **pass-with-findings** |

## 审查范围

本 review 从第一性原理审查 `Pre-Slice C - Compact Contract Closure` 是否必要、充分、最小且 code-generation-ready。审查依据：

- design source 第 24.3 章 vNext Compact I/O Contract
- design source 第 25 章 Context Governance
- 当前 production 代码直接验证（6 个生产文件 + 6 个测试文件）
- blocker artifact 的 138 pyright errors 直接证据
- controller 裁决的 `accepted-blocker` 判定

---

## Finding 1：exit signals 未显式列出受旧类型删除影响的关键测试文件

**严重性：non-blocking（建议改进）**

**问题：** Pre-Slice C 的测试命令（plan 第 278 行）已正确包含 `test_compaction_operation.py`：

```bash
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py \
  tests/host/test_compaction_operation.py tests/host/test_compact_material.py -q
```

但 exit signals（第 292-296 行）以"受影响 tests 与全量 pyright 通过"一笔带过，未显式列出该文件。鉴于 `test_compaction_operation.py` 导入了 6 个 Pre-Slice C 计划删除的旧类型，显式列出有助于实现 agent 理解迁移边界。

**直接证据：** `tests/host/test_compaction_operation.py` 第 20-35 行：

```python
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactSegmentTrigger,
    CompactQualityCheckResultVNext,
    CompactQualityIssueVNext,
    CompactionCandidate,          # Pre-Slice C 删除目标
    CompactionRequest,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
    EpisodeSummaryCandidate,      # Pre-Slice C 删除目标
    PinnedPatchOperation,         # Pre-Slice C 删除目标
    PinnedStatePatchCandidate,    # Pre-Slice C 删除目标
    PinnedStringTupleFieldPatch,  # Pre-Slice C 删除目标
    PinnedTextFieldPatch,         # Pre-Slice C 删除目标
    PreservationEvidence,         # Pre-Slice C 删除目标
)
```

该文件导入了 6 个 Pre-Slice C 计划删除的旧类型。若 `compaction.py` 删除这些类型但不同步迁移此测试，pyright 会报 import error。测试命令已包含该文件，但 exit signals 应明确将其列为必须通过的测试。

**修复建议：** 在 exit signals 中将"受影响 tests"改为显式列表：

```
- 受影响 tests（test_compaction_contract.py、test_llm_compaction.py、
  test_compaction_operation.py、test_compact_material.py）与全量 pyright 通过；
  若 context_events.py 或 compact_payload.py 被触碰，同 slice 追加
  test_context_compact_events.py。
```

---

## Finding 2：exit signals 缺少 vNext positive adoption 验证

**严重性：non-blocking（建议改进）**

**问题：** Pre-Slice C 的 exit signals 以 negative verification 为主——验证旧符号已删除（`rg` grep 不再匹配）。缺少 positive verification 确认 vNext 路径已实际成为 production 入口。

**当前 exit signals：**

1. `rg` 旧符号不再出现在 production closeout 文件（negative）
2. `CompactMaterialPack` 不再输出旧字段（negative）
3. `LLMContextCompactor.compact()` 只返回 vNext（positive，但仅针对 parser）
4. accepted/rejected/repair/fallback 使用 vNext（positive，但描述笼统）
5. 受影响 tests + pyright 通过（verification）

**缺失的 positive signal：**

- `context_governance.py` 的 production accept barrier 是否已切换到 `check_conversation_compact_output_vnext()`（而非只是删除旧 `check_compaction_candidate()`）
- `compaction_operation.py` 的 attempt result / repair retry / quality issue 是否统一使用 vNext candidate（该文件已是 vNext-only，但 exit signal 未确认其与 Pre-Slice C 的一致性）

**影响：** 实现 agent 可能通过删除旧代码让 grep 通过，但未正确接入 vNext checker，导致 production 路径断开。

**修复建议：** 在 exit signals 中增加：

```
- `context_governance.py` 的 production accept barrier 入口为
  `check_conversation_compact_output_vnext()` 或等价 vNext checker；
  `check_compaction_candidate()` 不再作为 production closeout 入口。
  可通过 grep 确认 production 调用路径。
```

---

## Challenge 1 结论：latest blocker 真实成立

**判定：blocker 成立，严重性评估正确。**

直接代码验证确认以下旧 production contract 残留：

| 文件 | 旧符号 | 严重性 |
|---|---|---|
| `compaction.py` | `CompactionCandidate`、`PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`PreservationEvidence` 及全部字段 | 生产类型定义，28+ 处引用 |
| `llm_compaction.py` | `pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preservation_evidence` 字符串常量 | parser 字段映射 |
| `context_governance.py` | `check_compaction_candidate()`、`pinned_state_patch_candidate`、`stable_input`、`history_input` | 生产 quality checker 入口 |
| `compact_material.py` | `CompactMaterialPack`（`stable_input`/`history_input`/`evidence_input`）、`CompactMaterialBlockKind`（`PINNED_STATE`/`WORKING_ASSUMPTION`/`OPEN_QUESTION`/`EPISODE_SUMMARY`）、`_stable_blocks_from_snapshot()` | 生产 material 构造 |
| 6 个测试文件 | 全部绑定旧 candidate / material / block kind | 测试 fixture |

这不是测试 fixture 落后，也不是 Slice C 可局部止血的类型错误。旧 `CompactionCandidate` 是 `LLMContextCompactor.compact()` 的返回类型、`check_compaction_candidate()` 的输入类型、`compaction_operation.py` 的候选处理类型。删除旧 memory snapshot / policy 后，这些旧类型仍被生产路径引用，pyright 必然报错。

blocker artifact 的 138 pyright errors 是直接证据，不是环境噪声。

---

## Challenge 2 结论：Pre-Slice C 独立性成立

**判定：不过度切分。**

理由：

1. **production owner 清晰：** 旧 compact contract 的 production owner 是 `compaction.py`、`llm_compaction.py`、`context_governance.py`、`compact_material.py`。这 4 个文件构成一个独立的 contract domain：request material → LLM proposal → quality gate → candidate output。

2. **blocker 已证明混合不可行：** AgentCodex 的 partial implementation 尝试同时迁移 memory snapshot / policy / RunInputBuilder 和 compact contract，结果 138 pyright errors。混合迁移会把 Slice C 变成跨 Slice A/B/C 的大迁移。

3. **后续 Slice C 正确收窄：** Slice C 已明确"不再承担 LLM parser、旧 `CompactionCandidate`、旧 `CompactMaterialPack` production closeout 或 compact event payload closure"（plan 第 306 行）。residual risks 正确标注 owner。

4. **compaction_operation.py 已是 vNext-only：** 该文件已不包含旧符号，说明 Pre-Slice C 的 scope 聚焦在真正需要迁移的 4 个生产文件上，而非人为扩大。

---

## Challenge 3 结论：allowed files 覆盖完整

**判定：覆盖全部 compact production owner，未越界。**

production owner 映射：

| 生产文件 | 旧 contract 残留 | Pre-Slice C 包含 | 验证结果 |
|---|---|---|---|
| `compaction.py` | `CompactionCandidate`、旧 candidate 类型 | 是 | 已验证存在 |
| `llm_compaction.py` | 旧 parser 字段映射 | 是 | 已验证存在 |
| `context_governance.py` | `check_compaction_candidate()`、旧 material 读取 | 是 | 已验证存在 |
| `compact_material.py` | `CompactMaterialPack`、`CompactMaterialBlockKind`、旧 stable blocks | 是 | 已验证存在 |
| `compaction_operation.py` | 无（已是 vNext-only） | 是（allowed，无需修改） | 已验证清洁 |
| `context_events.py` | 旧字段常量（仅 reject guard） | 条件包含 | 已验证为 guard-rail |
| `compact_payload.py` | 2 个 legacy reader（Slice D owner） | 条件包含 | 已验证为 compat shim |
| `dispatch.py` | 无 | 条件包含 | 已验证清洁 |
| `engine_ingest.py` | 无 | 条件包含 | 已验证清洁 |

**未错误排除的文件：**

- `compaction_evidence.py`：vNext-only，无需包含
- `context_policy.py`：vNext-only，无需包含
- `memory.py`、`durable/memory.py`、`run_input.py`：Slice C owner，正确排除

---

## Challenge 4 结论：禁止项充分

**判定：禁止项覆盖主要兼容性风险。**

逐项分析：

| 禁止项 | 防止的风险 | 评估 |
|---|---|---|
| 旧 `CompactionCandidate` 等 wrapper / facade / re-export | 旧 candidate 伪装成 vNext | 充分 |
| 旧 material fields alias / JSON alias / payload alias / test helper alias | `stable_input` 等字段借壳保留 | 充分 |
| 旧 `CompactMaterialBlockKind` enum alias 或运行时兼容桥 | 旧 block kind 到 vNext section 的隐式映射 | 充分 |
| 旧 snapshot bridge | `ConversationMemorySnapshot` → vNext 双向 helper | 充分 |
| 混入 Slice C 内容 | `memory.py`、`run_input.py`、`config_loader.py` 等被提前迁移 | 充分 |
| `hasattr` / `getattr`、无类型 dict、`Any`、lazy import、extra payload | 类型逃逸 | 充分 |

**migration table 验证：** plan 第 125-126 行的旧 block kind → vNext section 映射表与 design 24.3 对齐：

- `PINNED_STATE` / `WORKING_ASSUMPTION` → 删除（design 24.5 无对应语义）
- `EVIDENCE_BACKED_FACT` → `previous_compacted_view.evidence_backed_facts`
- `OPEN_QUESTION` → accepted vNext forward intent
- `RAW_USER_TURN` → `trace_material`
- `EPISODE_SUMMARY` → accepted vNext session summary
- `ACCEPTED_TOOL_EVIDENCE` → `evidence_material`
- `CURRENT_INPUT_ANCHOR` → 不可引用

映射表与 design 一致。

---

## Challenge 5 结论：未错误排除或混入

**判定：未错误排除必须同步的文件；未混入后续 Slice C 内容。**

**排除文件验证：**

- `compaction_evidence.py`（vNext-only）：grep 确认无旧符号，正确排除
- `context_policy.py`（vNext-only）：不在 Pre-Slice C scope，正确排除
- `memory.py`、`durable/memory.py`、`run_input.py`：Slice C owner，plan 明确禁止混入（第 271 行）

**混入检查：**

- Pre-Slice C 的实现边界（第 254-262 行）明确不迁移 `memory.py`、`durable/memory.py`、`run_input.py`、`host_assembly.py`、`config_loader.py`、`execution_profiles.json`
- 后续 Slice C（第 306-307 行）明确"不再承担 LLM parser、旧 `CompactionCandidate`、旧 `CompactMaterialPack` production closeout"

**compact_material.py 的 snapshot 依赖：** plan 第 258 行允许 `compact_material.py` 继续从旧 snapshot 读取材料，但只投影为 vNext sections。这是一个正确的过渡安排：Pre-Slice C 改 material contract，Slice C 改 snapshot contract。`_stable_blocks_from_snapshot()` 的 `snapshot.working_assumptions` 依赖在 Slice C 中处理。

---

## Challenge 6 结论：测试命令和 exit signals 基本充分

**判定：基本充分，但有 2 个改进点（见 Finding 1 和 Finding 2）。**

**测试命令分析：**

```bash
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py \
  tests/host/test_compaction_operation.py tests/host/test_compact_material.py -q
python -m pyright dayu/ tests/ utils/
```

- 4 个测试文件覆盖 compact contract / parser / operation / material 四个维度
- pyright 全量运行确保无类型扩散
- 不依赖泛化 `tests/host/*`，符合最小化原则

**exit signals 分析：**

| exit signal | 验证目标 | 评估 |
|---|---|---|
| `rg` 旧符号不在 production closeout 残留 | 旧 contract 删除 | 充分（negative） |
| `CompactMaterialPack` 不输出旧字段 | material JSON 迁移 | 充分 |
| `LLMContextCompactor.compact()` 只返回 vNext | parser 迁移 | 充分 |
| accepted/rejected/repair/fallback 使用 vNext | operation closeout 迁移 | 充分但笼统 |
| 受影响 tests + pyright 通过 | 整体验证 | 充分（但 Finding 1 建议显式列出） |

---

## Challenge 7 结论：后续 Slice C 正确收窄

**判定：目标、allowed files、tests、residual risks 已正确收窄。**

**Slice C 收窄验证：**

1. **目标收窄：** Slice C 目标（第 306 行）明确"不再承担 LLM parser、旧 `CompactionCandidate`、旧 `CompactMaterialPack` production closeout 或 compact event payload closure"。

2. **allowed files 收窄：** Slice C 不包含 `compaction.py`、`llm_compaction.py`（这两个文件由 Pre-Slice C 闭合后不再需要在 Slice C 中修改）。

3. **测试命令收窄：** Slice C 测试命令不包含 `test_compaction_contract.py`、`test_llm_compaction.py`（由 Pre-Slice C 覆盖）。

4. **residual risks 正确标注：**
   - Slice C residual: memory durable/projection/prompt assembly/config-service 较大 vertical closure（第 434 行）
   - Slice D residual: README 同步、public smoke、eval benchmark（第 488-493 行）

5. **compact contract closure 不重测：** Slice C 第 428 行明确"compact contract closure 不在 Slice C 重测为主验收"。

---

## 总体评估

### 动机与必要性

Pre-Slice C 的动机成立。旧 compact contract 是 production owner 级别的残留，不是测试 fixture 过期。blocker 的 138 pyright errors 是直接证据。将 compact contract closure 独立于 memory/projection/config-service 是正确的工程判断。

### 充分性

Pre-Slice C 的 allowed files 覆盖全部 compact production owner。禁止项足以防止旧 compat wrapper、旧 field alias、旧 snapshot bridge。migration table 与 design 24.3 对齐。

### 最小性

Pre-Slice C 只触碰 compact contract domain 的 4 个核心生产文件 + 条件包含的 2 个文件 + 4-6 个测试文件。不引入 memory/projection/config-service 迁移。不引入 eval benchmark、recall/search 或 User Profile。

### Code-Generation-Ready

ready。测试命令覆盖 4 个测试文件 + pyright 全量。exit signals 以 negative verification 为主。有 2 个 non-blocking 改进建议（Finding 1 显式列出测试文件、Finding 2 增加 positive adoption signal），不阻塞 code generation。

---

## 结论

**pass-with-findings。**

| Finding | 严重性 | 阻塞 |
|---|---|---|
| exit signals 未显式列出受旧类型删除影响的关键测试文件 | non-blocking | 否（建议改进） |
| exit signals 缺少 vNext positive adoption 验证 | non-blocking | 否（建议改进） |

两个 findings 均为 exit signals 清晰性改进，不影响 plan 的 allowed files、禁止项、实现边界或测试命令设计。plan 可直接进入 implementation gate；建议实现 agent 在实现时一并参考 findings 中的改进方向。
