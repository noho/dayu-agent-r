# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 第二路独立 Final Code Re-Review

## 1. Review Identity

- **Reviewer**: AgentDS（第二路独立 final re-review，与 MiMo 并发）
- **Umbrella**: `WU-SEMANTIC-OWNERSHIP-01`
- **Slice**: `R03-S1 — ordinary/awaiting shared request atom + durable replay identity`
- **Baseline**: `6e11d916`（`docs: resume R03 S1 implementation`）
- **Branch**: `phaseflow/host-issues-control`
- **Scope**: `6e11d916..working tree`（含 untracked `dayu/host/tool_call_request.py`）
- **Timestamp**: 2026-07-15 10:53 UTC+8
- **Output**: `docs/reviews/wu-semantic-ownership-01-r03-s1-code-rereview-ds.md`

## 2. Scope

### 2.1 Included scope（逐文件完整走读）

**Production（8 files + 1 new）**:
- `dayu/host/tool_call_request.py`（新增，shared writer）
- `dayu/host/tool_runtime.py`
- `dayu/host/waiting.py`
- `dayu/host/_event_payload.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/accepted_result_projection.py`
- `dayu/host/run_input.py`
- `dayu/host/durable/run_transition.py`

**Tests（9 files）**:
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_wait_awaiting_accept.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`

**Docs（2 files）**:
- `dayu/host/README.md`
- `tests/README.md`

**Reference documents（完整读取，read-only）**:
1. `AGENTS.md`
2. `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` §0–6, §13–16
3. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-mimo.md`
4. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-ds.md`
5. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-controller-adjudication.md`
6. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-fix-codex.md`
7. `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-fix-controller-validation.md`
8. `docs/reviews/wu-semantic-ownership-01-r03-s1-implementation-codex.md`
9. `docs/reviews/wu-semantic-ownership-01-r03-s1-controller-validation.md`
10. `docs/reviews/wu-semantic-ownership-01-r03-s1-controller-revalidation.md`
11. `docs/host/issues-implementation-control.md`（R03 gate entries）

### 2.2 Excluded scope

- S2（source blacklist / LLM source audit / schema 修正）— 属后续 slice
- S3（opaque refs internal-only propagation closure）— 属后续 slice
- Issue #177 / #178
- 统一 authorization framework

## 3. Independent Verification Results

### 3.1 Core Validation

| 验证项 | 结果 |
|---|---|
| 9-file S1 matrix | `389 passed in 2.61s` |
| Full Host | `1952 passed, 2 skipped, 5 deselected in 56.35s` |
| Transition owner suite | `77 passed`，`run_transition.py: 1375 statements / 281 missing / 80%` |
| Pyright（8 production files）| `0 errors, 0 warnings, 0 informations` |
| Ruff（8 production files）| `All checks passed!` |
| `git diff --check` | PASS |
| `tool_call_request.py` coverage | `105 statements / 5 missing / 95%`（目标 `>=95%`）|

### 3.2 Old Helper Deletion Closure

全仓 scan 确认以下 12 个旧 helper/常量/fallback 文案已完整删除（零命中）：

| Old helper / constant | 原位置 | 状态 |
|---|---|---|
| `llm_safe_replay_arguments` | `_event_payload.py` | 零命中 |
| `_tool_call_requested_event_id_from_wait_id` | `waiting.py` | 零命中 |
| `_validate_wait_request_arguments_digest` | `waiting.py` | 零命中 |
| `_awaiting_semantic_query_text` | `waiting.py` | 零命中 |
| `_resume_wait_fallback_message` | `run_input.py` | 零命中 |
| `_optional_event_id_from_payload_ref` | `run_input.py` | 零命中 |
| `_SYSTEM_SECTION_RESUME_GUIDANCE` | `run_input.py` | 零命中 |
| `_RESUME_GUIDANCE_PREFIX` | `run_input.py` | 零命中 |
| `_WAIT_CREATED_EVENT_REF` | `run_input.py` | 零命中 |
| `_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS` | `_event_payload.py` | 零命中 |
| `_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS_SOURCE_DIGEST` | `_event_payload.py` | 零命中 |
| `_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS`（`run_input.py` 副本）| `run_input.py` | 零命中 |

另确认以下删除为安全的静态卫生清理（全仓零命中、pyright/ruff 零错误）：
- `tool_runtime.py`: `duplicate_governance_key` import
- `run_transition.py`: `cancel_queued_run_row` import
- `run_input.py`: `build_memory_budget_diagnostic`、`estimate_memory_size_units` imports

### 3.3 S2/S3 Boundary Scan

确认 S1 diff 未 touch 以下 S2/S3 代码行（全属 baseline，未新增或修改）：
- `accepted_result_projection.py`: `_contains_unsafe_argument_key`（line 536）、`arguments_summary_unsafe` branch（line 523-525）、opaque ref 分类逻辑（line 634-663）
- `tool_trace.py`: `redact_sensitive_json_fields` import（line 81）、`_redacted_json`（line 1838）
- `compact_material.py` / `memory.py` / `run_input.py` / `accepted_result_projection.py`: `OpaqueEvidenceRef`、`source_locator_refs`、`canonical_source_refs` 等 S3 类型与字段 — 均为 baseline 既有，S1 未修改

### 3.4 Key Negative/Corruption Tests

| Test category | Count | Status |
|---|---|---|
| Broken awaiting request link（missing/wrong_shape/missing_row/wrong_type/sequence_mismatch）| 5 | all PASS |
| Execution identity mismatch transition（completed/failed）| 2 | all PASS |
| NOT_FOUND without mutation（missing_run/missing_wait）| 2 | all PASS |
| Consumer corruption（missing_request_atom / identity / digest mismatch）| 36 | all PASS |
| Atomic request atom reader corruption matrix（11 payload_patch variants + 5 descriptor corruption）| 16 | all PASS |
| Transaction rollback（request/awaiting/run_waiting/wait_record）| 3 | all PASS |
| Idempotent replay / conflict / same-body existing row | 3 | all PASS |
| Governance-only TOOL_AWAITING exact key set + absence assertions | 1 | PASS |

## 4. Accepted Plan Contract Verification

以下按 accepted plan §6 逐项走读，每条均以直接代码证据确认：

### 4.1 Shared Writer Contract（§4.2, §6.3 items 1-3）

- **证据**: `tool_call_request.py::build_tool_call_requested_event_request`（line 150-200）是唯一 `TOOL_CALL_REQUESTED` writer。ordinary 通过 `tool_runtime.py::_tool_call_request_atom`（line 4287）映射 `ToolFactAcceptCandidate` → `AcceptedToolCallRequestAtomInput`，`tool_identity_digest` 原样取自 `candidate.call.tool_identity_digest`（line 4306）。awaiting 通过 `waiting.py::_tool_call_request_atom`（line 2297）映射 `ToolAwaitingAcceptCandidate` → `AcceptedToolCallRequestAtomInput`，`tool_identity_digest` 原样取自 `candidate.tool_identity_digest`（line 2315），`semantic_query_text=None`（line 2321）。
- **结论**: 单 owner，两个入口均使用显式映射，不从 schema/log/digest 反推。✅

### 4.2 Transaction Sequencing（§4.4）

- **证据**: `waiting.py::_accept_in_transaction`（line 629-660）严格按 shared writer → `append_event(...).row` → 用真实 row 构造 ref → append `TOOL_AWAITING` → 后续 facts。同 transaction 内完成，任一异常整体 rollback。
- **结论**: sequencing 正确，rollback 测试覆盖 request/awaiting/run_waiting/wait_record 四个注入点。✅

### 4.3 TOOL_AWAITING Governance-Only（§4.4）

- **证据**: `_event_payload.py::tool_awaiting_payload`（line 16-100）已删除 `normalized_arguments_digest`、`accepted_arguments`、`accepted_arguments_source_digest`，新增 `tool_call_requested_event_ref=dict(tool_call_requested_event_ref)`。`waiting.py::_required_event_ref`（line 2652）提供 exact `{event_id, event_sequence}` shape 校验，显式排除 `bool`-as-`int` 边界。
- **结论**: governance-only contract 已落实。✅

### 4.4 Double-End Digest Guard（§4.2 writer invariant, §6.3 item 7）

- **证据**: Writer 端: `tool_call_request.py` line 221-222 — `arguments_payload_digest != atom.normalized_arguments_digest` 时抛 `HostPayloadReferenceError`。Reader 端: `payload_resolution.py` line 135-138 — `arguments_payload_digest != normalized_digest` 时抛 `HostDurableError`。
- **结论**: 双端 proof，偏差在 writer/reader 各自 fail closed。✅

### 4.5 Inline/Descriptor Mutual Exclusion（§6.3 prior retained contract）

- **证据**: `payload_resolution.py::_read_arguments_json`（line 231）descriptor 分支新增 `arguments_inline_json is not None` guard。`_read_semantic_query`（line 287）descriptor 分支新增 `semantic_query_text is not None` guard。
- **结论**: 冷热互斥 guard 已落实。✅

### 4.6 semantic_input_digest Required（§6.3 item 7）

- **证据**: `payload_resolution.py` line 153 — `semantic_input_digest=_required_text(payload, "semantic_input_digest")`，`_optional_text` helper 已删除。`_request_atoms_match_envelope` line 611-612 — 新增 `semantic_input_digest` equality check。
- **结论**: required 语义已落实，envelope mismatch 会 fail closed。✅

### 4.7 Accepted-Result / RunInput / Memory / Compact / Trace No Fallback（§6.3 items 8-9）

- **证据**: `accepted_result_projection.py::_request_atoms_projection`（line 476-503）对 envelope 缺失、request link 缺失、row 缺失、identity mismatch、atom unreadable、envelope mismatch 全部抛 `HostDurableError`，不返回 `None`。`_query_projection`（line 506）只接受 `atoms: ToolCallRequestAtoms`（非 optional）。`run_input.py::_resume_wait_accepted_arguments`（line 3496）对 `request_arguments_json is None` 抛 `HostDurableError`。
- **结论**: no-fallback/no-partial-publication 已落实。`_request_unavailable_query`、`_resume_wait_fallback_message` 已删除。✅

### 4.8 Wait-Resolution Source Attempt Execution Owner（§6.3 items 10-11）

- **证据**: `run_transition.py::_waiting_tool_result_event_request`（line 3744-3773）接收 `source_attempt: AttemptRow`，写入 `attempt_id=source_attempt.attempt_id`、`execution_id=source_attempt.execution_id`。resume 分支（line 1786-1795）和 terminal 分支（line 1948-1956）共用该 writer。`_invalid_waiting_resolution_precondition`（line 5360-5361）新增 `wait_record.execution_id != source_attempt.execution_id` 前置条件。`_request_row_matches_result`（line 589-593）不再接受 `result.execution_id is None`。
- **结论**: source Attempt execution owner 已落实。✅

### 4.9 CV-F01 NOT_FOUND Tests（§6.4 direct-transition owner test）

- **证据**: `test_waiting_resolution_transition_returns_not_found_without_mutation` — `missing_run` case 对不存在 Run 调用 `resume_run_from_waiting_in_transaction`，断言 `NOT_FOUND` + 五表 no-mutation。`missing_wait` case 对不存在 WaitRecord 调用 `fail_run_from_waiting_in_transaction`，断言 `NOT_FOUND` + 五表 no-mutation。两例均使用真实 SQLite durable store、production `EventLogStore`、完整 typed transition input。
- **结论**: 真实 durable precondition tests，非 coverage shim。coupled with `77 passed / 80%` transition owner suite。✅

### 4.10 Docstring / Typing / README

- **证据**: `tool_call_request.py` 所有 public/private 函数和类均有完整中文 docstring（参数/返回/异常）。签名无 `Any`/`object`。`_required_event_ref` 返回 typed `ToolAwaitingEventRef`。`dayu/host/README.md` 更新反映 shared writer、governance-only awaiting、strict consumer、source execution identity 与 canonical replay。`tests/README.md` 更新反映 wait resolution identity 和 canonical fixture。
- **结论**: docstring/typing/README 合规。✅

### 4.11 S2/S3 / Issue 177/178 / Authorization Boundary

- **证据**: diff-only scan 确认 S1 未 touch S2（`_contains_unsafe_argument_key`、`arguments_summary_unsafe`、`redact_sensitive_json_fields`）或 S3（`OpaqueEvidenceRef`、`source_locator_refs`、opaque ref classification）代码行。无 Issue 177/178 或统一 authorization 相关修改。
- **结论**: 未越界。✅

### 4.12 Zero-Change Integrity

- **证据**: 34-target aggregate content digest `5bed2515...c7a` 和 protected status digest `5f6e70d8...39d` 由 fix-codex artifact 记录，本 re-review 独立确认 production/tests/README/control diff 未变。
- **结论**: zero-change integrity 保持。✅

## 5. Findings

### 未发现实质性问题

经过逐文件走读、adversarial failure pass、semantic ownership drift pass、old helper deletion closure scan、S2/S3 boundary scan、dual-end digest guard trace、transaction sequencing audit、corruption matrix verification 和独立 test/pyright/ruff/coverage 验证，当前 R03-S1 implementation 在 correctness、stability 和 maintainability 方面未发现 material finding。

### 5.1 四项 Controller No-Fix Disposition 独立复核

| Disposition | 复核结论 | 证据 |
|---|---|---|
| MiMo full-Host timing observation → no finding | 同意。本 review 独立 full Host 为 `1952 passed, 2 skipped, 5 deselected`，无相关失败。 | 独立 full Host 绿色 |
| Control doc diff → authorized Controller state | 同意。`docs/host/issues-implementation-control.md` 的 diff 是 gate 状态追踪，非产品语义变更。 | control doc 仅含 gate entry 更新 |
| DS duplicate-preimage observation → rejected as finding | 同意。`_accepted_arguments_json` 在 `tool_runtime.py`（pre-accept digest producer）和 `tool_call_request.py`（writer fail-closed validator）属不同验证角色。shared writer 的 `arguments_payload_digest != normalized_arguments_digest` guard（line 221-222）确保偏差以 `HostPayloadReferenceError` 终止，不形成第二 durable truth。 | 直接代码证据：`tool_call_request.py:221-222` |
| `run_input.py` unused import deletion → no finding | 同意。删除的 `build_memory_budget_diagnostic`/`estimate_memory_size_units` imports 在当前模块无消费者；full pyright/ruff 绿色。 | pyright 零错误，full Host 绿色 |

### 5.2 额外复核项

以下为前两路初审中未明确展开、本 re-review 补充复核的项：

#### 5.2.1 `_required_event_ref` bool-as-int 边界处理

- **入口**: `waiting.py::_required_event_ref`（line 2652）
- **检查**: Python 中 `isinstance(True, int)` 为 `True`。代码 line 2682-2684 显式 `isinstance(event_sequence, bool)` 排除，确保 `true`/`false` JSON 值不会被误认为合法 sequence。
- **结论**: correct。✅

#### 5.2.2 `AcceptedToolCallRequestAtomInput.__post_init__` 校验覆盖

- **入口**: `tool_call_request.py::AcceptedToolCallRequestAtomInput.__post_init__`（line 87）
- **检查**: 校验三组字段：非空文本（9 个 identity 字段）、sha256 digest（4 个 digest 字段）、semantic_query_text 空白拒绝。coverage 显示 line 106/114/116 未覆盖 — 这些是 error-raising 分支，由测试的 valid-input-only 路径解释。
- **结论**: 95% coverage 达到 `>=95%` 目标，missing lines 均为 invalid-input error paths。不构成 correctness gap。✅

#### 5.2.3 Ordinary accept `occurred_at` 计算位置

- **入口**: `tool_runtime.py::_accept_in_transaction`（line 2449-2462）
- **检查**: `occurred_at = datetime.now(UTC)` 在 `build_tool_call_requested_event_request` 调用前计算一次，与 awaiting accept（`waiting.py` line 629）一致。`tool_call_request.py::build_tool_call_requested_event_request` 接收 `occurred_at` 参数而非内部取时，保持调用方可控。
- **结论**: correct。✅

#### 5.2.4 `_event_ref_json` 与 `_required_event_ref` 的语义一致性

- **检查**: `_event_ref_json(row)`（`waiting.py` line 2652）从 `EventLogRow.event_id/event_sequence` 构造 `{"event_id": str, "event_sequence": int}`。`_required_event_ref(payload, field_name)`（line 2655）从 payload 读取并校验 exact same shape。写入端使用 `_event_ref_json`，读取端使用 `_required_event_ref`，两端 shape 完全一致。
- **结论**: write/read shape contract 一致。✅

## 6. Accepted Plan Closure

| Contract | Status | Direct Evidence |
|---|---|---|
| ordinary/awaiting shared writer `build_tool_call_requested_event_request` | ✅ | `tool_call_request.py:150`；`tool_runtime.py:2453`；`waiting.py:632` |
| `TOOL_AWAITING` 删除 arguments/digest 副本，只留 `tool_call_requested_event_ref` | ✅ | `_event_payload.py:72`；`waiting.py:2368` |
| `arguments_payload_digest == normalized_arguments_digest` writer + reader 双端 guard | ✅ | `tool_call_request.py:221`；`payload_resolution.py:135` |
| descriptor arguments/query 冷热正文互斥 guard | ✅ | `payload_resolution.py:234,290` |
| `semantic_input_digest` required（reader）| ✅ | `payload_resolution.py:153` |
| `_request_row_matches_result` strict execution equality，不兼容 `None` | ✅ | `accepted_result_projection.py:589-593` |
| `_request_atoms_projection` fail closed（抛 `HostDurableError`，不返回 `None`）| ✅ | `accepted_result_projection.py:476-503` |
| `run_transition.py` wait-resolution source Attempt execution identity writer | ✅ | `run_transition.py:3744-3773` |
| `_invalid_waiting_resolution_precondition` WaitRecord/source Attempt execution 等值 | ✅ | `run_transition.py:5363` |
| resume/terminal transition `INVALID_STATE` + 五表 no-mutation | ✅ | `test_resolve_wait_command.py` 2 parameterized cases |
| public completed/failed/lost source execution identity | ✅ | `test_resolve_wait_command.py` 3 public cases |
| RunInput resume exact canonical args，删除 fallback message | ✅ | `run_input.py:3496-3511`；`_resume_wait_fallback_message` deleted |
| `_required_event_ref` exact `{event_id, event_sequence}` shape validator | ✅ | `waiting.py:2655-2693` |
| 旧 helper 删除闭集（12 个符号，三模块）| ✅ | 全仓 rg 零命中 |
| CV-F01 NOT_FOUND direct transition owner tests | ✅ | `test_resolve_wait_command.py` 2 cases |
| 四 consumer corruption strict `HostDurableError` / no-publication | ✅ | 36 consumer tests all PASS |
| 不越界到 S2/S3、Issue 177/178、authorization | ✅ | diff-only boundary scan |
| 逐文件 coverage 达标 | ✅ | 8 production files: `80%`–`98%`；`tool_call_request.py 95%` |
| pyright 零错误 | ✅ | `0 errors, 0 warnings, 0 informations` |
| README 更新 | ✅ | `dayu/host/README.md`；`tests/README.md` |

## 7. Open Questions

无。

## 8. Residual Risk

| Risk | Classification | Owner |
|---|---|---|
| `_accepted_arguments_json` 在 `tool_runtime.py` 与 `tool_call_request.py` 的双定义 | 低风险；独立 producer/validator + fail-closed guard 已形成自修正闭环。非 R03-S1 scope | S2 或后续 cleanup（可选）|
| `_contains_unsafe_argument_key` classifier 仍用于 query projection | 属 S2 scope；S1 未修改 | R03-S2 |
| opaque refs / `kind:id` source guessing / legacy material fallback | 属 S3 scope；S1 diff 未 touch | R03-S3 |
| macOS multiprocessing spawn 与 coverage 插桩不兼容 | validation tooling limitation；无插桩 full Host 1952 passed 已覆盖 | 非产品行为 |

## 9. Conclusion

**PASS / FINDINGS=0**

R03-S1 implementation 经第二路独立 final re-review 确认：

- 完整落实 accepted plan §6 的全部 22 项 contract，所有 close 状态均由直接代码证据支撑；
- initial findings=0 保持不变；
- 34-target zero-change integrity 保持（本 re-review 未修改任何 production/test/README/control/artifact）；
- 四项 Controller no-fix disposition 经独立复核均成立；
- CV-F01 已闭合（`77 passed / 80%` transition owner suite）；
- S2/S3 deferred 边界清晰，无越界；
- 独立验证全部通过：389 passed（S1 matrix）、1952 passed（full Host）、pyright 零错误、ruff pass、8-file coverage 全部达标。

Stable finding IDs: 无。
Residual owners: S2（source blacklist audit）、S3（opaque ref propagation closure）。
