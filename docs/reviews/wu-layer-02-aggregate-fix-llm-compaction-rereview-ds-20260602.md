# WU-LAYER-02 Aggregate Fix Re-Review — DS

- **Reviewer**: DS (deepseek-v4)
- **Date**: 2026-06-02
- **Gate**: aggregate fix re-review
- **Scope**: WU-LAYER-02 aggregate F-01 fix for `dayu/host/llm_compaction.py`
- **Upstream review**: `docs/reviews/wu-layer-02-aggregate-review-ds-20260602.md` F-01
- **Controller adjudication**: `docs/reviews/wu-layer-02-aggregate-review-controller-adjudication-20260602.md`
- **Fix report**: `docs/reviews/wu-layer-02-aggregate-fix-llm-compaction-report-20260602.md`

## Verification Summary

| Check | Command | Result |
|---|---|---|
| Runtime direct + Host compaction + import boundary | `pytest -q tests/runtime/test_diagnostic_text.py tests/host/test_llm_compaction.py tests/host/test_import_boundary.py` | 104 passed |
| Pyright | `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## Findings（按 Severity 排序）

### F-R1-01 [PASS] 私有 secret regex 已删除，统一使用 runtime redaction

**检查项**: `_BEARER_SECRET_PATTERN` 与 `_ASSIGNMENT_SECRET_PATTERN` 是否从 `dayu/host/llm_compaction.py` 删除，`_safe_outcome_text` 是否使用 `redact_sensitive_diagnostic_values`。

**直接证据**:

1. `dayu/host/llm_compaction.py` 第 70 行新增导入：
   ```python
   from dayu.runtime.diagnostic_text import redact_sensitive_diagnostic_values
   ```

2. 旧私有 regex 已完全删除（git diff 确认为删除行）：
   ```python
   # 已删除:
   _BEARER_SECRET_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
   _ASSIGNMENT_SECRET_PATTERN = re.compile(r"(?i)((?:api[_-]?key|authorization|secret|token)\s*[:=]\s*)[^,\s}\]]+")
   ```

3. `_safe_outcome_text`（第 346 行）改为调用 runtime primitive：
   ```python
   redacted = redact_sensitive_diagnostic_values(text, redaction_marker=_REDACTED_SECRET)
   ```

4. `import re` 保留在第 14 行——正确，因为 `_SAFE_ERROR_CODE_PATTERN = re.compile(...)` 仍在使用。

**结论**: PASS。私有 regex 重复实现已消除，Host compactor redaction 已收敛到 `dayu.runtime.diagnostic_text` 唯一真源。

---

### F-R1-02 [PASS] Host-specific truncation shape 保留

**检查项**: `_safe_outcome_text` 的 truncation 逻辑是否保留旧 shape（`text[:240] + "..."` 总长可达 243），是否被静默改为 runtime `truncate_diagnostic_text` 的 total-max 语义。

**直接证据**:

1. `_safe_outcome_text`（第 347-349 行）保留原截断逻辑：
   ```python
   if len(redacted) <= _MAX_SAFE_OUTCOME_MESSAGE_CHARS:
       return redacted
   return redacted[:_MAX_SAFE_OUTCOME_MESSAGE_CHARS] + _TRUNCATED_SUFFIX
   ```

2. `_MAX_SAFE_OUTCOME_MESSAGE_CHARS = 240`、`_TRUNCATED_SUFFIX = "..."` 保留。

3. 未导入 `truncate_diagnostic_text`——刻意不迁移，与 fix report 的 truncation 语义裁决一致。

4. 测试 `test_safe_outcome_text_preserves_existing_truncation_shape` 锁定旧 shape：
   - 输入 241 字符 → 输出前 240 字符 + `"..."` → 总长 243

**结论**: PASS。Host outcome truncation 行为完全保留，未静默改变。

---

### F-R1-03 [PASS] Host compactor semantics 完整保留

**检查项**: `_SAFE_ERROR_CODE_PATTERN`、`_safe_error_code`、`_non_final_outcome_message`、`LLMCompactionProposalError`、Engine outcome mapping、timeout behavior、Host compactor state semantics 是否未被误改。

**逐项核对**:

| 语义项 | 行号 | 状态 |
|---|---|---|
| `_SAFE_ERROR_CODE_PATTERN` | 77 | 保留，值未变 |
| `_safe_error_code` | 325-335 | 保留，`unknown_error` fallback 未变 |
| `_non_final_outcome_message` | 303-322 | 保留，EngineRunOutcomeFailed/Cancelled/Suspended + fallback 未变 |
| `LLMCompactionProposalError` | 122-126 | 保留，类定义与 docstring 未变 |
| Engine outcome mapping（`compact()` 内） | 232-235 | 保留，`EngineRunOutcomeFinalAnswer` 检查、`_non_final_outcome_message` 调用未变 |
| timeout 取消语义 | 229-231 | 保留，`TimeoutError` catch → `_signal_timeout_cancellation` → `LLMCompactionProposalError` |
| `_signal_timeout_cancellation` + `_CancellationSignalToken` | 108-119, 292-300 | 保留 |
| `_RejectingToolExecutor` | 129-145 | 保留 |
| `_candidate_from_final_answer` 全套 parser | 386-451 | 保留 |
| 所有 `CompactInputRange`/`PreservationEvidence`/`EpisodeSummaryCandidate` 等 Host 语义 | 453+ | 保留 |

**结论**: PASS。Host compactor 所有语义项均未被误改。

---

### F-R1-04 [PASS] 测试覆盖 redaction 新旧形态、普通 token 不误脱敏、truncation shape

**检查项**: `tests/host/test_llm_compaction.py` 新增测试是否覆盖敏感值脱敏、false-positive guard 和 truncation shape。

**逐项核对**:

1. **Redaction 新旧形态** — `test_safe_outcome_text_redacts_sensitive_diagnostic_values`（第 75-107 行），10 个 parametrized case：

   | 模式 | 输入示例 | 覆盖源 |
   |---|---|---|
   | `Authorization: Bearer <value>` | `Bearer bearer-secret` | 旧 Host regex + runtime |
   | `api_key=<value>` | `api_key=api-key-secret` | 旧 Host regex + runtime |
   | `token=<value>` | `token=token-secret` | 旧 Host regex + runtime |
   | `secret=<value>` | `secret=secret-value` | runtime 新增 |
   | `authorization=<value>` | `authorization=authorization-secret` | 旧 Host regex + runtime |
   | `password=<value>` | `password=password-secret` | runtime 新增 |
   | `api key <value>` （空格） | `api key spaced-secret` | runtime 新增 |
   | `apikey=<value>` | `apikey=apikey-secret` | runtime 新增 |
   | `api-key:<value>` | `api-key:colon-secret` | runtime 新增 |
   | `api-key: <value>` | `api-key: spaced-colon-secret` | runtime 新增 |

   每个 case 验证：secret_value 不在结果中、`<redacted>` 在结果中、非敏感上下文（`"provider failed"`、`"tail"`）保留。

2. **普通 JWT token 不误脱敏** — `test_safe_outcome_text_does_not_redact_plain_token_diagnostic`（第 110-119 行），输入 `"JWT token has expired"`，断言完全不改。验证 runtime `\b` word-boundary guard 对普通 token 诊断句生效。

3. **Truncation shape** — `test_safe_outcome_text_preserves_existing_truncation_shape`（第 122-138 行），241 字符输入 → `("x" * 240) + "..."`，长度 243。

4. **已有 integration 测试** — `test_llm_context_compactor_sanitizes_failed_runner_outcome`（第 774-820 行）继续通过，覆盖 `_non_final_outcome_message` → `_safe_outcome_text` 完整路径。

5. **Docstring** — 所有三个新增测试均有完整中文 docstring，包含 `:param`、`:returns`、`:raises`。

**结论**: PASS。新增测试覆盖了旧 Host regex 的全部场景、runtime 新增的 security hardening 模式、false-positive guard、truncation shape，且 docstring 完整。

---

### F-R1-05 [PASS] Overbroad abstraction / rejected scope / 类型签名 / getattr-hasattr / README 同步

**逐项核对**:

| 约束 | 状态 | 说明 |
|---|---|---|
| Overbroad abstraction | PASS | diff 只新增一行 import、删除两行 regex 定义；`_safe_outcome_text` 函数体减少为一次 runtime 调用 + 保留 truncation |
| 胶水 seam / lazy import | PASS | 无 |
| Rejected scope 误改 | PASS | diff 仅触及 `dayu/host/llm_compaction.py`、`tests/host/test_llm_compaction.py`、control doc；未改动 OpenAI diagnostic payload、runtime digest、Host durable、tool trace、EventLog |
| `Any` / `object` / 无类型签名 | PASS | 三个新测试函数 `raw_message: str, secret_value: str` / 无参 / 无参，返回值均为 `None` |
| `hasattr` / `getattr` | PASS | r1 diff 确认零命中 |
| 兼容性 wrapper / re-export | PASS | 无 |
| README 同步 | PASS | 不触发 README 更新规则——Host public contract、runtime public capability、CLI 命令、项目 workflow、配置入口、测试分类均未变化；仅删除私有 regex 重复实现 |
| `import re` 是否误删 | PASS | 第 14 行 `import re` 保留，因 `_SAFE_ERROR_CODE_PATTERN` 仍需 `re.compile()` |

**结论**: PASS。

---

## 对比 Fix Report 的 Residual Risks

Fix report 列出三项 residual risks，re-review 逐项评估：

| Risk | Fix Report 描述 | Re-review 评估 |
|---|---|---|
| `_safe_outcome_text` 保留 Host truncation shape | 未委托 runtime truncation，是刻意选择 | **确认**。旧 shape 保留，测试锁定。不构成问题。 |
| Runtime redaction 覆盖更多 secret pattern | 会脱敏旧私有 regex 未覆盖的模式 | **确认**。这是聚合修复的目标——收敛到 runtime 更全面的 security hardening。测试已覆盖新增模式。不构成回归。 |
| 未迁移 OpenAI provider diagnostic payload 等 | 明确不迁移 | **确认**。diff 未触及这些文件。 |

---

## F-01 关闭裁决

F-01（`llm_compaction.py` 私有 secret regex 未迁移）已完全修复：

- `_BEARER_SECRET_PATTERN` 与 `_ASSIGNMENT_SECRET_PATTERN` 已从 `dayu/host/llm_compaction.py` 删除。
- `_safe_outcome_text` 的 secret redaction 已迁移到 `dayu.runtime.diagnostic_text.redact_sensitive_diagnostic_values`。
- Host truncation shape 保留，不委托 runtime `truncate_diagnostic_text`——有明确的语义裁决和测试锁定。
- 所有 Host compactor 语义项（error_code、outcome mapping、timeout、parser、state machine）保留。
- 新增测试覆盖 10 种 secret pattern + false-positive guard + truncation shape。
- 104 测试通过，pyright 0 errors。

**F-01 可关闭。** Host compaction 域旧有两套 secret regex 的重复问题已消除。

---

## Verdict

**PASS — 0 findings.**

WU-LAYER-02 aggregate fix 正确、完整地解决了 F-01。`dayu/host/llm_compaction.py` 的 secret redaction helper 已收敛到 `dayu.runtime.diagnostic_text`，Host truncation policy 保留，所有 Host compactor 语义完整，测试覆盖充分，pyright clean。

原始 aggregate review 中 4 项 residual risks（RR-L2-01 到 RR-L2-04）中，RR-L2-01（llm_compaction 未迁移）已关闭；RR-L2-02（字符串级 replacement 依赖）因替换为 runtime 的 callable lambda replacement 已消除；RR-L2-03（缺少直接测试）已通过新增 3 个测试消除；RR-L2-04（runtime 新增 security hardening 模式）已在测试中覆盖，不再是遗漏而是增强。
