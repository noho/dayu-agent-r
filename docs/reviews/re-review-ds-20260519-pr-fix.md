# Code Review

## Scope

- Mode: current changes (re-review of uncommitted workspace changes)
- Branch: feat/host-p10-5-public-contract-freeze
- Base: main
- Output file: docs/reviews/re-review-ds-20260519-pr-fix.md
- Included scope: `dayu/host/llm_compaction.py`, `dayu/host/wait_adapter.py`, `dayu/host/admission.py`, `dayu/engine/agent.py`, `utils/smoke_host_public_multiturn.py`, related `tests/host/`, `tests/engine/`, README, `docs/reviews/controller-fix-20260519-pr-review-smoke.md`
- Excluded scope: console scripts (user-ruled), non-scope modules, archived review artifacts
- Parallel review coverage: 无，主 reviewer 逐文件走读全部路径

## Findings

### 1-PASS-未发现阻塞性问题

对用户指定的六个审查维度逐一走读后，未发现会导致错误 answer、错误状态、静默失效或不可恢复的 blocking defect。

**finish_reason=length 处理**：普通回答路径中 `_handle_length_final_decision`（agent.py:978-1040）正确追踪 `continuation_attempts` 与 `has_iteration_budget`，穷尽时合并累积内容为单个 `_FinalDecision(degraded=True)`。compactor 路径（llm_compaction.py:172-175）显式拒绝 `finish_reason=length` 的 final answer 为 `LLMCompactionProposalError`，compact operation 可进入 retry。两路径均不会导致"空 final answer 被当作成功"或"截断摘要被当作 compact 成功"。

**compactor retry/timeout/脏数据拒绝**：`_run_agent_request` 用 `asyncio.wait_for(timeout=...)` 约束超时（llm_compaction.py:228），超时取消内部 Engine task 后由 `TimeoutError` 透传。`_safe_error_code` 正则 `^[a-z][a-z0-9_-]{0,63}$` 过滤非法错误码为 `unknown_error`（llm_compaction.py:253-263），验证断言（test_llm_compaction.py:212-213）确认 `api_key=error-secret` 被中化为 `unknown_error`。这些异常均由 `compact()` 方法以 `LLMCompactionProposalError` 或透传异常形式返回给上层 compaction operation，compactor 本身不写 EventLog/HostEvent，不存在语义破坏风险。

**WaitPoller 有界记忆**：`poll_once()`（wait_adapter.py:328-410）每轮重构 `retained_abandoned_cancelled_wait_ids`，仅保留当前 DB 中仍为 CANCELLED 且 abandon 成功的 wait_id（行 344-349 + 行 360-364）。DB 中已消失的 CANCELLED wait 其 ID 自然脱落；abandon 失败的 ID 不进入 retained 集，下轮重试。新测试 `test_failed_cancelled_wait_abandon_is_retried_next_poll`（test_wait_adapter_polling.py:347-377）验证了 abandon 失败不写记忆、下轮重试的行为。无界增长风险已消除，不会漏掉应重试的 cancelled wait。

**Engine run guard 无锁安全**：`_acquire_run_slot`（agent.py:1065-1078）的 check-then-set 在 asyncio 单线程协作式调度下天然原子——`if self._active_run_id is not None` 与 `self._active_run_id = ...` 之间无 `await`，不存在并发竞争窗口。移除 `threading.Lock` 正确。

**close CancelledError 释放 slot**：`run_messages()` 的 `finally` 块（agent.py:930-934）使用嵌套 `try/finally`，内层 `_close_runner_once()` 的 `CancelledError` 被外层的 `finally` 捕获后，`_release_run_slot()` 必定执行。`_close_runner_once`（agent.py:2380-2405）仅在 `else` 分支设置 `_closed = True`（close 成功），CancelledError 时 `_closed` 保持 `False` 并记录 warning 后重抛。测试 `test_close_cancelled_error_releases_run_slot`（test_agent_phase2.py:985-1004）验证 run slot 在 CancelledError 后确实释放。

**force-answer inline guard**：`_run_force_answer`（agent.py:1975-1999）调用 `_run_runner_iteration`（agent.py:1090-1098），后者在进入 Runner 前执行 `_message_inline_size_failure(messages)`（行 1108-1113）。所有 force-answer 入口——max_iterations 耗尽（行 923-929）与 consecutive_failed_tool_batches（行 914-920）——都经过 `_fallback_after_tools` → `_run_force_answer` → `_run_runner_iteration`。测试 `test_oversized_tool_message_fails_before_force_answer_runner_call`（test_agent_phase3_tool_call.py:987-1013）验证 oversized 工具结果在 force-answer runner 调用前被拦截为 `context_compaction_required`。

**测试覆盖**：新增/修改的 8 个测试均覆盖关键失败路径，非仅 happy path：
- `test_close_cancelled_error_releases_run_slot`：close 被取消仍释放 slot
- `test_oversized_tool_message_fails_before_force_answer_runner_call`：force-answer 前 inline guard
- `test_cancel_before_tool_batch_does_not_register_tool_call_id`：工具批注册前取消
- `test_llm_context_compactor_rejects_truncated_final_output`：length 拒绝
- `test_llm_context_compactor_applies_runner_timeout`：超时
- `test_llm_context_compactor_sanitizes_failed_runner_outcome`（增强）：脱敏覆盖率提升
- `test_failed_cancelled_wait_abandon_is_retried_next_poll`：abandon 失败重试
- `test_cancel_predispatch_starting_promotion_survives_queue_wakeup_failure`（增强）：warning log 断言

**README/doc artifact**：`dayu/engine/README.md` 和 `dayu/host/README.md` 的增量内容准确反映新增行为（force-answer inline guard、close CancelledError slot 释放、compactor length 拒绝/timeout/脱敏、WaitPoller 有界记忆），无旧语义残留或过时术语。

### 2-未修复-低-`_close_runner_once` `_closed` 标志在 CancelledError/Exception 时保持 False 可能导致 Runner 重复关闭尝试

- **入口/函数**: `_AsyncAgent._close_runner_once`
- **文件(行号)**: dayu/engine/agent.py:2380-2405
- **输入场景**: Runner close 抛出普通 `Exception` 后，`finally` 块再次调用 `_close_runner_once`
- **实际分支**: close 抛 `Exception` → 被 `except Exception` 捕获并记录 warning → `_closed` 保持 `False`（未进入 `else` 分支）
- **预期行为**: 旧代码在 close 前设 `_closed = True`，失败不重试；新代码在 close 成功后才设 `_closed = True`
- **实际行为**: close 失败时，当前 `run_messages()` 的 `finally` 中先由"with_close"方法调用一次，再由 `finally` 调用第二次——第二次调用因 `_closed = False` 会重试 close，产生重复 warning 日志
- **直接证据**: agent.py:2404 的 `else: self._closed = True` 仅在 close 成功时执行；agent.py:2398-2403 的 `except Exception` 不会设置 `_closed`
- **影响**: 重复 warning 日志（每次 run 最多两次 close 调用），不造成功能错误。Runner close 通常幂等，重复调用一般无害，且 close 在同一实例生命周期内最多被调用两次
- **建议改法和验证点**: 可在 `except Exception` 分支也设置 `self._closed = True`，对齐旧语义"尝试过即不再重试"；或在 `finally` 中无条件设置。但当前双调用路径（with_close 方法 + finally）下重复 warning 不构成功能缺陷，仅诊断噪音。不修也可接受
- **修复风险（低）**: 改动仅影响 close 失败后的重试行为，不影响任何终态
- **严重程度（低）**: 不影响正确性，仅诊断噪音

### 3-未修复-低-`_safe_error_code` 正则拒绝含点的合法错误码

- **入口/函数**: `_safe_error_code`
- **文件(行号)**: dayu/host/llm_compaction.py:61, 253-263
- **输入场景**: Engine 返回含点的错误码（如 `provider.protocol_error`）
- **实际分支**: `_SAFE_ERROR_CODE_PATTERN.fullmatch(...)` 返回 `None`（`.` 不在 `[a-z0-9_-]` 字符集中）→ 返回 `"unknown_error"`
- **预期行为**: 合法机器码应原样返回供诊断；`provider.protocol_error` 是典型的引擎协议错误码，不代表敏感信息
- **实际行为**: 含点错误码被中化为 `unknown_error`，丢失诊断精度
- **直接证据**: llm_compaction.py:61 正则 `^[a-z][a-z0-9_-]{0,63}$` 不含 `.`；llm_compaction.py:261-262 不匹配时返回 `"unknown_error"`
- **影响**: compactor 失败日志中错误码信息丢失。不影响功能正确性——full error 已在内部日志中保留，仅异常消息被截断
- **建议改法和验证点**: 将正则改为 `^[a-z][a-z0-9_.-]{0,63}$`（加入 `.`），或在 `_safe_error_code` 注释中明确点号是有意拒绝的安全决策
- **修复风险（低）**: 允许点号不引入注入风险——点号在日志/异常消息中无特殊语义
- **严重程度（低）**: 仅诊断精度下降，不影响系统行为

## Open Questions

1. compactor `asyncio.wait_for` 取消内部 Engine task 时，Engine 的 `_close_runner_once` 可能因 task 级取消而在 `_runner.close()` 中途被打断。打断后 `_runner` 内部连接状态不清。此场景在 compactor 一次 proposal 生命周期内无实际影响（每次 proposal 创建新 Agent/Runner），但若将来 Engine 复用 Runner 实例需注意。
2. `_budget_after_compact` 从 `estimated_input_tokens // 2` 改为 `(len(summary) + 3) // 4` 是基于英文文本的 token 估算。对于中文摘要（中文字符/英文 token 比约为 1:2-3），该估算可能偏低约 2-3 倍。当前 compactor prompt 为英文，不触发此问题；若将来 prompt 切换为中文需重新评估。

## Residual Risk

- 无 compactor timeout 与 Engine CancelledError 交互的集成测试——当前 timeout 测试 monkeypatch 绕过了真实 Engine 路径，未覆盖 Engine task cancellation 后的 runner close + slot release 组合路径。风险中等偏低：compactor 每次创建新 Engine request/Runner 实例，状态隔离良好，且已有 Engine 层级的 close CancelledError 单元测试覆盖 slot release。
- 无 `finish_reason=length` + 空 content 在多轮 continuation 穷尽后产出空 final answer 的测试——此边缘场景在变更前已存在（非新引入），且需要模型同时返回 length + 几乎无内容的极端情况。当前 continuation 路径在 content 为空时跳过 assistant 消息注入（agent.py:1025-1033），空 content 不会导致注入异常。
- smoke 脚本 `_COMPACTOR_MAX_TOKENS=1024` 与 `_ORDINARY_MAX_TOKENS=2048` 分离正确，但 smoke 是手工脚本，不进入 CI 自动化。真实 compactor max_tokens 的正确性依赖 `CompactorRunnerBaseline.compactor_runner_options` 的 Host 配置，非代码层面可强制。

## 结论

**PASS** — 未发现阻塞性问题。所有六个审查维度的变更均正确，关键失败路径有测试覆盖。两条低严重度 finding 供参考，不要求必须修复。
