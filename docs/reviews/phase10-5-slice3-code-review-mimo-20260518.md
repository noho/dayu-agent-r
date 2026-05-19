# Phase 10.5 Slice 3 Code Review

## Gate

P10.5 Slice 3 code review。

## Review Target

当前工作区 uncommitted Slice 3 diff，相对 HEAD (`79f7b44`)。

## Review Artifacts

- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Implementation artifact: `docs/reviews/phase10-5-slice3-implementation-codex-20260518.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`

## Scope Verification

### Slice 3 内容审查

Slice 3 目标：SubmitFollowupRequest typed fields、per-run effective runner config field-level partial merge、tool_names semantics、effective tool set/config freeze、FollowupSnapshot command_watermark、focused tests/docs。

**变更文件清单**（19 files, +1270 / -64）：

| 文件 | 归属 | 验证 |
| --- | --- | --- |
| `dayu/host/api.py` | SubmitFollowupRequest typed fields, FollowupSnapshot command_watermark | 正确 |
| `dayu/host/admission.py` | effective config/tool set freeze, per-run baseline wiring | 正确 |
| `dayu/host/command.py` | semantic digest 更新, command_watermark mapping | 正确 |
| `dayu/host/dispatch.py` | 从 EventLog payload 读取 frozen effective decision | 正确 |
| `dayu/host/open_host.py` | baseline/tooling_options 传递到 admission service | 正确 |
| `dayu/host/run_input.py` | system_prompt 消费, message 构建 | 正确 |
| `dayu/host/tool_runtime.py` | selected_business_tool_names 过滤 | 正确 |
| `dayu/host/README.md` | 文档同步当前事实 | 正确 |
| `tests/README.md` | 新测试层说明同步 | 正确 |
| 新 `test_submit_followup_public_contract.py` | 3 tests | 正确 |
| 新 `test_per_run_tool_selection.py` | 4 tests | 正确 |
| 新 `test_effective_execution_config.py` | 2 tests | 正确 |
| 9 existing test files | 迁移 `SubmitFollowupRequest` 字段、`command_watermark` | 正确 |

**未越界确认**：
- 未实现 Slice 4 live HostEvent fanout：无 `watch_session_events` 实现变更。
- 未实现 Slice 5 steer/retry/replay/WAITING semantics：`behavior=steer` 仍返回 `UNSUPPORTED_OPERATION`。
- 未实现 Slice 6 smoke matrix。
- 未修改 durable schema / state-machine。

### Durable Schema / State Machine 审查

- 无 `dayu/host/durable/schema.py` 变更。
- 无 `dayu/host/durable/state.py` 变更。
- effective config/tool set 通过 EventLog `USER_INPUT_ACCEPTED` payload JSON freeze，不引入新的 durable 列或表。
- dispatch 读取同一冻结视图 (`_effective_dispatch_decision_from_payload`)。
- 旧 `start_run` 路径无 `effective_execution_config` payload 时 fallback 到 `_local_policy_snapshot()`，向后兼容。

### Explicit Fields / Extra Payload 审查

- `SubmitFollowupRequest` 所有新字段均为显式 typed fields：`system_prompt: str | None`、`user_prompt: str`、`tool_names: frozenset[str] | None`、`runner_spec: RunnerSpec | None`、`runner_options: RunnerCallOptions | None`、`agent_policy: AgentPolicy | None`。
- 无 `extra payload`、`untyped metadata`、`dict`、`Any` 或 `object` 使用。
- EventLog payload 中的 `effective_execution_config` 和 `effective_tool_set` 是 typed JSON projection，非 untyped metadata。

## Findings

### F1. Non-blocking: runner config JSON 序列化逻辑三处重复

**证据**：
- `admission.py`：`_runner_spec_json`、`_runner_options_json`、`_agent_policy_json`、`_provider_request_json`（~120 行）。
- `command.py`：`_runner_spec_digest_value`、`_runner_options_digest_value`、`_agent_policy_digest_value`、`_provider_request_digest_value`（~120 行），produces identical JSON structure。
- `dispatch.py`：`_runner_spec_from_json`、`_runner_options_from_json`、`_agent_policy_from_json`、`_provider_request_from_json`（~150 行），反向还原。

三组函数映射同一 typed objects 到相同 JSON 结构，只是函数名和错误处理不同（admission 用 `HostApiError`、command 静默、dispatch 用 `RuntimeError`）。

**影响**：新增 `ProviderRequestExtension` 子类型或 `RunnerSpec` / `AgentPolicy` 字段时需同步修改三处；遗漏会导致 dispatch 无法还原 admission 冻结的 config，或 command digest 与 admission digest 不一致导致幂等误判。

**严重程度**：Non-blocking（当前字段集稳定，三处同步正确）。

**修复建议**：后续 slice 考虑提取共享 `dayu/host/_runner_config_projection.py` 模块级私有 helper，admission / command / dispatch 三处复用同一序列化 / 反序列化 / digest 逻辑。

### F2. Non-blocking: EventLog payload 中 system_prompt 双写

**证据**：`admission.py:2126-2135`：
```python
"system_prompt": request.system_prompt,
"user_prompt": request.input.display_text,
```
同时保留旧字段：
```python
"display_text": request.input.display_text,
"payload_ref": request.input.payload_ref,
```

`system_prompt` 既作为顶层 payload 字段写入，又通过 `request.input.display_text` 在 `display_text` 字段中冗余存储 `user_prompt`。

**影响**：payload 体积略增；`run_input.py` 通过 `_PAYLOAD_FIELD_SYSTEM_PROMPT` 读取独立 `system_prompt` 字段，路径正确。旧字段保留确保旧路径不崩溃。

**严重程度**：Non-blocking。

**修复建议**：可接受为过渡期双写；后续清理时移除 `display_text` 中的 `user_prompt` 冗余。

### F3. Non-blocking: FollowupSnapshot queue 验证放宽

**证据**：旧代码：
```python
elif self.accepted_run_status in (RunStatus.ACCEPTED, RunStatus.RUNNING):
    ...  # queued_run_id must be None
else:
    raise ValueError("...must be queued accepted or running for queue")
```
新代码：
```python
if self.accepted_run_status != RunStatus.QUEUED:
    if self.queued_run_id is not None:
        raise ValueError(...)
if self.accepted_run_status == RunStatus.RECOVERING:
    raise ValueError(...)
```

旧代码只允许 QUEUED / ACCEPTED / RUNNING；新代码允许除 RECOVERING 外的所有状态（含 CANCELLED、FAILED、SUCCEEDED）。

**影响**：queue 结果 snapshot 现在可携带 CANCELLED / FAILED 等终态状态。这是因为 Slice 2 改变了 `submit_followup(queue)` 的行为——无 active Run 时先 ACCEPTED 再由 scheduler 启动为 RUNNING，幂等重放可能返回任意已到达状态。验证逻辑与运行时行为一致。

**严重程度**：Non-blocking（行为与设计意图一致，测试已更新为 `test_followup_snapshot_queue_rejects_recovering_status`）。

### F4. Non-blocking: effective execution config 测试未覆盖 agent_policy override

**证据**：`test_effective_execution_config.py` 包含 2 个测试：
- `test_field_level_partial_merge_uses_baseline_for_omitted_fields`：只传 `runner_options`，验证 `runner_spec` 和 `agent_policy` 来自 baseline。
- `test_effective_config_freezes_override_and_idempotent_replay`：只传 `runner_spec`，验证 freeze 和幂等。

无测试单独传 `agent_policy` override 验证 field-level partial merge。

**影响**：`_resolve_followup_effective_facts` 对三个字段使用相同逻辑（`is not None` 时用 request 值，否则用 baseline），覆盖 `runner_spec` 和 `runner_options` 后 `agent_policy` 的逻辑已被间接证明。风险低。

**严重程度**：Non-blocking。

**修复建议**：后续补充一个 `agent_policy` only override 测试以完整覆盖三字段独立 partial merge。

## Strict Typing / 中文 Docstring / 无 Any 审查

- 所有新增函数均有完整中文 docstring，含 `:param`、`:returns`、`:raises`。
- 所有新增 dataclass 字段均有显式类型标注。
- 无 `Any`、`object`、无类型参数、无类型返回值使用。
- `_ResolvedFollowupEffectiveFacts` 为 `frozen=True, slots=True`，字段类型为 `JsonValue`（项目契约类型）。
- `_EffectiveDispatchDecision` 为 `frozen=True, slots=True`，字段类型显式。

## Validation Artifact 声明验证

Implementation artifact 声明：
- `pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q` → 9 passed ✅（复现确认）
- `pyright dayu/host tests/host` → 0 errors, 0 warnings ✅（复现确认）

## Verdict

**PASS**。Blocking count = 0。

- Accepted findings: F1, F2, F3, F4 均为 non-blocking。
- Residual risks: F1 的三处序列化重复在新增 provider extension 类型时需同步维护；F4 的 agent_policy 覆盖缺口风险低。
- Artifact path: `docs/reviews/phase10-5-slice3-code-review-mimo-20260518.md`。
