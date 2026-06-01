# WU-STRESS-01 Slice 2 Code Review Artifact

## Gate

- **Gate**: implementation-review
- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Review role**: AgentDS, code review specialist
- **Review target**: 当前工作区未提交的 Slice 2 diff
- **Accepted plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- **Implementation artifact**: `docs/reviews/wu-stress-01-implementation-slice2-codex-20260601.md`
- **Slice 1 accepted commit**: `ffcc7e5`
- **Review artifact**: `docs/reviews/wu-stress-01-code-review-slice2-ds-20260601.md`

## Reviewed target

| File | Change type | Lines |
|------|-------------|-------|
| `tests/host/stress_support.py` | Slice 2 新增 | ~250 lines (diff) |
| `tests/host/test_host_production_stress.py` | Slice 2 新增测试 | ~280 lines (diff) |
| `tests/README.md` | 未修改 | 0 lines |

未修改其他文件。Production code（`dayu/host/**`、`dayu/engine/**` 等）无变更。

## Conclusion: PASS

Slice 2 实现正确覆盖了 plan 要求的全部验证点：3 轮 deterministic crash/reopen recovery、live owner probe 防误恢复、attempt_count/recovery_count/terminal duplicate 断言均可靠。无生产代码越界，未实现 Slice 3-5 内容。类型安全、docstring 完整，复用 recovery_support 而非复制逻辑。

发现 4 个 findings（0 个 BLOCKING，1 个 HIGH，2 个 MEDIUM，1 个 LOW），均非 correctness 缺陷。建议在 Slice 3-5 实施前处理 HIGH 和 MEDIUM findings。

## Findings

### 001-未修复-HIGH-_slice2_failure_boundary 参数过多，接近 god function

**位置**: `tests/host/test_host_production_stress.py:319-381`

`_slice2_failure_boundary` 有 15 个 keyword-only 参数，每个参数对应一类诊断信号。CLAUDE.md 明确禁止 god function。虽然本函数是私有诊断 helper，但当前签名已接近维护阈值——每新增一类断言就需要增加参数。随着 Slice 3-5 引入 watch lag、scheduler close、liveness stale 等更多诊断维度，该函数会进一步膨胀。

**建议**: 将 `_slice2_failure_boundary` 替换为更聚焦的 per-boundary predicate set，或改为接收 `HostStressSummary` + 局部诊断 dict 的窄接口。也可以在 `HostStressSummary` 上增加 `compute_failure_boundary()` 方法，由 summary 自己携带诊断逻辑。

### 002-未修复-MEDIUM-双重断言路径：failure_boundary 与测试断言存在逻辑重复，增加维护分歧风险

**位置**: `tests/host/test_host_production_stress.py:201-255`

`_slice2_failure_boundary`（行 201-216 调用）和后续 `assert` 语句（行 234-255）对同一组诊断值做了实质上相同的检查。例如：
- `_slice2_failure_boundary` 检查 `recovery_count != _CRASH_CYCLE_COUNT` → `"recovery"`
- 测试断言 `assert recovery_count == _CRASH_CYCLE_COUNT`

两者逻辑耦合但代码独立。如果未来某 slice 修改 `_CRASH_CYCLE_COUNT` 或调整断言语义，需要同时更新两处，否则 failure_boundary 可能返回与实际断言不一致的结果。

**补充观察**: `_slice2_failure_boundary` 未检查 `terminal_observations` 中每条 observation 的 `terminal_status` 是否为 `SUCCEEDED`，而测试断言（行 251-254）做了该检查。目前该差异无害（status 由 event_type 派生，kind 已检查），但体现了双重路径的不完全一致性。

**建议**: 将断言逻辑归一化——要么让 `_slice2_failure_boundary` 成为唯一真源，测试只 assert `failure_boundary is None` 并对非 None 情况输出 summary JSON；要么完全移除 `_slice2_failure_boundary`，让测试断言直接构造 `failure_boundary`。当前做法是两套逻辑并肩运行，违背单一真源原则。

### 003-未修复-MEDIUM-summary 中 watch_lag 与 scheduler_drained 字段硬编码，不反映 Slice 2 真实观测

**位置**: `tests/host/test_host_production_stress.py:224-226`

```python
watch_lag_max=0,
watch_lag_samples=(0,),
scheduler_drained=True,
```

这三个字段在 Slice 2 中未被测量或验证，始终为硬编码常量。Plan 要求在 summary 中包含这些字段，但 plan 的预期是它们在相应的 slice 中被赋予真实诊断值。对 Slice 2 而言，这些字段的硬编码值可能误导后续 reader：如果 Slice 2 测试通过但 scheduler 实际未 drain，summary 仍报告 `scheduler_drained=True`。

**建议**: 对于 Slice 2 未覆盖的字段，在 summary 中使用 sentinel 值（如 `watch_lag_max=-1` 或增加 `watch_lag_measured: bool`）来明确区分"已验证通过"和"未测量"。或者在 `HostStressSummary` docstring 中说明各字段在哪个 slice 中首次获得真实值。Slate 4 实现 scheduler long-run stress 时务必将 `scheduler_drained` 改为实际诊断。

### 004-未修复-LOW-start_and_crash_owner_for_stress 异常路径中 terminate_process 可能被重复调用

**位置**: `tests/host/stress_support.py:737-750`

```python
try:
    accepted = wait_for_accepted_marker(accepted_marker, timeout_seconds)
    terminate_process(owner_process)  # 第一次调用
    ...
    return accepted
except BaseException:
    terminate_process(owner_process)  # 可能第二次调用
    raise
```

如果 `terminate_process`（行 739）因进程无法终止而 raise `AssertionError`，异常被 `except BaseException` 捕获后再次调用 `terminate_process`。第二次调用大概率也会 raise（进程仍无法终止），但原始异常的上下文（是 wait 超时还是 terminate 失败）会丢失。实际影响极小——`terminate_process` 第二次调用的结果会替代第一次异常向上传播，且 terminate 失败在实际运行中极少发生。

**建议**: 在 `except` 分支中仅对仍存活的进程调用 `terminate_process`，并在第二次 terminate 失败时保留原始异常链（`raise ... from exc`）。

## Open questions / residual risk

1. **Probe recovery scan timing**: `_run_live_owner_probe` 假设 probe 子进程的 `open_host` recovery scan 在 `async with` 退出前完成。当前 recovery 测试用同一模式验证了该假设，但如果未来 `StartupRecoveryScanner.scan()` 改为 fire-and-forget 异步任务，probe 的 ATTEMPT_LOST delta 检查可能出现 false negative（scan 在 probe 退出后才完成，delta 延迟出现）。建议在 `HostStressSummary` 或测试 docstring 中记录该时序依赖。

2. **Same-DB shared state**: live owner probe 和 crash cycles 共享同一 `tmp_path` durable store。`_run_live_owner_probe` 在 crash cycles 之前执行并完成释放，不会污染 crash 诊断。但如果未来 slice 调整执行顺序，需要注意 EventLog 中已有 live owner 的 terminal event 会影响 `terminal_events_for_runs` 的计数。

3. **terminal_duplicate_count 语义**: 当前实现将同一 `run_id` 或同一 `event_id` 的重复出现都计为一次 duplicate。如果 EventLog 中存在 ATTEMPT_LOST 后 RUN_RECOVERING 再 RUN_SUCCEEDED 的正常序列，这些事件的 `event_id` 各不相同、`run_id` 相同但在 terminal_events_for_runs 中只筛选 terminal 类型，所以不会触发 duplicate。该语义在 Slice 2 中运行正确，但 Slice 5 mixed stress 中需重新确认。

## Controller decision status placeholder

- [ ] Reviewer findings reviewed by controller
- [ ] Decision: accept / accept-with-fix / rework
- [ ] Target: next gate (Slice 3 implementation or re-review)

## Implementation verification checklist

| Check | Result |
|-------|--------|
| 仅修改 allowed files | PASS |
| 3 轮 crash/reopen recovery 覆盖 | PASS — `_CRASH_CYCLE_COUNT = 3` |
| Live owner probe 不误恢复 | PASS — delta ATTEMPT_LOST=0, delta RUN_RECOVERING=0 |
| attempt_count 断言可靠 | PASS — crashed=2, live=1 |
| recovery_count 断言可靠 | PASS — RUN_RECOVERING count == crash count |
| terminal_duplicate_count == 0 | PASS — durable read + terminal_duplicate_count helper |
| terminal_dedupe_ok is True | PASS |
| durable SQL helper 只做诊断 | PASS — docstring 明确声明，类型安全 |
| 复用 recovery_support 而非复制 | PASS — 薄 wrapper，组合调用 |
| 无 production code 越界 | PASS — 所有变更在 tests/ 下 |
| 未实现 Slice 3-5 | PASS — 无 watch/scheduler/mixed stress |
| docstring 完整 | PASS — 所有新函数中文 docstring，参数/返回值/异常齐全 |
| 强类型，无 Any/object/裸 dict | PASS |
| 超时预算合理 | PASS — 60s timeout, deterministic release gate |
| pyright clean | 实现 artifact 报告 0 errors |
| stress marker + timeout marker | PASS — 继承 Slice 1 marker |
| pytest 默认排除 stress | PASS — 继承 Slice 1 addopts |
| 已有 recovery 测试回归通过 | 实现 artifact 报告 3 passed |
| StressFailureBoundary 封闭类型 | PASS |
| summary_to_json 可用 | PASS |
