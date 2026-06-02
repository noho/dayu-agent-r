# WU-LAYER-02 Slice 3 实施报告

## Changed files

- `dayu/host/compaction_operation.py`
  - 删除 Host compaction 私有 `_BEARER_SECRET_PATTERN` 与 `_ASSIGNMENT_SECRET_PATTERN`。
  - 引入 `dayu.runtime.diagnostic_text.redact_sensitive_diagnostic_values` 与 `truncate_diagnostic_text`。
  - `_safe_exception_message` 保持原有 Host 策略：`None` 返回 `none`，空白异常消息返回异常类名，非空消息先局部 value redaction，再按 Host 上限截断。
- `tests/host/test_compaction_operation.py`
  - 扩展 `_SensitiveFailingCompactor` 的异常消息覆盖范围。
  - 补充 value-bearing secret 参数化用例，覆盖 `Bearer`、`api_key=`、`token=`、`secret=`、`password=`、`api key `、`apikey=`、`api-key:` 与 `api-key: `。
  - 补充普通 `JWT token has expired` 不被误脱敏的诊断上下文保留测试。
  - 补充空异常消息路径，锁定 `_exception_diagnostic_suffix` 只输出异常类名、不拼接空消息。
  - 补齐本 Slice 新增 / 改动测试 helper 与测试函数的中文 docstring `:param` / `:returns` / `:raises` 说明。
- `docs/reviews/wu-layer-02-slice3-implementation-report-20260602.md`
  - 记录本 Slice 实施边界、验证结果、README 同步决策与 residual risks。

## 行为边界

- 本次是 diagnostic-only security hardening，不改变 compaction 状态机。
- 保留 `_ERROR_CODE_PATTERN` 与 `_exception_error_code`，`re` 仍只用于 Host compaction 的 `error_code=` 提取。
- 保留 `_exception_diagnostic_suffix` 的 Host-owned 异常类型前缀与消息拼接规则。
- 未修改 `CompactionAttemptRejected`、`diagnostic_refs` 结构、failure category、repair budget、quality check、multi-pass merge 或 Host Context Governance。
- Host 继续采用局部 value redaction：只替换敏感值，保留非敏感 provider 诊断上下文。

## 验证摘要

- `source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/host/test_compaction_operation.py`
  - 结果：`93 passed in 0.40s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
  - 备注：pyright 输出包含可用新版本提示，不影响本次类型验证结论。

## README 同步决策

- 未修改 README。
- 原因：本 Slice 只把 Host 私有异常诊断脱敏 / 截断实现切换到已存在的 runtime primitive；未改变 Host 对外接口、公共契约、运行方式、配置入口、分层关系或稳定文档职责范围。按 AGENTS.md 的 README 触发规则检查后，无需稳定文档同步。

## Residual risks

- 本次依赖 Slice 1 已建立的 `dayu.runtime.diagnostic_text` 正则语义；若未来需要新增 secret 形态，应优先扩展 runtime primitive 及其直接测试，再由 Host 通过同一 primitive 继承能力。
- Diagnostic ref 仍承载截断后的异常消息上下文；当前测试覆盖 value-bearing secret 与普通 token 句子，但不替代更广泛的 provider error payload 审计。
