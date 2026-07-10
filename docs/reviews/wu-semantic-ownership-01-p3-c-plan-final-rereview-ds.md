# WU-SEMANTIC-OWNERSHIP-01 P3-C Final Plan Re-Review — AgentDS

## Review metadata

- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01 / P3-C - Context compaction payload, evidence text, and LLM-safe projection contract`
- **Gate**: final independent plan re-review（micro-fix 后、implementation 前）
- **Timestamp**: `2026-07-10T17:14:32+08:00`
- **Reviewed plan**: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`（final micro-fix 后版本）
- **Micro-fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-final-micro-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-controller-adjudication.md`
- **Second re-reviews**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-ds.md`、`docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-mimo.md`
- **First-round reviews**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-ds.md`、`docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-mimo.md`
- **Design sources**: `docs/host/design.md` §23-25、`docs/engine/design.md` §1,4,14,15
- **Current code**: `dayu/host/run_input.py`、`dayu/host/compact_pipeline.py`、`dayu/host/compact_material.py`、`dayu/host/llm_compaction.py`、`dayu/host/compaction_operation.py`
- **Scope**: 只写 final re-review artifact；不修改 plan、生产代码、测试、control doc、README 或 reviewer artifacts；不 commit、不 push、不创建 PR

## Review posture

本 final re-review 执行 adversarial verification pass。用直接代码证据验证 micro-fix 的唯一 finding
`P3-C-RR2-PF-01` 在 plan 中真正闭合，复核 micro-fix 没有破坏所有前序 PF closure、三个 slices、
coverage 与 source scans，并扫描新 material finding。

---

## P3-C-RR2-PF-01 逐条直接证据验证

### 1. `_compact_material_source_ref` 唯一调用者确认

**Plan 声称**：`_compact_material_source_ref()` 只有一个调用者——`build_run_input_material_blocks()` 中
的 compact-message loop（`run_input.py:2518`），该 loop 在 S2 被删除。

**直接代码证据**：

```bash
$ rg -n '_compact_material_source_ref' dayu/host/run_input.py
2518:    compact_source_ref = _compact_material_source_ref(compact)
3123:def _compact_material_source_ref(compact: CompactArtifactView) -> str:
```

- Line 2518：调用点，位于 `build_run_input_material_blocks()` 的 compact-message loop 体内（loop 从 line 2519 开始，line 2518 为 loop 前的 source-ref 赋值）
- Line 3123：函数定义
- 全仓搜索结果：**恰好一个调用点 + 一个定义，零其它引用**

**结论**：唯一调用者假设成立。删除 loop（lines 2518-2530）后，`_compact_material_source_ref()` 成为 dead code。✓

### 2. 函数定义被点名删除且零匹配 scan 覆盖

**Plan 声称**：Plan §4.3、§6.4、S2 exact changes item 6 三处点名删除，§9 增加零匹配 hard acceptance scan。

**Plan 文本直接证据**：

- §4.3 final micro-fix closure：
  > "`_compact_material_source_ref()` 只有 `build_run_input_material_blocks()` 的 `compact.messages` loop 一个调用者，必须随该 loop 在同一变更中删除；9 节增加该符号在 `run_input.py` 的零匹配 hard acceptance scan。"

- §6.4 Ordinary RunInput：
  > "`_compact_material_source_ref()` 的唯一调用者就是该 loop，必须与 loop 在同一变更中删除函数定义；不得留下 dead helper。"

- S2 exact changes item 6：
  > "随这个唯一调用者 loop 一起删除 `_compact_material_source_ref()` 函数定义"

- §9 source scan（新增）：
  ```bash
  rg -n '_compact_material_source_ref' dayu/host/run_input.py
  ```
  预期零匹配；任何定义、调用或 alias 残留都使 S2 验收失败。

**结论**：三处点名 + 一处 hard scan，覆盖完整。✓

### 3. `_run_input_message_content` 因其它消费者被保留

**Plan 声称**：`_run_input_message_content()` 仍被 memory、continuity 与 material-kind 路径调用，
必须保留，不扩成无关 helper cleanup。

**直接代码证据**：

```bash
$ rg -n '_run_input_message_content' dayu/host/run_input.py
2506:        content = _run_input_message_content(message)    # memory loop — 保留
2525:                text=_run_input_message_content(message), # compact loop — S2 删除
2538:                text=_run_input_message_content(message), # continuity loop — 保留
3024:def _run_input_message_content(message: AgentMessage) -> str:  # 定义 — 保留
3064:    content = _run_input_message_content(message)       # material-kind helper — 保留
```

消费者矩阵：

| 行号 | 位置 | S2 后状态 | 说明 |
|---|---|---|---|
| 2506 | memory message loop | **保留** | `build_run_input_material_blocks()` 中 memory 迭代 |
| 2525 | compact message loop | **删除** | 随 `compact.messages` loop 一起删除 |
| 2538 | continuity message loop | **保留** | `build_run_input_material_blocks()` 中 continuity 迭代 |
| 3064 | material-kind helper | **保留** | `_memory_material_kind()` / `_history_material_kind()` 等调用 |

S2 删除 compact loop（lines 2518-2530）后，line 2525 的调用随之消失，但 lines 2506、2538、3064
的三个调用者全部存活。函数定义（line 3024）必须保留。

**结论**：`_run_input_message_content` 有三个非 compact-loop 调用者，plan 正确识别并显式禁止将其扩成
无关 helper cleanup。✓

### 4. 删除边界验证：不涉及其它 helper

**验证**：`_compact_material_source_ref` 与 `_run_input_message_content` 是两个独立 helper，职责不同：
- `_compact_material_source_ref`：从 `CompactArtifactView` 提取 compact artifact ref 字符串，仅用于
  `canonical_source_refs` 标识 compact material block 的来源
- `_run_input_message_content`：从 `AgentMessage` 提取文本内容，是通用 message content accessor

删除前者不影响后者。Plan 正确区分两者边界，未将其合并处理。✓

---

## P3-C-RR2-PF-01 Closure Verdict

| 子项 | 直接证据 | Verdict |
|---|---|---|
| 唯一调用者确认 | `rg` 全仓扫描：line 2518（调用）+ line 3123（定义），恰好一个调用点 | **PASS** |
| 函数定义点名删除 | Plan §4.3 + §6.4 + S2 item 6 三处点名 | **PASS** |
| 零匹配 scan | Plan §9 新增 `rg -n '_compact_material_source_ref' dayu/host/run_input.py` | **PASS** |
| `_run_input_message_content` 保留 | 三个非 compact-loop 调用者（lines 2506, 2538, 3064）存活 | **PASS** |
| 不扩成无关 cleanup | Plan §4.3、§6.4 显式禁止 | **PASS** |

**P3-C-RR2-PF-01**: **PASS 0**。全部五个子项均通过直接代码证据验证闭合。

---

## 前序 PF Closure 完整性复核

逐项验证 plan 中每项前序 closure 在 micro-fix 后仍保持完整：

### 首轮 Plan-Review Fix Closure（§4.1）

| Finding | Plan 位置 | Micro-fix 是否触及？ | 状态 |
|---|---|---|---|
| P3-C-PF-01 | §6.3 blocks/readable-view invariant + pair-transform helper | 否 | **closed** |
| P3-C-PF-02 | §6.4 event-id equality + 五格 matrix + MemoryProjectionRepairRequired | 否（§6.4 新增 `_compact_material_source_ref` 删除语句与已有 PF-02 无冲突） | **closed** |
| P3-C-PF-03 | §6.6 typed evidence contract + shared renderer | 否 | **closed** |
| P3-C-PF-04 | §6.5 POST_COMPACT_BASE_MESSAGE_COUNT=2 推导 + drift test | 否 | **closed** |
| P3-C-PF-05 | §7.1、S2、§9 命名测试 + focused/aggregate validation | 否 | **closed** |
| P3-C-PF-06 | S3 点名删除 envelope 二次解析 + str(exc) catch | 否 | **closed** |
| 三个 residual observations | S2 删除 dead string-wire helpers + 重复常量/parser + §6.5 false-owner 纠正 | 否 | **closed** |

### 第二轮 Plan Re-Review Fix Closure（§4.2）

| Finding | Plan 位置 | Micro-fix 是否触及？ | 状态 |
|---|---|---|---|
| P3-C-RR-PF-01 | §6.4 + S2 protocol 收窄 + structural subtype | 否 | **closed** |
| P3-C-RR-PF-02 | §6.4 + S2 compact loop 删除 + call sites + provenance | 否（micro-fix 仅增加 helper 删除，不改变 loop 删除范围） | **closed** |
| P3-C-RR-PF-03 | §6.6 no-rename mapping table | 否 | **closed** |
| P3-C-RR-PF-04 | §9 `_previous_compacted_*_vnext` 零匹配 scan | 否 | **closed** |
| P3-C-RR-PF-05 | §6.5 + S2 llm_compaction 三个 dead constants 删除 | 否 | **closed** |
| Controller coverage follow-up | §9 test_llm_compaction focused/aggregate/逐文件 gate | 否 | **closed** |

### Micro-fix 自身的 Closure & Regression Audit（micro-fix artifact）

Micro-fix artifact 的 "Closure & regression audit" 段落声明的所有项均与 plan 当前状态一致：
- 首轮 P3-C-PF-01 至 P3-C-PF-06：保持 closed ✓
- 三个 residual observations：保持 absorbed/closed ✓
- P3-C-RR-PF-01 至 P3-C-RR-PF-05：保持 closed ✓
- Controller coverage follow-up：S2 focused、aggregate matrix、`--cov=dayu.host.llm_compaction`、单文件 `--fail-under=80` 均保持不变 ✓
- Implementation slices：仍为 S1/S2/S3 三个 slice ✓
- Propagation path：compact material loop 与 helper 一起删除；typed compact provenance 继续直接服务 equality、raw-tail、evidence 去重、manifest/audit ✓

**复核结论**：micro-fix 仅向 S2 item 6 追加 `_compact_material_source_ref` 删除子句，向 §9 追加一条零匹配 scan，向 §4.3 追加一段 closure 记录。所有前序 PF closure 文本、slice 结构、coverage 矩阵、source scan 列表均未被修改、覆盖或削弱。**0 项 regression**。

---

## 三个 Implementation Slices 完整性复核

| Slice | 目标 | Allowed files | Exact changes | Micro-fix 触及？ | 状态 |
|---|---|---|---|---|---|
| S1 | Accepted compact typed payload → Conversation Memory | 5 production + 3 test | 5 项 | 否 | **完整** |
| S2 | Typed previous view → compact pipeline / RunInput / budget | 8 production + 7 test | 7 项（item 6 新增 helper 删除子句） | 仅 item 6 追加 `_compact_material_source_ref` 删除 | **完整** |
| S3 | Accepted evidence typed LLM material / renderer / mismatch | 7 production + 7 test | 6 项 | 否 | **完整** |

S2 item 6 的变更是增量式的：原 item 6 已覆盖 "删除 compact loop + compact 参数 + call sites + `_compact_artifact_message_content` + `_vnext_compact_candidate_semantic_lines` + candidate 字段常量"，micro-fix 仅在 loop 删除后追加 "随这个唯一调用者 loop 一起删除 `_compact_material_source_ref()` 函数定义" 和 "`_run_input_message_content()` 明确保留"。该追加不改变 item 6 的任何既有删除目标，不引入新文件，不跨越 slice 边界。

**复核结论**：三个 slice 的 objective、prerequisites、allowed files、exact changes、tests/assertions、completion signal、stop conditions 均保持完整。**0 项 slice 结构变化**。

---

## Coverage 与 Source Scans 完整性复核

### Coverage 矩阵

Plan §9 的 focused validation、aggregate matrix、逐文件 coverage collection 和 `--fail-under=80` gate 均未变化。`test_llm_compaction.py` 的 S2 focused + aggregate + 逐文件 gate 保持不变。

### Source Scans 完整性

Micro-fix 前 plan §9 已有 12 个 source scan。Micro-fix 新增第 13 个：

```
rg -n '_compact_material_source_ref' dayu/host/run_input.py
```

现有 13 个 scan 的覆盖矩阵：

| # | Scan 目标 | 覆盖项 | 状态 |
|---|---|---|---|
| 1 | `_accepted_candidate_mapping\|_vnext_compact_candidate_semantic_lines\|_parse_previous_*` | candidate parser 全族 | ✓ |
| 2 | `_previous_blocks_from_snapshot\|_snapshot_*\|_candidate_*` | snapshot/candidate helpers | ✓ |
| 3 | `def _previous_compacted_(view\|session_summary\|fact_material\|answer_anchors\|forward_intents\|references)_vnext` | previous helper 全族 6 函数 | ✓ |
| 4 | `str\(exc\).*ACCEPTED_EVIDENCE\|ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` | string exception protocol | ✓ |
| 5 | `def _accepted_tool_evidence_content\|def _accepted_evidence_readable_text` | private evidence renderers（3 处） | ✓ |
| 6 | `_PAYLOAD_FIELD_(SESSION_SUMMARY\|...)` | candidate 字段常量 | ✓ |
| 7 | `compact\.messages\|messages=.*CompactArtifactView\|_compact_artifact_message_content` | compact message 全消费者 | ✓ |
| 8 | Protocol scoped scan 1: `def (messages\|represented_evidence_refs)` | protocol property 收窄 | ✓ |
| 9 | Protocol scoped scan 2: `def compact_artifact_(ref\|digest)` | protocol property 保留 | ✓ |
| 10 | `accepted_evidence_envelope_from_payload\|str\(exc\)` | envelope parse/catch | ✓ |
| 11 | `_POST_COMPACT_(SYSTEM_PROMPT_ESTIMATE\|BASE_MESSAGE_COUNT\|TOOL_SCHEMA_OVERHEAD_COUNT)` | llm_compaction dead constants | ✓ |
| 12 | `git diff -- dayu/host/tool_trace.py` | Tool Trace 零变更 | ✓ |
| 13 | `_compact_material_source_ref` | **新增**：material source-ref helper 零匹配 | ✓ |

**复核结论**：13 个 scan 全部精确、可执行、覆盖完整。无遗漏。

---

## 新 Material Finding 扫描

逐项攻击面压测：

### 扫描 1：micro-fix 是否引入 plan 内部矛盾

- §4.3 说 `_compact_material_source_ref` 必须删除
- §6.4 说同一件事
- S2 item 6 说同一件事
- §9 有零匹配 scan
- 所有四处一致。**无矛盾**。

### 扫描 2：micro-fix 是否遗漏其它 dead code

compact loop 删除后可能成为 dead code 的符号：

| 符号 | 位置 | 处理 |
|---|---|---|
| `_compact_material_source_ref` | `run_input.py:3123` | Plan 点名删除 + 零匹配 scan |
| `compact_source_ref` 局部变量 | `run_input.py:2518` | 随 loop 删除 |
| `compact` 参数 | `run_input.py:2489` | Plan 点名从签名 + 2 个 call sites 删除 |
| `_run_input_message_content` | `run_input.py:3024` | Plan 显式保留（3 个其它调用者） |

**无遗漏**。

### 扫描 3：`compact` 参数删除后 call sites 安全性

两个 call sites：

| 行号 | 上下文 | 处理 |
|---|---|---|
| 1951 | `RunInputBuilder.build()` fallback path | S2 item 6 覆盖 |
| 2030 | `RunInputBuilder.build_material_blocks()` | S2 item 6 覆盖 |

函数体内唯一的 `compact` 使用是被删除的 loop（lines 2518-2530）。删除参数不会导致任何其它代码引用未定义变量。**安全**。

### 扫描 4：Protocol structural subtype 在 micro-fix 后仍闭合

Micro-fix 不触及 `CompactPipelineCompactArtifactView` Protocol 或 `CompactArtifactView` concrete class。前序 P3-C-RR-PF-01 的 closure 完全不受影响。**无回归**。

### 扫描 5：llm_compaction 三个 dead constants 在 micro-fix 后仍正确处理

三个常量（`llm_compaction.py:92-97`）仍为零消费者。Plan §6.5 与 §9 的删除指令和零匹配 scan 未变。**无回归**。

### 扫描 6：`_run_input_message_content` 的 call site 计数是否可能被误读

当前 4 个 call sites：lines 2506, 2525, 2538, 3064。S2 删除 line 2525 后剩 3 个。三个存活 call sites 全部在 `build_run_input_material_blocks()` 的非 compact 路径或独立 helper 中。**无误读风险**。

### 扫描 7：是否有类似 `_compact_material_source_ref` 但未被覆盖的 dead helper

搜索所有在 `build_run_input_material_blocks()` compact loop 中被调用但无其它消费者的私有函数：

- `_compact_material_source_ref` — 已覆盖 ✓
- `_run_input_message_content` — 有其它消费者，保留 ✓
- `run_input_material_block` — 被 memory、continuity、evidence 路径共享，保留 ✓
- `_material_section_for_message` — 仅用于 memory loop，保留 ✓
- `_memory_material_kind` — 仅用于 memory loop，保留 ✓
- `_memory_material_source_ref` — 仅用于 memory loop，保留 ✓
- `_history_material_kind` — 仅用于 continuity loop，保留 ✓

**无遗漏的 dead helper**。

---

## Architecture Boundary Re-verification

- `_compact_material_source_ref` 删除不改变任何 owner boundary。该 helper 的唯一职责是从 `CompactArtifactView` 提取 ref 字符串供 `canonical_source_refs` 使用。其职责在删除后由 builder 持有的 concrete `CompactArtifactView.compact_artifact_ref` 直接承担（与 event-ref equality check 共享同一 provenance 来源）。**无 owner boundary 漂移**。
- `_run_input_message_content` 保留且职责不变：从 `AgentMessage` 提取文本内容。其调用者（memory、continuity、material-kind）各自拥有自己的 section routing 职责，不因 compact loop 删除而改变。**无职责合并或拆分**。

---

## Final Verdict

| Item | Verdict | New material finding? |
|---|---|---|
| P3-C-RR2-PF-01 — `_compact_material_source_ref` 唯一调用 + 点名删除 + 零匹配 scan | **PASS 0** | 否 |
| P3-C-RR2-PF-01 — `_run_input_message_content` 保留（3 个其它调用者） | **PASS 0** | 否 |
| P3-C-RR2-PF-01 — 不扩成无关 helper cleanup | **PASS 0** | 否 |
| 首轮 PF-01 至 PF-06 closure 完整性 | **PASS 0**（0 regression） | 否 |
| 三个 residual observations closure 完整性 | **PASS 0**（0 regression） | 否 |
| P3-C-RR-PF-01 至 P3-C-RR-PF-05 closure 完整性 | **PASS 0**（0 regression） | 否 |
| Controller coverage follow-up 完整性 | **PASS 0**（0 regression） | 否 |
| S1/S2/S3 slice 结构完整性 | **PASS 0**（0 结构变化） | 否 |
| Coverage 矩阵完整性 | **PASS 0**（13 scans，新增 1 个） | 否 |
| New material findings | — | **0** |

**Overall plan review conclusion**: `pass`

`P3-C-RR2-PF-01` 五个子项全部通过直接代码证据验证闭合。Micro-fix 仅向 plan 追加 `_compact_material_source_ref` 删除指令和零匹配 scan，不破坏任何前序 PF closure、slice 结构、coverage 矩阵或 source scan 完整性。无新 material finding。

Plan 已达到 code-generation-ready 水平，可进入 implementation gate。

---

## Open questions

无。

## Residual risks

无新增 residual risk。既有 P3-E/P3-J 分配与三个 slice 的 stop conditions 保持不变。

## Suggested next step

Controller 应在 AgentMiMo final re-review 也返回 `pass` 后推进 P3-C S1 implementation。

---

Artifact path: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-final-rereview-ds.md`
