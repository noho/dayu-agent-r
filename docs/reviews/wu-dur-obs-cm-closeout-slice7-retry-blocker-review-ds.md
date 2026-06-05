# WU-CM-01-F01 Slice 7 Implementation Retry Blocker Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-dur-obs-cm-closeout-slice7-retry-blocker-review-ds.md`
- Included scope:
  - Uncommitted changes to `tests/host/public_smoke_support.py`、`tests/host/test_public_compact_smoke.py`、`tests/host/test_public_open_host_multiturn_smoke.py`、`tests/host/test_public_tool_wiring_smoke.py`、`tests/README.md`、`docs/host/issues-implementation-control.md`
  - Artifact `docs/reviews/wu-dur-obs-cm-closeout-slice7-implementation-retry-codex.md`
- Excluded scope: 已提交的 Slice 0-6 production commit（不在 review scope 内）；`utils/smoke_host_public_*.py` 四脚本未修改
- Design sources: `docs/host/design.md`、`docs/host/issues-implementation-control.md`、`docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 7
- Parallel review coverage: 无

## Review Questions & Verdicts

### Q1: Is the multi-system-message failure real public Host/Runner path evidence, not a test-private artifact?

**结论：是真实 public path 证据，不是测试私有产物。**

直接证据链：

1. 测试入口走 public `open_host()` → `submit_followup()` → worker dispatch → `AsyncRunner.call()` 完整链路。
2. `ToolCallingWorkerFactory` 在 `AsyncRunner.call()` 中记录 `self.messages_seen`，即实际传给 Runner 的 `AgentRunRequest.messages`。
3. 测试断言 `assert_at_most_one_system_message(factory.messages_seen[index], ...)` 读取的是这些 public-path messages，不是 durable table reconstruction。
4. 失败消息 `"tool wiring runner call 2 expected at most one system message, got 2; roles=('system', 'user', 'system', 'assistant', 'user')"` 中的 roles 序列直接对应 Runner 收到的 message list 中的 role 顺序，是 public path 的真实观测。

对应 production root cause（`dayu/host/run_input.py`，不在 Slice 7 allowed files 内）：

- `run_input.py:1867-1869` `_system_prompt_message()` → 第一条 `SystemMessage`
- `run_input.py:1869-1874` `build_scene_messages()` → 第二条 `SystemMessage`（Host execution context，line 1707）
- `run_input.py:1830-1831` `memory.messages` → `_memory_messages()`（line 2198-2224）按 section 产出独立 `SystemMessage`：Session Summary（line 2243）、Evidence/Fact（line 2268）、Answer Anchor（line 2297）、Forward Intent（line 2318）、Reference Continuity（line 2335）
- `run_input.py:1832` `compact.messages` → `SystemMessage`（line 1499）
- 上述全部以独立 `SystemMessage` 进入 `AgentRunRequest.messages`

这不是测试私有入口的记录偏差；测试观察到的就是 production RunInputBuilder 构造后传给 Engine/Runner 的实际 message list。

### Q2: Are added assertions in allowed files and aligned with Slice 7 success/stop conditions?

**结论：断言在 allowed files 内且语义对齐，但成功条件要求 production 行为变更而 Slice 7 不含生产代码修改权限。**

Slice 7 allowed files（plan line 608）：
- `tests/host/public_smoke_support.py` ✓
- `tests/host/test_public_compact_smoke.py` ✓
- `tests/host/test_public_open_host_multiturn_smoke.py` ✓
- `tests/host/test_public_tool_wiring_smoke.py` ✓
- 四个 `utils/smoke_host_public_*.py` — 未修改，已通过 `--help` 审计 ✓

新增断言与 Slice 7 invariants 对齐：

| 断言 | Slice 7 invariant | 对齐？ |
|---|---|---|
| `assert_at_most_one_system_message()` | "runner call 最多一个 system message"（F01 success signal） | 对齐 |
| `_assert_runner_call_manifest_messages()` | "compact 后 message_count / manifest / dump item 数量可解释"（F01 success signal） | 对齐 |
| `_assert_compactor_material_instruction_contract()` | "compactor prompt 不暴露内部实现术语"（Slice 7 expected assertion） | 对齐 |
| `test_default_compactor_prompt_is_llm_facing_and_self_contained()` | "Compactor prompt 不包含 `Host-owned context compaction`、`ConversationCompactOutputVNext`"（Slice 7 expected assertion） | 对齐 |

断言仅读取 public path 可观测数据（`AgentRunRequest.messages`、runner `messages_seen`、manifest JSON、material JSON），不读取 private durable table，不违反 "Smoke 不替代 focused durable tests" invariant。

但 Slice 7 stop condition 是："四个 smoke 入口任一仍无法解释 runner-call message_count mismatch，或需要依赖日志计数作为唯一证据。" 当前 one-system-message 断言失败就是该 stop condition 的触发场景——测试观测到了 production path 的真实 message shape mismatch，且 root cause 不在 allowed files 内。

### Q3: Is blocking root cause outside Slice 7 allowed files, requiring production RunInput/memory projection rescope?

**结论：是。Root cause 明确在 `dayu/host/run_input.py`，需要 production RunInputBuilder message assembly 或 memory projection 结构变更。**

Root cause 具体定位：

- `run_input.py:2198-2224` `_memory_messages()`：每个 memory section 返回独立 `SystemMessage`，组成 `memory.messages` 元组。调用方 `run_input.py:1831` 以 `*memory.messages` 展开进 `bounded_context_messages`。
- `run_input.py:1675-1708` `DeterministicSceneParameterProvider.build_scene_messages()`：Host execution context 作为独立 `SystemMessage`。
- `run_input.py:3052-3063` `_system_prompt_message()`：system prompt 作为独立 `SystemMessage`。
- `run_input.py:1499-1506` `CompactArtifactView.messages`：compact artifact 作为独立 `SystemMessage`。

上述所有文件均在 `dayu/host/run_input.py`，不在 Slice 7 allowed files 内。要收敛为至多一条 system message，至少需要以下之一：

- 将 system prompt、host execution context、memory sections、compact artifact 合并进单条 system message（改变 `run_input.py` message assembly）
- 或将部分 system-level 语义通过其他 role/结构传递（改变 memory projection contract）

两项都需要修改生产代码，超出 Slice 7 的 allowed files 范围。

**补充判断**：这种多 system message 设计是否本身就合理？当前设计选择是每个语义块（system prompt、execution context、session summary、evidence facts、answer anchors、forward intents、reference continuity、compact artifact）各成一条 `SystemMessage`，好处是语义边界清晰，每个块独立可替换；代价是多 system message 不是所有 provider/model 的最佳实践。但这属于产品设计决策，不是 review 需要裁决的；review 只需确认：若 Slice 7 要求至多一条 system message，必须修改 `run_input.py` 生产代码。

### Q4: Are compact material/manifest assertions correct and non-overbroad?

**结论：核心断言正确，有一个 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 条目存在轻微过度风险。**

正确的断言：

- `_assert_compactor_material_instruction_contract()`：验证 `instruction.output_schema_name == "conversation_compact_output_v1"` 且 material JSON 不含 `_FORBIDDEN_COMPACTOR_MATERIAL_TERMS`。这与 design.md line 2591 "compact input/output 不得暴露 EventLog id、payload ref、digest、cursor、policy 等内部治理细节" 对齐。
- `_assert_runner_call_manifest_messages()`：验证 `message_count`、`message_entries` 长度、per-entry `index`/`role`、role 序列与 `role_sequence_digest` 同源。digest 计算使用 `runner_role_sequence_digest()`（Engine contract public function），不依赖 magic string。
- `test_default_compactor_prompt_is_llm_facing_and_self_contained()`：验证 prompt 自足说明输入输出 JSON 字段、最小示例、label 引用规则。

过度风险点：

- `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 包含 `"policy"` 和 `"digest"`。`"digest"` 在 prompt 中若有类似 "digest the information" 的业务表述会误触发；`"policy"` 同样。但从当前 prompt 上下文看，这两个词在 compactor prompt 中使用概率低，且 prompt 不变时断言不会误触发。风险为低。
- `_FORBIDDEN_COMPACTOR_MATERIAL_TERMS` 中 `"tool_call_id="` 有具体 `=` 后缀约束，不会误匹配普通文本中 `tool_call_id` 作为字段名出现的情况。设计合理。
- `"ConversationCompactOutput"` 和 `"ConversationCompactInput"`（不含 `VNext` 后缀）的禁止比 S6-R1 的范围更宽，但符合 design.md 要求：LLM-facing material 不应暴露任何内部 Python 类型名。

### Q5: Is tests/README update justified?

**结论：是，符合 AGENTS.md 触发规则。**

触发规则：AGENTS.md 明确 "tests/ 修改 → 更新 tests/README.md"。

变更内容（`tests/README.md` line 130）：
- 在 `public-path smoke` 段对 `test_public_tool_wiring_smoke.py` 和 `test_public_open_host_multiturn_smoke.py` 补充 "并对记录到的 runner call messages 校验最多一条 system message"
- 对 `test_public_compact_smoke.py` 补充 "manifest 的 message_count / message_entries / role sequence digest 同源" 和 "默认 compactor prompt 和 material 不暴露内部实现术语且自足说明输入输出"

以上更新准确反映了测试行为变化，不越界写实现细节，不包含未来计划。未更新根 README（CLI usage 未变），判断正确。

### Q6: Is it acceptable to classify this retry as blocked even though targeted pytest fails by design while pyright/diff check pass?

**结论：是，blocked 分类正确且有原则。**

理由：

1. Slice 7 的 success condition 是 "runner call 最多一个 system message"（plan line 38 F01）。当前 production path 无法满足此条件，且 root cause 在 Slice 7 allowed files 之外。
2. pytest 失败是由正确的断言驱动的——断言读到了 production path 的真实 message shape，不是测试基础设施问题。
3. pyright 通过（0 errors）证明类型层面正确；`git diff --check` 通过证明无空白/格式问题。这两个检查通过是 "retry 本身没有引入低级错误" 的证据，不是 "retry 应该无阻断通过" 的理由。
4. 如果因为 pyright 通过就 weakening 断言使 pytest 通过，会直接违反 Slice 7 的核心目标——验证 public path 的 LLM-facing message 质量。
5. 代码未修改生产行为，说明 retry 遵守了 Slice 7 边界约束；在边界处停止是正确的工程判断。

对比 "completed-with-evidence" 分类：如果 Slice 7 定义为 "添加断言并报告结果"，那它应该 completed。但 plan 明确将 one-system-message 列为 success signal（而非 optional observation），且 stop condition 是 "任一仍无法解释 runner-call message_count mismatch"。当前状态恰好触发 stop condition，blocked 分类准确。

## Findings

### 1-未修复-严重-production RunInput message assembly 产出多条 system message，不符合 Slice 7 one-system-message 收敛要求

- **入口/函数**: `RunInputBuilder.build()` → `AgentRunRequest.messages` 组装
- **文件(行号)**: `dayu/host/run_input.py:1867-1879`（assembly 点），根因散布在 `run_input.py:2198-2224`（`_memory_messages`）、`run_input.py:1707`（`build_scene_messages`）、`run_input.py:1499`（`CompactArtifactView.messages`）、`run_input.py:3062`（`_system_prompt_message`）
- **输入场景**: 任意 `open_host()` → `submit_followup()` 路径触发 worker dispatch，且 Session 中存在 memory snapshot（含 summary / facts / anchors / intents / continuity）或 compact artifact
- **实际分支**: `run_input.py:1830-1833` non-fallback 路径，`memory.messages` 中每个 memory section 以独立 `SystemMessage` 展开；`compact.messages` 以独立 `SystemMessage` 展开；`build_scene_messages()` 的 host execution context 和 `_system_prompt_message()` 的 system prompt 各为独立 `SystemMessage`
- **预期行为**: Slice 7 F01 success signal 要求 runner call messages 至多一条 system message
- **实际行为**: public path 产出 2-5 条 `SystemMessage`（取决于 memory 当前有内容的 section 数量）
- **直接证据**: 
  - `run_input.py:2198-2224` `_memory_messages()` 对 session summary（line 2243）、evidence facts（line 2268）、answer anchors（line 2297）、forward intents（line 2318）、reference continuity（line 2335）各返回独立 `SystemMessage`
  - 测试失败报告 `"got 5; roles=('system', 'system', 'system', 'user', 'system', 'assistant', 'system', 'user')"` 对应 production path 实际产出
- **影响**: Slice 7 closeout 受阻；public smoke 无法证明 LLM-facing message shape 收敛
- **建议改法和验证点**: 
  1. 决定 one-system-message 是否为 hard requirement（若多 system message 是设计意图，则需调整 Slice 7 success condition）
  2. 若为 hard requirement，需修改 `run_input.py` message assembly 将 system prompt、host execution context、memory sections、compact artifact 合并为单条 system message（可能需要结构化分隔符）
  3. 修改后运行 Slice 7 聚焦 pytest 验证收敛
- **修复风险（低/中/高）**: 中 — 改变 message structure 可能影响所有 provider 的推理质量，需评估不同 model 对单条 vs 多条 system message 的响应差异
- **严重程度（低/中/高/严重）**: 严重 — 阻断 Slice 7 closeout，影响 WU-CM-01 整体收敛

### 2-未修复-低-`_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 中 `"policy"` 和 `"digest"` 可能在未来 prompt 变更时误触发

- **入口/函数**: `test_default_compactor_prompt_is_llm_facing_and_self_contained()`
- **文件(行号)**: `tests/host/test_public_compact_smoke.py:108-111`（`_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 定义）、`test_public_compact_smoke.py:131`（断言循环）
- **输入场景**: 未来修改 compactor prompt，加入 "follow the compaction policy below" 或 "digest the conversation" 等合法业务表述
- **实际分支**: 断言 `for forbidden_term in _FORBIDDEN_COMPACTOR_PROMPT_TERMS: assert forbidden_term not in prompt_text`
- **预期行为**: 禁止内部术语但不误伤业务可读文本
- **实际行为**: `"policy"` 和 `"digest"` 是英语通用词，若 prompt 使用其业务含义会误触发
- **直接证据**: `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 值为 `("Host-owned context compaction", "ConversationCompactOutputVNext", ..., "policy", ..., "digest", ...)`
- **影响**: 低 — 当前 prompt 中不存在这些用法，且 prompt 变更频率低；若误触发，只需从禁止列表中移除
- **建议改法和验证点**: 将 `"policy"` 替换为更精确的 `"policy ref"` 或 `"policy_snapshot_ref"`；将 `"digest"` 替换为 `"artifact_digest"` 或完全移除（material assertion 已有足够覆盖）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

1. **one-system-message 是否是 hard requirement？** 当前 RunInputBuilder 设计将不同语义块（system prompt、execution context、各 memory section、compact artifact）作为独立 `SystemMessage`。如果多 system message 是经过 provider 兼容性验证的合理设计选择，则 Slice 7 的 one-system-message success condition 需要调整。反之，若收敛为单条 system message 是产品要求，则需要 rescope production RunInput message assembly。

2. **多 system message 对不同 provider 的实际影响是什么？** 大部分 OpenAI-compatible API 支持多条 system message，但部分 provider（如 Anthropic Messages API）可能有不同处理方式。需要明确是否已有 provider 兼容性问题证据推动 one-system-message 要求，还是预防性约束。

## Residual Risk

- Slice 7 retry 未修改 `utils/smoke_host_public_*.py` 四个脚本，仅通过了 `--help` 审计。若需要完整的 utility smoke 运行验证（需要 provider/runtime 配置），仍有未覆盖区域。
- `test_real_compactor_public_opener_compacts_and_preserves_continuity` 默认 skip（需 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1`），real compactor path 的 one-system-message 行为未在本 retry 中验证。
- `test_public_real_runner_matrix_smoke.py` 覆盖 mimo/deepseek/gemini/qwen 的 real runner public path 未加入 one-system-message 断言，不同 provider 的 system message 行为可能不一致。

## Validation Commands

验证 retry 当前状态（预期：4 failed 是 one-system-message 断言失败）：

```bash
source .venv/bin/activate
pytest tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -v
```

验证 production root cause：

```bash
# 确认 SystemMessage 构造点都在 Slice 7 allowed files 之外
grep -n "SystemMessage(" dayu/host/run_input.py
```

验证 utility smoke 入口健康：

```bash
source .venv/bin/activate
python utils/smoke_host_public_conversation_memory.py --help
python utils/smoke_host_public_diagnostics.py --help
python utils/smoke_host_public_conversation_memory_scenarios.py --help
python utils/smoke_host_public_multiturn.py --help
```

验证类型和格式：

```bash
source .venv/bin/activate && pyright
git diff --check
```

## Verdict

**Slice 7 retry blocked — 证据有效。** Production public path 产出多条 system message 的直接证据来自 `run_input.py` 的 message assembly 代码与 public smoke 的 Runner-call messages 观测，两者一致。Root cause 明确位于 `dayu/host/run_input.py`（不在 Slice 7 allowed files 内），需要 production RunInputBuilder message assembly 或 memory projection 结构变更才能收敛。Retry 正确地在 Slice 7 边界处停止，未为了通过测试而修改生产代码或 weakening 断言。

建议 controller 裁决方向：
- **若 one-system-message 是 hard requirement**：将生产 RunInput/memory projection rescope 作为新 slice 或 phase 的前置条件
- **若多 system message 是可接受的当前设计**：调整 Slice 7 success condition，放宽 one-system-message 要求，或改为验证 system message 的语义正确性而非数量
