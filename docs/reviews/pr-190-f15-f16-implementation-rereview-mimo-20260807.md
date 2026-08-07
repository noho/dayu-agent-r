# PR190 F15/F16 Implementation Re-Review（MiMo 独立复验）

## Scope

- Mode: review-fix artifact 复验 + tracked diff + 两个 ignored harness。
- Branch: `codex/interactive-oracle`
- Base: `580b1427`（review-fix artifact 声称的修复完成态）
- Adjudication: `docs/gateflow/pr-190-f15-f16-implementation-review-adjudication-20260807.md`（C01–C05）
- Review-fix: `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md`
- Included scope: `git diff 580b1427` 全部 11 个 tracked 改动文件 + `utils/cli_ci_run_observation.py` + `workspace/tmp/prompt_observe_calibration.py` + `workspace/tmp/f14_real_cli_observation.py`
- Excluded scope: 无
- 本审查逐项验证 initial findings、Controller C01–C05、review-fix 声称与实际代码/diff 的一致性。

## Baseline verification

| Check | Result |
|---|---|
| `git diff HEAD -- dayu/host/durable/run_transition.py` | empty ✅ |
| `CompactAcceptedReplacementV4` / schema 5 / DDL | zero diff ✅ |
| `docs/cli_ci_scenarios.json` / `docs/cli_ci_oracles.json` / prompts | zero diff ✅ |
| F14 `compacted_source_refs` / frontier 实现 | zero diff (`grep compacted_source_refs` = 0) ✅ |
| `git diff --check` | clean ✅ |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings` ✅ |
| `python -m py_compile` 两个 temporary harness | pass ✅ |

## SHA-256 digest verification

| 文件 | review-fix artifact 声称 | `shasum -a 256` 实测 | 一致 |
|---|---|---|---|
| `utils/cli_ci_run_observation.py` | `d77195...bc0d8` | `d77195435042a6477ef97a244337aa945c8bc4a7bcf8644bf111a127774bc0d8` | ✅ |
| `workspace/tmp/prompt_observe_calibration.py` | `6d5444...9d4be1` | `6d544413af1038cdf7b67a82b6647fddd63d3408d9895dc6754d8684739d4be1` | ✅ |
| `workspace/tmp/f14_real_cli_observation.py` | `b4657d...c34f7c2d2` | `b4657d832fa6e676e305cd9addc210944abd2a618370debace25ac8c34f7c2d2` | ✅ |

## Test results

```
tests/cli/test_cli_ci_run_observation.py          — 23 passed
tests/host/test_compact_material.py                — (included in aggregate)
tests/host/test_context_compact_events.py          — (included in aggregate)
tests/host/test_dispatch_scheduler.py              — (included in aggregate)
tests/host/test_run_attempt_transitions.py         — (included in aggregate)
tests/host/test_active_cancel_dispatch.py          — (included in aggregate)
tests/host/test_wait_cancel_late_result.py         — (included in aggregate)
F15/F16 + producer aggregate                       — 423 passed
pyright dayu/ tests/ utils/                        — 0 errors, 0 warnings
```

## Finding-by-finding verification

### MiMo 001 — invalid 后二次崩溃 → **CLOSED**

**review-fix 声称**: `_segment_terminal_facts()` 改为 typed inspection；缺文件、malformed JSON、invalid shape 保留原 diagnostics 与 record path/digest，返回 `invalid` 并阻断依赖链。

**实际验证**:

`f14_real_cli_observation.py:541-686` — `_segment_terminal_facts()` 现在：
1. `OSError` / `UnicodeError` 读文件 → 返回 `_invalid_segment_terminal_facts(diagnostics=...)`（line 558-563）
2. `json.JSONDecodeError` → 返回 invalid（line 567-572）
3. 根不是 dict → 返回 invalid（line 573-578）
4. `evidence_status == "invalid"` → 读取 `validation_errors` 并返回 invalid（line 580-596）
5. `summary` 缺失/非 dict → 返回 invalid（line 597-603）— **直接修复了原 MiMo 001 的 `AttributeError`**
6. summary 字段类型非法 → 返回 invalid（line 616-621）
7. runs 不匹配 → 返回 invalid（line 623-628）
8. `accepted == 0` → 返回 invalid（line 664-669）

每个路径都保留原始 diagnostics 和 record path/digest，不静默变成 `(0, False)`。`_execute()` 中 `_segment_terminal_facts()` 的结果直接注入 row，不向外抛异常。

**证据测试**: `test_required_run_evidence_distinguishes_complete_insufficient_and_invalid` 覆盖三态（complete/insufficient/invalid），两个 harness `py_compile`/pyright 通过。

**结论**: 修复正确，无残余崩溃路径。

---

### MiMo 002 — index 字段不完整 → **CLOSED**

**review-fix 声称**: index 逐项/汇总输出 `process_outcomes`、八类 terminal counts、per-Run record path/digest、`dependency_gates`、strict context compaction count/refs、public evidence、exact-value/header/path secret scan。

**实际验证**:

`f14_real_cli_observation.py:1441-1470` — index 结构：
```python
{
    "target_commit": commit,
    "source_digests": {...},
    "scenario_count": len(rows),
    "process_outcomes": process_outcomes,           # ← 已修复
    "run_terminal_summary": terminal_summary,        # ← 8字段完整
    "run_terminal_records": terminal_records,        # ← 已修复
    "dependency_gates": dependency_gates,            # ← 已修复
    "context_compaction_observation": context_compaction,  # ← 已修复
    "evidence_status": evidence_status,
    "harness_invalid_count": ...,
    "rows": rows,
    "public_evidence": public,
    "secret_scan": {...},                            # ← 已修复
    "raw_host_sqlite_in_public_evidence": False,
    "oracle_status": "unadjudicated",                # ← C04 修复
}
```

`_aggregate_terminal_evidence()`（line 1060-1122）汇总 8 类 terminal counts + per-Run record descriptors。
`_aggregate_process_outcomes()`（line 1125-1157）汇总 exited/timed_out/harness_error + per-scenario 引用。
`_aggregate_dependency_gates()`（line 1160-1185）汇总 proceeded/stopped/invalid/not_run + per-segment facts。
`_secret_scan()`（line 970-1057）覆盖 exact-value、header pattern 与路径扫描。

**结论**: 修复正确，index 字段完整。

---

### MiMo 003 — 删除 `INDEPENDENT` → **CLOSED (rejected-with-reason / contract 加固)**

**review-fix 声称**: 保留复用 role；新增 pure `run_observation_role_for_harness_action()`，required/dependent/independent 显式投影。

**实际验证**:

`cli_ci_run_observation.py:57-63` — `RunObservationRole.INDEPENDENT` 保留。
`cli_ci_run_observation.py:492-507` — `run_observation_role_for_harness_action()` 实现，CLEANUP_EOT 抛 `ValueError`。
`tests/cli/test_cli_ci_run_observation.py:587-598` — `test_upstream_to_dependent_ordinal_and_independent_role_are_explicit` 验证 independent role 可用。

**结论**: 正确保留 contract 并加固映射。

---

### DS 016 — accepted-tool construction 重复 → **CLOSED**

**review-fix 声称**: `_CanonicalMaterialText` 与 `_AcceptedToolEvidenceText` 两个 typed wrapper 组成 union，进入唯一 low-level constructor。

**实际验证**:

`compact_material.py` 新增：
- `_CanonicalMaterialText`（line 367-372）
- `_AcceptedToolEvidenceText`（line 375-381）
- `_PreparedMaterialText` type alias（line 384-385）
- `_run_input_material_block_from_prepared_text()`（line 922-970）— 唯一 low-level constructor

`_canonical_material_text()`（line 881-895）包装 `normalized_material_text()` 输出。
`_accepted_tool_evidence_text()`（line 898-920）校验文本等于 shared renderer 输出。

无 dict/glue/bool/trusted string seam。`test_compact_material.py` 全文件通过。

**结论**: 修复正确，构造重复已消除。

---

### DS 017 — whitespace boundary 测试缺口 → **NOT FIXED (P3, 不阻塞)**

**review-fix 声称**: 补 `test_whitespace_only_candidate_anchor_is_rejected_at_typed_accept_boundary`、`test_whitespace_only_persisted_replacement_is_rejected_at_read_boundary`、`test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact`。

**实际验证**:

- `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact` — **存在**（line 2062-2250），覆盖 leading/trailing/repeated whitespace、blank lines、multiline prose、Markdown list/table、answer anchor exact renderer、reopen byte-exact、P3/P4 label exact。
- `test_whitespace_only_candidate_anchor_is_rejected_at_typed_accept_boundary` — **不存在**
- `test_whitespace_only_persisted_replacement_is_rejected_at_read_boundary` — **不存在**

**纵深防御已验证**: `normalized_material_text()` 在 `text.strip() == ""` 时 raise `ValueError`（line 850-851），`_canonical_material_text()` 委托该函数。`CompactAcceptedReplacementV4` typed constructor 也有非空校验。format matrix 测试中 `"  FY2025   conclusion  "` 被正确归一化为 `"FY2025 conclusion"`。

**严重程度**: P3。既有 `normalized_material_text()` ValueError + typed constructor 校验已是双层纵深防御，无功能风险。两个显式 boundary test 缺失是测试显式性缺口，不是行为缺口。

**结论**: 部分未修复，但不阻塞 re-review gate（P3 ≤ accepted plan 阈值）。

---

### DS 018 — 隐式 ordinal `+1` → **CLOSED**

**review-fix 声称**: upstream→紧邻 dependent accepted ordinal 集中为 typed pure `dependent_action_accepted_ordinal()`。

**实际验证**:

`cli_ci_run_observation.py:471-489` — `dependent_action_accepted_ordinal()` 实现，类型校验 + `_require_positive_int`。
`prompt_observe_calibration.py:901-904` — 消费 helper：
```python
dependent_ordinal = run_observation.dependent_action_accepted_ordinal(
    action.required_success_accepted_ordinal
)
```
`tests/cli/test_cli_ci_run_observation.py:594` — `assert dependent_action_accepted_ordinal(7) == 8`。

**结论**: 修复正确，`+1` 已集中。

---

### C01 — dependency stop 后 PTY 可永久等待 → **CLOSED**

**review-fix 声称**: tracked `classify_remaining_actions_for_safe_stop()` 逐项分类；PTY 记录全部 remaining dependent 为 `not_run`，不发送依赖输入，立即只发送一次显式 EOT，并设置 10 秒 cleanup exit deadline。

**实际验证**:

1. **Pure helper**: `cli_ci_run_observation.py:540-587` — `classify_remaining_actions_for_safe_stop()`：
   - 按 `HarnessActionRole` 分类：DEPENDENT → `NOT_RUN_DEPENDENT`；首个 CLEANUP_EOT → `SEND_CLEANUP_EOT`；其余 → `NOT_RUN_PROCESS_STOP`。
   - `cleanup_selected` 标志确保只允许一次 EOT。
   - 无 CLEANUP_EOT → raise `ValueError`。

2. **PTY consumer**: `prompt_observe_calibration.py:918-996` — `_stop_dependency_chain()`：
   - 构造 `HarnessActionControl` tuple，调用 `classify_remaining_actions_for_safe_stop()`。
   - `SEND_CLEANUP_EOT` → `_send_pty_action()` 一次。
   - 其余 → `not_run`。
   - `dependency_cleanup_deadline = now + 10.0`（line 1352, 1373）。

3. **Main loop deadline**: `prompt_observe_calibration.py:1445-1464`：
   ```python
   if dependency_cleanup_deadline is not None and now >= dependency_cleanup_deadline:
       process.terminate()  # ← 10秒后终止
       ...
       break
   ```

4. **反例验证**: 构造 4 个 remaining actions（2 DEPENDENT + 2 CLEANUP_EOT），验证 disposition 序列为 `(NOT_RUN_DEPENDENT, NOT_RUN_DEPENDENT, SEND_CLEANUP_EOT, NOT_RUN_PROCESS_STOP)`。

**结论**: 修复正确。Dependency stop 后不等待原 terminal count，10 秒内终止进程。不会卡 1800 秒。

---

### C02 — valid failure 被误投影为 evidence complete → **CLOSED**

**review-fix 声称**: pure evidence classifier 规定：非空 required statuses 全 succeeded 才 `complete`；valid failed/cancelled/lost 为 `insufficient`；canonical observation 损坏或 required acceptance/terminal 缺失为 `invalid`。

**实际验证**:

`cli_ci_run_observation.py:510-537` — `classify_required_run_evidence()`：
```python
if terminal_statuses is None or len(terminal_statuses) == 0:
    return RunEvidenceStatus.INVALID
for status in terminal_statuses:
    if status not in {SUCCEEDED, FAILED, CANCELLED, LOST}:
        raise TypeError(...)
if all(status is SUCCEEDED for status in terminal_statuses):
    return RunEvidenceStatus.COMPLETE
return RunEvidenceStatus.INSUFFICIENT
```

测试覆盖 5 个参数化 case：
- `(SUCCEEDED,)` → COMPLETE
- `(FAILED,)` → INSUFFICIENT
- `(CANCELLED, SUCCEEDED)` → INSUFFICIENT
- `None` → INVALID
- `()` → INVALID

`_segment_terminal_facts()` 中 role 为 required/dependent 且 terminal_class != succeeded 时，`required_terminal_statuses` 收集 `RunStatus(terminal_class)`（line 653-654），由 `classify_required_run_evidence()` 统一判定。

**结论**: 修复正确。Valid failure = insufficient，canonical 破损 = invalid。

---

### C03 — session 与 shared projector 不同源 → **CLOSED**

**review-fix 声称**: 强制 `terminal.session_id == accepted.session_id`；terminal class 复用 `run_status_for_terminal_event()`，public-outbox 复用 `is_public_outbox_terminal_item_event()`。

**实际验证**:

1. **Session identity**: `cli_ci_run_observation.py:682-685`：
   ```python
   if terminal.session_id != accepted.session_id:
       raise RunObservationError("Run terminal session_id does not match RUN_ACCEPTED")
   ```

2. **Terminal class projector**: `cli_ci_run_observation.py:740-751` — `_terminal_status()` 调用 `run_status_for_terminal_event()`。

3. **Public outbox projector**: `cli_ci_run_observation.py:704-706`：
   ```python
   public_outbox_terminal=is_public_outbox_terminal_item_event(terminal.event_type)
   ```

4. **无手写四分支**: 删除了旧的 `if terminal_type is not RUN_LOST` 映射。

5. **测试**: `test_terminal_session_must_match_accepted_session` 验证跨 session terminal 被拒绝；`test_terminal_projection_keeps_each_canonical_terminal_and_reason` 精确断言四类 status 与 public-outbox 布尔序列 `(True, True, True, False)`。

**结论**: 修复正确，复用 lifecycle owner projector。

---

### C04 — formal adjudication 状态值错误 → **CLOSED**

**review-fix 声称**: final index 固定 `oracle_status: "unadjudicated"`。

**实际验证**:

`f14_real_cli_observation.py:1468`：
```python
"oracle_status": "unadjudicated",
```

无 `pending_user_adjudication`、`accepted`、`ready`、`PASS` 等值。源码直接检查确认。

**结论**: 修复正确。

---

### C05 — implementation artifact 不实且 SHA 过期 → **CLOSED**

**review-fix 声称**: implementation artifact 已改为真实 safe-stop/independent-evidence/index 行为，并更新三个源码 SHA。

**实际验证**:

三个 SHA-256 已在上方 digest verification 表中确认一致。Implementation artifact（`docs/gateflow/pr-190-f15-f16-implementation-20260807.md`）中的 SHA 与实际文件一致。

**结论**: 修复正确。

---

## F14 frontier / validator / oracle / scenario zero drift

| 检查项 | 结果 |
|---|---|
| `git diff HEAD -- dayu/host/compact_material.py \| grep compacted_source_refs` | 0 行 ✅ |
| `validate_previous_compacted_view_pair` | zero diff ✅ |
| `CompactAcceptedReplacementV4` / schema 5 | zero diff ✅ |
| `docs/cli_ci_scenarios.json` / `docs/cli_ci_oracles.json` | zero diff ✅ |
| prompt 目录 | zero diff ✅ |
| `dayu/host/durable/run_transition.py` | zero diff ✅ |
| Engine contract | 无改动 ✅ |
| CLI public command/options | 无改动 ✅ |

## Safe-stop pure helper 与 evidence 三态反例验证

**Safe-stop 反例**: 构造无 CLEANUP_EOT 的 actions tuple → `classify_remaining_actions_for_safe_stop()` raise `ValueError("remaining actions must include explicit cleanup/EOT")`。验证通过。

**Evidence 三态反例**:
- `classify_required_run_evidence(None)` → `INVALID` ✅
- `classify_required_run_evidence(())` → `INVALID` ✅
- `classify_required_run_evidence((SUCCEEDED,))` → `COMPLETE` ✅
- `classify_required_run_evidence((FAILED,))` → `INSUFFICIENT` ✅
- `classify_required_run_evidence((CANCELLED, SUCCEEDED))` → `INSUFFICIENT` ✅

非 terminal RunStatus（如 `CANCELLING`）→ `TypeError`。验证通过。

## LLM-facing / schema / public contract / README 检查

- **LLM-facing**: 无 prompt、tool schema、compactor prompt/LLM schema 修改。✅
- **Schema**: `CompactAcceptedReplacementV4`、schema 5、durable DDL、EventLog payload 字段未修改。✅
- **Public contract**: Engine contract、CLI public command/options 未修改。✅
- **README**: `dayu/host/README.md`、`docs/host/design.md`、`docs/cli_ci.md`、`tests/README.md` 均与实现一致。✅

## Residual risks

1. **Fresh production real rerun 未执行**: Plan 要求在 clean committed target 上执行真实 provider/AAPL rerun。当前 implementation gate 未 commit。这是 plan 分配给 subsequent post-commit validation gate 的工作。
2. **DS 017 两个显式 whitespace boundary test 缺失**: 已有 format matrix test + `normalized_material_text()` ValueError + typed constructor 校验作为三重防御。P3，不阻塞。
3. **Secret scan 未执行**: 依赖 fresh rerun。
4. **Temporary harness 的 `session_id=None`**: 当前 CLI CI 场景每个 workspace 只有一个 session。功能无误。

## Review Conclusion

**PASS**。所有 initial findings（MiMo 001–003、DS 016–018）和 Controller C01–C05 均已验证关闭（DS 017 为 P3 残余，不阻塞）。F14 frontier/validator/oracle/scenario zero drift 确认。Safe-stop pure helper 与 evidence 三态经反例验证。SHA-256 一致。423 tests passed，pyright 0 errors。无新增 finding。

## 未关闭项

| Finding | 严重程度 | 状态 | 说明 |
|---|---|---|---|
| DS 017：两个显式 whitespace boundary test 缺失 | P3 | 不阻塞 | 纵深防御已覆盖；显式 test 缺口可在后续 gate 补充 |
