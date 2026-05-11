# P8.5 Slice 5a Code Review

- **review gate name**: code review
- **work unit**: P8.5 — P8 Stabilization / ToolRuntime Event Model
- **assigned slice**: Slice 5a — Attempt Lease Diagnostic Corrections
- **approved plan**: `docs/host/phase8.5-plan.md`
- **implementation artifact**: `docs/host/phase8.5-s5a-implementation-report.md`
- **reviewed target**: current uncommitted changes after Slice 4 commit `242f12a`
- **artifact path**: `docs/host/phase8.5-s5a-code-review.md`

## Reviewer Conclusion

**pass-with-risks**

本 slice 的核心实现满足 approved plan 中 Slice 5a 的范围：run id mismatch 已有独立
`RUN_ID_MISMATCH`，BUSY result 在 store typed result 层不再复用 fencing reason，
`lease_context` 在 acquire 前完成参数校验，`next_attempt_index()` 的独立测试覆盖了计划要求的场景。

保留一个非阻塞诊断风险：`AttemptSupervisor._require_acquired()` 仍把 BUSY acquire 失败折叠为
`AttemptFencingError(reason=STORAGE_CONFLICT)`。在“不改 public Host API / 不新增 busy exception contract”的
Slice 5a 边界内可以接受，但它会让 supervisor 层日志与异常缺少 `busy_reason` 细节，后续若继续收敛 attempt
diagnostics，应优先处理。

## Findings

未发现需要当前 slice 修复的 blocking code review finding。

## Evidence

- `AttemptFencingReason.RUN_ID_MISMATCH` 已新增，`AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT` 已新增；
  `AttemptLeaseResult.reason` 文档明确 `BUSY` 时为 `None`，`busy_reason` 独立表达 BUSY 业务冲突：
  `dayu/host/_attempt_lease.py:200-245`。
- `AttemptScopedRunEventAppender._verify_run_id_value()` 对 `run_id != owner_context.run_id` 抛
  `AttemptFencingError(reason=AttemptFencingReason.RUN_ID_MISMATCH)`：
  `dayu/host/_attempt_supervisor.py:453-481`。
- `lease_context()` 在生成 owner token、attempt id 与进入 acquire transaction 前调用
  `_validate_lease_context_args()`；该 helper 拒绝空 `run_id`、负数 `attempt_index`、空串
  `recovered_from_attempt_id`：`dayu/host/_attempt_supervisor.py:128-149`、
  `dayu/host/_attempt_supervisor.py:578-620`。
- `AttemptLeaseStore._build_busy_result()` 的 BUSY 返回路径均设置 `reason=None` 与
  `busy_reason=AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT`：
  `dayu/host/_run_state_store.py:1217-1262`。
- `RunStateStore.next_attempt_index()` 当前实现为 `MAX(attempt_index) + 1`，空集返回 `0`：
  `dayu/host/_run_state_store.py:933-952`。
- `next_attempt_index()` 测试覆盖无 attempt、active、terminal、gap/conflict：
  `tests/host/test_phase8_attempt_lease_store.py:246-356`。
- BUSY 诊断测试断言 `reason is None` 且 `busy_reason is ATTEMPT_INDEX_CONFLICT`：
  `tests/host/test_phase8_attempt_lease_store.py:1061-1101`。
- run id mismatch 测试覆盖普通 `append()` 与 `append_in_transaction()`，均断言
  `RUN_ID_MISMATCH`：`tests/host/test_phase8_attempt_fencing.py:493-512`、
  `tests/host/test_phase8_attempt_fencing.py:768-792`。
- `lease_context` 参数校验测试覆盖三类非法输入，并确认 acquire 前没有写入 `host_attempts`：
  `tests/host/test_phase8_attempt_supervisor.py:760-803`。
- `AttemptSupervisor._require_acquired()` 的 BUSY 折叠风险有直接证据：当 `result.reason is None` 时映射到
  `AttemptFencingReason.STORAGE_CONFLICT`，对应测试也固定了该行为：
  `dayu/host/_attempt_supervisor.py:961-1003`、
  `tests/host/test_phase8_attempt_supervisor.py:731-755`。
- 没有发现 public Host API 变更：diff scope 不含 `dayu/host/__init__.py`，且 `dayu/host/__init__.py` 未导出
  `AttemptLeaseBusyReason` / `AttemptFencingReason` / `AttemptLeaseResult` / `AttemptSupervisor`。
- 没有发现 `dayu.runtime` 泄漏：当前 slice 生产代码只在 `_attempt_lease.py` 模块 docstring 中声明 attempt
  lease 不属于 `dayu.runtime`，未新增 runtime import。
- README 与代码一致：Host README 中 attempt-scoped append 的 run id mismatch reason 已同步为
  `RUN_ID_MISMATCH`：`dayu/host/README.md:207-210`、`dayu/host/README.md:404-408`。

## Open Questions

无阻塞 open question。

## Residual Risk

### R1-[低]-supervisor acquire BUSY 异常仍显示 STORAGE_CONFLICT

- **入口/函数**: `AttemptSupervisor.lease_context()` -> `_require_acquired()`
- **文件(行号)**: `dayu/host/_attempt_supervisor.py:961-1003`
- **输入场景**: acquire 新 attempt 时命中同一 `(run_id, attempt_index)` 业务冲突，store 返回
  `AttemptLeaseResult(decision=BUSY, reason=None, busy_reason=ATTEMPT_INDEX_CONFLICT)`。
- **实际分支**: `_require_acquired()` 因 `result.reason is None` 将 reason 置为
  `AttemptFencingReason.STORAGE_CONFLICT`。
- **预期行为**: Slice 5a 明确要求 BUSY result 不复用 fencing reason，且不要求新增 public exception contract。
- **实际行为**: store 层 typed result 满足要求；supervisor 层异常和日志仍丢失 `busy_reason`，显示为
  `STORAGE_CONFLICT`。
- **直接证据**: `dayu/host/_run_state_store.py:1236-1262` 返回独立 `busy_reason`；
  `dayu/host/_attempt_supervisor.py:982-999` 将空 `reason` 折叠为 `STORAGE_CONFLICT`；
  `tests/host/test_phase8_attempt_supervisor.py:750-755` 当前断言该折叠行为。
- **影响**: 仅诊断精度风险；不会导致错误 owner 获取 lease，也不会复用 fencing reason 写入
  `AttemptLeaseResult`。
- **建议改法和验证点**: 后续 slice 若允许调整 internal supervisor diagnostic contract，可在日志中记录
  `busy_reason`，或引入不改变 public Host API 的内部 busy acquire error/result 表达；验证 BUSY 日志与异常诊断不再误导为 storage conflict。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **controller decision status**: pending-controller-decision

## Validation

- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_recovery.py -q`
  - 结果：通过，`44 passed in 0.47s`
- `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_lease_store.py -q`
  - 结果：通过，`29 passed in 0.16s`
