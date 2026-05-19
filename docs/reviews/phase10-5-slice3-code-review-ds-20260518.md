# P10.5 Slice 3 Code Review Artifact

## Gate

P10.5 Slice 3 code review。

## Review Target

当前工作区 uncommitted Slice 3 diff（相对 HEAD `79f7b44`）。

## Evidence Sources

- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Implementation artifact: `docs/reviews/phase10-5-slice3-implementation-codex-20260518.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`
- Diff: uncommitted changes in `dayu/host/` `tests/host/` `docs/host/` `tests/README.md`

## Scope Compliance

### In-scope (confirmed present)

| Plan item | Status | Evidence |
| --- | --- | --- |
| `SubmitFollowupRequest` typed fields (`system_prompt`, `user_prompt`, `tool_names`, `runner_spec`, `runner_options`, `agent_policy`) 替代 `HostInput` envelope | PASS | `api.py:1870-1878`；`HostInput` 不再作为 `SubmitFollowupRequest` 字段 |
| `tool_names=None` = 全量业务工具，空=`frozenset()` = 禁用，非空子集 = 过滤 | PASS | `admission.py:514-533`；test coverage 在 `test_per_run_tool_selection.py` |
| 未知 tool name 在 durable canonical facts 前拒绝 | PASS | `admission.py:518-527`；test `test_unknown_tool_name_is_rejected_before_dispatch` 验证 `factory.requests == []` |
| Field-level partial merge：`runner_spec`/`runner_options`/`agent_policy` 各自独立 fallback 到 opener baseline | PASS | `admission.py:295-307`；每个 override 独立判断 `is not None` |
| Effective execution config freeze 到 `USER_INPUT_ACCEPTED` EventLog payload | PASS | `admission.py:265-271` 写入 `effective_execution_config` 和 `effective_tool_set` |
| Dispatch 读取冻结视图构造 `AgentRunRequest` | PASS | `dispatch.py:1550-1574` 从 EventLog payload 读回 `_effective_dispatch_decision_from_payload` |
| `AttemptDispatchSnapshot.policy_snapshot_ref` 使用冻结 ref 替代本地 fallback | PASS | `dispatch.py:1612` 使用 `policy_snapshot_ref` 参数 |
| `EffectiveToolBundleBuildRequest.selected_business_tool_names` 过滤业务工具 | PASS | `tool_runtime.py:1644-1650` 在 `EffectiveToolBundleBuilder` 中调用 `_selected_business_definitions` |
| `RunInputBuilder` 消费冻结 `system_prompt` 并注入 system message | PASS | `run_input.py:1315` 调用 `_system_prompt_message` |
| `FollowupSnapshot.current_cursor` → `command_watermark` 重命名 | PASS | `api.py:2254`；docstring 明确"不是 watch cursor" |
| `start_run` 函数不在 `__all__`（internal admission primitive） | PASS | `__init__.py` `__all__` 不含 `"start_run"` |

### Out-of-scope (confirmed absent)

| Forbidden item | Status |
| --- | --- |
| Slice 4 live `HostEvent` fanout / `watch_session_events` 实现 | PASS — 未修改 |
| Slice 5 steer / retry / replay / WAITING resume semantics | PASS — `submit_followup(steer)` 仍返回 `UNSUPPORTED_OPERATION` |
| Slice 6 smoke matrix / real runner tests | PASS — 未添加 |
| Durable schema 变更（新表、新列、migration） | PASS — 仅使用 EventLog payload JSON |
| 把 explicit fields 塞入 extra payload / untyped metadata | PASS — 冻结 JSON 有明确 typed schema |
| 修改 Engine 合约 | PASS — 未修改 `dayu/engine/` |
| `tool_names` 携带 raw `ToolBundle`/callable/schema fragment | PASS — 只接受 `frozenset[str] \| None` |

## Findings

### Blocking

无。

### Non-blocking

#### N1: `provider_request` → JSON 序列化重复 (maintainability)

**Evidence**: `admission.py:_provider_request_json` (lines 400-452) 与 `command.py:_provider_request_digest_value` (lines 862-917) 结构完全相同——6 种 provider extension 类型到 JSON 的映射逐字重复。两者用途不同（EventLog payload vs semantic digest），但新增 provider extension 类型时必须同步修改两处。

**Impact**: 维护负担；不造成 correctness 问题。

**Recommendation**: 不要求在本 Slice 修复。可考虑将公共投影逻辑提取到 `dayu/host/` 内部共享辅助模块，但需评估是否违反"优先模块级私有辅助函数"与"避免为一次重复创建过早抽象"的权衡。建议在 Slice 5 或 Slice 6 中处理（若后续 slice 也需同类投影）。

#### N2: `tool_runtime.py:_selected_business_definitions` defense-in-depth 使用 `ValueError`

**Evidence**: `tool_runtime.py:1674` 中 `_selected_business_definitions` 对未知工具名抛出 `ValueError`，而 admission 层 `_effective_tool_set_json` 使用 `HostApiError`。这是 defense-in-depth——admission 已在写入 durable facts 前拒绝未知工具，但若 EventLog 被旁路损坏，dispatch 路径会得到 `ValueError` 而非结构化 `HostApiError`。

**Impact**: 极低——正常路径不可能触发；仅 corruption 场景受影响。dispatch 的 `ValueError` 会作为 RuntimeError 被 scheduler 捕获，不会泄露到 Service 层。

**Recommendation**: 接受为 defense-in-depth。不需要修改。若未来希望统一，可在 dispatch 路径增加 catch-translate，但当前不必要。

#### N3: `FollowupSnapshot.__post_init__` 验证逻辑从白名单变为排除法

**Evidence**: 旧代码显式允许 `QUEUED` / `ACCEPTED` / `RUNNING`，拒绝其余。新代码只显式拒绝 `RECOVERING`，允许其他所有非 `QUEUED` 但 `queued_run_id=None` 的状态组合。

```python
# 旧
elif self.accepted_run_status in (RunStatus.ACCEPTED, RunStatus.RUNNING):
    ...
else:
    raise ValueError("...must be queued accepted or running for queue")

# 新
if self.accepted_run_status != RunStatus.QUEUED:
    if self.queued_run_id is not None: ...
if self.accepted_run_status == RunStatus.RECOVERING:
    raise ValueError("...must not be recovering")
```

**Impact**: 低——production code 中 `submit_followup(queue)` 只产出 `QUEUED` 或 `ACCEPTED`，不会产出其他终态。验证语义等价但表达方式不同。`RECOVERING` 显式拒绝更明确。

**Recommendation**: 接受。新表达更简洁且明确标记 `RECOVERING` 为非法（Phase 11 范围）。

#### N4: 缺少 `ordinary_run_baseline=None` 错误路径的显式测试

**Evidence**: `admission.py:289-294` 中 `_resolve_followup_effective_facts` 在 `baseline=None` 时抛出 `HostApiError(INVALID_STATE, "submit_followup requires an opener ordinary Run baseline")`。低层 `create_host_command_handle` 路径不提供 baseline，因此 `submit_followup` 会 fail-early。但没有专门测试这条 fail-early 路径。

**Impact**: 低——fail-early 行为正确（阻止无 baseline 的 `submit_followup`），但未被测试覆盖。

**Recommendation**: 不要求在本 Slice 添加。低层 command handle 路径已经通过 Slice 2 tests 验证 `start_run`（不受影响）工作正常。若未来低层路径需要 `submit_followup` 支持，届时再补测试。

### Positive Observations

1. **EventLog payload freeze 是双向可逆的**：`admission.py` 序列化 `RunnerSpec`/`RunnerCallOptions`/`AgentPolicy` 到 JSON，`dispatch.py` 从 JSON 完整反序列化回 typed objects，包括所有 6 种 `ProviderRequestExtension` 子类型。round-trip fidelity 完整。

2. **ToolRuntime defense-in-depth 正确**：`_selected_business_definitions` 在 ToolRuntime 层重新校验工具名，但使用 `ValueError`（不假装是 API 层错误），且只在 defense-in-depth 场景触发。

3. **Semantic digest 覆盖所有新字段**：`command.py:_submit_followup_public_semantic_digest` 和 `admission.py:_followup_queue_semantic_digest` 都包含 `system_prompt`/`user_prompt` digest、`tool_names`、`runner_spec`/`runner_options`/`agent_policy` digest。幂等 key 涵盖所有可变项。

4. **`command_watermark` 语义清理完整**：所有 `current_cursor` 引用（dayu/ 和 tests/）已全部替换为 `command_watermark`；grep 确认无残留。

5. **Fallback 兼容旧 `start_run` 路径**：`_effective_dispatch_decision_from_payload` 正确处理 `effective_execution_config` 缺失的情况——回退到 `_LOCAL_POLICY_SNAPSHOT_REF` 和 `selected_business_tool_names=None`，确保旧 `start_run` 写入的 EventLog 记录仍然可 dispatch。

## Test Coverage Audit

| Required case | Covered by |
| --- | --- |
| `SubmitFollowupRequest` 不暴露 `input`/`payload`/`profile_id` | `test_submit_followup_request_freezes_typed_public_fields` |
| `tool_names` 拒绝 untyped list/string | `test_submit_followup_rejects_untyped_tool_selector` |
| 重复 `(session_id, client_request_id)` 返回同一 accepted Run | `test_repeated_client_request_returns_same_run_and_watermark` |
| `tool_names=None` → 全量业务工具 schema | `test_none_tool_names_uses_all_business_tools` |
| `tool_names=frozenset()` → 空 tool schema | `test_empty_tool_names_disables_business_tools` |
| `tool_names=frozenset({"search_note"})` → 只暴露 search_note | `test_subset_tool_names_filters_tool_schema` |
| 未知 tool name → admission 拒绝 + 无 dispatch | `test_unknown_tool_name_is_rejected_before_dispatch` |
| 只传 `runner_options` → runner_spec/agent_policy 来自 baseline | `test_field_level_partial_merge_uses_baseline_for_omitted_fields` |
| per-run override 冻结到 dispatch snapshot，幂等重放不二次 dispatch | `test_effective_config_freezes_override_and_idempotent_replay` |
| `system_prompt` 注入 system message | 同上 test，验证 `request.messages[0].role == SYSTEM` |

覆盖充分。9 tests, all pass.

## Docs Audit

| Doc | Trigger | Status |
| --- | --- | --- |
| `dayu/host/README.md` | `dayu/host/` 修改 | PASS — 新增 `SubmitFollowupRequest` typed fields 描述、`tool_names` 语义、`command_watermark` 说明、per-run 工具选择约束 |
| `tests/README.md` | `tests/` 修改 | PASS — 新增 Slice 3 focused test 运行命令，public run/wait API 行增加 typed prompt / per-run tool_names / effective config freeze 描述 |

README 同步内容与代码一致，无"未来设计"，无残留旧术语。

## Validation

```
pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q
→ 9 passed

python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings
```

## Verdict

**PASS** — blocking count = 0。

Accepted non-blocking findings: N1 (provider_request 序列化重复), N2 (`ValueError` vs `HostApiError` defense-in-depth), N3 (FollowupSnapshot 验证排除法), N4 (baseline=None 错误路径无显式测试)。

## Residual Risks

- N1 maintenance burden：新增 provider extension 类型需改两处。建议 Slice 5/6 评估是否提取公共投影。
- Slice 3 有效 config freeze 依赖 `open_host(options)` 提供 baseline；低层 `create_host_command_handle` 路径的 `submit_followup` 会 fail-early。当前低层测试均通过 `start_run`（不受影响），但若未来低层需要 `submit_followup` 支持，需补充 baseline 注入。

## Artifact Path

`docs/reviews/phase10-5-slice3-code-review-ds-20260518.md`
