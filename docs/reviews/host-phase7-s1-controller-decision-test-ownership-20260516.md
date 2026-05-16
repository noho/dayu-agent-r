# Host Phase 7 P7-S1 Controller Decision - Test Ownership - 2026-05-16

## 结论

Controller 裁决：允许 P7-S1 修改 `tests/host/test_public_run_api.py`，仅限更新旧 `ResolveWaitRequest` 构造为
typed outcome envelope 与 UTC-aware `datetime`。

## 理由

P7-S1 的核心目标是删除 `ResolveWaitRequest.outcome_ref: str`，替换为 `outcome: ResolveWaitOutcome`，并把
`observed_at` 改为 UTC-aware `datetime`。`tests/host/test_public_run_api.py` 当前仍构造旧 request shape，且 P7-S1
验证要求包含 `python -m pyright dayu/host tests/host`。如果不允许更新该测试文件，实现 agent 只能选择两种错误路径：

- 保留旧 `outcome_ref` 兼容入口；
- 缩窄 pyright 验证范围，绕过 `tests/host` 中的真实类型错误。

两者都违反总控约束与已通过的 Phase 7 plan。

## Scope

本裁决只扩大 P7-S1 test ownership：

- 允许修改：`tests/host/test_public_run_api.py`
- 限制：只允许更新 `ResolveWaitRequest` 相关构造、导入与断言，不能提前实现 P7-S3 / P7-S4 的 `resolve_wait` 行为测试。

生产文件 ownership 不变；P7-S1 仍不得实现 ToolRuntime awaiting accept、`resolve_wait` command path、poller 或 EngineEvent ingest。
