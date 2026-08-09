# PR190 F15/F16 最终 Adversarial Re-Review Gate（DeepSeek 独立）

## Gate / scope

- Gate: final adversarial re-review gate（Controller 裁决 review-fix 后，commit/PR 前最后一道独立审查）。
- Branch / base: `codex/interactive-oracle` / `580b1427`。
- 本复读只审查，严禁编辑、commit、push 或 PR 操作。
- 之前 re-review（`pr-190-f15-f16-implementation-rereview-ds-20260807.md`、`pr-190-f15-f16-implementation-rereview-mimo-20260807.md`）是 A-D 修复前的过期证据；本次从最新 tracked diff + ignored harness 独立出发，不依赖那两份 re-review 的结论。

## Binding artifacts（全部完整读取）

- `AGENTS.md`
- `docs/gateflow/pr-190-f15-f16-plan-acceptance-20260807.md`（plan）
- `docs/gateflow/pr-190-f15-f16-implementation-20260807.md`（implementation）
- `docs/gateflow/pr-190-f15-f16-implementation-review-adjudication-20260807.md`（Controller adjudication）
- `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md`（review-fix）
- `docs/reviews/pr-190-f15-f16-implementation-review-ds-20260807.md`（初始 DS review）
- `docs/reviews/pr-190-f15-f16-implementation-review-mimo-20260807.md`（初始 MiMo review）
- `docs/reviews/pr-190-f15-f16-implementation-rereview-ds-20260807.md`（过期 re-review，仅作背景参考）
- `docs/reviews/pr-190-f15-f16-implementation-rereview-mimo-20260807.md`（过期 re-review，仅作背景参考）

## 审查范围

- Tracked diff: 11 files（`dayu/host/compact_material.py` 为首）+ `utils/cli_ci_run_observation.py` 新增。
- 两个 ignored temporary harness：
  - `workspace/tmp/prompt_observe_calibration.py`
  - `workspace/tmp/f14_real_cli_observation.py`
- Focused tests:
  - `tests/host/test_compact_material.py`
  - `tests/host/test_context_compact_events.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `tests/host/test_active_cancel_dispatch.py`
  - `tests/host/test_run_attempt_transitions.py`
  - `tests/host/test_wait_cancel_late_result.py`
  - `tests/cli/test_cli_ci_run_observation.py`
- 禁改面审计：`dayu/host/durable/run_transition.py`、`dayu/host/compaction.py`（validator）、F14 `compacted_source_refs` 实现、oracle/scenario files、prompts、Engine。

## Pre-review baseline verification

| 检查项 | 结果 |
|---|---|
| `git diff --check` | PASS |
| `run_transition.py` diff | **0 lines** |
| `compaction.py` validator diff | **0 lines** |
| F14 `compacted_source_refs` 实现 diff | **0 lines**（文档中仅描述性约束，非实现改动） |
| oracle/scenario files diff | **0 lines** |
| prompts diff | **0 lines** |
| Engine diff | **0 lines** |
| `lifecycle_events.py` diff | **0 lines** |
| `CancelMode` enum diff | **0 lines** |
| Tracked helper SHA-256 | `92266b6869d8bcb76326803d8c7f9c5703145b66044e6b2f65851e5babd12d13` ✅（与 review-fix artifact 一致） |
| Prompt harness SHA-256 | `6d544413af1038cdf7b67a82b6647fddd63d3408d9895dc6754d8684739d4be1` ✅ |
| F14 harness SHA-256 | `c54b9b4e3e9d9145eb9dbbe4d1e30c729fd0fc7394a5a12d1914d7d11c66691a` ✅ |

## 测试与类型检查

| Suite | Result |
|---|---|
| 全量 affected tests（7 文件） | **450 passed** |
| F16 helper focused tests | **27 passed** |
| pyright `dayu/ tests/ utils/` | **0 errors, 0 warnings** |
| pyright ignored harness（2 文件） | **0 errors, 0 warnings** |
| `py_compile` ignored harness（2 文件） | PASS |

---

## F15 Adversarial Challenge：Canonical Renderer 反例验证

### 1. accepted tool evidence 是否被错误归一化？

**入口**: `run_input_material_block()` (`compact_material.py:1047-1051`) → `_accepted_tool_evidence_text()` (`:893-911`)

**证据链**:

1. `run_input_material_block()` 在 `accepted_tool_evidence is not None` 时走 `_accepted_tool_evidence_text(text, accepted_tool_evidence)`，返回 `_AcceptedToolEvidenceText` — **不经过 `normalized_material_text()`**。
2. `_accepted_tool_evidence_text()` 调用 `render_accepted_tool_evidence_for_llm()` 做 shared renderer exact 校验（`:907`），不调用任何 normalizer。
3. `_canonical_previous_replacement_projection()` 仅处理 `CompactAcceptedReplacementV4` 的 previous-view 文本叶子，**不含且不引用 accepted_tool_evidence 字段**。
4. 两条路径在 `_run_input_material_block_from_prepared_text()` 中以 `isinstance(text, _AcceptedToolEvidenceText)` vs `isinstance(text, _CanonicalMaterialText)` 显式区分，accepted evidence 分支要求 `accepted_tool_evidence is not None`，canonical 分支禁止携带 `accepted_tool_evidence`（`:914-922`）。

**反例构造**: 不存在将 accepted tool evidence raw text 传入 `_canonical_material_text()` / `normalized_material_text()` 的任何代码路径。

**裁决**: **PASS** — accepted tool evidence 保留 exact renderer 路径，不被 canonical normalizer 改写。

---

### 2. anchor ordinal 是否跳号？

**入口**: `_previous_compacted_view_pair_from_replacement()` (`:2618-2692`) → `_pack_previous_blocks()` (`:3377-3387`)

**证据链**:

1. `_previous_compacted_view_pair_from_replacement()` 按固定顺序追加 blocks：session_summary → evidence_facts → answer_anchors → forward_intents → references。每个 block 的 `event_sub_index` 使用 `len(blocks)` 在当前追加时的实时值，确保同 event 内子序严格递增。
2. `_pack_previous_blocks()` 从 `_FIRST_ORDINAL (1)` 开始 enumerate，block label 为 `P{ordinal}`。
3. 测试 `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact` 断言两个 answer anchor 的 label 分别为 `P3` 和 `P4`（前有 P1=session_summary, P2=evidence_fact），无跳号（`:2233-2236`）。

**反例构造**: 若 future 重构改变了五区追加顺序，label 编号会随之变化，但 numbering 本身是确定性的 enumerate，不会跳号。当前实现无任何 `continue`/`skip`/条件跳过逻辑。

**裁决**: **PASS** — anchor ordinal 由 `enumerate(blocks, start=1)` 确定性分配，无跳号。

---

### 3. 多 section 是否双投影（packed + readable 不同源）？

**入口**: `_canonical_previous_replacement_projection()` (`:2696-2745`) → `_previous_compacted_view_pair_from_replacement()` (`:2618-2692`)

**证据链**:

1. `_canonical_previous_replacement_projection(replacement)` 在 `_previous_compacted_view_pair_from_replacement` 开头**恰好调用一次**（`:2618`）。
2. 返回值 `projection` 被以下两方共同消费：
   - **Packed blocks**: `projection.session_summary` → `_previous_block_from_canonical_text()`（`:2622-2630`）、`projection.evidence_facts`、`projection.answer_anchors`、`projection.forward_intents`、`projection.references`。
   - **Readable view**: `_readable_previous_view_from_canonical_projection(projection, ...)`（`:2686`），直接读取 `projection.session_summary.value`、`fact.claim.value`、`intent.text.value` 等。
3. 两个消费方从同一 `projection` 对象的同一字段取值，不存在第二份规范化或独立文本投影。
4. 测试 `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact` 断言 packed block text 与 `previous_answer_anchor_block_text(ReadableAnswerAnchorVNext(...))` 渲染结果 exact 一致（`:2188-2191`），且 durable reopen 后 `reopened_readable.to_json() == readable.to_json()`（`:2133`）。

**裁决**: **PASS** — 五区文本叶子经唯一 canonical projection 规范化一次，packed 与 readable 消费同一 atoms。

---

### 4. durable reload 后是否不一致？

**入口**: `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact` reopen 段（`test_compact_material.py:2110-2143`）

**证据链**:

1. 第一段在 writable store 构造数据并读取 view。
2. 关闭 store 后通过 `open_host_durable_read_store(...)` 物理只读 reopen，重新执行 `build_pre_dispatch_compact_material_view()`。
3. 断言 `reopened_readable.to_json() == readable.to_json()`（完整 JSON exact 相等）。
4. 断言 `(block.text, block.size_units, block.content_digest)` 每个 block 均 byte-exact 相等。
5. 该过程不复用首次构造的任何 Python 对象，完全从 durable accepted event/artifact 重新读取并构造 pair。

**裁决**: **PASS** — durable reopen 后 previous pair byte-exact 一致。

---

### 5. 下一 ordinary Run freeze 是否失败？

**入口**: `test_durable_reopen_previous_pair_freezes_and_dispatches_next_ordinary_run`（`test_dispatch_scheduler.py:9031-9098`）

**证据链**:

1. 第一段 writable store 通过 `_append_previous_compacted_event` 持久化含格式矩阵的 accepted pair，并用 `_seed_accepted_run` 创建下一 ordinary `ACCEPTED` Run。
2. 关闭后由新的 writable store / scheduler 执行 `run_queue_promotion` → `prepare_runner_call_candidate_in_transaction` → `record_prepared_runner_call_candidate_in_transaction` → governed start → worker `accept`。
3. 测试断言 `frozen_source.candidate.messages == accepted_request.messages` exact 相等（`:9092`）。
4. 断言 `frozen_source.candidate.run_id == seeded.run_id`、`session_id` 同源（`:9090-9091`）。
5. 断言 Run 真实收口为 `SUCCEEDED`（`:9073-9076`）。

**裁决**: **PASS** — durable reopen 后下一 ordinary Run 正常 freeze 并 dispatch 到 worker。

---

### 6. F14 frontier 是否漂移？

**入口**: `git diff 580b1427` 全域审计

**证据链**:

- `compacted_source_refs` 实现: **0 lines diff**。
- `validate_previous_compacted_view_pair()`: **0 lines diff**。
- `run_transition.py`: **0 lines diff**。
- oracle/scenario files、prompts、Engine: **0 lines diff**。
- 文档中出现的 `compacted_source_refs` 均为描述性约束声明（`dayu/host/README.md:10`、`docs/host/design.md:767`），不修改 frontier 实现。

**裁决**: **PASS** — F14 frontier zero drift。

---

## F16 Adversarial Challenge：Terminal Observation 反例验证

### 7. accepted/terminal session identity 与 canonical reason shape

**入口**: `_project_terminal_rows()` (`utils/cli_ci_run_observation.py:909-988`) → `_terminal_reason()` (`:1031-1087`)

**证据链**:

1. **Session identity**: `terminal.session_id != accepted.session_id` → `RunObservationError("Run terminal session_id does not match RUN_ACCEPTED")`（`:959-962`）。测试 `test_terminal_session_must_match_accepted_session` 构造跨 session terminal → `RunObservationError(match="session_id")`。
2. **Reason 唯一源**: `_terminal_reason()` 仅读取 `row.reason_json` → `json.loads()` → `decoded[_REASON_KEY]`。不读取 `row.payload_json`、`host_runs` 表、日志文本或文件时间戳。
3. **Event-specific shapes**:
   - `RUN_SUCCEEDED` / `RUN_FAILED`: exact `{"reason": <non-empty str>}`（`:1080-1082`）
   - `RUN_CANCELLED`: `{reason}` 或 `{reason, mode}`；`mode` 必须属于 `CancelMode` 枚举（`:1053-1065`）
   - `RUN_LOST`: `{reason}` 或 `{reason, orphan_proof}`；`orphan_proof` 必须为非空 str（`:1066-1079`）
4. 测试覆盖: `test_terminal_reason_rejects_missing_extra_blank_or_wrong_typed_object`（6 参数化反例）、`test_cancel_and_lost_reason_shapes_reject_unknown_or_invalid_extras`（4 参数化反例）、`test_terminal_reason_rejects_malformed_json`。

**裁决**: **PASS** — session 强一致校验，reason 唯一读取 `reason_json.reason`，event-specific shape fail closed。

---

### 8. RUN_FAILED / CANCELLED / LOST 三态完整性

**入口**: `_project_terminal_rows()` terminal class assignment（`:979`）→ `_terminal_status()` (`:1017-1028`) → lifecycle owner `run_status_for_terminal_event()`

**证据链**:

1. Terminal class 复用 lifecycle owner `run_status_for_terminal_event()`（`:1025`），不手写映射。
2. 非 terminal enum → `RunObservationError`（`:1026-1028`）。
3. Public-outbox membership 复用 `is_public_outbox_terminal_item_event()`（`:981-983`），`RUN_LOST` → `False`，其余三态 → `True`。
4. 测试 `test_terminal_projection_keeps_each_canonical_terminal_and_reason` 精确断言四类 terminal event type、四类 `RunStatus`、四个 `public_outbox_terminal` 布尔序列 = `(True, True, True, False)`（`:140-158`）。

**裁决**: **PASS** — 三态由 lifecycle owner 统一投影，LOST 独立且 `public_outbox_terminal=False`。

---

### 9. summary / per-Run exact distribution

**入口**: `validate_terminal_class_summary()` (`:627-681`)

**证据链**:

1. 对 `accepted` 总数及 `succeeded/failed/cancelled/lost` 四类 per-Run 分布**逐类 exact 对账**（`:669-681`）。
2. `len(terminal_statuses) != accepted` → `RunObservationError`（`:674-677`）。
3. `observed != summary`（字典逐类对比）→ `RunObservationError`（`:678-681`）。
4. 测试 `test_terminal_class_summary_requires_exact_per_run_distribution` 覆盖合法四类矩阵与"总数相同但 failed/lost 分布矛盾"反例（`:751-784`）。

**裁决**: **PASS** — summary 逐类 exact 对账 per-Run records。

---

### 10. invalid unknown = null（不靠字符串推断）

**证据链**（来源：review-fix artifact + 源码审计）:

1. 已删除全部 `"missing"/"duplicate" in diagnostics` 字符串 heuristic。
2. Invalid observation 的 summary 中 `accepted/succeeded/failed/cancelled/lost/missing/invalid` 均为 `null`，仅 `invalid=1` 确定。
3. Diagnostics 原样保留，不从中反推计数。
4. `_segment_terminal_facts()` 对所有异常路径返回 `SegmentTerminalFacts(evidence_status=RunEvidenceStatus.INVALID, ...)`，保留 typed diagnostics，不抛异常。

**裁决**: **PASS** — invalid unknown 为 typed `null`，不从 diagnostic 字符串反推。

---

### 11. dependency stopped / not_run 与 single EOT / 10s cleanup

**入口**: `evaluate_success_dependency()` (`:501-555`) + `classify_remaining_actions_for_safe_stop()` (`:817-864`)

**证据链**:

1. **Dependency gate**: 仅 `terminal_class is SUCCEEDED` → `PROCEEDED`；`FAILED/CANCELLED/LOST` → `STOPPED`（`:546-550`）。Ordinal 不匹配 → `INVALID`（`:537-544`）。`None` + deadline 未到 → `PENDING`，deadline 已到 → `INVALID`（`:523-534`）。
2. **Safe stop**: `classify_remaining_actions_for_safe_stop()` 中所有 DEPENDENT → `NOT_RUN_DEPENDENT`；第一个 CLEANUP_EOT → `SEND_CLEANUP_EOT`；后续 CLEANUP_EOT / non-dependent → `NOT_RUN_PROCESS_STOP`。无 EOT → `ValueError`。
3. 测试 `test_safe_stop_classifies_dependents_and_sends_one_cleanup_eot` 断言 2 dependent → NOT_RUN_DEPENDENT + 1st EOT → SEND + 2nd EOT → NOT_RUN_PROCESS_STOP（`:566-587`）。
4. PTY harness 在 safe stop 后设置 10s cleanup deadline，不发送依赖输入，不等待不存在的 terminal count。

**裁决**: **PASS** — dependency stop 后 not_run 全覆盖、仅一次 EOT、10s cleanup。

---

### 12. process exit 不推导 scenario verdict

**入口**: `evaluate_success_dependency()` (`:501-555`)

**证据链**:

1. `evaluate_success_dependency()` 的**所有参数**: `observation: RunTerminalObservation | None`、`required_success_accepted_ordinal: int`、`deadline_reached: bool`。**不含** `exit_code`、`process_outcome`、`timed_out` 或任何 process 相关参数。
2. 决策仅基于 `observation.terminal_class`（`:548`），不读取 process 状态。
3. 测试 `test_process_exit_zero_does_not_satisfy_failed_run_dependency`：`exit_code=0` + `RUN_FAILED` → `STOPPED`，不因 process exit 0 而 proceed（`:437-495`）。

**裁决**: **PASS** — process exit 不进入 dependency gate，不推导 scenario verdict。

---

### 13. formal unadjudicated

**入口**: `f14_real_cli_observation.py` index construction

**证据链**:

1. `execution-index-f15-f16.json` 中 `"oracle_status": "unadjudicated"`（`:1468`）。
2. Scenario rows 中 `"scenario_status": "unadjudicated"`（`:1300`）。
3. 全文搜索无 `pending_user_adjudication`、`accepted`、`ready`、`PASS`、`scenario_success` 字段。

**裁决**: **PASS** — formal adjudication 状态精确为 `unadjudicated`。

---

## A-D Controller Follow-Up 反例验证

### A: 普通本机路径是否被当作 secret？

**入口**: `scan_public_evidence_files()` (`utils/cli_ci_run_observation.py:684-814`)
**测试**: `test_public_scan_does_not_treat_ordinary_local_paths_as_secrets`

**反例构造与验证**:

1. 构造 `command.json` 包含真实 repo 路径 `"/Users/leo/workspace/dayu-agent-r"` 与 corpus 路径 `"/Users/leo/workspace/.dayu-cli-ci/corpus"`。
2. Exact secret probe 仅包含 fixture 值 `"fixture-secret-value"`。
3. 扫描结果: `status: "complete"`，`secret_hits: []`，`path_hygiene_violations: []`。✅

**裁决**: **PASS** — repo/run/corpus 普通路径不触发 secret invalid。

---

### B: actual secret exact value 是否被检测？

**入口**: `scan_public_evidence_files()` (`:794-802`)
**测试**: `test_public_scan_detects_injected_exact_secret`

**反例构造与验证**:

1. 构造 `public.json` 内容 `'{"accidental":"fixture-secret-value"}'`。
2. Exact probe `PublicEvidenceSecretProbe("provider_api_key", "fixture-secret-value")`。
3. 扫描结果: `status: "invalid"`，`secret_scan.hits[0] = {"path": "public.json", "match_kind": "exact_value", "probe": "provider_api_key"}`。✅

**裁决**: **PASS** — actual secret exact value 命中 → invalid。

---

### C: raw DB 文件/路径/symlink 是否被检测？

**入口**: `scan_public_evidence_files()` (`:759-806`)
**测试**: `test_public_path_hygiene_detects_raw_database_and_symlink`

**反例构造与验证**:

1. 构造 `host.sqlite3` 文件 → `raw_database_file_forbidden`。
2. 构造 `manifest.json` 内含 `"raw_store":"/private/tmp/dayu/host.db"` 文本路径 → `raw_database_path_forbidden`。
3. 构造 symlink `linked.json → path_record` → `symlink_forbidden`。
4. 三种 violation reason 同时存在: `{"raw_database_file_forbidden", "raw_database_path_forbidden", "symlink_forbidden"}`。✅

**裁决**: **PASS** — raw DB 文件、文本 DB 路径、symlink 全部 fail closed。

---

### D: scope escape / missing / oversize 是否 fail closed？

**入口**: `scan_public_evidence_files()` (`:731-783`)

**证据链**:

1. `outside_evidence_root`: 文件 `relative_to(root)` 抛出 `ValueError` → path violation（`:733-738`）。
2. `regular_file_missing`: `candidate.is_file()` 为 False → validation error（`:764-768`）。
3. `file_size_limit_exceeded`: `size > max_file_bytes` → validation error（`:771-775`）。
4. 所有 violation/error 均保留 typed reason，不静默跳过。

**裁决**: **PASS** — scope escape、missing、oversize 全部 fail closed。

---

### E: final index 是否只引用 scan-derived truth？

**入口**: `PublicEvidenceScanResult.to_json()` (`:111-141`)

**证据链**:

1. Index 中 `secret_scan.status/hits` 仅来源于 exact probe 扫描事实。
2. `path_hygiene.status/violations` 仅来源于 path hygiene 扫描事实。
3. `validation_errors` 仅来源于文件读取/校验事实。
4. 无硬编码 `raw_host_sqlite* = false` 字段（已删除）。
5. `status: "complete"` 仅在 `not (secret_hits or path_hygiene_violations or validation_errors)` 时成立。

**裁决**: **PASS** — final index 仅引用 scan-derived truth，扫描完整 public evidence tree。

---

## 旧 Finding 关闭状态确认

| Finding | 状态 | 本次独立验证 |
|---|---|---|
| MiMo 001 — segment evidence invalid 崩溃 | FIXED | typed inspection + fallback → INVALID 保留 diagnostics ✅ |
| MiMo 002 — index 字段不完整 | FIXED | 完整 process/terminal/dependency/compaction/secret-scan facts ✅ |
| MiMo 003 — INDEPENDENT 枚举 | REJECTED-WITH-REASON / CONTRACT 加固 | role 保留 + pure projector + cleanup 不可伪装 Run ✅ |
| DS 016 — block 构造重复 | FIXED | typed wrappers + union → 唯一 low-level constructor ✅ |
| DS 017 — whitespace test 缺口 | FIXED | typed accept + strict read + anchor P3/P4 exact 断言 ✅ |
| DS 018 — 隐式 ordinal +1 | FIXED | `dependent_action_accepted_ordinal()` typed pure helper ✅ |
| C01 — PTY 永久等待 | FIXED | safe-stop pure control + 单 EOT + 10s cleanup ✅ |
| C02 — valid failure 误标 complete | FIXED | evidence 三态 classifier + insufficient ≠ complete ✅ |
| C03 — session/projector 不同源 | FIXED | session identity + lifecycle owner + public-outbox projector ✅ |
| C04 — adjudication 状态值 | FIXED | `"unadjudicated"` exact ✅ |
| C05 — artifact / SHA 不一致 | FIXED | SHA-256 与实际源码一致 ✅ |
| A — 普通路径当 secret | FIXED | exact probes 仅含实际 secret 值 ✅ |
| B — diagnostic 字符串推断 | FIXED | 删除 heuristic，invalid 用 null ✅ |
| C — summary 仅校验总数 | FIXED | `validate_terminal_class_summary()` 逐类 exact 对账 ✅ |
| D — raw DB 硬编码 false | FIXED | path hygiene 扫描实际文件系统 ✅ |

---

## Open Questions

无。

## Residual Risk

1. **Fresh production real rerun 未执行**: Accepted plan 要求 clean committed target 上执行真实 provider/AAPL rerun。当前未 commit，因此 rerun 未启动。这是 plan 明确分配给 subsequent post-commit validation gate 的工作。
2. **F14 harness 端到端行为**: temporary harness 的 `py_compile` + pyright 通过，但依赖实际 CLI CI workspace 的端到端行为（segment chain、evidence 写入、index 生成）由 deterministic tests 间接覆盖，非实际 workspace 运行。
3. **Format matrix 显式断言集中在 answer anchor**: Summary/fact/intent/reference 的 exact 文本通过 `reopened_readable.to_json() == readable.to_json()` 间接覆盖，显式逐 section 文本断言不如 anchor 细致。风险可控（所有 section 共享同一 normalizer）。

---

## 最终裁决

**PASS** — 无新增 finding。

所有 16 项旧 finding 均已关闭。F15 canonical single projection 正确实现：五区文本叶子经唯一 `_canonical_previous_replacement_projection()` 规范化一次，packed blocks 与 readable view 消费同一 canonical atoms，accepted tool evidence 保留 exact renderer 路径且与 canonical normalizer 完全隔离，answer anchor 先构造 typed anchor 再正向渲染，strict validator 未放宽，durable reopen byte-exact 一致，下一 ordinary Run 正常 freeze 并 dispatch。

F16 tracked helper 正确实现：filtered keyset window 读尽 frozen window，canonical reason 唯一读取 `reason_json.reason`，event-specific shape validation fail closed，session identity 强一致校验，shared lifecycle projector 复用，evidence 三态精确区分（complete/insufficient/invalid），safe-stop pure control 只发一次 EOT 且记录全部 dependent not_run，process exit 不进入 dependency gate。

A-D 全部反例验证通过：普通路径不触发 secret invalid，actual secret 命中 invalid，raw DB 文件/路径/symlink 全部 fail closed，scope escape/missing/oversize fail closed，final index 仅引用 scan-derived truth。

F14 frontier / validator / oracle / scenario / prompt / Engine: zero drift。

450 tests passed，pyright 0 errors，`git diff --check` clean，SHA-256 digests 一致。
