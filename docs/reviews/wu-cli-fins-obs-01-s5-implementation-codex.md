# WU-CLI-FINS-OBS-01 Slice S5 Implementation

## 结论

Slice S5 已完成：CLI main 恢复顶层日志装配；Fins direct CLI / Service 增加有界 stdlib 诊断日志；scoped command UI print / log 路径已审计并由测试或直接代码证据覆盖。

## 改动

- `dayu/cli/main.py`
  - 在 `parse_cli_args(argv)` 成功后、runner 执行前调用 `dayu.runtime.log.set_level_from_flags(...)`。
  - main 不实现日志优先级映射；当前 argparse 已把 `--debug` / `--verbose` / `--quiet` / `--log-level` 归一到 `args.log_level`，main 只把解析结果交给 runtime log helper。
  - main 只导入层中立日志装配入口 `dayu.runtime.log`。

- `dayu/cli/commands/fins.py`
  - 增加 stdlib logger。
  - VERBOSE：command start、job started、event received、terminal closeout、cancel requested。
  - DEBUG：event sequence、event label、status、bounded payload key count / keys。
  - ERROR：Service stream failure、cancel request failure。
  - progress / terminal summary 仍只通过 UI renderer 输出，不用日志替代。

- `dayu/service/fins_direct.py`
  - 增加 stdlib logger。
  - VERBOSE：Service command start、job started、runtime event received、terminal closeout、cancel requested。
  - DEBUG：runtime event sequence、event type、source event type、bounded payload key count / keys。
  - WARN：保留 terminal event sidecar 缺失时的 bounded terminal fallback。
  - ERROR：event read failure、terminal fallback read failure、cancel request failure。

- `tests/cli/test_arg_parsing.py`
  - 增加 CLI main spy 测试，验证 `--debug`、`--verbose`、`--quiet`、`--log-level warn` 的解析结果进入 `dayu.runtime.log.set_level_from_flags(...)`。
  - 测试不在 main 层重复断言 runtime log 的优先级映射。

- `tests/cli/test_fins_commands.py`
  - 增加默认日志不污染 progress stdout 的断言。
  - 增加 `--verbose` 执行骨架日志与 `--debug` event detail 诊断输出断言。

- `tests/README.md`
  - 按测试 README 职责补充 CLI log assembly 与 Fins direct UI/log 区分覆盖说明。

## Scoped Command Audit

| 命令 | 结论 | 依据 |
| --- | --- | --- |
| `init` | 正常 | `tests/cli/test_init_command.py` 覆盖 success、overwrite/reset、usage/error、copy SIGINT；本片完整 CLI 矩阵通过，日志装配未破坏 stdout/stderr。 |
| `prompt` | 正常；不新增 token streaming | `tests/cli/test_prompt_command.py` 覆盖 terminal final answer、outbox fallback、FAILED、SIGINT cancel；本片保持终态 UI，不扩大运行中 content streaming。 |
| `interactive` | 正常；不新增 token streaming | `tests/cli/test_interactive_command.py` 覆盖多轮终态 UI、FAILED/CANCELLED/LOST、运行态 SIGINT 与二次 SIGINT 本地退出；本片保持终态 UI。 |
| `download` | 本条修复 / 保护 | S4 已接 Service event stream 输出 progress / terminal；S5 验证默认日志不污染 progress，`--verbose` / `--debug` 输出诊断。 |
| `upload_filing` | 本条修复 / 保护 | 参数映射、progress / terminal summary、默认日志不污染输出由 `tests/cli/test_fins_commands.py` 覆盖。 |
| `upload_material` | 本条修复 / 保护 | 参数映射、progress / terminal summary、默认日志不污染输出由 `tests/cli/test_fins_commands.py` 覆盖。 |
| `process` | 本条修复 / 保护 | preprocess 参数映射、progress / terminal summary、默认日志不污染输出由 `tests/cli/test_fins_commands.py` 覆盖。 |
| `process_filing` | 本条修复 / 保护 | preprocess 参数映射、progress / terminal summary、默认日志不污染输出由 `tests/cli/test_fins_commands.py` 覆盖。 |
| `process_material` | 本条修复 / 保护 | preprocess 参数映射、progress / terminal summary、默认日志不污染输出由 `tests/cli/test_fins_commands.py` 覆盖。 |
| `upload_filings_from` | 正常；不 live stream | `tests/cli/test_upload_filings_from_command.py` 覆盖 stdout script、`--output` 写入、错误码、扫描期 SIGINT，并确认不启动 live event stream。 |

## README Decision

- `tests/README.md`：已更新。原因是本片新增 CLI log assembly 与 Fins direct UI/log 区分测试覆盖。
- `dayu/README.md`：不更新。本片只恢复 CLI main 调用既有 runtime log 装配入口，现有“日志与可观测性”章节已经描述 runtime log 真源和日志/UI职责；不做 S6 总览同步。
- `dayu/service/README.md`：不更新。`fins_direct` event observation 边界已在前序 slice 同步，本片仅补内部诊断日志，不改变 Service public boundary。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py -q`
  - 结果：110 passed, 3 warnings。
  - warnings：来自 edgar 依赖的 DeprecationWarning，非本片新增失败。

- `source .venv/bin/activate && python -m pyright dayu/cli/main.py dayu/cli/commands/fins.py dayu/service/fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py`
  - 结果：0 errors, 0 warnings, 0 informations。

- `git diff --check`
  - 结果：通过。

## Residual Risk

- 未新增 residual risk。
- prompt / interactive 运行中 token/content streaming 仍按批准计划排除在本片之外；如后续需要，应由独立 Agent command streaming/UI work unit 承接。
