# WU-ENG-02 Slice 2 Re-Review - AgentMiMo

## Gate / Work Unit / Slice

- gate: re-review
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 2 - RunnerSpec Policy And OpenAI-Compatible Header Mapping
- agent: AgentMiMo

## Verdict

**pass**

## Accepted Finding Closure

### F2 - 补充 `ClientCorrelationPolicy.DISABLED` 且 `request_identity=None` 时不发送 `X-Client-Request-Id` 的直接测试

- **状态**: 已修复
- **证据**: `tests/engine/runners/openai/test_request_identity.py:161-175` 新增 `test_policy_disabled_without_identity_does_not_send_header`。
  - 构造 `ClientCorrelationPolicy.DISABLED` runner，`request_identity=None`。
  - 断言 `session.calls[0][2]` 不含 `X-Client-Request-Id`。
  - 测试正确覆盖了 DISABLED + None 交叉组合。
- **生产代码验证**: `_build_request_headers` (`runner.py:174`) 在 `DISABLED` 时直接 early return，不检查 `request_identity`；组合路径安全。
- **测试矩阵完整性**: 现在覆盖全部有意义的 policy × identity 组合：

| 场景 | 测试 | 状态 |
|---|---|---|
| enabled + identity | `test_policy_enabled_sends_x_client_request_id` | ✓ |
| disabled + identity | `test_policy_disabled_does_not_send_x_client_request_id` | ✓ |
| disabled + None | `test_policy_disabled_without_identity_does_not_send_header` | ✓ |
| enabled + None | `test_policy_enabled_without_identity_does_not_send_header` | ✓ |
| enabled + static conflict | `test_policy_enabled_rejects_static_case_insensitive_header` | ✓ |
| retry 复用 | `test_transport_retry_reuses_same_request_identity_header` | ✓ |

## New Findings

none

## Slice 2 生产代码 Plan 合规确认

逐项确认 Slice 2 已有生产代码仍满足 plan：

1. **RunnerSpec 显式 policy**: `runner_spec.py:280` 新增 `client_correlation_policy: ClientCorrelationPolicy` required field。✓
2. **OpenAI-compatible runner 只在 policy enabled 且 identity 存在时发送 header**: `runner.py:174-190` DISABLED early return；OPENAI_X_CLIENT_REQUEST_ID 分支检查 `request_identity is not None`。✓
3. **disabled 或 identity None 不发送**: `runner.py:174-175` DISABLED → return；`runner.py:186` identity None → skip。✓
4. **静态 header 冲突 fail-fast**: `runner.py:180-185` case-insensitive 检查后 `raise ValueError`。✓
5. **retry 复用同一 identity header**: `runner.py:378-380` headers 在 `_call_impl` 构造一次，传入 `_do_attempt` 复用。✓
6. **response x-request-id 采集未变更**: `_extract_provider_request_id` 未被修改。✓

## AgentCodex 越界检查

- **生产代码**: fix 未修改任何生产代码文件。✓
- **control doc**: control doc 变更为 Phaseflow 总控更新 gate 状态，非 AgentCodex fix。✓
- **README**: 未修改。✓
- **commit/push/PR**: 未执行。✓
- **修改范围**: 仅 `tests/engine/runners/openai/test_request_identity.py`（新增一个测试）和 `docs/reviews/wu-eng-02-slice2-fix-codex.md`（fix artifact）。✓

## Validation Commands / Results

| 命令 | 结果 |
|---|---|
| `pytest tests/engine/runners/openai/test_request_identity.py tests/engine/contracts/test_runner_spec.py tests/host/test_effective_execution_config.py -v` | 40 passed in 0.39s |
| `pyright` | 0 errors, 0 warnings, 0 informations |

## Residual Risk

| 风险 | Owner | 状态 |
|---|---|---|
| Host ingest / Tool Trace 诊断 payload 投影 `client_correlation_id` | Slice 3 | deferred-with-owner |
| `RunInputBuilder.build()` 投影 `attempt_id/execution_id` 到 `AgentRunRequest` | Slice 3 | deferred-with-owner |
| native Anthropic runner policy / response request-id | future adapter slice | deferred-with-owner |
| production assembly 当前 `DISABLED`；启用需显式 config/profile 决策 | config/product decision | deferred-with-owner |
| 静态 header 冲突 `ValueError` 是否需上层结构化失败收口 | Slice 3 / aggregate review | deferred-with-owner |
| README sync | Slice 4 | deferred-with-owner |

## Final Recommendation

Accepted finding F2 已正确修复，新增测试精确覆盖 DISABLED + None 交叉组合，生产代码未被越界修改，测试通过，pyright 无报错。Slice 2 re-review 通过，可进入下一 gate。
