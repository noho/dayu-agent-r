# WU-SEMANTIC-OWNERSHIP-01 P3-C Second Plan Re-Review（AgentDS）

## Review metadata

- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01 / P3-C - Context compaction payload, evidence text, and LLM-safe projection contract`
- **Gate**: second independent plan re-review（second plan-fix 后、implementation 前）
- **Timestamp**: `2026-07-10T17:04:16+08:00`
- **Reviewed plan**: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-controller-adjudication.md`
- **Second-fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-fix-codex.md`
- **First-round re-reviews**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-ds.md`、`docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-mimo.md`
- **Design sources**: `docs/host/design.md` §23-25、`docs/engine/design.md` §1,4,14,15
- **Current code**: `dayu/host/compact_pipeline.py`、`dayu/host/run_input.py`、`dayu/host/compaction.py`、`dayu/host/compact_material.py`、`dayu/host/llm_compaction.py`、`dayu/host/compaction_operation.py`、`dayu/host/context_budget.py`
- **Scope**: 只写 second re-review artifact；不修改 plan、生产代码、测试、control doc、README 或 reviewer artifacts；不 commit、不 push、不创建 PR

## Review posture

本 second re-review 执行 adversarial verification pass。目标不是证明 second-fix 可行，而是用直接代码证据证伪每一项 controller-adjudicated fix claim。不信任 plan text 或 fix artifact 的自报状态。

## Method

1. 逐项用当前代码直接证据验证 `P3-C-RR-PF-01` 至 `P3-C-RR-PF-05`
2. 验证 controller coverage follow-up
3. 压测五项重点：narrow protocol 与 structural subtype、`build_run_input_material_blocks` 全 call sites、typed evidence no-rename mapping、previous helper 全族 scan、llm_compaction 三个常量零消费
4. 扫描任何新 material finding
5. 输出每项 closure verdict

---

## P3-C-RR-PF-01 验证 — narrow protocol 删除 messages/represented refs 与 structural subtype

**Plan 声称**：从 `CompactPipelineCompactArtifactView` Protocol 删除 `messages` 与 `represented_evidence_refs`，只保留 raw-tail 实际消费的 `compact_artifact_ref` / `compact_artifact_digest`；`CompactArtifactView` 保持 structural subtype。

**直接代码证据**：

1. Protocol 当前声明（`compact_pipeline.py:147-184`）：
   ```
   def messages(self) -> tuple[AgentMessage, ...]:           # line 151
   def compact_artifact_ref(self) -> str | None:              # line 160
   def compact_artifact_digest(self) -> str | None:            # line 169
   def represented_evidence_refs(self) -> tuple[str, ...]:    # line 178
   ```
   四个 property 全部声明。

2. Concrete view 当前（`run_input.py:424-437`）：
   ```python
   messages: tuple[AgentMessage, ...]           # line 434
   compact_artifact_ref: str | None             # line 435
   compact_artifact_digest: str | None          # line 436
   represented_evidence_refs: tuple[str, ...]   # line 437
   ```
   四个字段齐全，结构子类型当前成立。

3. Protocol consumer 实际消费（`run_input.py:1392-1425`）：
   - `load_ordinary_raw_tail()` 参数类型 `compact: CompactPipelineCompactArtifactView`（line 1397）
   - 函数体内唯一通过 protocol 访问的是 `compact.compact_artifact_ref`（line 1410）
   - `compact.messages` 与 `compact.represented_evidence_refs` 从未通过 protocol 读取
   - 向下游 `_load_protected_recent_raw_tail_tx()` 传递时仍为 protocol 类型

4. Structural subtype 检查点（`run_input.py:1920-1925`）：
   ```python
   self._protected_recent_raw_tail_provider.load_ordinary_raw_tail(
       attempt_snapshot, current_facts, memory, compact,
   )
   ```
   `compact` 是 `CompactArtifactView` 实例，传参给要求 `CompactPipelineCompactArtifactView` 的方法。

**Plan text 验证**：

- §3.7 明确："若只从 concrete `CompactArtifactView` 删除 `messages`，它将不再满足该 protocol，pyright 会暴露 structural subtype 断裂"
- §6.4 明确：protocol 收窄为 "只保留 protected-raw-tail selection 实际通过它消费的 `compact_artifact_ref` / `compact_artifact_digest` 两个 provenance property；`represented_evidence_refs` 继续保留在 concrete `CompactArtifactView`"
- S2 exact changes item 5 明确：protocol 同步删除 `messages` 与 "raw-tail path 不消费的 `represented_evidence_refs`"
- §9 source scan 有两个 scoped scan：
  - 第一个 `rg -n 'def (messages|represented_evidence_refs)'` 预期零匹配（protocol 内不再有这两个 property）
  - 第二个 `rg -n 'def compact_artifact_(ref|digest)'` 预期匹配两个 property
- §6.4 + S2 tests 要求 "pyright 与 focused protocol consumer tests 必须证明该 structural subtype 仍成立"

**代表性消费者验证**：

- `compact.represented_evidence_refs` 在 concrete view 的消费者：`run_input.py:3149` 的 `_represented_evidence_refs()` 函数 — 用于 evidence 去重，不经过 protocol，不受 protocol 收窄影响。✓
- `compact.messages` 经过 protocol 的消费者：无（`load_ordinary_raw_tail()` 不访问 `compact.messages`）✓

**Verdict**: **PASS 0**。Protocol 收窄路径正确：实际 consumer 只读 `compact_artifact_ref`，删除的 `messages`/`represented_evidence_refs` 没有 protocol-level consumer。concrete view 保留额外字段仍满足收窄后 protocol 的结构子类型要求。Source scan 和 pyright gate 双重验证。

---

## P3-C-RR-PF-02 验证 — build_run_input_material_blocks 删除 compact 参数与全 call sites/provenance

**Plan 声称**：删除 `build_run_input_material_blocks()` 中从 `compact_source_ref` 到整个 loop body；从 helper 签名与 call sites 删除 `compact` 参数；provenance 仍由 builder 的 typed compact view 提供。

**直接代码证据**：

1. 当前 loop body（`run_input.py:2518-2530`）：
   ```python
   compact_source_ref = _compact_material_source_ref(compact)       # line 2518
   for index, message in enumerate(compact.messages):                # line 2519
       blocks.append(
           run_input_material_block(
               block_id=f"compact:{index}",                          # line 2522
               section=CompactMaterialSection.TRACE_MATERIAL,        # line 2523
               kind=CompactMaterialBlockKind.SESSION_SUMMARY,        # line 2524
               ...
           )
       )
   ```
   从 `compact_source_ref` 赋值到 loop body 结束，完整形成 compact material block 生成路径。

2. 当前 `build()` 中的 splice（`run_input.py:1937`）：
   ```python
   *compact.messages,
   ```
   在 ordinary path 的 `bounded_context_messages` 拼接中。

3. `_compact_artifact_message_content()` 的定义（`run_input.py:3378`）和唯一调用（`run_input.py:1614`）。

4. 当前 helper 签名（`run_input.py:2485-2492`）：
   ```python
   def build_run_input_material_blocks(
       *, current_facts, memory, compact: CompactArtifactView, continuity, accepted_tool_evidence
   ) -> tuple[RunInputMaterialBlock, ...]:
   ```

5. 两个 call sites：
   - `run_input.py:1951-1957`：fallback path，`compact=compact`
   - `run_input.py:2030-2036`：compact builder material assembly，`compact=compact`

6. `compact.represented_evidence_refs` 的去重消费者（`run_input.py:3149`）不经过此 helper。✓

**Plan text 验证**：

- §6.4 明确："删除 `build_run_input_material_blocks()` 中从 `compact_source_ref = ...` 开始、遍历 `compact.messages` 并构造 `block_id="compact:*"` / `SESSION_SUMMARY` block 的整个 loop"，以及 "从该函数签名与 call sites 删除失去 material 职责的 `compact` 参数"
- S2 exact changes item 6 明确：删除 loop、删除参数、删除 `*compact.messages` splice、删除 `_compact_artifact_message_content()`
- §9 source scan `rg -n 'compact\.messages|messages=.*CompactArtifactView|_compact_artifact_message_content' dayu/host/run_input.py` 覆盖全部三处使用
- S2 tests 断言："`build_run_input_material_blocks()` 的结果不含 `compact:*` block，但 raw-tail selection、represented evidence 去重与 manifest 仍能读取 concrete compact provenance"

**全量 `compact.messages` 消费者验证**（通过 `rg -n 'compact\.messages' dayu/`）：

| 行号 | 位置 | Plan 覆盖 |
|---|---|---|
| `run_input.py:1937` | `*compact.messages` splice in `build()` | S2 item 6 点名删除 |
| `run_input.py:2519` | `for ... in enumerate(compact.messages)` | S2 item 6 点名删除 loop |
| (定义 `run_input.py:3378`) | `_compact_artifact_message_content` | S2 item 6 点名删除 |

全量 = 3 处，plan 全部覆盖。✓

**Verdict**: **PASS 0**。Loop body 删除、参数删除、call sites 删除全部显式指定。Source scan 覆盖全量消费者。Provenance 路径（event-ref equality、raw-tail selection、evidence 去重、manifest）不依赖此 helper 的 material 职责。

---

## P3-C-RR-PF-03 验证 — typed evidence no-rename mapping 准确

**Plan 声称**：`CompactEvidenceBlock` 和 `EvidenceReadableItemVNext` 字段名不变，值来源改为 typed material 对应字段；exact no-rename mapping table 固定映射关系。

**直接代码证据**：

1. `CompactEvidenceBlock` 当前字段（`compaction.py:443-460`）：
   - `readable_tool_name: str`（line 457）— 目标名含 `readable_` 前缀
   - `readable_query_text: str`（line 458）— 同上
   - `raw_result_text: str`（line 459）— 注意：`raw_result_text` 而非 `result_text`
   - `readable_source_text: str`（line 460）

2. `EvidenceReadableItemVNext` 当前字段（`compaction.py:956-995`）：
   - `tool_name: str`（line 967）
   - `query_text: str | None`（line 968）
   - `response_text: str`（line 969）— 注意：`response_text` 而非 `result_text`
   - `source_note: str | None`（line 970）

3. `AcceptedToolEvidenceLLMMaterial` plan 定义（§6.6）：
   - `tool_name: str`
   - `query_text: str`
   - `source_text: str`
   - `result_text: str`

4. 当前反模式证据（`compact_material.py:2757`）：
   ```python
   raw_result_text=block.text,   # block.text 将被改为完整四字段 renderer
   ```
   若计划落地后仍沿用此赋值，`raw_result_text` 会错误地包含 "工具名称：...\n查询语义：...\n业务来源：...\n工具结果：..." 全文。

**Plan mapping table 验证**（§6.6）：

| Target field | Typed material source | 字段名匹配？ |
|---|---|---|
| `CompactEvidenceBlock.readable_tool_name` | `material.tool_name` | 名不匹配（`readable_tool_name` vs `tool_name`），plan 明确不 rename |
| `CompactEvidenceBlock.readable_query_text` | `material.query_text` | 名不匹配（`readable_query_text` vs `query_text`），plan 明确不 rename |
| `CompactEvidenceBlock.raw_result_text` | `material.result_text` | 名不匹配（`raw_result_text` vs `result_text`），plan 明确不 rename |
| `CompactEvidenceBlock.readable_source_text` | `material.source_text` | 名不匹配（`readable_source_text` vs `source_text`），plan 明确不 rename |
| `EvidenceReadableItemVNext.response_text` | `material.result_text` | 名不匹配（`response_text` vs `result_text`），plan 明确不 rename |

Plan §6.6 显式声明："字段名保持现有 public/internal contract，不做 rename"；以及 "`CompactEvidenceBlock.raw_result_text` 与 `EvidenceReadableItemVNext.response_text` 都保持纯 `result_text` 分量"。✓

**renderer/component 分离验证**：

- §6.6 明确：`block.text` "逐字等于 `render_accepted_tool_evidence_for_llm(material)` 的四字段 renderer 输出；它不是上述任一 component field 的值来源，也不得被 parse"
- §10.2 propagation audit 明确：四字段 renderer 全文只进入 `block.text`，结果分量只进入 `raw_result_text/response_text`
- S3 tests 明确：断言 `block.text` 是完整四字段 renderer，而 `raw_result_text/response_text` 只等于 `material.result_text`

**Verdict**: **PASS 0**。Mapping table 覆盖全部 5 个 target field，明确标注所有命名不匹配并固定不 rename。renderer/component 分离有双重验证（test assertion + propagation audit）。

---

## P3-C-RR-PF-04 验证 — previous helper scan 覆盖全族

**Plan 声称**：source scan 覆盖 `_previous_compacted_view_vnext` 及五个子函数，零匹配为 hard acceptance criterion。

**直接代码证据**：

当前存在的 `_previous_compacted_*_vnext` 函数族（`compact_material.py`）：

| 函数名 | 行号 | 类型 |
|---|---|---|
| `_previous_compacted_fact_material_vnext` | 3229 | 子函数 |
| `_previous_compacted_answer_anchors_vnext` | 3245 | 子函数 |
| `_previous_compacted_forward_intents_vnext` | 3276 | 子函数 |
| `_previous_compacted_references_vnext` | 3301 | 子函数 |
| `_previous_compacted_view_vnext` | 3325 | 主函数（调用五个子函数） |
| `_previous_compacted_session_summary_vnext` | 3354 | 子函数 |

唯一外部调用者：`compact_material.py:601` 的 `conversation_compact_input_vnext_from_material_pack()`，调用 `_previous_compacted_view_vnext(material_pack.previous_compacted_view)`。S2 将迁移该调用者到 typed pair projector，主函数与五个子函数全部成为 dead code。

**Plan scan regex 验证**（§9）：

```
rg -n 'def _previous_compacted_(view|session_summary|fact_material|answer_anchors|forward_intents|references)_vnext' dayu/host/compact_material.py
```

匹配测试：

| 函数名 | Regex alternation | 匹配？ |
|---|---|---|
| `_previous_compacted_view_vnext` | `view` | ✓ |
| `_previous_compacted_session_summary_vnext` | `session_summary` | ✓ |
| `_previous_compacted_fact_material_vnext` | `fact_material` | ✓ |
| `_previous_compacted_answer_anchors_vnext` | `answer_anchors` | ✓ |
| `_previous_compacted_forward_intents_vnext` | `forward_intents` | ✓ |
| `_previous_compacted_references_vnext` | `references` | ✓ |

全族 6 个函数均被 regex 覆盖。✓

另外 §9 的原始 source scan 已覆盖 `_snapshot_*` helpers 和 `_candidate_*` parsers，与此次新增 scan 互补。

**Verdict**: **PASS 0**。Regex 精确覆盖全部 6 个函数，无遗漏。与已有 scan 形成完整 dead-code 验收矩阵。

---

## P3-C-RR-PF-05 验证 — llm_compaction 三个常量确实零消费且删除不影响 import/tests

**Plan 声称**：`llm_compaction.py` 的 `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`、`_POST_COMPACT_BASE_MESSAGE_COUNT`、`_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT` 均无消费点；正确 owner 纠正为 dead code 而非 proposal-budget owner。

**直接代码证据**：

1. 三个常量定义（`llm_compaction.py:92-97`）：
   ```python
   _POST_COMPACT_SYSTEM_PROMPT_ESTIMATE = (          # line 92
       "Host post-compact run context includes ..."   # line 93-94
   )                                                   # line 95
   _POST_COMPACT_BASE_MESSAGE_COUNT = 2               # line 96
   _POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT = 1       # line 97
   ```

2. 全仓搜索消费点：
   - `rg '_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE' dayu/` → 仅 `llm_compaction.py:92`（定义），零消费 ✓
   - `rg '_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT' dayu/` → 仅 `llm_compaction.py:97`（定义），零消费 ✓
   - `rg '_POST_COMPACT_BASE_MESSAGE_COUNT' dayu/host/` → `compaction_operation.py:69`（不同定义）、`compaction_operation.py:1493`（不同消费）、`llm_compaction.py:96`（定义）。`llm_compaction.py` 版本零消费 ✓

3. 无 import 污染：
   - `rg 'import.*llm_compaction|from.*llm_compaction' dayu/` → 仅 `from dayu.host.llm_compaction import LLMContextCompactor`（不 import 三个私有常量）✓

4. 正确 owner 分离：
   - `compaction_operation._POST_COMPACT_BASE_MESSAGE_COUNT` → 有真实消费（line 1493），迁入 `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT`
   - `llm_compaction._POST_COMPACT_BASE_MESSAGE_COUNT` → 零消费，直接删除
   - Plan 不再将零消费常量描述为 proposal-budget owner ✓

**Plan text 验证**：

- §6.5 纠正：三个常量 "均无任何消费点，不拥有当前 proposal-budget 或 ordinary post-compact budget 语义"
- S2 将 `llm_compaction.py` 纳入 allowed files，"仅原地删除这三个 dead constant 定义；不移动、合并、re-export、保留 alias，亦不让其复用 `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT`"
- §9 source scan：`rg -n '_POST_COMPACT_(SYSTEM_PROMPT_ESTIMATE|BASE_MESSAGE_COUNT|TOOL_SCHEMA_OVERHEAD_COUNT)' dayu/host/llm_compaction.py` 预期零匹配
- Source assertion：`llm_compaction.py` 不得 import/re-export/alias `context_budget` owner

**对 tests 的影响验证**：

- `tests/host/test_llm_compaction.py` 存在（39087 bytes），直接 import `dayu.host.llm_compaction` → 不受三个私有常量删除影响（测试不引用它们）
- 三个常量是模块级定义，import 时即执行；删除后模块仍可正常 import，不影响现有测试 ✓

**Verdict**: **PASS 0**。三个常量零消费的证据是精确 `rg` 结果，非推断。owner 纠正从 false "proposal-budget" 改为 "dead code"。删除范围最小（三个定义），不影响 import 或测试。

---

## Controller coverage follow-up 验证

**Plan 声称**：`tests/host/test_llm_compaction.py` 加入 S2 focused/aggregate matrix；aggregate coverage 增加 `--cov=dayu.host.llm_compaction`；单文件 `--fail-under=80` gate。

**直接代码证据**：

1. 测试文件存在性：
   ```
   -rw-r--r--  tests/host/test_llm_compaction.py  39087 bytes
   ```
   ✓

2. 测试文件直接覆盖证明：
   ```python
   from dayu.host.llm_compaction import LLMContextCompactor  # head -30 确认
   ```
   ✓

3. Plan §9 S2 focused validation：
   ```bash
   python -m pytest tests/host/test_llm_compaction.py -q
   ```
   ✓

4. Plan §9 aggregate coverage collection：
   ```bash
   --cov=dayu.host.llm_compaction \
   ```
   ✓（在 aggregate matrix command 中与其他 `--cov` 并列）

5. Plan §9 逐文件 coverage gate：
   ```bash
   python -m coverage report --include='dayu/host/llm_compaction.py' --fail-under=80
   ```
   ✓（显式独立命令，不依赖 aggregate 数字）

6. 原 matrix 缺口确认：原 aggregate 只通过 `test_public_compact_smoke.py` 的 monkeypatch 局部触达 `_run_agent_request`，不能保证整个模块 80%。Plan 正确识别此 gap ✓

**Verdict**: **PASS 0**。测试文件存在、直接 import 目标模块、已加入 focused/aggregate matrix、有独立单文件 coverage gate。不凭空命名测试文件。

---

## 新 material finding 扫描

### 扫描 1：全仓 `compact.messages` 消费者

`rg -n 'compact\.messages' dayu/` 结果：3 处（`run_input.py:1937, 2519` 以及函数定义 `run_input.py:3378`）。Plan 全部覆盖。**无新 finding**。

### 扫描 2：`build_run_input_material_blocks` call sites 完整性

2 个 call sites（`run_input.py:1951, 2030`），均传递 `compact=compact`。Plan §6.4 与 S2 item 6 均提到从 call sites 删除 `compact` 参数。**无遗漏**。

### 扫描 3：`_previous_compacted_*_vnext` 外部调用者

唯一外部调用者：`compact_material.py:601`。S2 将其迁移到 typed pair projector。**无遗漏**。

### 扫描 4：`represented_evidence_refs` 消费者保护

唯一直接消费者：`run_input.py:3149` 的 `_represented_evidence_refs()`。Plan 将 `represented_evidence_refs` 保留在 concrete `CompactArtifactView`，消费者不受 protocol 收窄影响。**无断裂**。

### 扫描 5：plan §9 source scan regex 精确性

逐条验证：

| 行 | Scan 目标 | 状态 |
|---|---|---|
| 861 | `_accepted_candidate_mapping\|_vnext_compact_candidate_semantic_lines\|...` | 覆盖 candidate parser 全族 ✓ |
| 862 | `_previous_blocks_from_snapshot\|_snapshot_*\|_candidate_*` | 覆盖 snapshot/candidate helpers ✓ |
| 863 | `def _previous_compacted_(view\|session_summary\|fact_material\|answer_anchors\|forward_intents\|references)_vnext` | 覆盖 previous helper 全族 ✓ |
| 864 | `str\(exc\).*ACCEPTED_EVIDENCE\|...` | 覆盖 string exception protocol ✓ |
| 865 | `def _accepted_tool_evidence_content\|def _accepted_evidence_readable_text` | 覆盖 private renderers ✓ |
| 866 | `_PAYLOAD_FIELD_(SESSION_SUMMARY\|...)` | 覆盖 candidate 字段常量 ✓ |
| 867 | `compact\.messages\|messages=.*CompactArtifactView\|_compact_artifact_message_content` | 覆盖 compact message 全消费者 ✓ |
| 868-869 | Protocol scoped scans | 覆盖 protocol property 收窄 ✓ |
| 870 | `accepted_evidence_envelope_from_payload\|str\(exc\)` | 覆盖 envelope parse/catch ✓ |
| 871 | `_POST_COMPACT_(SYSTEM_PROMPT_ESTIMATE\|BASE_MESSAGE_COUNT\|TOOL_SCHEMA_OVERHEAD_COUNT)` | 覆盖三个 dead constants ✓ |

12 个 scan 全部精确且可执行。**无遗漏**。

### 扫描 6：Coverage matrix 中每个实际修改文件的逐文件 gate

Plan §9 覆盖 `--cov` 的文件列表（13 个 production files）与 S1/S2/S3 allowed files 完全对齐。逐文件 `--fail-under=80` 命令显式写了 `compact_payload.py` 和 `llm_compaction.py`，并说明 "对上述每个实际修改的 production 文件分别执行同一 report 命令"。虽然非每个文件都有独立命令行展示，但 instruction 语义清晰，implementation agent 不会遗漏。**非 material finding**（instruction 已足够明确）。

---

## Architecture boundary re-verification

- Protocol 收窄后依赖方向正确：`CompactArtifactView`（concrete）→ `CompactPipelineCompactArtifactView`（protocol）← `_DurableProtectedRecentRawTailProvider`（consumer）。Protocol 声明 consumer 所需的最小接口，concrete 实现提供超集。**无反向依赖**。
- `build_run_input_material_blocks()` 删除 `compact` 参数后，该 helper 不再接触 compact 语义，职责收窄为 memory/continuity/evidence material 组装。Compact provenance 消费者（equality check、raw-tail selection、evidence 去重）通过 `RunInputBuilder` 持有的 concrete view 独立访问，不走该 helper。**职责分离清晰**。
- Evidence component 与 renderer 分离后：typed material → component fields（`CompactEvidenceBlock`/`EvidenceReadableItemVNext`），typed material → shared renderer → `block.text`。两个投影方向从同一 typed source 派生，但互不反向依赖。**无交叉污染**。
- `llm_compaction` 三个常量删除后，唯一 post-compact budget owner 是 `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT`。不产生第二 owner。**owner 归一**。

---

## Overengineering / Overcoupling re-check

- Protocol 收窄而非增加 adapter/facade → 不过度设计 ✓
- `build_run_input_material_blocks` 删除参数而非增加 abstract builder → 不过度设计 ✓
- Evidence mapping 固定 no-rename 而非引入 field alias registry → 不过度设计 ✓
- Source scan 精确点名删除目标而非依赖 general dead-code tool → enforcement 与 scope 对齐 ✓

---

## Final verdict

| Item | Verdict | New material finding? |
|---|---|---|
| P3-C-RR-PF-01 — narrow protocol + structural subtype | **PASS 0** | 否 |
| P3-C-RR-PF-02 — build_run_input_material_blocks compact 参数删除 | **PASS 0** | 否 |
| P3-C-RR-PF-03 — typed evidence no-rename mapping | **PASS 0** | 否 |
| P3-C-RR-PF-04 — previous helper 全族 scan | **PASS 0** | 否 |
| P3-C-RR-PF-05 — llm_compaction 三个 dead constants | **PASS 0** | 否 |
| Controller coverage follow-up | **PASS 0** | 否 |
| New material findings | — | **0** |

**Overall plan review conclusion**: `pass`

五项 controller-adjudicated fix 全部通过直接代码证据验证闭合。Plan 已到达 code-generation-ready 水平。三项 implementation slices、首轮 PF-01 至 PF-06 closure、三个 residual observations、与 controller coverage follow-up 全部保持完整。无新 material finding。

## Open questions

无。

## Residual risks

- 全部 covered by plan S1/S2/S3 或 assigned to P3-E/P3-J，与第二轮 plan-fix artifact 一致。无新增 residual risk。

## Suggested next step

Plan 可进入 implementation gate。Controller 应在 AgentMiMo second re-review 也返回 `pass` 后推进 S1。

---

Artifact path: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-ds.md`
