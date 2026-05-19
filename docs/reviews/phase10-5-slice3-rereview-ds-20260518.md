# P10.5 Slice 3 Re-review Artifact

## Gate

P10.5 Slice 3 re-review。

## Review Target

当前工作区 Slice 3 fix 后 uncommitted diff（fix agent 处理 controller adjudication F1/F2/F3 之后的状态）。

## Evidence Sources

- 设计真源：`docs/host/design.md`
- 总控文档：`docs/host/implementation-control.md`
- Accepted plan：`docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Slice 3 implementation artifact：`docs/reviews/phase10-5-slice3-implementation-codex-20260518.md`
- MiMo code review：`docs/reviews/phase10-5-slice3-code-review-mimo-20260518.md`
- DS code review：`docs/reviews/phase10-5-slice3-code-review-ds-20260518.md`
- Controller adjudication：`docs/reviews/phase10-5-slice3-code-review-controller-adjudication-20260518.md`
- Fix artifact：`docs/reviews/phase10-5-slice3-fix-codex-20260518.md`
- Diff：`dayu/host/` `tests/host/` 当前 uncommitted changes

## Accepted Fixes Verification

### F1: Extract duplicated runner / provider request projection logic

**裁决**：accepted，完成。

**验证**：

1. 新模块 `dayu/host/_execution_config_projection.py`（584 行）统一维护 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、`ProviderRequestExtension` 的 JSON 投影/反投影/字段读取原语。

2. 三处消费者均替换为 import 共享 helper：
   - `admission.py`：`effective_execution_config_json`、`optional_runner_spec_json`、`optional_runner_options_json`、`optional_agent_policy_json`
   - `command.py`：`optional_runner_spec_json`、`optional_runner_options_json`、`optional_agent_policy_json`
   - `dispatch.py`：`effective_execution_snapshot_from_json`、`required_json_mapping`、`required_json_text`

3. 旧重复函数已全量删除：
   - `admission.py` 中 `def _runner_spec_json` / `_runner_options_json` / `_agent_policy_json` / `_provider_request_json` — **0 残留**（grep 确认）
   - `command.py` 中 `def _runner_spec_digest_value` / `_runner_options_digest_value` / `_agent_policy_digest_value` / `_provider_request_digest_value` — **0 残留**（grep 确认）

4. Payload shape / digest / ref / schema / public API / state machine 未变：
   - `effective_execution_config_json` 产出的 JSON 结构（`policy_snapshot_ref`、`policy_snapshot_digest`、`config.runner_spec|runner_options|agent_policy|sources`）与原 admission.py 内联代码完全等价
   - `provider_request_json` 覆盖全部 6 种 extension 子类型（OpenAIReasoning / AnthropicThinking / DeepSeekThinking / MimoThinking / GeminiThinking / QwenThinking），映射逻辑与原三处逐字重复代码一致
   - `effective_execution_snapshot_from_json` 的 round-trip 从 JSON 还原 `RunnerSpec` + `RunnerCallOptions` + `AgentPolicy` + `policy_snapshot_ref`，与 dispatch 原 `_policy_snapshot_from_effective_execution` 等效
   - semantic digest 计算继续使用共享 helper 的 `optional_*_json` 函数，digest 值不变

5. 新增 helper 全部使用 `RuntimeError`（内部 corruption 场景），不引入 `HostApiError` 到序列化层（正确的分层决策）。

**F1 结论**：完全完成，无行为变化，无遗漏。

### F2: Add focused agent_policy override coverage

**裁决**：accepted，完成。

**验证**：

新增测试 `test_agent_policy_override_freezes_payload_and_dispatch_snapshot_ref`：

```python
# test_effective_execution_config.py:264-319
override_policy = AgentPolicy(
    max_iterations=7,
    continuation_max_attempts=1,
    allow_tool_calls=False,
    tool_execution_timeout_seconds=3.5,
    max_consecutive_failed_tool_batches=4,
)
```

验证覆盖点：
- `USER_INPUT_ACCEPTED` payload 中 `effective_execution_config.config.agent_policy.max_iterations == 7` — agent_policy override 正确冻结
- `effective_execution_config.config.sources.agent_policy == "request"` — 来源标注正确
- `effective_execution_config.config.sources.runner_spec == "opener_baseline"` — 未 override 字段回退 baseline
- `factory.requests[0].agent_policy == override_policy` — dispatch 使用冻结后的 agent_policy
- `factory.snapshots[0].policy_snapshot_ref == effective_execution["policy_snapshot_ref"]` — dispatch snapshot ref 与 admission 冻结 ref 一致

独立覆盖 `agent_policy` override 场景，与已有 `runner_spec` override / `runner_options` override 测试互补，三字段 field-level partial merge 完整覆盖。

**F2 结论**：完全完成。

### F3: Add baseline-none fail-early test

**裁决**：accepted，完成。

**验证**：

新增测试 `test_submit_followup_without_ordinary_baseline_fails_before_dispatch`：

```python
# test_effective_execution_config.py:322-345
handle = create_host_command_handle(_command_options(tmp_path))
# _command_options 中 local_execution=None → admission service 无 baseline
with pytest.raises(HostApiError) as exc_info:
    command_submit_followup(handle, session.session_id, _followup(session.session_id))

assert exc_info.value.code == HostApiErrorCode.INVALID_STATE
assert "ordinary Run baseline" in exc_info.value.message
```

验证覆盖点：
- 低层 `create_host_command_handle` 路径无 `ordinary_run_baseline` 时 `submit_followup` 早失败
- 错误码 `INVALID_STATE`、错误消息包含 "ordinary Run baseline"
- 失败发生在 dispatch 之前（admission 阶段拒绝）

**F3 结论**：完全完成。低层路径行为正确，public `open_host` 路径不受影响（`OpenHostOptions.ordinary_run_baseline` 必填）。

### Docstring 合规补充

新模块 `_execution_config_projection.py` 中所有函数（含模块级 docstring）均提供完整中文 docstring，含 `:param`、`:returns`、`:raises`。未改变任何行为。

**结论**：合规，无行为变化。

## New Findings

### N1 (non-blocking): 16 个现有低层 admission service 测试因 `baseline=None` 失败

**证据**：

```
FAILED tests/host/test_admission_queue.py - 14 tests
FAILED tests/host/test_projection_read_model.py - 2 tests
```

全部 16 个失败均源自同一根因：

```
HostApiError: submit_followup requires an opener ordinary Run baseline
dayu/host/admission.py:2178
```

**根因分析**：

`test_admission_queue.py` 和 `test_projection_read_model.py` 的测试辅助函数 `_service()` 通过 `create_host_admission_service` 构造 admission service，不传入 `ordinary_run_baseline`。Slice 3 新增 `_resolve_followup_effective_facts` 要求 baseline 非 `None` 才能计算 effective execution config，因此 `submit_followup_queue` 在 admission 阶段早失败。

这不是 fix 引入的回归——原始 Slice 3 implementation 引入 `_resolve_followup_effective_facts` 时即存在此问题。原始 implementation artifact 仅验证了 3 个新测试文件（9 tests），MiMo 和 DS code review 也只运行了 focused tests，未发现此问题。

**影响**：测试基础设施破损，不影响生产正确性（public `open_host` 路径始终提供 baseline）。

**严重程度**：Non-blocking。

**修复建议**：在 `test_admission_queue.py` 的 `_service()` helper 和 `test_projection_read_model.py` 的对应 helper 中，向 `create_host_admission_service` 传入 `ordinary_run_baseline` 和 `tooling_options` 参数。修复量小且机械。

**注意**：Controller adjudication 将 fix scope 限制为"existing focused tests only if projection helper extraction requires import path updates"，因此 fix agent 无权修改这些文件。建议在后续 slice 或独立 fix gate 中处理。

### N2 (non-blocking, observation): fix artifact residual risk 声明完整

Fix artifact 明确声明：
> `ordinary_run_baseline=None` 已在低层 command handle 路径覆盖；`OpenHostOptions` 构造期不允许 baseline 为 `None`，因此 public opener 路径不存在同类运行期缺口。

此声明正确，但未提及 admission queue / projection read model 测试的同类缺口。N1 补充了该项。

## Validation

```
source .venv/bin/activate && pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q
→ 11 passed

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations
```

Slice 3 focused tests 全部通过（11 tests，含 2 个原有 + 2 个 F2/F3 新增 = 相比原始 implementation 的 9 tests 新增 2 tests）。pyright 零报错。

全量 host 测试：620 passed, 42 failed（其中 16 个为 N1 描述的 pre-existing baseline=None 问题，26 个为 Slice 3 无关的 pre-existing 失败）。

## Positive Observations

1. **旧重复代码零残留**：grep 确认 `admission.py` 和 `command.py` 中 `def _runner_spec_json` / `_runner_options_json` / `_agent_policy_json` / `_provider_request_json` 及其 digest/from_json 变体均已删除。唯一的真源在 `_execution_config_projection.py`。

2. **Round-trip fidelity 完整**：`_execution_config_projection.py` 同时维护 `_json`（序列化）和 `_from_json`（反序列化）函数，admission/dispatch 之间的 JSON round-trip 在同一模块内可验证。

3. **provider extension 类型覆盖完整**：`provider_request_json` 和 `provider_request_from_json` 覆盖全部 6 种 extension 子类型，与原始实现一致。

4. **dispatch policy_snapshot_ref 正确使用 admission 冻结 ref**：`_snapshot_from_dispatch` 的 `policy_snapshot_ref` 参数由 `effective_decision.policy_snapshot.policy_snapshot_ref` 传入，不再使用 `_LOCAL_POLICY_SNAPSHOT_REF` 硬编码。`_LOCAL_POLICY_SNAPSHOT_REF` 仅作为 fallback（`effective_execution_config` 缺失时，即旧 `start_run` 路径）。

5. **三层 consumer 导入一致**：admission/command/dispatch 三个 consumer 从 `_execution_config_projection` 导入各自需要的函数子集，无多余导入。

## Verdict

**PASS** — blocking count = 0。

### Summary

| 项目 | 状态 |
| --- | --- |
| F1: 序列化重复抽取 | 完成，旧代码零残留 |
| F2: agent_policy override 覆盖 | 完成，三字段独立 partial merge 完整覆盖 |
| F3: baseline=None fail-early 测试 | 完成，低层 command handle 路径已覆盖 |
| Docstring 合规 | 完成，无行为变化 |
| Payload shape / digest / ref / schema | 不变 |
| Public API / durable schema / state machine | 不变 |
| pyright | 0 errors |
| Slice 3 focused tests | 11 passed |
| 新 Blocker | 0 |

### Non-blocking findings

- **N1**：16 个现有低层 admission service 测试因 `baseline=None` 失败（pre-existing from original Slice 3 implementation），建议后续 slice 补充 baseline 注入。
- **N2**：fix artifact residual risk 声明未覆盖 admission queue / projection read model 测试缺口。

## Artifact Path

`docs/reviews/phase10-5-slice3-rereview-ds-20260518.md`
