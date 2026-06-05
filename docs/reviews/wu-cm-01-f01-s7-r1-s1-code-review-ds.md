# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-ds.md`
- Design source: `docs/host/design.md` §23 (RunInputBuilder), §23.1 (Manifest), §24.6 (Prompt Assembly)
- Accepted plan: `docs/host/wu-cm-01-f01-s7-r1-one-system-message-rescope-plan.md`
- Implementation artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s1-implementation-codex.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Included scope:
  - `dayu/host/run_input.py` — `_normalize_ordinary_run_messages()`、system envelope section routing、manifest recorder、memory message rendering、compact summary rendering、fallback message rendering
  - `tests/host/test_run_input_builder.py` — focused one-system-message assertions
  - `tests/host/public_smoke_support.py` — `assert_at_most_one_system_message()`
  - `tests/host/test_public_compact_smoke.py` — public smoke one-system assertions
  - `tests/host/test_public_tool_wiring_smoke.py` — public smoke one-system assertions
  - `tests/host/test_public_open_host_multiturn_smoke.py` — public smoke one-system assertions
  - `dayu/host/README.md` — documentation sync
  - `tests/README.md` — documentation sync
- Excluded scope: compactor proposal path（`dayu/host/llm_compaction.py`、`dayu/host/compaction_operation.py` 等），不属 ordinary RunInput contract
- Parallel review coverage: 无（单 reviewer 走读全部关键路径）

## Findings

### 01-未修复-中-test 禁止片段是 production 禁止片段的真子集

- **入口/函数**: `tests/host/test_run_input_builder.py` `_assert_system_content_has_no_internal_refs()`
- **文件(行号)**: `tests/host/test_run_input_builder.py:3757-3770`
- **输入场景**: 任意 ordinary RunInput focused test 通过 `_single_system_content()` 断言 system envelope 不暴露内部标识
- **实际分支**: focused test 在 `_assert_system_content_has_no_internal_refs` 中检查 `forbidden_fragments` 元组，该元组只包含 12 个片段
- **预期行为**: focused test 应与 production `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 保持同步或为超集，以证明 production 的完整 forbidden-fragment 集在真实 RunInputBuilder 输出中不会出现
- **实际行为**: production `dayu/host/run_input.py:191-212` 的 `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 包含 21 个片段，但 test `forbidden_fragments` 只包含 12 个。以下 production 禁止片段在 test 中未覆盖：
  - `"manifest_payload_ref="`
  - `"manifest_digest="`
  - `"projection_checkpoint"`（test 有 `"checkpoint_event_id"` 和 `"checkpoint_event_sequence"`，但缺 bare `"projection_checkpoint"`)
  - `"projector_metadata"`
  - `"attempt_id="`
  - `"execution_id="`
  - `"runner_call_index="`
- **直接证据**:
  - Production 禁止列表: `dayu/host/run_input.py:191-212`
  - Test 禁止列表: `tests/host/test_run_input_builder.py:3757-3770`
  - 逐项对比证实 test 缺少上述 7 个片段
- **影响**: 若未来代码回归使 `attempt_id=xxx`、`execution_id=xxx` 或 `manifest_payload_ref=` 等片段泄漏到 LLM-facing content，focused RunInputBuilder tests 不会捕获（`assert` 不检查这些片段），但 production runtime 会在 `_validate_system_envelope_content` 抛出 `HostDurableError`。这意味着 test 与 production 之间存在置信度鸿沟——test 声称证明内部字段不泄露，但实际上只证明了部分字段。只有 production runtime error 会兜底捕获，这可能导致 CI 中隐秘的 runtime 失败而非清晰的 assert 差异。
- **建议改法和验证点**:
  1. 将 test 的 `forbidden_fragments` 扩充至与 production `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 完全一致，或从 `dayu.host.run_input` 导入同一常量。
  2. 补充 focused test case 显式覆盖每个禁止片段的反例（inject known bad content → assert runtime error）。
  3. 同步更新 `tests/host/test_run_input_builder.py` 中其他使用类似断言的位置（若有）。
- **修复风险（低）**: 仅扩大 test 断言范围，不改变 production 行为
- **严重程度（中）**: test 提供的证明弱于 production 实际要求，导致回归可能以 misleading pass 形式通过 focused tests

---

### 02-未修复-中-`_system_envelope_overhead` 不计算同 section 内 item 连接换行符

- **入口/函数**: `_validate_system_envelope_content()` → `_system_envelope_overhead()`
- **文件(行号)**: `dayu/host/run_input.py:2655-2677`（validate），`dayu/host/run_input.py:2680-2694`（overhead）
- **输入场景**: 同一 system envelope section 包含两条或更多 candidate system material（例如 post-compact 同时有 memory session summary 和 compact artifact summary 都进入 `Conversation Summary`，或 restore 场景多条 resume guidance 进入同一 `Resume Guidance`）
- **实际分支**: `_non_empty_system_section_blocks` 在 line 2637 用 `"\n".join(items)` 拼接同 section 内的多条 item；`_system_envelope_overhead` 只计算 section 级 header 和 section 间 separator，不计算 item 级连接符
- **预期行为**: envelope 的 boundedness sanity check 应在任何合法 input 下通过；overhead 应准确反映所有由合并引入的新增字符
- **实际行为**: 当 section 内 item 数 >= 2 时，`"\n"` 连接符使实际 envelope 长度超出 `source_system_chars + overhead` 上限。`_validate_system_envelope_content` 的条件 `len(content) > source_system_chars + overhead` 在此场景下为 `True`，导致误抛 `HostDurableError("ordinary system envelope exceeded deterministic overhead")`。
- **直接证据**:
  - `dayu/host/run_input.py:2637`: `"\n".join(items)` — 同 section 内 item 间插入 `\n`
  - `dayu/host/run_input.py:2680-2694`: overhead 仅计算 `header_chars + separator_chars`，不含 item 级 join
  - 具体计算：设 2 个 item 同在 section S，`source_system_chars = len(item1) + len(item2)`（已 strip），final envelope 含 `item1 + "\n" + item2`，多出 1 字符未计入 overhead
- **影响**: 当前测试套件 56 passed 未触发此路径（现有场景每 section 最多 1 条 item），但若未来 post-compact 场景同时产出 accepted compact view summary 与 delta session summary，或 resume 路径两条 guidance 合并，将在 runtime 误抛异常。这是一个 **latent bug**——当前不触发，但架构上已在代码中存在，不是在调用方保护就能消除。
- **建议改法和验证点**:
  1. 在 `_system_envelope_overhead` 中加入 item-join overhead: 对每个 section，`(len(items) - 1) * 1`（每个 `\n` 1 字符）。
  2. 添加 focused test：构造同一 section 2+ items，验证 envelope 正常渲染且 boundedness sanity 不误抛。
  3. 同时确认 `_non_empty_system_section_blocks` 中 `"\n".join(items)` 的语义是否与设计期望一致（两个 item 是否需要额外分隔，还是仅 `\n` 足够）。
- **修复风险（低）**: overhead 函数的改动仅影响该 sanity check 的判定，不影响实际 envelope 内容
- **严重程度（中）**: 虽当前未被现有测试触发，但一旦触发即为 runtime error 阻断 dispatch，属 latent correctness bug

---

### 03-未修复-低-test `forbidden_fragments` 硬编码串与 production 禁止列表不同步

- **入口/函数**: `_assert_system_content_has_no_internal_refs`
- **文件(行号)**: `tests/host/test_run_input_builder.py:3757`
- **输入场景**: 任意 focused test 通过 `_single_system_content` 校验
- **实际分支**: test 中的 forbidden list 是独立维护的 tuple literal，不从 production 导入
- **预期行为**: test 与 production 应共享同一禁止片段定义源，或 test 显式从 production 导入常量
- **实际行为**: 两个列表独立维护，必然随未来 design §23 内部字段表扩展而漂移。production 禁止片段列表 (`dayu/host/run_input.py:191-212`) 是模块级私有常量，test 不应重复声明。
- **直接证据**:
  - Production: `dayu/host/run_input.py:191` — `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS`
  - Test: `tests/host/test_run_input_builder.py:3757` — 独立 `forbidden_fragments` tuple
- **影响**: maintenance burden，两处列表漂移导致 test 覆盖盲区（已在 Finding 01 证实）
- **建议改法和验证点**: test 从 `dayu.host.run_input` 导入 `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS`，或提取到 shared test contract module
- **修复风险（低）**: 仅改 test import，不改 production
- **严重程度（低）**: 已有 Finding 01 覆盖更严重的安全后果；此处聚焦 maintainability

---

### 04-未修复-低-`_system_envelope_section_and_body` 默认分支不验证空内容

- **入口/函数**: `_system_envelope_section_and_body()`
- **文件(行号)**: `dayu/host/run_input.py:2534-2602`
- **输入场景**: caller system prompt (`_system_prompt_message` 产出) 为空白或仅含空格的内容
- **实际分支**: `content.startswith(...)` 对所有已知前缀返回 `False`，落入 `return (_SYSTEM_SECTION_TASK_INSTRUCTIONS, content)` (line 2602)，其中 `content` 是已经过 `message.content.strip()` 的值
- **预期行为**: 空 `Task Instructions` section 应在 normalization 中 fail closed（设计要求 "空 section 不渲染"），或由 envelope validation 捕获
- **实际行为**: 若 caller system prompt 为仅含空格的字符串（如 `"   "`），`message.content.strip()` 返回 `""`，`_normalize_ordinary_run_messages` 在 line 2506 捕获并抛出 `HostDurableError`。但若 system prompt 为 `None`，`_system_prompt_message` 返回空 tuple，不会有 system message 产生。这两种情况都被正确处理。
  然而，若 caller system prompt 为非空但内容恰好以某个已知前缀开头（如以 `"Execution guidance:"` 开头），会被错误路由到 `Execution Guidance` section 而非 `Task Instructions`。这是 prefix-matching router 的固有风险，目前未见 caller system prompt 可能以此类前缀开头，但缺乏显式 guard。
- **直接证据**:
  - `dayu/host/run_input.py:3354-3365`: `_system_prompt_message` 不为其产出的 content 加任何 caller 私有前缀
  - `dayu/host/run_input.py:2602`: 默认 `return (_SYSTEM_SECTION_TASK_INSTRUCTIONS, content)`
- **影响**: caller system prompt 若偶然以内部前缀开头会被错误归类，但当前所有生产 caller prompt 不以下划线前缀常量开头，概率极低
- **建议改法和验证点**: 为 caller system prompt 增加显式前缀包裹（如 `Caller system prompt:\n{content}`），或改为 typed section routing（而非纯文本 prefix matching）
- **修复风险（低）**: 需配合 caller prompt expectation 调整
- **严重程度（低）**: 当前生产无触发场景，属防御性改进

---

### 验证通过项（逐条确认无问题）

以下检查项均通过直接代码走读验证，不产生 finding：

| 检查项 | 验证依据 | 结论 |
|---|---|---|
| ordinary `AgentRunRequest.messages` 至多一条 system | `dayu/host/run_input.py:2487-2531` `_normalize_ordinary_run_messages()` 全局合并所有 SystemMessage 为单条 | PASS |
| 唯一 system 必须在首位 | `dayu/host/run_input.py:2528-2530` 返回 `(SystemMessage(...), *non_system)` | PASS |
| compactor proposal 未进入 ordinary contract | `dayu/host/run_input.py` 无 `compactor_proposal` 引用；compactor 通过 `dayu/host/llm_compaction.py` 独立路径 | PASS |
| `RUNNER_CALL_INPUT_ASSEMBLED` manifest 记录 normalized messages | `dayu/host/run_input.py:1924` `messages = _normalize_ordinary_run_messages(candidate_messages)` → `dayu/host/run_input.py:1925-1936` 传入 recorder → `dayu/host/run_input.py:3780` `message_count` 用 `len(record_input.messages)` | PASS |
| section 标题与顺序符合设计 §23 | `dayu/host/run_input.py:161-179` 9 个 section title 与 `dayu/host/run_input.py:170-179` 顺序与 `docs/host/design.md:2554-2564` 完全一致 | PASS |
| section 标题是 LLM-facing 业务标题 | `dayu/host/run_input.py:161-169` 使用 `"Task Instructions"`, `"Execution Guidance"`, `"Conversation Summary"` 等自然语言标题，不是 projector id / Python 类型名 / policy ref | PASS |
| section 间使用固定双换行分隔 | `dayu/host/run_input.py:159` `_SYSTEM_ENVELOPE_SEPARATOR = "\n\n"`，在 `_render_system_envelope` line 2652 使用 | PASS |
| section 标题用 Markdown 二级标题 | `dayu/host/run_input.py:160` `_SYSTEM_ENVELOPE_HEADER_PREFIX = "## "`，`_render_system_envelope` line 2649 使用 | PASS |
| accepted evidence、recent fallback、resume guidance 唯一归属 | `_system_envelope_section_and_body` 基于前缀路由，memory fact 进入 `Verified Evidence and Facts` (`_MEMORY_EVIDENCE_FACT_HEADER`)，fallback evidence 进入 `Recent Evidence` (`_RECENT_EVIDENCE_PREFIX` / `_ACCEPTED_TOOL_EVIDENCE_PREFIX`)，resume 进入 `Resume Guidance` (`_RESUME_GUIDANCE_PREFIX`)。`build()` 中 `fallback is None` 与 `fallback is not None` 互斥，同一条 evidence material 不会同时路由到两个 section | PASS |
| 无双重渲染 | compact summary 和 memory session summary 都路由到 `Conversation Summary`，但它们的 source 不同（分别来自 `_ACCEPTED_COMPACTED_VIEW_PREFIX` 和 `_MEMORY_SESSION_SUMMARY_HEADER`），不重复同一材料 | PASS |
| LLM-facing 不暴露 `policy_snapshot_ref` | `dayu/host/run_input.py:192` forbidden fragment 包含；`build_scene_messages` 在 line 1744-1748 产出 Host-neutral `"Use the available context and tools under the current run limits."` | PASS |
| LLM-facing 不暴露 `tool_call_id` | `dayu/host/run_input.py:193-194` forbidden fragment 包含 `"tool_call_id="` 和 `"tool_call_id"`（裸词）；resume guidance line 3477-3485 不含 `tool_call_id`，只用 `tool_name` | PASS |
| LLM-facing 不暴露 EventLog id/sequence | `dayu/host/run_input.py:195-196` forbidden fragment 包含；memory fact 渲染 line 2302-2307 使用 `Source F{n}` prompt-local label | PASS |
| LLM-facing 不暴露 digest/cursor | `dayu/host/run_input.py:199-201` forbidden fragment 包含 `compact_artifact_digest=`, `manifest_digest=`；`_vnext_compact_candidate_summary` line 3190-3226 只渲染 counts 和 summary text | PASS |
| LLM-facing 不暴露 Python 类型名 | `dayu/host/run_input.py:211` forbidden fragment 包含 `"ConversationCompactOutputVNext"` | PASS |
| boundedness sanity 存在 | `dayu/host/run_input.py:2655-2677` `_validate_system_envelope_content` 计算 overhead 并比较 `len(content) <= source_system_chars + overhead`；`dayu/host/run_input.py:2680-2694` `_system_envelope_overhead` 计算 header + separator 字符 | PASS（见 Finding 02 的 latent bug） |
| manifest 不内联完整 messages | `dayu/host/run_input.py:3906-3918` `_runner_call_message_entries` 只保存 `content_digest` + `content_size_bytes`，不保存 content 本体；`test_runner_call_manifest_is_bounded_and_does_not_inline_messages` line 360-403 验证大 input 不进入 manifest | PASS |
| public smoke 断言未放松 | `tests/host/public_smoke_support.py:178-200` `assert_at_most_one_system_message` 检查 count ≤ 1 且唯一 system 在 index 0；三个 public smoke 文件均调用该 helper | PASS |
| focused tests 覆盖多场景 | `tests/host/test_run_input_builder.py` 覆盖 no-compact、post-compact、manifest boundedness、noop provider manifest rows | PASS |
| `user`/`assistant` role 保留 | `_normalize_ordinary_run_messages` line 2511-2514 保留 UserMessage/AssistantMessage 原 role 和顺序 | PASS |
| selected recent window evidence 不产生额外 system message | `_memory_selected_recent_window_messages` line 2378-2411 中 user→UserMessage, assistant→AssistantMessage, 其它→SystemMessage（与其它 system material 合并） | PASS |
| README 只同步稳定职责 | `dayu/host/README.md` 新增 RunInputBuilder manifest、`TOOL_CALL_REQUESTED` atom、Tool Trace signal 文档；`tests/README.md` 更新测试覆盖描述；均反映实际代码行为，无 stale content | PASS |

## Open Questions

1. **`_system_envelope_section_and_body` 的前缀匹配路由是否足够 robust**: 当前依赖 `content.startswith(prefix)` 做 section routing。如果两个不同的 source 使用了相同的前缀（如 compact summary 和 memory summary 都使用不同前缀但都路由到 `Conversation Summary`，这是有意的），但若未来有新的 system material source 意外与现有前缀冲突，会导致错误路由。建议考虑 typed section routing（在 candidate 中携带显式 section enum）而非纯文本 prefix matching。——但这是 future-proofing 问题，当前所有 source 的 prefix 是模块级常量，不冲突。

2. **`_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 中 `"tool_call_id"` (line 194) 和 `"tool_call_id="` (line 193) 的冗余**: line 193 的 `"tool_call_id="` 已经是 line 194 `"tool_call_id"` 的子串匹配。如果 content 包含 `"tool_call_id=abc123"`，line 193 会命中；如果 content 包含 `"tool_call_id"` 不带 `=`，line 194 会命中。但 `"tool_call_id"` (line 194) 是一个更宽泛的匹配——它也会匹配 `"tool_call_id=..."`。两行都可以简化为仅 `"tool_call_id"`。这不是 bug，但可简化。

## Residual Risk

- **Finding 02 的 latent bug**: 同 section 多 item 场景目前未被测试覆盖。需要补充 focused test 并在 overhead 计算中修复，否则未来 post-compact memory + compact summary 合并场景会在 runtime 误抛异常。
- **Provider-specific system envelope behavior**: 不同 provider 对单条长 system envelope 的处理能力未在本轮验证（plan 明确列为后续 work）。当前所有 public smoke 使用 deterministic runner，未覆盖 real provider 对合并后长 system envelope 的实际行为差异。
- **Historical evidence role preservation trade-off**: design §23 明确接受 selected recent evidence 从原交错位置提前到 system envelope 的开头。这是被接受的 trade-off，但如 Engine 未来支持 historical `tool` role，需要回改本实现。当前无回归测试覆盖该未来迁移场景。
- **Test forbidden fragments 同步**: Finding 01 指出 test 禁止片段是 production 的真子集。虽然 production runtime 会兜底，但 CI 中可能出现 production 失败但 focused test 通过的不一致。建议尽快同步。
