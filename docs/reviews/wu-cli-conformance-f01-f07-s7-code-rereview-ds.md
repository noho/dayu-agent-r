# Code Re-Review — S7/F07 Fix Verification

## Scope

- Mode: current changes (fix re-review)
- Branch: `codex/interactive-oracle`
- Base: `b8f87e3b` (PR 190 HEAD)
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s7-code-rereview-ds.md`
- Review date: 2026-08-03T03:58:50+08:00
- Controller adjudication: `docs/reviews/wu-cli-conformance-f01-f07-s7-code-review-controller-adjudication.md`
- Fix artifact under review: `docs/reviews/wu-cli-conformance-f01-f07-s7-code-review-fix-codex.md`
- Prior review: `docs/reviews/wu-cli-conformance-f01-f07-s7-code-review-ds.md`
- Included scope: fix-loop changed files only (5 production/test + 2 docs)
- Excluded scope: frozen registry, README, Engine/CLI/Service/Fins production, all files not in fix loop
- Parallel review coverage: 无

## Controller-adjudicated finding closure

### C-001 — duplicate key repair feedback 泄密（accepted-medium）

**状态：✅ FULLY CLOSED**

逐项验证：

#### 1. Duplicate key raw key 不再进入 `json_path`

- **文件(行号)**: `dayu/host/llm_compaction.py:1034-1038`
- **直接证据**:
  ```python
  if raw_message.startswith("duplicate_json_key:"):
      code = CompactValidationIssueCodeV2.DUPLICATE_JSON_KEY
      # object_pairs_hook 尚不知道 nested object 的父路径；raw key 可能携带
      # secret，不能把它伪装成可回显的 JSON path。
      json_path = "$"
  ```
  `json_path` 固定为 `"$"` 而非 raw key。`DUPLICATE_JSON_KEY` code 自解释失败类别。
- **反例**: `test_secret_bearing_duplicate_key_report_and_repair_feedback_are_safe`（test_llm_compaction.py:82）构造 JSON key 为 `api_key=sk-secret-123 token=token-secret-456 Bearer bearer-secret-789 password=password-secret-000`，验证 `issue.json_path == "$"`（line 112）。

#### 2. Repair feedback 所有 LLM-facing 字段均脱敏并截断

- **文件(行号)**: `dayu/host/context_governance.py:755-790`
- **直接证据**: `_bounded_issue_message`（line 755）对 `json_path`、`message`、每个 `source_labels` 都调用 `_bounded_feedback_text`（line 776），后者组合 `redact_sensitive_diagnostic_values` + `truncate_diagnostic_text`（line 783-789）。code/attempt_number/required_action 不含 raw LLM 文本。
- **反例**: `test_repair_feedback_is_separate_and_requires_whole_candidate`（test_llm_compaction.py:221）用长 path（`$.api_key=sk-secret-123` + 500x `x`）、长 message（`token=secret-value` + 500x `x`）、长 labels（`Bearer bearer-secret-789` + 500x `x`），验证所有 secret 不在 repair prompt 中，且 path/message/labels 均 ≤ 240 字符。

#### 3. 单 issue 大量 labels 从尾部裁剪绕过整体 cap

- **文件(行号)**: `dayu/host/context_governance.py:138-150`
- **直接证据**: 新增 while 循环：当只剩 1 个 issue 但 feedback 仍超 8192 字符时，逐个从尾部去掉 source_labels 直到满足总长边界（line 138-150）。若 labels 已空仍超 cap，抛 `RuntimeError`（line 143）。
- **反例**: `test_repair_feedback_is_separate_and_requires_whole_candidate` 的 long-labels 场景间接覆盖此路径。

#### 4. Parser report 的 path 和 message 也经过脱敏

- **文件(行号)**: `dayu/host/llm_compaction.py:995-1010`
- **直接证据**: `_single_parser_issue_report` 对 `json_path` 和 `message` 均执行 `redact_sensitive_diagnostic_values` + `truncate_diagnostic_text`（240 字符上限），然后才构造 `CompactValidationReportV2`。

#### 5. 新引入 correctness/security 风险扫描

**未发现新风险。** `_bounded_issue_message` 的脱敏是纯文本变换，不改变 validation code、attempt number 或 `required_action` 的语义。feedback 字符数边界检查（32/240/8192）与非 labels 裁剪逻辑的降级路径均有显式上限。

---

### C-002 — Memory policy cap 文档精度（accepted-low）

**状态：✅ FULLY CLOSED**

逐项验证：

#### 1. design.md cap 描述修正

- **文件(行号)**: `docs/host/design.md` §24.3
- **直接证据**: 当前文本精确描述：
  > 使用 `MemoryProjectionPolicy` 与 Memory 相同的 `estimate_memory_size_units` 执行 session summary 字符上限，以及 evidence facts、answer anchors、forward intents、reference continuity 各自的 section item-count 与 aggregate-size 上限。diagnostics 不属于 Memory semantic projection，因此不受 `MemoryProjectionPolicy` cap。
- **与修复前对比**: 修复前文本笼统写 "item-char and total-char caps"，未区分 summary char cap 与各 section item-count/aggregate-size 的差异，也未说明 diagnostics 无 policy cap。

#### 2. Implementation artifact cap 描述修正

- **文件(行号)**: `docs/reviews/wu-cli-conformance-f01-f07-s7-implementation-codex.md` §4 验证矩阵 line 101
- **直接证据**: 当前文本精确描述：
  > session summary 字符上限，以及 facts、anchors、intents、references 各 section 的 item-count 与 aggregate-size `==cap` accept、`+1` reject；复用同一 `MemoryProjectionPolicy` 与 `estimate_memory_size_units`。diagnostics 不属于 Memory policy cap
- 与 `MemoryProjectionPolicy` 实际字段一致（验证矩阵 §9.8 row 4）。

#### 3. 确认未扩展产品策略

- 代码中 `MemoryProjectionPolicy` 字段无变更。
- `context_governance.py` 的 `_collect_policy_issues` 和 `memory.py` 的 `_validate_committed_candidate_policy` 消费相同 policy fields，未新增 cap 类型。

---

### M-R1 / DS-1 — accepted-in-part 防御路径测试

**状态：✅ FULLY CLOSED**

逐项验证：

#### 1. Mid-retry cancel

- **测试函数**: `test_cancellation_after_attempt_one_failure_stops_before_attempt_two`
- **文件(行号)**: `tests/host/test_compaction_operation.py:328-346`
- **直接证据**:
  - `_CancelBetweenAttemptsCompactor`（line 90-118）：attempt 1 在 `run_prepared_compactor_proposal` 中抛 `CompactorProposalError` 前调用 `self._cancellation_token.request_cancel("cancel_between_attempts")`。
  - 验证：`result.accepted_truth is None`、`result.failure_reason == "cancellation_requested"`、`compactor.run_calls == 1`（未执行 attempt 2）、`len(compactor.prepared_inputs) == 1`（attempt 2 的 prepare 未发生）。
  - rejected_attempts 正确记录 attempt 1 的 `proposal_failed` 和 attempt 2 的 `cancellation_requested`。
- **与旧测试对比**: 旧 `_CancelAfterFailureCompactor` 在 `compact()` 方法中取消，新实现在 `run_prepared_compactor_proposal()` 中取消并抛异常，适配 fresh v2 prepared compactor 接口。覆盖等价。

#### 2. Manifest/response identity guards

- **测试函数**: `test_accepted_result_missing_manifest_or_response_identity_fails_closed`
- **文件(行号)**: `tests/host/test_compaction_operation.py:408-427`
- **直接证据**:
  - 先运行成功 operation，验证 `result.required_proposal_manifest_reference()` 正确返回 manifest。
  - `missing_identity = replace(result, accepted_successful_response_identity=None)` 后调用 `required_successful_response_identity()` → `pytest.raises(RuntimeError, match="...missing successful response identity")`。
  - `_PreparedRecordingCompactor` 使用 fresh v2 prepared compactor 接口（`prepare_compactor_proposal_run_input` + `run_prepared_compactor_proposal`），不依赖旧 `compact()` fake。
- **与旧测试对比**: 旧测试通过直接调用 guard 函数验证，新测试通过 operation result 的 `required_*` 方法验证，更贴近真实调用路径。

#### 3. Later-pass failure no partial truth

- **测试函数**: `test_reactive_later_pass_failure_returns_no_partial_truth`
- **文件(行号)**: `tests/host/test_compact_pipeline.py:429-467`
- **直接证据**:
  - `_LaterPassFailingCompactor`（line 160-199）：`run_calls > 1` 时抛 `CompactorProposalError`。
  - 使用 `build_reactive_pass_queue_plan` 构造真实 reactive queue，通过 `run_compaction_operation` 执行。
  - 验证：`compactor.run_calls == len(queue.pass_requests)`（所有 pass 至少执行一次）、`result.accepted_truth is None`、`result.accepted_attempt_number is None`、`result.accepted_successful_response_identity is None`、`result.accepted_proposal_manifest_reference is None`。
  - 所有 rejected_attempts 的 `failure_category.value == "proposal_failed"`，无 partial truth 泄漏。
- **与旧测试对比**: 旧 `_SecondPassFailingCompactor` 使用 `compact()` 单 attempt API，新测试使用 prepared compactor + `run_compaction_operation` + reactive queue，覆盖真实 multi-pass 路径。

#### 4. 额外覆盖：cross-pass duplicate routes full pass repair

- **测试函数**: `test_reactive_cross_pass_duplicate_routes_full_pass_repair`
- **文件(行号)**: `tests/host/test_compact_pipeline.py:470-504`
- **直接证据**: `_CrossPassDuplicateCompactor` 让各 pass 产生相同 reference identity → root revalidation 检测到 cross-pass duplicate → 路由到最后一个贡献 pass → 用 `repair_feedback`（code=`duplicate_semantic_item`）完整重产 → 最终 success。
- 此测试是 fix 新增的 bonus 覆盖，证明了 root duplicate detection → pass routing → whole-candidate repair → final success 的完整闭环。

---

## 新 Correctness/Security/Ownership Finding 扫描

**逐项扫描结果：未发现新 finding。**

| 检查维度 | 方法 | 结果 |
|---|---|---|
| duplicate key raw key 泄漏 | 代码走读 llm_compaction.py:1034-1038 + 测试断言 | 固定为 `"$"`，不泄漏 |
| repair feedback path/message/label 泄密 | 代码走读 context_governance.py:755-790 + 测试断言 | 三个字段均 redact + truncate |
| repair feedback 绕过 8192 总长边界 | 代码走读 context_governance.py:138-150 | 逐 label 裁剪，最终 RuntimeError 降级 |
| execution retry 伪装成 semantic repair | 代码走读 _ParserRejectOnceCompactor 测试 | LLMCompactionValidationError vs CompactorProposalError 区分 |
| old symbol/v1 reader 新引入 | `rg` 扫描 changed files | 零命中 |
| hasattr/getattr 新引入 | `rg` 扫描 changed files | 零命中 |
| loose parsing/fallback 新引入 | 代码走读 | 无新增 |
| middle pass truth 泄漏到 durable | 代码走读 test_reactive_later_pass_failure | accepted_truth is None |
| manifest/identity guard 绕过 | 代码走读 test_accepted_result_missing | RuntimeError fail-closed |
| cancellation 在 attempt 间被忽略 | 代码走读 test_cancellation_after_attempt_one_failure | 第二次 prepare/run 均不发生 |

---

## Validation Summary

| 检查 | 结果 |
|---|---|
| Focused tests (3 files, 43 tests) | `43 passed in 0.37s` |
| Full S7 matrix (15 files, 711 tests) | `711 passed, 1 skipped, 3 warnings in 8.38s` |
| pyright (changed files) | `0 errors, 0 warnings, 0 informations` |
| pyright (full dayu/host + dayu/config + tests/host) | `0 errors, 0 warnings, 0 informations` |
| Old symbol scan (changed files) | 零命中 |
| `git diff --check` | clean |
| Frozen registry SHA-256 | `f9972d...` / `7f283b...` — unchanged |
| `ruff check` (all changed Python) | All checks passed |

---

## Open Questions

无。

---

## Residual Risk

1. **LLM 自然语言质量**（已知，非实现缺陷）：secret-safe feedback 和 bounded repair 已由 deterministic contract 保证，但模型在收到脱敏 feedback 后能否正确理解并修复语义问题，仍属于模型评估风险。

2. **`dayu/host/README.md:735` 的 v1 文档残留**：仍在 S8 文档 gate scope，不在本轮 fix loop 范围。

3. **S7 outer slice 的既有 unstaged diff**：fix loop 仅修改了 5 个 production/test 文件和 2 个 doc 文件；37 个文件的既有 S7 diff 保持不变。本 re-review 验证了 fix 的 5+2 文件正确性，未对整个 S7 diff 做第二轮全量审查。

---

## 结论

**ACCEPT** — 三个 controller-accepted findings（C-001、C-002、M-R1/DS-1）均已被 fix 完整关闭。未发现 fix 引入的新 correctness、security 或 ownership finding。所有 focused tests、full S7 matrix、pyright、old symbol scan、registry integrity 和 `git diff --check` 均通过。
