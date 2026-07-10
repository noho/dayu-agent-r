# WU-SEMANTIC-OWNERSHIP-01 P3-E S2 Fix - AgentCodex

## 状态

ready-for-controller-validation

## Finding closure

### P3-E-S2-CR-F01 - 已修复

要求：直接测试 `event_payload_unavailable -> LOST`。

处理结果：

- 在 `tests/host/test_accepted_result_projection.py` 新增 focused test：
  - `test_projection_missing_event_payload_maps_lost_with_diagnostic`
- 测试构造：
  - 先写入合法 SQLite payload descriptor；
  - descriptor 指向的 payload JSON 是 list，不是 EventLog payload object；
  - `TOOL_RESULT_ACCEPTED` EventLog row 使用该 descriptor 作为自身 payload；
  - `project_accepted_tool_result(...)` 读取 EventLog payload 时进入 `_result_event_payload(...)` 的 `HostDurableError` 捕获路径。
- 断言：
  - `projection.status is AcceptedToolResultStatus.LOST`
  - `"event_payload_unavailable" in projection.diagnostic_reasons`
- 既有 `result_payload_unavailable` 测试保持不变。

未修改生产代码。首次尝试用缺失 descriptor 构造不可用 payload 时被 durable foreign key 拦截，说明缺失 descriptor 不是合法到达 projection owner 的 fixture；最终改为合法 descriptor + 非 object payload，使错误发生在 projection payload 读取边界。

## Owner boundary

`event_payload_unavailable` 的 owner 是 Host accepted-result projection：

- durable EventLog row 是已提交事实；
- `_result_event_payload(...)` 负责把 row payload 解析为 accepted result payload object；
- 当 EventLog payload 本身不可读或不是 object 时，projection owner 产生 `event_payload_unavailable`；
- `_accepted_status(...)` 基于该 owner diagnostic 映射 `AcceptedToolResultStatus.LOST`；
- 下游消费者只消费 projection，不自行解释损坏 EventLog payload。

本 fix 只补 owner boundary 的测试证明，没有在下游消费者或展示层加特例。

## Validation commands/results

```bash
source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py -q
```

结果：`17 passed in 0.39s`

```bash
source .venv/bin/activate && pytest tests/service/test_wait_callback_endpoint.py tests/host/test_accepted_result_projection.py tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_projection_read_model.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py -q
```

结果：`312 passed in 1.68s`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

备注：pyright 输出同时提示有新版本可用：`v1.1.409 -> v1.1.411`，不影响当前检查结果。

```bash
git diff --check
```

结果：通过，无输出。

## README decision

本次只新增 `tests/host/test_accepted_result_projection.py` 中 accepted-result projection 的 focused diagnostic 测试。`tests/README.md` 已记录 Host accepted result projection 覆盖 accepted 工具结果 query / status / source typed projection、payload digest / descriptor 诊断和 cross-consumer equivalence；新增单个 diagnostic branch 不改变测试分层或公共运行方式，因此无需继续更新 README。

根 README、`dayu/README.md`、`dayu/host/README.md` 不涉及最终用户 workflow、架构边界或 Host public contract 描述变化，均无需更新。

## Residual risk

- 无新增 residual risk。
- 既有 S2 residual risk 仍然成立：`UNKNOWN` 的产品展示策略若需要区别于 failed/error，应作为后续 projection/display policy work unit 处理，不能恢复 raw outcome status reconstruction。

