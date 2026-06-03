# WU-ENG-02 Slice 1 Re-Review — AgentMiMo

## Gate / Work Unit / Slice

- gate: re-review
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 1 — Engine Contract And Agent Identity
- agent: AgentMiMo
- review type: deepreview

## Fix Artifact

`docs/reviews/wu-eng-02-slice1-fix-codex.md`

## Review Target

当前未提交 workspace changes（`git diff HEAD`），覆盖 implementation + fix 两个 gate 的累积变更。

## Accepted Finding 最终状态

### Finding DS-1: EngineEvent client_correlation_id 值未在 Agent 测试中断言

- **来源**: AgentDS code review Finding 1 (LOW)
- **Fix 声明**: 已修复
- **最终状态**: ✅ 已修复
- **验证**:

| 测试函数 | 断言内容 | 评估 |
|---|---|---|
| `test_success_run_lifts_runner_events_and_agent_final` (phase2) | `IterationCompletedData.client_correlation_id == request_identity.client_correlation_id` | 直接验证 EngineEvent emission 路径，非表面断言 |
| `test_completed_tool_call_injects_messages_and_reaches_final` (phase3) | 两个 `ITERATION_COMPLETED` 事件分别与两个 Runner call identity 一致 | 验证多 iteration 场景下 EngineEvent 级 correlation id 逐次对齐 |
| `test_tool_calls_finish_reason_mismatch_keeps_provider_request_id` (phase3) | `IterationCompletedData` 与 terminal `RunFailedData` 均携带同一 correlation id | 验证失败路径 EngineEvent emission |
| `test_length_continuation_appends_prompt_and_joins_content` (phase3) | 两个 `ITERATION_COMPLETED` 事件分别与两个 Runner call identity 一致 | 验证 continuation 场景 EngineEvent 级 correlation id |
| `test_run_agent_and_wait_preserves_provider_request_id` (phase2) | `EngineRunOutcomeFailed.client_correlation_id == expected_client_correlation_id` | 验证 `run_agent_and_wait` 终态映射透传 |

**判定依据**: 断言直接比较 `EngineEvent.data.client_correlation_id` 与 `RunnerRequestIdentity.client_correlation_id`，覆盖了 success、tool-loop、continuation、failure 四种路径。代码通过 `_client_correlation_id_from_state(state)` 单一 helper 在所有 emission site 一致使用，测试验证了该 helper 的输出正确进入 emitted event。若未来某处遗漏调用 helper，现有测试将捕获回归。

### Finding DS-2: `_validate_batch_bijection` RunFailedData 缺少 client_correlation_id

- **来源**: AgentDS code review Finding 2 (LOW)
- **Fix 声明**: 已修复
- **最终状态**: ✅ 已修复
- **验证**:

**生产代码变更**:
- `_validate_batch_bijection` 签名新增 `client_correlation_id: str | None` 参数
- 两条失败路径（duplicate record、input/output id set mismatch）均写入 `RunFailedData.client_correlation_id=client_correlation_id`
- 调用点 `_execute_tool_batch` 传入 `decision.client_correlation_id`

**测试覆盖**:
- `_RecordingToolExecutor` 新增 `records_override` 字段，支持注入 mismatched records
- `test_duplicate_and_executor_exception_paths` 新增 mismatch 场景：
  - 输入 `tc_1`，注入返回 `tc_other` 的 record → 触发 bijection failure
  - 断言 `mismatch_failed.error_code == "tool_batch_outcome_mismatch"`
  - 断言 `mismatch_failed.client_correlation_id == mismatch_runner.request_identities_seen[0].client_correlation_id`

**判定依据**: 测试通过 `records_override` 注入 mismatch 场景，验证失败 data 的 correlation id 与当前 Runner request identity 一致。不是表面断言——直接验证了 fix 引入的参数传递路径。

### MiMo F-01: `RunFailedData` 部分实例化路径未显式传递 `client_correlation_id`

- **来源**: AgentMiMo code review F-01 (Low, accepted)
- **Fix 声明**: N/A（code review 裁决为"当前可接受"，非 accepted finding 要求修复）
- **最终状态**: 证据仍有效，非 blocking
- **说明**: 该 finding 在 code review 中裁决为 accepted（可接受），不要求在 Slice 1 fix 中修复。fix gate 未处理此 finding 是正确的。

### MiMo F-02: `__post_init__` 与 builder 重复校验

- **来源**: AgentMiMo code review F-02 (Info, accepted)
- **Fix 声明**: N/A（code review 裁决为"不修改"）
- **最终状态**: 证据仍有效，非 blocking

### MiMo F-03: `_encode_canonical_part` 碰撞安全性

- **来源**: AgentMiMo code review F-03 (Info, accepted)
- **Fix 声明**: N/A（code review 裁决为"不修改"）
- **最终状态**: 证据仍有效，非 blocking

## Scope Creep 检查

| 检查项 | 结果 |
|---|---|
| fix 是否引入 Slice 2 行为（OpenAI header mapping） | 否 |
| fix 是否引入 Slice 3 行为（Host projection / ingest） | 否 |
| fix 是否引入新模块或新公共契约 | 否 |
| fix 是否修改 README | 否 |
| fix 是否修改 control_doc 以外的非目标文件 | 否（control_doc 更新为 gate 状态推进，符合流程） |
| fix 是否引入新的类型/docstring 问题 | 否 |

**结论**: fix 严格限于关闭两条 accepted findings，无 scope creep。

## Validation Evidence

| 验证项 | 结果 |
|---|---|
| `pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/contracts/test_runner_identity.py tests/engine/contracts/test_agent_run.py tests/engine/test_metadata_boundary.py` | 127 passed, 0.21s |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff HEAD` | 已审查全部未提交变更 |

## 新增 Blocking Issue

无。

## Residual Risks

| 风险 | 分类 | Owner |
|---|---|---|
| `_fallback_after_tools` RAISE_ERROR 路径 `client_correlation_id=None` 未有测试显式断言 | 防御性缺口 | Slice 3/4（设计决策点） |
| 3+ call index 路径未显式测试 | 覆盖缺口 | 低风险，递增逻辑不变 |
| `_MetadataBoundaryRunner` 未捕获 request_identity | 覆盖缺口 | 非阻塞（metadata boundary 测试职责不含 identity 验证） |
| Slice 2 OpenAI header 映射未实现 | 预期未实现 | Slice 2 |
| Slice 3 Host projection / ingest 未实现 | 预期未实现 | Slice 3 |

## 结论

**pass**

- 0 条未修复 / 部分修复
- 0 条新增 blocking issue
- 2 条 accepted findings 均已修复，验证证据充分（非表面断言）
- fix 无 scope creep，严格限于关闭 accepted findings
- 127 tests passed, pyright 0 errors
- blocking open questions: 无
- 只修改了 re-review artifact
