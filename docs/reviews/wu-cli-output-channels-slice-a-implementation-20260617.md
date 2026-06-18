# WU CLI Output Channels Slice A Implementation

Gate: Implementation
Work unit: Dayu CLI 输出通道拆分
Slice: A - 全局 `--log-file` 与日志 sink
Branch: `wu-cli-activity-01`
日期: 2026-06-17
执行者: AgentCodex

## Scope

本 slice 只实现全局 `--log-file <path>` 与 runtime diagnostic log sink 切换。未实现 `prompt --detail` / `--no-detail`，未实现 interactive run view。

## Changed Files

- `dayu/cli/arg_parsing.py`
  - `ParsedCliArgs` 增加 `log_file: str | None`。
  - 默认 namespace 设置 `log_file = None`。
  - 全局 parent 增加 `--log-file`，因此支持写在 command 前或 command 后。
- `dayu/cli/main.py`
  - parse 后、日志装配前处理 `args.log_file`。
  - 空白路径返回 `EXIT_USAGE_ERROR`。
  - 以 append + UTF-8 打开日志文件；打开失败返回 `EXIT_USAGE_ERROR` 并写 stderr。
  - 将打开的文件流传给 `runtime_log.set_level_from_flags(...)`。
  - runner 结束、返回错误码、`KeyboardInterrupt` 或未预期异常路径都会进入 `finally`；若打开了日志文件，先恢复 dayu logger 到 stderr handler，再关闭文件。
- `tests/cli/test_arg_parsing.py`
  - 覆盖 `--log-file` command 前后位置。
  - 覆盖默认 stderr stream、文件 stream、打开失败、空白路径 usage error。
  - 覆盖 runner 未预期异常时的恢复 stderr 后关闭文件顺序。
- `tests/cli/test_fins_commands.py`
  - 覆盖 Fins direct `--verbose --log-file` 时诊断进入文件，progress / summary 用户 UI 仍在 stdout/stderr 原通道。
  - 覆盖仅 `--log-file` 不提升默认 INFO level，VERBOSE 诊断仍被抑制。
- `tests/README.md`
  - 按测试手册职责同步新增 CLI main 与 Fins direct log-file 覆盖说明。

未修改 `dayu/runtime/log.py`。现有 runtime helper 已支持 stream override；main 按顺序恢复 stderr handler 后再关闭文件即可避免 dayu logger 持有已关闭文件流。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py`
  - 结果：67 passed, 3 warnings。
  - warnings：来自 `edgar` 依赖 deprecation warning，非本 slice 引入。
- `source .venv/bin/activate && pyright dayu/cli/arg_parsing.py dayu/cli/main.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py`
  - 结果：0 errors, 0 warnings, 0 informations。

## README Decision

- `tests/README.md`：已更新。原因是本 slice 修改并新增了 `tests/cli` 覆盖，且 README 职责明确记录当前测试分层与覆盖面。
- `dayu/README.md`：不更新。原因是本 slice 没有改变 `UI / Service / Host / Engine` 分层关系、装配边界或跨层职责；变更只发生在 CLI composition root 的日志 sink 装配。

## Residual Risks

- 文件并发写同一个 `--log-file` 可能交错：assigned to later work unit。当前 plan 明确不引入文件锁或 tee。
- `--log-file` 不自动创建父目录：fixed in current slice by design。打开失败会返回 usage error，避免拼错路径时静默创建意外目录。
- 仅支持单一 diagnostic sink，不同时 tee 到 stderr 和 file：assigned to later work unit。当前需求只要求改变 sink，不要求复制输出。
- `prompt --detail` 与 interactive run view 尚未实现：covered by later approved slice。

## Completion Status

Slice A implementation complete. 无 Host / Engine / Service / Fins storage 文件变更，无 runtime schema 或 public contract 变更。

