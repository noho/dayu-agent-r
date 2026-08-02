# Code Re-Review — S7/F07 Fix Loop Verification

## Scope

- Mode: current changes（S7 implementation + fix loop，未提交）
- Branch: `codex/interactive-oracle`
- Base: `b8f87e3b`（entry HEAD）
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s7-code-rereview-mimo.md`
- Included scope: fix loop 修改的 2 production + 3 test + 2 docs 文件，以及全部 S7 unstaged diff
- Excluded scope: frozen registry、README、Engine/CLI/Service production
- Parallel review coverage: 无（本轮 focused re-review，不需要并行 subagent）

## Finding-by-finding closure status

### C-001 — duplicate key repair feedback 泄密 — ✅ CLOSED

**裁决**: `accepted-medium`
**状态**: 已完整修复并验证

**修复验证**:

1. **`llm_compaction.py:1034-1038`**: duplicate key 的 `json_path` 设为固定 `$`，raw key 不进入 path
2. **`llm_compaction.py:1059`**: `message` 包含 raw_message 但经 `_single_parser_issue_report`（line 995-1009）的 `redact_sensitive_diagnostic_values` 脱敏
3. **`llm_compaction.py:995-1009`**: `json_path` 和 `message` 都经过 redaction + 240 字符截断
4. **`context_governance.py:755-790`**: `_bounded_issue_message` 对 `json_path`、`message`、每个 `source_label` 分别应用 `_bounded_feedback_text`（redaction + 240 字符 cap）
5. **`context_governance.py:131-147`**: 32 issue cap + 8192 总字符 cap，超出时从尾部 pop issue

**直接证据**:

- `test_secret_bearing_duplicate_key_report_and_repair_feedback_are_safe`（`test_llm_compaction.py:82-131`）：
  - 恶意 duplicate key 含 `api_key=sk-secret-123`、`token=token-secret-456`、`Bearer bearer-secret-789`、`password=password-secret-000`
  - 断言 `issue.json_path == "$"`（不是 raw key）
  - 断言 `<redacted>` 出现在序列化输出中
  - 断言 4 个 secret 均不出现在序列化输出中
  - 断言所有字段长度 ≤ 240，总长度 ≤ 8192

**风险**: 无。redaction 模式覆盖 `api_key=`、`token=`、`Bearer`、`password=`、`secret=`、`authorization=` 赋值模式；json_path 固定为 `$`；message 和 source_labels 都经过同一 redactor。

### C-002 — Memory policy cap 文档精度 — ✅ CLOSED

**裁决**: `accepted-low`
**状态**: 已完整修复并验证

**修复验证**:

1. **`docs/host/design.md:3375`**: 现在精确描述"session summary 字符上限，以及 evidence facts、answer anchors、forward intents、reference continuity 各自的 section item-count 与 aggregate-size 上限。diagnostics 不属于 Memory semantic projection，因此不受 `MemoryProjectionPolicy` cap"
2. **`docs/reviews/wu-cli-conformance-f01-f07-s7-implementation-codex.md:101`**: 现在精确描述"session summary 字符上限，facts、anchors、intents、references 各 section 的 item-count 与 aggregate-size `==cap` accept、`+1` reject；diagnostics 不属于 Memory policy cap"

**直接证据**:

- `context_governance.py:41`: `from dayu.host.memory import MemoryProjectionPolicy, estimate_memory_size_units`
- `memory.py:1021`: `estimate_memory_size_units` 定义在同一模块
- `context_governance.py:469`: `estimate_memory_size_units(candidate.session_summary.text).units > policy.session_summary_char_cap`

**风险**: 无。文档已与实际 `MemoryProjectionPolicy` 对齐。

### M-R1 / DS-1 — fresh v2 owner tests — ✅ CLOSED

**裁决**: `accepted-in-part`
**状态**: 总控点名的 4 条防御路径测试已全部添加并验证

**修复验证**:

1. **`test_cancellation_after_attempt_one_failure_stops_before_attempt_two`**（`test_compaction_operation.py:328-346`）:
   - attempt 1 失败后、attempt 2 前收到 parent cancellation
   - 断言 `accepted_truth is None`、`failure_reason == "cancellation_requested"`
   - 断言 `run_calls == 1`（第二次 prepare/run 均不发生）
   - 断言 rejected attempts 包含 `proposal_failed` 和 `cancellation_requested`

2. **`test_accepted_result_missing_manifest_or_response_identity_fails_closed`**（`test_compaction_operation.py:408-427`）:
   - 断言 `required_proposal_manifest_reference()` 在 manifest 缺失时 raise `RuntimeError`
   - 断言 `required_successful_response_identity()` 在 identity 缺失时 raise `RuntimeError`

3. **`test_reactive_later_pass_failure_returns_no_partial_truth`**（`test_compact_pipeline.py:429-467`）:
   - 较早 pass 成功、较晚 pass 失败
   - 断言 `failure_reason == "proposal_failed"`
   - 断言 `accepted_truth is None`、`accepted_attempt_number is None`、`accepted_successful_response_identity is None`
   - 断言 `accepted_proposal_manifest_reference is None`

4. **Secret-bearing parser report 进入下一 attempt 前已脱敏**: 由 `test_secret_bearing_duplicate_key_report_and_repair_feedback_are_safe` 覆盖

**直接证据**:

- 所有 4 个测试使用 fresh v2 contract，无 v1 fake/fixture
- diagnostics-only validity 继续由 accept-barrier owner test 覆盖

**风险**: 无。总控点名的防御路径全部覆盖。

## 不重开的已拒绝/关闭 finding

| ID | 裁决 | 理由 |
|---|---|---|
| M-001 | rejected | `CompactMaterialSection` 不是旧 `ConversationCompactLabelSectionVNext` |
| M-002 | rejected | duplicate label 已由 Context Governance 拒绝 |
| M-003 | rejected | dataclass Exception args 实际已填充 |
| M-004 | rejected | `compact()` 是文档化的单次便捷边界 |
| M-005 | rejected | 字符串前缀匹配由 owner tests 覆盖 |
| M-006 | rejected | utils diff 是 v2 consumer 迁移 |
| DS-2 | rejected | `-w` numstat 差异不是 conformance finding |
| DS-3 | rejected | free-text `intent_type`/`reason` 是 plan 冻结 |
| DS-4 | rejected | flattened anchor shape 是 plan 冻结 |
| DS-O1/O2/O3 | closed | 设计/evidence 已关闭 |

以上 finding 无新直接证据使其复活。

## Fix 引入的新 finding 扫描

### 扫描结果：未发现新 correctness/security/ownership finding

逐项检查：

1. **C-001 修复的副作用**: `_strict_object_pairs` 仍把 raw key 放入 `ValueError` 消息，但 `_parser_validation_report` 已在 line 1034-1038 将 `json_path` 固定为 `$`，且 message 经 redaction。`unknown_json_key` 路径（line 1039-1041）也经同一 redactor。无新泄露路径。

2. **C-002 修复的副作用**: 仅修改文档文本，无代码变更。无新 risk。

3. **M-R1/DS-1 新增测试**: 测试使用 fresh v2 contract 和 `ControllableCancellationToken`、`_PreparedRecordingCompactor` 等已有 fake。未引入新 fake/fixture。无新 risk。

4. **`required_proposal_manifest_reference()` / `required_successful_response_identity()`**: 这两个 guard 方法是 frozen dataclass 上的 fail-closed accessor。不改变 operation 逻辑，只暴露已有字段的 None-check。无新 risk。

## 验证记录

```text
# Focused tests
pytest -q tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_pipeline.py
43 passed in 0.36s

# Full S7 matrix (15 test files)
711 passed, 1 skipped, 3 warnings in 8.34s

# Focused pyright
python -m pyright dayu/host/llm_compaction.py dayu/host/context_governance.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_pipeline.py
0 errors, 0 warnings, 0 informations

# Full repository pyright
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

# Old v1 symbol scan (excluding README)
rg -n 'conversation_compact_(input|output)_v1|...' dayu/host/ dayu/config/ tests/host/ docs/host/design.md
<zero hits>

# Frozen registry digests
f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4  docs/cli_ci_oracles.json
7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef  docs/cli_ci_scenarios.json

# git diff --check
PASS

# git diff --cached --name-only
<empty>
```

## Open Questions

- 无。

## Residual Risk

- 无新 residual risk。C-001/C-002/M-R1/DS-1 均已完整关闭。
- README 历史说明属于已排期 S8 文档同步。
- LLM 自然语言质量风险由 accepted plan 已分类。

## 结论

**ACCEPT**

逐项验证结果：

| Finding | 状态 | 验证 |
|---|---|---|
| C-001 | ✅ CLOSED | duplicate key json_path=`$`，message/labels 经 redaction + 240/8192 cap，恶意 key 回归测试通过 |
| C-002 | ✅ CLOSED | design doc 和 implementation artifact 已精确描述实际 MemoryProjectionPolicy |
| M-R1/DS-1 | ✅ CLOSED | 4 条防御路径测试（mid-retry cancel、manifest/identity guard、later-pass failure、secret-safe feedback）全部添加并通过 |

Fix 未引入新 correctness/security/ownership finding。Full S7 matrix 711 passed，full repository pyright 0 errors，旧 v1 symbol 零命中，frozen registry 未变。
