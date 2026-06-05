# Code Review — WU-CM-01-F02-S6-R1 Compact Instruction Contract Rescope

## Scope

- Mode: current changes (uncommitted, based on `main`)
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Output file: `docs/reviews/wu-cm-01-f02-s6-r1-code-review-ds.md`
- Work unit: `WU-CM-01-F02-S6-R1`
- Plan: `docs/host/wu-cm-01-f02-s6-r1-compact-instruction-rescope-plan.md`
- Implementation artifact: `docs/reviews/wu-cm-01-f02-s6-r1-implementation-codex.md`

### Included scope

- `dayu/host/compaction.py` — production constant definition, `CompactInstructionVNext` validation and `to_json()`.
- `dayu/config/prompts/scenes/conversation_compaction_user.md` — LLM-facing prompt template input schema clarification.
- `docs/host/design.md` — section 24.3 `CompactInstruction` design truth sync.
- `docs/host/issues-implementation-control.md` — control doc gate/status bookkeeping.
- `tests/host/test_compaction_contract.py` — contract-level instruction literal and validation tests.
- `tests/host/test_llm_compaction.py` — LLM compactor rendered material JSON assertions.
- `tests/host/test_public_compact_smoke.py` — public fake compactor runtime material contract assertions.

### Excluded scope

- Output parser `parse_conversation_compact_output_vnext()` — unchanged by design.
- Accept barrier `check_conversation_compact_output_vnext()` — unchanged by design.
- Durable schemas, EventLog payloads, memory projection — unchanged by design.
- `dayu/host/context_governance.py` — unchanged by design.
- Optional real-provider smoke — environment-dependent, outside this residual closure.

## Review Methodology

沿真实代码路径逐行走读，覆盖以下链路：

1. 常量定义 → `CompactInstructionVNext.default/output_schema_name` → `__post_init__` 校验 → `to_json()` → `ConversationCompactInputVNext.to_json()` → `_compaction_request_prompt_block_vnext()` → `UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN/END` → model-readable user prompt。
2. 测试断言：contract-level `CompactInstructionVNext` 构造 + `ConversationCompactInputVNext.to_json()` 直接断言、LLM compactor mock runner 拦截并提取渲染后 prompt 中的 material JSON、public fake compactor `run_agent_and_wait` 拦截每条 request 并断言 material contract。
3. Prompt/design 文字：逐条检查是否引入内部 Python 类型名、Host 实现术语或 migration 概念。
4. README sync 决策：逐条检查三个 README 是否因本次变更产生文档不一致。

## Findings

### 01-未修复-低-`FORBIDDEN_COMPACTOR_PROMPT_TERMS` 常量提取未同步到所有引用

- **入口/函数**: 模块级常量 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 定义及使用。
- **文件(行号)**: `tests/host/test_public_compact_smoke.py:98-109`
- **输入场景**: 编译器或 linter 无法检测字符串字面量是否与常量定义一致。
- **实际分支**: `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 从 `"ConversationCompactOutputVNext"` 改为引用 `_INTERNAL_COMPACT_OUTPUT_TYPE_NAME`（第 100 行）。但 `_INTERNAL_COMPACT_OUTPUT_TYPE_NAME` 定义在第 74 行，而同一元组中 `"vNext"` 和 `"migration"` 等仍然使用裸字符串。
- **预期行为**: 实现 artifact 声称从硬编码字符串改为了模块级常量引用。
- **实际行为**: 实现 artifact 声称属实——`_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 中的 `_INTERNAL_COMPACT_OUTPUT_TYPE_NAME` 和 `_INTERNAL_COMPACT_INPUT_TYPE_NAME` 已正确改为常量引用。`"vNext"` 和 `"migration"` 等其他字符串不在本次 rescope 范围，保持裸字符串是合理的最小变更。
- **直接证据**: 第 100-101 行 `_INTERNAL_COMPACT_OUTPUT_TYPE_NAME, _INTERNAL_COMPACT_INPUT_TYPE_NAME` 已正确使用常量引用。
- **影响**: 无功能影响。仅作为代码一致性记入低严重度观察。
- **建议改法和验证点**: 无需修改。当前变更满足计划范围。
- **修复风险（低）**: 不适用。
- **严重程度（低）**: 不构成缺陷，仅记录为观察。

## 审查点逐项核查

### 1. Runtime LLM-facing material JSON 不再暴露 ConversationCompactOutputVNext — 通过

- **字面量变更**: `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 从 `"ConversationCompactOutputVNext"` 改为 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT` = `"conversation_compact_output_v1"`（`compaction.py:34`）。
- **数据流路径验证**: `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` → `CompactInstructionVNext.output_schema_name`（第 692 行，默认值）→ `CompactInstructionVNext.to_json()`（第 713 行，`{"output_schema_name": self.output_schema_name, "compact_goal": self.compact_goal}`）→ `ConversationCompactInputVNext.to_json()`（第 127 行附近，`"instruction": self.instruction.to_json()`）→ `_compaction_request_prompt_block_vnext()`（`llm_compaction.py:526`，序列化为 JSON 后包装在 `UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN/END` 中）→ user prompt → LLM 可见。
- **验证**: `git grep "CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT" -- ':!dayu/host/compaction.py' ':!docs/'` 无外部生产引用。`conversation_compaction_user.md` 中无 `ConversationCompactOutputVNext` 或 `ConversationCompactInputVNext`。

### 2. CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT 从 _VERSION 派生，无重复字面量 — 通过

- `compaction.py:34`: `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`
- `compaction.py:31`: `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT = "conversation_compact_output_v1"`
- 无独立硬编码 `"conversation_compact_output_v1"` 字面量出现在常量定义区。
- plan review controller adjudication 明确选择了派生方式以避免未来 schema version 升级时出现 skew。

### 3. CompactInstructionVNext 严格校验和 to_json 字段名不变 — 通过

- `__post_init__`（第 695-705 行）:
  - `if self.output_schema_name != CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT`: 仍作严格相等检查。
  - `if self.compact_goal != CONVERSATION_COMPACT_GOAL_ROLL_FORWARD_SESSION_MEMORY`: 未改动。
- `to_json()`（第 707-716 行）:
  - 字段名 `"output_schema_name"` 和 `"compact_goal"` 未改动。
  - 仅值从 `"ConversationCompactOutputVNext"` 变为 `"conversation_compact_output_v1"`。

### 4. Output schema 字段/output schema_version/parser/accept barrier/durable schema/public Host API 不变 — 通过

- Output candidate 字段: 无变更。
- `ConversationCompactOutputVNext` Python 类未重命名。
- `schema_version = "conversation_compact_output_v1"` 在 output candidate 中未变更。
- `parse_conversation_compact_output_vnext()` — 未修改。
- `check_conversation_compact_output_vnext()` — 未修改。
- Durable artifact/EventLog/memory projection schema — 未修改。
- Public `ContextCompactor` Protocol / `compact()` API — 未修改。

### 5. Tests 验证最终 runtime material JSON（不只是 prompt template 文本），包括 public fake compactor 路径 — 通过

- `tests/host/test_compaction_contract.py`:
  - `test_compact_instruction_uses_llm_facing_output_contract_identifier()`（第 78 行）: 从 `ConversationCompactInputVNext.to_json()` 直接断言 `instruction.output_schema_name`，并通过 `json.dumps(payload, ensure_ascii=False, sort_keys=True)` 断言序列化后不含 `ConversationCompactOutputVNext`。
  - `test_compact_instruction_rejects_internal_python_type_name()`（第 104 行）: 断言旧内部类型名被 `CompactInstructionVNext.__post_init__` 拒绝并抛出 `ValueError`。
- `tests/host/test_llm_compaction.py`:
  - `test_llm_context_compactor_compact_uses_vnext_material()`（第 246 行）: 从实际渲染的 `AgentRunRequest.messages[1].content` 提取 material JSON（通过 `UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN/END` 分隔符），断言 `output_schema_name` 值和内部类型名不存在。
  - 新增 `_material_json_from_compactor_prompt()`（第 351 行）和 `_required_mapping()`（第 380 行）辅助函数。
- `tests/host/test_public_compact_smoke.py`:
  - `FakeCompactorRunAgent.run_agent_and_wait()`（第 630 行）: 每次 compactor request 拦截都调用 `_assert_compactor_material_instruction_contract(material_json)`。
  - `_assert_compactor_material_instruction_contract()`（第 733 行）: 断言 runtime material JSON 的 `instruction.output_schema_name` 值和序列化后不含内部类型名。
  - `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence()`（第 269 行）: 显式调用 `_assert_compactor_material_instruction_contract()` 以增强可读性。

**关键区别**: 旧测试只检查 prompt template 文本中包含哪些 section 名；新测试从实际渲染的 prompt 中**提取并解析** material JSON，直接断言最终 LLM 看到的 `instruction.output_schema_name` 值。这是 review point 的核心要求。

### 6. 旧内部类型名被 CompactInstructionVNext 拒绝 — 通过

- `tests/host/test_compaction_contract.py:104-112`:
  ```python
  def test_compact_instruction_rejects_internal_python_type_name() -> None:
      with pytest.raises(ValueError, match="output_schema_name"):
          CompactInstructionVNext(output_schema_name=_INTERNAL_COMPACT_OUTPUT_TYPE_NAME)
  ```
- `_INTERNAL_COMPACT_OUTPUT_TYPE_NAME = "ConversationCompactOutputVNext"`（第 41 行）。
- 该测试通过（39 passed, 1 skipped）。

### 7. Prompt/design 措辞保持 LLM-facing，未引入内部类型名或 migration 术语 — 通过

- `conversation_compaction_user.md`:
  - 第 20-22 行: 新措辞 `instruction.output_schema_name`：JSON string，唯一允许值为 `conversation_compact_output_v1`；它只是本次请求的输出格式标识，不是业务事实。和 `instruction.compact_goal`：JSON string，唯一允许值为 `roll_forward_session_memory`；它只是本次整理目标，不是财报事实或用户结论。
  - 无 `ConversationCompactOutputVNext`、`ConversationCompactInputVNext`、`vNext`、`Host`、`Python`、`类型名`、`migration`、`compatibility` 等术语。
- `docs/host/design.md`:
  - 第 2831 行: `output_schema_name: "conversation_compact_output_v1"`。
  - 第 2837 行: 邻近 prose 明确 `output_schema_name` 是业务可读输出 contract 标识，不是 Python 类型名。

### 8. 无兼容性 alias/wrapper/fallback — 通过

- 搜索 `compaction.py` 全文，无 `old_`、`legacy_`、`_deprecated`、`_compat`、`_v0` 等模式。
- 未新增任何包装函数、转发导入或 fallback 逻辑。
- 未保留旧字面量 `"ConversationCompactOutputVNext"` 在运行时路径中的兼容分支。

### 9. README sync 决策可辩护 — 通过

- `dayu/host/README.md`:
  - 第 288 行引用 `ConversationCompactOutputVNext` 作为内部 structured candidate 类型名，并非 `instruction.output_schema_name` 的字面量。此为内部类型系统文档，不在本次 LLM-facing literal rescope 范围内。
  - 未记录旧的 `instruction.output_schema_name` 字面量值，因此改为 `conversation_compact_output_v1` 不会导致文档不一致。
- `dayu/config/README.md`:
  - 未记录 `conversation_compaction_user.md` 中的具体 instruction 字段或 `output_schema_name` 字面量。无文档不一致。
- `tests/README.md`:
  - 未记录 compaction contract 测试的具体断言。无文档不一致。
- 其他 README 不在触发范围内（无 CLI/用户流程/分层边界变更）。
- **结论**: 三个 README 均无需更新，决策可辩护。

## Open Questions

无。

## Residual Risk

- Optional real-provider compact smoke（`test_real_compactor_public_opener_compacts_and_preserves_continuity`）仍依赖环境变量 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 且需要外部 provider。该风险已由 plan 分配给 WU-CM-01-F01 Slice 7 public smoke closeout。
- 内部 Python 类型名 `ConversationCompactOutputVNext` 仍在 Python 代码、类型注解和内部文档中保留。非本工作单元目标，已在 plan non-goals 中记录。
- `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 的语义已从 "schema name" 变化为 "contract identifier"，但其名称未更改。若后续维护者基于旧名称语义使用该常量，可能产生误解。当前无外部消费者，风险低。

## Verdict

**PASS** — 实现正确、范围精确、测试覆盖关键运行时路径。所有 9 个审查点均通过。无中等及以上严重度 finding。控制 doc bookkeeping 状态正确反映了当前 gate（review 阶段，residual 未关闭等待 controller closure）。

## Validation

- `pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_public_compact_smoke.py -q`: **39 passed, 1 skipped**
- `pyright`: **0 errors, 0 warnings, 0 informations**
- `git grep "CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT" -- ':!dayu/host/compaction.py' ':!docs/'`: **无外部生产引用**
