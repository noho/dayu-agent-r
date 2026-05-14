# A4 Engine Parser / Provider Robustness 修复记录

## 范围

- 来源：`docs/reviews/repo-review-controller-adjudication-20260514.md` 的 A4。
- 分支：`fix/host-phase-4`。
- 本轮只处理 controller accepted A4 项；未进入 A5/A6/A8/A9，未修改 config json findings。

## 动机核对

- `run_agent_and_wait` 已导入 `TERMINAL_ENGINE_EVENT_TYPES`，但终态判断仍手写四个事件类型，存在后续终态集合漂移风险；修复成立。
- `payload.py` / `reasoning_protocol.py` 消费封闭联合时缺少 `assert_never` 守护，新增 provider 扩展或消息成员时静态检查不够硬；修复成立。
- `detect_context_overflow` 对 `http_status >= 500` 直接返回 `False`，导致 5xx 错误体里的明确 context overflow marker 被漏判；修复成立。runner 侧已经在 HTTP 错误路径统一调用该函数，本轮只调整分类器边界。
- `ClientPayloadError` 文档写成超时类，但实现经 `aiohttp.ClientError` 分支归为 `NETWORK_ERROR`；这是文档与实现不一致，修复成立。
- `payload.py` 的 `_serialize_arguments` 内部 lazy import `json`，没有必要；修复成立。
- `_exception_diagnostic_message` 截断异常消息时没有显式截断标记，诊断可读性不足；修复成立。
- SSE 非 dict choice 当前静默跳过，适合补低风险诊断日志；non-stream `fatal_emitted` 是死变量，适合删除。
- malformed usage 降级、`GeminiToolCallState` / provider state contract、runner factory / provider injection 均属于非目标，本轮未改。

## 变更摘要

- `dayu/engine/agent.py`
  - `run_agent_and_wait` 复用 `TERMINAL_ENGINE_EVENT_TYPES`。
  - 异常诊断消息截断时在 `_EXCEPTION_MESSAGE_MAX_LENGTH` 内追加 `"... [truncated]"`。
- `dayu/engine/runners/openai/payload.py`
  - `json` 移到模块顶部。
  - 对 message、provider state、provider request extension、reasoning effort / thinking level 枚举 match 补 `assert_never`。
- `dayu/engine/runners/openai/reasoning_protocol.py`
  - 对 provider request extension match 补 `assert_never`。
- `dayu/engine/runners/openai/error_classifier.py`
  - context overflow marker 检测覆盖 4xx 与 5xx。
  - 修正 `ClientPayloadError` 文档归类说明。
- `dayu/engine/runners/openai/sse_parser.py`
  - SSE `choices` 内非 dict 成员记录 `sse_choice_not_object` 诊断日志，协议行为保持跳过。
  - 补齐触及 helper 的中文参数、返回值、异常 docstring。
- `dayu/engine/runners/openai/non_stream_parser.py`
  - 删除 `fatal_emitted` 死变量。
  - 补齐触及 helper / dataclass 的中文参数、返回值、异常 docstring。

Controller self-review 补充：

- 首版实现为异常摘要直接追加 truncation marker；controller 自审后改为先为 marker 预留长度，保持摘要 body 不超过 `_EXCEPTION_MESSAGE_MAX_LENGTH`，并补充测试断言。

## 测试与验证

- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_context_overflow_classifier.py tests/engine/runners/openai/test_http_error_classification.py tests/engine/runners/openai/test_protocol_error.py tests/engine/test_agent_phase2.py`
  - 64 passed。
- `source .venv/bin/activate && pytest tests/engine/runners/openai`
  - 187 passed。
- `source .venv/bin/activate && python -m pyright dayu/engine tests/engine`
  - 0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 通过。

## README 同步

本轮变更不改变 Engine 公共接口、用户命令、配置入口、分层关系或 README 中描述的执行路径；只增强内部健壮性、静态穷尽检查与诊断日志。因此按 README 触发规则检查后未更新 README。

## 残余风险

- 5xx context overflow 识别仍依赖已读取的错误体文本；本轮未修改 runner 的错误体读取策略，因为 `runner.py` 不在允许生产文件范围内。
- SSE 非 dict choice 仍保持旧行为：记录诊断并跳过，不升级为协议错误。
