# WU-SEMANTIC-OWNERSHIP-01 P3-C Final Independent Plan Re-Review — AgentMiMo

## Reviewed target and scope

- **Plan artifact**: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`（final micro-fix 后版本）
- **Final micro-fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-final-micro-fix-codex.md`
- **Controller adjudication input**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-controller-adjudication.md`
- **Second re-review input**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-mimo.md`
- **Design sources**: `docs/host/design.md` §23-25、`docs/engine/design.md` §1,4,14,15
- **Scope**: 用直接代码证据验证 `P3-C-RR2-PF-01` 是否在 plan 中真正闭合；复核微修没有破坏所有前序 PF closure、三 slices、coverage 和 source scans；扫描新 material finding
- **Gate**: final plan re-review
- **Review date**: 2026-07-10
- **Reviewer**: AgentMiMo
- **Code evidence**: current `HEAD` (8787714d) direct reads of all affected production modules

## Review Posture

本 final re-review 不信任 final micro-fix artifact 的自报状态。逐项用当前代码直接证据验证
`P3-C-RR2-PF-01` 是否在 plan 文本中真正闭合，并确认微修没有引入 regression。

## P3-C-RR2-PF-01 逐项验证

### Controller 裁决

`_compact_material_source_ref()` 在 `dayu/host/run_input.py` 中只有一个调用者：
`build_run_input_material_blocks()` 的 compact-message loop。S2 删除 loop 后该 helper 成为
dead code。要求：

1. S2 exact changes 必须显式删除 `_compact_material_source_ref()` 与其唯一调用者。
2. 增加 `rg -n '_compact_material_source_ref' dayu/host/run_input.py` 零匹配 hard acceptance scan。
3. 保留 `_run_input_message_content()`，它有其它调用者。

### 代码直接验证

**1. `_compact_material_source_ref()` 唯一调用者假设**

- `run_input.py:3123` — `def _compact_material_source_ref(compact: CompactArtifactView) -> str:` 函数定义
- `run_input.py:2518` — `compact_source_ref = _compact_material_source_ref(compact)` 唯一调用点
- 全文件 `grep -n '_compact_material_source_ref'` 仅返回这两行：一个定义、一个调用
- 调用点位于 `build_run_input_material_blocks()` 的 compact loop（lines 2518-2530）内

**结论：唯一调用者假设成立。** ✓

**2. compact loop 完整删除覆盖**

Plan §6.4 明确："从 `compact_source_ref = ...` 开始、遍历 `compact.messages` 并构造
`block_id=\"compact:*\"` / `SESSION_SUMMARY` block 的整个 loop 必须删除"。

当前代码 loop 范围：
- line 2518: `compact_source_ref = _compact_material_source_ref(compact)` — loop 前置语句
- line 2519-2530: `for index, message in enumerate(compact.messages):` — loop 主体

Plan S2 item 6 明确："同步从该函数签名与 call sites 删除失去 material 职责的 `compact` 参数"。

函数签名（line 2489）：`compact: CompactArtifactView` — 将被删除
Call site 1（line 1951-1954）：`build_run_input_material_blocks(..., compact=compact, ...)` — `compact=compact` 将被删除
Call site 2（line 2030-2033）：同上模式 — `compact=compact` 将被删除

**结论：loop 起止、函数签名、两个 call sites 全部在 plan 中精确覆盖。** ✓

**3. `_compact_material_source_ref()` 函数定义删除覆盖**

Plan §4.3 明确："函数定义必须与 loop 在同一变更中删除"。
Plan S2 item 6 明确："随这个唯一调用者 loop 一起删除 `_compact_material_source_ref()` 函数定义"。
Plan §9 新增 source scan（line 882）：`rg -n '_compact_material_source_ref' dayu/host/run_input.py` — 预期零匹配。

**结论：函数定义删除有点名覆盖和零匹配 scan 双重保障。** ✓

**4. `_run_input_message_content()` 保留假设**

- `run_input.py:3024` — `def _run_input_message_content(message: AgentMessage) -> str:` 函数定义
- 调用者清单：
  - line 2506: memory loop in `build_run_input_material_blocks()` — **保留**
  - line 2525: compact loop — 将随 loop 删除（但函数本身保留）
  - line 2538: continuity loop — **保留**
  - line 3064: `_memory_material_kind()` — **保留**
- 三个非 compact-loop 调用者确认函数不是 dead code

Plan §6.4 明确："`_run_input_message_content()` 仍服务 memory、continuity 与 material-kind 等其它调用者，必须保留；不得借此清理不相关 helper"。
Plan §9 source scan 预期说明："`_run_input_message_content()` 因仍有其它调用者而保留，不属于 dead-code scan 或本次清理范围"。

**结论：保留假设成立。plan 精确说明了保留理由和边界。** ✓

**5. §9 source scan 完整性**

当前 §9 source scan 清单（lines 875-888）包含 11 个 `rg`/`sed` 命令。`_compact_material_source_ref`
scan 已在 line 882 新增。第二轮 re-review 发现的 9/10 覆盖缺口已补齐为 10/10。

**结论：source scan 完整。** ✓

## 前序 Closure 回归验证

### P3-C-PF-01 至 P3-C-PF-06（首轮 plan review）

Plan §4.1 记录的六个 closure 在 plan 文本中全部保持：
- P3-C-PF-01（line 147）：blocks/readable-view exact invariant — ✓
- P3-C-PF-02（line 149）：event-id equality matrix — ✓
- P3-C-PF-03（line 152）：typed evidence contract — ✓
- P3-C-PF-04（line 154）：post-compact count 推导 — ✓
- P3-C-PF-05（line 156）：mismatch 命名测试 — ✓
- P3-C-PF-06（line 158）：envelope 二次解析删除 — ✓

微修只影响 §4.3、§6.4 和 §9，未触及上述六个 closure 对应的 plan 章节。**无 regression。**

### P3-C-RR-PF-01 至 P3-C-RR-PF-05（第二轮 re-review）

Plan §4.2 记录的五个 closure 在 plan 文本中全部保持：
- P3-C-RR-PF-01（line 167）：protocol messages 删除 — ✓
- P3-C-RR-PF-02（line 171）：compact loop 完整删除 — ✓
- P3-C-RR-PF-03（line 175）：no-rename mapping — ✓
- P3-C-RR-PF-04（line 178）：`_previous_compacted_*_vnext` scan — ✓
- P3-C-RR-PF-05（line 180）：`llm_compaction` dead constants — ✓

微修未修改这些 closure 对应的任何 plan 文本。**无 regression。**

### Controller coverage follow-up

`test_llm_compaction.py` 在 S2 focused validation（line 813）、aggregate matrix（line 828）、
coverage collection（line 840 附近）和逐文件 `--fail-under=80` gate 中均保持包含。**无 regression。**

## 三 Slices 验证

- S1（line 593）：Accepted compact typed payload -> Conversation Memory closure — 未修改
- S2（line 635）：Typed previous view -> compact pipeline / ordinary RunInput / budget closure —
  微修在 S2 exact changes item 6 增加了 `_compact_material_source_ref()` 删除点名，属于收紧而非扩展
- S3（line 736）：Accepted evidence typed LLM material / renderer / typed mismatch closure — 未修改

**三 slices 完整，S2 收紧属于纯增强。**

## Coverage 验证

- S2 focused commands 包含 `test_run_input_builder.py` 和 `test_llm_compaction.py`（lines 812-814）
- Aggregate matrix 包含全部 12 个测试文件（lines 821-836）
- Aggregate coverage collection 包含全部 13 个 production 模块（lines 838-841）
- 逐文件 `--fail-under=80` 包含 `compact_payload.py` 和 `llm_compaction.py`（lines 858-859）

**Coverage 矩阵完整，微修未引入 regression。**

## 新 Material Finding 扫描

对以下攻击面逐一压测：

### Attack-1：`_compact_material_source_ref` 删除后 compact provenance 是否受影响

- compact provenance 路径：`CompactArtifactView.compact_artifact_ref` / `compact_artifact_digest`
- 这些属性在 `run_input.py` 的多个非 material-block 位置被直接访问：
  - line 1410: `_DurableProtectedRecentRawTailProvider` — raw-tail selection
  - line 3330/3332: `_validate_loaded_compact_view_matches_event` — event-ref equality
  - line 4982-5050: manifest/audit — evidence ref 去重
- `_compact_material_source_ref()` 只返回格式化字符串 `"compact:{ref}"`，用于 material block 的 `canonical_source_refs` 字段
- 删除 material block loop 后，`canonical_source_refs` 不再需要该 helper
- **No issue found.** provenance 路径不依赖被删除的 helper。

### Attack-2：`compact` 参数删除后其它使用是否受影响

- `build_run_input_material_blocks()` 函数内 `compact` 的唯一使用是 lines 2518-2530 的 loop
- 删除 loop 后参数无消费者，删除参数是正确的
- Call site 的 `compact` 变量仍被其它代码使用（如 `_accepted_tool_evidence_material_provider.load_accepted_tool_evidence_materials` 的参数）
- **No issue found.** 参数删除不影响 compact view 的其它用途。

### Attack-3：§9 新增 scan 与已有 scan 的一致性

- Line 882: `rg -n '_compact_material_source_ref' dayu/host/run_input.py` — 预期零匹配
- 该 scan 与 line 881 的 `compact.messages|messages=.*CompactArtifactView|_compact_artifact_message_content` scan 互补
- 前者覆盖 helper 定义/调用残留，后者覆盖 compact message 直接使用残留
- **No issue found.** scan 之间无重叠或遗漏。

### Attack-4：微修是否引入新的 import 依赖或 circular dependency

- 微修只修改 plan artifact 文本，不涉及代码变更
- Plan 中描述的 S2 变更不引入新的 import：`_compact_material_source_ref` 是模块内私有函数，
  删除它不改变模块间依赖
- **No issue found.**

### Attack-5：微修是否影响 stop conditions

- Plan §13 的 stop conditions 未被微修改改
- 新增的 `_compact_material_source_ref` 删除属于确定性 dead code 清理，不触发任何 stop condition
- **No issue found.**

**新 material findings：0**

## Source Scan 完整性最终确认

§9 source scan 现在覆盖 10/10 个目标模式：

| # | 模式 | 目标文件 | 预期 | 行号 |
|---|---|---|---|---|
| 1 | `_accepted_candidate_mapping\|_vnext_compact_candidate_semantic_lines\|...` | `dayu/host` | 无匹配 | 875 |
| 2 | `_previous_blocks_from_snapshot\|_snapshot_*\|_candidate_*` | `compact_material.py` | 无匹配 | 876 |
| 3 | `def _previous_compacted_*_vnext` | `compact_material.py` | 无匹配 | 877 |
| 4 | `str\(exc\).*ACCEPTED_EVIDENCE\|...` | `dayu/host` | 无匹配 | 878 |
| 5 | `def _accepted_tool_evidence_content\|...` | `dayu/host` | 无匹配 | 879 |
| 6 | `_PAYLOAD_FIELD_*` | memory/compact_material/run_input | 无匹配 | 880 |
| 7 | `compact\.messages\|messages=.*CompactArtifactView\|...` | `run_input.py` | 无匹配 | 881 |
| 8 | **`_compact_material_source_ref`** | **`run_input.py`** | **无匹配** | **882** |
| 9 | protocol messages/represented scan | `compact_pipeline.py` | 零匹配 | 883 |
| 10 | protocol ref/digest scan | `compact_pipeline.py` | 只匹配 ref/digest | 884 |

第二轮 re-review 识别的 9/10 缺口已补齐。

## Architecture Boundary 最终确认

Plan §5 的 7 个语义 owner boundary 在 final micro-fix 后仍然闭合：

1. compact candidate 五类语义：producer → validator → persistence → typed projection → consumers。✓
2. forward intent/reference enum：constructor → JSON `.value` → snapshot → same parser。✓
3. accepted compact ordinary LLM material：candidate → memory → snapshot → RunInput。✓
4. accepted compact next-compactor previous view：candidate → pair projector → typed view + blocks → next compact input。✓
5. post-compact budget：candidate business texts → pure estimator → operation gate。✓
6. accepted evidence durable facts：accept barrier → envelope codec → projection。✓
7. accepted evidence LLM 文本：typed material → 唯一 renderer → 三个 consumer。✓

微修未改变任何 owner boundary。`_compact_material_source_ref` 是 material block 内部 helper，
不属于任何 owner boundary 的边界组件。

## Open Questions

无。

## Residual Risks

无新增 residual risk。既有 P3-E/P3-J 分配、三个 slice 的 stop conditions 与
non-goals（§12）保持不变。

## Plan Review Conclusion

**Verdict: PASS 0**

`P3-C-RR2-PF-01` 在 plan 文本中真正闭合：

1. **唯一调用者**：`_compact_material_source_ref()` 只被 `build_run_input_material_blocks()` 的 compact loop 调用 — 代码直接证据确认。
2. **函数定义删除**：plan §4.3、§6.4、S2 item 6 三处点名删除；§9 零匹配 scan 双重保障。
3. **`_run_input_message_content()` 保留**：三个非 compact-loop 调用者确认不是 dead code — plan 精确说明保留理由。
4. **前序 closure 无 regression**：P3-C-PF-01 至 P3-C-PF-06、P3-C-RR-PF-01 至 P3-C-RR-PF-05、controller coverage follow-up 全部保持。
5. **三 slices 完整**：S1/S2/S3 未被破坏，S2 收紧属于纯增强。
6. **Coverage 矩阵完整**：focused/aggregate/逐文件 gate 全部保持。
7. **Source scans 完整**：10/10 模式覆盖，无遗漏。
8. **新 material findings：0**。

Plan 可以进入 implementation。

---

## Review Metadata

- **P3-C-RR2-PF-01 closure**: PASS
- **P3-C-PF-01 至 P3-C-PF-06 regression check**: PASS（无 regression）
- **P3-C-RR-PF-01 至 P3-C-RR-PF-05 regression check**: PASS（无 regression）
- **Controller coverage follow-up regression check**: PASS（无 regression）
- **Three slices integrity**: PASS（S1/S2/S3 完整）
- **Coverage matrix integrity**: PASS（focused + aggregate + 逐文件 gate 完整）
- **Source scan completeness**: 10/10 模式覆盖
- **Owner boundaries re-verified**: 7/7 闭合
- **New material findings**: 0
- **Blocking questions**: 0
- **Review artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-final-rereview-mimo.md`
