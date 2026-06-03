# WU-ENG-02 Slice 2 Fix

## Accepted Finding

- Controller accepted finding：缺少直接测试覆盖 `ClientCorrelationPolicy.DISABLED` 且 `request_identity=None` 时，OpenAI-compatible runner 不应发送 `X-Client-Request-Id` header。
- 判断：动机成立。既有测试已覆盖 disabled + identity、enabled + no identity，但缺少 disabled + no identity 的交叉组合，无法直接防护 policy disabled 分支在身份缺失时误发客户端关联 header。

## 变更文件

- `tests/engine/runners/openai/test_request_identity.py`
  - 新增 `test_policy_disabled_without_identity_does_not_send_header`。
  - 构造 `ClientCorrelationPolicy.DISABLED` runner，传入 `request_identity=None`，断言 fake HTTP session 捕获的 outbound headers 不含 `X-Client-Request-Id`。

## 验证命令与结果

- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_request_identity.py tests/engine/contracts/test_runner_spec.py tests/host/test_effective_execution_config.py`
  - 结果：通过，`40 passed in 0.53s`。
- `source .venv/bin/activate && pyright`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`。

## 未覆盖项 / Residual Risk

- 本 fix 只补 Controller accepted finding 要求的窄测试，不新增生产代码。
- 未覆盖其它 provider 的 client correlation header 映射；Slice 2 当前目标限定 OpenAI-compatible runner。
- 未执行全量测试；本 gate 要求的指定测试与 pyright 已通过。

## 完成结论

- accepted finding 已修复。
- 本次只修改允许范围内的测试文件与 fix artifact，未修改生产代码、control doc、README、PR 或提交状态。
