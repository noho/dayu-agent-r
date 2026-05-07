# Host P4 OLD/NEW 语义专项 Code Review

结论：未通过，有 findings。

本次只做静态 code review，未修改实现代码，未运行测试。P4 的动机成立：context overflow 后 compact/retry 的所有权确实应该从 Engine 迁到 Host；但当前实现仍有几处会破坏 OLD 关键语义或 NEW 计划约束。

## Findings

### Finding 1 — [已修复，待复查] 同一 Run 内 overflow 前已落库的工具事实没有进入 compact 输入，可能造成证据断链（严重）

**文件**：`dayu/host/_run_harness.py:351`、`dayu/host/_run_harness.py:387`、`dayu/host/_run_harness.py:436`、`dayu/host/_context_compaction.py:115`、`dayu/host/_context_compaction.py:321`

**问题**：`_run_to_store` 在 overflow 前会把非终态 Engine 事件先 append 到 EventStore（例如 `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED`），但 `_compact_or_fail` 触发时只读取 `memory_store.get_snapshot()`，而 memory projection 只在 `terminal_seen` 后的 `finally` 中执行。也就是说，同一次 attempt 中 overflow 前已经发生并落库的 canonical tool facts，不会进入本次 compact 使用的 `ConversationMemorySnapshot`，随后 `_build_compacted_run_input` 只从旧 snapshot 渲染 compact memory。

**为什么严重**：OLD `_compact_messages` 的核心不变量之一是保留最近尾部，并在切分时不拆散 `assistant(tool_calls)` + `tool` 结果组；即使中间历史被压缩，也会把工具结果摘要带入 summary。NEW plan 也要求 compact 输入来自 `USER_INPUT_ACCEPTED`、canonical terminal / tool facts、memory snapshot 与 trace 中的可消费事实。当前实现只继承了“旧 memory snapshot”部分，漏掉了“本 attempt 已发生的 canonical tool facts”。

**财报分析风险**：第一轮 attempt 可能已经通过 fins 工具拿到某个年报 chunk / source cursor / tool result summary，然后在后续模型调用时 context overflow。compact retry 后这些刚取到的证据不会随 RunInput 进入第二次 attempt；模型要么重新取数，要么在缺失证据锚点的情况下继续作答，容易产生“回答看似正确，但 source cursor / evidence anchor 断链”的结果。

**建议**：compact 前从本 Run 的 EventStore 读取 overflow 前已 append 的 canonical tool facts / evidence anchors，或提供一个仅用于当前 Run 的临时 memory projection，合并到 compact 输入；同时补测试：同一 Run 先产生工具事实再 overflow，compact 后 RunInput 必须保留 tool_call_id、source_event_cursor、cursor_fingerprint / has_more 等等价 evidence。

**修复说明**：已新增同源临时工具事实投影 helper，compact 前读取本 Run EventLog 中已 append 的 canonical tool facts / evidence anchors 并合并进 compact snapshot；已补同 Run tool fact 后 overflow 的 retry 测试，断言 compacted attempt 保留 `tool_call_id`、`source_event_cursor`、`cursor_fingerprint`、`has_more`。

### Finding 2 — [已修复，待复查] Host token estimator 没有继承 OLD 的保守换算分母，中文财报文本被系统性低估（高）

**文件**：`dayu/host/_token_estimator.py:18`、`dayu/host/_token_estimator.py:21`、`dayu/host/_token_estimator.py:24`、`dayu/host/_context_compaction.py:94`、`dayu/host/_context_compaction.py:120`

**问题**：当前 estimator 使用半角 `1 unit`、全角/宽字符 `2 units`，但 `TOKEN_UNITS_PER_ESTIMATED_TOKEN = 4`。OLD `conversation_memory.py` 的对应常量是 `2`，即中文宽字符大致按 1 token/字、半角按 0.5 token/字符估算。当前实现把中文宽字符估成 0.5 token/字，明显比 OLD 宽松，且测试 `FY2024 营收增长 12% -> 5 tokens` 也锁死了这个宽松口径。

**为什么严重**：P4 plan 明确要求不要继续依赖 P3 `_APPROX_TOKEN_CHARS=4` 粗估，而要继承 OLD 对中英文混合财报文本更保守的宽/窄字符估算。当前分母为 4，虽然形式上有宽/窄 unit，但对中文财报段落的最终 token 估算接近“4 字符一个 token”的旧粗估变体。compact `before/after` 与 `not_reduced` gate 都使用该 estimator，可能把实际仍很长的中文 compacted RunInput 判定为有效变短。

**建议**：将换算分母恢复到 OLD 语义（或在 plan 中明确证明新的分母更保守且有测试依据）。测试应覆盖纯中文财报段落、纯 ASCII、混合文本，并对照 OLD `_estimate_tokens` 的关键样例。

**修复说明**：`TOKEN_UNITS_PER_ESTIMATED_TOKEN` 已恢复为 `2`；测试已覆盖纯中文、纯 ASCII、中英文混合财报文本的 OLD 关键口径样例，不再锁死宽松分母。

### Finding 3 — [已修复，待复查] Engine overflow classifier 的结构化错误优先级不完整，结构化非 overflow code 仍会落入 message fallback（中）

**文件**：`dayu/engine/runners/openai/error_classifier.py:111`、`dayu/engine/runners/openai/error_classifier.py:114`

**问题**：`detect_context_overflow` 先检查结构化 `context_length_exceeded`，未命中后无条件对整个 response text 做 message marker fallback。若 provider 返回结构化错误，例如 `{"error": {"code": "invalid_request_error", "message": "...context length exceeded..."}}`，当前仍会分类为 overflow。

**为什么不符合 NEW 计划**：计划要求“结构化错误优先；当 provider 同时给出结构化 code 与 message 时，以明确 code / typed field 为准”，并要求普通 client error 负例不误判。当前负例测试只覆盖了 message 不含 marker 的普通 client error，没有覆盖“结构化 code 明确非 overflow，但 message 含 fallback marker”的情况。

**建议**：当 payload 中存在明确结构化 code 且不为 `context_length_exceeded` 时，应拒绝 fallback，或只在 code 缺失 / 空值 / provider 无结构字段时启用受控 fallback。补结构化非 overflow code + marker message 的负例测试。

**修复说明**：Engine classifier 现在先读取明确非空结构化 code；只要 code 存在且不是 `context_length_exceeded`，就不会进入 message fallback。已补 `invalid_request_error` + `context length exceeded` message 的负例测试。

### Finding 4 — [已修复，待复查] final answer 防回显只靠 prompt 提示，未形成 P4 语义 gate（中）

**文件**：`dayu/host/_run_input_builder.py:627`、`dayu/host/_context_compaction.py:321`、`dayu/host/_event_translation.py:381`

**问题**：Host Memory / Host Compact Memory 开头确实加入了 `INTERNAL_ONLY` 与禁止原样输出说明，但 `FINAL_ANSWER` 终态投影仍直接把 `FinalAnswerData.content` 写入 `RunSucceededResult`，没有任何测试或校验暴露模型 echo `Host Memory`、`Tool Facts`、`Evidence Anchors`、`tool_fact_id`、`source_event_cursor` 等内部标题/字段的风险。

**为什么重要**：NEW plan 明确把 internal memory non-echo 列为 gate，并要求 fake model 若回显内部标题时 final answer 路径能暴露风险。当前实现属于“提示层建议”，不是可验证的语义保护。对于财报分析，source cursor、cursor fingerprint、tool fact id 等内部治理元数据一旦被模型当成正文结构输出，会让用户看到看似权威但不应暴露的内部事实表，也会混淆“可见引用”和“Host 内部 provenance”。

**建议**：至少补 P4 语义测试，构造 fake Engine 返回包含内部标题/字段的 final answer，确认当前风险被测试捕获；若 P4 不实现输出校验，也应在 review gate / README 中把该风险标为未覆盖，而不是仅靠 prompt 文案视为已解决。

**修复说明**：Host 在 `FINAL_ANSWER` 翻译边界增加最小 P4 输出 gate，命中 `Host Memory`、`Tool Facts`、`tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、`scope_token`、raw EventLog metadata 或工具结果 repr 标记时，返回安全占位内容并标记 `filtered=True`、`degraded=True`。已补 fake Engine 回显内部字段的 Host 测试。

## 其它核对结论

- Engine 当前没有迁回 OLD `_compact_messages`，也未在 Engine 内实现 compact / retry / memory / RunInput 重建；这个边界符合 NEW 计划。
- Host compact retry 没有再次 append `USER_INPUT_ACCEPTED`，memory projection 仍以原始用户输入事件为真源；该点符合计划。
- compacted RunInput 的 system 顺序在现有能力内是 caller system messages 在前、Host compact memory 在后、当前 user 最后；但 public `start_run` 当前只接受单条 `UserMessage`，尚未真正支持 caller / Agent / app system prompt 的入口语义。

## 复审结论

复审通过，无 findings。

- OLD provider overflow 信号矩阵已覆盖结构化 `context_length_exceeded`、`maximum context length is`、`context length exceeded`、`total message token length exceed model limit`、`model's maximum context length`、`range of input length should be`、`model requires more context`；结构化非 overflow code 会阻断 message marker fallback，`invalid_request_error` + marker message 不误判。
- Engine / Runner 只把 provider overflow 归一为 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`、`context_compaction_requested` 与 recoverable `run_failed("context_compaction_required")` 事实；compact policy、memory、retry 与 RunInput 重建仍在 Host。
- Host token estimator 已继承 OLD 半角 1 unit、全角 / 宽字符 2 units、2 units/token 的口径；`DefaultRunInputBuilder` trace 与 `ContextCompactCoordinator` before / after 均复用同一 `_token_estimator`。
- Host compact 前会从同一 Run EventLog 读取已 append 的 canonical tool facts / evidence anchors，并通过与 memory projection 同源的 `snapshot_with_transient_tool_facts()` 合并进 compact 输入；测试覆盖 `tool_call_id`、`source_event_cursor`、`cursor_fingerprint`、`has_more` 保留。
- final answer 翻译边界已有最小内部字段回显 gate，命中 `Host Memory`、`Tool Facts`、`tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、`scope_token`、raw EventLog metadata 或工具结果 repr 标记时返回 filtered/degraded 安全内容；已有 fake Engine 回显测试。
- 财报证据保真仍成立：compact 成功需严格变短并保留当前用户问题、pinned state、evidence anchors、source cursor 与 tool facts；无法变短或保真失败不 retry。

验证：

- `source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider tests/engine/runners/openai/test_context_overflow_classifier.py tests/engine/test_agent_phase2.py::test_context_overflow_http_error_maps_to_compaction_required_fact tests/host/test_phase4_token_estimator.py tests/host/test_phase4_context_compaction.py tests/host/test_phase4_overflow_retry.py -q`：29 passed。
- `source .venv/bin/activate && pyright`：0 errors, 0 warnings, 0 informations。
