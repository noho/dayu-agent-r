# WU-CLI-PROMPT-01 S1 Implementation

- Work unit: `WU-CLI-PROMPT-01`
- Gate: `implementation`
- Slice: `S1 — Cancelled UI projection`
- Owner: `controller`
- Timestamp: `2026-07-31 18:27:00 +0800`
- Accepted plan commit: `a394f831`

## 实现范围

本 slice 只修复 `prompt.cancel-closeout-reason-ui-leak`。公共 CLI terminal-result projection 是用户可见取消语义的唯一 owner；Host terminal result 中的 typed `cancel_reason` 继续作为内部诊断事实保留，UI 不再解释或展示该字段。

## 修改文件

- `dayu/cli/output.py`
  - 将 prompt 与 interactive 的 cancelled terminal projection 统一为固定、用户可理解的 `Cancelled.`。
  - 删除对 `CLI_SIGINT_REASON` 的展示层依赖和 raw-reason fallback。
  - `_public_cancel_message()` 不再接收内部 reason，从类型边界保证所有内部 reason 都不能进入公共 UI。
- `tests/cli/test_output.py`
  - owner-level contract 覆盖空 reason、已知 SIGINT reason、watchdog closeout reason 和未知未来 reason。
  - 同时断言 prompt/interactive 的公共文案、退出码以及内部 reason 不泄漏。
- `tests/cli/test_interactive_command.py`
  - 将直接消费旧 raw reason 的集成断言迁移到公共 UI contract；不改变 interactive 生命周期语义。

## 语义决策

没有使用 reason 字符串黑名单、白名单或兼容分支。UI projection 对 cancelled terminal state 只承诺用户语义；typed reason 的产生、持久化与诊断仍由 Host/runtime owner 负责。因此新增或未知 reason 也不会泄漏，且 durable EventLog 不受影响。

## 验证证据

1. `pytest tests/cli/test_output.py --cov=dayu.cli.output ...`
   - `8 passed`。
   - 由于 `output.py` 同时承载多个无关 CLI projection，单测集合的模块覆盖率为 40%，不能代表受影响模块整体覆盖。
2. 首次完整 `tests/cli` 回归暴露一项旧测试仍期望 raw interactive reason；这是 owner contract 迁移所需的直接消费者测试，已同步更新。
3. `pytest tests/cli/test_output.py tests/cli/test_interactive_command.py::test_interactive_failed_and_cancelled_continue_until_eof`
   - `9 passed`。
4. `pytest tests/cli --cov=dayu.cli.output ...`
   - `722 passed, 7 skipped`。
   - `dayu/cli/output.py` 覆盖率 `93%`。
5. `pyright dayu/cli/output.py tests/cli/test_output.py tests/cli/test_interactive_command.py`
   - `0 errors, 0 warnings, 0 informations`。

## README 判定

本 slice 没有新增或改变 CLI 命令、参数、输出通道、日志位置或用户工作流；只是将本就不应公开的内部 reason 修正为稳定取消文案。README 触发检查留在已计划的 S6 聚合处理。

## 残余风险与后续验证

- 本 slice 仅证明 projection owner 不泄漏内部 reason；真实 Ctrl+C 时序、Host terminal state、SQLite/EventLog 证据由 S2 与最终 frozen scenario 重放验证。
- 当前没有修改 Host typed reason、EventLog 或 cancellation lifecycle。

## Gate 结论

S1 实现和受影响测试完成，进入独立 `deepreview` gate。
