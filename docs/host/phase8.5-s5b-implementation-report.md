# P8.5 Slice 5b 实施报告

- **工作 gate**: implementation
- **work unit**: P8.5 — P8 Stabilization / ToolRuntime Event Model
- **assigned slice**: Slice 5b — Attempt Lease / Recovery Adversarial Hardening
- **approved plan**: `docs/host/phase8.5-plan.md`
- **artifact path**: `docs/host/phase8.5-s5b-implementation-report.md`

## 分配范围

本 slice 只处理 approved adversarial coverage 与直接必要的 root-cause fix：

- `_renew_loop` 并发竞争：renew vs terminal/owner-lost race、第一 owner-lost reason 不被 late renew 覆盖、storage exception 分类为 `STORAGE_ERROR` 且不泄漏 background task exception。
- recovery CAS miss 不得关闭或覆盖新 owner。
- owner-lost late Engine event 不得追加 attempt-scoped EventLog。
- terminal override 不得覆盖既有 terminal truth。
- Slice 1 后不恢复 cursor facts；expired/denied fencing 通过普通 `fetch_more` failed outcome 与 attempt-scoped generic tool call path 覆盖。

明确未做：

- 未实现 production process supervisor。
- 未实现 P9 lifecycle admission。
- 未恢复 cursor/truncation/fetch_more special RunEvents。
- 未进入 Slice 6、commit、PR 或 closeout。

## 修改文件

- `dayu/host/_attempt_supervisor.py`
- `tests/host/test_phase8_attempt_supervisor.py`
- `tests/host/test_phase8_attempt_fencing.py`
- `tests/host/test_phase8_attempt_recovery.py`
- `tests/host/test_phase8_tool_runtime_fencing.py`
- `docs/host/phase8.5-s5b-implementation-report.md`

## 已实现计划项

- `_renew_loop` 在 renew 返回 `ACQUIRED` 后再次检查 session 是否已 owner-lost；若已失活，保留第一 loss reason 并退出，不用 late renew 刷新 session owner context。
- 新增 renew late-success adversarial test，覆盖 owner-lost 第一原因不被 late renew 覆盖。
- 扩展 storage error 测试，断言 renew task 正常完成且 `exception()` 为 `None`，避免 background task exception 泄漏。
- 新增 terminal override adversarial test，断言已有 `SUCCEEDED` terminal truth 时，后续 `LOST` override 被 `ATTEMPT_TERMINAL` fencing 拒绝，EventLog 与 attempt state 不被覆盖。
- 扩展 recovery CAS miss 测试，模拟 scan 与 mark 之间 owner token、owner id、fencing token 被替换，断言 recovery 返回 `NOOP_TERMINAL` 且新 owner 字段保持不变。
- 新增 ToolRuntime generic tool call fencing 测试，断言 durable owner verify 在业务工具调用前拒绝，业务 executor 不被调用且不写 EventLog。
- 新增 expired `fetch_more` 普通 failed outcome 测试；既有 wrong-scope test 继续覆盖 denied fencing，不恢复任何 cursor special facts。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_recovery.py tests/host/test_phase8_tool_runtime_fencing.py -q`
  - 结果：通过，`55 passed in 0.50s`
- `source .venv/bin/activate && pytest tests/host/test_phase8_multiprocess_stress.py -q`
  - 结果：通过，`4 passed in 1.60s`
- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`

## 文档决策

未更新 README。

理由：本 slice 是 Host 内部 lease/recovery adversarial hardening 与测试补强；未改变 public CLI、配置入口、Host/Engine/Fins 对外接口、README 中的运行方式或开发手册抽象边界。测试命令仍使用 approved plan 中既有 P8/P8.5 validation 命令。

## Plan 缺口 / Controller 问题

未发现阻塞 implementation 的 plan gap。无需 controller 裁决。

## 剩余风险

- **多进程真实 crash supervisor**: 分类为后续 phase/work unit。当前 slice 明确 non-goal，不实现 production process supervisor。
- **P9 lifecycle admission**: 分类为后续 phase/work unit。当前 slice 明确 stop condition，不在本 slice 实现。
- **更大规模随机化 concurrency fuzz**: 分类为后续 phase/work unit。当前已覆盖 approved deterministic adversarial cases 与 P8 multiprocess stress；未新增无界 fuzz harness。

## 完成信号

Slice 5b assigned scope 已完成；required validation 全部通过；未启动 Slice 6；未 commit；未 PR；未 closeout。

## Stop Condition 状态

- Need production process supervisor: 未触发。
- Need P9 lifecycle admission: 未触发。
- Need restore cursor/truncation/fetch_more special RunEvents: 未触发；按 plan 保持 non-goal。
