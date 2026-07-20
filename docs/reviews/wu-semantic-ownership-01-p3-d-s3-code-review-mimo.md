# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S3 Code Review

## Scope

- Mode: current workspace changes, only P3-D S3 related modifications and artifacts
- Work unit: WU-SEMANTIC-OWNERSHIP-01 / P3-D - Engine provider protocol normalization
- Slice: S3 - Typed Engine error codes and propagation audit
- Base: main
- Accepted prior commits: plan c52519f0, S1 d009ad11, S2 43510168
- Output file: docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-mimo.md

## Findings

### 001-未修复-低-测试中 typed wrapper 与裸字符串字面量直接比较

- **入口/函数**: `tests/engine/test_agent_phase2.py:1819`, `tests/engine/test_agent_phase2.py:726`, `tests/engine/test_agent_phase2.py:821`, `tests/engine/test_agent_phase2.py:870`, `tests/engine/test_agent_phase2.py:1001`, `tests/engine/test_agent_phase2.py:1014`, `tests/engine/test_agent_phase2.py:1465`, `tests/engine/test_agent_phase2.py:1593`, `tests/engine/test_agent_phase2.py:1819`
- **文件(行号)**: `tests/engine/test_agent_phase2.py:726`, `tests/engine/test_agent_phase2.py:1819`
- **输入场景**: 测试断言比较 `EngineRunOutcomeFailed.error_code` / `RunFailedData.error_code` 与裸字符串字面量
- **实际分支**: `assert terminal.data.error_code == "bad_sse"` (line 726), `assert result.error_code == "provider_http_error"` (line 1819)
- **预期行为**: 测试应验证 typed error code 的值正确，同时隐式验证类型正确
- **实际行为**: 比较通过 `RunnerSpecificErrorCode.__eq__`（继承自 `str`）成功，但测试不区分 `RunnerSpecificErrorCode("bad_sse", source=...)` 与裸字符串 `"bad_sse"`
- **直接证据**: `RunnerSpecificErrorCode` 继承 `str`，`str.__eq__` 使 wrapper 与裸字符串比较恒等；弱类型守卫 `test_engine_error_code_constructors_do_not_use_literal_strings` 只扫描构造点，不扫描断言中的字符串比较
- **影响**: 若 `error_code` 字段意外退化为裸 `str`，这些断言仍会通过，降低测试的回归检测能力
- **建议改法和验证点**: 断言中可增加 `isinstance(terminal.data.error_code, RunnerSpecificErrorCode)` 或比较 `.value`；或在弱类型守卫中增加对断言位置的扫描。此为测试质量改进，不影响生产正确性
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 验证结果

### 测试

```bash
source .venv/bin/activate && pytest tests/engine/contracts tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py tests/engine/test_weak_typing_guard.py -q
# 156 passed in 0.46s

source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py -q
# 85 passed in 1.12s
```

### pyright

```bash
source .venv/bin/activate && python -m pyright dayu/engine/contracts/error_codes.py dayu/engine/contracts/engine_events.py dayu/engine/contracts/runner_events.py dayu/engine/contracts/agent_run.py dayu/engine/agent.py dayu/host/engine_ingest.py
# 0 errors, 0 warnings, 0 informations
```

### 源码扫描

- `rg -n "error_code: str|error_code=\"|error_code=data\.error_code" dayu/engine dayu/host tests/engine tests/host`
  - `dayu/engine/contracts/` 公共字段无 `error_code: str` 退回
  - `dayu/engine/runners/openai/_choice_policy.py:80` 和 `sse_parser.py:303` 的 `error_code: str` 是 adapter 内部值，进入 `RunnerProtocolErrorData` 前已包装
  - `dayu/engine/agent.py:1435,1446` 的 `error_code=data.error_code` 是 typed union / wrapper 透传
  - Host / tests 中的 `error_code: str` 是 durable text、Host 自有错误码或测试 projection 字段
- `rg -n "RunFailedData\(|EngineRunOutcomeFailed\(|ProviderProtocolErrorData\(|RunnerProtocolErrorData\(" dayu/engine tests/engine`
  - 构造点均使用 enum member 或 wrapper constructor
  - `test_weak_typing_guard.py` 覆盖未来 literal string `error_code=` 回退
- `rg -n "error_code|provider_error_code|failure_metadata" dayu/host/engine_ingest.py`
  - Host ingest 通过 `serialize_engine_error_code(...)` 统一序列化 typed Engine code
- LLM-facing leakage 窄扫描: `rg -n "PROVIDER_DIAGNOSTIC|RunnerSpecificErrorCode|EngineRunErrorCode" dayu/config dayu/host/memory.py dayu/host/compact_* dayu/host/_terminal_answer.py dayu/host/accepted_result_projection.py` — 无命中

## 传播审计

1. **Provider protocol code**: OpenAI adapter 在产生 fatal runner protocol code 时构造 `RunnerSpecificErrorCode`（经 `runner_protocol_error_code()` / `http_provider_error_code()` 包装），保留闭集 source
2. **Agent failure candidate**: `RunnerProtocolErrorData.error_code` 是 `RunnerSpecificErrorCode`，Agent 直接透传给 `RunFailedData` 和 `ProviderProtocolErrorData`；Agent-owned known failures 使用 `EngineRunErrorCode` enum member；HTTP runner 非 context failure 使用 `adapter_error_code()`
3. **Engine `run_failed` / Agent outcome**: `RunFailedData.error_code` 与 `EngineRunOutcomeFailed.error_code` 均为 `EngineErrorCode` typed union；`__post_init__` 运行时校验拒绝裸字符串
4. **Host `RUN_FAILED`**: `engine_ingest.py` 在 ingest boundary 对 `event.data.error_code` / `data.error_code` 调用 `serialize_engine_error_code()`；durable JSON 写入序列化文本
5. **Tool Trace failure metadata**: `provider_error_code` 由 `serialize_engine_error_code()` 写入；`tool_trace.py` 只读取 durable text
6. **Public HostEvent / Read API / Outbox**: 从 durable payload 读 `error_code` / `provider_error_code` 文本；不读取 typed wrapper
7. **Memory / compact / evidence / LLM-facing**: 窄扫描未命中 typed error-code 或 provider diagnostic 关键字

## Open Questions

- 无

## Residual Risk

- S3 有意改变 Engine public contract 类型，不保留旧 string-only 构造兼容；符合 S3 non-goal / prohibition
- Provider-specific protocol code 仍以 durable serialized text 对外投影；Host 不掌握 wrapper source。若未来 public API 需要暴露 source，应由 Engine/Host public contract 单独设计
- `RunnerSpecificErrorCode` 继承 `str` 使得测试中 wrapper 与裸字符串可直接比较（finding 001），不影响生产正确性但降低部分测试回归检测精度

S3 code review complete.
