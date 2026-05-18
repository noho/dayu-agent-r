# P10.5 Slice 3 Re-Review Artifact

## Gate

P10.5 Slice 3 re-review。

## Review Target

controller adjudication accepted fixes（F1、F2、F3）的实现是否完成且未引入新 blocker。

## Review Inputs

- Controller adjudication: `docs/reviews/phase10-5-slice3-code-review-controller-adjudication-20260518.md`
- Fix artifact: `docs/reviews/phase10-5-slice3-fix-codex-20260518.md`
- MiMo code review: `docs/reviews/phase10-5-slice3-code-review-mimo-20260518.md`
- DS code review: `docs/reviews/phase10-5-slice3-code-review-ds-20260518.md`
- Implementation artifact: `docs/reviews/phase10-5-slice3-implementation-codex-20260518.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`
- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`

## Accepted Fixes Verification

### F1. Extract duplicated runner / provider request projection logic

**Verdict: COMPLETE。**

**Evidence:**

1. 新增 `dayu/host/_execution_config_projection.py`（~580 行），集中维护：
   - `runner_spec_json` / `runner_spec_from_json`：RunnerSpec ↔ JSON 双向投影。
   - `runner_options_json` / `runner_options_from_json`：RunnerCallOptions ↔ JSON 双向投影。
   - `agent_policy_json` / `agent_policy_from_json`：AgentPolicy ↔ JSON 双向投影。
   - `provider_request_json` / `provider_request_from_json`：6 种 ProviderRequestExtension 子类型 ↔ JSON 双向投影。
   - `effective_execution_config_json`：admission 写入用组合 config + digest + ref 生成。
   - `effective_execution_snapshot_from_json`：dispatch 读取用组合还原。
   - `optional_runner_spec_json` / `optional_runner_options_json` / `optional_agent_policy_json`：command semantic digest 用可选投影。
   - JSON reading helpers：`required_json_mapping`、`required_json_text`、`required_json_bool`、`required_json_int`、`required_json_float` 及 optional 变体。

2. `admission.py`（line 98-103）import `_effective_execution_config_json`、`_optional_*_json`，旧 `_provider_request_json`、`_runner_spec_json`、`_runner_options_json`、`_agent_policy_json` 已删除。

3. `command.py`（line 52-56）import `_optional_*_json`，旧 `_provider_request_digest_value`、`_runner_spec_digest_value`、`_runner_options_digest_value`、`_agent_policy_digest_value` 已删除。

4. `dispatch.py`（line 77-81）import `_effective_execution_snapshot_from_json`、`_required_json_mapping`、`_required_json_text`，旧 `_provider_request_from_json`、`_runner_spec_from_json`、`_runner_options_from_json`、`_agent_policy_from_json` 已删除。

5. Grep 确认 `dayu/host/` 下无残留旧函数定义。

**Payload shape 不变性验证：**
- `effective_execution_config_json` 产出的 JSON 结构与旧 admission 内联代码完全相同：`{policy_snapshot_ref, policy_snapshot_digest, config: {runner_spec, runner_options, agent_policy, sources}}`。
- `policy_snapshot_ref` 仍为 `"policy:sha256:<digest>"`，digest 算法不变（`sha256_digest_json`）。
- dispatch `_policy_snapshot_from_effective_execution` 通过 `effective_execution_snapshot_from_json` 还原，产出相同 `PolicySnapshot` 字段。

**Public API / state machine 不变性验证：**
- `SubmitFollowupRequest` 字段无变化。
- `FollowupSnapshot` 字段无变化。
- EventLog payload shape 无变化。
- dispatch state machine 无变化。

### F2. Add focused `agent_policy` override coverage

**Verdict: COMPLETE。**

**Evidence:**

新增 `test_agent_policy_override_freezes_payload_and_dispatch_snapshot_ref`（`test_effective_execution_config.py:265-319`）：
- 构造 `AgentPolicy(max_iterations=7, continuation_max_attempts=1, allow_tool_calls=False, tool_execution_timeout_seconds=3.5, max_consecutive_failed_tool_batches=4)` override。
- 验证 `USER_INPUT_ACCEPTED` payload 中 `effective_execution_config.config.agent_policy` 字段值正确。
- 验证 `sources.agent_policy == "request"`，`sources.runner_spec == "opener_baseline"`（field-level partial merge 独立性）。
- 验证 `factory.requests[0].agent_policy == override_policy`（dispatch 还原正确）。
- 验证 `factory.snapshots[0].policy_snapshot_ref == effective_execution["policy_snapshot_ref"]`（dispatch snapshot 使用 admission 冻结 ref）。

覆盖充分。三个 override 字段（`runner_spec`、`runner_options`、`agent_policy`）现在各有独立 focused test。

### F3. Add baseline-none fail-early test

**Verdict: COMPLETE。**

**Evidence:**

新增 `test_submit_followup_without_ordinary_baseline_fails_before_dispatch`（`test_effective_execution_config.py:323-345`）：
- 使用 `create_host_command_handle(_command_options(tmp_path))` 构造不含 `ordinary_run_baseline` 的低层 handle。
- 调用 `command_submit_followup` 预期抛出 `HostApiError`。
- 断言 `exc_info.value.code == HostApiErrorCode.INVALID_STATE`。
- 断言 `"ordinary Run baseline" in exc_info.value.message`。
- 确认 fail-early 在 dispatch 前发生（`factory.requests == []` 通过 handle close 前无 accepted 事件隐式验证）。

覆盖充分。低层 command handle 路径缺少 baseline 时的 fail-early 行为已被显式测试覆盖。

### F4. Docstring 合规补充

**Verdict: COMPLETE，无行为变更。**

**Evidence:**

- `_execution_config_projection.py` 所有 public/helper 函数均有完整中文 docstring，含 `:param`、`:returns`、`:raises`。
- `:raises` 说明区分：无主动抛出、JSON shape validation（`RuntimeError`）、enum/dataclass validation（`ValueError`）、未知 provider extension（`TypeError`）。
- `test_effective_execution_config.py` 新增测试函数和 helper 函数均有完整中文 docstring。
- 无行为变更：docstring 仅为文档补充，未修改函数签名、逻辑或返回值。

## New Findings

无。

### Non-blocking

无新增 non-blocking findings。

## Validation Re-Run

```
pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q
→ 11 passed in 0.30s

python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations
```

与 fix artifact 声明一致。

## Test Coverage Summary

| Test file | Count | Notes |
| --- | --- | --- |
| `test_submit_followup_public_contract.py` | 3 | Slice 3 原有 |
| `test_per_run_tool_selection.py` | 4 | Slice 3 原有 |
| `test_effective_execution_config.py` | 4 | Slice 3 原有 2 + fix 新增 2 |
| **Total** | **11** | |

Fix 新增 tests：
- `test_agent_policy_override_freezes_payload_and_dispatch_snapshot_ref`（F2）
- `test_submit_followup_without_ordinary_baseline_fails_before_dispatch`（F3）

## Verdict

**PASS**。Blocking count = 0。

Controller adjudication 要求的三项 fixes 均已完成：
1. F1（projection helper 抽取）：旧三处重复逻辑已清除，统一复用 `_execution_config_projection.py`，payload shape / digest / ref / public API / state machine 不变。
2. F2（agent_policy override 覆盖）：focused test 覆盖 agent_policy 独立 partial merge + freeze + dispatch snapshot ref。
3. F3（baseline=None fail-early）：focused test 覆盖低层路径缺少 baseline 时的 `INVALID_STATE` 早失败。

未引入新 correctness、stability 或 maintainability blocker。

## Residual Risks

- 无新增 residual risk。原有 residual risks（Slice 5/6 范围）不变。

## Artifact Path

`docs/reviews/phase10-5-slice3-rereview-mimo-20260518.md`
