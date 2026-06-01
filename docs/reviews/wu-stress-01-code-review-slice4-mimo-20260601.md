# Code Review

## Scope

- Mode: current changes
- Branch: test/host-stress-suite
- Base: main (f558eae)
- Output file: docs/reviews/wu-stress-01-code-review-slice4-mimo-20260601.md
- Included scope: tests/host/stress_support.py, tests/host/test_host_production_stress.py (uncommitted Slice 4 diff only)
- Excluded scope: production code, Slice 5 behavior, design/control docs, commits/push/PR
- Parallel review coverage: 无

## Conclusion

**PASS** — 未发现影响 correctness、stability 或可维护性的实质性问题。

## Findings

### 01-未修复-低-InspectableStressWorkerFactory.wait_accepted_run 为死代码

- **入口/函数**: `InspectableStressWorkerFactory.wait_accepted_run`
- **文件(行号)**: tests/host/stress_support.py:614-639
- **输入场景**: 任何调用路径
- **实际分支**: 该方法已定义但从未被测试或其他 helper 调用
- **预期行为**: plan 要求"按 Run 等待 accepted"诊断入口；测试实际使用 `_wait_accepted_count` 和 `_submit_followup_waiting_for_accept` 实现相同语义
- **实际行为**: `wait_accepted_run` 存在但无调用方
- **直接证据**: `grep -rn "wait_accepted_run" tests/` 仅命中定义行；测试使用 `_wait_accepted_count` 轮询 accepted count 替代
- **影响**: 不影响 correctness，但增加维护负担；后续修改可能误以为该方法有调用方
- **建议改法和验证点**: 删除 `wait_accepted_run`，或在测试中替换 `_wait_accepted_count` 路径以使用该方法；删除后运行 `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q` 确认通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-跨模块重复常量与 helper

- **入口/函数**: 模块级常量与 `_is_terminal_status`
- **文件(行号)**: tests/host/test_host_production_stress.py:108-112 与 tests/host/stress_support.py:101-104, 1328-1341
- **输入场景**: 无；结构问题
- **实际分支**: 无
- **预期行为**: 常量与 helper 优先复用已有定义，避免跨模块不一致
- **实际行为**: `_EVENT_TYPE_RUN_SUCCEEDED`/`_EVENT_TYPE_RUN_FAILED`/`_EVENT_TYPE_RUN_CANCELLED`/`_HOST_DB_FILENAME` 在 stress_support.py 已定义，test 文件重复定义；`_is_terminal_status` 在 test 文件定义，语义与 stress_support.py 的 `_is_public_run_terminal` 重叠（仅类型不同：`RunStatus` vs `HostTerminalStatus`）
- **直接证据**: test_host_production_stress.py:108-112 重复定义 `_EVENT_TYPE_RUN_*` 和 `_HOST_DB_FILENAME`；test_host_production_stress.py:1873-1886 定义 `_is_terminal_status`
- **影响**: 不影响 correctness，但增加维护时两个位置需同步的风险
- **建议改法和验证点**: 将 `_EVENT_TYPE_RUN_*` 和 `_HOST_DB_FILENAME` 改为从 stress_support.py import；将 `_is_terminal_status` 改为调用 stress_support.py 中的同语义 helper 或移入 stress_support.py；运行 pyright 和 stress 测试确认
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Validation

已独立验证：

```bash
# Slice 4 targeted stress
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k scheduler_liveness -q
# 结果: 1 passed, 3 deselected (1.15s)

# Full stress suite
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
# 结果: 4 passed (4.73s)

# Pyright
python -m pyright dayu/ tests/ utils/
# 结果: 0 errors, 0 warnings, 0 informations
```

回归测试：

```bash
pytest tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py tests/host/test_public_cancel_session_runs.py -q
# 结果: 1 failed, 74 passed
# 失败的 test_memory_lag_pre_dispatch_failure_does_not_enter_recovering 是 pre-existing flaky test
# 已通过 git stash 验证：在不含 Slice 4 改动的 clean state 上同样失败
# 单独运行该测试时通过，属于测试隔离问题，非 Slice 4 引入
```

## Evidence Summary

Slice 4 实现正确覆盖 plan 要求的所有场景：

1. **正确性**: 测试名、场景常量、行为脚本、诊断断言均与 plan Slice 4 对齐
2. **确定性**: 使用 release gate 控制 blocking final，poll interval 固定，无随机或不可控 sleep
3. **公共证明链**: `wait_all_runs_terminal` 仅用 `Host.get_run()`；`verify_lane_released` 通过独立 LaneController 公共 acquire/release 证明容量可用；`read_host_instances` 为 fresh short-read 诊断
4. **Scheduler/liveness 语义**: `scheduler_drained` 检查 snapshot terminal + handle close + 无 clean recovery 增量；`liveness_stale_detected` 检查 intentional crash 计数 + stale instance + 无 clean close 误判
5. **Lane release**: `verify_lane_released` 使用 `timeout_seconds=0` 非阻塞 acquire，`_LANE_CLAIM_TTL_SECONDS` 和 `_LANE_HEARTBEAT_INTERVAL_SECONDS` 与 Host 使用的常量一致
6. **RUN_LOST 处理**: `_is_public_run_terminal` 正确包含 `RunStatus.LOST`；`_terminal_event_count_for_runs` 正确包含 `RUN_LOST` event type；`stream_exception_closeout_ok` 验证 `_SLICE4_EXPECTED_LOST_COUNT == 1`
7. **Terminal dedupe**: `terminal_dedupe_ok` 检查 duplicate == 0 且 all_terminal_event_count == public snapshot count
8. **Docstrings/types**: 所有新增类型、函数、dataclass 均有完整中文 docstring（参数、返回值、异常）；无 `Any`、`object`、无类型参数或返回值
9. **无生产代码**: diff 仅涉及 tests/host/ 下的两个文件
10. **无 Slice 5**: 未引入 `HostStressScenario` 或 mixed deterministic fault injection 场景

## Open Questions

无。

## Residual Risk

- `read_host_instances` 使用 1.0 秒 stale 阈值（`_HOST_INSTANCE_STALE_AFTER_SECONDS`）。该值在 CI 机器或高负载环境下可能产生误判；但 recovery truth 来自 Host recovery scanner 和 EventLog facts，本 helper 仅为诊断视图，不影响正确性。
- Stress 测试是确定性有界场景，非随机 fuzz 或长时间 soak。90 秒超时预算内稳定通过（实测 1.15 秒）。
- `RUN_LOST` 不是 `HostTerminalStatus`，因此 Slice 4 通过 `_terminal_event_count_for_runs` 单独统计包含 `RUN_LOST` 的 terminal EventLog 数，与 public snapshot 数交叉验证。这是正确处理，但若未来 `HostTerminalStatus` 新增 `LOST` 成员，需同步更新。
