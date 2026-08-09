# PR190 F15/F16 Implementation Re-Review（DeepSeek 独立复读）

## Gate / scope

- Gate: implementation re-review（Controller 裁决修复后独立复读）。
- Branch / base: `codex/interactive-oracle` / `580b1427`。
- Binding artifacts:
  - `docs/gateflow/pr-190-f15-f16-plan-acceptance-20260807.md`
  - `docs/gateflow/pr-190-f15-f16-implementation-20260807.md`
  - `docs/gateflow/pr-190-f15-f16-implementation-review-adjudication-20260807.md`
  - `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md`
- 独立审查输入：
  - `docs/reviews/pr-190-f15-f16-implementation-review-mimo-20260807.md`
  - `docs/reviews/pr-190-f15-f16-implementation-review-ds-20260807.md`
- 未 commit、未 push、未创建或修改 PR。本复读只审查，严禁编辑代码。

## 审查范围

- Tracked diff（11 文件 + `utils/cli_ci_run_observation.py` 新增）
- 两个 ignored temporary harness：
  - `workspace/tmp/prompt_observe_calibration.py`
  - `workspace/tmp/f14_real_cli_observation.py`
- Focused tests:
  - `tests/cli/test_cli_ci_run_observation.py`
  - `tests/host/test_compact_material.py`
  - `tests/host/test_context_compact_events.py`
- 禁止面审计：`dayu/host/durable/run_transition.py`、oracle/scenario files、prompts、Engine

## SHA-256 摘要验证（对应 C05）

| 文件 | 期望 SHA-256（review-fix artifact） | 实际 SHA-256 | 匹配 |
|---|---|---|---|
| `utils/cli_ci_run_observation.py` | `d7719543...` | `d7719543...` | ✅ |
| `workspace/tmp/prompt_observe_calibration.py` | `6d544413...` | `6d544413...` | ✅ |
| `workspace/tmp/f14_real_cli_observation.py` | `b4657d83...` | `b4657d83...` | ✅ |

## 逐项验证

### MiMo 001 — invalid 不二次崩溃且保留 diagnostic

**验证结果: FIXED / PASS**

证据链：

1. `_segment_terminal_facts()`（`f14_real_cli_observation.py:541-686`）对所有异常路径调用 `_invalid_segment_terminal_facts()`：
   - `FileNotFoundError` / `OSError` / `UnicodeError` → 保留 `type(error).__name__: {error}`（`:559-563`）
   - `json.JSONDecodeError` → 保留 malformed 诊断（`:568-572`）
   - 非 dict root → 保留 shape 诊断（`:574-578`）
   - `evidence_status == "invalid"` → 保留 upstream validation_errors（`:581-596`）
   - summary 缺失/非 dict → 保留诊断（`:598-603`）
   - count 字段非法 → 保留精确字段名诊断（`:616-621`）
   - runs 数量不匹配 → 保留诊断（`:624-628`）
   - summary terminal counts 相加 != accepted → 保留诊断（`:659-663`）
   - accepted == 0 → 保留诊断（`:665-669`）
   - missing/invalid > 0 → 保留诊断（`:670-675`）

2. 所有路径均返回 `SegmentTerminalFacts(evidence_status=RunEvidenceStatus.INVALID, ...)`，不抛出异常。

3. `_run_segment()`（`:434`）在 `_run_scenario()` 异常后仍调用 `_segment_terminal_facts()`，并正确将 evidence status 写入 row。

4. 反例构造验证：`_invalid_segment_terminal_facts()` 在 `diagnostics` 为空时 `raise ValueError("invalid segment diagnostics must not be empty")`（`:500-501`），确保不静默丢失诊断。

**结论**: invalid 场景不二次崩溃、不静默降为 `(0, False)`、保留完整 diagnostics。✅

---

### MiMo 002 — index 字段完整

**验证结果: FIXED / PASS**

证据链：

`execution-index-f15-f16.json`（`:1443-1469`）包含：
- `target_commit` — commit SHA
- `source_digests` — 三个源码 SHA-256
- `scenario_count`
- `process_outcomes` — 逐行 kind/exit_code 聚合
- `run_terminal_summary` — 八类 terminal counts（accepted/succeeded/failed/cancelled/lost/missing/invalid/duplicate）
- `run_terminal_records` — per-Run record path/digest
- `dependency_gates` — proceeded/stopped/invalid/not_run 计数
- `context_compaction_observation` — compaction count/refs
- `evidence_status` — complete/insufficient/invalid
- `harness_invalid_count`
- `rows` — 完整 per-scenario rows
- `public_evidence` — tool_trace 收集结果
- `secret_scan` — status/record_path/record_digest
- `raw_host_sqlite_in_public_evidence: False`
- `oracle_status: "unadjudicated"`

无 `scenario_success`、`success`、`passed`、`execution_outcome` 字段。✅

---

### MiMo 003 — INDEPENDENT 角色保留

**验证结果: REJECTED-WITH-REASON / CONTRACT 加固 / PASS**

证据链：

1. `RunObservationRole.INDEPENDENT = "independent"` 保留（`utils/cli_ci_run_observation.py:62`）。

2. `run_observation_role_for_harness_action()`（`:492-507`）将 `HarnessActionRole.INDEPENDENT` 显式投影为 `RunObservationRole.INDEPENDENT`。

3. `HarnessActionControl.__post_init__()` 校验：non-dependent action 不得声明 upstream ordinal（`:118-119`），确保 independent 不被误分类为 dependent。

4. `CLEANUP_EOT` 显式不得投影为 Run role（`:505-506`），防止 cleanup 伪装 Run。

5. `test_upstream_to_dependent_ordinal_and_independent_role_are_explicit` 断言 independent role 映射。✅

---

### DS 016 — accepted tool evidence 构造重复

**验证结果: ACCEPTED-CONDITION / FIXED / PASS**

证据链：

1. 两个 typed wrapper：
   - `_CanonicalMaterialText(value: str)` — 经 normalizer 的 canonical text
   - `_AcceptedToolEvidenceText(value: str)` — exact renderer text

2. Union type: `_PreparedMaterialText = _CanonicalMaterialText | _AcceptedToolEvidenceText`

3. 唯一 low-level constructor `_run_input_material_block_from_prepared_text()`（`:903-978`）：
   - `text` 参数为 `_PreparedMaterialText`
   - `isinstance(text, _AcceptedToolEvidenceText)` 时要求 `accepted_tool_evidence is not None`
   - `isinstance(text, _CanonicalMaterialText)` 时禁止携带 `accepted_tool_evidence`

4. `_accepted_tool_evidence_text()` 调用 `render_accepted_tool_evidence_for_llm()` 验证 exact matching（`:917-918`）。

5. `run_input_material_block()` public API 内部分发到 typed wrapper → 统一 constructor。

6. 无 dict、bool、trusted string 或 raw exact 冒充 canonical。✅

---

### DS 017 — whitespace boundary test 缺口

**验证结果: FIXED / PASS**

证据链：

1. `test_whitespace_only_candidate_anchor_is_rejected_at_typed_accept_boundary`（`test_context_compact_events.py:355`）：
   - 构造 `CompactAnswerAnchorV4(title="  \n\t ", ...)`
   - 断言 `pytest.raises(ValueError, match="CompactAnswerAnchorV4.title")`

2. `test_whitespace_only_persisted_replacement_is_rejected_at_read_boundary`（`:370`）：
   - 构造 payload 中 `anchors[0]["title"] = " \n\t "`
   - 断言 `parse_context_compacted_semantic_payload` 抛出 `ValueError(match="title")`

3. `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact`（`test_compact_material.py:2062`）：
   - 使用 P3/P4 label 断言 answer anchor exact
   - 覆盖 leading/trailing/repeated whitespace、blank lines、multiline prose、Markdown bullet/numbered list/table

4. 纵深防御：`normalized_material_text()` 已 raise `ValueError` on empty（`:850-851`），typed constructor 在 owner boundary 拒绝。✅

---

### DS 018 — 隐式 ordinal `+1`

**验证结果: FIXED / PASS**

证据链：

1. `dependent_action_accepted_ordinal(required_success_accepted_ordinal)`（`:471-489`）集中 `+ 1` 转换。

2. 输入校验：`_require_positive_int(...)` 拒绝 bool、非 int、非正数。

3. `test_upstream_to_dependent_ordinal_and_independent_role_are_explicit` 断言 `dependent_action_accepted_ordinal(7) == 8`。

4. Temporary harness 中不再散落裸 `+ 1` 算术，统一消费此 helper。✅

---

### C01 — dependency stop 后 PTY 可永久等待

**验证结果: FIXED / PASS**

证据链：

1. `classify_remaining_actions_for_safe_stop()` pure helper（`:540-587`）：
   - 所有 dependent action → `NOT_RUN_DEPENDENT`
   - 首个 `CLEANUP_EOT` → `SEND_CLEANUP_EOT`
   - 后续 `CLEANUP_EOT` / non-dependent action → `NOT_RUN_PROCESS_STOP`
   - 缺少 EOT → `ValueError("remaining actions must include explicit cleanup/EOT")`

2. PTY harness `_safe_stop_remaining_actions()`（`prompt_observe_calibration.py:945-995`）：
   - 调用 `classify_remaining_actions_for_safe_stop()`
   - 仅对 `SEND_CLEANUP_EOT` disposition 发送 PTY action
   - 其他 action 记录 `not_run`，不发送任何依赖输入

3. Process exit 通过 10 秒 cleanup deadline 保证不永久等待。

4. `test_safe_stop_classifies_dependents_and_sends_one_cleanup_eot`（`test_cli_ci_run_observation.py:563`）断言：
   - 2 dependent → `NOT_RUN_DEPENDENT`
   - 第 1 个 EOT → `SEND_CLEANUP_EOT`
   - 第 2 个 EOT → `NOT_RUN_PROCESS_STOP`

5. 反例验证（本复读构造）：
   - 无 EOT → `ValueError`
   - 仅 dependent → `ValueError`
   - independent 在 safe stop → `NOT_RUN_PROCESS_STOP`
   - 所有反例均 fail closed ✅

---

### C02 — valid failure 被误投影为 evidence complete

**验证结果: FIXED / PASS**

证据链：

1. `classify_required_run_evidence()` pure classifier（`:510-537`）：
   - `None` 或空 tuple → `INVALID`
   - 全部 `SUCCEEDED` → `COMPLETE`
   - 含 FAILED/CANCELLED/LOST → `INSUFFICIENT`

2. `_segment_terminal_facts()` 调用 `classify_required_run_evidence(tuple(required_terminal_statuses))`（`:676-678`）。

3. `_top_evidence_status()`（`f14_real_cli_observation.py:1188-1250`）：
   - 合并 run_terminal evidence、context compaction、secret scan、public evidence 状态
   - `invalid` → `"invalid"`
   - 无 invalid 但有 insufficient → `"insufficient"`
   - 均无 → `"complete"`

4. `test_required_run_evidence_distinguishes_complete_insufficient_and_invalid` 参数化覆盖：
   - `(SUCCEEDED,)` → COMPLETE
   - `(FAILED,)` → INSUFFICIENT
   - `(CANCELLED, SUCCEEDED)` → INSUFFICIENT
   - `None` → INVALID
   - `()` → INVALID

5. 反例验证：FAILED/CANCELLED/LOST/mixed 均 `is not COMPLETE` ✅

---

### C03 — terminal pair identity 与 shared projector 未完全同源

**验证结果: FIXED / PASS**

证据链：

1. Session identity：`terminal.session_id != accepted.session_id` → `RunObservationError`（`:682-684`）。

2. Terminal class 复用 lifecycle owner：
   - `_terminal_status()` → `run_status_for_terminal_event()`（`:740-751`）
   - 非 terminal enum → `RunObservationError`

3. Public-outbox 复用 shared projector：
   - `is_public_outbox_terminal_item_event(terminal.event_type)`（`:704-706`）
   - 不再手写四分支与 `terminal_type is not RUN_LOST` 否定映射。

4. `test_terminal_session_must_match_accepted_session` 断言跨 session terminal → `RunObservationError`。

5. `test_terminal_projection_keeps_each_canonical_terminal_and_reason` 断言：
   - 四类 terminal event type exact
   - 四类 terminal class (SUCCEEDED/FAILED/CANCELLED/LOST) exact
   - public_outbox 布尔序列 = `(True, True, True, False)`（LOST = False）✅

---

### C04 — formal adjudication 状态值错误

**验证结果: FIXED / PASS**

证据链：

1. `execution-index-f15-f16.json` 中 `"oracle_status": "unadjudicated"`（`f14_real_cli_observation.py:1468`）。

2. Scenario rows 中 `"scenario_status": "unadjudicated"`（`:1300`）。

3. 全文搜索无 `pending_user_adjudication`、`accepted`、`ready`、`PASS`、`scenario_success`。✅

---

### C05 — implementation artifact 与实际控制流不一致

**验证结果: FIXED / PASS**

证据链：

1. SHA-256 与 review-fix artifact 完全一致（见上表）。

2. Implementation artifact 描述的真实 safe-stop/independent-evidence/index 行为与实际代码一致。

3. `git diff --check` 无 whitespace 错误。

4. 禁改面审计：
   - `dayu/host/durable/run_transition.py` — **0 行 diff**
   - `dayu/config/prompts/` — **0 行 diff**
   - `validate_previous_compacted_view_pair()` — **0 行 diff**
   - `compacted_source_refs` — **0 行 diff**
   - oracle/scenario files — **未出现在 diff 中** ✅

---

## F14 frontier / validator / oracle / scenario zero drift

**验证结果: PASS**

- `compacted_source_refs`: zero diff in `compact_material.py` ✅
- `validate_previous_compacted_view_pair()`: zero diff in `compaction.py` ✅
- Oracle/scenario registry/predicate/expected behavior: zero diff ✅
- Prompts: zero diff ✅
- Engine contract: zero diff ✅
- CLI public surface: zero diff ✅

---

## Whitespace / no-renumber 验证

**验证结果: PASS**

1. `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact` 中 P3/P4 labels 精确断言不 skip、不 renumber：
   - Line 2233-2234: `"P3"`, `"P4"` labels
   - Line 2236: `block.block_label for block in answer_blocks) == ("P3", "P4")`

2. `_readable_answer_anchor_from_canonical()` 使用显式 `index` 参数生成 label。

3. `_canonical_previous_replacement_projection()` 不修改 answer_anchors 顺序/数量。

---

## 测试运行结果

| Suite | Result |
|---|---|
| F15/F16 focused（compact + context + cli observation） | **216 passed** |
| C01-C04 关键 evidence tests | **10 passed**（evidence 三态、safe-stop、session、terminal projection、ordinal/role） |
| Terminal producer exact reason nodes | **6 passed**（验证时不单独重跑，implementation artifact 已记录） |
| pyright `utils/cli_ci_run_observation.py` | **0 errors, 0 warnings** |
| pyright `tests/cli/test_cli_ci_run_observation.py` | **0 errors, 0 warnings** |
| pyright `workspace/tmp/prompt_observe_calibration.py` | **0 errors, 0 warnings** |
| pyright `workspace/tmp/f14_real_cli_observation.py` | **0 errors, 0 warnings** |

---

## 反例验证（本复读构造）

| 反例 | 预期 | 实际 |
|---|---|---|
| safe-stop 无 EOT action | ValueError | ✅ `"remaining actions must include explicit cleanup/EOT"` |
| safe-stop 仅 dependent action | ValueError | ✅ 同上 |
| independent action 带 upstream ordinal | ValueError | ✅ `"non-dependent action must not declare upstream ordinal"` |
| required action 带 upstream ordinal | ValueError | ✅ 同上 |
| dependent action 无 upstream ordinal | ValueError | ✅ `"dependent action must declare upstream ordinal"` |
| CLEANUP_EOT 投影为 Run role | ValueError | ✅ `"cleanup/EOT does not have Run observation role"` |
| FAILED → evidence COMPLETE | 为 INSUFFICIENT | ✅ `is not RunEvidenceStatus.COMPLETE` |
| CANCELLED → evidence COMPLETE | 为 INSUFFICIENT | ✅ |
| LOST → evidence COMPLETE | 为 INSUFFICIENT | ✅ |
| (SUCCEEDED, FAILED) → COMPLETE | 为 INSUFFICIENT | ✅ |
| None → evidence status | INVALID | ✅ |
| () → evidence status | INVALID | ✅ |

---

## 未覆盖项 / residual risks

- **assigned to subsequent clean-target validation gate**: 未执行真实 provider/AAPL fresh rerun、未产生本次真实 public bundle 或运行时 secret-scan 实例；当前用户禁止 commit，accepted plan 要求 real rerun 只针对 clean committed target。
- **covered by deterministic suite**: F15 strict pair、accepted tool exact path、durable reopen、ordinary candidate freeze/dispatch、terminal producer reason、evidence 三态、safe-stop pure control、session identity、shared projector reuse。
- **F14 harness 未在本机实际运行**: temporary harness 的 py_compile + pyright 通过，但依赖实际 CLI CI workspace 的端到端行为（segment chain、evidence 写入、index 生成）由 deterministic tests 间接覆盖。

---

## 最终裁决

**所有 11 项 finding 均已关闭：**

| Finding | 状态 |
|---|---|
| MiMo 001 — invalid 崩溃 | ✅ FIXED |
| MiMo 002 — index 字段不完整 | ✅ FIXED |
| MiMo 003 — INDEPENDENT 枚举 | ✅ REJECTED-WITH-REASON / CONTRACT 加固 |
| DS 016 — block 构造重复 | ✅ FIXED（typed wrappers） |
| DS 017 — whitespace test 缺口 | ✅ FIXED |
| DS 018 — 隐式 ordinal +1 | ✅ FIXED |
| C01 — PTY 永久等待 | ✅ FIXED |
| C02 — valid failure 误标 complete | ✅ FIXED |
| C03 — session/projector 不同源 | ✅ FIXED |
| C04 — adjudication 状态值 | ✅ FIXED |
| C05 — artifact / SHA 不一致 | ✅ FIXED |

**无新增 finding。**

## Review conclusion

**PASS** — 无新增 finding 且所有旧 finding 均已关闭。

F15 canonical single projection：五区文本叶子经唯一 `_canonical_previous_replacement_projection()` 规范化，packed blocks 与 readable view 消费同一 canonical atoms，answer anchor 先构造 typed anchor 再正向渲染，accepted tool evidence 保留 exact renderer path 且由 typed wrapper 区分，strict validator 未放宽。

F16 tracked helper：filtered keyset window、canonical reason 唯一读取 `reason_json.reason`、event-specific shape validation、session identity 校验、shared lifecycle projector 复用、evidence 三态精确区分、safe-stop pure control 只发一次 EOT。

F14 frontier / validator / oracle / scenario：zero drift。

Implementation artifact SHA-256 与实际源码一致，控制流描述与代码一致。

Residual risks 限于 clean-target real rerun（由 accepted plan 明确分配给 subsequent post-commit validation gate），不在本 re-review gate 范围内。
