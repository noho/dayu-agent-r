# WU-LAYER-02 聚合修复报告：LLM Compaction Diagnostic Text

- 日期：2026-06-02
- 范围：修复 aggregate review F-01 指出的 `dayu/host/llm_compaction.py` 私有 diagnostic text redaction helper 遗漏。
- 设计真源：`docs/host/design.md`
- Review 来源：`docs/reviews/wu-layer-02-aggregate-review-ds-20260602.md` F-01
- Controller 裁决：`docs/reviews/wu-layer-02-aggregate-review-controller-adjudication-20260602.md`

## Changed Files

- `dayu/host/llm_compaction.py`
  - 删除私有 `_BEARER_SECRET_PATTERN`。
  - 删除私有 `_ASSIGNMENT_SECRET_PATTERN`。
  - 在 `_safe_outcome_text` 中导入并使用 `dayu.runtime.diagnostic_text.redact_sensitive_diagnostic_values`。
  - 保留 `_SAFE_ERROR_CODE_PATTERN`、`_safe_error_code`、`_non_final_outcome_message`、`LLMCompactionProposalError`、Engine outcome mapping、timeout cancellation behavior 与 Host compactor state semantics。
- `tests/host/test_llm_compaction.py`
  - 为 `_safe_outcome_text` 增加直接 redaction 覆盖：Bearer、`api_key=`、`token=`、`secret=`、`authorization=`、`password=`、`api key <value>`、`apikey=`、`api-key:<value>` 与 `api-key: <value>`。
  - 增加普通 `JWT token has expired` 不误脱敏覆盖。
  - 增加现有 Host outcome truncation shape 覆盖。
- `docs/reviews/wu-layer-02-aggregate-fix-llm-compaction-report-20260602.md`
  - 记录实现裁决、验证输出、README 同步决策与 residual risks。

## Truncation 语义裁决

`_safe_outcome_text` 没有迁移到 `truncate_diagnostic_text`。

原因：现有 Host outcome 行为在 redacted message 超过 240 字符时返回 `text[:240] + "..."`，因此可见返回文本总长可以达到 243。`dayu.runtime.diagnostic_text.truncate_diagnostic_text` 保证返回总长不超过 `max_chars`；若直接用 `max_chars=240` 替换，会改变 proposal error text 的可见形状，不满足 controller 对 truncation shape 的约束。

本修复因此只把重复的 secret-value redaction primitive 迁移到 runtime，保留 Host-owned outcome truncation policy。`tests/host/test_llm_compaction.py::test_safe_outcome_text_preserves_existing_truncation_shape` 已锁定保留形状。

这不违反 WU non-goal：该 WU 明确不改变 Host-owned diagnostic event / state semantics。保留的 truncation shape 属于现有 Host proposal error text policy；删除的私有 regex helper 则是层中立 sensitive diagnostic value detection / redaction 重复实现。

## Validation Summary

- `source .venv/bin/activate && pytest -q tests/host/test_llm_compaction.py`
  - `39 passed in 0.27s`
- `source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/host/test_llm_compaction.py tests/host/test_import_boundary.py`
  - `104 passed in 1.24s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `0 errors, 0 warnings, 0 informations`

## README 同步决策

未更新 README。

理由：本聚合修复不改变 Host public contract、runtime public capability documentation、CLI 使用方式、项目 workflow、配置入口、包边界或测试分类。它只删除一个遗留的 Host 私有 regex 重复实现，并保留现有 Host outcome truncation 行为。WU-LAYER-02 已有的 `dayu.runtime.diagnostic_text` README 同步仍然充分。

## Residual Risks

- `_safe_outcome_text` 仍保留 Host-specific truncation shape，没有委托 runtime truncation。这是为保留可见 proposal error text 的刻意选择；若要改变，应作为单独显式 Host 行为决策。
- Runtime redaction 覆盖的 secret-bearing 写法多于旧私有 Host regex。这是聚合修复的目标并已有测试覆盖，但会把 compactor runner failure message 中新识别出的敏感值替换为 `<redacted>`。
- 本修复没有迁移或重新解释 OpenAI provider diagnostic payload、runtime digest、Host durable、tool trace、EventLog 或 audit 语义。
