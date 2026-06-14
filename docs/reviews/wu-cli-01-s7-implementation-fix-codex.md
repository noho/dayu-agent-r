# WU-CLI-01 / CLI-01-S7 implementation fix

## Gate

- gate: implementation fix
- work unit: WU-CLI-01
- slice: CLI-01-S7 init current-schema workspace bootstrap
- finding: S7-RV-F02
- artifact path: `docs/reviews/wu-cli-01-s7-implementation-fix-codex.md`

## Scope

本轮只修复 controller accepted finding S7-RV-F02。未处理 rejected findings S7-RV-F01 / S7-RV-F03，未进入 re-review、commit、push 或 PR。

## First-principles judgment

S7-RV-F02 成立。`run_init_command` 读取 `args.reset`，且 `reset` 与 `overwrite` 同为 `init` 的布尔参数；真实 argparse 路径会由 `store_true` 给 `reset` 写入默认 `False`，但 `ParsedCliArgs` 与 `_new_default_namespace()` 未显式声明 / 初始化该字段，导致 typed CLI namespace 与 runtime attribute 不一致。

root cause 在 `dayu/cli/arg_parsing.py` 的 namespace contract，而不是 `run_init_command` 的读取路径。最佳修复是补齐 typed namespace 字段与默认值，不在 init runner 内用 `getattr` 或兼容分支兜底。

## Changed files

- `dayu/cli/arg_parsing.py`
  - 在 `ParsedCliArgs` 中补充 `reset: bool`。
  - 在 `_new_default_namespace()` 中设置 `namespace.reset = False`。
- `tests/cli/test_arg_parsing.py`
  - 新增 `test_default_namespace_initializes_reset_false`，验证 `parse_cli_args(("init",))` 下 `reset` 与 `overwrite` 默认为 `False`，并验证非 init 命令也从默认 namespace 获得 `reset=False`。

## Docs decision

- `tests/README.md`：不更新。原因是本轮没有新增测试层级、运行入口或测试职责，只是在既有 `tests/cli/` parser 覆盖面中补充一个字段一致性断言；当前 README 已记录 CLI parser factory 与 init 测试覆盖。
- `docs/host/ui-implementation-control.md`：不更新。用户明确要求只写本 fix artifact，不进入 re-review / commit / push / PR；总控状态仍停在 fix gate。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py -q`
  - result: 35 passed, 3 warnings
  - warnings: 既有 `edgar` 依赖弃用警告
- `source .venv/bin/activate && pytest tests/cli -q`
  - result: 94 passed, 3 warnings
  - warnings: 既有 `edgar` 依赖弃用警告
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: 0 errors, 0 warnings, 0 informations
  - note: pyright 提示存在新版本 v1.1.410，未影响结果
- `git diff --check`
  - result: clean

## Finding status

- S7-RV-F02: 已修复。

## Residual risks and uncovered areas

- fixed in current slice: typed CLI namespace 与 runtime default namespace 的 `reset` 字段一致性。
- assigned to later work unit: 无。
- requiring new issue or explicit user decision: 无。

## Stop condition

按用户要求，本轮完成 S7-RV-F02 fix 与 required validation 后停止；不进入 re-review、commit、push 或 PR。
