# WU-LAYER-02 Aggregate Fix Re-Review — MiMo

- **Reviewer**: MiMo (mimo-v2.5-pro)
- **Date**: 2026-06-02
- **Gate**: aggregate fix re-review (F-01 closure)
- **Scope**: `dayu/host/llm_compaction.py` + `tests/host/test_llm_compaction.py`
- **Design source**: `docs/host/design.md` §3
- **Controller adjudication**: `docs/reviews/wu-layer-02-aggregate-review-controller-adjudication-20260602.md`
- **Fix report**: `docs/reviews/wu-layer-02-aggregate-fix-llm-compaction-report-20260602.md`
- **Original finding**: `docs/reviews/wu-layer-02-aggregate-review-ds-20260602.md` F-01

## Findings

**PASS — 0 findings.**

逐项审查结果如下。

### 1. Secret regex 迁移 — PASS

`_BEARER_SECRET_PATTERN` 和 `_ASSIGNMENT_SECRET_PATTERN` 已从 `llm_compaction.py` 完全删除（grep 零命中）。`_safe_outcome_text` 现在调用 `dayu.runtime.diagnostic_text.redact_sensitive_diagnostic_values`，使用 callable lambda replacement 而非旧的 `rf"\1{_REDACTED_SECRET}"` 字符串级 replacement。这消除了 DS F-01 中指出的 regex replacement 安全隐患（RR-L2-02）。

Runtime regex 比旧 Host regex 覆盖更广：新增 `password`、`api key`（空格写法）、`api-key:`（冒号分隔）等模式，属于 diagnostic-only 安全增强。

### 2. Host-specific truncation shape 保留 — PASS

`_safe_outcome_text` 未迁移 `truncate_diagnostic_text`，保留旧 Host truncation 行为：

```python
redacted = redact_sensitive_diagnostic_values(text, redaction_marker=_REDACTED_SECRET)
if len(redacted) <= _MAX_SAFE_OUTCOME_MESSAGE_CHARS:
    return redacted
return redacted[:_MAX_SAFE_OUTCOME_MESSAGE_CHARS] + _TRUNCATED_SUFFIX
```

超限时返回 `text[:240] + "..."`，总长 243。`test_safe_outcome_text_preserves_existing_truncation_shape` 锁定此形状。与 controller adjudication 约束一致。

### 3. 保留项完整性 — PASS

| 保留项 | 状态 | 证据 |
|---|---|---|
| `_SAFE_ERROR_CODE_PATTERN` | 保留 | L77，`re.compile(r"^[a-z][a-z0-9_-]{0,63}$")` |
| `_safe_error_code` | 保留 | L325-335，未修改 |
| `_non_final_outcome_message` | 保留 | L303-322，未修改 |
| `LLMCompactionProposalError` | 保留 | L122，未修改 |
| Engine outcome mapping | 保留 | L311-322，`EngineRunOutcomeFailed`/`Cancelled`/`Suspended` 分支未变 |
| timeout behavior | 保留 | L231，`raise LLMCompactionProposalError(_COMPACTOR_PROPOSAL_TIMEOUT_MESSAGE)` |
| Host compactor state semantics | 保留 | `CompactionCandidate`、`CompactionRequest`、diagnostic refs 全部未变 |
| `import re` | 保留 | L14，仍被 `_SAFE_ERROR_CODE_PATTERN` 使用 |

### 4. 测试覆盖 — PASS

新增 3 个测试函数（66 行），覆盖：

| 测试 | 覆盖目标 | 结果 |
|---|---|---|
| `test_safe_outcome_text_redacts_sensitive_diagnostic_values` (10 parametrized) | Bearer、`api_key=`、`token=`、`secret=`、`authorization=`、`password=`、`api key <value>`、`apikey=`、`api-key:<value>`、`api-key: <value>` | 通过 |
| `test_safe_outcome_text_does_not_redact_plain_token_diagnostic` | 普通 `JWT token has expired` 不误脱敏 | 通过 |
| `test_safe_outcome_text_preserves_existing_truncation_shape` | 超限文本截断为 240 字符 + `...`，总长 243 | 通过 |

新增测试 docstring 完整，含 `:param`/`:returns`/`:raises`。

### 5. 编码约束合规 — PASS

| 约束 | 状态 | 说明 |
|---|---|---|
| 禁止 `Any`/`object`/无类型签名 | PASS | 无新增类型违规；`object` 出现均为 JSON object docstring 上下文 |
| 禁止 `hasattr`/`getattr` | PASS | grep 零命中 |
| 禁止胶水 seam / lazy import | PASS | import 在模块顶层，非 lazy |
| 禁止 overbroad abstraction | PASS | 只迁移 redaction primitive，保留 Host truncation policy |
| 中文 docstring | PASS | 所有新增/改动函数有完整中文 docstring |

### 6. Scope 合规 — PASS

Controller adjudication 允许的文件：

| 文件 | 变更类型 | 合规 |
|---|---|---|
| `dayu/host/llm_compaction.py` | 删除私有 regex，使用 runtime primitive | PASS |
| `tests/host/test_llm_compaction.py` | 补齐 redaction/truncation 测试 | PASS |
| `docs/reviews/wu-layer-02-aggregate-fix-llm-compaction-report-20260602.md` | 记录实现裁决与验证 | PASS |
| `docs/host/host-core-followup-implementation-control.md` | 状态行更新 | PASS（control doc 更新属于 gateflow 常规维护） |

未触及 rejected scope（OpenAI diagnostic payload、runtime digest、Host durable、tool trace、EventLog、audit）。

### 7. README 同步 — PASS

本修复不改变 Host public contract、runtime public capability、CLI 使用方式或测试分类。不触发 README 更新条件。修复报告中已记录决策理由。

## Validation Summary

| 检查 | 命令 | 结果 |
|---|---|---|
| Runtime + Host compaction + import boundary | `pytest -q tests/runtime/test_diagnostic_text.py tests/host/test_llm_compaction.py tests/host/test_import_boundary.py` | **104 passed in 1.25s** |
| Pyright | `python -m pyright dayu/ tests/ utils/` | **0 errors, 0 warnings, 0 informations** |

## F-01 Closure Decision

**F-01 关闭。**

原始 finding（DS aggregate review）指出 `llm_compaction.py` 的私有 secret regex 是 WU-LAYER-02 scope 内的遗漏重复实现。本修复：

1. 删除了 `_BEARER_SECRET_PATTERN` 和 `_ASSIGNMENT_SECRET_PATTERN`。
2. 使用 `dayu.runtime.diagnostic_text.redact_sensitive_diagnostic_values` 替代，callable lambda replacement 消除了旧 `rf"\1{...}"` 安全隐患。
3. 保留了 Host-specific truncation shape（240 + `...` = 243），未静默改为 runtime total-max shape。
4. 补齐了 10 种 secret pattern + 误脱敏 guard + truncation shape 测试。
5. 所有保留项（`_SAFE_ERROR_CODE_PATTERN`、`_safe_error_code`、`_non_final_outcome_message`、`LLMCompactionProposalError`、Engine outcome mapping、timeout behavior）完整未动。

DS aggregate review 的 Residual Risks：
- **RR-L2-01**（`_safe_outcome_text` 未迁移 runtime primitive）→ 已关闭。redaction 部分已迁移；truncation 保留是刻意的 Host policy 决策。
- **RR-L2-02**（`rf"\1{...}"` 安全隐患）→ 已关闭。改用 callable lambda replacement。
- **RR-L2-03**（无直接 redaction 测试）→ 已关闭。10 parametrized + 误脱敏 guard + truncation shape 测试。
- **RR-L2-04**（旧 regex 不覆盖 `api key`、`password` 等）→ 已关闭。Runtime regex 覆盖更广。

WU-LAYER-02 aggregate owner boundary map 现在不再包含 `llm_compaction.py` 遗留条目。
