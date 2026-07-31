# WU-CLI-PROMPT-01 S5 Implementation

- Work unit: `WU-CLI-PROMPT-01`
- Gate: `implementation`
- Slice: `S5 — Complete logging selector and debug-stream contract`
- Owner: `controller`
- Timestamp: `2026-07-31 19:07:03 +0800`
- Prerequisite accepted commit: `d847d593`

## Root cause 与语义 owner

旧 CLI parser 只暴露部分日志等级，快捷项写入同一最终字段但没有跨 root、command、action
scope 的 occurrence truth，因而无法稳定判断重复或冲突 selector；`quiet` 还被错误归约为
`error`。公开 invocation grammar 与 canonical spelling 的唯一 owner 是
`dayu.cli.arg_parsing`。

旧 runtime helper 同时接收显式字符串与多组布尔 flag，并按优先级把 `debug_stream` 直接改写为
最低数值 level。这会连带放出普通 DEBUG/VERBOSE，违反 stream 诊断与普通阈值正交的 contract。
canonical diagnostic level 到 stdlib threshold 的映射，以及 handler admission rule 的唯一 owner
是 `dayu.runtime.log`；共享整数 level 真源仍是 `dayu.runtime.log_levels`。

## 修改文件

- `dayu/cli/arg_parsing.py`
  - 以 `DiagnosticLogLevel` 保存七个 canonical 等级，公开 spelling map 只在输入边界把
    `warn` 与 `warning` 收敛为 `WARNING`。
  - 从同一 option spec 注册 `--log-level` 八种 spelling 和八个快捷项。
  - root、command、action 分别收集 typed occurrence；公共 finalizer 合并三份事实并拒绝任何
    两次 selector，包括相同入口重复与跨 scope 组合。
  - `--debug-stream` 保持在 selector 组外，允许与全部非 quiet selector 组合且不改写普通等级；
    quiet 组合在 parser 边界 exit 2。`--log-file` 继续独立。
  - 每次 invocation 创建三份新 list，parser/action 不保存跨调用 mutable collector。
- `dayu/cli/main.py`
  - 删除旧多 flag helper 接线，只把 canonical level、debug-stream 与目标 stream 传给 runtime。
  - 日志文件 cleanup 恢复 stderr 时保留同一 canonical level/debug-stream 事实。
- `dayu/runtime/log.py`
  - 新增七值 `DiagnosticLogLevel`；numeric `LogLevel` 使用 `WARNING` 与显式 `QUIET`，不保留
    `WARN` compatibility alias。
  - 删除 `set_level_from_flags` 与旧 priority resolver，新增朴素
    `configure_selected_diagnostics`。
  - `configure` 以 ordinary threshold 和 debug-stream 两个正交事实装配：开启 stream 时只把
    logger/handler gate 下调到 `STREAM_DEBUG`，handler filter 精确放行 stream record，并仍按
    ordinary threshold 过滤普通 record。
  - quiet 显式拒绝所有普通 record；quiet+stream 在改动 logger 状态前 fail closed；root
    装配复用同一 admission rule。
- `dayu/runtime/log_levels.py`
  - 新增 `QUIET_LOG_LEVEL = CRITICAL_LOG_LEVEL + 1` 作为共享数值真源。
- `tests/cli/test_arg_parsing.py`
  - 覆盖 16 个公开 selector、16×16 有序冲突、跨三层 scope、同 parser fresh namespace、
    debug-stream 的 14 个非 quiet 组合、quiet 冲突四种顺序、log-file 全组合与 main cleanup
    接线。
- `tests/runtime/test_log.py`
  - 覆盖七个 canonical 映射、ordinary/stream admission 矩阵、info+stream、quiet/critical、
    quiet+stream、root、gate、幂等和第三方 WARNING suppression。
- `tests/fins/test_sec_downloader.py`
  - 两处直接消费 numeric enum 的测试随 canonical member rename 改用 `LogLevel.WARNING`；没有
    修改 Fins production 或产品行为，也没有恢复旧 alias。

## Scope 判定

修改只位于 accepted plan 指定的公共 parser/config/runtime owner 及直接测试消费者。没有新增
prompt-only shim、argv 字符串扫描、logger namespace、业务 logging call site 或 Host/Engine
行为。Fins 测试的两行机械迁移是删除明确禁止的 `WARN` alias 后的必要受影响测试同步，不改变
S5 产品范围。

## 验证证据

1. 公共 parser owner：
   - `pytest -q tests/cli/test_arg_parsing.py`
   - `413 passed`。
2. runtime 与直接 numeric enum 消费者：
   - `pytest -q tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/fins/test_sec_downloader.py`
   - `164 passed`。
3. 全部 CLI 回归（含 Fins CLI）：
   - `pytest -q tests/cli`
   - `1047 passed, 7 skipped`；skip 均为既有条件 skip。
4. S5 合并覆盖率：
   - `pytest -q tests/cli/test_arg_parsing.py tests/runtime/test_log.py tests/runtime/test_log_levels.py --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov=dayu.runtime.log --cov=dayu.runtime.log_levels --cov-report=term-missing`
   - `530 passed`；`arg_parsing.py 99%`、`main.py 94%`、`runtime/log.py 100%`、
     `runtime/log_levels.py 100%`。
5. 定向静态类型：
   - `pyright dayu/cli/arg_parsing.py dayu/cli/main.py dayu/runtime/log.py dayu/runtime/log_levels.py tests/cli/test_arg_parsing.py tests/runtime/test_log.py tests/fins/test_sec_downloader.py`
   - `0 errors, 0 warnings, 0 informations`。
6. `git diff --check`：通过。

## README 判定

用户可见 selector、debug-stream 与 quiet contract 已变化，根 README 与 tests README 均命中更新
触发；按 accepted plan 在 S6 先读取各自 Agent 更新约束后统一同步，不在本 slice 扩写文档。

## 残余风险与后续验证

- 当前 owner/unit/integration matrix 已完整覆盖 grammar 与 runtime admission；最终仍需从冻结
  registry 重放 PC-LS 32、PC-DS 15、PC-DQ 4、PC-LC 256 的真实 CLI argv，并核对 exit、screen、
  filesystem、SQLite、EventLog/Tool Trace 与 primary-operation 副作用。
- 本 slice 执行了定向 pyright；完整仓库 pyright 留在 aggregate/final gate。

## Gate 结论

S5 实现与验证完成，进入独立 `deepreview` gate。
