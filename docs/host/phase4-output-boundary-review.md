# P4 Internal Output Boundary 专项 Review

## 结论

未通过，存在 findings。

本次 review 动机成立：`docs/host/phase4-plan.md` 与 `docs/host/design.md` 均把 Host Memory / compact memory 定位为 internal grounding context / verification context，并明确要求不得把 `Host Memory`、`Tool Facts`、`Evidence Anchors`、`tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、`scope_token`、tool args/result repr 或 raw EventLog metadata 原样输出到 final answer。当前实现已经在输入侧加了 internal-only / not-output-template 提示，但输出侧和测试侧仍不足以捕捉回显风险。

## Findings

### High: [已修复，待复查] final answer 对内部 Host Memory 标题、字段和工具结果 repr 没有输出边界测试，当前 Host 会原样透传 Engine final content

直接证据：

- `dayu/host/_event_translation.py:60`-`77` 的 `translate_engine_event()` 直接把 Engine `event.data` 放入 Host `RunEventDraft`，没有检查或标记 final answer 中是否包含内部标题 / 字段。
- `dayu/host/_event_translation.py:381`-`389` 的 `terminal_result_from_event()` 对 `FinalAnswerData.content` 直接赋给 `RunSucceededResult.content`，没有过滤、降级或测试钩子。
- P4 retry 测试中的 fake final answer 是干净文本 `已基于证据回答。`，只断言结果等于该文本：`tests/host/test_phase4_overflow_retry.py:153`-`164`、`tests/host/test_phase4_overflow_retry.py:322`-`323`。没有任何用例让 fake Engine 回显 `Host Memory`、`Tool Facts`、`Evidence Anchors`、`历史工具摘要`、`tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、`scope_token`、tool result repr 或 raw EventLog metadata 后断言被捕捉。
- 工具事实摘要来源还可能包含工具结果 repr：`dayu/host/_conversation_memory.py:807`-`812` 对 `ToolCompletedOutcome` 使用 `repr(outcome.result.value)` 生成 `工具结果已接纳：value=...` 摘要。该摘要随后会进入 `Tool Facts`，见 `dayu/host/_run_input_builder.py:960`-`966`。

影响：

当前 P4 的“internal-only / not-output-template”只是 prompt 约束。只要模型或 fake Engine 把 system block 中的内部标题、字段、cursor 指纹或工具结果 repr 原样放进 final answer，Host 会把它作为成功结果落库并返回。现有测试不会失败，因此不能证明用户重点担心的回显风险已被 P4 捕捉。

建议：

至少补一个 Host 层输出边界回归：fake proxy 在 compact retry 后返回包含上述禁止 token 的 `FinalAnswerData.content`，测试应能失败或产生明确 degraded / filtered / contract violation 行为。如果 P4 明确只做提示层约束、不做输出治理，也应把测试目标改成“smoke 观察无法保证”，并在 P4 交付说明中列为未覆盖风险，不能声称 final answer 回显风险已被捕捉。

修复说明：

- `translate_engine_event()` 对 `FINAL_ANSWER` 增加最小输出边界 gate，命中 Host Memory / Tool Facts / evidence 字段 / raw EventLog metadata / 工具结果 repr 等内部标记时，过滤为安全占位文本，并设置 `filtered=True`、`degraded=True`。
- 已补 `tests/host/test_phase4_overflow_retry.py::test_internal_final_answer_echo_is_filtered_result`，fake Engine 回显内部字段时不再作为干净成功结果透传。

### Medium: [已修复，待复查] caller / app / agent system prompt 的主运行路径未支持，Host Memory 初始注入顺序缺少真实覆盖

直接证据：

- `LocalRunHarness.start_run()` 先调用 `_extract_current_user_text()`，随后完全用 `DefaultRunInputBuilder.build()` 的结果替换入口 `request.input`：`dayu/host/_run_harness.py:231`-`250`。
- `_extract_current_user_text()` 要求入口 `RunInput.messages` 必须且只能有一条非空 `UserMessage`，任何 `SystemMessage` 都会 `ValueError`：`dayu/host/_run_harness.py:897`-`918`。
- `DefaultRunInputBuilder.build()` 本身也没有 caller system prompt 参数，生成的 `RunInput` 固定是 `Host Memory` system message 后接 current user：`dayu/host/_run_input_builder.py:171`-`212`。
- compact helper 对已有非 Host system message 的相对顺序是正确的：`_build_compacted_run_input()` 会保留 previous input 中非 Host memory 的 `SystemMessage`，再追加 compact block 与 current user：`dayu/host/_context_compaction.py:294`-`309`。但真实 `LocalRunHarness` 初始入口不会让 caller/app/agent system prompt 进入这个路径。

影响：

若当前 P4 声称支持 caller / app / agent system prompt，则实现与声明不一致：主入口不是把 Host Memory 追加在 caller prompt 后，而是直接拒绝含 system prompt 的请求。若 P4 暂不支持 caller prompt，则这不是顺序错误，但需要在 review / README / design 中明确“当前无 caller prompt 主路径”，并补 compact helper 的顺序单测，避免后续接入 caller prompt 时破坏该约束。

修复说明：

- `LocalRunHarness.start_run()` 当前支持多条 leading `SystemMessage` + exactly one non-empty current `UserMessage`；仍拒绝 assistant/tool/history、多条 user、空 user 与 user 后追加 system。
- `DefaultRunInputBuilder.build()` 接收 caller system prompt 并保持顺序：caller system prompt(s) 在前，Host Memory system block 在后，current UserMessage 最后；compact retry 继承相同顺序。
- 已补 ordering 测试与非法入口消息拒绝测试。

## 已通过项

- `DefaultRunInputBuilder` 的 Host Memory block 在 `Tool Facts` / `Evidence Anchors` 之前有 block 级声明：`INTERNAL_ONLY`、仅供 grounding 与校验、不是最终回答模板，见 `dayu/host/_run_input_builder.py:627`-`635`。
- compact memory block 同样继承 internal-only / not-output-template 声明，并显式点名禁止输出 `Host Memory`、`Tool Facts`、`历史工具摘要`、`tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、`scope token`、raw EventLog metadata，见 `dayu/host/_context_compaction.py:318`-`342`。
- `Tool Facts` / `Evidence Anchors` 没有被渲染为 assistant/tool history message，而是进入 system memory block；P3 测试覆盖了不进入 assistant/tool 消息：`tests/host/test_phase3_run_input_builder.py:289`-`305`。
- 当前看到的 Host Memory / compact memory 输入侧未包含 `scope_token` 明文；测试也覆盖了 builder system content 不含 `scope_token`：`tests/host/test_phase3_run_input_builder.py:303`。

## 风险与未覆盖项

- 现有 P4 compact 测试主要断言 internal block 中保留 `source_event_cursor`、`tool_fact_id` 与 `INTERNAL_ONLY`：`tests/host/test_phase4_context_compaction.py:217`-`226`，没有断言 final answer 不包含这些内部字段。
- 当前实现允许把 `source_event_cursor` / `cursor_fingerprint` 放入 LLM-facing system block 作为 grounding 元数据；这与 P3/P4 的 evidence 保真目标一致，但进一步提高了 final answer 回显测试的重要性。

## 复审结论

复审通过，无 findings。

复审确认：

- Host Memory 与 Host Compact Memory 均保留 `INTERNAL_ONLY` / 非最终回答模板约束，且约束文本位于 `Tool Facts` / `Evidence Anchors` 等内部事实区块之前。
- `FINAL_ANSWER` 翻译边界已增加最小 internal echo gate，命中 `Host Memory`、`Tool Facts`、`Evidence Anchors`、`历史工具摘要`、`tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、`scope_token`、工具结果 repr 与 raw EventLog metadata 相关标记时，会替换为 filtered/degraded 安全占位；用户可见 `RunSucceededResult.content` 不再包含原始内部字段。
- `LocalRunHarness.start_run()` 主路径已支持多条 leading caller / app / agent `SystemMessage` 加一条非空 current `UserMessage`；首轮顺序为 caller system 在前、Host Memory 在后、User 最后，compact retry 顺序为 caller system 在前、Host Compact Memory 在后、User 最后。
- 非法入口形状仍拒绝：assistant/tool/history 消息、多条 user、user 后追加 system、空 user 均会在 ingress 边界失败。
- compact retry ordering 与首轮 ordering 一致，第二次 attempt 继承 caller system prompt，并替换为 Host Compact Memory。
- 新增测试覆盖了输出边界 gate、caller system 主路径、compact retry ordering 与非法入口拒绝，不再只是测试输入侧 prompt 注入。

验证：

```bash
source .venv/bin/activate && pytest tests/host/test_phase4_overflow_retry.py tests/host/test_phase4_context_compaction.py tests/host/test_phase3_run_input_builder.py -q
source .venv/bin/activate && pyright
```

结果：23 passed；pyright 0 errors。
