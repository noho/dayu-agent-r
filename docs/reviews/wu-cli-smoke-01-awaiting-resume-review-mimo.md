# Code Review

## Scope

- Mode: current changes
- Branch: phase/host-issues-control
- Base: main
- Output file: docs/reviews/wu-cli-smoke-01-awaiting-resume-review-mimo.md
- Included scope: dayu/host/run_input.py, waiting.py, tool_runtime.py, _event_payload.py, engine_ingest.py, wait_adapter.py, Host/tests README, tests/host/*
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

### F01-未修复-中-accepted_arguments 明文持久化可能泄露敏感参数

- **入口/函数**: `_event_payload.py:tool_awaiting_payload()` 和 `waiting.py:ToolAwaitingAcceptCandidate`
- **文件(行号)**: `dayu/host/_event_payload.py:74`, `dayu/host/waiting.py:221`
- **输入场景**: 工具调用参数包含 API key、token、密码等敏感信息
- **实际分支**: `accepted_arguments` 直接 `dict(accepted_arguments)` 写入 EventLog payload
- **预期行为**: 敏感参数应该被脱敏或加密存储，或至少在设计文档中明确安全边界
- **实际行为**: 明文存储在 EventLog 中，可被任何有 DB 访问权限的人读取
- **直接证据**:
  - `_event_payload.py:74`: `"accepted_arguments": dict(accepted_arguments)`
  - `waiting.py:267`: `sha256_digest_json({"arguments": dict(self.accepted_arguments)})`
  - 测试 `test_wait_adapter_polling.py:467` 确认 `payload_secret` 不进入日志，但 EventLog payload 仍然明文存储
- **影响**: 敏感参数泄露风险；如果工具参数包含 API key、数据库密码等，这些信息会永久保存在 EventLog 中
- **建议改法和验证点**:
  - 评估工具参数是否真的需要持久化完整内容
  - 如果只用于 resume 重建，可以考虑只存储必要字段或使用单向 hash
  - 如果必须存储完整参数，应在设计文档中明确安全边界和访问控制要求
  - 验证点：检查现有工具（如 Fins download）的参数是否包含敏感信息
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### F02-未修复-低-resume 时 wait_created_event_ref 缺失会导致 HostDurableError

- **入口/函数**: `run_input.py:_resume_wait_accepted_arguments()`
- **文件(行号)**: `dayu/host/run_input.py:4162-4168`
- **输入场景**: 旧 `TOOL_RESULT_ACCEPTED` event 没有 `wait_created_event_ref` 字段（旧库兼容场景）
- **实际分支**: `_event_id_from_payload_ref()` 会抛出 `HostDurableError`
- **预期行为**: 应该 fallback 到 legacy guidance，而不是抛异常导致 resume 失败
- **实际行为**: `HostDurableError("resume wait created event not found")` 会导致整个 resume Attempt 失败
- **直接证据**:
  - `run_input.py:4162-4168`:
    ```python
    wait_event_id = _event_id_from_payload_ref(
        tool_result_payload,
        field_name=_PAYLOAD_FIELD_WAIT_CREATED_EVENT_REF,
    )
    wait_event = read_event_by_id(transaction, wait_event_id)
    if wait_event is None:
        raise HostDurableError("resume wait created event not found")
    ```
  - 上层 `_resume_wait_messages_from_current_start()` 没有捕获此异常
- **影响**: 旧库中已存在的 resume Attempt 会失败，无法降级到 legacy guidance
- **建议改法和验证点**:
  - 方案 A：在 `_resume_wait_accepted_arguments()` 中捕获 `HostDurableError`，返回 `None` 让上层 fallback
  - 方案 B：在 `_resume_wait_messages_from_current_start()` 中捕获 `_resume_wait_accepted_arguments()` 的异常，fallback 到 legacy guidance
  - 验证点：添加测试覆盖 `wait_created_event_ref` 缺失时的 fallback 行为
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F03-未修复-低-resume 时 TOOL_AWAITING event 缺失会导致 HostDurableError

- **入口/函数**: `run_input.py:_resume_wait_accepted_arguments()`
- **文件(行号)**: `dayu/host/run_input.py:4169`
- **输入场景**: `wait_created_event_ref` 指向的 event 不存在或类型不匹配
- **实际分支**: `_require_event()` 会抛出 `HostDurableError`
- **预期行为**: 应该 fallback 到 legacy guidance
- **实际行为**: `HostDurableError` 会导致整个 resume Attempt 失败
- **直接证据**:
  - `run_input.py:4169`: `_require_event(wait_event, expected_type=_EVENT_TYPE_TOOL_AWAITING)`
  - 上层没有捕获此异常
- **影响**: EventLog 不一致时 resume 会失败，无法降级到 legacy guidance
- **建议改法和验证点**:
  - 与 F02 合并处理：在 `_resume_wait_messages_from_current_start()` 中捕获 `_resume_wait_accepted_arguments()` 的所有异常，fallback 到 legacy guidance
  - 验证点：添加测试覆盖 `TOOL_AWAITING` event 缺失或类型不匹配时的 fallback 行为
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F04-未修复-低-_continuity_starts_with_current_user() 使用字符串比较判断用户消息

- **入口/函数**: `run_input.py:_continuity_starts_with_current_user()`
- **文件(行号)**: `dayu/host/run_input.py:3976-3990`
- **输入场景**: 用户消息内容被格式化或添加时间戳
- **实际分支**: `first.content == current_facts.user_prompt` 字符串精确比较
- **预期行为**: 应该使用更 robust 的比较方式，或在 continuity 构建时标记
- **实际行为**: 如果消息内容被任何中间层修改（如添加时间戳、格式化），比较会失败，导致用户消息重复追加
- **直接证据**:
  - `run_input.py:3990`: `return isinstance(first, UserMessage) and first.content == current_facts.user_prompt`
- **影响**: 可能导致用户消息在 resume 时重复追加，模型看到两次相同的用户输入
- **建议改法和验证点**:
  - 方案 A：在 continuity 构建时标记是否已包含当前用户消息
  - 方案 B：使用 digest 比较而非字符串比较
  - 验证点：检查是否有中间层会修改用户消息内容
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- `accepted_arguments` 是否应该持久化完整内容？当前 Fins 工具的参数（如 ticker、download path）是否包含敏感信息？如果包含，是否有现有的安全机制（如 Host payload encryption）可以复用？
- resume 时如果 EventLog 异常（F02/F03），是否有现有的 diagnostic 机制可以记录降级原因，而不仅仅是 fallback？

## Residual Risk

- 旧库中已存在的 `TOOL_AWAITING` event 没有 `accepted_arguments`，只能走 fallback guidance，无法 retroactively 重建 assistant tool call；这是旧事实缺字段导致的不可恢复边界
- 本轮验证覆盖了 Host 行为、投影、日志和类型检查，但未覆盖真实 provider 对 assistant tool-call + tool result resume 消息的 E2E 响应差异
- 当前重建的 assistant tool call 不携带 provider-specific state；OpenAI-compatible 工具协议应可工作，若某 provider 强依赖私有 tool-call state，需要在 runner adapter 层增加明确契约
- 测试未覆盖 `accepted_arguments` 包含敏感参数时的行为
- 测试未覆盖 resume 时 EventLog 异常（F02/F03）的完整降级路径

## 总体评估

本次修改解决了 resume 后模型重复启动工具的 root cause，修复方向正确：

1. **Root cause 由直接证据支撑**：日志证明 poller 已 resolve，但 resume 输入只有 system/user 两条消息，没有 assistant tool-call + tool result 协议消息，导致模型不知道工具已完成
2. **修复真正解决 resume 后重复启动工具**：通过持久化 `accepted_arguments` 并重建 `user -> assistant tool_call -> tool result` 闭环，模型能看到工具已完成的完整上下文
3. **LLM-facing resume 消息符合 AGENTS.md**：fallback 消息使用中文、自解释、不暴露 Host 内部治理字段
4. **engine_ingest 停止 worker stream 语义正确**：confirmed waiting event 停止 stream 是正确行为，不会吞掉合法 terminal/failure（因为 waiting 状态已由 Host 接管）
5. **wait_adapter 新日志足够排障且不泄露 payload**：日志只记录 wait id、adapter key、outcome 类别，不记录工具结果正文
6. **测试覆盖关键边界**：覆盖了 resume 重建、legacy fallback、日志输出、digest 一致性

主要发现是 F01（敏感参数明文持久化）和 F02/F03（EventLog 异常时的降级策略），这些是 maintainability 和 robustness 问题，不阻塞当前修复的核心正确性。
