# WU-PROJ-01 S3/S4 Code Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: S3/S4 code review
- Date: 2026-06-11
- Controller: Phaseflow
- Review artifacts:
  - `docs/reviews/wu-proj-01-s3-s4-code-review-mimo.md`
  - `docs/reviews/wu-proj-01-s3-s4-code-review-ds.md`

## 结论

S3/S4 code review accepted。无需 fix gate。

AgentMiMo 与 AgentDS 均裁决 `PASS`，无 blocking findings。AgentMiMo 的两个 informational findings 不改变行为、测试稳定性或可维护性要求，当前 PR 不需要额外修复。

## Findings 裁决

| Finding | 来源 | 裁决 | 理由 |
|---|---|---|---|
| `_read_memory_checkpoint_sequence` helper 命名可与既有 pattern 更一致 | AgentMiMo NF-1 | rejected-with-reason | 当前命名直接表达读取 memory checkpoint sequence 的测试意图，类型与中文 docstring 完整；不影响正确性，也不值得为风格 churn 修改。 |
| S3 与 S4 都使用 `lane_default_timeout_seconds=1.0` 可能让 grep flaky 修复时混淆 | AgentMiMo NF-2 | rejected-with-reason | S3/S4 都是 dispatch scheduler 集成测试，1.0s 是测试专用 lane acquire 稳定窗口；S3 使用该值是为了避免新 happy-path 测试引入同类无关 timing 风险，不需要额外注释或拆分。 |

## 关闭依据

- S3-R1：新增 `test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input`，覆盖 checkpoint 已覆盖 required cursor 时 dispatch 内部 catch-up 不重复扫描、ordinary RunInput 构造、worker accepted，且不进入 `RUN_FAILED` / `RUN_RECOVERING`。
- S4-R1：`test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 使用测试专用 `lane_default_timeout_seconds=1.0`，避免无关 10ms lane acquire 窗口；原 fallback artifact、第二次 dispatch request、Attempt 数量、无 `CONTEXT_COMPACTED`、无 `RUN_LOST` 等断言全部保留。

## 验证

总控复验：

- `python -m pytest tests/host/test_dispatch_scheduler.py` -> 68 passed
- `pyright` -> 0 errors
- `git diff --check` -> passed

## 后续

`WU-PROJ-01-S3-R1` 与 `WU-PROJ-01-S4-R1` 从 active residual risk 表移除。
