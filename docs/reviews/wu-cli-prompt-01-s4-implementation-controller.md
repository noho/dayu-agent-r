# WU-CLI-PROMPT-01 S4 Implementation

- Work unit: `WU-CLI-PROMPT-01`
- Gate: `implementation`
- Slice: `S4 — Invocation UTF-8 and log destination error ownership`
- Owner: `controller`
- Timestamp: `2026-07-31 18:52:43 +0800`
- Prerequisite accepted commit: `3c892188`

## Root cause 与语义 owner

### Invalid UTF-8

POSIX raw argv 由 Python 通过 surrogateescape 形成 `str` 后，旧公共 parser 直接交给 argparse；surrogate 因而可以进入命令 runner、Service/Host 甚至错误输出，造成业务副作用或二次 `UnicodeEncodeError`。CLI invocation text 的唯一 owner 是 `dayu.cli.arg_parsing.parse_cli_args` 的 argparse 前置边界。

### Log-file missing parent

旧 `_open_log_file` 同时把空白路径和所有 `OSError` 打印为 usage diagnostic 并返回 `None`，`main` 统一映射 exit 2。空白 path 是 argv misuse；缺失父目录是运行输出目的地准备失败。CLI typed error classification 与 `main` 的精确 exit mapping 是唯一 owner。

## 修改文件

- `dayu/cli/arg_parsing.py`
  - 显式 argv 或 `sys.argv[1:]` 先物化为 `tuple[str, ...]`。
  - 在 argparse 消费前逐 token strict UTF-8 encode；任一 surrogate 通过 parser 的静态 ASCII-safe、脱敏 diagnostic exit 2。
  - 不输出 token、raw byte、repr 或底层 Unicode 异常，也不使用 replace/ignore/surrogatepass。
- `dayu/cli/errors.py`
  - 新增独立 `CliResourcePreparationError`；不继承 `CliUsageError`。
- `dayu/cli/main.py`
  - `_open_log_file` 对空白 path 抛 `CliUsageError`，对 `OSError` 抛 `CliResourcePreparationError`。
  - `main` 只在显式日志目的地准备边界分别映射 exit 2/1；没有 blanket exception remap。
  - 继续直接 `open(..., "a", encoding="utf-8")`，不创建父目录。
- `tests/cli/test_arg_parsing.py`
  - 覆盖合法中文/emoji、surrogate command/option value/positional、真实 POSIX bytes argv。
  - 断言 stderr strict UTF-8、脱敏、无 traceback/UnicodeEncodeError，且日志资源、runtime log、runner、workspace 均无副作用。
  - missing parent 断言 exit 1、可行动 path/错误、父目录与目标文件不存在、runtime log/runner 零调用；空白 path 保持 exit 2。

## Scope 判定

没有修改 Host/Service/Engine 编码、stdin/env/config/provider 文本，不吞掉非法文本，不创建目录，不新增事务回滚或竞态处理。两个错误只在各自 CLI owner boundary 分类，primary operation 未启动。

## 验证证据

1. 定向 owner tests：
   - `pytest -q tests/cli/test_arg_parsing.py -k 'utf8 or invalid_utf8 or log_file_parent or log_file_is_empty'`
   - `8 passed`。
2. 受影响完整回归与覆盖率：
   - `pytest -q tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov=dayu.cli.errors --cov-report=term-missing`
   - `153 passed`。
   - `arg_parsing.py 100%`、`errors.py 100%`、`main.py 94%`。
3. 静态类型：
   - `pyright dayu/cli/arg_parsing.py dayu/cli/main.py dayu/cli/errors.py tests/cli/test_arg_parsing.py`
   - `0 errors, 0 warnings, 0 informations`。
4. 安装后真实 console probes：
   - raw `0xff` positional：exit 2；stdout 空；stderr strict UTF-8 且仅静态错误；workspace/log file 均不存在。
   - missing log parent：exit 1；stdout 空；stderr 包含目标 path 与 `No such file or directory`；workspace、父目录、日志文件均不存在。
5. `git diff --check`：通过。

## README 判定

用户可见 `--log-file` parent 预建要求与 UTF-8 测试职责需要同步，按 accepted plan 在 S6 统一更新根 README 与 tests README。

## 残余风险与后续验证

- 最终必须用 frozen `prompt.PC-BD-03-invalid-utf8-positional` 的 raw bytes exec 与 P62 exact argv 重放，并核对 filesystem diff、Host/runtime SQLite、EventLog/Tool Trace 零副作用；当前真实 probe 与 owner tests不替代 registry evidence。
- 当前 parser usage 仍展示 S5 尚未完成的旧日志等级 choices；S5 会按 prerequisite 顺序修复该共享 contract，不影响 S4 的 UTF-8/exit owner。

## Gate 结论

S4 实现与验证完成，进入独立 `deepreview` gate。
