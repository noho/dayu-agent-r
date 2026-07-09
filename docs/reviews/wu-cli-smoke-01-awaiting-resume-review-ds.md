# Code Review

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `HEAD` (uncommitted diff)
- Output file: `docs/reviews/wu-cli-smoke-01-awaiting-resume-review-ds.md`
- Included scope: `dayu/host/run_input.py`、`dayu/host/waiting.py`、`dayu/host/tool_runtime.py`、`dayu/host/_event_payload.py`、`dayu/host/engine_ingest.py`、`dayu/host/wait_adapter.py`、`dayu/host/README.md`、`tests/README.md`、`tests/host/test_run_input_builder.py`、`tests/host/test_resolve_wait_command.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_wait_adapter_polling.py`、`tests/host/test_wait_awaiting_accept.py`
- Excluded scope: `dayu/host/durable/`（未修改）、`dayu/engine/`（未修改）、`dayu/cli/`（未修改）
- Parallel review coverage: 无（单一 reviewer 逐条走读全部 diff 文件）
- Background artifact: `docs/reviews/wu-cli-smoke-01-awaiting-resume-fix-codex.md`
- Design sources: `docs/host/design.md`、`docs/engine/design.md`
- Control document: `docs/host/issues-implementation-control.md`

## Findings

### F01-中-`_resume_wait_fallback_message` 把内部 result wrapper 结构原样暴露给 LLM

- **入口/函数**: `_resume_wait_fallback_message`
- **文件(行号)**: `dayu/host/run_input.py:4129-4134`
- **输入场景**: resume 时 `TOOL_AWAITING` 事件缺少 `accepted_arguments`（旧事件），进入 fallback 路径
- **实际分支**: `accepted_arguments = _resume_wait_accepted_arguments(...)` 返回 `None`，走 `return (_resume_wait_fallback_message(payload),)`
- **预期行为**: LLM-facing 文本应只包含业务可读的工具结果，不暴露内部 result envelope 结构（`kind`、`result`、`ok`）
- **实际行为**:

  ```python
  result_text = json.dumps(
      payload.get("result"),  # 整个 result envelope，包含内部结构
      sort_keys=True, separators=(",", ":"), ensure_ascii=False,
  )
  ```

  产出类似 `{"kind":"completed","result":{"ok":true,"value":{"answer":42}}}` 的文本直接进入 LLM 上下文。`kind`、`ok` 是 Host 内部治理字段，不属于业务事实或财报数据。

- **直接证据**: `test_resume_wait_legacy_message_appends_shared_duplicate_result_guidance` 断言包含 `'工具结果：{"kind":"completed","result":{"ok":true,"value":{"answer":42}}}'`（`test_run_input_builder.py` 第 813 行）——内部字段 `kind`、`result`、`ok` 确认为已投影进 LLM 消息
- **影响**: 违反 AGENTS.md LLM-facing 约束"不得把系统状态、调度状态、Host / Engine 内部治理信息伪装成财报事实、业务事实或用户可见结论"。模型可能被内部结构误导（如把 `kind` 当作业务字段），增加推理噪音
- **建议改法和验证点**: fallback 路径应复用同一文件中 `_resume_wait_tool_message_content` 的 result 投影逻辑，提取 `result["result"]` 子结构而非 dump 整个 result envelope；或显式在 fallback 中剥离 `kind`/`ok` 等 wrapper 字段后只投影业务正文。验证点：更新 legacy 测试断言不再包含 `"kind"` / `"ok"` 字面量
- **修复风险（低）**: 只影响旧事件 fallback 路径，不修改新路径、EventLog schema 或状态机；旧 `TOOL_RESULT_ACCEPTED` payload 已有稳定的 `result["result"]` 子结构
- **严重程度（中）**: 限制了旧事件 resume 时的 LLM-facing 质量，是已知残量风险（Codex artifact 已记录），但违反 AGENTS.md 显式约束

### F02-中-`_continuity_starts_with_current_user` 对 continuity 结构有隐式假设

- **入口/函数**: `_continuity_starts_with_current_user` → `_current_user_tail_messages`
- **文件(行号)**: `dayu/host/run_input.py:4006-4020`、`dayu/host/run_input.py:3982-4003`
- **输入场景**: resume dispatch 时，`DurableSessionContinuityProvider.build_continuity_view` 返回以 `UserMessage(current_facts.user_prompt)` 为首的三条 resume 消息
- **实际分支**: `continuity.messages[0]` 是 `UserMessage` 且 `content == current_facts.user_prompt`，返回 `True`，跳过追加当前用户消息
- **预期行为**: 当 continuity 已包含当前用户请求时，不应重复追加到消息列表末尾
- **实际行为**: 当前正确——`DurableSessionContinuityProvider.build_continuity_view`（第 1023-1029 行）**只**返回 resume 消息元组，不与 memory/snapshot 历史拼接
- **直接证据**: `DurableSessionContinuityProvider.build_continuity_view` 第 1023 行 `del snapshot` 之后第 1024-1029 行直接返回 `resume_messages`，不调用 `super().build_continuity_view()`，也不合并 session history——因此 `continuity.messages[0]` 永远是当前用户消息
- **影响**: 当前无行为错误。但函数签名 `continuity: SessionContinuityView` 未约束"首条必为当前 user"这一隐含契约；若后续 SessionContinuityProvider 合并 memory 前缀（如 base class 或新的 composite provider），`[0]` 检查将静默失效，导致当前用户消息被重复追加，出现两条相同 user content
- **建议改法和验证点**: 两种选一：(a) 在当前函数 docstring 中显式记录假设"caller 保证 continuity 不含 memory/snapshot 前缀"；(b) 把 `[0]` 检查改为遍历 `continuity.messages` 查找是否存在 `isinstance(msg, UserMessage) and msg.content == current_facts.user_prompt`。若当前设计刻意保持 `[0]` 性能（避免 O(n) 扫描），选 (a) 并建议在 `build_continuity_view` 返回值处加 assert 约束
- **修复风险（低）**: 不改变行为，只加固契约表达或改用 O(n) 扫描（n 极小，3 条消息）
- **严重程度（中）**: 当前行为正确，但隐式契约脆弱，未来 provider 组合变更可能引入静默重复用户消息的回归

### F03-低-`_RESUME_GUIDANCE_PREFIX` 英文前缀混入 LLM-facing 系统消息

- **入口/函数**: `_resume_wait_fallback_message`
- **文件(行号)**: `dayu/host/run_input.py:227`（常量定义）、`dayu/host/run_input.py:4137`（使用位置）
- **输入场景**: resume fallback 路径
- **实际分支**: 始终拼接 `"Resume guidance:" + 中文 body`
- **预期行为**: 前缀是内部 envelope section 分类标签（`run_input.py:2831-2836` 用于 system message 分段），不应以英文内部术语形态进入 LLM 可见文本
- **实际行为**: 旧路径和新 fallback 路径都在系统消息开头拼接 `"Resume guidance:"`；新主路径（user/assistant/tool 协议消息）不使用此前缀
- **直接证据**: `_RESUME_GUIDANCE_PREFIX = "Resume guidance:"`（第 227 行），fallback 消息以 `_RESUME_GUIDANCE_PREFIX` 开头（第 4137 行），最终文本如 `"Resume guidance:\n上一轮被等待中断的..."` 出现在 LLM 视野
- **影响**: 轻微增加 LLM 认知噪音；内部治理标签没有业务含义
- **建议改法和验证点**: fallback 路径移除前缀，改为直接用中文开头，或改用中文分类标签（如 `[恢复上下文]`）。同时 `run_input.py:2831-2836` 的分段逻辑依赖此前缀匹配，修改时需同步更新分段键
- **修复风险（低）**: 只影响 fallback system 消息文本和 system section 分类逻辑；新主路径不依赖此前缀
- **严重程度（低）**: 无正确性影响，纯 LLM-facing 文本质量

### F04-中-`_resume_wait_completed_tool_content` 对非 dict value 直接包 `{"content": value}` 可能丢失语义

- **入口/函数**: `_resume_wait_completed_tool_content`
- **文件(行号)**: `dayu/host/run_input.py:4214-4226`
- **输入场景**: resume 时 wait resolution 为 `completed`，且 `result["result"]["value"]` 不是 dict
- **实际分支**: `isinstance(value, Mapping)` 为 `False`，返回 `{"content": value}`
- **预期行为**: 投影应与普通 Engine tool result 注入格式一致（docstring 申明"与 Engine 普通工具注入一致的扁平 JSON 字符串"）
- **实际行为**: 对 dict value 直接透传 `dict(value)`；对非 dict value 包裹为 `{"content": value}`。如果 Engine 正常 tool result 对字符串/数值等非 dict 结果使用不同的投影格式（例如直接字符串），此处格式不一致可能导致模型理解偏差
- **直接证据**: `_resume_wait_completed_tool_content` 第 4223-4226 行；需要对比 Engine 正常 tool result 注入格式（`dayu/engine/` 下的 tool message content 构造路径）确认是否对齐
- **影响**: 若 Engine 正常 tool result 直接使用裸值（字符串/数值）而不包 `{"content": ...}` 包装，则 resume 路径与正常路径的工具结果投影不一致，可能对模型产生不同的信号
- **建议改法和验证点**: 交叉比对 Engine 侧 `ToolMessage.content` 对 completed result 的投影格式；如有差异，对齐到同一格式。若无 Engine 统一约定（原 Engine 侧也包 `{"content": ...}`），则为无问题并关闭此 finding
- **修复风险（低）**: 只涉及投影格式对齐，不修改 schema/状态机
- **严重程度（中）**: 若格式不一致则为真实不一致性缺陷；若一致则为误报——需要交叉验证

## Open Questions

- **OQ1**: `_resume_wait_completed_tool_content` 的 `{"content": value}` 投影是否与 Engine 正常 tool result message content 一致？建议 reviewer 或后续 agent 交叉阅读 `dayu/engine/` 下 tool result 注入路径确认。若一致则 F04 可关闭。
- **OQ2**: `DurableSessionContinuityProvider.build_continuity_view` 刻意不合并 memory 前缀的设计决策是否应在 docstring/设计真源中显式记录？（当前方法 docstring 第 1017-1020 行只说"从当前 resume RUN_STARTED 重建 wait result fact message"，未说明不合并 memory 历史）

## Residual Risk

- **旧事件不可恢复**: 已存在的 `TOOL_AWAITING` event 没有 `accepted_arguments`，只能走 fallback guidance——这是旧事实缺字段导致的不可恢复边界。已在 Codex artifact 中记录。
- **resume 新消息形态未经真实 provider E2E 验证**: assistant tool-call + tool result 的 resume 消息形态在本轮仅通过 Host 层单元测试验证，未覆盖真实 provider（mimo/deepseek/qwen 等）对该消息形态的响应差异。若某 provider 强依赖 `provider_state` 字段（当前填充为 `None`，`run_input.py:4110`），可能行为异常。
- **`provider_state=None` 风险**: 重建的 `AssistantToolCall` 中 `provider_state=None`（`run_input.py:4110`）。若某 provider 的 runner adapter 期望从 provider_state 恢复内部 token/state，`None` 可能导致错误。当前已知 OpenAI-compatible 协议可工作；CODE 文档未对此显式覆盖。
- **测试覆盖**: 当前测试不覆盖 `accepted_arguments` 中存在非 dict value 时的 completed result 投影（`_resume_wait_completed_tool_content` 的 `else` 分支 `{"content": value}` 在第 4226 行，无专属测试 case）；也不覆盖 `_resume_wait_failed_tool_content` 和 `_resume_wait_cancelled_tool_content` 的 boundary（hint 可选字段分支、必填字段缺失时 `HostDurableError` 分支）。
- **未覆盖的并发/竞态**: 当前测试不覆盖 resume 路径与 concurrent Engine event 的竞态——`stop_worker_stream=True` 在 ACCEPTED 路径终止 stream，但如果 Engine 在 TOOL_AWAITING event 之后还产生一个 terminal event（例如 provider 侧超时后 Engine 侧 RUN_FAILED），该 terminal event 会被 stream close 吞掉，不作为 canonical fact 写入。需确认 Engine 协议是否保证 TOOL_AWAITING 之后不再产生 terminal event。

## Conclusion

**Pass with findings**（3 个中优先级、1 个低优先级 finding，无不阻塞 merge 的严重缺陷）

- F01（中）：Fallback 路径暴露内部 result wrapper 给 LLM——已知残量风险，但在 AGENTS.md 约束下应修复
- F02（中）：`_continuity_starts_with_current_user` 隐式依赖 continuity 结构——当前行为正确，契约未显式化
- F03（低）：英文 "Resume guidance:" 前缀进入 LLM-facing 文本——微小可修
- F04（中）：`_resume_wait_completed_tool_content` 对非 dict value 投影格式需与 Engine 侧对齐验证

核心正确性判断：root cause 证据链直接、充分（diff 中 `run_input.py` 的重建逻辑 + `engine_ingest.py` 的 `stop_worker_stream` + `wait_adapter.py` 的日志补充），修复方向正确。`accepted_arguments` / `normalized_arguments_digest` 的 digest 校验在写入（`ToolAwaitingAcceptCandidate.__post_init__`）和读取（`_resume_wait_accepted_arguments`）两侧均有覆盖，round-trip 一致性经过 JSON canonical encoding 保证。新消息 `user -> assistant tool_call -> tool` 符合模型工具协议，比旧的单条 system guidance 显著改善 resume 输入质量。`stop_worker_stream` 在 dispatch 消费侧（`dispatch.py:3904`）正确区分 `terminal_closeout`（Run 终态）和 `stop_worker_stream`（仅停止 stream），避免误写 `clean_eof_without_terminal` CRITICAL 日志。wait adapter 日志只记录 wait_id/adapter_key/outcome 类别/计数，不包含工具结果 payload（`test_wait_adapter_polling.py:948-949` 验证了 `payload_secret` 和 `do-not-log` 不出现在日志中）。

pyright/docstring/README 触发均已满足：pyright `0 errors`、所有新增函数含完整中文 docstring、`dayu/host/README.md` 和 `tests/README.md` 按触发规则同步了 resume 输入重建和测试覆盖说明。
