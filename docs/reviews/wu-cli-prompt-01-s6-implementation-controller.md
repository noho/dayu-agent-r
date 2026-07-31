# WU-CLI-PROMPT-01 S6 Implementation

- Work unit: `WU-CLI-PROMPT-01`
- Gate: `implementation`
- Slice: `S6 — README contract synchronization`
- Owner: `controller`
- Timestamp: `2026-07-31 19:17:56 +0800`
- Prerequisite accepted commit: `d6f786d0`

## README 更新约束判定

修改前已完整读取根 `README.md` 与 `tests/README.md`。根 README 只面向最终用户同步已落地的
CLI 日志参数、组合规则和日志目的地准备要求；tests README 只记录当前测试事实与运行边界。
没有写入 work unit、review 过程、Host/Engine 内部状态机或未落地能力。

## 修改文件

- `README.md`
  - 列出七个日志等级，以及 `warn` / `warning` 两种等价公开写法。
  - 列出八个快捷参数并保留 `--warn`。
  - 说明所有等级 selector 彼此互斥；debug-stream 不改变普通等级、可与非 quiet 等级组合且
    不可与 quiet 组合；log-file 与合法等级选择独立。
  - 明确 log-file 不创建父目录，父目录缺失或目标无法打开时在分析开始前 exit 1。
- `tests/README.md`
  - 更新两个公开入口共用轻量 bootstrap 与 startup `KeyboardInterrupt -> 130` 的测试事实。
  - 更新 strict UTF-8 invocation、typed usage/resource error 与 pre-primary zero-call 测试事实。
  - 更新完整 selector、跨 parser scope、debug-stream/quiet/log-file 组合矩阵，以及新的
    `configure_selected_diagnostics` 接线事实。
  - 修正 prompt 快速重复 Ctrl+C 的描述为等待 terminal 后退出，同时保留 interactive 的既有
    二次 Ctrl+C 本地退出测试事实；补充 cancelled UI 不展示内部 reason。
  - 更新 runtime ordinary/stream admission、quiet 与 root/namespace gate/filter 测试事实。

## 验证

- 根 README 的 prompt 日志示例 argv 已由当前 `parse_cli_args` 成功解析。
- `rg` 确认旧 `set_level_from_flags`、debug-stream 同时打开普通 DEBUG、prompt 第二次 Ctrl+C
  terminal 前本地退出的描述均已消失。
- `git diff --check`：通过。

## Scope 判定

只修改 accepted plan 允许的 `README.md`、`tests/README.md` 与本 implementation artifact；没有
修改生产代码、测试、冻结 oracle/scenario 或其它 README。

## Gate 结论

S6 文档同步完成，进入独立 `deepreview` gate。
